ckan.module('pidinst-composite-enhancements', function ($, _) {
  return {
    initialize: function () {
      var self = this;
      this.hideDependentFields();
      this.updateCollapsiblePanels();
      this.updateIndexes();

      // Re-process after row add/remove
      $(document).on('click', '.composite-btn.btn-success', function () {
        self.assignUniqueIdsAndDestroySelect2().then(() => {
          setTimeout(function () {
            self.updateIndexes();
            self.updateCollapsiblePanels();
            self.initializeAllSelect2().then(() => {
              self.reapplySelect2Values();
              self.initializeRorSelect2();
              self.reapplyRorValues();
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
          self.initializeRorSelect2();
          self.reapplyRorValues();
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
        // Destroy author-affiliation Select2 instances
        $('input[name*="author-"][name*="-author_affiliation"]:not([name$="_identifier"])').each(function () {
          var $input = $(this);
          if ($input.data('select2')) {
            $input.select2('destroy');
          }
        });
        // Destroy ROR owner Select2 instances
        $('input.ror-owner-lookup').each(function () {
          var $input = $(this);
          if ($input.data('select2')) {
            try { $input.select2('destroy'); } catch (e) { /* noop */ }
          }
          $input.removeData('select2');
        });
        // Clean leftover Select2 containers from cloneNode
        $('[data-ror-subfield] .select2-container').remove();
        $('input.ror-owner-lookup')
          .removeClass('select2-offscreen select2-hidden-accessible')
          .removeAttr('style');
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

    // ----------------------------------------------------------------
    // ROR Owner (Facility) Select2 – integrated into the same
    // destroy → cloneNode → reinit lifecycle as author_affiliation.
    // ----------------------------------------------------------------

    _rorEsc: function (s) {
      if (!s) return '';
      var d = document.createElement('div');
      d.appendChild(document.createTextNode(String(s)));
      return d.innerHTML;
    },

    _rorDerivePrefix: function ($input) {
      var name = $input.attr('name') || '';
      var m = name.match(/^(.+-\d+-)/);
      return m ? m[1] : '';
    },

    initializeRorSelect2: function () {
      var self = this;
      $('input.ror-owner-lookup').each(function () {
        var $input = $(this);
        // Skip hidden template rows
        if ($input.closest('.composite-control-repeating').css('display') === 'none') return;
        // Skip if already initialised
        if ($input.data('select2')) return;

        var prefix = self._rorDerivePrefix($input);
        if (!prefix) return;

        var $block   = $input.closest('[data-ror-subfield]');
        var $preview = $block.find('.ror-hierarchy-preview');
        var $text    = $block.find('.ror-hierarchy-text');

        function fid(sub) { return '#field-' + prefix + sub; }
        function setH(sub, v) { $(fid(sub)).val(v); }
        var esc = self._rorEsc;

        var debounce;
        $input.select2({
          placeholder: 'Start typing to search ROR\u2026',
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
            h += '<strong>' + esc(item.name) + '</strong>';
            if (item.types) h += ' <small class="text-muted">(' + esc(item.types) + ')</small>';
            if (item.state || item.country) {
              var loc = item.state ? item.state + ', ' + item.country : item.country;
              h += '<br><small class="text-muted"><i class="fa fa-map-marker"></i> ' + esc(loc) + '</small>';
            }
            if (item.hierarchy_display && item.hierarchy_display !== item.name) {
              h += '<br><small class="text-muted"><i class="fa fa-sitemap"></i> ' + esc(item.hierarchy_display) + '</small>';
            }
            h += '</div>';
            return h;
          },
          formatSelection: function (item) { return esc(item.name || item.text || ''); },
          escapeMarkup: function (m) { return m; }
        })
        .on('change', function (e) {
          if (e.added) {
            setH('owner_ror_id',                e.added.ror_id || e.added.id || '');
            setH('owner_ror_name',              e.added.name || '');
            setH('owner_ror_types',             e.added.types || '');
            setH('owner_ror_country',           e.added.country || '');
            setH('owner_ror_state',             e.added.state || '');
            setH('owner_ror_website',           e.added.website || '');
            setH('owner_ror_parents_json',      e.added.parents_json || '[]');
            setH('owner_ror_hierarchy_display', e.added.hierarchy_display || '');
            var hier = e.added.hierarchy_display || e.added.name || '';
            if (hier) { $text.text(hier); $preview.show(); }
          } else if (!$input.select2('val')) {
            $.each(['owner_ror_id','owner_ror_name','owner_ror_types','owner_ror_country',
                    'owner_ror_state','owner_ror_website','owner_ror_parents_json',
                    'owner_ror_hierarchy_display'], function (_, s) { setH(s, ''); });
            $preview.hide(); $text.text('');
          }
        });
      });
    },

    reapplyRorValues: function () {
      var self = this;
      $('input.ror-owner-lookup').each(function () {
        var $input = $(this);
        if (!$input.data('select2')) return;
        var prefix = self._rorDerivePrefix($input);
        if (!prefix) return;

        var rorId   = $('#field-' + prefix + 'owner_ror_id').val();
        var rorName = $input.data('display-name') || $('#field-' + prefix + 'owner_ror_name').val();
        if (!rorId || !rorName) return;

        try {
          $input.select2('data', { id: rorId, text: rorName, name: rorName });
          var hier = $('#field-' + prefix + 'owner_ror_hierarchy_display').val();
          if (hier) {
            var $block = $input.closest('[data-ror-subfield]');
            $block.find('.ror-hierarchy-text').text(hier);
            $block.find('.ror-hierarchy-preview').show();
          }
        } catch (e) {
          console.error('Error restoring ROR Select2:', $input.attr('id'), e);
        }
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
