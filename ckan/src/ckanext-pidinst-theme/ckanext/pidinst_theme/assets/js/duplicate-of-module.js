ckan.module('duplicate-of-module', function ($, _) {
  'use strict';

  function buildLabel(pkg) {
    var label = pkg.title || pkg.name;
    var doi = (pkg.doi || '').trim();
    if (doi) label += '  (DOI: ' + doi + ')';
    return label;
  }

  return {
    initialize: function () {
      var self = this;
      var currentPkgId = (this.el.attr('data-current-pkg-id') || '').trim();
      var $hidden = this.el.find('input[name="duplicate_of"]');
      var $search = this.el.find('.pidinst-duplicate-of-search');

      $search.select2({
        placeholder: 'Search datasets\u2026',
        minimumInputLength: 0,
        allowClear: true,
        ajax: {
          url: '/api/3/action/package_search',
          dataType: 'json',
          quietMillis: 400,
          data: function (term) {
            var safe = (term || '').replace(/([+\-&|!(){}[\]^"~*?:\\/])/g, '\\$1');
            var query = safe.length > 0
              ? safe.split(/\s+/).filter(function (w) { return w.length > 0; }).map(function (w) { return w + '*'; }).join(' ')
              : safe;
            return { q: query, rows: 20 };
          },
          results: function (data) {
            if (!data.success) return { results: [] };
            return {
              results: (data.result.results || [])
                .filter(function (p) { return p.id !== currentPkgId && p.name !== currentPkgId; })
                .map(function (p) { return { id: p.id, text: buildLabel(p) }; })
            };
          },
          cache: true
        },
        formatResult:    function (item) { return item.text; },
        formatSelection: function (item) { return item.text; },
        dropdownCssClass: 'bigdrop',
        escapeMarkup: function (m) { return m; }
      });

      $search.on('select2-selected', function (e) { $hidden.val(e.choice.id); });
      $search.on('select2-removed',  function ()  { $hidden.val(''); });

      var prepopId = ($hidden.val() || '').trim();
      if (prepopId) {
        $.ajax({
          url: '/api/3/action/package_show',
          data: { id: prepopId },
          method: 'GET',
          dataType: 'json',
          success: function (resp) {
            if (!resp.success || !resp.result) return;
            var p = resp.result;
            $search.select2('data', { id: p.id, text: buildLabel(p) }, false);
            $hidden.val(p.id);
          }
        });
      }
    }
  };
});
