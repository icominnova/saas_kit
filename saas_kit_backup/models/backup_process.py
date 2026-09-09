# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
#
#################################################################################

import os
from datetime import datetime
import paramiko
from odoo import fields, api, models, tools
from odoo.exceptions import UserError
from odoo.tools.config import config

from odoo.addons.wk_backup_restore.models.lib import manage_backup_crons, check_connectivity, saas_client_backup


import logging

_logger = logging.getLogger(__name__)

INSTANCE = [
    ('self', 'Self'),
    ('saas_client', 'SaaS Client'),
]

class SaasBackupProcess(models.Model):
    _inherit = 'backup.process'

    saas_client_id = fields.Many2one(comodel_name='saas.client', string="Linked Client", domain="[('state', '=', 'started')]", help="Select the saas client instances that are started")
    backup_instance = fields.Selection(selection=INSTANCE, string="Backup Instance", default="self", help="Instance whose backup process needs to be created.")


    @api.model_create_multi
    def create(self, vals_list):
        res = None
        for vals in vals_list:
            res = super(SaasBackupProcess,self).create(vals)
            if res.saas_client_id:
                res.saas_client_id.backup_process_id = res.id 
        return res
    
    
    def write(self, vals):
        old_saas_client = None
        if self.saas_client_id:
            old_saas_client = self.saas_client_id
        res = super(SaasBackupProcess, self).write(vals)
        if self.backup_instance == 'saas_client' and self.saas_client_id:
            if old_saas_client and self.saas_client_id.id != old_saas_client.id:
                old_saas_client.backup_process_id = None
            self.saas_client_id.backup_process_id = self.id 
        return res


    def confirm_process(self):
        """
            Overrided method to confirm the saas backup process record
        """

        if self.saas_client_id:
            if self.state == 'draft':

                # Creating the backup log file if doesn't exists
                if not os.path.exists(manage_backup_crons.LOG_FILE_PATH):
                    _logger.info("========== Creating Log File ==========")
                    fp = open(manage_backup_crons.LOG_FILE_PATH, 'x')
                    fp.close()

                if self.backup_location == 'remote':
                    self.validate_remote_backup()
                self.state ="confirm"
        else:
            super(SaasBackupProcess, self).confirm_process()


    def create_backup_request(self):
        if self.saas_client_id:
            self.saas_client_id.get_backup()
        else:
            res = super(SaasBackupProcess, self).create_backup_request()
            return res
    
    
    @api.onchange('backup_instance')
    def change_backup_instance(self):
        """
            Method to change the database name and storage path field
        """
        if self.backup_instance == 'self':
            self.storage_path = None
            self.saas_client_id = None
            self.db_name = self._default_db_name()
        
    
    @api.onchange('saas_client_id')
    def onchange_saas_client(self):
        for rec in self:
            if rec.saas_client_id:
                saas_backup = self.env['backup.process'].sudo().search([('saas_client_id', '=', rec.saas_client_id.id)], limit=1)
                confirmed_saas_backup = saas_backup.filtered(lambda b:b.state in ['confirm', 'running'])
                draft_saas_backup = saas_backup.filtered(lambda b:b.state in ['draft'])
                if confirmed_saas_backup:
                    raise UserError("The chosen saas client has already confirmed/running backup process " + saas_backup.name + ". Please choose another saas client.")
                draft_saas_backup.saas_client_id = None
                rec.storage_path = rec.saas_client_id.container_path
                rec.db_name = rec.saas_client_id.database_name


    def call_backup_script(self, master_pass=None, port_number=None, url=None, db_user=None, db_password=None, kwargs={}):
        """
            Called by create_backup_request method
            Overrided the method to call_backup_script to update the 
            temp backup path for the saas client remote backups 
        """
        if self.saas_client_id:
            kwargs.update(
                is_remote_client = True if self.saas_client_id.server_id.host_server == 'remote' else False,
            )
        return super(SaasBackupProcess, self).call_backup_script(master_pass=master_pass, port_number=port_number, url=url, db_user=db_user, db_password=db_password, kwargs=kwargs)
                

    def _call_local_backup_script(self, master_pass=None, port_number=None, url=None, db_user=None, db_password=None, backup_format="zip", kwargs={}):
        """
            
            Overrided Method to check the local saas backup path on the remote saas server,
            calling script require few arguments, some are passed in this method same are prepared below
        """
        res = None
        saas_client = self.saas_client_id
        if saas_client:
            dir_exist = self.check_saas_backup_path()
            if not dir_exist:
                res = {'status': False}
                return res
        res = super(SaasBackupProcess, self)._call_local_backup_script(master_pass=master_pass, port_number=port_number, url=url, db_user=db_user, db_password=db_password, backup_format=backup_format, kwargs=kwargs)
        return res
    
    
    
    def check_saas_backup_path(self):
        """
            Method to check the existance of the temporary backup path
            for saas client backups
        """
        try:
            saas_client = self.saas_client_id
            bkp_dir = os.path.join(saas_client.data_directory_path, 'backups') 
            if saas_client.server_id.host_server == 'remote':
                host_server, _ = saas_client.server_id.get_server_details()
                response = check_connectivity.ishostaccessible(host_server)
                if not response.get('status'):
                    return False
                
                ssh_obj = response.get('result')

                #check path exist or not
                sftp = ssh_obj.open_sftp()
                try:
                    sftp.chdir(bkp_dir)
                except IOError:
                    sftp.mkdir(bkp_dir)
                sftp.close()
            else:
                if not os.path.exists(bkp_dir):
                    os.makedirs(bkp_dir)
            
            return True
        except Exception as e:
            _logger.info(f"======= Exception while checking the backup directory for the saas client backups ======= {e} ")
            return False

    
    def _remove_local_backup_files(self, bkp_details_id):
        """
            Method to check if the backup file exist, and if exist then remove that backup file.
            Also, updates the status and the message of the backup process details.
            
            Args:
                bkp_details_ids ([object]): [all the backup process ids whose backup file needs to be deleted.]
        """
        try:
            msg = None
            if bkp_details_id.backup_process_id.saas_client_id and bkp_details_id.backup_process_id.saas_client_id.server_id.host_server == 'remote':
                ssh_obj = self.login_saas_remote(bkp_details_id.backup_process_id)
                if self.check_remote_backup_existance(ssh_obj, bkp_details_id.url):
                    sftp = ssh_obj.open_sftp()
                    sftp.remove(bkp_details_id.url)
                    sftp.close()
                    msg = 'Database backup dropped successfully  at ' + datetime.now().strftime("%m-%d-%Y-%H:%M:%S") + " after retention from remote saas server."
                    bkp_details_id.message = msg
                    bkp_details_id.status = "Dropped"
                else:
                    msg = "Database backup file doesn't exists on remote saas server."
                    bkp_details_id.message = msg
                    bkp_details_id.status = "Failure"
                return msg
            msg = super(SaasBackupProcess, self)._remove_local_backup_files(bkp_details_id)
            return msg
        except Exception as e:
            _logger.error("Database backup remove error: " + str(e))
            return False
        
    
    def login_saas_remote(self, backup_process_id):
        """
            Method to login to the remote saas server using SSH.
            
        Returns:
            [Object]: [Returns SSh object if connected successfully to the remote saas server.]
        """
        try:
            remote_saas_server = backup_process_id.saas_client_id.server_id
            ssh_obj = paramiko.SSHClient()
            ssh_obj.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_obj.connect(hostname=remote_saas_server.sftp_host, username=remote_saas_server.sftp_user, password=remote_saas_server.sftp_password, port=remote_saas_server.sftp_port)
            return ssh_obj
        except Exception as e:
            _logger.info(f"==== Exception while connecting to remote saas server ==== {e} ===")
            return False
    
