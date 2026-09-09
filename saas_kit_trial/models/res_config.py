# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import api, fields, models
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auto_purchase_reminder = fields.Boolean(string="Auto Purchase Reminder")
    enable_renew_mail_trial_contract = fields.Boolean(string="Send Renew mail to continue the Trial contract")
    renew_period_trial_contract = fields.Integer(string="Renew Ends for trial contract")
    no_of_mails_trial_contract = fields.Integer(string="No of Renew Mail for trial contract", default = 3)
    stop_client_trial_contract = fields.Boolean(string="Stop trial client after last warning")
    drop_trial_contract = fields.Boolean(string="Delete Saas Client")
    buffer_trial_contract = fields.Integer(string="Buffer for trial contract", default = 3)
    reminder_mail_count = fields.Integer(string="Purchase reminder ends after (mails)" , default=3)

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        IrDefault = self.env['ir.default'].sudo()
        IrDefault.set('res.config.settings', 'auto_purchase_reminder', self.auto_purchase_reminder)
        IrDefault.set('res.config.settings', 'reminder_mail_count', self.reminder_mail_count)
        if not self.enable_renew_mail:
            self.enable_renew_mail_trial_contract = False
        IrDefault.set('res.config.settings', 'enable_renew_mail_trial_contract', self.enable_renew_mail_trial_contract)
        if not self.enable_renew_mail_trial_contract:
            self.renew_period_trial_contract = 0 
            self.no_of_mails_trial_contract = 0
            self.stop_client_trial_contract = False

        if self.no_of_mails_trial_contract>self.renew_period_trial_contract:
            raise UserError(f"No of mail should be less than or equal to Renew period.")
        
        IrDefault.set('res.config.settings', 'renew_period_trial_contract', self.renew_period_trial_contract)
        IrDefault.set('res.config.settings', 'no_of_mails_trial_contract', self.no_of_mails_trial_contract)
        IrDefault.set('res.config.settings', 'stop_client_trial_contract', self.stop_client_trial_contract)
        if not self.stop_client_trial_contract:
            self.drop_trial_contract = False

        IrDefault.set('res.config.settings', 'drop_trial_contract', self.drop_trial_contract)
        if not self.drop_trial_contract:
            self.buffer_trial_contract = 7

        IrDefault.set('res.config.settings', 'buffer_trial_contract', self.buffer_trial_contract)
        return True

    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        IrDefault = self.env['ir.default'].sudo()
        res.update(
            {
                'auto_purchase_reminder': IrDefault._get('res.config.settings', 'auto_purchase_reminder'),
                'reminder_mail_count': IrDefault._get('res.config.settings', 'reminder_mail_count') or 3, 
                'enable_renew_mail_trial_contract': IrDefault._get('res.config.settings', 'enable_renew_mail_trial_contract'),
                'renew_period_trial_contract': IrDefault._get('res.config.settings', 'renew_period_trial_contract'),
                'no_of_mails_trial_contract': IrDefault._get('res.config.settings', 'no_of_mails_trial_contract'),
                'stop_client_trial_contract': IrDefault._get('res.config.settings', 'stop_client_trial_contract'),
                'drop_trial_contract': IrDefault._get('res.config.settings', 'drop_trial_contract'),
                'buffer_trial_contract': IrDefault._get('res.config.settings', 'buffer_trial_contract'),
            }
        )
        return res
