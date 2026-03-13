/**
 * Unified vocabulary picker module.
 *
 * Two searchable Select2 dropdowns (GCMD + Custom taxonomy) with Add (+)
 * buttons.  Added items appear as a list with Remove (–) buttons.
 *
 * Supports two storage modes:
 *   mode="composite"  – writes composite-repeating hidden inputs
 *                        (name / identifier / identifier_type per row)
 *   mode="split"      – writes to three separate hidden fields
 *                        (gcmd codes, gcmd labels, custom labels)
 *
 * Data-attributes are set by the Jinja template.
 */
this.ckan.module('vocab-picker-module', function ($, _) {
  'use strict';

  return {
    options: {
      mode: 'composite',            // 'composite' | 'split'
      gcmdScheme: '',
      gcmdSchemePlatform: '',
      customTaxonomy: '',
      customTaxonomyPlatform: '',
      fieldName: '',                  // composite parent field name
      nameSubfield: '',               // e.g. instrument_type_name
      identifierSubfield: '',         // e.g. instrument_type_identifier
      identifierTypeSubfield: '',     // e.g. instrument_type_identifier_type
      gcmdCodeField: '',              // for split mode: hidden field name for GCMD URIs
      gcmdLabelField: '',             // for split mode: hidden field name for GCMD labels
      customField: '',                // for split mode: hidden field name for custom terms
      gcmdLabelInstrument: '',
      gcmdLabelPlatform: '',
      customLabelInstrument: '',
      customLabelPlatform: ''
    },

    initialize: function () {
      var self = this;

      // Detect instrument vs platform context
      this.isPlatform = ($('#field-is_platform').val() === 'true');
      this.gcmdScheme = this.isPlatform
        ? (this.options.gcmdSchemePlatform || this.options.gcmdScheme)
        : this.options.gcmdScheme;
      this.customTaxonomy = this.isPlatform
        ? (this.options.customTaxonomyPlatform || this.options.customTaxonomy)
        : this.options.customTaxonomy;

      this.entries = [];       // {name, identifier, identifierType, source, uid}
      this._uid = 0;

      // Cache DOM handles
      this.gcmdSelect       = this.el.find('.vocab-picker-gcmd-select');
      this.customSelect     = this.el.find('.vocab-picker-custom-select');
      this.listContainer    = this.el.find('.vocab-picker-list');
      this.hiddenContainer  = this.el.find('.vocab-picker-hidden-inputs');

      this._updateLabels();
      this._initGcmdSelect2();
      this._initCustomSelect2();
      this._bindAddButtons();
      this._prepopulate();
    },

    /* ── Label switching (instrument ↔ platform) ────────────────────── */
    _updateLabels: function () {
      var gcmdLabel = this.isPlatform
        ? this.options.gcmdLabelPlatform
        : this.options.gcmdLabelInstrument;
      var customLabel = this.isPlatform
        ? this.options.customLabelPlatform
        : this.options.customLabelInstrument;
      if (gcmdLabel)   this.el.find('.vocab-picker-gcmd-label-text').text(gcmdLabel);
      if (customLabel) this.el.find('.vocab-picker-custom-label-text').text(customLabel);
    },

    /* ── GCMD Select2 ───────────────────────────────────────────────── */
    _initGcmdSelect2: function () {
      var self = this;
      var nextPage = 0;
      var lastTerm = null;

      this.gcmdSelect.select2({
        placeholder: 'Search GCMD keywords…',
        minimumInputLength: 3,
        multiple: false,
        allowClear: true,
        query: function (query) {
          if (lastTerm !== query.term) { nextPage = 0; lastTerm = query.term; }
          $.ajax({
            url: '/api/proxy/fetch_gcmd',
            data: { page: nextPage, keywords: query.term, scheme: self.gcmdScheme },
            dataType: 'json',
            success: function (resp) {
              var items = (resp.result.items || []).map(function (item) {
                return { id: item._about, text: item.prefLabel._value };
              });
              nextPage = resp.result.page + 1;
              query.callback({ results: items, more: !!resp.result.next });
            },
            error: function () { query.callback({ results: [] }); }
          });
        }
      });
    },

    /* ── Custom taxonomy Select2 ────────────────────────────────────── */
    _initCustomSelect2: function () {
      var self = this;

      this.customSelect.select2({
        placeholder: 'Search custom terms…',
        minimumInputLength: 0,
        multiple: false,
        allowClear: true,
        query: function (query) {
          $.ajax({
            url: '/api/proxy/taxonomy_terms/' + encodeURIComponent(self.customTaxonomy),
            data: { q: query.term || '' },
            dataType: 'json',
            success: function (resp) {
              query.callback({ results: resp.results || [] });
            },
            error: function () { query.callback({ results: [] }); }
          });
        }
      });
    },

    /* ── Add buttons ────────────────────────────────────────────────── */
    _bindAddButtons: function () {
      var self = this;

      this.el.find('.vocab-picker-gcmd-add').on('click', function () {
        var d = self.gcmdSelect.select2('data');
        if (!d) return;
        self._addEntry(d.text, d.id, 'URI', 'gcmd');
        self.gcmdSelect.select2('val', '');
      });

      this.el.find('.vocab-picker-custom-add').on('click', function () {
        var d = self.customSelect.select2('data');
        if (!d) return;
        self._addEntry(d.text, d.id || '', d.id ? 'URI' : '', 'custom');
        self.customSelect.select2('val', '');
      });
    },

    /* ── Core entry management ──────────────────────────────────────── */
    _addEntry: function (name, identifier, identifierType, source) {
      if (!name) return;
      // Prevent duplicates by name
      var exists = this.entries.some(function (e) {
        return e.name.toLowerCase() === name.toLowerCase();
      });
      if (exists) return;

      this.entries.push({
        name: name,
        identifier: identifier || '',
        identifierType: identifierType || '',
        source: source || 'custom',
        uid: ++this._uid
      });
      this._renderList();
      this._syncHidden();
    },

    _removeEntry: function (uid) {
      this.entries = this.entries.filter(function (e) { return e.uid !== uid; });
      this._renderList();
      this._syncHidden();
    },

    /* ── Render visible list ────────────────────────────────────────── */
    _renderList: function () {
      var self = this;
      this.listContainer.empty();

      if (this.entries.length === 0) {
        this.listContainer.append('<li class="vocab-picker-empty">No types added yet.</li>');
        return;
      }

      this.entries.forEach(function (entry) {
        var $li = $(
          '<li class="vocab-picker-item">' +
            '<span class="vocab-picker-item-label"></span>' +
            '<span class="badge vocab-picker-badge-' + entry.source + '">' +
              entry.source.toUpperCase() +
            '</span>' +
            '<button type="button" class="btn btn-danger btn-sm vocab-picker-remove">' +
              '<i class="fa fa-minus"></i>' +
            '</button>' +
          '</li>'
        );
        // Use .text() to safely set the label (XSS-safe)
        $li.find('.vocab-picker-item-label').text(entry.name);
        $li.find('.vocab-picker-remove').data('uid', entry.uid);
        self.listContainer.append($li);
      });

      this.listContainer.find('.vocab-picker-remove').on('click', function () {
        self._removeEntry($(this).data('uid'));
      });
    },

    /* ── Sync hidden inputs for form submission ─────────────────────── */
    _syncHidden: function () {
      this.hiddenContainer.empty();

      if (this.options.mode === 'composite') {
        this._syncComposite();
      } else {
        this._syncSplit();
      }
    },

    _syncComposite: function () {
      var self = this;
      var fn = this.options.fieldName;
      var nameSub = this.options.nameSubfield;
      var idSub   = this.options.identifierSubfield;
      var idtSub  = this.options.identifierTypeSubfield;

      if (this.entries.length === 0) {
        // Ensure at least one blank row so the validator doesn't complain
        // about a completely missing field (optional fields should be fine).
        return;
      }

      this.entries.forEach(function (entry, idx) {
        var i = idx + 1;
        var prefix = fn + '-' + i + '-';
        self.hiddenContainer.append(
          $('<input>').attr({ type: 'hidden', name: prefix + nameSub, value: entry.name }),
          $('<input>').attr({ type: 'hidden', name: prefix + idSub,  value: entry.identifier }),
          $('<input>').attr({ type: 'hidden', name: prefix + idtSub, value: entry.identifierType })
        );
      });

      // Also clear legacy GCMD hidden fields if present
      var gcmdCodeField  = this.options.gcmdCodeField;
      var gcmdLabelField = this.options.gcmdLabelField;
      if (gcmdCodeField)  $('input[name="' + gcmdCodeField + '"]').val('');
      if (gcmdLabelField) $('input[name="' + gcmdLabelField + '"]').val('');
    },

    _syncSplit: function () {
      var gcmdCodes = [], gcmdLabels = [], customLabels = [];

      this.entries.forEach(function (entry) {
        if (entry.source === 'gcmd') {
          gcmdCodes.push(entry.identifier);
          gcmdLabels.push(entry.name);
        } else {
          customLabels.push(entry.name);
        }
      });

      var gcmcCodeName  = this.options.gcmdCodeField;
      var gcmdLabelName = this.options.gcmdLabelField;
      var customName    = this.options.customField;

      this.hiddenContainer.append(
        $('<input>').attr({ type: 'hidden', name: gcmcCodeName,  value: gcmdCodes.join(',') }),
        $('<input>').attr({ type: 'hidden', name: gcmdLabelName, value: JSON.stringify(gcmdLabels) }),
        $('<input>').attr({ type: 'hidden', name: customName,    value: JSON.stringify(customLabels) })
      );
    },

    /* ── Prepopulation ──────────────────────────────────────────────── */
    _prepopulate: function () {
      if (this.options.mode === 'composite') {
        this._prepopulateComposite();
      } else {
        this._prepopulateSplit();
      }
      this._renderList();
      this._syncHidden();
    },

    _prepopulateComposite: function () {
      var self = this;

      // 1) Read existing composite data
      var compositeEl = this.el.find('.vocab-picker-existing-composite');
      if (compositeEl.length) {
        try {
          var list = JSON.parse(compositeEl.text());
          for (var i = 0; i < list.length; i++) {
            var e = list[i];
            if (!e || !e.name) continue;
            var source = self._guessSource(e.identifier);
            self.entries.push({
              name: e.name,
              identifier: e.identifier || '',
              identifierType: e.identifierType || '',
              source: source,
              uid: ++self._uid
            });
          }
        } catch (ex) { /* ignore parse errors */ }
      }

      // 2) Merge legacy GCMD data (from old gcmd_code / gcmd_label fields)
      var gcmdEl = this.el.find('.vocab-picker-existing-gcmd');
      if (gcmdEl.length) {
        try {
          var legacy = JSON.parse(gcmdEl.text());
          var codes = (legacy.codes || '');
          var labels = (legacy.labels || '');
          // codes is comma-separated URIs, labels is JSON array of strings
          var codeArr = codes ? codes.split(',') : [];
          var labelArr = [];
          if (labels) {
            try { labelArr = JSON.parse(labels); } catch (e2) { /* noop */ }
          }
          for (var j = 0; j < codeArr.length && j < labelArr.length; j++) {
            if (!codeArr[j] || !labelArr[j]) continue;
            // Avoid duplicates already loaded from composite
            var exists = self.entries.some(function (ent) {
              return ent.name.toLowerCase() === labelArr[j].toLowerCase();
            });
            if (!exists) {
              self.entries.push({
                name: labelArr[j],
                identifier: codeArr[j],
                identifierType: 'URI',
                source: 'gcmd',
                uid: ++self._uid
              });
            }
          }
        } catch (ex) { /* ignore */ }
      }
    },

    _prepopulateSplit: function () {
      var self = this;

      // GCMD entries from hidden fields rendered before this widget
      var gcmdCodeVal  = $('input[name="' + this.options.gcmdCodeField + '"]').val() || '';
      var gcmdLabelVal = $('input[name="' + this.options.gcmdLabelField + '"]').val() || '';

      var codes = gcmdCodeVal ? gcmdCodeVal.split(',') : [];
      var labels = [];
      if (gcmdLabelVal) {
        try { labels = JSON.parse(gcmdLabelVal); } catch (e) { labels = []; }
      }
      for (var i = 0; i < codes.length && i < labels.length; i++) {
        if (codes[i] && labels[i]) {
          self.entries.push({
            name: labels[i],
            identifier: codes[i],
            identifierType: 'URI',
            source: 'gcmd',
            uid: ++self._uid
          });
        }
      }

      // Custom entries from hidden field
      var customVal = $('input[name="' + this.options.customField + '"]').val() || '';
      var customTerms = [];
      if (customVal) {
        try { customTerms = JSON.parse(customVal); } catch (e) { customTerms = []; }
      }
      if (typeof customTerms === 'string') {
        customTerms = customTerms.split(',').map(function (t) { return t.trim(); }).filter(Boolean);
      }
      for (var j = 0; j < customTerms.length; j++) {
        if (customTerms[j]) {
          self.entries.push({
            name: customTerms[j],
            identifier: '',
            identifierType: '',
            source: 'custom',
            uid: ++self._uid
          });
        }
      }
    },

    /* ── Utilities ──────────────────────────────────────────────────── */
    _guessSource: function (identifier) {
      if (!identifier) return 'custom';
      if (identifier.indexOf('cmr.earthdata.nasa.gov') > -1 ||
          identifier.indexOf('gcmd.earthdata.nasa.gov') > -1 ||
          identifier.indexOf('vocabs.ardc.edu.au') > -1) {
        return 'gcmd';
      }
      return 'custom';
    }
  };
});
