/**
 * owner-party-select-module.js
 *
 * NOTE: Select2 initialization and change-handler logic for the
 * owner party dropdown have been moved into
 * pidinst-composite-enhancements.js (initPartySelects), because
 * updateCollapsiblePanels() clones/replaces composite row DOM nodes
 * before CKAN's module system can initialize this module, which caused
 * Select2 to be attached to a detached (off-DOM) element.
 *
 * This stub is retained so the webassets entry remains valid.
 */
this.ckan.module('owner-party-select-module', function ($, _) {
  'use strict';
  return {
    initialize: function () {}
  };
});
