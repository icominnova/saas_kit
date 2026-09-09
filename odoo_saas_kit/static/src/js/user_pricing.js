/** @odoo-module **/

// import { WebsiteSale } from '@website_sale/js/website_sale';
// import { WebsiteSale } from '@website_sale/interations/website_sale';
import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';
import wSaleUtils from '@website_sale/js/website_sale_utils';


patch(WebsiteSale.prototype, {

    _updateRootProduct(form) {
        super._updateRootProduct(...arguments);
        const productId = parseInt(
            form.querySelector('input[type="hidden"][name="product_id"]')?.value
        );
        console.log(form.querySelector('input[type="hidden"][name="number_of_user"]'));
        var number_of_user = form.querySelector('input[type="hidden"][name="number_of_user"]')?.value;
        this.rootProduct['number_of_user'] = number_of_user;
    }
});
