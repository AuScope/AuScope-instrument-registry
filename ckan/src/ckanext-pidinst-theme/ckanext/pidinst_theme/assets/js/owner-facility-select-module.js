/**
 * owner-facility-select-module.js
 *
 * NOTE: Select2 initialization and change-handler logic for the
 * instrument_owner facility dropdown have been moved into
 * pidinst-composite-enhancements.js (initFacilitySelects), because
 * updateCollapsiblePanels() clones/replaces composite row DOM nodes
 * before CKAN's module system can initialize this module, which caused
 * Select2 to be attached to a detached (off-DOM) element.
 *
 * This stub is retained so the webassets entry remains valid.
 */
this.ckan.module('owner-facility-select-module', function ($, _) {
  'use strict';
  return {
    initialize: function () {}
  };
});
