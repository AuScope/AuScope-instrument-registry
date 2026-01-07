this.ckan.module("parent-instrument-selector-module", function ($, _) {
    return {
        initialize: function () {
            this.inputElement = $("#field-parent");
            this.initializeSelect2();
            this.prepopulateSelect2();
        },

        initializeSelect2: function () {
            var self = this;
            this.org_id = this.options.group;
            this.inputElement.select2({
                placeholder: "Select Parent of Instrument",
                minimumInputLength: 0,
                ajax: {
                    url: "/api/3/action/package_search",
                    dataType: "json",
                    quietMillis: 500,
                    data: function (term, page) {
                        return {
                            q: term,
                            fq: "owner_org:" + self.org_id,
                            rows: 1000,
                        };
                    },
                    results: function (data, page) {
                        if (!data.success) {
                            return { results: [] };
                        }
                        return {
                            results: data.result.results.map(function (item) {
                                return { id: item.id, text: item.title };
                            }),
                        };
                    },
                    cache: true,
                },
                formatResult: function (item) {
                    return item.text;
                },
                formatSelection: function (item) {
                    return item.text;
                },
                dropdownCssClass: "bigdrop",
                escapeMarkup: function (m) {
                    return m;
                }, // we do not want to escape markup since we are displaying html in results
            });
        },

        prepopulateSelect2: function () {
            var self = this;
            var existingId = this.inputElement.val();
            if (existingId) {
                $.ajax({
                    url: "/api/3/action/package_show",
                    data: { id: existingId },
                    type: "GET",
                    dataType: "json",
                    success: function (data) {
                        if (data.success && data.result) {
                            var item = data.result;
                            var dataForSelect2 = { id: item.id, text: item.title };
                            self.inputElement.select2("data", dataForSelect2, true);
                        }
                    },
                });
            }
        },
    };
});
