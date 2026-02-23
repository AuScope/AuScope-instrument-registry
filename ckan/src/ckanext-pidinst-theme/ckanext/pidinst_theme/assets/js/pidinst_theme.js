ckan.module("pidinst_theme", function ($, _) {
  "use strict";

  function ensureLoader() {
    var $loader = $("#pidinst-loader");
    if (!$loader.length) return null;
    return $loader;
  }

  function bindResourceFormLoader() {
    var $form = $("#resource-edit");
    if (!$form.length) return;

    var $loader = ensureLoader();
    if (!$loader) return;

    $form.on("submit", function () {
      $loader.addClass("is-visible");
    });

    // Hide it when page is fully loaded (eg after server validation reload)
    $(window).on("load", function () {
      $loader.removeClass("is-visible");
    });
  }

  return {
    initialize: function () {
      console.log("Initialized!");
      bindResourceFormLoader();
    },
  };
});