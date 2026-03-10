/**
 * owner-facility-select-module.js
 *
 * CKAN module for the <select> dropdown in the instrument_owner
 * composite_repeating field.  When a facility is selected:
 *   - Fills the hidden owner_facility_name field
 *   - Pre-fills owner_contact from the facility's contact (if set)
 *     but only when the contact field is currently empty.
 */
this.ckan.module('owner-facility-select-module', function ($, _) {
  'use strict';

  return {
    initialize: function () {
      var self = this;
      var $select = self.el.find('.owner-facility-dropdown');
      if (!$select.length) return;

      $select.on('change', function () {
        var $opt   = $select.find('option:selected');
        var prefix = $select.data('field-prefix');
        if (!prefix) return;

        var facTitle   = $opt.data('facility-title') || '';
        var facContact = $opt.data('facility-contact') || '';

        // Set the hidden name field
        var $nameField = $('#field-' + prefix + 'owner_facility_name');
        if ($nameField.length) {
          $nameField.val(facTitle);
        }

        // Pre-fill contact only if currently blank
        var $contactField = $('#field-' + prefix + 'owner_contact');
        if ($contactField.length && !$contactField.val().trim() && facContact) {
          $contactField.val(facContact);
        }
      });
    }
  };
});
