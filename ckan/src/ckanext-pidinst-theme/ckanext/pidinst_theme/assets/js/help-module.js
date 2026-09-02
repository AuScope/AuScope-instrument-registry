/* User Guide page behaviour.
 *
 * Attach to the .pidinst-help wrapper via data-module="help-module". Provides:
 *   - an "on this page" list of the current page's headings, injected into the
 *     sidebar under the active section, with scroll-spy highlighting;
 *   - click-to-enlarge for screenshots.
 */
"use strict";

ckan.module("help-module", function ($) {
  return {
    initialize: function () {
      this._buildSubNav();
      this._bindLightbox();
    },

    /* Build the sidebar sub-list from this page's section headings. */
    _buildSubNav: function () {
      var $activeItem = $(".help-nav-item.is-active");
      if (!$activeItem.length) return;

      var headings = this.el
        .find(".help-section > h2[id], .help-section[id] > h2")
        .toArray();
      if (headings.length < 2) return;

      var $list = $('<ol class="help-nav-sub"></ol>');
      var targets = [];

      headings.forEach(function (heading) {
        var $heading = $(heading);
        // Prefer the heading's own id, else fall back to its section's.
        var id = heading.id || $heading.closest(".help-section").attr("id");
        if (!id) return;
        if (!heading.id) heading.id = id;

        var $link = $("<a></a>")
          .attr("href", "#" + id)
          .text($heading.text().trim());

        $list.append($("<li></li>").append($link));
        targets.push({ id: id, el: heading, link: $link });
      });

      if (!targets.length) return;
      $activeItem.append($list);

      this._spy(targets);
    },

    /* Highlight the sub-nav entry for whichever heading is currently on screen. */
    _spy: function (targets) {
      if (!("IntersectionObserver" in window)) return;

      var visible = {};

      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            visible[entry.target.id] = entry.isIntersecting;
          });

          var current = null;
          for (var i = 0; i < targets.length; i++) {
            if (visible[targets[i].id]) {
              current = targets[i];
              break;
            }
          }

          targets.forEach(function (t) {
            t.link.toggleClass("is-current", current !== null && t.id === current.id);
          });
        },
        // Bias the active band toward the top of the viewport.
        { rootMargin: "-80px 0px -70% 0px", threshold: 0 }
      );

      targets.forEach(function (t) {
        observer.observe(t.el);
      });

      this._observer = observer;
    },

    /* Click (or Enter/Space) a figure to view it full size. */
    _bindLightbox: function () {
      var self = this;

      this.el.on("click", "[data-help-zoom]", function (event) {
        event.preventDefault();
        var img = $(this).find("img")[0];
        if (img) self._openLightbox(img);
      });
    },

    _openLightbox: function (img) {
      var self = this;

      var $overlay = $('<div class="help-lightbox" role="dialog" aria-modal="true"></div>');
      var $close = $('<button type="button" class="help-lightbox-close"></button>')
        .attr("aria-label", this.options.closeLabel || "Close")
        .append('<i class="fa-solid fa-xmark" aria-hidden="true"></i>');
      var $full = $("<img>").attr("src", img.src).attr("alt", img.alt);

      $overlay.append($close).append($full).appendTo(document.body);

      // Remember focus so it can be restored when the overlay closes.
      var previouslyFocused = document.activeElement;
      $close.trigger("focus");

      function close() {
        $overlay.remove();
        $(document).off("keydown.helpLightbox");
        if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
      }

      $close.on("click", close);
      $overlay.on("click", function (event) {
        // Click the backdrop (not the image) to dismiss.
        if (event.target === $overlay[0]) close();
      });
      $(document).on("keydown.helpLightbox", function (event) {
        if (event.key === "Escape") close();
      });

      self._closeLightbox = close;
    },

    teardown: function () {
      if (this._observer) this._observer.disconnect();
      if (this._closeLightbox) this._closeLightbox();
      this.el.off("click", "[data-help-zoom]");
    },
  };
});
