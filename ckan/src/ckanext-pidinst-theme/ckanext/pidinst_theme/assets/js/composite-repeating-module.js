ckan.module('composite-repeating-module', function ($, _) {
  return {
    initialize: function () {
      var self = this;
      this.hideDependentFields();
      this.updateCollapsiblePanels();
      this.updateIndexes();

      $(document).on('click', '.composite-btn.btn-success', function () {
        self.assignUniqueIdsAndDestroySelect2().then(() => {
          setTimeout(function () {
            self.updateIndexes();
            self.updateCollapsiblePanels();
            self.initializeAllSelect2().then(() => {
              self.reapplySelect2Values();
            });
          }, 100);
        });
      });
      this.assignUniqueIdsAndDestroySelect2().then(() => {
        self.initializeAllSelect2().then(() => {
          self.reapplySelect2Values();
        });
      });
    },

    reapplySelect2Values: function () {
      var self = this;
      $('input[name*="author-"][name*="-author_affiliation"]:not([name$="_identifier"])').each(function () {
        var $input = $(this);
        if (!$input.data("select2")) {
          // console.error("Select2 has not been initialized on the element:", $input.attr('id'));
          return;
        }
        var identifierFieldId = $input.attr('id').replace('affiliation', 'affiliation_identifier');
        var $identifierField = $('#' + identifierFieldId);
        if ($identifierField.length === 0) {
          // console.error("Identifier field not found:", identifierFieldId);
          return;
        }
        var selectedId = $identifierField.val();
        var selectedText = $input.val(); // Assuming this gets the text correctly
        if (!selectedId || !selectedText) {
          // console.error("Selected ID or text is missing for input:", $input.attr('id'));
          return; // Skip this iteration
        }
        try {
          ///TODO: This should  probably be fixed in the  future but for now just return the selected
          $input.select2('data', { id: selectedText, text: selectedText }, true);
          // $input.select2('data', { id: selectedId, text: selectedText }, true);
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
      } else {
        console.error('Input field not found:', $inputField.attr('id'));
      }
      var $identifierField = $('#' + identifierFieldId);
      if ($identifierField.length) {
        $identifierField.val(affiliationId);
      } else {
        console.error('Identifier field not found:', identifierFieldId);
      }
      var $identifierTypeField = $('#' + identifierTypeFieldId);
      if ($identifierTypeField.length) {
        $identifierTypeField.val('ROR'); // Assuming ROR is the identifier type
      } else {
        console.error('Identifier type field not found:', identifierTypeFieldId);
      }
    },

    hideDependentFields: function () {
      $('input[id*="author-"][id*="-author_affiliation"]:not([id*="identifier"])').each(function () {
        var $inputField = $(this);
        var identifierFieldId = $inputField.attr('id').replace('affiliation', 'affiliation_identifier');
        var $identifierFieldGroup = $('#' + identifierFieldId).closest('.form-group');
        if ($identifierFieldGroup.length) {
          $identifierFieldGroup.hide();
        } else {
          console.error('Identifier field group not found for:', identifierFieldId);
        }

        var identifierTypeFieldId = $inputField.attr('id').replace('affiliation', 'affiliation_identifier_type');
        var $identifierTypeFieldGroup = $('#' + identifierTypeFieldId).closest('.form-group');
        if ($identifierTypeFieldGroup.length) {
          $identifierTypeFieldGroup.hide();
        } else {
          console.error('Identifier type field group not found for:', identifierTypeFieldId);
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
        let headerText = panelHeader.querySelector('span:last-child'); // Assuming the last span is the headerText
        if (!headerText) {
          headerText = document.createElement('span');
          panelHeader.appendChild(headerText);
        }
        headerText.textContent = 'Details of ' + title + ' ' + (index + 1);
      } else {
        // If somehow there's no panelHeader, create it anew (might be unlikely if cloning behavior is consistent)
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
      $(document).find('[data-module="composite-repeating"]').each(function () {
        var title = $(this).closest('[data-module="composite-repeating-module"]').find('.hidden-title-input').val() || 'Default Title';
        const groups = this.querySelectorAll('.composite-control-repeating');
        self.makeCollapsible(title, groups);
      });
    },

    updateIndexes: function () {
      $(document).find('[data-module="composite-repeating"]').each(function () {
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
