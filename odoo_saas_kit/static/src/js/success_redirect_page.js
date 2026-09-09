/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.SaasAccountRedirect = publicWidget.Widget.extend({
    selector: '.redirect_page_div',
    events: {

        'click .go_to_account': '_onClickGoToAcc',
    },

    init() {
        this._super(...arguments);
        this.orm = this.bindService("orm");
    },
    
    _onClickGoToAcc: function(ev){
        var contract_id = $(ev.currentTarget).val();
        this.orm.call("saas.contract", "redirect_invitation_url", [contract_id])
        .then(function(url){
            location.href=url;
        });
    },
    
});
