# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import http, _
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools import consteq
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager

import logging
import os

_logger = logging.getLogger(__name__)

class BackupPortal(CustomerPortal):
    
    

    
    @http.route()
    def portal_contract_page(self, contract=None, access_token=None, **kw):
        result = super(BackupPortal, self).portal_contract_page(contract=contract, access_token=access_token, **kw)
        contract_sudo = result.qcontext.get('contract')
        backup_process = contract_sudo.saas_client.backup_process_id
        pager = portal_pager(
            url="/my/saas/contract/",
            total=len(backup_process.backup_details_ids),
            page=kw.get('page', 1),
            step=10
        )
        
        ###### Retention Values #######
        IrDefault = request.env['ir.default'].sudo()
        enable_retention = IrDefault._get('res.config.settings', 'enable_retention')
        backup_retention_count = IrDefault._get('res.config.settings', 'backup_retention_count')
                
        result.qcontext.update({
            'pager': pager,
            'backup_process': backup_process,
            'enable_retention': enable_retention,
            'backup_retention_count': backup_retention_count
        })
        return result
        

    
    
    
    
class BackupController(http.Controller):
    
    @http.route('/remote/server/creds', type='http', auth='none', methods=['POST'], csrf=False)
    def remote_server_creds(self, **kwargs):
        data = dict()
        backup_process_id = kwargs.get('backup_process_id', False)
        if not backup_process_id:
            data['status'] = False
            data['message'] = _("Backup process_id doesn't found.")
        else:
            backup_process = request.env['backup.process'].sudo().browse([int(backup_process_id)])
            remote_server = backup_process.saas_client_id.server_id
            host_server, _ = remote_server.get_server_details()
            data_dir_path = backup_process.saas_client_id.data_directory_path
            backup_path = os.path.join(data_dir_path, 'backups')
            data['host_server'] = host_server
            data['backup_path'] = backup_path
        response = request.make_json_response(data)
        return response
