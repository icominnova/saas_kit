# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    _description = 'Class for managing global SaaS settings'

    auto_create_client = fields.Boolean(string="Automatically create clients from contract via Scheduler.",help="Automatically create clients from contract via Scheduler.")
    enable_renew_mail = fields.Boolean(string="Send Renew mail to continue the contract")
    enable_renew_mail_paid_contract = fields.Boolean(string="Send Renew mail to continue the paid contract")
    renew_period_paid_contract = fields.Integer(string="Renew Ends for paid contract")
    no_of_mails_paid_contract = fields.Integer(string="No of Renew Mail for paid contract", default = 3)
    stop_client_paid_contract = fields.Boolean(string="Stop client after last warning")
    drop_paid_contract = fields.Boolean(string="Delete Saas client")
    buffer_paid_contract = fields.Integer(string="Buffer Period")
    restrict_add_to_cart = fields.Boolean(string="Restrict Cart for Single Saas Plan")
    enable_contract_renewal = fields.Boolean(string="Enable Contract Renewal")
    renew_btn_enable_days = fields.Integer(string="Days since Renew Button visible")

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        IrDefault = self.env['ir.default'].sudo()
        IrDefault.set('res.config.settings', 'auto_create_client', self.auto_create_client)
        IrDefault.set('res.config.settings', 'enable_renew_mail', self.enable_renew_mail)
        if not self.enable_renew_mail:
            self.enable_renew_mail_paid_contract = False

        IrDefault.set('res.config.settings', 'enable_renew_mail_paid_contract', self.enable_renew_mail_paid_contract)
        if not self.enable_renew_mail_paid_contract:
            self.renew_period_paid_contract = 0 
            self.no_of_mails_paid_contract = 0
            self.stop_client_paid_contract = False

        if self.no_of_mails_paid_contract>self.renew_period_paid_contract:
            raise UserError(f"No of mail should be less than or equal to Renew period.")

        IrDefault.set('res.config.settings', 'renew_period_paid_contract', self.renew_period_paid_contract)
        IrDefault.set('res.config.settings', 'no_of_mails_paid_contract', self.no_of_mails_paid_contract)
        IrDefault.set('res.config.settings', 'stop_client_paid_contract', self.stop_client_paid_contract)
        if not self.stop_client_paid_contract:
            self.drop_paid_contract = False

        IrDefault.set('res.config.settings', 'drop_paid_contract', self.drop_paid_contract)
        if not self.drop_paid_contract:
            self.buffer_paid_contract = 7
            
        IrDefault.set('res.config.settings', 'buffer_paid_contract', self.buffer_paid_contract)
        IrDefault.set('res.config.settings', 'restrict_add_to_cart', self.restrict_add_to_cart or False)
        IrDefault.set('res.config.settings', 'enable_contract_renewal', self.enable_contract_renewal or False)
        IrDefault.set('res.config.settings', 'renew_btn_enable_days', self.renew_btn_enable_days)
        return True

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        IrDefault = self.env['ir.default'].sudo()
        res.update(
            {
                'auto_create_client': IrDefault._get('res.config.settings', 'auto_create_client'),
                'enable_renew_mail': IrDefault._get('res.config.settings', 'enable_renew_mail'),
                'enable_renew_mail_paid_contract': IrDefault._get('res.config.settings', 'enable_renew_mail_paid_contract'),
                'renew_period_paid_contract': IrDefault._get('res.config.settings', 'renew_period_paid_contract'),
                'no_of_mails_paid_contract': IrDefault._get('res.config.settings', 'no_of_mails_paid_contract'),
                'stop_client_paid_contract': IrDefault._get('res.config.settings', 'stop_client_paid_contract'),
                'drop_paid_contract': IrDefault._get('res.config.settings', 'drop_paid_contract'),
                'buffer_paid_contract': IrDefault._get('res.config.settings', 'buffer_paid_contract'),
                'restrict_add_to_cart': IrDefault._get('res.config.settings', 'restrict_add_to_cart') or False,
                'enable_contract_renewal': IrDefault._get('res.config.settings', 'enable_contract_renewal') or False,
                'renew_btn_enable_days': IrDefault._get('res.config.settings', 'renew_btn_enable_days'),
            }
        )
        return res
