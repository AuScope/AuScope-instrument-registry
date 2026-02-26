this.ckan.module('pidinst-composite-repeating', function (jQuery, _) {
  'use strict';

  return {
    options: {
      fieldSelector: '.composite-control-repeating',
      required: 'false',
      startEmpty: 'false',
      fieldLabel: 'item'
    },

    initialize: function () {
      if (jQuery('html').hasClass('ie7')) return;

      var self = this;
      jQuery.proxyAll(this, /_on/);

      this.isRequired  = (this.options.required === 'true');
      this.startEmpty  = (this.options.startEmpty === 'true');
      this.fieldLabel  = this.options.fieldLabel || 'item';

      // Capture clean blank-row template before DOM manipulation
      var firstRow = this.el.find(this.options.fieldSelector + ':first');
      if (firstRow.length) {
        this.templateRow = this._cleanClone(firstRow);
      }

      // Add minus buttons on existing rows
      var fieldContainers = this.el.find(this.options.fieldSelector);
      fieldContainers.each(function (index) {
        if (jQuery(this).attr('data-row-readonly') === 'true') return;
        jQuery(this).find('.controls:first')
          .append(self._getMinusButton(index + 1));
      });
      this.el.find('.fa-minus').children(':checkbox').hide();

      this._updateMinusButtons();

      // Persistent "+ Add" button outside repeating rows
      this.addBtnContainer = jQuery(
        '<div class="composite-add-container" style="margin-top:8px; padding: 8px 0;"></div>'
      );
      var addBtnText = '<i class="fa fa-plus" style="margin-right:6px;"></i>Add ' + 
                       this.fieldLabel.charAt(0).toUpperCase() + this.fieldLabel.slice(1);
      var addBtn = jQuery(
        '<label class="checkbox btn btn-success composite-btn composite-add-btn" ' +
        'style="margin:0;"><input type="checkbox" id="add-field" ' +
        'style="display:none;"/><span class="add-btn-text">' + addBtnText + '</span></label>'
      );
      this.addBtnContainer.append(addBtn);
      this.el.append(this.addBtnContainer);

      // Event delegation for add/remove buttons
      this.el.on('change', ':checkbox', jQuery.proxy(this._onChange, this));

      // Empty-start: remove the hidden blank row from DOM
      if (this.startEmpty) {
        this.el.find(this.options.fieldSelector).remove();
      }
    },

    teardown: function () {
      this.el.off('change', ':checkbox');
    },

    _cleanClone: function (row) {
      var clone = jQuery(row).clone(false, false);

      // Remove dynamic widgets
      clone.find('.composite-btn').remove();
      clone.find('.composite-panel-header').remove();
      var wrapper = clone.find('.composite-content');
      if (wrapper.length) { wrapper.children().unwrap(); }
      
      // Remove Select2 artifacts
      clone.find('.select2-container').remove();
      clone.find('.select2-offscreen').removeClass('select2-offscreen');
      clone.find('.select2-hidden-accessible').removeClass('select2-hidden-accessible');

      // Reset select elements
      clone.find('select').each(function () {
        jQuery(this).find('option').removeAttr('selected').prop('selected', false);
        this.selectedIndex = 0;
      });

      // Reset inputs/textareas
      clone.find('input, textarea').each(function () {
        var $i = jQuery(this);
        var type = ($i.attr('type') || '').toLowerCase();
        if (type === 'checkbox' || type === 'radio') {
          $i.prop('checked', false);
          $i.removeAttr('checked');
        } else if (type !== 'hidden') {
          $i.val('');
          $i.removeAttr('value');
        } else {
          $i.val('');
        }
      });

      // Remove disabled/readonly state
      clone.find(':input').each(function () {
        var $i = jQuery(this);
        $i.removeAttr('disabled').removeAttr('readonly');
        $i.prop('disabled', false).prop('readonly', false);
        $i.removeAttr('data-select2-id');
      });

      clone.find('*').removeClass('disabled select2-hidden-accessible');
      clone.find('input, select, textarea').removeClass('pidinst-disabled');
      clone.removeClass('is-readonly');
      clone.removeAttr('data-row-readonly');
      clone.removeAttr('style');

      return clone;
    },

    _getMinusButton: function (index) {
      var btn = jQuery(
        '<label class="checkbox btn btn-danger fa fa-minus composite-btn">' +
        '<input type="checkbox" /></label>'
      );
      btn.attr('id', 'label-remove-field-' + index)
         .attr('name', 'label-remove-field-' + index);
      btn.find(':checkbox')
         .attr('id', 'remove-field-' + index)
         .attr('name', 'remove-field-' + index);
      return btn;
    },

    _increment: function (index, str) {
      return (str || '').replace(/\d+/, function (n) {
        return 1 + parseInt(n, 10);
      });
    },

    newFieldFromTemplate: function () {
      if (!this.templateRow) {
        console.error('[pidinst-composite-repeating] No template row available');
        return;
      }
      var newRow = this.templateRow.clone(false, false);

      var existingCount = this.el.find(this.options.fieldSelector).length;
      if (existingCount > 0) {
        this._setRowIndex(newRow, existingCount + 1);
      }

      this._attachRow(newRow);
      this._afterAddRowReset(newRow);
      this._updateMinusButtons();
    },

    _afterAddRowReset: function (row) {
      // Reset selects
      row.find('select').each(function () {
        var $sel = jQuery(this);
        $sel.find('option').removeAttr('selected').prop('selected', false);
        this.selectedIndex = 0;
        $sel.val($sel.find('option:first').val() || '');
        $sel.removeAttr('data-select2-id');
      });

      // Reset inputs/textareas
      row.find('input, textarea').each(function () {
        var $input = jQuery(this);
        var type = ($input.attr('type') || '').toLowerCase();
        if (type === 'checkbox' || type === 'radio') {
          $input.prop('checked', false).removeAttr('checked');
        } else {
          $input.val('');
        }
        // Destroy select2 if present
        if ($input.data('select2')) {
          try { $input.select2('destroy'); } catch (e) { /* noop */ }
        }
        $input.removeData('select2');
        $input.removeAttr('data-select2-id');
      });

      // Remove disabled/readonly
      row.find(':input').each(function () {
        var $el = jQuery(this);
        $el.removeAttr('disabled').removeAttr('readonly');
        $el.prop('disabled', false).prop('readonly', false);
        $el.removeClass('disabled pidinst-disabled');
      });

      // Remove select2 containers
      row.find('.select2-container').remove();
      row.find('.select2-hidden-accessible').removeClass('select2-hidden-accessible');
      row.find('.form-group, .control-group').removeClass('disabled');

      row.removeAttr('style');
      row.show();
    },

    _setRowIndex: function (row, idx) {
      row.find('label.control-label').each(function () {
        var $l = jQuery(this);
        $l.attr('for', ($l.attr('for') || '').replace(/\d+/, idx));
        $l.text(($l.text() || '').replace(/\d+/, idx));
      });
      row.find(':input').each(function () {
        var $i = jQuery(this);
        if ($i.attr('id'))   $i.attr('id',   $i.attr('id').replace(/\d+/, idx));
        if ($i.attr('name')) $i.attr('name', $i.attr('name').replace(/\d+/, idx));
      });
      row.find('label.fa-minus').each(function () {
        var $l = jQuery(this);
        if ($l.attr('id'))   $l.attr('id',   $l.attr('id').replace(/\d+/, idx));
        if ($l.attr('name')) $l.attr('name', $l.attr('name').replace(/\d+/, idx));
      });
    },

    _attachRow: function (row) {
      var self = this;

      row.find('.composite-btn').remove();
      row.find('.composite-panel-header').remove();
      var cw = row.find('.composite-content');
      if (cw.length) { cw.children().unwrap(); }

      var count = this.el.find(this.options.fieldSelector).length + 1;
      row.find('.controls:first').append(this._getMinusButton(count));
      row.find('.fa-minus').children(':checkbox').hide();

      row.removeAttr('style');
      row.show();

      this.addBtnContainer.before(row);
      
      return row;
    },

    resetField: function (field) {
      var inc = this._increment;

      var input = field.find(':input');
      input.attr('id', inc).attr('name', inc);
      input.each(function () {
        if (!jQuery(this).hasClass('composite-multiple-checkbox')) {
          jQuery(this).val('');
        }
      });
      input.filter('.composite-multiple-checkbox').attr('checked', false);

      var label = field.find('label');
      label.each(function () {
        var $l = jQuery(this);
        if (!$l.hasClass('fa-minus') && $l.hasClass('control-label')) {
          $l.attr('for', inc);
        }
      });
      label.each(function () {
        var $l = jQuery(this);
        if ($l.hasClass('fa-minus')) {
          $l.attr('id', inc).attr('name', inc);
        }
      });
      label.each(function () {
        var $l = jQuery(this);
        if ($l.hasClass('control-label')) { $l.text(inc); }
      });

      field.find('.fa-plus').remove();
      field.find('button.outsidebutton').remove();
      return field;
    },

    deleteField: function (target) {
      var field = jQuery(target).parents('.composite-control-repeating').first();
      
      var totalRows = this.el.find(this.options.fieldSelector)
        .filter(function() {
          return jQuery(this).attr('data-row-readonly') !== 'true';
        }).length;

      if (this.isRequired && totalRows <= 1) {
        alert('This field is required. You cannot delete the last item.');
        jQuery(target).prop('checked', false);
        return;
      }
      
      field.remove();
      this._updateMinusButtons();
    },

    _updateMinusButtons: function () {
      var self = this;
      var totalRows = this.el.find(this.options.fieldSelector)
        .filter(function() {
          return jQuery(this).attr('data-row-readonly') !== 'true';
        }).length;
      
      if (this.isRequired && totalRows <= 1) {
        this.el.find(this.options.fieldSelector).each(function() {
          if (jQuery(this).attr('data-row-readonly') !== 'true') {
            jQuery(this).find('.fa-minus').hide();
          }
        });
      } else {
        this.el.find(this.options.fieldSelector).each(function() {
          if (jQuery(this).attr('data-row-readonly') !== 'true') {
            jQuery(this).find('.fa-minus').show();
          }
        });
      }
    },

    _onChange: function (event) {
      var target = event.target || event.currentTarget;
      var targetId = target.id || '';
      
      if (targetId === 'add-field') {
        this.newFieldFromTemplate();
      } else if (targetId && targetId.indexOf('remove-field-') === 0) {
        this.deleteField(target);
      }
    }
  };
});
