# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import api, fields, models, tools
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
from configparser import ConfigParser
from tempfile import TemporaryFile
import base64
import operator
import subprocess
import tempfile
import logging
import os

_logger = logging.getLogger(__name__)




class ServerPem(models.TransientModel):
    _name = "import.server.pem"
    _description = 'Import Server Pem.'

    server_id = fields.Many2one(comodel_name="saas.server", string="Related SaaS Server", required=True)
    pem_file  = fields.Binary(string = "Pem File")
    filename = fields.Char(string = "Complete Filename",required=True)

    def upload_pem_file(self):
        try:
            with tempfile.NamedTemporaryFile(delete=False) as data_file:
                data_file.write(base64.decodebytes(self.pem_file))
            path = tools.misc.file_path('odoo_saas_kit')+"/models/lib/saas.conf"
            parser = ConfigParser()
            parser.read(path)
            odoo_saas_data = parser.get("options","odoo_saas_data") + "key_files"
            if not os.path.exists(odoo_saas_data):
                os.makedirs(odoo_saas_data)
            cmd = "cp -r "+ data_file.name + " " + odoo_saas_data
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
            cmd = f"rm -rf {data_file.name}"
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
            file_name = data_file.name.split("/")[-1]
            path_to_filename = odoo_saas_data+"/"+file_name
            name = self.filename
            os.rename(path_to_filename, odoo_saas_data+"/"+name)
            self.server_id.key_file_path = odoo_saas_data+"/"+name
            cmd  =  f"chmod -R 400 {self.server_id.key_file_path}"
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
            
        except Exception as e:
            _logger.info(f"==============e================{e}")
            raise UserError(e)
  

    
