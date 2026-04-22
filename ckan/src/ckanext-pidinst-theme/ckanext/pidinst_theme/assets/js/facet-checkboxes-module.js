/**
 * Facet Checkboxes Module – toggles checkbox facet values in URL params.
 */
this.ckan.module('facet-checkboxes-module', function ($, _) {
  'use strict';

  return {
    initialize: function () {
      var self = this;
      self._param = self.el.data('param');

      self.el.on('change', '.facet-cb', function () {
        self._apply();
      });
    },

    _apply: function () {
      var self = this;
      var params = new URLSearchParams(window.location.search);

      // Rebuild this param from checked boxes
      params.delete(self._param);
      params.delete('page');

      self.el.find('.facet-cb:checked').each(function () {
        params.append(self._param, $(this).data('value'));
      });

      window.location.search = params.toString();
    }
  };
});

/**
 * Facet Filter Search Module – client-side text filter for checkbox facets.
 * Attach to the facet <section>. Expects a .pf-facet-search input and
 * .pf-check-list <ul> elements containing <li> rows with .pf-check-name.
 */
this.ckan.module('facet-filter-search', function ($, _) {
  'use strict';

  return {
    initialize: function () {
      var self = this;
      self.el.on('input', '.pf-facet-search', function () {
        var q = $(this).val().toLowerCase().trim();
        self.el.find('.pf-check-list li').each(function () {
          var label = $(this).find('.pf-check-name').text().toLowerCase();
          $(this).toggle(q === '' || label.indexOf(q) !== -1);
        });
      });
    }
  };
});

/**
 * Date Filters Module – handles the combined Dates facet (From/To inputs).
 * Accepts YYYY, YYYY-MM, or YYYY-MM-DD.
 */
this.ckan.module('date-filters-module', function ($, _) {
  'use strict';

  return {
    initialize: function () {
      var self = this;

      self.el.on('click', '.df-apply', function () {
        self._applyRow($(this));
      });
      self.el.on('keydown', '.df-input', function (e) {
        if (e.key === 'Enter') {
          self._applyRow($(this).closest('.date-filter-row').find('.df-apply'));
        }
      });
    },

    _applyRow: function ($btn) {
      var fromParam = $btn.data('from');
      var toParam = $btn.data('to');
      var $row = $btn.closest('.date-filter-row');
      var inputs = $row.find('.df-input');
      var fromVal = inputs.filter('[data-param="' + fromParam + '"]').val().trim();
      var toVal = inputs.filter('[data-param="' + toParam + '"]').val().trim();

      var params = new URLSearchParams(window.location.search);
      params.delete(fromParam);
      params.delete(toParam);
      params.delete('page');

      if (fromVal) { params.set(fromParam, fromVal); }
      if (toVal) { params.set(toParam, toVal); }

      window.location.search = params.toString();
    }
  };
});
