/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { session } from "@web/session";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.SaasUserModel = publicWidget.Widget.extend({
    selector: '.users_no_div',
    events: {
        'click #modal_target': '_onClickModalTarget',
    },

    init() {
        this._super(...arguments);
        this.orm = this.bindService("orm");
    },
        
    _onClickModalTarget:function(){
        if (session.is_public){
            alert("Please login First to Continue !");
            return;
        }
        var min_users = parseInt($('#min_user')).text;
        $('#new_min_user').attr('value',min_users);
        var product_id = parseInt($('.product_id').attr('value'));
        min_users = $('#new_min_user').val()
        $('#total_cost').text('');                
        this.orm.read("product.product",[product_id], ['user_cost'])
        .then(function(data){
            var total_amount = min_users * (parseFloat(data[0]['user_cost']));
            var website_currency_id = parseInt($('#website_currency_id').text());
            rpc("/get/converted/price", {'website_currency_id': website_currency_id, 'total_amount': total_amount}).then(function (data){
                var converted_amount = parseFloat(data.converted_amount);
                $('#total_cost').text(converted_amount.toFixed(2));
                $("#modify_min_users").modal("toggle");
            });
        });            
    },
});

publicWidget.registry.SaasUserCount = publicWidget.Widget.extend({
    selector: '#modify_min_users',
    events: {
        'change #new_min_user': '_onChangeNewMinUser',
        'click #min_user_submit': '_onClickMinUserSubmit',
    },

    init() {
        this._super(...arguments);
        this.orm = this.bindService("orm");
    },

    async _onChangeNewMinUser(){
        var min_users = parseInt($('#min_user_quantity').attr('value'));
        var max_users = parseInt($('#max_user_quantity').attr('value'));
        var new_user = parseInt($('#new_min_user').val());
        var product_id = parseInt($('.product_id').attr('value'));
        if (new_user < min_users){
            alert("User must be more than or equal to "+ min_users);
        }
        else if(new_user > max_users && max_users !== -1){
            alert("User must be less than or equal to "+ max_users);
        }else{
            const data = await this.orm.read("product.product",[product_id], ['user_cost'])
                var total_amount = new_user * parseFloat(data[0]['user_cost']);
                var website_currency_id = parseInt($('#website_currency_id').text());
                rpc("/get/converted/price", {'website_currency_id': website_currency_id, 'total_amount': total_amount}).then(function (data){
                    var converted_amount = parseFloat(data.converted_amount);
                    $('#total_cost').text(converted_amount.toFixed(2));
                });
        }
    },

    _onClickMinUserSubmit:function(){
        var min_users = parseInt($('#min_user_quantity').attr('value'));
        var max_users = parseInt($('#max_user_quantity').attr('value'));
        var new_user = parseInt($('#new_min_user').val());
        if (new_user < min_users){
            alert("User must be more than or equal to "+ min_users);
        }
        else if(new_user > max_users && max_users !== -1){
            alert("User must be less than or equal to "+ max_users);
        }else{
            $('#min_user').text(new_user);
            $('#number_of_user').attr('value',new_user);
            $('#modify_min_users').modal('hide');
        }
    },
});
