/**
 * Unified autocomplete module for field-scoped terms.
 * Supports both single and multiple selection modes.
 * Uses <input> for Select2 tags UI with hidden input for JSON storage.
 * 
 * Options (data attributes):
 * - data-field-name: The field name to fetch terms for
 * - data-allow-new: Whether to allow creating new terms (default: true)
 * - data-multiple: Whether to allow multiple selections (default: true)
 */
this.ckan.module('field-terms-autocomplete-module', function ($, _) {
    return {
        initialize: function () {
            // Guard against double initialization
            if (this.el.data('select2-initialized')) {
                return;
            }
            this.el.data('select2-initialized', true);

            this.fieldName = this.el.data('field-name');
            this.allowNew = this.el.data('allow-new') !== false;
            this.isMultiple = this.el.data('multiple') !== false;
            
            // Find elements within this container using class selectors for reliability
            this.hiddenElement = this.el.find('input[type="hidden"]');
            this.inputElement = this.el.find('.field-terms-input');
            
            // Parse existing terms from hidden field (contains JSON)
            this.existingTerms = this.parseExistingValue();
            
            // Clear visible input to prevent JSON from showing
            this.inputElement.val('');
            
            this.initializeSelect2();
            this.prepopulateSelect2();
        },

        parseExistingValue: function () {
            // Read from hidden element which contains the JSON string
            var rawValue = this.hiddenElement.val();
            
            if (!rawValue || rawValue === '[]' || rawValue === '""' || rawValue === 'null' || rawValue === 'None') {
                return [];
            }
            
            // Guard: never return raw JSON string as a single value
            if (typeof rawValue === 'string' && rawValue.trim().startsWith('[')) {
                // Decode HTML entities that might be in the value attribute
                var decoded = $('<textarea>').html(rawValue).val();
                
                // Try standard JSON parsing
                try {
                    var parsed = JSON.parse(decoded);
                    if (Array.isArray(parsed)) {
                        return parsed.filter(function(t) { return t && typeof t === 'string' && t.trim(); });
                    }
                } catch (e) {
                    // If JSON parsing fails, try handling Python-style list notation
                    try {
                        var jsonFixed = decoded.replace(/'/g, '"');
                        var parsed = JSON.parse(jsonFixed);
                        if (Array.isArray(parsed)) {
                            return parsed.filter(function(t) { return t && typeof t === 'string' && t.trim(); });
                        }
                    } catch (e2) {
                        // Still failed - strip brackets and split by comma
                        var inner = decoded.slice(1, -1).trim();
                        if (inner) {
                            var matches = inner.match(/["']([^"']+)["']/g);
                            if (matches && matches.length > 0) {
                                return matches.map(function(m) {
                                    return m.replace(/^["']|["']$/g, '').trim();
                                }).filter(Boolean);
                            }
                            return inner.split(',').map(function(t) {
                                return t.trim().replace(/^['"]|['"]$/g, '');
                            }).filter(Boolean);
                        }
                    }
                }
                return [];
            }
            
            // Decode HTML entities
            var decoded = $('<textarea>').html(rawValue).val();
            
            // Comma-separated values without brackets
            if (decoded.indexOf(',') > -1) {
                return decoded.split(',').map(function(t) { return t.trim(); }).filter(Boolean);
            }
            
            return decoded.trim() ? [decoded.trim()] : [];
        },

        initializeSelect2: function () {
            var self = this;
            var tokenSeparators = (self.allowNew && self.isMultiple) ? [","] : [];

            var select2Options = {
                placeholder: self.isMultiple ? "Type to search or add terms" : "Type to search or select",
                delay: 250,
                minimumInputLength: 0,
                tags: self.allowNew ? [] : false,
                tokenSeparators: tokenSeparators,
                multiple: self.isMultiple,
                allowClear: !self.isMultiple,
                createSearchChoice: self.allowNew ? function(term, data) {
                    var exists = data.some(function(item) {
                        return item.text.toLowerCase() === term.toLowerCase();
                    });
                    if (!exists && term.trim()) {
                        return { id: term.trim(), text: term.trim() };
                    }
                    return null;
                } : undefined,
                query: function (query) {
                    var apiUrl = '/api/field_terms/' + self.fieldName;
                    $.ajax({
                        type: 'GET',
                        url: apiUrl,
                        data: { q: query.term || '' },
                        dataType: 'json',
                        success: function (response) {
                            var items = (response.terms || []).map(function (term) {
                                return { id: term, text: term };
                            });
                            query.callback({ results: items });
                        },
                        error: function() {
                            query.callback({ results: [] });
                        }
                    });
                }
            };

            this.inputElement.select2(select2Options).on("change", function (e) {
                self.updateHiddenField();
            });
        },

        updateHiddenField: function () {
            // Write JSON value to hidden input only (which has the field name for form submission)
            // Never set the Select2 input value to JSON
            var selectedData = this.inputElement.select2('data');
            if (this.isMultiple) {
                var values = [];
                if (selectedData && selectedData.length > 0) {
                    values = selectedData.map(function (item) { 
                        return item.text || item.id; 
                    }).filter(Boolean);
                }
                this.hiddenElement.val(JSON.stringify(values));
            } else {
                if (selectedData && (selectedData.text || selectedData.id)) {
                    this.hiddenElement.val(selectedData.text || selectedData.id);
                } else {
                    this.hiddenElement.val('');
                }
            }
        },

        prepopulateSelect2: function () {
            // Prepopulate Select2 with existing terms from hidden field.
            // In Select2 v3, select2('data', [{id, text}]) is the reliable API
            // for programmatic value setting in tags mode (same approach as gcmd module).
            if (!this.existingTerms || this.existingTerms.length === 0) {
                return;
            }
            var dataForSelect2 = this.existingTerms.map(function (term) {
                return { id: term, text: term };
            });
            if (this.isMultiple) {
                this.inputElement.select2('data', dataForSelect2, true);
            } else {
                this.inputElement.select2('data', dataForSelect2[0], true);
            }
        }
    };
});

