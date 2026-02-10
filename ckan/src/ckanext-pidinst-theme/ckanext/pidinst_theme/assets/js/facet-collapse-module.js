/**
 * facet-collapse-module.js
 *
 * Handles collapsible facet sections and checkbox-driven filtering.
 *  - Click heading to collapse/expand
 *  - Checking/unchecking a checkbox navigates to the filtered URL
 *  - Search input filters the visible checkbox items
 */
this.ckan.module('facet-collapse-module', function ($, _) {
    return {
        initialize: function () {
            var self = this;

            // -- Collapse toggle --
            this.heading = this.el.find('.facet-section-heading');
            this.body = this.el.find('.facet-section-body');

            this.heading.on('click', function () {
                self.body.slideToggle(200);
                self.heading.find('.facet-toggle-icon').toggleClass('fa-chevron-up fa-chevron-down');
                var expanded = self.heading.attr('aria-expanded') === 'true';
                self.heading.attr('aria-expanded', !expanded);
            });

            // -- Checkbox change => navigate --
            this.el.find('[data-facet-checkbox]').on('change', function () {
                self.applyCheckboxFilter();
            });

            // -- Search / filter input --
            this.el.find('.facet-search-input').on('input', function () {
                var query = $(this).val().toLowerCase();
                self.el.find('.facet-check-item').each(function () {
                    var text = $(this).data('facet-value') || '';
                    $(this).toggle(text.indexOf(query) !== -1);
                });
            });
        },

        applyCheckboxFilter: function () {
            var url = new URL(window.location.href);
            var params = new URLSearchParams(url.search);

            // Collect all checkbox groups inside this section
            this.el.find('.facet-check-list').each(function () {
                var $checkboxes = $(this).find('[data-facet-checkbox]');
                if ($checkboxes.length === 0) return;

                var facetName = $checkboxes.first().attr('name');
                params.delete(facetName);

                $checkboxes.filter(':checked').each(function () {
                    params.append(facetName, $(this).val());
                });
            });

            // Remove page param so we go back to page 1
            params.delete('page');

            url.search = params.toString();
            window.location.href = url.toString();
        }
    };
});
