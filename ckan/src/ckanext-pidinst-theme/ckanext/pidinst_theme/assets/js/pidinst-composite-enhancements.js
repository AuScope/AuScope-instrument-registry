ckan.module('pidinst-composite-enhancements', function ($, _) {
  return {
    initialize: function () {
      var self = this;
      this.hideDependentFields();
      this.applyConditionalDisplay();
      this.updateCollapsiblePanels();
      this.updateIndexes();
      // Initialize party selects AFTER updateCollapsiblePanels has run
      this.initPartySelects();
      this.initFunderPartySelects();
      this.initManufacturerPartySelects();

      // Re-process after row add/remove
      $(document).on('click', '.composite-btn.btn-success', function () {
        self.assignUniqueIdsAndDestroySelect2().then(() => {
          setTimeout(function () {
            self.updateIndexes();
            self.updateCollapsiblePanels();
            self.applyConditionalDisplay();
            self.initPartySelects();
            self.initFunderPartySelects();
            self.initManufacturerPartySelects();
            self.initializeAllSelect2().then(() => {
              self.reapplySelect2Values();
            });
          }, 100);
        });
      });

      $(document).on('click', '.composite-btn.btn-danger', function () {
        setTimeout(function () {
          self.updateIndexes();
          self.updateCollapsiblePanels();
          self.hideDependentFields();
        }, 100);
      });

      this.assignUniqueIdsAndDestroySelect2().then(() => {
        self.initializeAllSelect2().then(() => {
          self.reapplySelect2Values();
        });
      });

      this.applyDynamicLabel();
    },

    applyDynamicLabel: function () {
      var labelInstrument = this.options.labelInstrument;
      var labelPlatform   = this.options.labelPlatform;
      if (!labelInstrument && !labelPlatform) return;

      var isPlatform = $('#field-is_platform').val() === 'true';
      var newLabel   = isPlatform ? (labelPlatform || labelInstrument)
                                  : (labelInstrument || labelPlatform);
      if (!newLabel) return;

      // composite_header renders a <label> as the first label inside this.el
      var $label = this.el.find('label:first');
      if (!$label.length) return;

      // Preserve the required-star span if present
      var $required = $label.find('.control-required').detach();
      $label.text(newLabel);
      if ($required.length) {
        $label.prepend($required);
      }
    },

    /* ── party owner Select2 ──────────────────────────────────────────
     *  Scoped to this.el so only the owner instance acts on
     *  the party dropdowns.  Other composite-field instances find
     *  zero dropdowns and return immediately.
     * ─────────────────────────────────────────────────────────────────── */
    initPartySelects: function () {
      var $dropdowns = this.el.find('.owner-party-dropdown');
      if ($dropdowns.length === 0) return;

      // Thoroughly clean up Select2 artifacts (stale clones, hiding)
      $dropdowns.each(function () {
        var $sel = $(this);
        if ($sel.data('select2')) {
          $sel.select2('destroy');
        }
        // Remove dead Select2 containers left by cloneNode
        $sel.siblings('.select2-container').remove();
        // Remove Select2 hiding classes and data attributes
        $sel.removeClass('select2-offscreen select2-hidden-accessible');
        $sel.removeAttr('data-select2-id');
        // Reset inline style to the original width (Select2 may have hidden it)
        $sel.attr('style', 'width:100%');
      });

      // (Re-)initialize Select2 and bind change handler
      $dropdowns.each(function () {
        var $select = $(this);

        $select.select2({
          placeholder: '-- Select a party --',
          allowClear: true,
          width: 'resolve'
        });

        // Direct binding — Select2 v3 doesn't reliably bubble 'change'
        $select.off('change.ownerParty').on('change.ownerParty', function () {
          var $opt     = $select.find('option:selected');
          var $row     = $select.closest('.composite-control-repeating');

          var facTitle   = $opt.data('party-title')   || '';
          var facContact = $opt.data('party-contact') || '';
          var facId      = $opt.data('party-identifier')      || '';
          var facIdType  = $opt.data('party-identifier-type')  || '';

          $row.find('input[name$="owner_contact"]').val(facContact);

          // Hidden fields for DOI minting
          $row.find('input[name$="owner_name"]').val(facTitle);
          $row.find('input[name$="owner_identifier"]').val(facId);
          $row.find('input[name$="owner_identifier_type"]').val(facIdType);
        });
      });
    },

    /* ── Funder party Select2 ───────────────────────────────────────
     *  Same pattern as initPartySelects but for the funder composite.
     *  Scoped to this.el so only the funder instance processes these.
     * ─────────────────────────────────────────────────────────────────── */
    initFunderPartySelects: function () {
      var $dropdowns = this.el.find('.funder-party-dropdown');
      if ($dropdowns.length === 0) return;

      // Thoroughly clean up Select2 artifacts (stale clones, hiding)
      $dropdowns.each(function () {
        var $sel = $(this);
        if ($sel.data('select2')) {
          $sel.select2('destroy');
        }
        $sel.siblings('.select2-container').remove();
        $sel.removeClass('select2-offscreen select2-hidden-accessible');
        $sel.removeAttr('data-select2-id');
        $sel.attr('style', 'width:100%');
      });

      $dropdowns.each(function () {
        var $select = $(this);

        $select.select2({
          placeholder: '-- Select a funder --',
          allowClear: true,
          width: 'resolve'
        });

        $select.off('change.funderParty').on('change.funderParty', function () {
          var $opt = $select.find('option:selected');
          var $row = $select.closest('.composite-control-repeating');

          var facTitle     = $opt.data('party-title')           || '';
          var facId        = $opt.data('party-identifier')      || '';
          var facIdType    = $opt.data('party-identifier-type')  || '';

          $row.find('input[name$="funder_name"]').val(facTitle);
          $row.find('input[name$="funder_identifier"]').val(facId);
          $row.find('input[name$="funder_identifier_type"]').val(facIdType);
        });
      });
    },

    /* ── Manufacturer party Select2 ────────────────────────────────
     *  Same pattern as initPartySelects but for the manufacturer composite.
     *  Scoped to this.el so only the manufacturer instance processes these.
     * ─────────────────────────────────────────────────────────────────── */
    initManufacturerPartySelects: function () {
      var $dropdowns = this.el.find('.manufacturer-party-dropdown');
      if ($dropdowns.length === 0) return;

      $dropdowns.each(function () {
        var $sel = $(this);
        if ($sel.data('select2')) {
          $sel.select2('destroy');
        }
        $sel.siblings('.select2-container').remove();
        $sel.removeClass('select2-offscreen select2-hidden-accessible');
        $sel.removeAttr('data-select2-id');
        $sel.attr('style', 'width:100%');
      });

      $dropdowns.each(function () {
        var $select = $(this);

        $select.select2({
          placeholder: '-- Select a manufacturer --',
          allowClear: true,
          width: 'resolve'
        });

        $select.off('change.mfrParty').on('change.mfrParty', function () {
          var $opt = $select.find('option:selected');
          var $row = $select.closest('.composite-control-repeating');

          var partyTitle  = $opt.data('party-title')           || '';
          var partyId     = $opt.data('party-identifier')      || '';
          var partyIdType = $opt.data('party-identifier-type')  || '';

          $row.find('input[name$="manufacturer_name"]').val(partyTitle);
          $row.find('input[name$="manufacturer_identifier"]').val(partyId);
          $row.find('input[name$="manufacturer_identifier_type"]').val(partyIdType);
        });
      });
    },

    reapplySelect2Values: function () {
      var self = this;
      $('input[name*="author-"][name*="-author_affiliation"]:not([name$="_identifier"])').each(function () {
        var $input = $(this);
        if (!$input.data("select2")) return;

        var identifierFieldId = $input.attr('id').replace('affiliation', 'affiliation_identifier');
        var $identifierField = $('#' + identifierFieldId);
        if ($identifierField.length === 0) return;

        var selectedId = $identifierField.val();
        var selectedText = $input.val();
        if (!selectedId || !selectedText) return;

        try {
          $input.select2('data', { id: selectedText, text: selectedText }, true);
          $input.val(selectedId);
          self.fillDependentFields($input, selectedId, selectedText);
        } catch (error) {
          console.error("Error setting Select2 data for input:", $input.attr('id'), error);
        }
      });
    },

    assignUniqueIdsAndDestroySelect2: function () {
      return new Promise(function (resolve) {
        $('input[name*="author-"][name*="-author_affiliation"]:not([name$="_identifier"])').each(function (index) {
          var $input = $(this);
          if ($input.data('select2')) {
            $input.select2('destroy');
          }
        });
        resolve();
      });
    },

    initializeAllSelect2: function () {
      var self = this;
      return new Promise(function (resolve, reject) {
        var $inputs = $('input[name*="author-"][name*="-author_affiliation"]:not([name$="_identifier"])');
        var inputsCount = $inputs.length;

        if (inputsCount === 0) {
          resolve();
        }
        $inputs.each(function (index) {
          var $input = $(this);
          $input.off('select2-selected');
          $input.select2({
            ajax: {
              url: 'https://api.ror.org/organizations',
              dataType: 'json',
              delay: 250,
              data: function (params) {
                var encodedQuery = encodeURIComponent(params);
                return { affiliation: encodedQuery };
              },
              processResults: function (data) {
                return {
                  results: $.map(data.items, function (item) {
                    return { id: item.organization.id, text: item.organization.name };
                  })
                };
              },
              cache: true
            },
            placeholder: 'Search for an affiliation',
            minimumInputLength: 3,
          })

          $input.on('select2-selected', function (e) {
            var selectedData = e.choice;
            if (selectedData && selectedData.id && selectedData.text) {
              self.fillDependentFields($input, selectedData.id, selectedData.text);
            }
          });

          if (index + 1 === inputsCount) {
            resolve();
          }

        });
      });
    },

    fillDependentFields: function ($inputField, affiliationId, affiliationName) {
      var identifierFieldId = $inputField.attr('id').replace('affiliation', 'affiliation_identifier');
      var identifierTypeFieldId = $inputField.attr('id').replace('affiliation', 'affiliation_identifier_type');

      if ($inputField.length) {
        $inputField.val(affiliationName);
      }

      var $identifierField = $('#' + identifierFieldId);
      if ($identifierField.length) {
        $identifierField.val(affiliationId);
      }

      var $identifierTypeField = $('#' + identifierTypeFieldId);
      if ($identifierTypeField.length) {
        $identifierTypeField.val('ROR');
      }
    },

    /* ── Conditional show/hide (schema show_if) ────────────────────────
     *  Reads data-show-if-field / data-show-if-value attributes emitted
     *  by the pidinst_composite_repeating template and shows/hides the
     *  wrapper div whenever the controlling select value changes.
     *  Works per-row so multiple repeating rows are independent.
     * ─────────────────────────────────────────────────────────────────── */
    applyConditionalDisplay: function () {
      this.el.find('.composite-show-if-wrapper').each(function () {
        var $wrapper    = $(this);
        var controlName = $wrapper.data('show-if-field');  // subfield name only
        var controlVal  = String($wrapper.data('show-if-value'));
        var $row        = $wrapper.closest('.composite-control-repeating');
        // Find the controlling select/input in the same row by matching name suffix
        var $control    = $row.find('[name$="-' + controlName + '"]');

        function update() {
          if (String($control.val()) === controlVal) {
            $wrapper.show();
          } else {
            $wrapper.hide();
          }
        }

        update();
        $control.off('change.showif').on('change.showif', update);
      });
    },

    hideDependentFields: function () {
      $('input[id*="author-"][id*="-author_affiliation"]:not([id*="identifier"])').each(function () {
        var $inputField = $(this);
        var identifierFieldId = $inputField.attr('id').replace('affiliation', 'affiliation_identifier');
        var $identifierFieldGroup = $('#' + identifierFieldId).closest('.form-group');
        if ($identifierFieldGroup.length) {
          $identifierFieldGroup.hide();
        }

        var identifierTypeFieldId = $inputField.attr('id').replace('affiliation', 'affiliation_identifier_type');
        var $identifierTypeFieldGroup = $('#' + identifierTypeFieldId).closest('.form-group');
        if ($identifierTypeFieldGroup.length) {
          $identifierTypeFieldGroup.hide();
        }
      });
    },

    makeCollapsible: function (title, groups) {
      var self = this;
      groups.forEach(function (group, index) {
        let panelHeader = group.querySelector('.composite-panel-header');
        let contentWrapper = group.querySelector('.composite-content');
        self.updatePanelHeader(group, panelHeader, contentWrapper, title, index);
      });
    },

    updatePanelHeader: function (group, panelHeader, contentWrapper, title, index) {
      if (!contentWrapper) {
        contentWrapper = document.createElement('div');
        contentWrapper.className = 'composite-content active';
        Array.from(group.childNodes).forEach(function (child) {
          if (child !== panelHeader) contentWrapper.appendChild(child.cloneNode(true));
        });
        while (group.firstChild) group.removeChild(group.firstChild);
        if (panelHeader) group.appendChild(panelHeader);
        group.appendChild(contentWrapper);
      }

      if (panelHeader) {
        let headerText = panelHeader.querySelector('span:last-child');
        if (!headerText) {
          headerText = document.createElement('span');
          panelHeader.appendChild(headerText);
        }
        headerText.textContent = 'Details of ' + title + ' ' + (index + 1);
      } else {
        panelHeader = document.createElement('div');
        panelHeader.className = 'composite-panel-header';
        const toggleIndicator = document.createElement('span');
        toggleIndicator.className = 'toggle-indicator';
        toggleIndicator.textContent = '▼';
        const headerText = document.createElement('span');
        headerText.textContent = 'Details of ' + title + ' ' + (index + 1);
        panelHeader.appendChild(toggleIndicator);
        panelHeader.appendChild(headerText);
        group.insertBefore(panelHeader, group.firstChild);
      }

      const panelHeaderClone = panelHeader.cloneNode(true);
      panelHeader.parentNode.replaceChild(panelHeaderClone, panelHeader);

      panelHeaderClone.addEventListener('click', function () {
        contentWrapper.classList.toggle('active');
        const indicator = panelHeaderClone.querySelector('.toggle-indicator');
        indicator.textContent = contentWrapper.classList.contains('active') ? '▲' : '▼';
      });
    },

    updateCollapsiblePanels: function () {
      var self = this;
      $('[data-module="pidinst-composite-repeating"]').each(function () {
        var title = $(this).closest('[data-module="pidinst-composite-enhancements"]').find('.hidden-title-input').val() || 'Default Title';
        const groups = this.querySelectorAll('.composite-control-repeating');
        self.makeCollapsible(title, groups);
      });
    },

    updateIndexes: function () {
      $('[data-module="pidinst-composite-repeating"]').each(function () {
        $(this).find('.composite-control-repeating').each(function (index, item) {
          $(item).find('label, input, select').each(function () {
            if (this.tagName === 'LABEL' && this.htmlFor) {
              const newFor = this.htmlFor.replace(/\d+/, index + 1);
              this.htmlFor = newFor;
              const matches = this.textContent.match(/(.*?)(\d+)$/);
              if (matches && matches.length > 2) {
                this.textContent = `${matches[1]}${index + 1}`;
              }
            }

            if (this.tagName === 'INPUT' || this.tagName === 'SELECT') {
              const baseId = this.id.replace(/\d+/, index + 1);
              this.id = baseId;
              const baseName = this.name.replace(/\d+/, index + 1);
              this.name = baseName;
            }
          });
        });
      });
    }
  };
});
