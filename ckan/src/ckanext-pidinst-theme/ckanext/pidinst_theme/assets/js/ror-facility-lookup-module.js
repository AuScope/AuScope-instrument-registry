/**
 * ror-facility-lookup-module.js
 *
 * CKAN module that orchestrates the Facility group create/edit form.
 *
 * Attached to the .ror-facility-lookup-block wrapper (the
 * facility_identifier_ror field).  On initialisation it:
 *
 *   1.  Watches #field-facility_identifier_type (the <select>).
 *   2.  When type == "ROR":
 *       - Shows the ROR search (this block) + ROR-specific readonly fields
 *       - Hides free-text facility_identifier + parent_facility
 *       - Initialises Select2 for /api/proxy/ror_search
 *       - On ROR selection: fills title, name, hierarchy, country, facility_state …
 *       - On form submit: calls /api/facility/ensure_ror_parents first
 *   3.  When type != "ROR":
 *       - Shows free-text facility_identifier, parent_facility
 *       - Hides this block + ROR-specific readonly fields
 *       - Syncs facility_identifier → title + name on input
 */
this.ckan.module('ror-facility-lookup-module', function ($, _) {
  'use strict';

  /* ── helpers ────────────────────────────────────────────────────── */

  function _esc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
  }

  function _nameToSlug(name) {
    var slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    if (slug.length < 2) slug += '-facility';
    return slug.substring(0, 100);
  }

  /* ── ROR-specific fields that should only be visible in ROR mode ── */
  var ROR_FIELDS = [
    'ror_hierarchy_display', 'ror_types', 'ror_country'
  ];

  return {
    /* ── initialise ───────────────────────────────────────────────── */
    initialize: function () {
      var self      = this;
      var $block    = self.el;                               // .ror-facility-lookup-block
      var $input    = $block.find('.ror-facility-search');
      var $preview  = $block.find('.ror-hierarchy-preview');
      var $hierText = $block.find('.ror-hierarchy-text');

      // Cache important elements
      self.$block      = $block;
      self.$input      = $input;
      self.$preview    = $preview;
      self.$hierText   = $hierText;
      self.$typeSelect = $('#field-facility_identifier_type');
      self.$freeIdGrp  = $('#field-facility_identifier').closest('.form-group');
      self.$parentGrp  = $('#field-parent_facility').closest('.form-group');

      // Collect ROR-only field form-groups
      self.$rorFieldGrps = $();
      for (var i = 0; i < ROR_FIELDS.length; i++) {
        self.$rorFieldGrps = self.$rorFieldGrps.add(
          $('#field-' + ROR_FIELDS[i]).closest('.form-group')
        );
      }

      // Bind type-change handler
      self.$typeSelect.on('change', function () { self._onTypeChange(); });

      // Bind facility_identifier (free text) → title / name sync
      $('#field-facility_identifier').on('input', function () {
        var v = $(this).val();
        self._setField('title', v);
        self._setField('name', _nameToSlug(v || ''));
      });

      // Initialise Select2 on the ROR search input
      self._initSelect2();

      // Set initial visibility based on current type
      self._onTypeChange();

      // Intercept form submit for ROR parent creation
      self.$block.closest('form').on('submit', function (e) {
        return self._onFormSubmit(e);
      });
    },

    /* ── visibility toggle ────────────────────────────────────────── */
    _onTypeChange: function () {
      var isRor = this.$typeSelect.val() === 'ROR';

      // Toggle this block (ROR search) vs free-text identifier
      this.$block.toggle(isRor);
      this.$freeIdGrp.toggle(!isRor);

      // Toggle ROR-only readonly fields
      this.$rorFieldGrps.toggle(isRor);

      // Hide parent_facility for ROR (auto-handled on submit)
      this.$parentGrp.toggle(!isRor);

      // If switching to non-ROR, sync free-text → title/name immediately
      if (!isRor) {
        var v = $('#field-facility_identifier').val() || '';
        if (v) {
          this._setField('title', v);
          this._setField('name', _nameToSlug(v));
        }
      }
    },

    /* ── Select2 for ROR search ───────────────────────────────────── */
    _initSelect2: function () {
      var self = this;
      var $input = self.$input;
      if (!$input.length) return;

      var debounce;

      $input.select2({
        placeholder: 'Start typing to search ROR (e.g. CSIRO, Curtin University)\u2026',
        minimumInputLength: 2,
        allowClear: true,
        multiple: false,
        query: function (q) {
          clearTimeout(debounce);
          debounce = setTimeout(function () {
            $.ajax({
              url: '/api/proxy/ror_search',
              dataType: 'json',
              data: { q: q.term },
              success: function (r) { q.callback({ results: r.results || [] }); },
              error:   function ()  { q.callback({ results: [] }); }
            });
          }, 300);
        },
        formatResult: function (item) {
          var h = '<div class="ror-result">';
          h += '<strong>' + _esc(item.name) + '</strong>';
          if (item.types) h += ' <small class="text-muted">(' + _esc(item.types) + ')</small>';
          if (item.facility_state || item.country) {
            var loc = item.facility_state ? item.facility_state + ', ' + item.country : item.country;
            h += '<br><small class="text-muted"><i class="fa fa-map-marker"></i> ' + _esc(loc) + '</small>';
          }
          if (item.hierarchy_display && item.hierarchy_display !== item.name) {
            h += '<br><small class="text-muted"><i class="fa fa-sitemap"></i> ' + _esc(item.hierarchy_display) + '</small>';
          }
          h += '</div>';
          return h;
        },
        formatSelection: function (item) {
          return _esc(item.name || item.text || '');
        },
        escapeMarkup: function (m) { return m; }
      })
      .on('change', function (e) {
        if (e.added) {
          var d = e.added;
          self._setField('title',                 d.name || '');
          self._setField('name',                  _nameToSlug(d.name || ''));
          self._setField('ror_hierarchy_display',  d.hierarchy_display || '');
          self._setField('ror_parents_json',       d.parents_json || '[]');
          self._setField('ror_types',              d.types || '');
          self._setField('ror_country',            d.country || '');
          self._setField('facility_state',                  d.facility_state || '');
          self._setField('website',                d.website || '');

          // Derive immediate parent slug from parents_json
          try {
            var parents = JSON.parse(d.parents_json || '[]');
            if (parents.length) {
              var immParent = parents[parents.length - 1];
              self._setField('parent_facility', _nameToSlug(immParent.name || ''));
            } else {
              self._setField('parent_facility', '');
            }
          } catch (_) {
            self._setField('parent_facility', '');
          }

          // Show hierarchy preview
          var hier = d.hierarchy_display || d.name || '';
          if (hier) {
            self.$hierText.text(hier);
            self.$preview.show();
          }
        } else if (!$input.select2('val')) {
          // Cleared – reset all fields
          var fields = ['title','name','ror_hierarchy_display','ror_parents_json',
                        'ror_types','ror_country','facility_state','website','parent_facility'];
          for (var i = 0; i < fields.length; i++) {
            self._setField(fields[i], '');
          }
          self.$preview.hide();
          self.$hierText.text('');
        }
      });

      // Restore value on edit forms
      var currentRorId   = self.$block.data('current-ror-id');
      var currentDisplay = self.$block.data('current-display-name');
      if (currentRorId && currentDisplay) {
        try {
          $input.select2('data', {
            id: currentRorId, text: currentDisplay, name: currentDisplay
          });
        } catch (_) { /* ignore */ }
      }
    },

    /* ── form submit interceptor ──────────────────────────────────── */
    _onFormSubmit: function (e) {
      var self = this;
      if (self.$typeSelect.val() !== 'ROR') return true; // allow normal submit
      if (self._parentsEnsured) return true;             // already done

      var parentsJson = $('#field-ror_parents_json').val() || '[]';
      var parents;
      try { parents = JSON.parse(parentsJson); } catch (_) { parents = []; }
      if (!parents.length) return true;                  // no parents → skip

      // Prevent default submit, ensure parents via API, then re-submit
      e.preventDefault();
      var $form = self.$block.closest('form');
      var $btn  = $form.find('[type="submit"]').prop('disabled', true);

      $.ajax({
        url: '/api/facility/ensure_ror_parents',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ parents_json: parentsJson }),
        dataType: 'json'
      })
      .always(function () {
        self._parentsEnsured = true;

        // The parent_facility field is a <select> whose options were rendered
        // at page load.  The parent we just created doesn't exist as an
        // <option>, so setting the select's value would silently fail.
        // Fix: disable the <select> (so it won't submit) and inject a hidden
        // <input> with the correct parent slug.
        if (parents.length) {
          var immParent = parents[parents.length - 1];
          var parentSlug = _nameToSlug(immParent.name || '');
          if (parentSlug) {
            var $parentSel = $form.find('select[name="parent_facility"]');
            $parentSel.prop('disabled', true);
            $form.append(
              '<input type="hidden" name="parent_facility" value="' + parentSlug + '">'
            );
          }
        }

        $btn.prop('disabled', false);
        $form.submit();
      });

      return false;
    },

    /* ── utility ──────────────────────────────────────────────────── */
    _setField: function (fieldName, value) {
      var $f = $('#field-' + fieldName);
      if ($f.length) $f.val(value);
    }
  };
});
