/**
 * composite-repeating.js
 *
 * Replacement for the upstream ckanext-composite "composite-repeating" module.
 * Adds support for:
 *  - Non-required fields: empty initial state, allow deleting the last row.
 *  - Required fields: keep at least one row (original behavior).
 *
 * Options (set via data-module-* attributes on the element):
 *  - required:    "true" | "false"  (default "false")
 *  - start-empty: "true" | "false"  (default "false")
 */
this.ckan.module('composite-repeating', function (jQuery, _) {
  'use strict';

  return {
    options: {
      fieldSelector: '.composite-control-repeating',
      required: 'false',
      startEmpty: 'false'
    },

    initialize: function () {
      if (jQuery('html').hasClass('ie7')) return;

      var self = this;
      jQuery.proxyAll(this, /_on/);

      this.isRequired  = (this.options.required === 'true');
      this.startEmpty  = (this.options.startEmpty === 'true');

      /* ── 1. Capture a clean blank-row template before anyone else touches the DOM ── */
      var firstRow = this.el.find(this.options.fieldSelector + ':first');
      if (firstRow.length) {
        this.templateRow = this._cleanClone(firstRow);
      }

      /* ── 2. Minus buttons on every existing row ── */
      var fieldContainers = this.el.find(this.options.fieldSelector);
      fieldContainers.each(function (index) {
        // Skip readonly rows (e.g. IsNewVersionOf)
        if (jQuery(this).attr('data-row-readonly') === 'true') return;
        jQuery(this).find('.controls:first')
          .append(self._getMinusButton(index + 1));
      });
      this.el.find('.fa-minus').each(function () {
        jQuery(this).on('change', ':checkbox', self._onChange);
        jQuery(this).children(':checkbox').hide();
      });

      /* ── 3. Persistent "+ Add" button (lives OUTSIDE any repeating row) ── */
      this.addBtnContainer = jQuery(
        '<div class="composite-add-container" style="margin-top:4px;"></div>'
      );
      var addBtn = jQuery(
        '<label class="checkbox btn btn-success fa fa-plus composite-btn" ' +
        'style="margin-top:3px;"><input type="checkbox" id="add-field" ' +
        'style="padding:5px;"/></label>'
      );
      addBtn.on('change', ':checkbox', this._onChange);
      addBtn.children(':checkbox').hide();
      this.addBtnContainer.append(addBtn);
      this.el.append(this.addBtnContainer);

      /* ── 4. Empty-start handling: remove the hidden blank row from the DOM ── */
      if (this.startEmpty) {
        this.el.find(this.options.fieldSelector).remove();
      }
    },

    /* ------------------------------------------------------------------ */
    /*  Helpers                                                           */
    /* ------------------------------------------------------------------ */

    /** Create a clean (value-cleared) deep clone suitable for templating. */
    _cleanClone: function (row) {
      var clone = jQuery(row).clone(true, true);

      // Strip dynamic widgets added by composite-repeating-module
      clone.find('.composite-btn').remove();
      clone.find('.composite-panel-header').remove();
      var wrapper = clone.find('.composite-content');
      if (wrapper.length) { wrapper.children().unwrap(); }
      clone.find('.select2-container').remove();
      clone.find('.select2-offscreen').removeClass('select2-offscreen');

      // Clear inputs
      clone.find(':input').each(function () {
        var $i = jQuery(this);
        if ($i.hasClass('composite-multiple-checkbox')) {
          $i.prop('checked', false);
        } else {
          $i.val('');
        }
        $i.removeAttr('disabled');
      });

      // Remove readonly markers
      clone.removeClass('is-readonly');
      clone.removeAttr('data-row-readonly');
      clone.removeAttr('style'); // remove any display:none from start-empty

      return clone;
    },

    /** Build a minus-button label for the given 1-based index. */
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

    /** Regex-increment the first number in a string. */
    _increment: function (index, str) {
      return (str || '').replace(/\d+/, function (n) {
        return 1 + parseInt(n, 10);
      });
    },

    /* ------------------------------------------------------------------ */
    /*  Row operations                                                    */
    /* ------------------------------------------------------------------ */

    /** Clone + reset the source row, then append it before the add-button. */
    newField: function (source) {
      var newRow = this.resetField(jQuery(source).clone(true, true));
      this._attachRow(newRow);
    },

    /** Create a brand-new row from the stored blank template. */
    newFieldFromTemplate: function () {
      if (!this.templateRow) return;
      // Clone and reset so indexes increment from "1" in the template
      var newRow = this.templateRow.clone(true, true);
      // Don't call resetField – template already has correct base index (1)
      this._attachRow(newRow);
    },

    /** Common logic: wire minus button and insert before the add-container. */
    _attachRow: function (row) {
      var self = this;

      // Remove any old +/- buttons that came along with the clone
      row.find('.composite-btn').remove();

      // Remove collapsible wrappers that might have been cloned
      row.find('.composite-panel-header').remove();
      var cw = row.find('.composite-content');
      if (cw.length) { cw.children().unwrap(); }

      var count = this.el.find(this.options.fieldSelector).length + 1;
      row.find('.controls:first').append(this._getMinusButton(count));
      row.find('.fa-minus').each(function () {
        jQuery(this).on('change', ':checkbox', self._onChange);
        jQuery(this).children(':checkbox').hide();
      });

      this.addBtnContainer.before(row);
    },

    /**
     * Increment the first number found in every id / name / for / label-text
     * inside the given row. (Same logic as upstream.)
     */
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

    /** Remove (or clear) a row, respecting the required-field rule. */
    deleteField: function (target) {
      var field = jQuery(target).parents('.composite-control-repeating').first();
      var totalRows = this.el.find(this.options.fieldSelector).length;

      if (totalRows > 1) {
        // More than one row: always OK to remove
        field.remove();
      } else if (!this.isRequired) {
        // Non-required: allow removing the very last row → empty state
        field.remove();
      } else {
        // Required: keep row, just clear values
        field.find(':input').each(function () {
          if (!jQuery(this).hasClass('composite-multiple-checkbox')) {
            jQuery(this).val('');
          }
        });
        field.find('.composite-multiple-checkbox').prop('checked', false);
      }
    },

    /* ------------------------------------------------------------------ */
    /*  Event handler                                                     */
    /* ------------------------------------------------------------------ */

    _onChange: function (event) {
      if (event.currentTarget.id === 'add-field') {
        var lastRow = this.el.find(this.options.fieldSelector + ':last');
        if (lastRow.length) {
          this.newField(lastRow);
        } else {
          // Empty state → create from blank template
          this.newFieldFromTemplate();
        }
      } else {
        this.deleteField(event.currentTarget);
      }
    }
  };
});
