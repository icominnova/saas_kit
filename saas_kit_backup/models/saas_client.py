# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2017-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import models, fields, tools, api, _
from odoo.exceptions import UserError
from datetime import datetime
import base64
from pytz import timezone
import pytz


import configparser
import logging

_logger = logging.getLogger(__name__)


class SaasClientBackup(models.Model):
    _inherit = 'saas.client'

    backup_process_id = fields.Many2one(comodel_name='backup.process', string="Backup Process")
    is_crone_ignited = fields.Boolean(string="Backup Attaches", default=False)
    crone_state = fields.Selection(related='backup_process_id.state', string="Crone state")


    frequency = fields.Integer(string="Frequency", help="Frequency for backuping the database.", related="backup_process_id.frequency")
    backup_path = fields.Char(string="Backup Path", help="The directory path where the backup files will be stored on server.", related="backup_process_id.storage_path")
    backup_location = fields.Selection(string="Backup Location", help="Server where the backup file will be stored.", related="backup_process_id.backup_location")
    backup_format = fields.Selection(string="Backup Format", help="Select the file format of the data backup file.", related="backup_process_id.backup_format")
    frequency_cycle = fields.Selection(string="Frequency Cycle", help="Select frequency cycle of Database Backup.", related="backup_process_id.frequency_cycle")
    backup_details_ids = fields.One2many(comodel_name="backup.process.detail", inverse_name="saas_client_id", string="Backup Details", help="Details of the database backups that has been created.", related="backup_process_id.backup_details_ids")


    def get_backup(self):
        config = configparser.RawConfigParser()
        module_path = tools.misc.file_path('odoo_saas_kit')
        config.read(module_path+'/models/lib/saas.conf')
        config_dict = dict(config.items('options'))
        _logger.info("-------- called from client---------")
        url = 'localhost' if self.server_id.host_server == 'self' else self.server_id.sftp_host
        url += ':'+self.container_port
        res = self.backup_process_id.call_backup_script(master_pass=config_dict['container_master'], port_number=self.container_port, url=url)
        if res.get('success'):
            self.is_crone_ignited = True
            
    def get_saas_admins(self):
        saas_admin_list = []
        users = self.env['res.users'].sudo().search([])
        for user in users:
            if user.has_group('odoo_saas_kit.group_saas_manager'):
                saas_admin_list.append(user.partner_id.id)
        
        return saas_admin_list
            
    def send_backup_process_creation_mail(self):
        for obj in self:
            saas_admins = self.get_saas_admins()
            template = self.env.ref('saas_kit_backup.backup_creation_template')
            email_values = {"recipient_ids":saas_admins}
            mail_id = template.send_mail(obj.id, force_send=True, email_values=email_values)
            current_mail = self.env['mail.mail'].browse(mail_id)
            current_mail.send()

    def create_backup_process(self, frequency=1, frequency_cycle=None, backup_starting_time=None, backup_format="zip", enable_retention=None, retention=None, backup_location=None, **kwargs):
        """
        Call from wizard and will to create/update the backup process.
        """
        if type(backup_starting_time) == str:
            user_time_zone = self.saas_contract_id.partner_id.tz or self._context.get('tz')
            local_zone = pytz.timezone(user_time_zone)
            naive_datetime = datetime.strptime(backup_starting_time, "%Y-%m-%d %H:%M")
            local_datetime = local_zone.localize(naive_datetime, is_dst=None)
            utc_datetime = local_datetime.astimezone(pytz.utc)
            backup_starting_time = utc_datetime.strftime("%Y-%m-%d %H:%M:%S")
        
        backup_location = backup_location or self.server_id.backup_location
        path_response = {}
        vals = dict(
            backup_instance="saas_client",
            frequency=frequency,
            frequency_cycle=frequency_cycle,
            backup_location=backup_location,
            db_name=self.database_name,
            saas_client_id=self.id,
            backup_starting_time=backup_starting_time,
            backup_format=backup_format,
        )
        if enable_retention != None:
            vals.update(
                enable_retention=enable_retention,
                retention=retention
            )
        if hasattr(self,'_set_%s_backup_storage_path'%backup_location):## if you want to update dictionary then you can define this function _set_{backup_location}_backup_storage_path
                path_response = getattr(self,'_set_%s_backup_storage_path'%backup_location)(**kwargs)
        
        vals.update(path_response)
        if self.backup_process_id and not self.backup_process_id.state == 'cancel':
            vals['update_requested'] = True
            self.backup_process_id.write(vals)
        else:
            backup_record = self.env['backup.process'].sudo().create(vals)
            self.backup_process_id = backup_record.id
        self.send_backup_process_creation_mail()
        
        
    def _set_local_backup_storage_path(self, **kwargs):
        return dict(   
            storage_path = self.data_directory_path,
        )
        
    def _set_remote_backup_storage_path(self, **kwargs):
        remote_server_id = kwargs.get('remote_server_id', False)
        if remote_server_id:
            remote_server = self.env['backup.remote.server'].sudo().browse([int(remote_server_id)])
        else:
            remote_server = self.server_id.remote_server_id
        return dict(
            remote_server_id=remote_server.id,
            storage_path = remote_server.def_backup_dir
        )


    def update_backup_process(self):
        """
        Call from client record and will pop up a wizard for update params.
        """
        server_response = dict()
        vals = dict(
            name='update',
            frequency=self.backup_process_id.frequency,
            frequency_cycle=self.backup_process_id.frequency_cycle,
            backup_starting_time=self.backup_process_id.backup_starting_time,
            backup_format=self.backup_process_id.backup_format,
            enable_retention=self.backup_process_id.enable_retention,
            retention=self.backup_process_id.retention,
            backup_location=self.backup_process_id.backup_location,
        )
        
        if hasattr(self,'_set_%s_backup_server'%self.backup_process_id.backup_location):## if you want to update dictionary then you can define this function _set_{backup_location}_backup_storage_path
                server_response = getattr(self,'_set_%s_backup_server'%self.backup_process_id.backup_location)()
                
        vals.update(server_response)
        res = self.env['backup.process.wizard'].sudo().create(vals)
        return {
            'name': _('Update Backup Process'),
            'res_model': 'backup.process.wizard',
            'view_mode': 'form',
            'res_id' : res.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'client_id': self.id}
        }

    
    def _set_local_backup_server(self):
        return {}
    
    
    def _set_remote_backup_server(self):
        return dict(
            remote_server_id = self.backup_process_id.remote_server_id.id
        )    
        
    def cancel_backup_process(self):
        """
        Call from client record and will pop up a wizard for confirmation.
        """
        vals = dict(
            name=_('Are you sure you want to Cancel/Delete the attach Backup Process. It will stop the future backups ?'),
            purpose='cancel_backup',
            record_id=self.id,
        )
        res = self.env['cancel.backup.process'].sudo().create(vals)
        return {
            'name': _('Confirmation'),
            'res_model': 'cancel.backup.process',
            'view_mode': 'form',
            'res_id' : res.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def delete_backup_crone(self):
        """
        Call from wizard to delete the crone.
        """
        res = self.backup_process_id.remove_attached_cron()
        _logger.info('---backup cron deletion--  %r -------'%res)
        if res.get('success'):
            self.is_crone_ignited = False


    @api.model
    def get_create_backup_process_data(self, frequency, frequency_cycle, starting_date, update_req, client_id):
        """
        Called from JS to Create/Update process.
        Upate Req args is for future purpose.
        """
        client_id = self.env['saas.client'].sudo().browse([client_id])
        starting_date = starting_date.replace('T', ' ')
        if not update_req:
            IrDefault = self.env['ir.default'].sudo()
            enable_retention = IrDefault._get('res.config.settings', 'enable_retention')
            backup_retention_count = IrDefault._get('res.config.settings', 'backup_retention_count')
            client_id.create_backup_process(frequency=int(frequency), frequency_cycle=frequency_cycle, backup_starting_time=starting_date, enable_retention=enable_retention, retention=backup_retention_count)
        else:
            client_id.create_backup_process(frequency=int(frequency), frequency_cycle=frequency_cycle, backup_starting_time=starting_date)
            
        data = dict()
        data['contract_id'] = client_id.saas_contract_id.id
        data['token'] = client_id.saas_contract_id.access_token
        return data

    def get_cancel_backup_process_call(self, client_id):
        """
        Call from JS to Cancel the process
        """
        client_id = self.env['saas.client'].sudo().browse([client_id])
        client_id.delete_backup_crone()
        data = dict()
        data['contract_id'] = client_id.saas_contract_id.id
        data['token'] = client_id.saas_contract_id.access_token
        return data

    def download_backup_process(self, detail_id=None):
        file_path = detail_id.file_path + detail_id.file_name
        data = {}
        data['status'] = True
        data['download_url'] = None
        if detail_id.backup_location == 'remote':
            backup_copy_status = detail_id.get_remote_backup_file()
            if backup_copy_status:
                temp_path = detail_id.backup_process_id.remote_server_id.temp_backup_dir
                file_path = temp_path+"/"+detail_id.file_name
                data['download_url'] = f"/backupfile/download?path={file_path}&backup_location=remote"
            else:
                _logger.error("Cannot download remote backup file from remote server. Follow logs for more details.")
                data['status'] = False
                data['err_message'] = _("Something went wrong. Kindly contact admin.")
        else:
            data['download_url'] = f"/backupfile/download?path={file_path}&backup_location=local"
            saas_client = detail_id.backup_process_id.saas_client_id
            if saas_client.server_id and saas_client.server_id.host_server == 'remote':
                if detail_id.backup_location == 'local':
                    file_get_status = detail_id.get_saas_remote_backup_file()
                    if not file_get_status:
                        _logger.error("Cannot download remote backup file from remote server. Follow logs for more details.")
                        data['status'] = False
                        data['err_message'] = _("Something went wrong. Kindly contact admin.")
                    else:
                        file_path = "/tmp/"+detail_id.file_name
                        data['download_url'] = f"/backupfile/download?path={file_path}&backup_location=remote"
        return data


    def get_download_backup_zip_call(self, client_id, detail_id, name):
        """
        Call from JS to call download function
        """
        client_id = self.env['saas.client'].sudo().browse([client_id])
        detail_id = self.env['backup.process.detail'].sudo().browse([detail_id])
        if detail_id in client_id.backup_process_id.backup_details_ids and detail_id.name == name:
            return client_id.download_backup_process(detail_id=detail_id)
        else:
            return False          
        
    def drop_db(self):
        """
            Overrided this method to cancel the running/confirmed saas client backup process after dropping 
            the saas client instance db
        """
        res = super(SaasClientBackup, self).drop_db()
        if res and self.backup_process_id:
            if self.backup_process_id.state in ['confirm']:
                self.backup_process_id.state="cancel"
            elif self.backup_process_id.state in ['running']:
                self.delete_backup_crone()
        
        return res
    
    def write(self, vals):
        """
            Overrided this method to cancel the running/confirmed saas client backup process after the state 
            is changed to cancel state
        """
        res = super(SaasClientBackup, self).write(vals)
        if res and self.state=='cancel' and self.backup_process_id:
            if self.backup_process_id.state in ['draft', 'confirm']:
                self.backup_process_id.state="cancel"
            elif self.backup_process_id.state in ['running']:
                self.delete_backup_crone()
        
        return res      

