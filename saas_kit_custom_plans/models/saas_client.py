# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import models, api, fields, tools, _
from odoo.addons.auth_signup.models.res_partner import random_token as generate_token
from odoo.api import NewId
from odoo.exceptions import UserError
from odoo.addons.odoo_saas_kit.models.lib import query
from odoo.addons.odoo_saas_kit.models.lib import saas
from odoo.addons.odoo_saas_kit.models.lib import client
from odoo.addons.odoo_saas_kit.models.lib.pg_query import PgQuery

import requests,json,time
import logging

_logger = logging.getLogger(__name__)

from . lib import saas_install

MODULE_STATUS = [('installed', "Installed"), 
                ('uninstalled', "To Be Installed")]


class CustomSaasClient(models.Model):
    _inherit = 'saas.client'

    version_code = fields.Char(string = "Instance Odoo Version" , compute="get_code",help="Version code of client's odoo instance")
    is_enterprise = fields.Boolean(string="Enterprise Edition", compute="get_code")

    def get_code(self):
        for rec in self:
            rec.version_code = '19.0'
            rec.is_enterprise = False
            if rec.saas_contract_id.odoo_version_id:
                rec.version_code = rec.saas_contract_id.version_code
                rec.is_enterprise = rec.saas_contract_id.is_enterprise
            elif rec.saas_contract_id.plan_id.provide_odoo_version:
                # rec.odoo_version_id = rec.plan_id.plan_odoo_version.id
                rec.version_code = rec.saas_contract_id.plan_id.plan_odoo_version.code
                rec.is_enterprise = rec.saas_contract_id.plan_id.plan_odoo_version.is_enterprise

            # if rec.version_code and 'e' in rec.version_code:
            #     rec.is_enterprise = True
    
    @api.depends('data_directory_path')
    def _compute_addons_path(self):
        for obj in self:
            if obj.saas_contract_id.is_custom_plan or obj.saas_contract_id.from_backend or obj.saas_contract_id.odoo_version_id:
                code = obj.saas_contract_id.odoo_version_id.code or obj.saas_contract_id.version_code
                if obj.data_directory_path and type(obj.id) != NewId:
                    obj.addons_path = "{}/addons/{}".format(
                        obj.data_directory_path, code)
                else:
                    obj.addons_path = ""
            else:
                super(CustomSaasClient, self)._compute_addons_path()

    missed_modules = fields.Boolean(string="Missed Modules", default=True)

    
    def install_modules(self):
        host_server, _ = self.server_id.get_server_details()
        endpoint = str(host_server.get('host')) if (host_server['server_type'] == 'remote') else "localhost"
        endpoint = f"http://{endpoint}:{self.container_port}" + "/install/saas/modules"
        count = 0
        while count < 3:
            response = requests.get(endpoint)
            _logger.info(f"=======Calling Module Installation on Client URL===Attempt : {count+1}=======")
            if response.status_code == 200:
                break
            time.sleep(3)
            count+=1
        if response.status_code ==200 and response.json()['status']:
            remaining_module_list=[]
            if response.json()['missed_module_list']!="False":
                remaining_module_list=response.text.split(",")
            
            for rec in self.saas_module_ids:
                if rec.technical_name not in remaining_module_list:
                    rec.status = "installed"
            if remaining_module_list==[]:
                self.missed_modules = False


    def fetch_client_url(self, domain_name=None):
        for obj in self:
            if obj.saas_contract_id.is_custom_plan:
                if type(domain_name) != str:
                    if obj.saas_contract_id.use_separate_domain:
                        domain_name = obj.saas_contract_id.domain_name
                    else:
                        domain_name = "{}.{}".format(obj.saas_contract_id.domain_name, obj.saas_contract_id.saas_domain_url)

                response = None
                try:
                    response = obj.create_client_instance(domain_name)
                except Exception as e:
                    raise UserError("Unable To Create Client\nERROR: {}".format(e))
                if response:
                    obj.client_url = response.get("url", False)
                    obj.container_port = response.get("port", False)
                    obj.container_lport = response.get("lport", False)
                    obj.container_path = response.get("path", False)
                    obj.container_name = response.get("name", False)
                    obj.container_id = response.get("container_id", False)
                    obj.state = "started"
                    obj.saas_contract_id.under_process = False
                    obj.data_directory_path = response.get("extra-addons", False)
                    self.env.cr.commit()
                    
                    restrict_app_list = str(obj.saas_contract_id.odoo_version_id.restrict_app_list)
                    host_server, db_server = obj.server_id.get_server_details()
                    pgX = PgQuery(db_server['host'],obj.database_name, db_server['user'], db_server['password'], db_server['port'])
                    module_list=",".join([module.technical_name  for module in obj.saas_module_ids])
                    query1 = "Update ir_config_parameter set value ='{}' where key='module_list'".format(module_list)
                    query2 = "Update ir_config_parameter set value ='{}' where key='missed_module_list'".format(module_list)
                    query3 = "Update ir_config_parameter set value ='{}' where key='restrict_app_list'".format(restrict_app_list)
                    with pgX as pg:
                        if not pg.get('status'):
                            return pg
                        result1 = pgX.executeQuery(query1)
                        result2 = pgX.executeQuery(query2)
                        result3 = pgX.executeQuery(query3)
                    obj.install_modules()
                    obj.update_app_list()

                else:
                    raise UserError("Couldn't create the instance with the selected domain name. Please use some other domain name.")
            else:
                obj.missed_modules = False
                super(CustomSaasClient, self).fetch_client_url(domain_name=domain_name)

    @api.model
    def create_docker_instance(self, domain_name=None):
        version_code = self.saas_contract_id.version_code
        if self.saas_contract_id.is_custom_plan or self.saas_contract_id.from_backend or self.saas_contract_id.odoo_version_id:
            modules = [module.technical_name for module in self.saas_module_ids]
            host_server, db_server = self.saas_contract_id.server_id.get_server_details()
            response = None
            self.database_name = domain_name.replace("https://", "").replace("http://", "")
            config_path = tools.misc.file_path('odoo_saas_kit')
            is_enterprise = self.is_enterprise
            enterprise_addons_path = self.saas_contract_id.odoo_version_id.enterprise_addons_path if self.saas_contract_id.odoo_version_id and self.is_enterprise else None
            response = saas.main(dict(
                db_template = self.saas_contract_id.db_template,
                db_name=self.database_name,
                modules=modules,
                config_path = config_path,
                host_domain=domain_name,
                host_server=host_server,
                db_server=db_server,
                version=version_code,
                is_enterprise = self.is_enterprise,
                enterprise_addons_path = enterprise_addons_path,)
            )
            return response
        else:
            res = super(CustomSaasClient, self).create_docker_instance(domain_name=domain_name)
            return res

    @api.model
    def module_installation_crone_action(self):
        client_ids = self.env['saas.client'].sudo().search([('state', '=', 'started'), ('missed_modules', '=', True)])
        for client_id in client_ids:
            client_id.install_modules()
            
    def drop_db(self):
        for obj in self:
            if obj.saas_contract_id.is_custom_plan:
                try:
                    if obj.state == "inactive":
                        host_server, db_server = obj.saas_contract_id.server_id.get_server_details()
                        _logger.info("HOST SERER %r   DB SERVER  %r"%(host_server,db_server))
                        response = client.main(obj.database_name, obj.container_port, host_server, tools.misc.file_path('odoo_saas_kit'), from_drop_db=True, version=obj.saas_contract_id.odoo_version_id.code or '19.0')
                        if not response['db_drop']:
                            raise UserError("ERROR: Couldn't Drop Client Database. Please Try Again Later.\n\nOperation\tStatus\n\nDrop database: \t{}\n".format(response['db_drop']))
                        else:
                            obj.is_drop_db = True
                            if obj.is_drop_container:
                                obj.saas_contract_id.state = 'cancel'
                                obj.state = 'cancel'
                except Exception as e:
                    raise UserError(e)
            else:
                return super(CustomSaasClient, self).drop_db()
                        
    def drop_container(self):
        for obj in self:
            if obj.saas_contract_id.is_custom_plan:
                if obj.state == "inactive" and obj.container_id:
                    host_server, db_server = obj.saas_contract_id.server_id.get_server_details()
                    _logger.info("HOST SERER %r   DB SERVER  %r"%(host_server,db_server))
                    response = client.main(obj.database_name, obj.container_port, host_server, tools.misc.file_path('odoo_saas_kit'), container_id=obj.container_id, db_server=db_server, from_drop_container=True, version=obj.saas_contract_id.odoo_version_id.code or '19.0')
                    if not response['drop_container'] or not response['delete_nginx_vhost'] or not response['delete_data_dir']:
                        raise UserError("ERROR: Couldn't Drop Client Container. Please Try Again Later.\n\nOperation\tStatus\n\nDelete Domain Mapping: \t{}\nDelete Data Directory: \t{}".format(response['drop_container'], response['delete_nginx_vhost']))
                    else:
                        obj.is_drop_container = True
                        if obj.is_drop_db:
                            obj.saas_contract_id.state = 'cancel'
                            obj.state = 'cancel'
                else:
                    obj.is_drop_container = True
                    if obj.is_drop_db:
                        obj.saas_contract_id.state = 'cancel'
                        obj.state = 'cancel'
            else:
                return super(CustomSaasClient, self).drop_container()
            
    ###Update below for rebuilding instance
    def rebuild_client(self):
        for obj in self:
            if obj.state == "stopped" and obj.container_id:
                host_server, db_server = self.saas_contract_id.server_id.get_server_details()
                response = None
                #self.database_name = domain_name.replace("https://", "").replace("http://", "")
                config_path = tools.misc.file_path('odoo_saas_kit')
                domain_name = self.database_name
                enterprise_addons_path = self.saas_contract_id.odoo_version_id.enterprise_addons_path if self.saas_contract_id.odoo_version_id and self.is_enterprise else None

                try:
                    response = saas.rebuild(dict(
                    #db_template = self.saas_contract_id.db_template,
                    db_name=self.database_name,
                    config_path = config_path,
                    host_domain = domain_name,
                    host_server = host_server,
                    db_server = db_server,
                    data_dir = self.data_directory_path,
                    container_path = self.container_path,
                    port = self.container_port,
                    lport = self.container_lport,
                    version = self.saas_contract_id.version_code,
                    is_enterprise = self.is_enterprise,
                    enterprise_addons_path = enterprise_addons_path,))
                    self.print_logs('info', 'calling client.main rebuld script', 365)
                    if not response['status']:
                        obj.rebuild_cmd = response.get('rebuild_cmd', None)
                        raise UserError(f"ERROR: Couldn't Rebuld Client Container. \n Manual Rebuild command : {response.get('rebuild_cmd', None)}")
                    else:
                        obj.last_rebuild_status = True
                        obj.state = 'started'
                        if response.get('update_port'):
                            obj.container_port = response.get('port')
                        if response.get('update_lport'):
                            obj.container_lport = response.get('lport')
                except Exception as e:
                    raise UserError(f"{e}")
            else:
                raise UserError("Please stop Saas Client first!!")


class CustomModuleStatus(models.Model):
    _inherit = 'saas.module.status'

    status = fields.Selection(selection=MODULE_STATUS, default="uninstalled",help="Status of saas module in client's Instance i.e. Installed/Unistalled")

    def unlink(self):
        for record in self:
            if record.status =="installed":
                raise UserError("Can't remove this moudle as this is installed")
            else:
                rec1 = record.client_id.saas_contract_id.saas_module_ids.filtered(lambda rec: rec.id == record.module_id.id)
                record.client_id.saas_contract_id.saas_module_ids = record.client_id.saas_contract_id.saas_module_ids.filtered(lambda rec: rec.id != rec1.id)
        return super(CustomModuleStatus,self).unlink()

