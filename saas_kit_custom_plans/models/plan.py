# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

import re
from odoo import models, api, fields, tools, _
from odoo.exceptions import UserError

from odoo.addons.odoo_saas_kit.models.lib import query
from odoo.addons.odoo_saas_kit.models.lib import saas
from odoo.addons.odoo_saas_kit.models.lib import install_module
from . static_custom_plan import DEFAULT_ODOO_VERSION
import logging
_logger = logging.getLogger(__name__)


class SaasPlanCustomPlan(models.Model):
    _inherit= 'saas.plan'


    """
    Feature Addition: Version Selection from Backend
    
    """
    def _get_default_odoo_version(self):
        return self.env['saas.odoo.version'].search([('state', '=', 'confirm'),('code','=', DEFAULT_ODOO_VERSION)], limit=1).id

    provide_odoo_version = fields.Boolean(string="Provide Odoo Version", default=False,help="Checkbox to provide version selection in Saas Plan")
    plan_odoo_version = fields.Many2one(string="Select Odoo Version", comodel_name="saas.odoo.version", domain="[('state', '=', 'confirm')]", default=_get_default_odoo_version,help="Odoo version of the Saas Plan")
    odoo_version_code = fields.Char(compute="_compute_odoo_version_code",help="Code of odoo version")
    is_enterprise = fields.Boolean(string = "Enterprise Edition", default = False)


    saas_module_ids = fields.Many2many(
        comodel_name="saas.module",
        relation="saas_plan_module_relation",
        column1="plan_id",
        column2="module_id",
        string="Related Modules",
        domain="[('odoo_version_id.code', '=', odoo_version_code)]")
    
    @api.onchange('plan_odoo_version')
    def _compute_odoo_version_code(self):
        for plan in self:
            plan.odoo_version_code = plan.plan_odoo_version.code if (plan.provide_odoo_version and plan.plan_odoo_version) else '19.0'
            #New flow for enterprise edition
            plan.is_enterprise = plan.plan_odoo_version.is_enterprise if (plan.provide_odoo_version and plan.plan_odoo_version) else False
        # _logger.info(f"========self.odoo_version_code======{self.odoo_version_code}===========================")

    @api.depends('provide_odoo_version')
    def _set_plan_version_to_default(self):
       # if self.provide_odoo_version:
        _logger.info(f"======_set_plan_version_to_default===============")
        self.plan_odoo_version = self.env['saas.odoo.version'].search([('state', '=', 'confirm'),('code','=', DEFAULT_ODOO_VERSION)], limit=1).id
        _logger.info(f"======plan_odoo_version===={self.plan_odoo_version}======")

    def create_db_template(self):
        """
            Method to create the database template of the saas plan and confirm the state of the plan.
            Called from the Create Db Template button over saas plan.

            Update: Feature addition for custom odoo version selection
            Can be improved with super calling and updating super method with odoo version parameter
        """
        
        for obj in self:
            if not obj.db_template:
                raise UserError(_("Please select the DB template name first."))
            if re.match("^template_",obj.db_template):
                raise UserError(_("Couldn't Create DB. Please try again with some other Template Name!"))
            db_template_name = "template_{}".format(obj.db_template)
            config_path = tools.misc.file_path('odoo_saas_kit')
            status_module = obj.create_status_modules()
            installable_modules = obj.get_installable_modules()
            modules = [module.technical_name for module in installable_modules]            
            modules.append('wk_saas_tool')

            ####added selected odoo version in for plan db creation###
            odoo_version = obj.odoo_version_code
            enterprise_addons_path = self.plan_odoo_version.enterprise_addons_path if self.plan_odoo_version and self.is_enterprise else None
            ################################
            try:
                host_server, db_server = obj.server_id.get_server_details()
                response = saas.create_db_template(
                    db_template=db_template_name,
                    modules=modules,
                    config_path=config_path,
                    host_server=host_server,
                    db_server=db_server,
                    version=odoo_version,
                    is_enterprise = self.is_enterprise,
                    enterprise_addons_path = enterprise_addons_path,)
                ##Updated the create_db_template parameters, added version for custom version
                
            except Exception as e:
                _logger.info("--------DB-TEMPLATE-CREATION-EXCEPTION-------%r", e)
                raise UserError(e)
            else:
            # response = True
                if response:
                    if response.get('status', False):
                        obj.db_template = db_template_name
                        obj.state = 'confirm'
                        obj.container_id = response.get('container_id', False)
                        # _logger.info("-= =- =- =-= -= -= %r-= -= = =-= "%installable_modules)
                        if response['result'] != "alreadyexists":
                            for module in installable_modules:
                                if not module.technical_name in list(response['result']['modules_missed'].keys()):
                                    module.status="installed"
                                else:
                                    module.error_message = response['result']['modules_missed'][module.technical_name]
                                if not self.get_installable_modules():
                                    self.is_all_installed=True
                            # _logger.info(f"============Status======={self.env['saas.module.status'].browse(id).status}=============")

                    else:
                        msg = response.get('msg', False)
                        if msg:
                            raise UserError(msg)
                        else:
                            raise UserError(_("Unknown Error. Please try again later with some different Template Name"))
                else:
                    raise UserError(_("No Response. Please try again later with some different Template Name"))


    def login_to_db_template(self):
        """
            Overridden for db(version) in login url
            #Called from the Login button over saas plan
            #Redict to the Plan instance to login in to template database
            Need improvement, can done by calling super and updating super method with version parameter
        """
        
        for obj in self:
            host_server, db_server = obj.server_id.get_server_details()
            response = query.get_credentials(
                obj.db_template,
                host_server=host_server,
                db_server=db_server)
            if response.get('status'):
                response = response.get('result')
                login = response[0][0]
                password = response[0][1]
                # login_url = "http://db16_templates.{}/saas/login?db={}&login={}&passwd={}".format(obj.saas_base_url,obj.db_template, login, password)
                login_url = "http://db{}_templates.{}/saas/login?db={}&login={}&passwd={}".format(obj.odoo_version_code.split('.')[0],obj.saas_base_url,obj.db_template, login, password)


                _logger.info("SaaS login URL generated")
                return {
                    'type': 'ir.actions.act_url',
                    'url': login_url,
                    'target': 'new',
                }
            else:
                raise UserError(_("ERR001: %s") % response.get("message"))


    def install_remaining_modules(self,modules=[],installable_modules=None):
        installable_modules =installable_modules or self.get_installable_modules()

        modules = modules or  [module.technical_name for module in installable_modules]
        host_server, db_server = self.server_id.get_server_details()
        cred_response = query.get_credentials(
                    self.db_template,
                    host_server=host_server,
                    db_server=db_server)
        if cred_response.get('status'):
            response = cred_response.get('result')
            login = response[0][0]
            password = response[0][1]
            try:
                response = install_module.main(dict(
                    db_name=self.db_template,
                    modules=modules,
                    version=self.odoo_version_code,
                    config_path = tools.misc.file_path('odoo_saas_kit'),
                    login=login,
                    password=password))
            except Exception as e:
                    _logger.info("--------MODULE-INSTALLATION-EXCEPTION-------%r", e)
                    raise UserError(e)
            else:
                if response:
                    for module in installable_modules:
                        if not module.technical_name in list(response['modules_missed'].keys()):
                            module.status="installed"
                            module.error_message = ""
                        else:
                            module.error_message = _("Error: %s") % response['modules_missed'][module.technical_name]
                        if not self.get_installable_modules():
                            self.is_all_installed=True
                        self.env.cr.commit()
                    if response.get('modules_installation', False):
                        self.state = 'confirm'
                    else:
                        raise UserError(_("Some Modules are not insatlled Please check Error tab"))
                else:
                    raise UserError(_("No Response. Please try again later"))
        else:
            raise UserError(_("Details Not found !"))
