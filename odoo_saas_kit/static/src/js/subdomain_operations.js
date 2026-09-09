/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";


publicWidget.registry.ContractSubdomainOperations = publicWidget.Widget.extend({
    selector: '.contract_details_portal_page, .contract_subdomain_data_row, #add_custom_domain, .subdomain_revoke_button_div',
    events: {
        'click #add_domain_icon_div, #sub_domain_span_1': '_onClickAddDomain',
        'click #use_custom_domain': '_onClickUseCustomDomain',
        'click #btn_add_domain': '_onClickButtonAddDomain',
        'click .revoke_domain': '_onClickRevokeDomain',

    },

    init() {
        this._super(...arguments);
        this.orm = this.bindService("orm");
    },

    _onClickAddDomain: function(ev){
        $("#add_custom_domain").modal("toggle");
        $("#ssl_note").hide();
    },

    _onClickUseCustomDomain: function(ev){
        if($("#use_custom_domain").prop("checked") == true){
            $("#base_url_text").hide();
            $("#ssl_note").show();
        }
        else{
            $("#ssl_note").hide();
            $("#base_url_text").show();
        }
    },

    _onClickButtonAddDomain: function(ev){
        var contract_id = $('#contract_id').attr('value');
        var domain_name = $('#add_subdomain_name').val();
        var use_separate_domain = $("#use_custom_domain").prop("checked")
        var is_ssl = false;
        if($("#add_subdomain_is_ssl").prop("checked") == true){
            is_ssl = true
        }
        rpc("/my/saas/contract/add/domain", {
            'contract_id':contract_id, 'domain_name':domain_name,'is_ssl':is_ssl,'use_separate_domain':use_separate_domain,
        }).then(function(vals){
            console.log(vals);
            if (vals['response']['status']){
                $("#add_custom_domain").modal("hide");
                $('#domain_tbody').replaceWith(vals['data']);
            }else{
                $('#domain_taken_warning').text(vals['response']['msg']);
                $('#domain_taken_warning').show();
            }
        });
    },

    _onClickRevokeDomain:function(ev){
        var answer = confirm("Are You Sure You want to Revoke this domain..?");
        if (answer == true){
            var domain_id = parseInt($(ev.currentTarget).attr('domain_id'));
            this.orm.call("custom.domain", "revoke_subdomain_call", [domain_id])
            .then(function(url){
                location.href = url
            });
        }
    },
});
