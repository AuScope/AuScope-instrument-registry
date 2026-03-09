/**
 * ror-owner-module.js
 *
 * CKAN JS module for the Owner (ROR) lookup field.
 * Uses Select2 to search the backend ROR proxy endpoint and populates
 * hidden metadata fields with the resolved organisation data + parent
 * hierarchy.
 *
 * Follows the same pattern as gcmd-fields-handler-module.js.
 */
this.ckan.module('ror-owner-module', function ($, _) {
    'use strict';

    // Hidden field IDs that hold the cached ROR metadata.
    var HIDDEN_FIELDS = [
        'owner_ror_id',
        'owner_ror_name',
        'owner_ror_types',
        'owner_ror_country',
        'owner_ror_state',
        'owner_ror_website',
        'owner_ror_parents_json',
        'owner_ror_hierarchy_display'
    ];

    var SEARCH_URL = '/api/proxy/ror_search';
    var DEBOUNCE_MS = 350;
    var MIN_CHARS = 2;

    return {
        initialize: function () {
            this.lookupInput = this.el.find('.ror-owner-lookup');
            this.hierarchyPreview = this.el.find('#ror-hierarchy-preview');
            this.hierarchyText = this.el.find('#ror-hierarchy-text');

            this._initSelect2();
            this._prepopulate();
        },

        // ----------------------------------------------------------------
        // Select2 initialisation
        // ----------------------------------------------------------------
        _initSelect2: function () {
            var self = this;
            var debounceTimer = null;

            this.lookupInput.select2({
                placeholder: 'Start typing to search ROR…',
                minimumInputLength: MIN_CHARS,
                allowClear: true,
                // Single selection
                multiple: false,
                // Remote data source
                ajax: {
                    url: SEARCH_URL,
                    dataType: 'json',
                    quietMillis: DEBOUNCE_MS,
                    data: function (term) {
                        return { q: term };
                    },
                    results: function (data) {
                        return { results: data.results || [] };
                    },
                    cache: true
                },
                // Render each result
                formatResult: function (item) {
                    var html = '<div class="ror-result">';
                    html += '<strong>' + self._escapeHtml(item.name) + '</strong>';
                    if (item.types) {
                        html += ' <small class="text-muted">(' + self._escapeHtml(item.types) + ')</small>';
                    }
                    if (item.state) {
                        html += '<br><small class="text-muted"><i class="fa fa-map-marker"></i> ' + self._escapeHtml(item.state) + ', ' + self._escapeHtml(item.country) + '</small>';
                    }
                    if (item.hierarchy_display && item.hierarchy_display !== item.name) {
                        html += '<br><small class="text-muted"><i class="fa fa-sitemap"></i> ' + self._escapeHtml(item.hierarchy_display) + '</small>';
                    }
                    html += '</div>';
                    return html;
                },
                formatSelection: function (item) {
                    return self._escapeHtml(item.name || item.text);
                },
                // Allow HTML in results
                escapeMarkup: function (m) { return m; }
            })
            .on('change', function (e) {
                if (e.added) {
                    self._onSelect(e.added);
                } else if (e.removed || !self.lookupInput.select2('data')) {
                    self._onClear();
                }
            });
        },

        // ----------------------------------------------------------------
        // Populate hidden fields when a result is selected
        // ----------------------------------------------------------------
        _onSelect: function (item) {
            this._setHidden('owner_ror_id', item.ror_id || item.id || '');
            this._setHidden('owner_ror_name', item.name || '');
            this._setHidden('owner_ror_types', item.types || '');
            this._setHidden('owner_ror_country', item.country || '');
            this._setHidden('owner_ror_state', item.state || '');
            this._setHidden('owner_ror_website', item.website || '');
            this._setHidden('owner_ror_parents_json', item.parents_json || '[]');
            this._setHidden('owner_ror_hierarchy_display', item.hierarchy_display || '');

            // Show hierarchy preview
            var hierarchy = item.hierarchy_display || item.name || '';
            if (hierarchy) {
                this.hierarchyText.text(hierarchy);
                this.hierarchyPreview.show();
            }
        },

        // ----------------------------------------------------------------
        // Clear all hidden fields when the selection is removed
        // ----------------------------------------------------------------
        _onClear: function () {
            for (var i = 0; i < HIDDEN_FIELDS.length; i++) {
                this._setHidden(HIDDEN_FIELDS[i], '');
            }
            this.hierarchyPreview.hide();
            this.hierarchyText.text('');
        },

        // ----------------------------------------------------------------
        // On edit: prepopulate Select2 from existing hidden field values
        // ----------------------------------------------------------------
        _prepopulate: function () {
            var rorId = this._getHidden('owner_ror_id');
            var rorName = this.lookupInput.data('display-name') || this._getHidden('owner_ror_name');

            if (rorId && rorName) {
                this.lookupInput.select2('data', {
                    id: rorId,
                    text: rorName,
                    name: rorName
                });

                // Show hierarchy if available
                var hierarchy = this._getHidden('owner_ror_hierarchy_display');
                if (hierarchy) {
                    this.hierarchyText.text(hierarchy);
                    this.hierarchyPreview.show();
                }
            }
        },

        // ----------------------------------------------------------------
        // Helpers
        // ----------------------------------------------------------------
        _setHidden: function (fieldName, value) {
            var el = $('#field-' + fieldName);
            if (el.length) {
                el.val(value);
            }
        },

        _getHidden: function (fieldName) {
            var el = $('#field-' + fieldName);
            return el.length ? el.val() : '';
        },

        _escapeHtml: function (str) {
            if (!str) return '';
            var div = document.createElement('div');
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        }
    };
});
