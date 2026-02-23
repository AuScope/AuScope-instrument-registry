/**
 * cover-photo-module.js
 *
 * CKAN JS module that manages the "Use as cover photo" checkbox on the
 * resource form.
 *
 * Responsibilities:
 *  1. Show the checkbox only when the resource is an image
 *     (detected from file input, URL, or format field).
 *  2. When the user checks the box and another cover photo already exists
 *     for the dataset, display a confirmation dialog; revert if cancelled.
 *  3. Keep the hidden-input / checkbox pair in sync so the correct value
 *     ("true" or "false") is always submitted.
 */
ckan.module("cover-photo", function ($, _) {
  "use strict";

  /* ---- constants ---- */

  var IMAGE_EXTENSIONS = [
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg",
    "tiff", "tif", "ico", "avif"
  ];

  var IMAGE_FORMATS = IMAGE_EXTENSIONS.concat([
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/bmp", "image/svg+xml", "image/tiff", "image/avif",
    "image/x-icon"
  ]);

  /* ---- helpers ---- */

  function extensionOf(name) {
    if (!name) return "";
    // strip query-string / fragment first
    var clean = name.split("?")[0].split("#")[0];
    var parts = clean.split(".");
    return parts.length > 1 ? parts.pop().toLowerCase() : "";
  }

  function isImageExtension(name) {
    var ext = extensionOf(name);
    return ext !== "" && IMAGE_EXTENSIONS.indexOf(ext) !== -1;
  }

  function isImageFormat(fmt) {
    if (!fmt) return false;
    return IMAGE_FORMATS.indexOf(fmt.toLowerCase()) !== -1;
  }

  /* ---- module ---- */

  return {
    options: {
      existingCoverResourceId: "",
      existingCoverResourceName: "",
      currentResourceId: "",
      currentResourceUrl: "",
      currentResourceFormat: "",
      isCurrentlyCover: false   // true when this resource is already the cover photo
    },

    initialize: function () {
      this._checkbox = this.$("input[type='checkbox']");
      this._hidden  = this.$("input[type='hidden']");
      this._form     = this.el.closest("form");

      // events
      this._checkbox.on("change", $.proxy(this._onCheckboxChange, this));
      this._bindResourceDetection();

      // initial state
      this._updateVisibility();
      this._syncHidden();
    },

    /* ------------------------------------------------
     * Bind listeners that fire whenever the "resource
     * type" might have changed.
     * ------------------------------------------------ */
    _bindResourceDetection: function () {
      var self = this;

      // 1. File-upload <input type="file">
      this._form.on("change", "input[name='upload']", function () {
        self._updateVisibility();
      });

      // 2. URL text field (link mode)
      this._form.on("change input blur keyup", "input[name='url']", function () {
        self._updateVisibility();
      });

      // 3. Format auto-complete field
      this._form.on(
        "change input",
        "input[name='format'], select[name='format']",
        function () { self._updateVisibility(); }
      );

      // 4. "Remove" / "Clear" button in CKAN upload widget
      this._form.on("click", ".btn-remove-url, .btn-remove-upload", function () {
        setTimeout(function () { self._updateVisibility(); }, 150);
      });

      // 5. Upload / Link toggle buttons — re-evaluate after mode switch
      this._form.on("click", ".btn-upload, .btn-link, [data-module='image-upload'] .btn", function () {
        setTimeout(function () { self._updateVisibility(); }, 150);
      });
    },

    /* ------------------------------------------------
     * Detect whether the current resource looks like
     * an image.  Checks in priority order:
     *   file input ➜ URL value ➜ format field ➜
     *   saved resource format/URL (edit mode)
     * ------------------------------------------------ */
    _detectIsImage: function () {
      // 1. Active file upload
      var fileInput = this._form.find("input[name='upload']")[0];
      if (fileInput && fileInput.files && fileInput.files.length > 0) {
        var file = fileInput.files[0];
        if (file.type && file.type.indexOf("image/") === 0) return true;
        if (isImageExtension(file.name)) return true;
        return false;          // file selected but not an image
      }

      // 2. URL field value
      var url = this._form.find("input[name='url']").val();
      if (url) {
        if (isImageExtension(url)) return true;
      }

      // 3. Format field
      var fmt =
        this._form.find("input[name='format']").val() ||
        this._form.find("select[name='format']").val();
      if (fmt && isImageFormat(fmt)) return true;

      // 4. Existing / saved resource metadata (edit mode)
      if (this.options.currentResourceFormat &&
          isImageFormat(this.options.currentResourceFormat)) {
        return true;
      }
      if (this.options.currentResourceUrl &&
          isImageExtension(this.options.currentResourceUrl)) {
        return true;
      }

      return false;
    },

    /* ------------------------------------------------
     * Keep hidden input disabled when checkbox is
     * checked so only ONE value reaches the server.
     * ------------------------------------------------ */
    _syncHidden: function () {
      this._hidden.prop("disabled", this._checkbox.is(":checked"));
    },

    /* ------------------------------------------------
     * Show / hide the checkbox container
     * ------------------------------------------------ */
    _updateVisibility: function () {
      if (this._detectIsImage()) {
        this.el.slideDown(200);
      } else {
        this.el.slideUp(200);
        // clear the tick when hiding so a non-image can never be a cover
        this._checkbox.prop("checked", false);
        this._syncHidden();
      }
    },

    /* ------------------------------------------------
     * Checkbox change handler – prompt when another
     * cover already exists in the dataset
     * ------------------------------------------------ */
    _onCheckboxChange: function () {
      if (!this._checkbox.is(":checked")) {
        this._syncHidden();
        return;
      }

      // If THIS resource was already the cover photo on page load, no confirmation
      // needed — the user is simply re-selecting their own cover.
      if (this.options.isCurrentlyCover) {
        this._syncHidden();
        return;
      }

      var existingId = this.options.existingCoverResourceId;
      var currentId  = this.options.currentResourceId;

      // Only prompt when there is a *different* resource already flagged
      if (existingId && existingId !== currentId) {
        var name = this.options.existingCoverResourceName || "another resource";
        var ok   = confirm(
          'A cover photo is already set ("' + name +
          '"). Replace it with this image?'
        );
        if (!ok) {
          this._checkbox.prop("checked", false);
        }
      }
      this._syncHidden();
    }
  };
});
