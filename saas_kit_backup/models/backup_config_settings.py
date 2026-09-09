# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import api, fields, models, _
import logging
_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    _description = 'Class for managing global SaaS Backup settings.'

    enable_retention = fields.Boolean(string="Enable Retention", help="Check if you want to drop old backups stored on the server.")
    backup_retention_count = fields.Integer(string="Default Backup Retention Count", help="Count of recent backups that will be retained after dropping old backups on server.")

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        IrDefault = self.env['ir.default'].sudo()
        IrDefault.set('res.config.settings', 'enable_retention', self.enable_retention)
        IrDefault.set('res.config.settings', 'backup_retention_count', self.backup_retention_count)
        return True

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        IrDefault = self.env['ir.default'].sudo()
        res.update(
            enable_retention=IrDefault._get('res.config.settings', 'enable_retention'),
            backup_retention_count=IrDefault._get('res.config.settings', 'backup_retention_count') or 7,
        )
        return res
