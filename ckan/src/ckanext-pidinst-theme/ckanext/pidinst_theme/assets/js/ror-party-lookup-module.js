/**
 * ror-party-lookup-module.js
 *
 * CKAN module that orchestrates the party group create/edit form.
 *
 * Attached to the .ror-party-lookup-block wrapper (the
 * party_identifier_ror field).  On initialisation it:
 *
 *   1.  Watches #field-party_identifier_type (the <select>).
 *   2.  When type == "ROR":
 *       - Shows the ROR search (this block) + ROR-specific readonly fields
 *       - Hides free-text party_identifier + parent_party
 *       - Initialises Select2 for /api/proxy/ror_search
 *       - On ROR selection: fills title, name, hierarchy, country, party_state …
 *       - On form submit: calls /api/party/ensure_ror_parents first
 *   3.  When type != "ROR":
 *       - Shows free-text party_identifier, parent_party
 *       - Hides this block + ROR-specific readonly fields
 *       - Syncs party_identifier → title + name on input
 */
this.ckan.module('ror-party-lookup-module', function ($, _) {
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
    if (slug.length < 2) slug += '-party';
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
      var $block    = self.el;                               // .ror-party-lookup-block
      var $input    = $block.find('.ror-party-search');
      var $preview  = $block.find('.ror-hierarchy-preview');
      var $hierText = $block.find('.ror-hierarchy-text');

      // Cache important elements
      self.$block      = $block;
      self.$input      = $input;
      self.$preview    = $preview;
      self.$hierText   = $hierText;
      self.$typeSelect = $('#field-party_identifier_type');
      self.$freeIdGrp  = $('#field-party_identifier').closest('.form-group');
      self.$parentGrp  = $('#field-parent_party').closest('.form-group');
      self.$titleGrp   = $('#field-title').closest('.form-group');

      // Collect ROR-only field form-groups
      self.$rorFieldGrps = $();
      for (var i = 0; i < ROR_FIELDS.length; i++) {
        self.$rorFieldGrps = self.$rorFieldGrps.add(
          $('#field-' + ROR_FIELDS[i]).closest('.form-group')
        );
      }

      // Bind type-change handler
      self.$typeSelect.on('change', function () { self._onTypeChange(); });

      // Bind title (visible for non-ROR) → name slug sync
      $('#field-title').on('input', function () {
        if (self.$typeSelect.val() !== 'ROR') {
          self._setField('name', _nameToSlug($(this).val() || ''));
        }
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

      // Hide parent_party for ROR (auto-handled on submit)
      this.$parentGrp.toggle(!isRor);

      // Title: visible for non-ROR (user enters name), hidden for ROR (auto-populated)
      this.$titleGrp.toggle(!isRor);

      // If switching to non-ROR, sync title → name slug immediately
      if (!isRor) {
        var v = $('#field-title').val() || '';
        if (v) {
          this._setField('name', _nameToSlug(v));
        }
      }
    },

    /* ── Select2 for ROR search ───────────────────────────────────── */
    _isManufacturerRole: function () {
      // Check if the Manufacturer checkbox is ticked in party_role
      var $mfr = $('input[name="party_role"][value="Manufacturer"]');
      return $mfr.length > 0 && $mfr.is(':checked');
    },

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
            var params = { q: q.term };
            if (self._isManufacturerRole()) {
              params.manufacturer = 'true';
            }
            $.ajax({
              url: '/api/proxy/ror_search',
              dataType: 'json',
              data: params,
              success: function (r) { q.callback({ results: r.results || [] }); },
              error:   function ()  { q.callback({ results: [] }); }
            });
          }, 300);
        },
        formatResult: function (item) {
          var h = '<div class="ror-result">';
          h += '<strong>' + _esc(item.name) + '</strong>';
          if (item.types) h += ' <small class="text-muted">(' + _esc(item.types) + ')</small>';
          if (item.party_state || item.country) {
            var loc = item.party_state ? item.party_state + ', ' + item.country : item.country;
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
          self._setField('party_state',                  d.party_state || '');
          self._setField('website',                d.website || '');

          // Derive immediate parent slug from parents_json
          try {
            var parents = JSON.parse(d.parents_json || '[]');
            if (parents.length) {
              var immParent = parents[parents.length - 1];
              self._setField('parent_party', _nameToSlug(immParent.name || ''));
            } else {
              self._setField('parent_party', '');
            }
          } catch (_) {
            self._setField('parent_party', '');
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
                        'ror_types','ror_country','party_state','website','parent_party'];
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
      if (self._parentsEnsured) return true;             // already done

      // Gather the child's selected party_role checkboxes
      var partyRoles = [];
      $('input[name="party_role"]:checked').each(function () {
        partyRoles.push($(this).val());
      });

      // ── Non-ROR path: propagate roles to selected parent ────────
      if (self.$typeSelect.val() !== 'ROR') {
        var parentName = ($('#field-parent_party').val() || '').trim();
        if (!parentName || !partyRoles.length) return true; // no parent or no roles → normal submit

        // Also sync name slug from title for non-ROR
        var titleVal = $('#field-title').val() || '';
        if (titleVal) {
          self._setField('name', _nameToSlug(titleVal));
        }

        e.preventDefault();
        var $form = self.$block.closest('form');
        var $btn  = $form.find('[type="submit"]').prop('disabled', true);

        $.ajax({
          url: '/api/party/sync_parent_roles',
          type: 'POST',
          contentType: 'application/json',
          data: JSON.stringify({ parent_name: parentName, roles: partyRoles }),
          dataType: 'json'
        })
        .always(function () {
          self._parentsEnsured = true;
          $btn.prop('disabled', false);
          $form.submit();
        });

        return false;
      }

      // ── ROR path: ensure parents exist with roles ───────────────

      var parentsJson = $('#field-ror_parents_json').val() || '[]';
      var parents;
      try { parents = JSON.parse(parentsJson); } catch (_) { parents = []; }
      if (!parents.length) return true;                  // no parents → skip

      // Prevent default submit, ensure parents via API, then re-submit
      e.preventDefault();
      var $form = self.$block.closest('form');
      var $btn  = $form.find('[type="submit"]').prop('disabled', true);

      $.ajax({
        url: '/api/party/ensure_ror_parents',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ parents_json: parentsJson, party_role: partyRoles }),
        dataType: 'json'
      })
      .always(function () {
        self._parentsEnsured = true;

        // The parent_party field is a <select> whose options were rendered
        // at page load.  The parent we just created doesn't exist as an
        // <option>, so setting the select's value would silently fail.
        // Fix: disable the <select> (so it won't submit) and inject a hidden
        // <input> with the correct parent slug.
        if (parents.length) {
          var immParent = parents[parents.length - 1];
          var parentSlug = _nameToSlug(immParent.name || '');
          if (parentSlug) {
            var $parentSel = $form.find('select[name="parent_party"]');
            $parentSel.prop('disabled', true);
            $form.append(
              '<input type="hidden" name="parent_party" value="' + parentSlug + '">'
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
