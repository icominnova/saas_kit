# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import fields, models
import logging
_logger = logging.getLogger(__name__)


class AccountInvoice(models.Model):
    _inherit = 'account.move'

    contract_id = fields.Many2one(comodel_name='saas.contract', string='SaaS Contract', help="Saas Contract related to this sale order")




class AccountPaymentInherit(models.Model):
    _inherit = 'account.payment'
    _description = "Account Payment Inherit Model"


    def action_post(self):
        result = super(AccountPaymentInherit,self).action_post()
        if self.memo:
            move_id = self.env["account.move"].sudo().search([("name","=",self.memo)])
            if move_id:
                if move_id.contract_id and move_id.contract_id.is_renewal_requested:
                    move_id.contract_id.renew_contract()
        return result
    
    
    def write(self, vals):
        result = super(AccountPaymentInherit,self).write(vals)
        for rec in self:
            if rec.state == "posted":
                move_id = self.env["account.move"].sudo().search([("name","=",rec.payment_transaction_id.reference)])
                if move_id:
                    if move_id.contract_id and move_id.contract_id.is_renewal_requested:
                        move_id.contract_id.renew_contract()
        return result
