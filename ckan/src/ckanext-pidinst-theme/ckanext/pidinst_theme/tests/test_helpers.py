"""Tests for helpers.py."""

from pathlib import Path

import ckanext.pidinst_theme.helpers as helpers


def test_pidinst_theme_hello():
    assert helpers.pidinst_theme_hello() == "Hello, pidinst_theme!"


BASE_PACKAGE = {
    "title": "LEMI-120 magnetic induction coil sensor",
}
BASE_CITATION = (
    "Laboratory of Electromagnetic Innovations (LEMI) (2026): "
    "LEMI-120 magnetic induction coil sensor. AuScope. "
    "https://doi.org/10.82388/wwo07kxn"
)


def _package_with_identifiers(*identifiers):
    return dict(BASE_PACKAGE, alternate_identifier_obj=list(identifiers))


def test_format_citation_adds_serial_number():
    package = _package_with_identifiers({
        "alternate_identifier_type": "SerialNumber",
        "alternate_identifier": "112",
    })

    assert helpers.pidinst_format_citation(package, BASE_CITATION) == (
        "Laboratory of Electromagnetic Innovations (LEMI) (2026): "
        "LEMI-120 magnetic induction coil sensor (Serial No. 112). AuScope. "
        "https://doi.org/10.82388/wwo07kxn"
    )


def test_format_citation_prefers_serial_number():
    package = _package_with_identifiers(
        {
            "alternate_identifier_type": "InventoryNumber",
            "alternate_identifier": "INV-9",
        },
        {
            "alternate_identifier_type": "SerialNumber",
            "alternate_identifier": "112",
        },
    )

    citation = helpers.pidinst_format_citation(package, BASE_CITATION)
    assert "(Serial No. 112)" in citation
    assert "INV-9" not in citation


def test_format_citation_adds_inventory_number():
    package = _package_with_identifiers({
        "alternate_identifier_type": "InventoryNumber",
        "alternate_identifier": "XYZ",
    })

    assert "(Inventory No. XYZ)" in helpers.pidinst_format_citation(
        package, BASE_CITATION
    )


def test_format_citation_uses_other_identifier_description():
    package = _package_with_identifiers({
        "alternate_identifier_type": "Other",
        "alternate_identifier_name": "Asset tag",
        "alternate_identifier": "A-42",
    })

    assert "(Asset tag A-42)" in helpers.pidinst_format_citation(
        package, BASE_CITATION
    )

    unnamed_package = _package_with_identifiers({
        "alternate_identifier_type": "Other",
        "alternate_identifier": "A-43",
    })
    assert "(Identifier A-43)" in helpers.pidinst_format_citation(
        unnamed_package, BASE_CITATION
    )


def test_format_citation_without_identifier_is_unchanged():
    assert helpers.pidinst_format_citation(BASE_PACKAGE, BASE_CITATION) == BASE_CITATION


def test_format_citation_is_idempotent():
    package = _package_with_identifiers({
        "alternate_identifier_type": "SerialNumber",
        "alternate_identifier": "112",
    })
    formatted = helpers.pidinst_format_citation(package, BASE_CITATION)

    assert helpers.pidinst_format_citation(package, formatted) == formatted


def test_format_citation_tolerates_malformed_composite_values():
    for value in (
        None,
        "not-json",
        [None, "bad", {}],
        {"unexpected": "value"},
        [{"alternate_identifier": {"nested": "bad"}}],
        [{
            "alternate_identifier": "A-42",
            "alternate_identifier_type": ["Other"],
        }],
    ):
        package = dict(BASE_PACKAGE, alternate_identifier_obj=value)
        result = helpers.pidinst_format_citation(package, BASE_CITATION)
        assert isinstance(result, str)


def test_format_citation_preserves_package_and_resource_links():
    package = _package_with_identifiers({
        "alternate_identifier_type": "SerialNumber",
        "alternate_identifier": "112",
    })
    resource_url = "https://example.test/instrument/example/resource/abc"
    citation = BASE_CITATION + " " + resource_url

    formatted = helpers.pidinst_format_citation(package, citation)
    assert "https://doi.org/10.82388/wwo07kxn" in formatted
    assert formatted.endswith(resource_url)

    templates = Path(helpers.__file__).parent / "templates" / "doi" / "snippets"
    package_template = (templates / "package_citation.html").read_text()
    resource_template = (templates / "resource_citation.html").read_text()
    assert "'https://doi.org/' + pkg_dict['doi']" in package_template
    assert "h.url_for('instrument_resource.read'" in resource_template


def test_format_citation_escapes_identifier_html_for_markdown():
    package = _package_with_identifiers({
        "alternate_identifier_type": "SerialNumber",
        "alternate_identifier": "<img src=x onerror=alert(1)>",
    })

    formatted = helpers.pidinst_format_citation(package, BASE_CITATION, True)
    assert type(formatted) is str
    assert "<img" not in formatted
    assert "&lt;img src=x onerror=alert(1)&gt;" in formatted
