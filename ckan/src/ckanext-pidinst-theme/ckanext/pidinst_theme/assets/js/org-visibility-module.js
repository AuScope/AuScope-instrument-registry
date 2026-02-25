/**
 * org-visibility-module.js
 *
 * CKAN JS module that dynamically adjusts the "Visibility" (private) field
 * based on the user's capacity (role) in the selected organization.
 *
 * Each <option> in #field-organizations carries a data-capacity attribute
 * set by the Jinja template  (admin | editor | member).
 *
 * Rules:
 *   admin / editor  → can choose Private *or* Public
 *   member (or none) → forced to Private, Public option hidden, hint shown
 */
ckan.module('org-visibility', function ($) {
  'use strict';

  return {
    initialize: function () {
      this.orgSelect     = $('#field-organizations');
      this.privateSelect = $('#field-private');
      this.publicOption   = this.privateSelect.find('option[value="False"]');
      this.memberHint    = $('#visibility-member-hint');
      this.visControl    = $('#visibility-control');

      // Bind change event
      this.orgSelect.on('change', $.proxy(this._onOrgChange, this));

      // Run once on load to set initial state
      this._onOrgChange();
    },

    _onOrgChange: function () {
      var selected = this.orgSelect.find(':selected');
      var capacity = (selected.data('capacity') || '').toString().toLowerCase();

      if (!selected.val()) {
        // No org selected – hide visibility entirely
        this.visControl.hide();
        return;
      }

      this.visControl.show();

      if (capacity === 'admin' || capacity === 'editor') {
        // Elevanted role – allow Public & Private
        this.publicOption.show();
        this.memberHint.hide();
      } else {
        // Member or unknown – Private only
        this.publicOption.hide();
        this.privateSelect.val('True');
        this.memberHint.show();
      }
    }
  };
});
