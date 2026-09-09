# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://store.webkul.com/license.html/>
# 
#################################################################################

import base64
import logging
import json
from odoo import http, _, fields
from odoo.http import request
from odoo.addons.website_sale.controllers.cart import Cart
from odoo.tools.json import scriptsafe as json_scriptsafe
from odoo.addons.payment import utils as payment_utils
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MailController(http.Controller):
    _cp_path = '/mail'

    @http.route(['/mail/confirm_domain'], type='jsonrpc', auth="public", methods=['POST'], website=True)
    def confirm_domain(self, domain_name, contract_id,  **kw):
        """
        This controller is called when the customers submits the domain name from the controller.
        """
        contract = request.env['saas.contract'].sudo().search([('domain_name', '=ilike', domain_name), ('state', '!=', 'cancel')])
        if contract:
            _logger.info("---------ALREADY TAKEN--------%r", contract)
            return dict(
                status=1
            )
        else:
            _logger.info("---------CREATING CLIENT--------%r", contract)
            contract = request.env['saas.contract'].sudo().browse(int(contract_id))
            if contract.state == 'draft' and ((contract.server_id and contract.server_id.total_clients < contract.server_id.max_clients) or (not contract.server_id)) and not contract.saas_client:
                contract.domain_name = domain_name
                try:
                    # Creating Client -- Script Called--START
                    contract.create_saas_client()
                    # Creating Client -- Script Called--END
                    if contract.saas_client and contract.saas_client.client_url:
                        _logger.info("---Success----------")
                        return dict(
                            status=2,
                            url=contract.saas_client.client_url
                        )
                except Exception as e:
                    body = "An Exception is occur while creating client : {}".format(e)
                    contract.message_post(body=body, subject="Client Creation Exceptions")
                    _logger.info("---1----------%r", e)
                    return dict(
                        status=3,
                    )
            _logger.info("---3----------")
            body = "An Exception occur: \n Please Check Contract Not be in Draft State, or Maximum Client Limit Exceeds, or Client Exist with same Contract"
            contract.message_post(body=body, subject="Client Creation Exceptions")
            return dict(
                status=3,
            )

    @http.route('/mail/contract/subdomain', type='http', auth='public', website=True)
    def mail_action_view(self, contract_id=None, token=None, partner_id=None, **kwargs):
        """
        This controller returns the domain selection portal page for the customer.
        """
        if contract_id and token and partner_id:
            contract = request.env['saas.contract'].sudo().browse(int(contract_id))
            if contract.exists() and (contract.partner_id.id == int(partner_id)) and (contract.access_token == token) and (contract.state == 'draft'):
                return request.render('odoo_saas_kit.subdomain_page', {
                    'contract_id': contract_id,
                    'contract': contract,
                    'base_url': contract.saas_domain_url,
                    'page_name': 'saas_subdomain',
                })
            else:
                return request.redirect('/my')
        else:
            return request.redirect('/error')

    @http.route('/client/domain-created/redirect', type="http", auth="public", website=True)
    def domain_set_template(self, contract_id=None, **kwargs):
        contract_id = int(contract_id)
        contract = request.env['saas.contract'].sudo().browse([contract_id])
        base_url=request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        status_url = contract.get_portal_url()

        values = {
            'contract_id' : contract_id,
            'status_url' : status_url
        }
        active_partner = request.env.user.partner_id
        if contract.exists() and contract.partner_id.id == active_partner.id:
            return request.render('odoo_saas_kit.redirect_page', values)
        else:
            return request.redirect('/my')


class SaaSCustomCart(Cart):
    



    @http.route()
    def add_to_cart(
        self,
        product_template_id,
        product_id,
        quantity=1.0,
        uom_id=None,
        product_custom_attribute_values=None,
        no_variant_attribute_value_ids=None,
        linked_products=None,
        **kwargs
    ):
        """
        Override the controller to add the extra line for user pricing in website with custom price based on number of users and number of cycles.
        """

        order_sudo = request.cart or request.website._create_cart()
        quantity = int(quantity)  # Do not allow float values in ecommerce by default

        product = request.env['product.product'].browse(product_id).exists()
        
        if not product or not product._is_add_to_cart_allowed():
            raise UserError(_(
                "The given product does not exist therefore it cannot be added to cart."
            ))
        
        
        warning = None
        IrDefault = request.env['ir.default'].sudo()
        restrict_cart = IrDefault._get('res.config.settings', 'restrict_add_to_cart')
        if restrict_cart and product.saas_plan_id:
            cart_products = order_sudo.order_line.mapped('product_id')
            if int(product_id) in cart_products.ids:
                warning = _("You have already added this Saas plan to the cart. You can update the quantity on the cart page!")
            saas_plan = cart_products.mapped('saas_plan_id')
            if not warning and saas_plan:
                warning = _("You already have a Saas Plan added to your cart!! Please remove it first to purchase another plan.")

        if warning:
            return {
                        'cart_quantity': order_sudo.cart_quantity,
                        'notification_info': {
                            'warning': warning,
                        },
                        'quantity': 0,
                        'tracking_info': [],
                    }
        added_qty_per_line = {}
        values = order_sudo.with_context(skip_cart_verification=True)._cart_add(
            product_id=product_id,
            quantity=quantity,
            uom_id=uom_id,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            **kwargs,
        )
        line_ids = {product_template_id: values['line_id']}
        added_qty_per_line[values['line_id']] = values['added_qty']
        is_combo = product.type == 'combo'
        updated_line = (
            values['line_id']
            and order_sudo.order_line.filtered(lambda line: line.id == values['line_id'])
        ) or order_sudo.env['sale.order.line']

        if linked_products and values['line_id']:
            for product_data in linked_products:
                product_sudo = request.env['product.product'].sudo().browse(
                    product_data['product_id']
                ).exists()
                if product_data['quantity'] and (
                    not product_sudo
                    or (
                        not product_sudo._is_add_to_cart_allowed()
                        # For combos, the validity of the given product will be checked
                        # through the SOline constraints (_check_combo_item_id)
                        and not product_data.get('combo_item_id')
                    )
                ):
                    raise UserError(_(
                        "The given product does not exist therefore it cannot be added to cart."
                    ))

                product_values = order_sudo.with_context(skip_cart_verification=True)._cart_add(
                    product_id=product_data['product_id'],
                    quantity=product_data['quantity'],
                    uom_id=product_data.get('uom_id'),
                    product_custom_attribute_values=product_data['product_custom_attribute_values'],
                    no_variant_attribute_value_ids=[
                        int(value_id) for value_id in product_data['no_variant_attribute_value_ids']
                    ],
                    # Using `line_ids[...]` instead of `line_ids.get(...)` ensures that this throws
                    # if an optional product contains bad data.
                    linked_line_id=line_ids[product_data['parent_product_template_id']],
                    **self._get_additional_cart_update_values(product_data),
                    **kwargs,
                )
                if is_combo and not product_values.get('quantity'):
                    # Early return when one of the combo products if fully unavailable
                    # Delete main combo line (and existing children in cascade)
                    updated_line.unlink()
                    # Return empty notification since cart update is considered as failed
                    return {
                        'cart_quantity': order_sudo.cart_quantity,
                        'notification_info': {
                            'warning': product_values.get('warning', ''),
                        },
                        'quantity': 0,
                        'tracking_info': [],
                    }

                line_ids[product_data['product_template_id']] = product_values['line_id']
                added_qty_per_line[product_values['line_id']] = product_values['added_qty']

        warning = values.pop('warning', '')
        if is_combo and order_sudo._check_combo_quantities(updated_line):
            # If quantities were modified through `_check_combo_quantities`, the added qty per line
            # must be adapted accordingly, and the returned warning should be the final one saved
            # on the combo line.
            added_qty_per_line = {
                line.id: updated_line.product_uom_qty
                for line in (updated_line + updated_line.linked_line_ids)
            }
            warning = updated_line.shop_warning
            values['quantity'] = updated_line.product_uom_qty

        # Recompute delivery prices & other cart stuff (loyalty rewards)
        order_sudo._verify_cart_after_update()

        # The validity of a combo product line can only be checked after creating all of its combo
        # item lines.
        main_product_line = request.env['sale.order.line'].browse(values['line_id'])
        if main_product_line.product_type == 'combo':
            main_product_line._check_validity()


        if product.saas_plan_id and product.saas_plan_id.per_user_pricing and product.saas_plan_id.user_product:
            user_pricing_product = product.saas_plan_id.user_product
            if not user_pricing_product.sudo() or not user_pricing_product.sudo()._is_add_to_cart_allowed():
                updated_line.unlink()
                order_sudo._verify_cart_after_update()
                return {
                        'cart_quantity': order_sudo.cart_quantity,
                        'notification_info': {
                            'warning': _("This service is currently unavailable. Kindly contact admin."),
                        },
                        'quantity': 0,
                        'tracking_info': [],
                    }
            number_of_user = kwargs.get('number_of_user') or 1
            line_config = order_sudo._cart_add(
                product_id=int(user_pricing_product.id),
                quantity=quantity,
            )
            product_amount = int(number_of_user) * float(product.user_cost)
            from_currency = request.env.company.currency_id
            converted_amount = from_currency._convert(product_amount, request.website.currency_id, request.env.company, fields.Date.today())
            order_line = request.env['sale.order.line'].sudo().browse(int(line_config['line_id']))
            plan_line_id = request.env['sale.order.line'].sudo().browse(int(values['line_id']))
            plan_line_id.write({
                'plan_line_id': order_line.id,
            })
            self.env.cr.commit()
            order_line.write({'price_unit': round(converted_amount, 2),
            'is_user_product': True,
            'saas_users': int(number_of_user),
            'saas_users_unit_price': float(product.user_cost),
            'linked_line_id': plan_line_id.id,
            })
            # order_line._cr.commit()
            self.env.cr.commit()

        return {
            'cart_quantity': order_sudo.cart_quantity,
            'notification_info': {
                **self._get_cart_notification_information(
                    order_sudo, added_qty_per_line
                ),
                'warning': warning,
            },
            'quantity': values.pop('quantity', 0),
            'tracking_info': self._get_tracking_information(order_sudo, line_ids.values()),
        }
    

    @http.route()
    def update_cart(self, line_id, quantity, product_id=None, **kwargs):
        order_sudo = request.cart
        quantity = int(quantity)  # Do not allow float values in ecommerce by default
        IrUiView = request.env['ir.ui.view']

        if not line_id:
            line_id = order_sudo.order_line.filtered(
                lambda sol: sol.product_id.id == product_id
            )[:1].id

        values = order_sudo._cart_update_line_quantity(line_id, quantity, **kwargs)

        values['cart_quantity'] = order_sudo.cart_quantity
        values['cart_ready'] = order_sudo._is_cart_ready()
        values['amount'] = order_sudo.amount_total
        values['minor_amount'] = (
            order_sudo and payment_utils.to_minor_currency_units(
                order_sudo.amount_total, order_sudo.currency_id
            )
        ) or 0.0
        values['website_sale.cart_lines'] = IrUiView._render_template(
            'website_sale.cart_lines', {
                'website_sale_order': order_sudo,
                'date': fields.Date.today(),
                'suggested_products': order_sudo._cart_accessories()
            }
        )
        values['website_sale.total'] = IrUiView._render_template(
            'website_sale.total', {
                'website_sale_order': order_sudo,
            }
        )
        values['website_sale.quick_reorder_history'] = IrUiView._render_template(
            'website_sale.quick_reorder_history', {
                'website_sale_order': order_sudo,
                **self._prepare_order_history(),
            }
        )
        return values


    @http.route(['/get/converted/price'], type='jsonrpc', auth="public", methods=['POST'], website=True, csrf=False)
    def get_converted_price(self, website_currency_id, total_amount, **kw):
        if website_currency_id:
            website_currency = request.env['res.currency'].browse([int(website_currency_id)])
            from_currency = request.env.company.currency_id
            converted_amount = from_currency._convert(total_amount, website_currency, request.env.company, fields.Date.today())
            return {'converted_amount': float(converted_amount)}
