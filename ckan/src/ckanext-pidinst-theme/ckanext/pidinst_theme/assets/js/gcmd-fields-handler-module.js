this.ckan.module('gcmd-fields-handler-module', function ($, _) {
    return {
        initialize: function () {
            this.textInputElement = $('#field-gcmd_keywords');
            this.inputElement = $('#field-gcmd_keywords_code');

            this.initializeSelect2();
            this.prepopulateSelect2();

        },

        initializeSelect2: function () {

            var self = this;
            var nextPage = 0;
            var lastSearchTerm = null;

            this.inputElement.select2({
                placeholder: "Select GCMD Keywords",
                delay: 250,
                minimumInputLength: 3,
                tags: [],
                tokenSeparators: [",", " "],
                multiple: true,
                cache: true,
                query: function (query) {
                    if (lastSearchTerm !== query.term) {
                        nextPage = 0; 
                        lastSearchTerm = query.term; 
                    }

                    var apiUrl = '/api/proxy/fetch_gcmd';
                    var data = {
                        page: nextPage, 
                        keywords: query.term 
                    };

                    $.ajax({
                        type: 'GET',
                        url: apiUrl,
                        data: data, 
                        dataType: 'json',
                        success: function (response) {
                            nextUrl = response.result.next;
                            var items = response.result.items.map(function (item) {
                                return { id: item._about, text: item.prefLabel._value };
                            });
                            nextPage = response.result.page + 1;
                            query.callback({ results: items, more: !!response.result.next });
                        }
                    });
                }
            }).on("change", function (e) {
                self.updateDependentFields();
            });
        },
        updateDependentFields: function () {
            var self = this;
            var selectedData = self.inputElement.select2('data');
            var texts = selectedData.map(function (item) { return item.text; });
            self.textInputElement.val(JSON.stringify(texts));
        },

        prepopulateSelect2: function () {
            var self = this;
            var existingIdsString = this.inputElement.val();
            var existingIds = existingIdsString ? existingIdsString.split(',') : [];

            var existingTextsString = this.textInputElement.val();
            var existingTexts = existingTextsString ? JSON.parse(existingTextsString) : [];
            if (existingIds.length > 0 && existingIds[0] !== "") {
                var dataForSelect2 = existingIds.map(function (id, index) {
                    return { id: id, text: existingTexts[index] };
                });
                self.inputElement.select2('data', dataForSelect2, true);
            }
            // self.inputElement.val(existingIds);
        },
    };
});
