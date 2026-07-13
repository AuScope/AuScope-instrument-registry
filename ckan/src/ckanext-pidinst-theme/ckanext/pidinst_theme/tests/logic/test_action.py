"""Tests for action.py."""

import pytest

import ckan.tests.helpers as test_helpers
import ckan.plugins.toolkit as tk

from ckanext.pidinst_theme.doi_resolution.types import (
    FetchedMetadata,
    ResolvedFields,
    ResolveResult,
)
from ckanext.pidinst_theme.logic import action


@pytest.mark.ckan_config("ckan.plugins", "pidinst_theme")
@pytest.mark.usefixtures("with_plugins")
def test_pidinst_theme_get_sum():
    result = test_helpers.call_action(
        "pidinst_theme_get_sum", left=10, right=30)
    assert result["sum"] == 40


def test_doi_resolution_action_returns_contract(monkeypatch):
    captured = {}

    def fake_resolve(identifier, datacite, crossref, mapper, **kwargs):
        captured['identifier'] = identifier
        captured['datacite'] = datacite
        captured['crossref'] = crossref
        return ResolveResult(
            status='ok',
            source='datacite',
            doi='10.1234/example',
            identifier_url='https://doi.org/10.1234/example',
            fetched=FetchedMetadata(
                title='Resolved title',
                provider_metadata={
                    'data': {'attributes': {'titles': [{'title': 'Resolved title'}]}}
                },
                available_unmapped={'subjects': [{'subject': 'Seismology'}]},
            ),
            resolved_fields=ResolvedFields(
                identifier_url='https://doi.org/10.1234/example',
                title='Resolved title',
            ),
        )

    def fake_reconcile(resolved_fields, context):
        captured['reconciled_fields'] = resolved_fields
        return {
            'manufacturer': [],
            'owner': [],
            'funder': [],
            'instrument_type': [],
            'measured_variable': [],
        }

    monkeypatch.setattr(action, 'resolve_doi', fake_resolve)
    monkeypatch.setattr(action.doi_reconciliation, 'reconcile', fake_reconcile)
    monkeypatch.setitem(
        tk.config,
        'ckanext.pidinst_theme.doi_resolution.datacite_api_url',
        'https://datacite.test/dois',
    )
    monkeypatch.setitem(
        tk.config,
        'ckanext.pidinst_theme.doi_resolution.crossref_api_url',
        'https://crossref.test/works',
    )
    monkeypatch.setitem(
        tk.config, 'ckanext.pidinst_theme.doi_resolution.timeout', '2.5'
    )

    result = action.pidinst_resolve_doi_metadata(
        {'ignore_auth': True}, {'identifier': '10.1234/example'}
    )

    assert captured['identifier'] == '10.1234/example'
    assert captured['datacite'].api_url == 'https://datacite.test/dois'
    assert captured['crossref'].api_url == 'https://crossref.test/works'
    assert captured['datacite'].timeout == 2.5
    assert result['status'] == 'ok'
    # resolved_fields always carries the backward-compatible keys plus the
    # advanced composite keys and the Tier-3 suggestion-only keys.
    assert {'identifier_url', 'title', 'notes'}.issubset(result['resolved_fields'])
    for advanced_key in (
        'instrument_classification', 'alternate_identifier_obj', 'date', 'model',
        'related_identifier_obj', 'instrument_type_suggestions',
        'owner_suggestions', 'manufacturer_suggestions', 'funder_suggestions',
        'party_identifier_suggestions', 'taxonomy_suggestions',
        'geo_location_suggestions', 'publication_metadata_suggestions',
    ):
        assert advanced_key in result['resolved_fields']
    assert result['provider_metadata']['data']['attributes']['titles'] == [
        {'title': 'Resolved title'}
    ]
    assert result['available_unmapped'] == {
        'subjects': [{'subject': 'Seismology'}]
    }
    assert result['matched_suggestions'] == {
        'manufacturer': [],
        'owner': [],
        'funder': [],
        'instrument_type': [],
        'measured_variable': [],
    }
    assert captured['reconciled_fields']['title'] == 'Resolved title'


def test_doi_resolution_action_uses_test_datacite_api_for_test_resolver_url(
    monkeypatch,
):
    captured = {}

    def fake_resolve(identifier, datacite, crossref, mapper, **kwargs):
        captured['identifier'] = identifier
        captured['datacite'] = datacite
        return ResolveResult(status='not_found')

    monkeypatch.setattr(action, 'resolve_doi', fake_resolve)
    monkeypatch.setitem(
        tk.config,
        'ckanext.pidinst_theme.doi_resolution.datacite_api_url',
        'https://datacite.example/dois',
    )
    monkeypatch.setitem(
        tk.config,
        'ckanext.pidinst_theme.doi_resolution.datacite_test_api_url',
        'https://datacite-test.example/dois',
    )

    result = action.pidinst_resolve_doi_metadata(
        {'ignore_auth': True},
        {'identifier': 'https://handle.test.datacite.org/10.83627/yst9hxwy'},
    )

    assert captured['identifier'] == (
        'https://handle.test.datacite.org/10.83627/yst9hxwy'
    )
    assert captured['datacite'].api_url == 'https://datacite-test.example/dois'
    assert result['status'] == 'not_found'


def test_doi_resolution_action_rejects_missing_identifier():
    with pytest.raises(tk.ValidationError):
        action.pidinst_resolve_doi_metadata({'ignore_auth': True}, {})


class _FakePackage:
    """Minimal stand-in for the package ORM object used by the write hooks."""

    def __init__(self, private=True, extras=None):
        self.id = 'pkg-1'
        self.private = private
        self.extras = extras or {}


def _call_package_update(monkeypatch, package, data_dict):
    monkeypatch.setattr(action, 'get_package_object', lambda context, d: package)
    monkeypatch.setattr(action, '_is_doi_published', lambda pkg: False)
    return action.package_update(
        lambda context, d: d, {}, dict(data_dict, id=package.id),
    )


def test_package_update_stamps_publication_date_when_private_is_a_bool(monkeypatch):
    """The API sends private as a real bool; the UI form sends 'False'."""
    result = _call_package_update(
        monkeypatch,
        _FakePackage(private=True),
        {'title': 'Batch instrument', 'private': False},
    )
    assert result['publication_date']


def test_package_update_stamps_publication_date_when_private_is_a_string(monkeypatch):
    result = _call_package_update(
        monkeypatch,
        _FakePackage(private=True),
        {'title': 'Form instrument', 'private': 'False'},
    )
    assert result['publication_date']


def test_package_update_backfills_public_record_missing_publication_date(monkeypatch):
    """Re-running the update over an already-public record repairs a missing date."""
    result = _call_package_update(
        monkeypatch,
        _FakePackage(private=False),
        {'title': 'Already public', 'private': False},
    )
    assert result['publication_date']


def test_package_update_preserves_stored_publication_date(monkeypatch):
    """package_update replaces the record, so an omitted date must not be blanked."""
    result = _call_package_update(
        monkeypatch,
        _FakePackage(private=False, extras={'publication_date': '2025-03-04'}),
        {'title': 'Already public', 'private': False},
    )
    assert result['publication_date'] == '2025-03-04'


def test_package_update_does_not_stamp_private_record(monkeypatch):
    result = _call_package_update(
        monkeypatch,
        _FakePackage(private=True),
        {'title': 'Still private', 'private': True},
    )
    assert not result.get('publication_date')


def test_package_create_stamps_publication_date_when_private_is_a_bool(monkeypatch):
    class _FakePlugin:
        def create_package_schema(self):
            return {}

    monkeypatch.setattr(
        action.lib_plugins, 'lookup_package_plugin', lambda t: _FakePlugin(),
    )
    result = action.package_create(
        lambda context, d: d,
        {},
        {'title': 'Batch instrument', 'type': 'instrument', 'private': False},
    )
    assert result['publication_date']
