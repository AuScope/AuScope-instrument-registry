/**
 * CKAN module to hide IsNewVersionOf relationship from form
 * The relationship is displayed as read-only text and submitted via hidden inputs
 */
ckan.module("related-identifier-readonly", function ($, _) {
    "use strict";

    return {
        initialize: function () {
            console.log("Initializing related-identifier-readonly module");

            // Wait for DOM to be fully loaded
            setTimeout(() => {
                this.hideIsNewVersionOfFormFields();
            }, 1000);

            // Also check after any DOM changes
            const observer = new MutationObserver(() => {
                this.hideIsNewVersionOfFormFields();
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true,
            });
        },

        hideIsNewVersionOfFormFields: function () {
            // Find all related identifier panels/blocks
            $('[id^="related_identifier_obj-"]').each((index, element) => {
                const $block = $(element);

                // Check if this block has relation_type = IsNewVersionOf
                const $relationTypeSelect = $block.find('select[name*="relation_type"]');

                if ($relationTypeSelect.length && $relationTypeSelect.val() === "IsNewVersionOf") {
                    console.log("Hiding IsNewVersionOf form fields at index", index);

                    // Disable all inputs just in case and hide the block
                    $block.find("input, select, textarea, button").prop("disabled", true);

                    // Hide the entire panel/div that contains this block
                    const $panel = $block.closest(".panel");
                    if ($panel.length) {
                        $panel.hide();
                    } else {
                        $block.hide();
                    }

                    // Also hide parent containers
                    $block.parent().hide();
                }
            });

            // Alternative approach: look for the collapse panel by checking select values
            $(".panel-collapse").each((index, panel) => {
                const $panel = $(panel);
                const $relationSelect = $panel.find('select[name$="-relation_type"]');

                if ($relationSelect.length && $relationSelect.val() === "IsNewVersionOf") {
                    console.log("Hiding panel with IsNewVersionOf");
                    $panel.closest(".panel").hide();
                }
            });
        },
    };
});
