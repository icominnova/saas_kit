/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
// import rpc from "@web/legacy/js/core/rpc";
// import ajax from "@web/legacy/js/core/ajax";
import { rpc } from "@web/core/network/rpc";


publicWidget.registry.GetSaasTrialProduct = publicWidget.Widget.extend({
    selector: '.get_trial_product_div',
    events: {
        'click .get_trial': '_onClickGetTrial',

    },

    _onClickGetTrial: function(event){
        var product_id = $(".product_id").attr('value');
        var quantity = $(".quantity").val();
        var saas_users = parseInt($('#new_min_user').val());
        rpc("/saas/trial/add/product", {
            'product_id': product_id,
            'quantity': quantity,
            'saas_users': saas_users,
        }).then(function(a){
            location.href='/shop/cart';
        });
    }
});
