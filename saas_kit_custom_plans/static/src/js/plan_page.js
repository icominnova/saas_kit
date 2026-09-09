/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";


/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : https://store.webkul.com/license.html/ */
publicWidget.registry.saas_kit_plans = publicWidget.Widget.extend({
    selector: '#saas_plans',

    events: {
        'click #community_btn': '_showCommunityPlans',
        'click #enterprise_btn': '_showEnterprisePlans',
        'click .community_version_button': '_fetch_community_plans',
        'click .enterprise_version_button': '_fetch_enterprise_plans',
        
    },

    start: function () {
        this._fetch().then(this._render.bind(this));
        return this._super.apply(this, arguments);
    },
    _fetch: function () {

        return $.get('/saas/version/data')
        .then(function(res) {
            return res;
        });
    },
    _render: async function (res) {
        if(res){
            await $(".saas_plans").html(res);
            this._fetch_community_plans();
        }
        else{
            await $(".saas_plans").html(`<div class="text-center py-3">No Saas Odoo Versions Found.</div>`);
        }
    },

    _fetch_community_plans: function(ev) {
        var self = this;
        var version_id = null;
        if(ev){
            version_id = $(ev.currentTarget).attr('data-id');
            $('.def_community_version_btn').text($(ev.currentTarget).text());
        }
        else{
            version_id = $('.def_community_version_btn').attr('data-id');
        }
        return $.get(`/saas/plans/data/${parseInt(version_id)}`)
        .then(function(res) {
            $('div.community_plans_card').html(res);
            self._saas_plan_carousel()
            let cards = document.querySelectorAll('.plan_card');
            let maxHeight = Math.max(...Array.from(cards).map(card => card.offsetHeight));
            cards.forEach(card => {
                card.style.height = `${maxHeight}px`;
            });
            return res;
        });
    },

    _fetch_enterprise_plans: function(ev) {
        var self = this;
        if(ev){
            var version_id = $(ev.currentTarget).attr('data-id');
            $('.def_enterprise_version_btn').text($(ev.currentTarget).text());
        }
        else{
            var version_id = $('.def_enterprise_version_btn').attr('data-id');
        }
        
        return $.get(`/saas/plans/data/${parseInt(version_id)}`)
        .then(function(res) {
            $('div.enterprise_plans_card').html(res);
            self._saas_plan_carousel()
            let cards = document.querySelectorAll('.plan_card');
            let maxHeight = Math.max(...Array.from(cards).map(card => card.offsetHeight));
            cards.forEach(card => {
                card.style.height = `${maxHeight}px`;
            });
            return res;
        });
    },

    
    _showCommunityPlans: function () {
        $('#enterprise_plans').hide();
        $('#community_plans').show();
        $(".enterprise_buttons_div").hide();
        $(".community_buttons_div").show();
        this._fetch_community_plans();
    },

    _showEnterprisePlans: function () {
        $('#enterprise_plans').show();
        $('#community_plans').hide();
        $(".enterprise_buttons_div").show();
        $(".community_buttons_div").hide();
        this._fetch_enterprise_plans();
    },
    
    _saas_plan_carousel: function () {
        $('.owl-carousel').owlCarousel({
            margin:5,
            loop:false,
            nav:false,
            dots: true,
            navigation : false,
            responsive: {
                0: {
                    items: 1,
                },
                600: {
                    items: 2,
                },
                1000: {
                    items: 3,
                }
            },
        });

        $('.customNextBtn').click(function() {
            $('.owl-carousel').trigger('next.owl.carousel');
        });
        // Go to the previous item
        $('.customPrevBtn').click(function() {
            $('.owl-carousel').trigger('prev.owl.carousel', [300]);
        });
    },

});

    
