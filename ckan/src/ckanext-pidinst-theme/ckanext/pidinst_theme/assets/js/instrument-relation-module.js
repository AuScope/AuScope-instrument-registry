/**
 * instrument-relation-module.js
 *
 * CKAN JS module for related_identifier_obj composite rows.
 *
 * When resource_type == "Instrument":
 *   - Disables identifier/type/name fields, shows Select2 instrument search.
 *   - Auto-fills DOI (preferred) or CKAN URL, title, and package id.
 *   - Restricts relation to HasPart/IsPartOf, syncs role field.
 *   - Prepopulates from related_instrument_package_id on edit.
 *
 * When non-Instrument:
 *   - Re-enables fields, restores any saved manual values, hides search.
 */
ckan.module('instrument-relation-module', function ($, _) {
  'use strict';

  /* ── DOM helpers ──────────────────────────────────── */

  function rowOf(el) {
    return $(el).closest('.composite-control-repeating');
  }

  /** Find input/select whose NAME ends with "-<subfieldName>", excluding hidden mirrors. */
  function fieldIn($row, subfieldName) {
    return $row.find(
      'input[name$="-' + subfieldName + '"]:not([data-mirror-for]),' +
      'select[name$="-' + subfieldName + '"]'
    ).first();
  }

  /** "related_identifier_obj-3-related_resource_type" → "related_identifier_obj-3" */
  function rowPrefix(name) {
    var match = (name || '').match(/^(.+-\d+)-/);
    return match ? match[1] : name;
  }

  /* ── Module ──────────────────────────────────────── */

  return {

    initialize: function () {
      var self = this;
      this.$root = this.el;

      this._processAllRows(true);

      this.$root.on('change', 'select[name$="-related_resource_type"]', function () {
        self._processRow(rowOf(this));
      });

      this.$root.on('change', 'select[name$="-relation_type"]', function () {
        var $row = rowOf(this);
        self._updateSearchLabel($row);
        self._syncRole($row);
      });

      // Re-process after "Add another" inserts a new row.
      // We capture the row count BEFORE the click so we can identify
      // the newly cloned row(s) reliably, regardless of whether the
      // composite plugin preserved jQuery .data() on the clone.
      $(document).on(
        'click',
        '#composite-repeating-div-related_identifier_obj .composite-btn.btn-success',
        function () {
          var countBefore = self.$root.find('.composite-control-repeating').length;
          setTimeout(function () {
            self.$root.find('.composite-control-repeating').each(function (i) {
              var $row = $(this);
              if (i >= countBefore) {
                // Newly cloned row — always reset, then process fresh
                self._resetClonedRow($row);
                self._processRow($row);
              }
            });
          }, 250);
        }
      );
    },

    /* ── row processing ────────────────────────────── */

    _processAllRows: function (isInitial) {
      var self = this;
      this.$root.find('.composite-control-repeating').each(function () {
        self._processRow($(this));
      });
    },

    /**
     * Strip stale state from a row cloned by "Add another".
     * The composite-repeating module duplicates the DOM (including our
     * hidden mirrors, search container, and field values) but jQuery
     * .data() is NOT cloned, so we detect new rows by the missing flag.
     */
    _resetClonedRow: function ($row) {
      // Remove stale hidden mirrors cloned from the source row
      $row.find('input[data-mirror-for]').remove();

      // Remove stale search container
      this._destroySearchContainer($row);

      // Clear any saved-state flag
      $row.removeData('pidinst-saved');

      // Re-enable and clear all instrument-related fields
      var self = this;
      ['related_identifier', 'related_identifier_type', 'related_identifier_name',
       'related_instrument_package_id', 'instrument_relation_role'].forEach(function (sf) {
        var $f = fieldIn($row, sf);
        if ($f.length) {
          $f.prop('disabled', false).removeClass('pidinst-disabled').val('');
        }
      });

      // Reset type selects so the user starts with a clean row
      fieldIn($row, 'related_resource_type').val('');
      fieldIn($row, 'relation_type').val('');
    },

    _processRow: function ($row) {
      if ($row.attr('data-row-readonly') === 'true') return;
      var isInstrument = (fieldIn($row, 'related_resource_type').val() === 'Instrument');
      if (isInstrument) {
        this._enableInstrumentMode($row);
      } else {
        this._disableInstrumentMode($row);
      }
    },

    /* ── Instrument mode ON ───────────────────────────────────── */

    _enableInstrumentMode: function ($row) {
      var self = this;
      var $id   = fieldIn($row, 'related_identifier');
      var $type = fieldIn($row, 'related_identifier_type');
      var $name = fieldIn($row, 'related_identifier_name');

      // Save manual values before disabling so we can restore on toggle-back
      if (!$row.data('pidinst-saved')) {
        $row.data('pidinst-saved', {
          identifier: $id.val(),
          type:       $type.val(),
          name:       $name.val()
        });
      }

      // Disable identifier fields + create hidden mirrors for form submission
      [$id, $type, $name].forEach(function ($f) {
        $f.prop('disabled', true).addClass('pidinst-disabled');
        self._ensureHiddenMirror($f);
      });

      this._rebuildSearchContainer($row);

      // Init Select2 if not done yet
      var $searchInput = $row.find('.pidinst-instrument-search-input');
      if ($searchInput.length && !$searchInput.data('select2')) {
        this._initSelect2($searchInput, $row);
      }

      this._prepopulate($row);
      this._updateSearchLabel($row);
      this._syncRole($row);
    },

    /* ── Instrument mode OFF ───────────────────────── */

    _disableInstrumentMode: function ($row) {
      var self = this;
      var $id   = fieldIn($row, 'related_identifier');
      var $type = fieldIn($row, 'related_identifier_type');
      var $name = fieldIn($row, 'related_identifier_name');

      var saved = $row.data('pidinst-saved');
      if (saved) {
        $id.val(saved.identifier || '');
        $type.val(saved.type || '');
        $name.val(saved.name || '');
        $row.removeData('pidinst-saved');
      }

      [$id, $type, $name].forEach(function ($f) {
        $f.prop('disabled', false).removeClass('pidinst-disabled');
        self._removeHiddenMirror($f);
      });

      this._destroySearchContainer($row);

      // Clear hidden instrument fields
      var $pkgId = fieldIn($row, 'related_instrument_package_id');
      var $role  = fieldIn($row, 'instrument_relation_role');
      if ($pkgId.length) $pkgId.val('');
      if ($role.length)  $role.val('');
    },

    /* ── search container lifecycle ───────────────── */

    _rebuildSearchContainer: function ($row) {
      var $existing = $row.find('.pidinst-instrument-search');
      if ($existing.length) {
        var $s2 = $existing.find('.pidinst-instrument-search-input');
        if ($s2.data('select2')) {
          try { $s2.select2('destroy'); } catch (e) { /* ignore */ }
        }
        if ($existing.find('.select2-container').length) {
          $existing.remove();
          this._createSearchContainer($row);
          return;
        }
        $existing.show();
        return;
      }
      this._createSearchContainer($row);
    },

    _createSearchContainer: function ($row) {
      var prefix = rowPrefix(
        (fieldIn($row, 'related_resource_type').attr('name') || '')
      );

      var html =
        '<div class="pidinst-instrument-search form-group">' +
          '<label class="pidinst-instrument-search-label control-label">' +
            'Select related instrument' +
          '</label>' +
          '<input class="pidinst-instrument-search-input form-control" ' +
                 'type="text" data-row-prefix="' + prefix + '" style="width:100%" />' +
          '<p class="pidinst-instrument-search-help help-block">' +
            'Search for an instrument record by title. ' +
            'Identifier fields will be auto-filled.' +
          '</p>' +
        '</div>';

      // Insert after the types row (resource_type + relation_type)
      var $typesRow = $row.find('.pidinst-row-types');
      if ($typesRow.length) {
        $typesRow.after(html);
      } else {
        var $relGroup = fieldIn($row, 'relation_type').closest('.control-group, .form-group');
        if ($relGroup.length) { $relGroup.after(html); }
        else { $row.append(html); }
      }
    },

    _destroySearchContainer: function ($row) {
      var $c = $row.find('.pidinst-instrument-search');
      if (!$c.length) return;
      var $s2 = $c.find('.pidinst-instrument-search-input');
      if ($s2.data('select2')) {
        try { $s2.select2('destroy'); } catch (e) { /* ignore */ }
      }
      $c.remove();
    },

    /* ── Select2 search ───────────────────────────── */

    _initSelect2: function ($input, $row) {
      var self = this;

      $input.select2({
        placeholder: 'Search instrument in registry\u2026',
        minimumInputLength: 1,
        allowClear: true,
        ajax: {
          url: '/api/3/action/package_search',
          dataType: 'json',
          quietMillis: 400,
          // Escape Solr special chars so identifiers like "10.83627" don't cause parse errors
          data: function (term) {
            var safe = (term || '').replace(/([+\-&|!(){}[\]^"~*?:\\/])/g, '\\$1');
            return { q: safe, rows: 20 };
          },
          results: function (data) {
            if (!data.success) return { results: [] };
            var currentName = '';
            try { currentName = $input.closest('form').find('input[name="name"]').val() || ''; }
            catch (e) { /* ignore */ }

            return {
              results: (data.result.results || [])
                .filter(function (p) { return p.name !== currentName && p.id !== currentName; })
                .map(function (p) {
                  var doi = (p.doi || '').trim();
                  var label = p.title || p.name;
                  if (doi) label += '  (DOI: ' + doi + ')';
                  return { id: p.id, text: label, doi: doi,
                           title: p.title || p.name, name: p.name };
                })
            };
          },
          cache: true
        },
        formatResult:    function (item) { return item.text; },
        formatSelection: function (item) { return item.text; },
        dropdownCssClass: 'bigdrop',
        escapeMarkup: function (m) { return m; }
      });

      $input.on('select2-selected', function (e) { self._fillFromSelection($row, e.choice); });
      $input.on('select2-removed',  function ()  { self._clearInstrumentFields($row); });
    },

    /* ── fill / clear ────────────────────────────────────────── */

    _fillFromSelection: function ($row, pkg) {
      var self = this;
      var $id   = fieldIn($row, 'related_identifier');
      var $type = fieldIn($row, 'related_identifier_type');
      var $name = fieldIn($row, 'related_identifier_name');
      var $pkgId = fieldIn($row, 'related_instrument_package_id');

      // DOI preferred; fallback to CKAN URL. UUID stored in package_id for prepop.
      var doi = (pkg.doi || '').trim();
      var idVal, typeVal;
      if (doi) {
        idVal   = doi.indexOf('http') === 0 ? doi : 'https://doi.org/' + doi;
        typeVal = 'DOI';
      } else {
        idVal   = window.location.origin + '/dataset/' + (pkg.name || pkg.id);
        typeVal = 'URL';
      }

      $id.val(idVal);       self._syncHiddenMirror($id,   idVal);
      $type.val(typeVal);   self._syncHiddenMirror($type, typeVal);
      $name.val(pkg.title || ''); self._syncHiddenMirror($name, pkg.title || '');
      if ($pkgId.length) $pkgId.val(pkg.id);

      this._syncRole($row);
    },

    _clearInstrumentFields: function ($row) {
      var self = this;
      ['related_identifier','related_identifier_type','related_identifier_name',
       'related_instrument_package_id','instrument_relation_role'].forEach(function (sf) {
        var $f = fieldIn($row, sf);
        if ($f.length) { $f.val(''); self._syncHiddenMirror($f, ''); }
      });
    },

    /* ── prepopulation on edit ────────────────────────────────── */

    _prepopulate: function ($row) {
      var pkgId = (fieldIn($row, 'related_instrument_package_id').val() || '').trim();
      if (!pkgId) return;

      var $si = $row.find('.pidinst-instrument-search-input');
      if (!$si.length || !$si.data('select2')) return;

      var cur = $si.select2('data');
      if (cur && cur.id === pkgId) return;

      $.ajax({
        url: '/api/3/action/package_show',
        data: { id: pkgId },
        method: 'GET',
        dataType: 'json',
        success: function (resp) {
          if (!resp.success || !resp.result) return;
          var p = resp.result;
          var doi = (p.doi || '').trim();
          var label = p.title || p.name;
          if (doi) label += '  (DOI: ' + doi + ')';
          $si.select2('data', {
            id: p.id, text: label, doi: doi,
            title: p.title || p.name, name: p.name
          }, false);
        }
      });
    },

    /* ── search label / help ─────────────────────────────────── */

    _updateSearchLabel: function ($row) {
      var $c = $row.find('.pidinst-instrument-search');
      if (!$c.length) return;
      var rt = (fieldIn($row, 'relation_type').val() || '').trim();
      $c.find('.pidinst-instrument-search-label').text(
        rt === 'HasPart'  ? 'Select child instrument (part)'   :
        rt === 'IsPartOf' ? 'Select parent instrument (whole)' :
                            'Select related instrument'
      );
      $c.find('.pidinst-instrument-search-help').text(
        rt === 'HasPart'  ? 'The selected instrument will be recorded as a component of this instrument.' :
        rt === 'IsPartOf' ? 'This instrument is a component of the selected (parent) instrument.' :
                            'Search for an instrument record by title.'
      );
    },

    _syncRole: function ($row) {
      var $r = fieldIn($row, 'instrument_relation_role');
      if (!$r.length) return;
      var rt = (fieldIn($row, 'relation_type').val() || '').trim();
      $r.val(rt === 'HasPart' ? 'child' : rt === 'IsPartOf' ? 'parent' : '');
    },

    /* ── hidden mirror helpers ───────────────────────────────── */

    _ensureHiddenMirror: function ($f) {
      var name = $f.attr('name');
      if (!name) return;
      var $p = $f.closest('.control-group, .form-group');
      if (!$p.find('input[data-mirror-for="' + name + '"]').length) {
        $p.append(
          '<input type="hidden" name="' + name + '" data-mirror-for="' + name + '" value="' + ($f.val() || '') + '">'
        );
      }
    },

    _syncHiddenMirror: function ($f, value) {
      var name = $f.attr('name');
      if (!name) return;
      $f.closest('.control-group, .form-group')
        .find('input[data-mirror-for="' + name + '"]').val(value);
    },

    _removeHiddenMirror: function ($f) {
      var name = $f.attr('name');
      if (!name) return;
      $f.closest('.control-group, .form-group')
        .find('input[data-mirror-for="' + name + '"]').remove();
    }

  };
});
