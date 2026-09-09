# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
#
#################################################################################
from odoo import fields, api, models, tools, _
from dateutil.relativedelta import relativedelta
from werkzeug.urls import url_encode
from odoo.exceptions import UserError, ValidationError
import random
import string
from odoo.addons.auth_signup.models.res_partner import random_token as generate_token
from . lib import query
from odoo.addons.odoo_saas_kit.models.lib import query as query2
import datetime
import logging
_logger = logging.getLogger(__name__)


class SaaSTrialContract(models.Model):
    _inherit = 'saas.contract'

    is_trial_enabled = fields.Boolean(default=False, string="Is Trial", readonly=True)
    purchase_reminder_sent = fields.Boolean(default=False)
    reminder_show = fields.Boolean(default=False, compute="check_trial_expiry")
    state = fields.Selection(selection_add=[('trial_expired', 'Trial Expired'), ('trial_converted', 'Trial Closed')])
    converted_contract_id = fields.Many2one(comodel_name="saas.contract", string="Converted Contract")
    trial_started_date = fields.Date(string="Trial Start Date")
    trial_data_enabled = fields.Boolean(default=False)

    trial_expiry_set = fields.Boolean(default=False)
    reminder_mail_count = fields.Integer(string="Purchase reminder mail Count" , default=0)
    trial_invoice_product = fields.Many2one(comodel_name="product.product", string="Trial Product", domain="[('is_trial_price', '=', True)]", default=None)

    @api.model
    def check_contract_expiry(self):
        self.trial_purchase_reminder()
        contracts = self.search([('state', 'in', ['trial_expired']), ('remaining_cycles', '=', 0), ('domain_name', '!=', False)])
        _logger.info("-------  Trial Contract Expiry Cron ------")
        for contract in contracts:
            if (contract.plan_id.trial_product and not contract.trial_expiry_set):
                _logger.info("--------Trial--records  %r    "%contract.id)
                database = contract.saas_client and contract.saas_client.database_name or False
                _, db_server = contract.server_id.get_server_details()
                response = query2.set_contract_expiry(database, str(True), db_server=db_server)

                if response.get('status'):
                    contract.saas_client.restart_client()
                    contract.trial_expiry_set = True
                else:
                    _logger.info("-------   Exception While writing on client's Instance ------")
                contract._cr.commit()
        super(SaaSTrialContract, self).check_contract_expiry()
        
    def resume_trial_contract(self):
        """
        Called after successfully purchasing the trial contracts to resume the normal working of client's instance.
        """
        for obj in self:
            database = obj.saas_client and obj.saas_client.database_name or False
            _, db_server = obj.server_id.get_server_details()
            response = query2.set_contract_expiry(database, str(False), db_server=db_server)
            if response.get('status'):
                obj.saas_client.restart_client()
            else:
                _logger.info("---------    Error while Updating Trial Contract expiry  data ---------")
            obj._cr.commit()
            _logger.info("---------  Trial Contract Resuming ---------")


    @api.model
    def check_trial_expiry(self):
        today_date = datetime.date.today()
        for rec in self:
            if rec.is_trial_enabled and (rec.state not in ['trial_converted', 'hold', 'expired', 'cancel']) and (today_date >= rec.start_date):
                rec.state = 'trial_expired'
                rec.reminder_show = True
                return True
            else:
                rec.reminder_show = False
                
                
    def trial_purchase_reminder(self):
        contracts = self.env['saas.contract'].search([('is_trial_enabled','=',True),('start_date','<=',datetime.date.today())])
        today_date = datetime.date.today()
        for rec in contracts:
            rec.check_trial_expiry()
            

    @api.model
    def purchase_reminder_reminder(self):
        IrDefault = self.env['ir.default'].sudo()
        auto_purchase_reminder = IrDefault._get('res.config.settings', 'auto_purchase_reminder')
        reminder_mail_count = IrDefault._get('res.config.settings', 'reminder_mail_count')
        contracts = self.env['saas.contract'].search([('is_trial_enabled','=',True),('start_date','<=',datetime.date.today()),('reminder_mail_count','<',reminder_mail_count)])
        for contract in contracts:
            if contract.check_trial_expiry():
                if auto_purchase_reminder:
                    contract.send_reminder()
                    contract.reminder_mail_count+=1

    def send_reminder(self):
        for obj in self:
            template = self.env.ref('saas_kit_trial.saas_purchase_reminder_template')
            mail_id = template.send_mail(obj.id)
            current_mail = self.env['mail.mail'].sudo().browse(mail_id)
            current_mail.send()
            self.purchase_reminder_sent = True
            self.message_post(body="Purchase reminder has been sent to Client", subject="one")


    def create_saas_client(self):
        for obj in self:
            if not obj.domain_name:
                raise UserError("Please select a domain first!")
            if obj.under_process:
                raise UserError("Client Creation Already Under Progress!")
            if not obj.pricelist_id:
                raise UserError("Please set the pricelist for the contract first!")
            else:
                domain_name = None
                if obj.use_separate_domain:
                    domain_name = obj.domain_name
                else:
                    domain_name = "{}.".format(obj.domain_name)   # is edited
                obj.under_process = True
                self.env.cr.commit()
                obj.check_server_status()
                contracts = self.sudo().search([('domain_name', '=ilike', obj.domain_name), ('state', '!=', 'cancel')])
                if len(contracts) > 1:
                    _logger.info("---------ALREADY TAKEN--------%r", contracts)
                    obj.under_process = False
                    obj.domain_name = False
                    self.env.cr.commit()
                    raise UserError("This domain name is already in use! Please try some other domain name!")
                obj.under_process = True
                self.env.cr.commit()
                if not obj.use_separate_domain:
                    domain_name = domain_name+'{}'.format(obj.saas_domain_url)
                if obj.server_id.max_clients <= obj.server_id.total_clients:
                    obj.under_process = False
                    self.env.cr.commit()
                    raise UserError("Maximum Clients limit reached!")
                vals = dict(
                    saas_contract_id = obj.id,
                    partner_id = obj.partner_id and obj.partner_id.id or False,
                    server_id = obj.server_id.id,
                )
                client_id = self.env['saas.client'].search([('saas_contract_id', '=', obj.id)])
                if client_id:
                    client_id.write(vals)
                else:
                    client_id = self.env['saas.client'].search([('database_name', '=', domain_name)])
                    if client_id:
                        obj.under_process = False
                        self.env.cr.commit()
                        raise UserError("This domain name is already in use with other client! Please try some other domain name!")
                    else:
                        client_id = self.env['saas.client'].create(vals)
                obj.attach_modules(client_id)
                obj.write({'saas_client': client_id.id})
                self.env.cr.commit()
                try:
                    client_id.fetch_client_url(domain_name)
                    _logger.info("--------Client--Created-------%r", client_id)
                except Exception as e:
                    obj.under_process = False
                    self.env.cr.commit()
                    _logger.info("--------Exception-While-Creating-Client-------%r", e)
                    raise UserError("Exceptionc While Creating Client {}".format(e))
                else:
                    obj.write({'state': 'open'})
                    obj.under_process = False
                    self.env.cr.commit()
                    if client_id.client_url:
                        try:
                            token = generate_token()
                            if (obj._fields.get('version_code') and int(obj.version_code[:2]) >= 18) or not obj._fields.get('version_code'):
                                token = obj.generate_signup_auth_token()
                                all_characters = string.ascii_letters + string.digits + string.punctuation
                                temp_password = ''.join(random.choices(all_characters, k=10))
                                client_id.temp_password = temp_password
                            _logger.info("--------------%r", token)
                            obj.sudo().set_user_data(token=token)
                            obj.sudo().set_trial_data()
                            self.env.cr.commit()
                        except Exception as e:
                            _logger.info("--------EXCEPTION-WHILE-UPDATING-DATA-AND-SENDING-INVITE-------%r----", e)
                            raise UserError(f'Exception while updating client data:{e}')
                        else:
                            reset_pwd_url = "{}/web/signup?token={}&db={}".format(client_id.client_url, token, client_id.database_name)
                            client_id.invitation_url = reset_pwd_url
                            template = obj.on_create_email_template
                            mail_id = template.send_mail(client_id.id)
                            current_mail = self.env['mail.mail'].sudo().browse(mail_id)
                            res = current_mail.send()
                            obj.write({'state': 'confirm'})
                            self.env.cr.commit()
                            try:
                                # if obj.from_backend:
                                ''' ----- Functionality to check the trial converted contract ---------'''
                                trial_converted_contract = self.search([('converted_contract_id', '=', obj.id)], limit=1)
                                is_trial_converted = True if len(trial_converted_contract) else False
                                if obj.from_backend or (is_trial_converted and not obj.sale_order_line_id):
                                    obj.generate_invoice(first_invoice=True)
                                    if obj.is_trial_enabled:
                                        obj.next_invoice_date = obj.start_date
                                elif obj.per_user_pricing:
                                    obj.update_billing_history(first=True)
                                    obj.previous_cycle_user = max(obj.min_users, obj.saas_users)
                            except Exception as e:
                                _logger.info("----------------  Exception While creating invoice-----------------")
                            return res

    def send_credential_email(self):
        self.ensure_one()
        if not self.saas_client.client_url:
            raise UserError("SaaS Instance Not Found! Please create it from the associated client record for sharing the credentials.")
        template = self.on_create_email_template
        compose_form = self.env.ref('mail.email_compose_message_wizard_form')


        if True:
            try:
                token = generate_token()
                if (self._fields.get('version_code') and int(self.version_code[:2]) >= 18) or not self._fields.get('version_code'):
                    token = self.generate_signup_auth_token()
                self.sudo().set_user_data(token=token)
                self.sudo().set_trial_data()
                self.env.cr.commit()
                reset_pwd_url = "{}/web/signup?token={}&db={}".format(self.saas_client.client_url, token, self.saas_client.database_name)
                self.saas_client.invitation_url = reset_pwd_url
                self.state = 'confirm'
            except Exception as e:
                _logger.info("--------EXCEPTION-WHILE-UPDATING-DATA-AND-SENDING-INVITE-------%r----", e)
                raise UserError(f'Exception while updating client data:{e}')
            
        ctx = dict(
            default_model='saas.client',
            default_res_ids=[self.saas_client.id],
            default_use_template=bool(template),
            default_template_id=template and template.id or False,
            default_composition_mode='comment',
        )
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    def set_trial_data(self):
        web_base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        web_base_url = web_base_url.replace('https://', '').replace('http://', '')
        web_base_url = 'http://'+web_base_url
        for obj in self:
            if hasattr(obj, 'is_trial_enabled'):
                trial_data = dict()
                trial_data['trial.is_trial_enabled'] = str(obj.is_trial_enabled)
                trial_data['trial.trial_period'] = str(obj.trial_period)
                trial_data['trial.purchase_link'] = web_base_url+obj.get_contract_url()
                _, db_server = obj.server_id.get_server_details()
                database = obj.saas_client and obj.saas_client.database_name or False
                response = query.set_trial_data(database, trial_data, db_server=db_server)
                if response.get('status'):
                    obj.trial_data_enabled = True
                    self.env.cr.commit()
                    if not obj.is_trial_enabled:
                        try:
                            obj.saas_client.restart_client()
                        except:
                            raise UserError("Unable To Write Trial Data")
                    _logger.info("------------------  Trial Date Updated ------")
                else:
                    _logger.info("------------------  Trial Date Exception ------")
                    obj.trial_data_enabled = False
                    self.env.cr.commit()
                    raise UserError("Unable To Write Trial Data")

    def update_trial_data(self):
        """
        Called from The button "Set Trial Data in the Contract Form"
        """
        for obj in self:
            obj.sudo().set_trial_data()


    @api.model
    def renew_mail_cron_action(self):
        IrDefault = self.env['ir.default'].sudo()
        enable_renew_mail = IrDefault._get('res.config.settings', 'enable_renew_mail')
        enable_renew_mail_trial_contract = IrDefault._get('res.config.settings', 'enable_renew_mail_trial_contract')
        renew_period_trial_contract = IrDefault._get('res.config.settings', 'renew_period_trial_contract')
        no_of_mails_trial_contract = IrDefault._get('res.config.settings', 'no_of_mails_trial_contract')
        stop_client_trial_contract = IrDefault._get('res.config.settings', 'stop_client_trial_contract')
        drop_trial_contract = IrDefault._get('res.config.settings', 'drop_trial_contract')
        buffer_trial_contract = IrDefault._get('res.config.settings', 'buffer_trial_contract')
        if not enable_renew_mail or not enable_renew_mail_trial_contract or not renew_period_trial_contract:
            return super(SaaSTrialContract,self).renew_mail_cron_action()
        starting_date = fields.Date.today() - relativedelta(days=renew_period_trial_contract)
        contracts = self.env['saas.contract'].sudo().search([ ('start_date', '>=', starting_date),('start_date', '<=', fields.Date.today()), ('state', '=', 'trial_expired'),('is_trial_enabled','=','False')])  # trial converted is added for now will update in future
        logging.info(f"========for trial==========={contracts}")
        for contract in contracts:
            contract.renew_deadline_date = contract.next_invoice_date + relativedelta(days=renew_period_trial_contract)
            gap_factor = renew_period_trial_contract / no_of_mails_trial_contract
            next_period = renew_period_trial_contract - ((no_of_mails_trial_contract - contract.delivered_renew_mail)*gap_factor)
            # contract.send_renew_reminder_mail()
            # contract.delivered_renew_mail -=1
            if next_period <= 0 and contract.delivered_renew_mail != no_of_mails_trial_contract:
                contract.send_renew_reminder_mail()
            else:
                next_date = fields.Date.today() - relativedelta(days=next_period)
                if next_date <= contract.next_invoice_date and contract.delivered_renew_mail != no_of_mails_trial_contract:
                    contract.send_renew_reminder_mail()
            if contract.saas_client and contract.saas_client.container_id and stop_client_trial_contract and contract.delivered_renew_mail >= no_of_mails_trial_contract and contract.renew_deadline_date<=fields.Date.today():
                logging.info("===========trial stop client==============")
                contract.saas_client.stop_client()
            if drop_trial_contract and contract.saas_client.state == "stop" and contract.next_invoice_date>= fields.Date.today()-relativedelta(days=(renew_period_trial_contract + buffer_trial_contract)):
                contract.saas_client.inactive_client()
                contract.saas_client.drop_container()
                contract.saas_client.drop_db()
        return super(SaaSTrialContract,self).renew_mail_cron_action()
    
    
    def generate_invoice(self, first_invoice=None):
        for obj in self:
            if obj.trial_invoice_product and obj.is_trial_enabled:
                if obj.remaining_cycles:
                    user_count = None
                    data = {}
                    if obj.per_user_pricing:
                        if obj.saas_client and obj.saas_client.database_name:
                            _, db_server = obj.server_id.get_server_details()
                            response = query.get_user_count(obj.saas_client.database_name, db_server=db_server)
                            
                            if response.get('status'):
                                response = response.get('result')
                                user_count = response[0][0]
                            else:
                                raise UserError(response.get('message'))
                            if obj.plan_id.max_users != -1 and user_count > obj.plan_id.max_users:
                                raise UserError("Client have crossed the maximum user limit.")
                            user_count = max(user_count, obj.saas_users)
                            if user_count > obj.previous_cycle_user:
                                arrer_response = query.get_arrear_users(
                                    obj.saas_client.database_name,
                                    db_server=db_server,
                                    limit = user_count - obj.previous_cycle_user,
                                )
                                if not arrer_response.get('status'):
                                    raise UserError("Couldn't fetch arrer users! Please try again.")
                                data = obj.calculate_arrear_price(arrer_response)

                        if not user_count:
                            raise UserError("Couldn't fetch user count! Please try again later.")                    
                    try:
                        price = None                    
                        if first_invoice == True:
                            if obj.per_user_pricing:
                                obj.update_billing_history(first=True)
                                obj.previous_cycle_user = max(obj.min_users, obj.saas_users)
                            price = obj.total_cost
                        else:
                            if obj.per_user_pricing:
                                res = obj.update_billing_history(arrear_users=data.get('arrear_users', 0), arrear_price=data.get('total_price', 0))
                                price = res.get('total_cost', 0) + obj.contract_rate
                                obj.previous_cycle_user = res.get('new_users', obj.previous_cycle_user)
                            else:
                                price = obj.contract_rate
                        
                        invoice_vals = {
                            'move_type': 'out_invoice',
                            'partner_id': obj.partner_id and obj.partner_id.id or False,
                            'currency_id': obj.pricelist_id and obj.pricelist_id.currency_id.id or False,
                            'contract_id': obj.id,
                            'invoice_line_ids': [(0, 0, {
                                'price_unit': obj.trial_invoice_product.lst_price,
                                'quantity': 1.0,
                                'product_id': obj.trial_invoice_product.id,
                            })],
                        }

                        invoice = self.env['account.move'].sudo().create(invoice_vals)
                        invoice.action_post()
                        obj.send_invoice_mail(invoice)
                        _logger.info("--------Invoice--Created-------%r", invoice)
                    except Exception as e:
                        _logger.info("--------Exception-While-Creating-Invoice-------%r", e)
                        raise UserError("Exception While Creating Invoice: {}".format(e))
                    else:
                        old_date = obj.next_invoice_date and fields.Date.from_string(obj.next_invoice_date) or fields.Date.from_string(fields.Date.today())
                        if first_invoice == True:
                            relative_delta = relativedelta(months=(self.recurring_interval*self.total_cycles))
                            obj.remaining_cycles = 0
                        else:    
                            relative_delta = relativedelta(months=self.recurring_interval)
                            obj.remaining_cycles -= 1
                        next_date = fields.Date.to_string(old_date + relative_delta)
                        obj.next_invoice_date = next_date
                else:
                    raise UserError("This Contract Has Expired!")
            else:
                super(SaaSTrialContract,obj).generate_invoice(first_invoice=first_invoice)
                
                
    def convert_to_paid(self):
        return {
            'name': "Choose Conversion Type",
            'view_mode': 'form',
            'view_id': False,
            "context": {"default_contract_id": self.id},
            'res_model': 'saas.trial.conversion',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
