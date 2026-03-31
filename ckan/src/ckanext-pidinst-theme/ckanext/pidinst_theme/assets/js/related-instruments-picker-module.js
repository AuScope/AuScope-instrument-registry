/**
 * related-instruments-picker-module.js
 *
 * Search + add + list picker for related instruments (components & previous version).
 * Writes hidden inputs consumed by related_instruments_validator on submit.
 */
this.ckan.module('related-instruments-picker-module', function ($, _) {
  'use strict';

  function parseComposite(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    if (typeof value === 'string') {
      try {
        var p = JSON.parse(value);
        return Array.isArray(p) ? p : (p && typeof p === 'object') ? [p] : [];
      } catch (e) { return []; }
    }
    return [];
  }

  function extractMeta(pkg) {
    var models = parseComposite(pkg.model);
    var modelName = (models.length && models[0].model_name) ? models[0].model_name : '';
    var altIds = parseComposite(pkg.alternate_identifier_obj);
    var chosen = null;
    for (var i = 0; i < altIds.length; i++) {
      if (altIds[i].alternate_identifier_type === 'SerialNumber') { chosen = altIds[i]; break; }
    }
    if (!chosen && altIds.length) chosen = altIds[0];
    var sn = chosen ? (chosen.alternate_identifier || '') : '';
    return { modelName: modelName, serialNumber: sn };
  }

  function buildLabel(pkg, meta) {
    var label = pkg.title || pkg.name;
    if (meta.modelName || meta.serialNumber) {
      var parts = [];
      if (meta.modelName) parts.push(meta.modelName);
      if (meta.serialNumber) parts.push(meta.serialNumber);
      label += '  [' + parts.join('-') + ']';
    }
    return label;
  }

  return {
    options: {
      fieldName: 'related_instruments',
      doiResolverUrl: 'https://doi.org',
      siteUrl: ''
    },

    initialize: function () {
      this.entries = [];
      this._uid = 0;
      this.$search = this.el.find('.related-instruments-search-input');
      this.$list = this.el.find('.related-instruments-list');
      this.$hidden = this.el.find('.related-instruments-hidden-inputs');

      this._prepopulate();
      this._enrichPrepopulatedLabels();
      this._initSelect2();
      this._bindAdd();
    },

    _prepopulate: function () {
      var self = this;
      var el = this.el.find('.related-instruments-existing');
      if (!el.length) return;
      try {
        var list = JSON.parse(el.text());
        for (var i = 0; i < list.length; i++) {
          var e = list[i];
          if (!e) continue;
          // Skip child-side reciprocals — only parent-owned rows belong here
          if (e.relation_type === 'IsPartOf') continue;
          var isVersion = (e.relation_type === 'IsNewVersionOf');
          // Allow:
          //  • Version entries (always, identified by URL/DOI and now by package_id too)
          //  • Component entries with a known package_id
          //  • Legacy component entries without package_id but with an identifier
          //    (created before related_instrument_package_id was stored)
          if (!e.package_id && !isVersion && !e.identifier) continue;
          self.entries.push({
            package_id: e.package_id,
            name: e.name || '',
            label: e.label || e.related_identifier_name || e.package_id,
            doi: e.doi || '',
            identifier: e.identifier || '',
            relation_type: e.relation_type || 'HasPart',
            role: isVersion ? 'version' : 'component',
            locked: isVersion,
            uid: ++self._uid
          });
        }
      } catch (ex) { /* ignore */ }
      this._render();
      this._sync();
    },

    _initSelect2: function () {
      var self = this;
      this.$search.select2({
        placeholder: 'Search instrument…',
        minimumInputLength: 0,
        allowClear: true,
        ajax: {
          url: '/api/3/action/package_search',
          dataType: 'json',
          quietMillis: 400,
          data: function (term) {
            var safe = (term || '').replace(/([+\-&|!(){}[\]^"~*?:\\/])/g, '\\$1');
            var query = safe.split(/\s+/).filter(Boolean).map(function (w) { return w + '*'; }).join(' ');
            return { q: query || '*:*', fq: 'type:instrument AND private:false AND state:active', rows: 20 };
          },
          results: function (data) {
            if (!data.success) return { results: [] };
            var currentName = '';
            try { currentName = self.$search.closest('form').find('input[name="name"]').val() || ''; } catch (e) {}
            var selectedIds = self.entries.map(function (e) { return e.package_id; });
            return {
              results: (data.result.results || [])
                .filter(function (p) { return p.name !== currentName && p.id !== currentName && selectedIds.indexOf(p.id) === -1; })
                .map(function (p) {
                  var meta = extractMeta(p);
                  return { id: p.id, text: buildLabel(p, meta), doi: (p.doi || '').trim(), title: p.title || p.name, name: p.name };
                })
            };
          },
          cache: true
        },
        formatResult: function (item) { return item.text; },
        formatSelection: function (item) { return item.text; },
        dropdownCssClass: 'bigdrop',
        escapeMarkup: function (m) { return m; }
      });
    },

    _bindAdd: function () {
      var self = this;
      this.$search.on('change', function (e) {
        var d = self.$search.select2('data');
        if (!d) return;
        self._addComponent(d);
        self.$search.select2('val', '');
      });
    },

    _enrichPrepopulatedLabels: function () {
      var self = this;
      var siteUrl = (this.options.siteUrl || '').replace(/\/+$/, '');
      var instBase = siteUrl + '/instrument/';

      // Resolve a lookup key (package_id or slug from identifier URL) for each entry
      var toEnrich = [];
      this.entries.forEach(function (e) {
        var key = e.package_id;
        if (!key && e.identifier && siteUrl && e.identifier.indexOf(instBase) === 0) {
          key = e.identifier.slice(instBase.length).split('/')[0];
        }
        if (key) toEnrich.push({ entry: e, key: key });
      });
      if (!toEnrich.length) return;

      // Use package_show (accepts UUID or slug, works for private packages) instead
      // of package_search so the lookup is reliable regardless of Solr indexing.
      var pending = toEnrich.length;
      var changed = false;
      toEnrich.forEach(function (item) {
        $.ajax({
          url: '/api/3/action/package_show',
          data: { id: item.key },
          dataType: 'json',
          success: function (data) {
            if (data && data.success) {
              var pkg = data.result;
              var meta = extractMeta(pkg);
              item.entry.label = buildLabel(pkg, meta);
              changed = true;
            }
          },
          complete: function () {
            pending--;
            if (pending === 0 && changed) {
              self._render();
              self._sync();
            }
          }
        });
      });
    },

    _addComponent: function (pkg) {
      var exists = this.entries.some(function (e) { return e.package_id === pkg.id; });
      if (exists) return;
      this.entries.push({
        package_id: pkg.id,
        name: pkg.name || '',
        label: pkg.text || pkg.title || pkg.name || pkg.id,
        doi: pkg.doi || '',
        identifier: '',
        relation_type: 'HasPart',
        role: 'component',
        locked: false,
        uid: ++this._uid
      });
      this._render();
      this._sync();
    },

    _remove: function (uid) {
      this.entries = this.entries.filter(function (e) { return e.uid !== uid; });
      this._render();
      this._sync();
    },

    _render: function () {
      var self = this;
      this.$list.empty();
      if (!this.entries.length) {
        this.$list.append('<li class="related-instruments-empty">No related instruments added.</li>');
        return;
      }
      // Version entries first
      var sorted = this.entries.slice().sort(function (a, b) {
        if (a.role === 'version' && b.role !== 'version') return -1;
        if (a.role !== 'version' && b.role === 'version') return 1;
        return 0;
      });
      sorted.forEach(function (entry) {
        var badgeClass = entry.role === 'version' ? 'related-instruments-badge-version' : 'related-instruments-badge-component';
        var badgeText = entry.role === 'version' ? 'Previous version' : 'Component';
        var $li = $(
          '<li class="related-instruments-item">' +
            '<span class="related-instruments-item-label"></span>' +
            '<span class="related-instruments-badge ' + badgeClass + '">' + badgeText + '</span>' +
            (entry.locked ? '' :
              '<button type="button" class="btn btn-danger btn-sm related-instruments-remove">' +
                '<i class="fa fa-minus"></i>' +
              '</button>') +
          '</li>'
        );
        $li.find('.related-instruments-item-label').text(entry.label);
        if (!entry.locked) {
          $li.find('.related-instruments-remove').data('uid', entry.uid);
        }
        self.$list.append($li);
      });
      this.$list.find('.related-instruments-remove').on('click', function () {
        self._remove($(this).data('uid'));
      });
    },

    _sync: function () {
      var self = this;
      this.$hidden.empty();
      var fn = this.options.fieldName;
      var doiResolver = this.options.doiResolverUrl.replace(/\/+$/, '');
      var siteUrl = (this.options.siteUrl || '').replace(/\/+$/, '');

      var payload = this.entries.map(function (entry) {
        var idVal, idType;
        if (entry.doi) {
          idVal = entry.doi.indexOf('http') === 0 ? entry.doi : doiResolver + '/' + entry.doi;
          idType = 'DOI';
        } else if (entry.identifier) {
          idVal = entry.identifier;
          idType = 'URL';
        } else {
          var slug = entry.name || entry.package_id;
          idVal = siteUrl + '/instrument/' + slug;
          idType = 'URL';
        }
        return {
          package_id: entry.package_id,
          relation_type: entry.relation_type,
          label: entry.label,
          identifier: idVal,
          identifier_type: idType
        };
      });

      self.$hidden.append(
        $('<input>').attr({ type: 'hidden', name: fn, value: JSON.stringify(payload) })
      );
    }
  };
});
