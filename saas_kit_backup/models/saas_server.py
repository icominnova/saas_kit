# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import models, fields, tools
from odoo.exceptions import UserError


import logging
_logger = logging.getLogger(__name__)


LOCATION = [
    ('local', 'Local'),
    ('remote', 'Remote Server')
]


class SaasServerBackup(models.Model):
    _inherit = 'saas.server'
    
    
    backup_location = fields.Selection(selection=LOCATION, string="Backup Location", default='local')
    retention = fields.Integer(string="Backup Retention")
    remote_server_id = fields.Many2one(comodel_name="backup.remote.server", string="Backup Remote Server", domain=[('state', '=', 'validated')])
    backup_sftp_host = fields.Char(related="remote_server_id.sftp_host")
    backup_sftp_port = fields.Char(related="remote_server_id.sftp_port")
    backup_sftp_user = fields.Char(related="remote_server_id.sftp_user")
    backup_sftp_password = fields.Char(related="remote_server_id.sftp_password")
    def_backup_dir = fields.Char(related="remote_server_id.def_backup_dir")


    def test_remote_host_connection(self):
        if self.remote_server_id:
            return self.remote_server_id.test_host_connection()
