/* Collapsible search-filter facets.
 *
 * Attach to the .pidinst-search-filters wrapper via data-module="facet-collapse-module".
 * Delegates heading clicks to toggle "is-collapsed" on the parent <section>,
 * and persists state in localStorage.
 */
"use strict";

ckan.module("facet-collapse-module", function ($) {
  var STORAGE_KEY = "pidinst-facet-collapse";

  return {
    initialize: function () {
      var self = this;
      var savedState = self._loadState();

      self.el.find("section.module").each(function () {
        var $section = $(this);
        var $heading = $section.children(".module-heading");
        if (!$heading.length) return;

        // Append caret indicator
        $heading.append('<span class="facet-collapse-caret" aria-hidden="true"></span>');

        // Restore collapsed state
        var key = self._key($section);
        if (savedState[key] === true) {
          $section.addClass("is-collapsed");
        }

        // Toggle on heading click
        $heading.on("click", function () {
          $section.toggleClass("is-collapsed");
          self._saveKey(key, $section.hasClass("is-collapsed"));
        });
      });
    },

    /** Derive a stable key from the section's heading text. */
    _key: function ($section) {
      return $section.children(".module-heading").text().trim().replace(/\s+/g, " ");
    },

    _loadState: function () {
      try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      } catch (e) {
        return {};
      }
    },

    _saveKey: function (key, collapsed) {
      try {
        var state = this._loadState();
        state[key] = collapsed;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      } catch (e) {
        /* storage may be unavailable */
      }
    }
  };
});
