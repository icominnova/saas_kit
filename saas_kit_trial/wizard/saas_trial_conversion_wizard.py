# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import models, api, fields
from dateutil.relativedelta import relativedelta
from odoo import fields, api, models
import datetime
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class SaasTrialConversionWizard(models.TransientModel):
    _name = 'saas.trial.conversion'
    _description = "Saas Trial Contract Conversion Wizard"
    
    
    contract_id = fields.Many2one(comodel_name="saas.contract", string="Saas Contract", help="Saas Trial Contract")
    convert_type = fields.Selection([("same_instance", "Same Instance"), ("new_instance", "New Instance")], default="same_instance", string="Conversion Type", help="Conversion Type of the Saas Trial Contract")

    
    def convert_trial_contract(self):
        old_contract = self.contract_id
        if self.convert_type == "same_instance":
            old_contract.is_trial_enabled = False
            if old_contract.state == 'trial_expired':
                old_contract.state = 'confirm'
            old_contract.start_date = fields.Date.from_string(fields.Date.today())
            old_contract.remaining_cycles = old_contract.total_cycles
            # recurring_interval_delta = relativedelta(months=(int(old_contract.recurring_interval * old_contract.total_cycles)))                
            # old_contract.next_invoice_date = fields.Date.from_string(fields.Date.today()) + recurring_interval_delta
            self.env.cr.commit()
            old_contract.set_trial_data()
            old_contract.resume_trial_contract()
            old_contract.generate_invoice()
        else:
            old_contract.state = 'trial_converted'
            old_contract.saas_client.stop_client()
            old_contract.start_date = fields.Date.from_string(fields.Date.today())
            contract_product = self.env['product.product'].search([('saas_plan_id', '=', old_contract.plan_id.id)], limit=1)
            contract_rate = contract_product.lst_price
            recurring_interval = contract_product.recurring_interval
            total_cycles = old_contract.total_cycles
            is_trial_enabled = False
            trial_period = 0
            
            saas_users = 0
            user_billing = 0
            if contract_product.saas_plan_id.per_user_pricing:
                saas_users = old_contract.saas_users
                user_billing = contract_product.user_cost * total_cycles # need to update this 
            relative_delta = relativedelta(days=trial_period)
            old_date = fields.Date.from_string(fields.Date.today())
            start_date = fields.Date.to_string(old_date + relative_delta)
            recurring_interval_delta = relativedelta(months=(int(recurring_interval * old_contract.total_cycles)))
            server_id = None
            if not contract_product.saas_plan_id.is_multi_server:
                server_id = contract_product.saas_plan_id.server_id.id
            else:
                priority_servers = contract_product.saas_plan_id.default_saas_servers_ids.sorted(lambda s: s.priority)
                for server in priority_servers:
                    if server.server_id.max_clients <= server.server_id.total_clients:
                        continue
                    else:
                        server_id = server.server_id.id
                        break
            vals = dict(
                partner_id=old_contract.partner_id and old_contract.partner_id.id or False,
                recurring_interval=recurring_interval,
                recurring_rule_type=contract_product.saas_plan_id.recurring_rule_type,
                invoice_product_id=contract_product and contract_product.id or False,
                pricelist_id=old_contract.pricelist_id and old_contract.pricelist_id.id or False,
                currency_id=old_contract.pricelist_id and old_contract.pricelist_id.currency_id and old_contract.pricelist_id.currency_id.id or False,
                start_date=start_date,
                total_cycles=total_cycles,
                trial_period=trial_period,
                remaining_cycles=old_contract.total_cycles,
                next_invoice_date=fields.Date.to_string(fields.Date.from_string(start_date) + recurring_interval_delta),
                contract_rate=contract_rate,
                contract_price=contract_rate * total_cycles,
                per_user_pricing=contract_product.saas_plan_id.per_user_pricing,
                user_cost=contract_product.user_cost,
                due_users_price=contract_product.saas_plan_id.due_users_price,
                saas_users=saas_users,
                min_users=contract_product.saas_plan_id.min_users,
                max_users=contract_product.saas_plan_id.max_users,
                user_billing=user_billing,
                total_cost=(contract_rate * total_cycles) + user_billing,
                auto_create_invoice=False,
                saas_module_ids=[(6, 0, contract_product.saas_plan_id.saas_module_ids.ids)],
                on_create_email_template=self.env.ref('odoo_saas_kit.client_credentials_template').id,
                is_multi_server=contract_product.saas_plan_id.is_multi_server,
                server_id=server_id,
                plan_id=contract_product.saas_plan_id.id,
                db_template=contract_product.saas_plan_id.db_template,
                is_trial_enabled=is_trial_enabled,
                trial_started_date=False,
            )
            try:
                record_id = self.env['saas.contract'].create(vals)
                old_contract.converted_contract_id = record_id.id
                _logger.info("------VIA-ORDER--Contract--Created-------%r", record_id)
            except Exception as e:
                _logger.info("-----VIA-ORDER---Exception-While-Creating-Contract-------%r", e)
            else:
                record_id.send_subdomain_email()
