/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.ContractPortalOperation = publicWidget.Widget.extend({
    selector: '.contract_portal_page, .container',
    events: {
        'click .get_subdomain_email': '_onClickGetSubdomainEmail',
        'click .instance_login': '_onClickInstanceLogin',
        'click .renew_contract': '_onClickRenewBtn',
    },

    init() {
        this._super(...arguments);
        this.orm = this.bindService("orm");
    },

    _onClickGetSubdomainEmail:function(ev) {
        ev.stopPropagation();
        var contract_id = $("#contract_id").attr('value');
        this.orm.call("saas.contract", "get_subdomain_email", [contract_id])
        .then(function(){
            console.log("--Email sent--")
        });
    },


    _onClickInstanceLogin: function(ev){
        ev.stopPropagation();
        var client_id = parseInt($('.instance_login').attr('client_id'));
        this.orm.read("saas.client",[client_id], ['client_url'])
        .then(function(url){
            window.open(url[0]['client_url'], "_blank");
        });
    },

    _onClickRenewBtn: function(ev){
        var contract_id = parseInt($(ev.currentTarget).attr('contract_id'));
        this.orm.call("saas.contract", "generate_renew_invoice", [contract_id])
        .then(function(res){
            if(res.status == true){
                window.location.reload();
            }
            else{
                $('.err_alert').show();
                $('.err_alert').html(res.message);
            }
        });
    },
    
});
