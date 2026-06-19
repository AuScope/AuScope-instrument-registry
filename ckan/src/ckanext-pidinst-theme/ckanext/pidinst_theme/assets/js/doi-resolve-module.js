/**
 * doi-resolve-module.js
 *
 * Phase 2 — read-only DOI/URL metadata resolution helper.
 *
 * Attached to the "Fetch metadata" button rendered next to the
 * Identifier URL field on the manual/external Instrument/Platform add/edit
 * form (External_Flow only). On click it reads the current identifier_url
 * value, guards against a concurrent request, and POSTs `{identifier}` to the
 * side-effect-free CKAN action `pidinst_resolve_doi_metadata`.
 *
 * The action returns a uniform envelope with a `status` field. This module
 * switches on `status`:
 *   - ok            → open the Resolve_Dialog with both tabs populated.
 *   - invalid_input → keep the dialog closed, show the inline invalid message.
 *   - not_found     → keep the dialog closed, show the inline not-found message.
 *   - fetch_error   → keep the dialog closed, show the inline fetch-error message.
 *   AJAX/transport failure is treated as a fetch error (Requirement 6.7, 13).
 *
 * Applying values only mutates in-memory form inputs; nothing is saved until
 * the registrar submits the form (Requirement 8.8).
 *
 * The pure helpers (`defaultApplyState`, `applyResolvedFields`) are extracted
 * so they can be property/unit tested in isolation (tasks 9.4, 9.5). They are
 * exposed via `module.exports` (CommonJS, for tests) and on a browser global
 * `window.PidinstDoiResolve`.
 *
 * Dialog markup: the form snippet (identifier_url_field.html) includes
 * `scheming/package/snippets/doi_resolve_dialog.html` inside the container div
 * whose id is passed to this module as `data-module-dialog-id`. This module
 * scopes all of its lookups to that container, so the dialog's static element
 * ids never collide even if the markup pattern is reused.
 */
(function (root) {
  'use strict';

  /* ── constants ──────────────────────────────────────────────────── */

  // Exact inline messages for the non-ok statuses (Requirements 11.1, 12.1, 13.1).
  var MESSAGES = {
    invalid_input: 'Please enter a valid DOI, DOI URL, or http/https URL.',
    not_found: 'No metadata was found for this identifier. You can continue entering the details manually.',
    fetch_error: 'Could not fetch metadata. Please try again.',
    unsupported_format: 'The URL was fetched, but the response is not in a supported metadata format.'
  };

  // Mapped resolved-field keys and the form field each writes to.
  // `notes` is bound to the `description` form field (Requirement 10.3, design
  // decision: contract key `notes` → scheming `description`).
  var RESOLVED_FIELDS = [
    { key: 'identifier_url', formField: 'identifier_url', label: 'Identifier URL' },
    { key: 'title', formField: 'title', label: 'Title' },
    { key: 'notes', formField: 'description', label: 'Description' },
    {
      key: 'instrument_classification',
      formField: 'instrument_classification',
      label: 'Instrument Classification'
    }
  ];

  var MANUAL_RESOLVED_FIELD_LABELS = {
    instrument_type_suggestions: 'Instrument Type Suggestions',
    manufacturer_suggestions: 'Manufacturer Suggestions',
    owner_suggestions: 'Owner Suggestions',
    funder_suggestions: 'Funder Suggestions',
    party_identifier_suggestions: 'Party Identifier Suggestions',
    taxonomy_suggestions: 'Taxonomy Suggestions',
    geo_location_suggestions: 'Geo Location Suggestions',
    publication_metadata_suggestions: 'Publication Metadata Suggestions',
    related_identifier_obj: 'Related Identifiers (manual review)'
  };

  var SUGGESTION_ONLY_FIELDS = Object.keys(MANUAL_RESOLVED_FIELD_LABELS);

  var SUPPORTED_COMPOSITE_FIELDS = [
    {
      key: 'model',
      label: 'Model',
      subfields: ['model_name', 'model_identifier', 'model_identifier_type']
    },
    {
      key: 'alternate_identifier_obj',
      label: 'Alternate Identifiers',
      subfields: [
        'alternate_identifier_type',
        'alternate_identifier',
        'alternate_identifier_name'
      ]
    },
    {
      key: 'date',
      label: 'Lifecycle Dates',
      subfields: ['date_value', 'date_type']
    },
    // NOTE: related_identifier_obj is intentionally excluded from
    // SUPPORTED_COMPOSITE_FIELDS. DataCite relatedIdentifiers do not provide
    // `related_resource_type`, which is required in the PIDINST schema. They
    // are surfaced as suggestion-only metadata for manual review instead.
  ];

  var LOCAL_MATCH_GROUPS = [
    {
      key: 'manufacturer',
      label: 'Manufacturer',
      targetLabel: 'Manufacturer',
      selectClass: 'manufacturer-party-dropdown',
      partyComposite: true,
      compositeField: 'manufacturer',
      partySubfield: 'manufacturer_party_id'
    },
    {
      key: 'owner',
      label: 'Owner',
      targetLabel: 'Owner',
      selectClass: 'owner-party-dropdown',
      partyComposite: true,
      compositeField: 'owner',
      partySubfield: 'owner_party_id'
    },
    {
      key: 'funder',
      label: 'Funder',
      targetLabel: 'Funding References',
      selectClass: 'funder-party-dropdown',
      partyComposite: true,
      compositeField: 'funder',
      partySubfield: 'funder_party_id'
    },
    {
      key: 'instrument_type',
      label: 'Instrument type',
      targetLabel: 'Instrument Type',
      vocabPicker: true,
      controlSelector: '#vocab-picker-instrument_type .vocab-picker-gcmd-select, ' +
        '#vocab-picker-instrument_type .vocab-picker-custom-select, ' +
        '#field-instrument_type, [name="instrument_type"]'
    },
    {
      key: 'measured_variable',
      label: 'Measured variable',
      targetLabel: 'Measured Variables',
      vocabPicker: true,
      controlSelector: '#vocab-picker-measured_variable .vocab-picker-gcmd-select, ' +
        '#vocab-picker-measured_variable .vocab-picker-custom-select, ' +
        '#field-measured_variable, [name="measured_variable"]'
    }
  ];

  // Optional fetched-metadata rows shown only when a value is present
  // (Requirements 7.4-7.8). source/doi/identifier_url are always shown.
  var OPTIONAL_FETCHED_FIELDS = [
    'title', 'description', 'creators', 'publisher', 'publication_year'
  ];

  var ACTION_PATH = '/api/3/action/pidinst_resolve_doi_metadata';

  /* ── pure helpers (testable in isolation) ───────────────────────── */

  /**
   * True when a current form value counts as "present" (non-empty after
   * trimming surrounding whitespace). A whitespace-only value is treated as
   * empty.
   */
  function hasValue(value) {
    return value != null && String(value).trim() !== '';
  }

  /**
   * Default "Apply?" state for a mapped field, computed from the current form
   * value (Requirements 8.3, 8.4, 9.1):
   *   - empty current value     → checked   (true)
   *   - non-empty current value → unchecked (false)
   *
   * Pure: depends only on its argument.
   */
  function defaultApplyState(currentValue) {
    return !hasValue(currentValue);
  }

  /**
   * Compute the result of confirming "Apply selected fields" (Requirements
   * 8.6, 8.7, 9.2). Pure: returns the final value each field should hold
   * without touching the DOM.
   *
   * @param {Array} fields Each item: { key, currentValue, resolvedValue, apply }
   * @returns {Array} Each item: { key, value, changed }
   *   - checked (apply true)  → value is the resolved value (replacing even a
   *                             non-empty current value); changed is true.
   *   - unchecked (apply false) → value is the original current value;
   *                             changed is false.
   */
  function applyResolvedFields(fields) {
    if (!fields || !fields.length) {
      return [];
    }
    return fields.map(function (field) {
      var apply = !!field.apply;
      return {
        key: field.key,
        value: apply ? field.resolvedValue : field.currentValue,
        changed: apply
      };
    });
  }

  function hasDisplayableMetadata(value) {
    if (value == null) {
      return false;
    }
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    if (typeof value === 'object') {
      return Object.keys(value).length > 0;
    }
    return String(value).trim() !== '';
  }

  function formatJsonForDisplay(value) {
    if (!hasDisplayableMetadata(value)) {
      return '';
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch (error) {
      return String(value);
    }
  }

  function manualResolvedFields(resolved) {
    var manual = {};
    resolved = resolved || {};
    Object.keys(MANUAL_RESOLVED_FIELD_LABELS).forEach(function (key) {
      if (hasDisplayableMetadata(resolved[key])) {
        manual[MANUAL_RESOLVED_FIELD_LABELS[key]] = resolved[key];
      }
    });
    return manual;
  }

  function localMatchGroups(matchedSuggestions) {
    matchedSuggestions = matchedSuggestions || {};
    return LOCAL_MATCH_GROUPS.map(function (group) {
      var matches = matchedSuggestions[group.key] || [];
      return {
        key: group.key,
        label: group.label,
        targetLabel: group.targetLabel,
        selectClass: group.selectClass,
        controlSelector: group.controlSelector,
        vocabPicker: group.vocabPicker,
        matches: matches.map(function (match) {
          var copy = {};
          Object.keys(match || {}).forEach(function (key) {
            copy[key] = match[key];
          });
          copy.group = group.key;
          return copy;
        })
      };
    });
  }

  function isIdentifierType(type) {
    return type === 'ROR' || type === 'URL' || type === 'URI';
  }

  function isEligibleMatch(match, formContext) {
    return localMatchRejectionReasons(match, formContext, true).length === 0;
  }

  function localMatchRejectionReasons(match, formContext, hasWriter) {
    var reasons = [];
    if (!match) {
      reasons.push('not exact_unique');
      return reasons;
    }
    if (!hasWriter) {
      reasons.push('no writer');
    }
    if (match.match_status !== 'exact_unique') {
      reasons.push('not exact_unique');
    }
    if (match.apply_allowed !== true) {
      reasons.push('apply_allowed false');
    }
    if (!hasValue(match.source_identifier)) {
      reasons.push('missing source_identifier');
    }
    if (!hasValue(match.source_identifier_type)) {
      reasons.push('missing source_identifier_type');
    } else if (!isIdentifierType(match.source_identifier_type)) {
      reasons.push('missing source_identifier_type');
    }
    if (!hasValue(match.matched_local_id)) {
      reasons.push('missing matched_local_id');
    }
    if (!match.group ||
        !formContext ||
        typeof formContext.hasSafeOption !== 'function') {
      reasons.push('no safe option/control found');
      return reasons;
    }
    if (formContext.hasSafeOption(match.group, match.matched_local_id) !== true) {
      reasons.push('no safe option/control found');
    }
    return reasons;
  }

  function debugLocalMatchEnabled() {
    if (root && root.PIDINST_DOI_RESOLVE_DEBUG === true) {
      return true;
    }
    try {
      return !!(root && root.localStorage &&
        root.localStorage.getItem('pidinstDoiResolveDebug') === '1');
    } catch (error) {
      return false;
    }
  }

  function parseJsonScript($script) {
    if (!$script || !$script.length) {
      return null;
    }
    try {
      return JSON.parse($script.text() || '');
    } catch (error) {
      return null;
    }
  }

  function splitIdentifierList(value) {
    if (!hasValue(value)) {
      return [];
    }
    return String(value).split(',').map(function (item) {
      return item.trim();
    }).filter(function (item) {
      return item !== '';
    });
  }

  function valueMatchesIdentifier(value, identifier) {
    return hasValue(value) &&
      hasValue(identifier) &&
      normalizeIdentifier(value) === normalizeIdentifier(identifier);
  }

  function vocabEntryMatchesIdentifier(entry, identifier) {
    if (!entry || typeof entry !== 'object') {
      return false;
    }
    return valueMatchesIdentifier(entry.identifier, identifier) ||
      valueMatchesIdentifier(entry.id, identifier) ||
      valueMatchesIdentifier(entry.uri, identifier) ||
      valueMatchesIdentifier(entry.value_uri, identifier) ||
      valueMatchesIdentifier(entry.valueURI, identifier);
  }

  function partyControlTargetIndex(controls, matchedLocalId) {
    if (!Array.isArray(controls) || !hasValue(matchedLocalId)) {
      return -1;
    }
    for (var i = 0; i < controls.length; i++) {
      var current = controls[i] || {};
      if (current.value === matchedLocalId &&
          (current.hasOption === true ||
           (current.optionValues || []).indexOf(matchedLocalId) !== -1)) {
        return i;
      }
    }
    for (var j = 0; j < controls.length; j++) {
      var candidate = controls[j] || {};
      if (!hasValue(candidate.value) &&
          (candidate.hasOption === true ||
           (candidate.optionValues || []).indexOf(matchedLocalId) !== -1)) {
        return j;
      }
    }
    return -1;
  }

  function partyCompositeApplyPlan(existingControls, matchedLocalIds) {
    var controls = (existingControls || []).map(function (control) {
      return {
        value: control && control.value ? String(control.value) : '',
        optionValues: (control && control.optionValues || []).slice()
      };
    });
    var applied = [];
    var skipped = [];
    (matchedLocalIds || []).forEach(function (matchedLocalId) {
      if (!hasValue(matchedLocalId)) {
        return;
      }
      var targetIndex = partyControlTargetIndex(controls, matchedLocalId);
      if (targetIndex !== -1) {
        if (controls[targetIndex].value !== matchedLocalId) {
          controls[targetIndex].value = matchedLocalId;
        }
        applied.push(matchedLocalId);
        return;
      }
      var template = null;
      for (var i = 0; i < controls.length; i++) {
        if ((controls[i].optionValues || []).indexOf(matchedLocalId) !== -1) {
          template = controls[i];
          break;
        }
      }
      if (!template) {
        skipped.push(matchedLocalId);
        return;
      }
      controls.push({
        value: matchedLocalId,
        optionValues: template.optionValues.slice()
      });
      applied.push(matchedLocalId);
    });
    return {
      values: controls.map(function (control) { return control.value; }),
      applied: applied,
      skipped: skipped
    };
  }

  function compositeFieldConfig(fieldName) {
    for (var i = 0; i < SUPPORTED_COMPOSITE_FIELDS.length; i++) {
      if (SUPPORTED_COMPOSITE_FIELDS[i].key === fieldName) {
        return SUPPORTED_COMPOSITE_FIELDS[i];
      }
    }
    return null;
  }

  function rowHasNonEmptyValue(row) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) {
      return false;
    }
    return Object.keys(row).some(function (key) {
      return hasValue(row[key]);
    });
  }

  function qualifiesForApply(value) {
    return Array.isArray(value) && value.some(rowHasNonEmptyValue);
  }

  function subfieldSignature(row, subfieldOrder) {
    row = row || {};
    subfieldOrder = subfieldOrder || [];
    return subfieldOrder.map(function (subfield) {
      var value = Object.prototype.hasOwnProperty.call(row, subfield)
        ? row[subfield]
        : '';
      return value == null ? '' : String(value).trim();
    });
  }

  function signatureKey(signature) {
    return JSON.stringify(signature || []);
  }

  function missingResolvedRows(existingRows, resolvedRows, subfieldOrder) {
    if (!Array.isArray(resolvedRows)) {
      return [];
    }

    var seen = {};
    (Array.isArray(existingRows) ? existingRows : []).forEach(function (row) {
      seen[signatureKey(subfieldSignature(row, subfieldOrder))] = true;
    });

    var missing = [];
    resolvedRows.forEach(function (row) {
      var signature = subfieldSignature(row, subfieldOrder);
      var hasAnyValue = signature.some(function (value) { return value !== ''; });
      var key = signatureKey(signature);
      if (!hasAnyValue || seen[key]) {
        return;
      }
      seen[key] = true;
      missing.push(row);
    });
    return missing;
  }

  function defaultCompositeApplyState(existingRows, subfieldOrder) {
    existingRows = Array.isArray(existingRows) ? existingRows : [];
    return !existingRows.some(function (row) {
      return subfieldSignature(row, subfieldOrder).some(function (value) {
        return value !== '';
      });
    });
  }

  function compositeApplyTargets(resolved) {
    resolved = resolved || {};
    return SUPPORTED_COMPOSITE_FIELDS.filter(function (config) {
      return qualifiesForApply(resolved[config.key]);
    });
  }

  function localMatchStatusLabel(status) {
    if (status === 'exact_unique') {
      return 'Exact match';
    }
    if (status === 'ambiguous') {
      return 'Multiple matches';
    }
    return 'No exact match';
  }

  function normalizeIdentifier(identifier) {
    return String(identifier || '').trim().replace(/\/+$/, '').toLowerCase();
  }

  function csrfHeaders(doc) {
    doc = doc || (root && root.document);
    if (!doc || !doc.querySelector) {
      return {};
    }

    var field = doc.querySelector('meta[name="csrf_field_name"]');
    var fieldName = field && field.getAttribute('content');
    if (!fieldName) {
      return {};
    }

    var token = doc.querySelector('meta[name="' + fieldName + '"]');
    var tokenValue = token && token.getAttribute('content');
    if (!tokenValue) {
      return {};
    }

    return { 'X-CSRFToken': tokenValue };
  }

  /**
   * Compute summary counts for the resolved tab. Pure helper exposed for
   * testing.
   *
   * @param {Object} opts
   * @param {Object} opts.matchedSuggestions - matched_suggestions from result
   * @param {Object} opts.resolved - resolved_fields from result
   * @param {Object} opts.manual - output of manualResolvedFields()
   * @param {Object} opts.unmapped - available_unmapped from result
   * @returns {Object} { exactMatches, manualLocal, structured, manualGroups, unmappedKeys }
   */
  function computeSummaryCounts(opts) {
    opts = opts || {};
    var matched = opts.matchedSuggestions || {};
    var resolved = opts.resolved || {};
    var manual = opts.manual || {};
    var unmapped = opts.unmapped || {};

    var groups = localMatchGroups(matched);
    var exactCount = 0;
    var manualLocalCount = 0;
    groups.forEach(function (group) {
      group.matches.forEach(function (match) {
        if (match.match_status === 'exact_unique') {
          exactCount++;
        } else {
          manualLocalCount++;
        }
      });
    });

    var structuredCount = compositeApplyTargets(resolved).length;
    var manualGroupCount = Object.keys(manual).length;
    var unmappedKeyCount = (unmapped && typeof unmapped === 'object' &&
      !Array.isArray(unmapped)) ? Object.keys(unmapped).length : 0;

    return {
      exactMatches: exactCount,
      manualLocal: manualLocalCount,
      structured: structuredCount,
      manualGroups: manualGroupCount,
      unmappedKeys: unmappedKeyCount
    };
  }

  /* ── CKAN module (browser only) ─────────────────────────────────── */

  function registerModule(ckan, jQuery) {
    var $ = jQuery;

    ckan.module('doi-resolve-module', function ($, _) {
      'use strict';

      return {
        options: {
          inputId: '',
          dialogId: ''
        },

        initialize: function () {
          var self = this;

          this.inFlight = false;
          this.$button = this.el;

          // The identifier_url input whose value is the resolution input
          // (Requirement 1.4).
          this.$input = $('#' + this.options.inputId);

          // The container the form snippet rendered the dialog markup into.
          // All dialog lookups are scoped here.
          this.$dialog = $('#' + this.options.dialogId);
          this.$modal = this.$dialog.find('.doi-resolve-dialog').first();

          if (!this.$input.length || !this.$modal.length) {
            // Missing wiring — leave the button inert rather than throwing.
            return;
          }

          this.$rowTemplate = this.$dialog
            .find('[data-doi-resolve="field-row-template"]').first();
          this.$fieldsBody = this.$dialog.find('[data-doi-resolve="fields"]').first();
          this.$structuredFields = this.$dialog
            .find('[data-doi-resolve="structured_fields"]').first();
          this.$applyButton = this.$dialog.find('[data-doi-resolve="apply"]').first();

          // Inline message holder, rendered next to the button. Created lazily.
          this.$message = null;

          this.$button.on('click', function (event) {
            event.preventDefault();
            self._onFetch();
          });

          this.$applyButton.on('click', function (event) {
            event.preventDefault();
            self._onApply();
          });
        },

        /* ── fetch flow ─────────────────────────────────────────── */

        _onFetch: function () {
          var self = this;

          // In-flight guard: prevent a second concurrent resolution from the
          // same form (Requirement 1.5).
          if (this.inFlight) {
            return;
          }
          this.inFlight = true;
          this.$button.prop('disabled', true);
          this._clearMessage();

          var identifier = this.$input.val() || '';

          $.ajax({
            url: ACTION_PATH,
            type: 'POST',
            contentType: 'application/json',
            dataType: 'json',
            headers: csrfHeaders(),
            data: JSON.stringify({ identifier: identifier })
          })
            .done(function (response) {
              if (!response || response.success !== true || !response.result) {
                // Unexpected API envelope — treat as a fetch error
                // (Requirement 6.7).
                self._handleStatus({ status: 'fetch_error' });
                return;
              }
              self._handleStatus(response.result);
            })
            .fail(function () {
              // AJAX/transport failure is treated as a fetch error
              // (Requirements 6.7, 13.1, 13.2, 13.3).
              self._handleStatus({ status: 'fetch_error' });
            })
            .always(function () {
              // Re-enable on both success and error (Requirement 1.5).
              self.inFlight = false;
              self.$button.prop('disabled', false);
            });
        },

        _handleStatus: function (result) {
          var status = result && result.status;
          if (status === 'ok') {
            this._openDialog(result);
            return;
          }
          // invalid_input / not_found / fetch_error (and anything unexpected):
          // keep the dialog closed and show the inline message; leave all form
          // values untouched (Requirements 11.1, 11.2, 12.1, 12.2, 13.1-13.3).
          var message = MESSAGES[status] || MESSAGES.fetch_error;
          this._showMessage(message);
        },

        /* ── dialog population ──────────────────────────────────── */

        _openDialog: function (result) {
          this._clearMessage();
          this._populateFetched(result);
          this._populateResolved(result);
          this._showModal();
        },

        _populateFetched: function (result) {
          var fetched = result.fetched || {};

          // Always-present values (Requirements 7.2, 7.3).
          this._setText('source', result.source || '');
          this._setText('doi', result.doi || '');

          var url = result.identifier_url || '';
          var $url = this.$dialog.find('[data-doi-resolve="identifier_url"]');
          $url.text(url);
          if ($url.is('a')) {
            $url.attr('href', url || '#');
          }

          // Optional descriptive fields — show the row only when present
          // (Requirements 7.4-7.8).
          for (var i = 0; i < OPTIONAL_FETCHED_FIELDS.length; i++) {
            var name = OPTIONAL_FETCHED_FIELDS[i];
            var value = fetched[name];
            var display = this._formatFetchedValue(value);
            this._setText(name, display);
            this._toggleFieldRow(name, display !== '');
          }

          // Warnings — one entry per returned warning (Requirements 7.9, 14.3).
          this._populateWarnings(result.warnings || []);
          this._populateJsonBlock(
            'provider_metadata',
            result.provider_metadata || fetched.provider_metadata || {}
          );
        },

        _populateWarnings: function (warnings) {
          var $list = this.$dialog.find('[data-doi-resolve="warnings"]').first();
          var $container = this.$dialog
            .find('[data-doi-resolve-field="warnings"]').first();
          $list.empty();
          if (!warnings.length) {
            this._setHidden($container, true);
            return;
          }
          for (var i = 0; i < warnings.length; i++) {
            $list.append($('<li>').text(warnings[i]));
          }
          this._setHidden($container, false);
        },

        _populateResolved: function (result) {
          var self = this;
          var resolved = result.resolved_fields || {};

          this.$fieldsBody.empty();
          this._rows = [];
          this._compositeRows = [];

          var unmapped = result.available_unmapped ||
            (result.fetched || {}).available_unmapped || {};
          this._populateUnmappedSection(unmapped);
          this._populateCompositeFields(resolved);
          var manual = manualResolvedFields(resolved);
          this._populateManualGroups(manual);
          this._populateJsonBlock('manual_resolved', manual);
          this._debugLocalMatch('result.matched_suggestions', result.matched_suggestions || {});
          this._populateLocalMatches(result.matched_suggestions || {});

          if (this.$rowTemplate.length) {
            RESOLVED_FIELDS.forEach(function (config) {
              var resolvedValue = resolved[config.key];
              if (resolvedValue == null) {
                resolvedValue = '';
              }

              var $formInput = self._findFormInput(config.formField);
              var currentValue = $formInput.length ? ($formInput.val() || '') : '';

              var $row = self._cloneRow();
              if (!$row) {
                return;
              }

              $row.find('[data-doi-resolve="field-name"]').text(config.label);
              $row.find('[data-doi-resolve="field-current"]').text(currentValue);
              $row.find('[data-doi-resolve="field-resolved"]').text(resolvedValue);

              var $check = $row.find('[data-doi-resolve="field-apply"]');
              $check.prop('checked', defaultApplyState(currentValue));

              self.$fieldsBody.append($row);

              self._rows.push({
                key: config.key,
                formField: config.formField,
                resolvedValue: resolvedValue,
                $input: $formInput,
                $check: $check
              });
            });
          }

          // Populate summary strip
          this._populateSummary(result, resolved, manual, unmapped);
        },

        /* ── apply flow ─────────────────────────────────────────── */

        _onApply: function () {
          var self = this;
          var rows = this._rows || [];
          var localRows = this._localMatchRows || [];
          var compositeRows = this._compositeRows || [];
          var hadCompositeError = false;

          // Build the pure input from the live checkbox + form state.
          var fields = rows.map(function (row) {
            return {
              key: row.key,
              currentValue: row.$input.length ? (row.$input.val() || '') : '',
              resolvedValue: row.resolvedValue,
              apply: row.$check.prop('checked')
            };
          });

          var outcomes = applyResolvedFields(fields);

          // Write only the checked fields into the in-memory form inputs;
          // unchecked fields are left unchanged (Requirements 8.6, 8.7, 9.2).
          // Nothing is saved here (Requirement 8.8).
          outcomes.forEach(function (outcome, index) {
            if (!outcome.changed) {
              return;
            }
            var row = rows[index];
            if (row && row.$input.length) {
              row.$input.val(outcome.value).trigger('change');
            }
          });

          var partyLocalRowsByGroup = {};
          localRows.forEach(function (row) {
            if (
              row.$check &&
              row.$check.prop('checked') &&
              row.writer &&
              isEligibleMatch(row.match, self._localMatchFormContext())
            ) {
              if (self._isPartyLocalMatchGroup(row.group)) {
                if (!partyLocalRowsByGroup[row.group]) {
                  partyLocalRowsByGroup[row.group] = [];
                }
                partyLocalRowsByGroup[row.group].push(row);
                return;
              }
              row.writer.write();
            }
          });

          Object.keys(partyLocalRowsByGroup).forEach(function (groupKey) {
            if (!self._applyPartyLocalMatchBatch(groupKey, partyLocalRowsByGroup[groupKey])) {
              hadCompositeError = true;
            }
          });

          compositeRows.forEach(function (row) {
            if (row.$check && row.$check.prop('checked')) {
              if (!self._applyCompositeField(row)) {
                hadCompositeError = true;
              }
            }
          });

          if (!hadCompositeError) {
            this._hideModal();
          }
        },

        /* ---- composite writer ---- */

        _compositeWidget: function (fieldName) {
          var $widget = $('#composite-repeating-div-' + fieldName).first();
          return $widget.length ? $widget : $();
        },

        _readExistingRows: function ($widget, subfieldOrder) {
          var rows = [];
          if (!$widget || !$widget.length) {
            return rows;
          }
          $widget.find('.composite-control-repeating').each(function () {
            var $row = $(this);
            var values = {};
            subfieldOrder.forEach(function (subfield) {
              var $control = $row.find(':input[name$="-' + subfield + '"]').first();
              values[subfield] = $control.length ? ($control.val() || '') : '';
            });
            rows.push(values);
          });
          return rows;
        },

        _applyCompositeField: function (row) {
          var config = row.config;
          var $notice = row.$notice;
          var $widget = this._compositeWidget(config.key);

          this._setHidden($notice, true);
          if (!$widget.length) {
            this._setHidden($notice, false);
            return false;
          }

          var existingRows = this._readExistingRows($widget, config.subfields);
          var rowsToAppend = missingResolvedRows(
            existingRows,
            row.resolvedRows,
            config.subfields
          );
          for (var i = 0; i < rowsToAppend.length; i++) {
            var index = this._appendCompositeRow($widget, config);
            if (index == null) {
              this._setHidden($notice, false);
              return false;
            }
            this._fillCompositeRow(config.key, index, rowsToAppend[i], config.subfields);
          }
          return true;
        },

        _appendCompositeRow: function ($widget, config) {
          var before = this._compositeRowIndexes($widget);
          var $add = $widget.find('.composite-add-container #add-field').first();
          if (!$add.length) {
            $add = $widget.find('#add-field').first();
          }
          if (!$add.length) {
            return null;
          }

          $add.prop('checked', true).trigger('change');
          $add.prop('checked', false);

          var after = this._compositeRowIndexes($widget);
          for (var i = 0; i < after.length; i++) {
            if (before.indexOf(after[i]) === -1 &&
                this._compositeRowHasControls($widget, config.key, after[i], config.subfields)) {
              return after[i];
            }
          }
          return null;
        },

        _compositeRowIndexes: function ($widget) {
          var indexes = [];
          var seen = {};
          $widget.find('.composite-control-repeating :input[name]').each(function () {
            var match = ($(this).attr('name') || '').match(/-(\d+)-/);
            if (!match) {
              return;
            }
            var index = parseInt(match[1], 10);
            if (!seen[index]) {
              seen[index] = true;
              indexes.push(index);
            }
          });
          return indexes;
        },

        _compositeRowHasControls: function ($widget, fieldName, index, subfieldOrder) {
          for (var i = 0; i < subfieldOrder.length; i++) {
            if ($widget.find('[name="' + fieldName + '-' + index + '-' + subfieldOrder[i] + '"]').length) {
              return true;
            }
          }
          return false;
        },

        _fillCompositeRow: function (fieldName, index, values, subfieldOrder) {
          var self = this;
          subfieldOrder.forEach(function (subfield) {
            var rawValue = values && values[subfield] != null ? values[subfield] : '';
            var value = rawValue == null ? '' : String(rawValue);
            if (!hasValue(value)) {
              return;
            }
            var selector = '[name="' + fieldName + '-' + index + '-' + subfield + '"], ' +
              '#field-' + fieldName + '-' + index + '-' + subfield + ', ' +
              '#' + fieldName + '-' + index + '-' + subfield;
            var $control = $(selector).first();
            if (!$control.length) {
              return;
            }
            self._setCompositeControlValue($control, value);
          });
        },

        _setCompositeControlValue: function ($control, value) {
          if ($control.is('select')) {
            var $option = $control.find('option').filter(function () {
              return $(this).val() === value;
            }).first();
            if (!$option.length) {
              return;
            }
            $control.val(value);
            if ($control.data('select2')) {
              $control.select2('val', value);
            }
            $control.trigger('change');
            return;
          }
          $control.val(value).trigger('change');
        },

        /* ── dialog helpers ─────────────────────────────────────── */

        _findFormInput: function (formField) {
          var $byId = $('#field-' + formField);
          if ($byId.length) {
            return $byId.first();
          }
          return $('[name="' + formField + '"]').first();
        },

        _cloneRow: function () {
          var tmpl = this.$rowTemplate.get(0);
          var node;
          if (tmpl && tmpl.content && tmpl.content.firstElementChild) {
            // <template> element — clone its content.
            node = tmpl.content.firstElementChild.cloneNode(true);
          } else {
            // Fallback: clone inner row markup directly.
            var $inner = this.$rowTemplate.find('[data-doi-resolve-row]').first();
            if (!$inner.length) {
              return null;
            }
            node = $inner.get(0).cloneNode(true);
          }
          return $(node);
        },

        _setText: function (name, value) {
          this.$dialog.find('[data-doi-resolve="' + name + '"]').text(value);
        },

        _populateJsonBlock: function (name, value) {
          var display = formatJsonForDisplay(value);
          this.$dialog.find('[data-doi-resolve="' + name + '"]').text(display);
          this._toggleFieldRow(name, display !== '');
        },

        _populateCompositeFields: function (resolved) {
          var self = this;
          var $groups = this.$structuredFields;
          this._compositeRows = [];
          if (!$groups || !$groups.length) {
            return;
          }

          $groups.empty();
          var targets = compositeApplyTargets(resolved);
          if (!targets.length) {
            $groups.append(
              $('<p>')
                .addClass('doi-resolve-structured-empty text-muted')
                .text('No structured fields can be applied from this DOI metadata.')
            );
            return;
          }

          // Build a table: Field | Resolved value / preview | Apply?
          var $table = $('<table>').addClass('doi-resolve-structured-table');
          var $thead = $('<thead>').append(
            $('<tr>')
              .append($('<th>').text('Field'))
              .append($('<th>').text('Resolved value'))
              .append($('<th>').addClass('doi-resolve-structured-apply-col').text('Apply?'))
          );
          $table.append($thead);
          var $tbody = $('<tbody>');

          targets.forEach(function (config) {
            var rows = resolved[config.key] || [];
            var $widget = self._compositeWidget(config.key);
            var existingRows = self._readExistingRows($widget, config.subfields);
            var checkboxId = 'doi-resolve-composite-' + config.key;

            var $tr = $('<tr>').attr('data-doi-resolve-composite-field', config.key);

            // Field name cell
            $tr.append(
              $('<td>').addClass('doi-resolve-structured-field-name').text(config.label)
            );

            // Preview cell with compact nested table
            var $previewCell = $('<td>').addClass('doi-resolve-structured-preview-cell');
            $previewCell.append(self._compositePreview(rows, config.subfields));
            $previewCell.append(
              $('<div>')
                .addClass('doi-resolve-composite-notice alert alert-warning')
                .css({ 'margin': '0.4rem 0 0', 'padding': '0.3rem 0.6rem', 'font-size': '0.8rem' })
                .attr({
                  role: 'alert',
                  hidden: 'hidden',
                  'data-doi-resolve': 'composite-apply-notice'
                })
                .text('Could not apply this structured field. You can still add it manually.')
            );
            $tr.append($previewCell);

            // Apply checkbox cell
            var $applyCell = $('<td>').addClass('doi-resolve-structured-apply-col');
            var $check = $('<input>')
              .attr({
                type: 'checkbox',
                id: checkboxId,
                'data-doi-resolve': 'composite-apply',
                'data-field': config.key,
                'aria-label': 'Apply ' + config.label
              })
              .addClass('doi-resolve-composite-apply-check')
              .prop('checked', defaultCompositeApplyState(existingRows, config.subfields));
            $applyCell.append($check);
            $tr.append($applyCell);

            $tbody.append($tr);

            self._compositeRows.push({
              config: config,
              resolvedRows: rows,
              $check: $check,
              $notice: $tr.find('[data-doi-resolve="composite-apply-notice"]').first()
            });
          });

          $table.append($tbody);
          $groups.append($table);
        },

        _compositePreview: function (rows, subfields) {
          var $table = $('<table>')
            .addClass('table table-sm doi-resolve-structured-preview');
          var $headRow = $('<tr>');
          subfields.forEach(function (subfield) {
            $headRow.append($('<th>').attr('scope', 'col').text(subfield));
          });
          $table.append($('<thead>').append($headRow));

          var $body = $('<tbody>');
          rows.forEach(function (row) {
            if (!rowHasNonEmptyValue(row)) {
              return;
            }
            var $row = $('<tr>');
            subfields.forEach(function (subfield) {
              var value = row && row[subfield] != null ? row[subfield] : '';
              $row.append($('<td>').text(value));
            });
            $body.append($row);
          });
          $table.append($body);
          return $table;
        },

        _populateManualGroups: function (manual) {
          // Render each manual/suggestion group as a compact card with
          // readable values. Raw JSON is available behind a collapsed toggle.
          var $groups = this.$dialog
            .find('[data-doi-resolve="manual_groups"]').first();
          if (!$groups.length) {
            return;
          }
          $groups.empty();
          manual = manual || {};
          var groupCount = Object.keys(manual).length;

          // Update the group count badge in the collapsed summary
          var $countBadge = this.$dialog
            .find('[data-doi-resolve="manual_group_count"]').first();
          if ($countBadge.length) {
            $countBadge.text(groupCount);
          }

          Object.keys(manual).forEach(function (label) {
            var value = manual[label];
            var itemCount = Array.isArray(value) ? value.length : 1;
            var $card = $('<div>').addClass('doi-resolve-manual-card');

            var $header = $('<div>').addClass('doi-resolve-manual-card-header');
            $header.append(
              $('<span>').addClass('doi-resolve-manual-card-title').text(label)
            );
            $header.append(
              $('<span>').addClass('badge badge-info doi-resolve-manual-card-count')
                .text(itemCount + (itemCount === 1 ? ' item' : ' items'))
            );
            $card.append($header);

            // Compact readable values
            if (Array.isArray(value)) {
              var $list = $('<ul>').addClass('doi-resolve-manual-card-list');
              value.forEach(function (item) {
                var text = '';
                if (item && typeof item === 'object') {
                  // Show key fields as compact text
                  var parts = [];
                  Object.keys(item).forEach(function (key) {
                    if (item[key] != null && String(item[key]).trim() !== '') {
                      parts.push(key + ': ' + String(item[key]).trim());
                    }
                  });
                  text = parts.join(' · ');
                } else {
                  text = String(item || '');
                }
                $list.append($('<li>').text(text));
              });
              $card.append($list);
            } else if (value && typeof value === 'object') {
              var $dl = $('<dl>').addClass('doi-resolve-manual-card-dl');
              Object.keys(value).forEach(function (key) {
                if (value[key] != null && String(value[key]).trim() !== '') {
                  $dl.append($('<dt>').text(key));
                  $dl.append($('<dd>').text(String(value[key]).trim()));
                }
              });
              $card.append($dl);
            }

            // Optional raw JSON toggle
            var $details = $('<details>').addClass('doi-resolve-json-details');
            $details.append($('<summary>').text('Show raw JSON'));
            $details.append(
              $('<pre>').addClass('doi-resolve-json-block')
                .text(formatJsonForDisplay(value))
            );
            $card.append($details);
            $groups.append($card);
          });
        },

        _populateUnmappedSection: function (unmapped) {
          var display = formatJsonForDisplay(unmapped);
          this.$dialog.find('[data-doi-resolve="available_unmapped"]').text(display);
          this._toggleFieldRow('available_unmapped', display !== '');

          // Render compact key list
          var $keys = this.$dialog
            .find('[data-doi-resolve="unmapped_keys"]').first();
          if ($keys.length) {
            $keys.empty();
            if (unmapped && typeof unmapped === 'object' && !Array.isArray(unmapped)) {
              var keys = Object.keys(unmapped);
              if (keys.length) {
                var $list = $('<ul>').addClass('doi-resolve-unmapped-key-list');
                keys.forEach(function (key) {
                  $list.append($('<li>').append(
                    $('<code>').text(key)
                  ));
                });
                $keys.append($list);
              }
            }
          }
        },

        _populateSummary: function (result, resolved, manual, unmapped) {
          var $summary = this.$dialog
            .find('[data-doi-resolve="summary"]').first();
          if (!$summary.length) {
            return;
          }

          var matched = result.matched_suggestions || {};
          var groups = localMatchGroups(matched);
          var exactCount = 0;
          var manualLocalCount = 0;
          groups.forEach(function (group) {
            group.matches.forEach(function (match) {
              if (match.match_status === 'exact_unique') {
                exactCount++;
              } else {
                manualLocalCount++;
              }
            });
          });

          var structuredCount = compositeApplyTargets(resolved).length;
          var manualGroupCount = Object.keys(manual).length;
          var unmappedKeyCount = (unmapped && typeof unmapped === 'object' &&
            !Array.isArray(unmapped)) ? Object.keys(unmapped).length : 0;

          var showSummary = exactCount > 0 || manualLocalCount > 0 ||
            structuredCount > 0 || manualGroupCount > 0 || unmappedKeyCount > 0;

          this._setHidden($summary, !showSummary);

          this._setSummaryBadge('summary-local-exact', exactCount);
          this._setSummaryBadge('summary-local-manual', manualLocalCount);
          this._setSummaryBadge('summary-structured', structuredCount);
          this._setSummaryBadge('summary-manual-groups', manualGroupCount);
          this._setSummaryBadge('summary-unmapped', unmappedKeyCount);
        },

        _setSummaryBadge: function (name, count) {
          var $badge = this.$dialog
            .find('[data-doi-resolve="' + name + '"]').first();
          var $count = this.$dialog
            .find('[data-doi-resolve="' + name + '-count"]').first();
          if ($badge.length) {
            this._setHidden($badge, count === 0);
          }
          if ($count.length) {
            $count.text(count);
          }
        },

        _populateLocalMatches: function (matchedSuggestions) {
          var self = this;
          var $groups = this.$dialog
            .find('[data-doi-resolve="local_match_groups"]').first();
          this._localMatchRows = [];
          if (!$groups.length) {
            return;
          }

          $groups.empty();
          var rendered = false;
          localMatchGroups(matchedSuggestions).forEach(function (group) {
            self._debugLocalMatch('local match group', {
              group: group.key,
              matches: group.matches
            });
            if (!group.matches.length) {
              return;
            }
            rendered = true;
            var $block = $('<div>').addClass('doi-resolve-local-match-group');
            $block.append($('<h6>').addClass('doi-resolve-local-match-group-title')
              .text(group.label));

            var $table = $('<table>')
              .addClass('table table-sm doi-resolve-local-match-table');
            $table.append(
              $('<thead>').append(
                $('<tr>')
                  .append($('<th>').attr('scope', 'col').text('Source'))
                  .append($('<th>').attr('scope', 'col').text('Matched local record'))
                  .append($('<th>').attr('scope', 'col').text('Status'))
                  .append($('<th>').attr('scope', 'col').addClass('doi-resolve-local-match-apply').text('Apply'))
              )
            );
            var $body = $('<tbody>');
            group.matches.forEach(function (match) {
              $body.append(self._localMatchRow(group, match));
            });
            $table.append($body);
            $block.append($table);
            $groups.append($block);
          });
          if (!rendered) {
            $groups.append(
              $('<p>')
                .addClass('doi-resolve-local-matches-empty text-muted')
                .text('No existing local matches were found.')
            );
          }
          this._toggleFieldRow('local_matches', true);
        },

        _localMatchRow: function (group, match) {
          var matchWithGroup = match || {};
          if (!matchWithGroup.group) {
            matchWithGroup.group = group.key;
          }
          if (matchWithGroup.match_status === 'exact_unique') {
            this._debugLocalMatch('exact match fields', {
              group: group.key,
              matched_local_id: matchWithGroup.matched_local_id,
              matched_local_record_id: matchWithGroup.matched_local_record_id,
              matched_local_name: matchWithGroup.matched_local_name,
              matched_local_label: matchWithGroup.matched_local_label,
              matched_local_identifier: matchWithGroup.matched_local_identifier,
              source_identifier: matchWithGroup.source_identifier,
              source_identifier_type: matchWithGroup.source_identifier_type,
              apply_allowed: matchWithGroup.apply_allowed
            });
          }
          var writer = this._localMatchWriter(group, matchWithGroup);
          var reasons = localMatchRejectionReasons(
            matchWithGroup,
            this._localMatchFormContext(),
            !!writer
          );
          var canApply = reasons.length === 0;
          this._debugLocalMatch('local match', {
            group: group.key,
            match: matchWithGroup,
            applyable: canApply,
            rejection_reasons: reasons
          });

          var isExact = matchWithGroup.match_status === 'exact_unique';
          var $row = $('<tr>').addClass('doi-resolve-local-match-row');
          if (!isExact) {
            $row.addClass('doi-resolve-local-match-row--warning');
          }

          // Source column: source value + identifier as muted sub-text
          var $sourceCell = $('<td>');
          var sourceLabel = matchWithGroup.source_value || group.targetLabel || '-';
          $sourceCell.append($('<span>').text(sourceLabel));
          if (matchWithGroup.source_identifier) {
            $sourceCell.append(
              $('<span>').addClass('doi-resolve-local-match-id')
                .text(matchWithGroup.source_identifier)
            );
          }
          $row.append($sourceCell);

          // Matched local record column: label + local ID as muted sub-text
          var $localCell = $('<td>');
          var localLabel = matchWithGroup.matched_local_label || matchWithGroup.matched_local_name || '-';
          $localCell.append($('<span>').text(localLabel));
          var localId = matchWithGroup.matched_local_identifier ||
            matchWithGroup.matched_local_id || '';
          if (localId && localId !== localLabel) {
            $localCell.append(
              $('<span>').addClass('doi-resolve-local-match-id').text(localId)
            );
          }
          $row.append($localCell);

          // Status column: badge
          var $statusCell = $('<td>');
          var statusLabel = localMatchStatusLabel(matchWithGroup.match_status);
          var badgeClass = 'doi-resolve-status-badge ';
          if (isExact) {
            badgeClass += 'doi-resolve-status-badge--exact';
          } else if (!canApply && matchWithGroup.match_status !== 'ambiguous') {
            badgeClass += 'doi-resolve-status-badge--manual';
            statusLabel = 'Manual review';
          } else {
            badgeClass += 'doi-resolve-status-badge--warning';
            statusLabel = 'No exact match found';
          }
          $statusCell.append($('<span>').addClass(badgeClass).text(statusLabel));
          $row.append($statusCell);

          // Apply column
          var $applyCell = $('<td>').addClass('doi-resolve-local-match-apply');
          if (canApply) {
            var $check = $('<input>')
              .attr({
                type: 'checkbox',
                'aria-label': 'Apply local match'
              })
              .addClass('doi-resolve-local-match-check')
              .prop('checked', defaultApplyState(writer.currentValue()));
            $applyCell.append($check);
            this._localMatchRows.push({
              group: group.key,
              match: matchWithGroup,
              writer: writer,
              $check: $check
            });
          } else {
            $applyCell.append(
              $('<span>').addClass('doi-resolve-status-badge doi-resolve-status-badge--manual')
                .text('Manual review')
            );
          }
          $row.append($applyCell);
          return $row;
        },

        _localMatchWriter: function (group, match) {
          var self = this;
          var matchedLocalId = match && match.matched_local_id;
          if (!hasValue(matchedLocalId)) {
            return null;
          }
          var groupConfig = this._localMatchGroupConfig(group);
          if (groupConfig && groupConfig.vocabPicker) {
            return this._localVocabMatchWriter(group, match);
          }
          this._debugLocalMatchControls(group, matchedLocalId);
          if (!this._hasPartySafeOption(group, matchedLocalId)) {
            return null;
          }
          return {
            currentValue: function () {
              var $control = self._localMatchControlForOption(group, matchedLocalId);
              if (!$control.length) {
                return '';
              }
              return $control.val() || '';
            },
            write: function () {
              return self._applyPartyLocalMatch(group, match);
            }
          };
        },

        _localVocabMatchWriter: function (group, match) {
          var self = this;
          var matchedLocalId = match && match.matched_local_id;
          this._debugVocabControls(group, matchedLocalId);
          var option = this._safeVocabOption(group, matchedLocalId);
          if (!option) {
            return null;
          }
          return {
            currentValue: function () {
              return self._vocabCurrentValue(group);
            },
            write: function () {
              var currentOption = self._safeVocabOption(group, matchedLocalId);
              if (!currentOption) {
                return false;
              }
              if (currentOption.$control && currentOption.$control.length) {
                if (currentOption.$control.data('select2')) {
                  currentOption.$control.select2('val', matchedLocalId);
                } else {
                  currentOption.$control.val(matchedLocalId);
                }
                currentOption.$control.trigger('change');
              }
              return true;
            }
          };
        },

        _localMatchFormContext: function () {
          var self = this;
          return {
            hasSafeOption: function (groupKey, matchedLocalId) {
              return self._hasSafeOption(groupKey, matchedLocalId);
            }
          };
        },

        _localMatchGroupConfig: function (groupOrKey) {
          var key = typeof groupOrKey === 'string'
            ? groupOrKey
            : groupOrKey && groupOrKey.key;
          for (var i = 0; i < LOCAL_MATCH_GROUPS.length; i++) {
            if (LOCAL_MATCH_GROUPS[i].key === key) {
              return LOCAL_MATCH_GROUPS[i];
            }
          }
          return null;
        },

        _isPartyLocalMatchGroup: function (groupOrKey) {
          var group = this._localMatchGroupConfig(groupOrKey);
          return !!(group && group.partyComposite);
        },

        _localMatchControls: function (groupOrKey) {
          var group = this._localMatchGroupConfig(groupOrKey);
          if (!group) {
            return $();
          }
          if (group.selectClass) {
            return $('.' + group.selectClass);
          }
          if (group.controlSelector) {
            return $(group.controlSelector);
          }
          return $();
        },

        _localMatchControl: function (groupOrKey) {
          var $controls = this._localMatchControls(groupOrKey);
          if (!$controls.length) {
            return $();
          }
          var $empty = $controls.filter(function () {
            return !hasValue($(this).val());
          }).first();
          return $empty.length ? $empty : $controls.first();
        },

        _localMatchControlForOption: function (groupOrKey, matchedLocalId) {
          var self = this;
          var $controls = this._localMatchControls(groupOrKey);
          if (!$controls.length || !hasValue(matchedLocalId)) {
            return $();
          }
          var controlStates = [];
          $controls.each(function () {
            var $control = $(this);
            var optionValues = [];
            $control.find('option').each(function () {
              optionValues.push($(this).val());
            });
            controlStates.push({
              value: $control.val() || '',
              optionValues: optionValues,
              hasOption: self._findSafeOption($control, matchedLocalId).length === 1
            });
          });
          var index = partyControlTargetIndex(controlStates, matchedLocalId);
          return index === -1 ? $() : $controls.eq(index);
        },

        _hasSafeOption: function (groupOrKey, matchedLocalId) {
          var group = this._localMatchGroupConfig(groupOrKey);
          if (group && group.vocabPicker) {
            return !!this._safeVocabOption(group, matchedLocalId);
          }
          return this._hasPartySafeOption(group, matchedLocalId);
        },

        _hasPartySafeOption: function (groupOrKey, matchedLocalId) {
          var self = this;
          var $controls = this._localMatchControls(groupOrKey);
          if (!$controls.length || !hasValue(matchedLocalId)) {
            return false;
          }
          return $controls.filter(function () {
            return self._findSafeOption($(this), matchedLocalId).length === 1;
          }).length > 0;
        },

        _applyPartyLocalMatchBatch: function (groupOrKey, rows) {
          var self = this;
          var group = this._localMatchGroupConfig(groupOrKey);
          var ok = true;
          var seen = {};
          rows.forEach(function (row) {
            var matchedLocalId = row && row.match && row.match.matched_local_id;
            if (!hasValue(matchedLocalId) || seen[matchedLocalId]) {
              return;
            }
            seen[matchedLocalId] = true;
            if (!self._applyPartyLocalMatch(group, row.match)) {
              ok = false;
            }
          });
          return ok;
        },

        _applyPartyLocalMatch: function (groupOrKey, match) {
          var group = this._localMatchGroupConfig(groupOrKey);
          var matchedLocalId = match && match.matched_local_id;
          if (!group || !group.partyComposite || !hasValue(matchedLocalId)) {
            return false;
          }
          var $control = this._localMatchControlForOption(group, matchedLocalId);
          if (!$control.length) {
            $control = this._appendPartyCompositeRowForMatch(group, matchedLocalId);
          }
          var $option = this._findSafeOption($control, matchedLocalId);
          if (!$control.length || !$option.length) {
            this._debugLocalMatch('party apply failed', {
              group: group.key,
              matched_local_id: matchedLocalId
            });
            return false;
          }
          if ($control.val() === matchedLocalId) {
            return true;
          }
          if (hasValue($control.val())) {
            return false;
          }
          if ($control.data('select2')) {
            $control.select2('val', matchedLocalId);
          } else {
            $control.val(matchedLocalId);
          }
          $control.trigger('change');
          this._syncPartyCompositeSiblingFields(group, $control);
          return true;
        },

        _appendPartyCompositeRowForMatch: function (groupOrKey, matchedLocalId) {
          var group = this._localMatchGroupConfig(groupOrKey);
          if (!group || !group.compositeField || !group.partySubfield) {
            return $();
          }
          var $widget = this._compositeWidget(group.compositeField);
          if (!$widget.length) {
            return $();
          }
          var index = this._appendCompositeRow($widget, {
            key: group.compositeField,
            subfields: [group.partySubfield]
          });
          if (index == null) {
            return $();
          }
          var $control = $widget.find(
            '[name="' + group.compositeField + '-' + index + '-' + group.partySubfield + '"]'
          ).first();
          if (!$control.length || !this._findSafeOption($control, matchedLocalId).length) {
            return $();
          }
          return $control;
        },

        _syncPartyCompositeSiblingFields: function (groupOrKey, $control) {
          var group = this._localMatchGroupConfig(groupOrKey);
          if (!group || !$control || !$control.length) {
            return;
          }
          var $option = $control.find('option:selected').first();
          var $row = $control.closest('.composite-control-repeating');
          if (!$option.length || !$row.length) {
            return;
          }
          var title = $option.data('party-title') || '';
          var identifier = $option.data('party-identifier') || '';
          var identifierType = $option.data('party-identifier-type') || '';
          if (group.key === 'manufacturer') {
            $row.find('input[name$="manufacturer_name"]').val(title);
            $row.find('input[name$="manufacturer_identifier"]').val(identifier);
            $row.find('input[name$="manufacturer_identifier_type"]').val(identifierType);
          } else if (group.key === 'owner') {
            $row.find('input[name$="owner_name"]').val(title);
            $row.find('input[name$="owner_identifier"]').val(identifier);
            $row.find('input[name$="owner_identifier_type"]').val(identifierType);
            $row.find('input[name$="owner_contact"]').val($option.data('party-contact') || '');
          } else if (group.key === 'funder') {
            $row.find('input[name$="funder_name"]').val(title);
            $row.find('input[name$="funder_identifier"]').val(identifier);
            $row.find('input[name$="funder_identifier_type"]').val(identifierType);
            $row.find('input[name$="schema_uri"]').val($option.data('party-schema-uri') || '');
          }
        },

        _findSafeOption: function ($control, matchedLocalId) {
          if (!$control || !$control.length || !hasValue(matchedLocalId)) {
            return $();
          }
          var $matches = $control.find('option').filter(function () {
            return $(this).val() === matchedLocalId;
          });
          return $matches.length === 1 ? $matches.first() : $();
        },

        _vocabPickerContainer: function (groupOrKey) {
          var group = this._localMatchGroupConfig(groupOrKey);
          if (!group || !group.vocabPicker) {
            return $();
          }
          return $('#vocab-picker-' + group.key).first();
        },

        _vocabControlForIdentifier: function (groupOrKey, identifier) {
          var $container = this._vocabPickerContainer(groupOrKey);
          if (!$container.length || !hasValue(identifier)) {
            return $();
          }
          var selector = this._looksLikeGcmdIdentifier(identifier)
            ? '.vocab-picker-gcmd-select'
            : '.vocab-picker-custom-select';
          var $control = $container.find(selector).first();
          if ($control.length) {
            return $control;
          }
          return $container.find('.vocab-picker-gcmd-select, .vocab-picker-custom-select').first();
        },

        _safeVocabOption: function (groupOrKey, identifier) {
          var $container = this._vocabPickerContainer(groupOrKey);
          if (!$container.length || !hasValue(identifier)) {
            return null;
          }

          var $control = this._vocabControlForIdentifier(groupOrKey, identifier);
          var $option = this._findSafeOption($control, identifier);
          if ($option.length) {
            return { source: 'option', $control: $control };
          }
          if ($control.length && valueMatchesIdentifier($control.val(), identifier)) {
            return { source: 'control', $control: $control };
          }

          var foundHidden = false;
          $container.find('.vocab-picker-hidden-inputs input').each(function () {
            if (valueMatchesIdentifier($(this).val(), identifier)) {
              foundHidden = true;
              return false;
            }
            return true;
          });
          if (foundHidden) {
            return { source: 'hidden' };
          }

          var composite = parseJsonScript(
            $container.find('.vocab-picker-existing-composite').first()
          );
          if (Array.isArray(composite)) {
            for (var i = 0; i < composite.length; i++) {
              if (vocabEntryMatchesIdentifier(composite[i], identifier)) {
                return { source: 'existing-composite' };
              }
            }
          }

          var gcmd = parseJsonScript(
            $container.find('.vocab-picker-existing-gcmd').first()
          );
          var codes = gcmd ? splitIdentifierList(gcmd.codes) : [];
          for (var j = 0; j < codes.length; j++) {
            if (valueMatchesIdentifier(codes[j], identifier)) {
              return { source: 'existing-gcmd' };
            }
          }
          return null;
        },

        _vocabCurrentValue: function (groupOrKey) {
          var found = '';
          var $container = this._vocabPickerContainer(groupOrKey);
          if (!$container.length) {
            return '';
          }
          $container.find('.vocab-picker-hidden-inputs input').each(function () {
            var value = $(this).val();
            if (hasValue(value)) {
              found = value;
              return false;
            }
            return true;
          });
          return found;
        },

        _looksLikeGcmdIdentifier: function (identifier) {
          var value = String(identifier || '').toLowerCase();
          return value.indexOf('cmr.earthdata.nasa.gov') !== -1 ||
            value.indexOf('gcmd.earthdata.nasa.gov') !== -1 ||
            value.indexOf('vocabs.ardc.edu.au') !== -1;
        },

        _debugLocalMatch: function (label, payload) {
          if (!debugLocalMatchEnabled() ||
              !root.console ||
              typeof root.console.log !== 'function') {
            return;
          }
          root.console.log('[doi-resolve local matches]', label, payload);
        },

        _debugLocalMatchControls: function (groupOrKey, matchedLocalId) {
          if (!debugLocalMatchEnabled()) {
            return;
          }
          var group = this._localMatchGroupConfig(groupOrKey);
          if (!group || group.vocabPicker) {
            return;
          }
          var $controls = this._localMatchControls(group);
          var hasEmptyCompositeRow = false;
          var controls = [];
          $controls.each(function () {
            var $control = $(this);
            var $row = $control.closest('.composite-control-repeating');
            var rowEmpty = true;
            if ($row.length) {
              $row.find(':input').each(function () {
                var $input = $(this);
                if ($input.is(':checkbox,:radio')) {
                  if ($input.prop('checked')) {
                    rowEmpty = false;
                    return false;
                  }
                  return true;
                }
                if (hasValue($input.val())) {
                  rowEmpty = false;
                  return false;
                }
                return true;
              });
              if (rowEmpty) {
                hasEmptyCompositeRow = true;
              }
            }
            var optionValues = [];
            $control.find('option').each(function () {
              optionValues.push($(this).val());
            });
            controls.push({
              exists: true,
              name: $control.attr('name') || '',
              id: $control.attr('id') || '',
              option_values: optionValues,
              current_selected_value: $control.val() || '',
              select2_attached: !!$control.data('select2'),
              inside_composite_row: $row.length > 0,
              composite_row_empty: $row.length ? rowEmpty : null,
              composite_row_visible: $row.length ? $row.is(':visible') : null,
              has_exact_option: optionValues.indexOf(matchedLocalId) !== -1
            });
          });
          this._debugLocalMatch('party controls', {
            group: group.key,
            matched_local_id: matchedLocalId,
            control_exists: $controls.length > 0,
            has_empty_composite_row: hasEmptyCompositeRow,
            needs_existing_empty_row_or_new_row: $controls.length > 0 &&
              $controls.closest('.composite-control-repeating').length > 0 &&
              !hasEmptyCompositeRow,
            controls: controls
          });
        },

        _debugVocabControls: function (groupOrKey, matchedLocalId) {
          if (!debugLocalMatchEnabled()) {
            return;
          }
          var group = this._localMatchGroupConfig(groupOrKey);
          if (!group || !group.vocabPicker) {
            return;
          }
          var $container = this._vocabPickerContainer(group);
          var hiddenValues = [];
          var controls = [];
          if ($container.length) {
            $container.find('.vocab-picker-hidden-inputs input').each(function () {
              hiddenValues.push({
                name: $(this).attr('name') || '',
                value: $(this).val() || ''
              });
            });
            $container.find('.vocab-picker-gcmd-select, .vocab-picker-custom-select').each(function () {
              var $control = $(this);
              var optionValues = [];
              $control.find('option').each(function () {
                optionValues.push($(this).val());
              });
              controls.push({
                classes: $control.attr('class') || '',
                current_value: $control.val() || '',
                option_values: optionValues,
                select2_attached: !!$control.data('select2')
              });
            });
          }
          this._debugLocalMatch('vocab controls', {
            group: group.key,
            matched_local_id: matchedLocalId,
            container_exists: $container.length > 0,
            hidden_inputs: hiddenValues,
            existing_composite: parseJsonScript(
              $container.find('.vocab-picker-existing-composite').first()
            ),
            existing_gcmd: parseJsonScript(
              $container.find('.vocab-picker-existing-gcmd').first()
            ),
            controls: controls,
            safe_option_source: (this._safeVocabOption(group, matchedLocalId) || {}).source || ''
          });
        },

        _toggleFieldRow: function (name, visible) {
          var $row = this.$dialog
            .find('[data-doi-resolve-field="' + name + '"]').first();
          this._setHidden($row, !visible);
        },

        _setHidden: function ($el, hidden) {
          if (!$el || !$el.length) {
            return;
          }
          if (hidden) {
            $el.attr('hidden', 'hidden');
          } else {
            $el.removeAttr('hidden');
          }
        },

        _formatFetchedValue: function (value) {
          if (value == null) {
            return '';
          }
          if (Array.isArray(value)) {
            return value.filter(function (v) { return v != null && v !== ''; })
              .join(', ');
          }
          return String(value);
        },

        /* ── modal show/hide ────────────────────────────────────── */

        _modalElement: function () {
          return this.$modal.get(0);
        },

        _showModal: function () {
          var el = this._modalElement();
          if (!el) {
            return;
          }
          if (root.bootstrap && root.bootstrap.Modal) {
            root.bootstrap.Modal.getOrCreateInstance(el).show();
            return;
          }
          // Defensive fallback if the Bootstrap JS bundle is unavailable.
          this.$modal.addClass('show').css('display', 'block').removeAttr('hidden');
        },

        _hideModal: function () {
          var el = this._modalElement();
          if (!el) {
            return;
          }
          if (root.bootstrap && root.bootstrap.Modal) {
            root.bootstrap.Modal.getOrCreateInstance(el).hide();
            return;
          }
          this.$modal.removeClass('show').css('display', 'none');
        },

        /* ── inline messages (non-ok statuses) ──────────────────── */

        _showMessage: function (text) {
          if (!this.$message) {
            this.$message = $('<div>')
              .addClass('pidinst-doi-resolve-message alert alert-warning')
              .attr('role', 'alert');
            this.$button.closest('.pidinst-doi-resolve').append(this.$message);
          }
          this.$message.text(text).show();
        },

        _clearMessage: function () {
          if (this.$message) {
            this.$message.text('').hide();
          }
        }
      };
    });
  }

  /* ── wiring: register in browser, export for tests ──────────────── */

  if (typeof root.ckan !== 'undefined' && root.ckan.module && typeof jQuery !== 'undefined') {
    registerModule(root.ckan, jQuery);
  }

  var api = {
    MESSAGES: MESSAGES,
    RESOLVED_FIELDS: RESOLVED_FIELDS,
    SUPPORTED_COMPOSITE_FIELDS: SUPPORTED_COMPOSITE_FIELDS,
    SUGGESTION_ONLY_FIELDS: SUGGESTION_ONLY_FIELDS,
    LOCAL_MATCH_GROUPS: LOCAL_MATCH_GROUPS,
    hasValue: hasValue,
    defaultApplyState: defaultApplyState,
    applyResolvedFields: applyResolvedFields,
    compositeFieldConfig: compositeFieldConfig,
    qualifiesForApply: qualifiesForApply,
    subfieldSignature: subfieldSignature,
    missingResolvedRows: missingResolvedRows,
    defaultCompositeApplyState: defaultCompositeApplyState,
    compositeApplyTargets: compositeApplyTargets,
    hasDisplayableMetadata: hasDisplayableMetadata,
    formatJsonForDisplay: formatJsonForDisplay,
    manualResolvedFields: manualResolvedFields,
    localMatchGroups: localMatchGroups,
    isIdentifierType: isIdentifierType,
    isEligibleMatch: isEligibleMatch,
    localMatchRejectionReasons: localMatchRejectionReasons,
    localMatchStatusLabel: localMatchStatusLabel,
    normalizeIdentifier: normalizeIdentifier,
    valueMatchesIdentifier: valueMatchesIdentifier,
    vocabEntryMatchesIdentifier: vocabEntryMatchesIdentifier,
    partyControlTargetIndex: partyControlTargetIndex,
    partyCompositeApplyPlan: partyCompositeApplyPlan,
    csrfHeaders: csrfHeaders,
    computeSummaryCounts: computeSummaryCounts
  };

  // CommonJS (test runners).
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }

  // Browser global (DOM tests / debugging).
  root.PidinstDoiResolve = api;

})(typeof window !== 'undefined' ? window : this);
