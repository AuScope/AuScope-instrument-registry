"""Rendering tests for the ``identifier_url_field`` scheming form snippet.

These tests exercise the Fetch_Button rendering rules on the manual/external
add form (Requirement 1):

* 1.1 - the Fetch_Button is shown while the form is in the External_Flow.
* 1.2 - the Fetch_Button is hidden while the form is not in the External_Flow.
* 1.3 - the Fetch_Button renders identically for Instrument and Platform forms.

The snippet derives the External_Flow from either the ``identifier_source``
request argument or the ``identifier_source`` value in ``data`` (the request
argument takes precedence), so both drivers are covered.
"""

import pytest

import ckan.plugins.toolkit as tk

SNIPPET = "scheming/form_snippets/identifier_url_field.html"

# Markers that uniquely identify the Fetch_Button rendered by the snippet.
FETCH_BTN_CLASS = "pidinst-doi-fetch-btn"
FETCH_BTN_MODULE = 'data-module="doi-resolve-module"'
FETCH_BTN_LABEL = "Fetch metadata"

# The snippet chains scheming/taxonomy actions, so the test app needs the
# plugins those chained actions depend on in addition to pidinst_theme.
TEST_PLUGINS = (
    "taxonomy scheming_datasets scheming_organizations "
    "scheming_groups pidinst_theme"
)


def _field():
    """A minimal scheming field definition for the identifier_url field."""
    return {
        "field_name": "identifier_url",
        "label": "Identifier URL",
        "form_placeholder": "https://doi.org/10.xxxx/yyyy",
    }


def _render(app, *, source_in_data=None, source_in_args=None,
            package_type="instrument"):
    """Render the form snippet for the given identifier_source drivers."""
    data = {"type": package_type}
    if source_in_data is not None:
        data["identifier_source"] = source_in_data

    path = "/"
    if source_in_args is not None:
        path = "/?identifier_source={0}".format(source_in_args)

    with app.flask_app.test_request_context(path):
        return tk.render_snippet(
            SNIPPET, {"field": _field(), "data": data, "errors": {}}
        )


@pytest.mark.ckan_config("ckan.plugins", TEST_PLUGINS)
@pytest.mark.usefixtures("with_plugins")
class TestIdentifierUrlFieldSnippet:
    """Fetch_Button presence/absence and Instrument/Platform equivalence."""

    # --- Requirement 1.1: shown in the External_Flow --------------------- #

    def test_fetch_button_shown_for_external_instrument(self, app):
        html = _render(app, source_in_data="external", package_type="instrument")
        assert FETCH_BTN_CLASS in html
        assert FETCH_BTN_MODULE in html
        assert FETCH_BTN_LABEL in html

    def test_fetch_button_shown_for_external_platform(self, app):
        html = _render(app, source_in_data="external", package_type="platform")
        assert FETCH_BTN_CLASS in html
        assert FETCH_BTN_MODULE in html
        assert FETCH_BTN_LABEL in html

    def test_fetch_button_shown_when_external_comes_from_request_args(self, app):
        # The request argument drives the External_Flow even when data says
        # system, mirroring how the add form is opened with ?identifier_source.
        html = _render(app, source_in_data="system", source_in_args="external")
        assert FETCH_BTN_CLASS in html
        assert FETCH_BTN_MODULE in html

    # --- Requirement 1.2: hidden when not in the External_Flow ----------- #

    def test_fetch_button_hidden_for_system_instrument(self, app):
        html = _render(app, source_in_data="system", package_type="instrument")
        assert FETCH_BTN_CLASS not in html
        assert FETCH_BTN_MODULE not in html
        assert FETCH_BTN_LABEL not in html

    def test_fetch_button_hidden_for_system_platform(self, app):
        html = _render(app, source_in_data="system", package_type="platform")
        assert FETCH_BTN_CLASS not in html
        assert FETCH_BTN_MODULE not in html

    def test_fetch_button_hidden_when_source_defaults_to_system(self, app):
        # No identifier_source supplied at all -> defaults to system -> hidden.
        html = _render(app)
        assert FETCH_BTN_CLASS not in html

    # --- Requirement 1.3: identical for Instrument and Platform ---------- #

    def test_fetch_button_identical_for_instrument_and_platform(self, app):
        instrument_html = _render(
            app, source_in_data="external", package_type="instrument"
        )
        platform_html = _render(
            app, source_in_data="external", package_type="platform"
        )
        assert FETCH_BTN_CLASS in instrument_html
        assert instrument_html == platform_html
