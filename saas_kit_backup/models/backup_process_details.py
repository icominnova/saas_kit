# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
#
#################################################################################

import os
from odoo import fields, api, models
from odoo.exceptions import UserError
from odoo.addons.wk_backup_restore.models.lib import check_connectivity


import logging

_logger = logging.getLogger(__name__)

class SaasBackupProcessDetails(models.Model):
    _inherit = 'backup.process.detail'

    saas_client_id = fields.Many2one(comodel_name='saas.client', string="Saas Client",related="backup_process_id.saas_client_id")
    
    def download_db_file(self):
        """
            Called by the download button over every backup detail record.
            Overrided the method to download the zip file of remote saas client backups 
        """
        if self.backup_process_id.saas_client_id:
            saas_client = self.backup_process_id.saas_client_id
            if saas_client.server_id and saas_client.server_id.host_server == 'remote':
                if self.backup_location == 'local':
                    file_get_status = self.get_saas_remote_backup_file()
                    if not file_get_status:
                        raise UserError("Cannot download local backup file from remote saas server. Follow logs for more details.")
                return self.get_saas_backup_download_url()

        return super(SaasBackupProcessDetails, self).download_db_file()


    def get_saas_remote_backup_file(self):
        """
            Method to copy the backup file from the remote saas server to the main server

            Returns:
                [Boolean]: True in case file is successfully copied or False
        """
        try:
            saas_client = self.backup_process_id.saas_client_id
            host_server, _ = saas_client.server_id.get_server_details()
            response = check_connectivity.ishostaccessible(host_server)
            
            if not response.get('status'):
                return False
            
            ssh_obj = response.get('result')
            sftp = ssh_obj.open_sftp()
            sftp.get(self.url, '/tmp/'+self.file_name)
            sftp.close()
            _logger.info("======== Backup file successfully copied to the local server. ===========")
            return True
        except Exception as e:
            _logger.info(f"======= Exception while copying the backup file from the remote server ======= {e} ")
            return False



    def get_saas_backup_download_url(self):
        """
            Method to get the download url of the saas backup file to be downloaded
            Called from the download_db_file method after the saas backup file is successfully 
            copied to the main server from saas remote server.
        """
        backup_file_path = None
        download_url = None
        if self.backup_location == 'local':
            backup_file_path = "/tmp/"+self.file_name
            download_url = f"/backupfile/download?path={backup_file_path}&backup_location=local"
        else:
            backup_copy_status = self.get_remote_backup_file()
            if backup_copy_status:
                backup_file_path = self.backup_process_id.remote_server_id.temp_backup_dir+"/"+self.file_name
                download_url = f"/backupfile/download?path={backup_file_path}&backup_location=remote"
            else:
                raise UserError("Cannot download remote backup file from remote server. Follow logs for more details.")
            
        if self.status == "Success" and os.path.exists(backup_file_path):
            return  {
                        'type': 'ir.actions.act_url',
                        'url': download_url,
                        'target': 'new',
                    }
        else:
            raise UserError("Backup doesn't exists.")
