# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

from odoo import models, fields, api
from odoo.exceptions import UserError
from . lib import module_lib
import os

import logging

_logger = logging.getLogger(__name__)

class SaasModule(models.Model):
    _inherit = 'saas.module'


    @api.depends('name')
    def set_default_path(self):
        for obj in self:
            if obj.module_type == 'core':
                IrDefault = obj.env['ir.default'].sudo()
                addons_path = IrDefault._get('res.config.settings', 'addons_path')
                obj.addons_path = addons_path
            else:
                if not obj.addons_path and obj.odoo_version_id:
                    obj.addons_path = obj.odoo_version_id.common_addons_path


    is_published = fields.Boolean(string="Publised", default=False)
    price = fields.Float(string="Price")
    auto_install = fields.Boolean(string="Auto Install Module", default=True)
    addons_path = fields.Char(string="Addons Path", compute="set_default_path", store=True, readonly=False)
    contract_id = fields.Many2one(comodel_name="saas.contract")
    odoo_version_id = fields.Many2one(comodel_name="saas.odoo.version")
    module_type = fields.Selection([('core', 'Core Module'), ('custom', 'Custom Module')], string="Module Type")
    addon_path_verified = fields.Boolean(string="Addon's Path verified")

    @api.constrains('odoo_version_id')
    def check_name_and_version(self):
        check=self.env['saas.module'].sudo().search([('technical_name','=',self.technical_name), ('id','!=',self.id), ('odoo_version_id','=',self.odoo_version_id.id)])
        if (check):
            raise UserError("Module with same version already exists!")
        
    @api.onchange('module_type')
    def change_module_publish(self):
        for rec in self:
            rec.is_published = False
            rec.addon_path_verified = False

    @api.constrains('module_type')
    def check_module_type(self):
        for rec in self:
            if rec.module_type == "custom" and not rec.addons_path:
                raise UserError("Please enter module addons path!!")
        
    @api.onchange('module_type','odoo_version_id')
    def change_addons_path(self):
        if self.module_type =="core":
            IrDefault = self.env['ir.default'].sudo()
            addons_path = IrDefault._get('res.config.settings', 'addons_path')
            self.addons_path = addons_path
        else:
            self.addons_path = self.odoo_version_id.common_addons_path


    def check_available_version(self):
        IrDefault = self.env['ir.default'].sudo()
        is_odoo_version = IrDefault._get('res.config.settings', 'is_odoo_version')
        domain = []
        if not is_odoo_version:
            domain = [('code', '=', '19.0')]
        domain.append(('state', '=', 'confirm'))
        version = self.env['saas.odoo.version'].sudo().search(domain)
        return version and True or False


    def toggle_module_publish(self):
        if not self.is_published:
            """
            Check whether the module exist in the path or not.
            """
            if not self.check_available_version():
                raise UserError("No Version has been configured yet, please configure atleast one version to continue")
            
            if self.module_type=='custom' and not self.addon_path_verified:
                    raise UserError("Please verify custom addons path to publish the module.")
                
            # if self.auto_install and self.module_type=='custom':
                # if self.addons_path:
                #     res = module_lib.check_if_module([self.addons_path], self.technical_name)
                #     if res.get('status'):
                #         self.is_published = not self.is_published                  
                #     elif not res.get('msg'):
                #         raise UserError("You have Selected Auto install for the Module but Module does not present on the Default path.")
                #     else:
                #         raise UserError(res.get('msg'))
                # else:
                #     raise UserError("Please enter module addons path!!")

            else:
                self.is_published = not self.is_published
        else:
            self.is_published = not self.is_published

    
    @api.model_create_multi
    def create(self, vals_list):
        res = None
        for vals in vals_list:
            if not vals.get('module_type'):
                raise UserError('Please choose module type!!')
            else:
                res = super(SaasModule, self).create(vals)

        return res
    
    def write(self, vals):
        for rec in self:
            if vals.get('module_type') or vals.get('technical_name'):
                vals['is_published'] = False
                vals['addon_path_verified'] = False
            
            if (vals.get('module_type') or vals.get('odoo_version_id')) and not vals.get('addons_path'):
                if vals.get('module_type') and vals.get('module_type') == "core":
                    IrDefault = rec.env['ir.default'].sudo()
                    addons_path = IrDefault._get('res.config.settings', 'addons_path')
                    vals['addons_path'] = addons_path
                elif ((vals.get('module_type') and vals.get('module_type') == "custom") or (not vals.get('module_type') and rec.module_type =="custom")):
                    version = vals.get('odoo_version_id') or rec.odoo_version_id.id 
                    odoo_version_id = rec.env['saas.odoo.version'].browse(int(version))
                    vals['addons_path'] = odoo_version_id.common_addons_path


            res = super(SaasModule, rec).write(vals)
        return res
    
    def check_custom_addons_path(self):
        for rec in self:
            try:
                exists = False
                if os.path.isdir(rec.addons_path):
                    module_path = os.path.join(rec.addons_path, rec.technical_name)
                    if os.path.isdir(module_path):
                        if os.path.exists(os.path.join(module_path, '__manifest__.py')):
                            self.addon_path_verified = True
                            message = self.env['custom.message.wizard'].create({'message':"Path verified!"})
                            action = self.env.ref('odoo_saas_kit.custom_message_wizard_action').read()[0]
                            action['res_id'] = message.id
                            return action
                    raise UserError("Path verified but custom modules doesn't exists")
                raise UserError("Custom Addon's Path doesn't exist")
            except Exception as e:
                raise UserError(e)

