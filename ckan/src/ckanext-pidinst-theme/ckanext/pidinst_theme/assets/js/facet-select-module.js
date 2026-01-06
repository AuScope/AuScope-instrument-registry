this.ckan.module('facet-select-module', function ($, _) {
    return {
        initialize: function () {
            this.inputElements = this.el.find('.facet-select');
            this.title = this.el.data('title');
            if (this.inputElements.length > 0) {
                this.initializeSelect2();
            } else {
                setTimeout(this.initialize.bind(this), 500);
            }
        },

        initializeSelect2: function () {
            var self = this;
            this.inputElements.each(function () {
                var $element = $(this);
                $element.select2({
                    placeholder: "Select " + self.title,
                    allowClear: true,
                    width: 'resolve'
                }).on("change", function (e) {
                    self.updateQueryString($element);
                });
            });
        },

        updateQueryString: function ($element) {
            var selectedValues = $element.val();
            var url = new URL(window.location.href);
            var params = new URLSearchParams(url.search);
            params.delete($element.attr('name'));

            if (selectedValues) {
                selectedValues.forEach(function (value) {
                    params.append($element.attr('name'), value);
                });
            }

            url.search = params.toString();
            window.history.pushState({}, '', url.toString());

            // Hide the select2 container and show loading indicator
            $element.select2('destroy');
            this.el.find('.loading-indicator').show();
            $element.hide();

            // Delay the page reload to ensure the loading indicator is visible
            setTimeout(function () {
                window.location.reload();
            }, 500);
        }
    };
});
