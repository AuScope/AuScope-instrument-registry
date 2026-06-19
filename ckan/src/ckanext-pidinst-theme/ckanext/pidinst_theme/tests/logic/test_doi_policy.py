from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

import ckan.plugins.toolkit as tk
from ckanext.pidinst_theme import doi_policy, helpers
from ckanext.pidinst_theme.logic import action, validators


class _PackagePlugin:
    def create_package_schema(self):
        return {}


class _Package:
    id = 'pkg-1'

    def __init__(self, extras=None, private=True):
        self.extras = extras or {}
        self.private = private


def _next_action(context, data_dict):
    return dict(data_dict)


def _patch_create(monkeypatch):
    monkeypatch.setattr(
        action.lib_plugins,
        'lookup_package_plugin',
        lambda package_type: _PackagePlugin(),
    )
    monkeypatch.setattr(action, 'manage_parent_related_resource', lambda data_dict: None)


def test_normalize_doi_accepts_common_resolver_forms():
    assert doi_policy.normalize_doi('https://doi.org/10.1234/ABC') == '10.1234/ABC'
    assert doi_policy.normalize_doi('doi:10.1234/ABC') == '10.1234/ABC'


def test_identifier_url_helper_splits_system_and_external():
    assert helpers.pidinst_identifier_url({
        'identifier_source': 'system',
        'doi': '10.1234/system',
    }) == 'https://doi.org/10.1234/system'
    assert helpers.pidinst_identifier_url({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/instrument-1',
    }) == 'https://example.org/id/instrument-1'


def test_system_identifier_url_displays_generated_dev_prefix():
    assert helpers.pidinst_identifier_url({
        'identifier_source': 'system',
        'doi': '12.34567/dev-generated',
    }) == 'https://doi.org/12.34567/dev-generated'


def test_stale_external_source_is_displayed_as_manual_record():
    pkg_dict = {
        'doi_source': 'external',
        'doi': '10.1234/test-instrument-002',
    }

    assert helpers.pidinst_is_manual_record(pkg_dict) is True
    assert helpers.pidinst_identifier_url(
        pkg_dict
    ) == 'https://doi.org/10.1234/test-instrument-002'


def test_system_identifier_url_falls_back_to_doi_store(monkeypatch):
    monkeypatch.setattr(
        doi_policy,
        '_system_doi_from_store',
        lambda pkg_dict: '10.1234/from-store',
    )

    assert helpers.pidinst_identifier_url({
        'id': 'pkg-1',
        'identifier_source': 'system',
    }) == 'https://doi.org/10.1234/from-store'


def test_decorate_show_populates_system_doi_from_store(monkeypatch):
    monkeypatch.setattr(
        doi_policy,
        '_system_doi_from_store',
        lambda pkg_dict: '10.1234/from-store',
    )
    pkg_dict = {'id': 'pkg-1', 'identifier_source': 'system'}

    doi_policy.decorate_show(pkg_dict)

    assert pkg_dict['doi'] == '10.1234/from-store'


def test_pidinst_external_identifier_create_stores_identifier_url(monkeypatch):
    _patch_create(monkeypatch)
    data = {
        'type': 'instrument',
        'title': 'Instrument A',
        'identifier_source': 'external',
        'identifier_url': 'https://doi.org/10.1234/test-instrument-001',
    }

    result = action.package_create(_next_action, {}, data)

    assert result['identifier_source'] == 'external'
    assert result['identifier_url'] == 'https://doi.org/10.1234/test-instrument-001'
    assert 'doi' not in result


def test_pidinst_system_identifier_create_strips_submitted_identifiers(monkeypatch):
    _patch_create(monkeypatch)
    data = {
        'type': 'instrument',
        'title': 'Instrument A',
        'identifier_source': 'system',
        'identifier_url': 'https://doi.org/10.1234/should-not-persist',
        'doi': '10.1234/should-not-persist',
        'doi_source': 'external',
        'external_identifier_url': 'https://example.org/stale',
    }

    result = action.package_create(_next_action, {}, data)

    assert result['identifier_source'] == 'system'
    assert 'identifier_url' not in result
    assert 'doi' not in result
    assert 'doi_source' not in result
    assert 'external_identifier_url' not in result


def test_pidinst_create_rejects_invalid_identifier_source(monkeypatch):
    _patch_create(monkeypatch)

    with pytest.raises(tk.ValidationError):
        action.package_create(_next_action, {}, {
            'type': 'instrument',
            'title': 'Instrument A',
            'identifier_source': 'external-system',
        })


def test_pidinst_should_manage_doi_policy_splits_system_and_external():
    assert doi_policy.should_manage_doi({
        'identifier_source': 'system',
        'doi': '10.1234/system',
    }) is True
    assert doi_policy.should_manage_doi({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/instrument',
    }) is False


def test_instrument_and_platform_share_external_identifier_create_logic(monkeypatch):
    _patch_create(monkeypatch)

    for is_platform in ('false', 'true'):
        result = action.package_create(_next_action, {}, {
            'type': 'instrument',
            'title': f'Record {is_platform}',
            'is_platform': is_platform,
            'identifier_source': 'external',
            'identifier_url': 'https://doi.org/10.1234/shared',
        })
        assert result['identifier_url'] == 'https://doi.org/10.1234/shared'
        assert result['identifier_source'] == 'external'
        assert 'doi' not in result


def test_package_patch_preserves_existing_external_identifier(monkeypatch):
    package = _Package({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/original',
    })
    monkeypatch.setattr(action, 'get_package_object', lambda context, data_dict: package)

    result = action.package_patch(_next_action, {}, {'id': 'pkg-1', 'title': 'Updated'})

    assert result['identifier_source'] == 'external'
    assert result['identifier_url'] == 'https://example.org/id/original'
    assert 'doi' not in result


def test_package_patch_rejects_invalid_external_identifier_url(monkeypatch):
    package = _Package({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/original',
    })
    monkeypatch.setattr(action, 'get_package_object', lambda context, data_dict: package)

    with pytest.raises(tk.ValidationError):
        action.package_patch(_next_action, {}, {
            'id': 'pkg-1',
            'identifier_url': 'not-a-url',
        })


def test_package_update_preserves_existing_external_identifier(monkeypatch):
    package = _Package({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/original',
    })
    monkeypatch.setattr(action, 'get_package_object', lambda context, data_dict: package)
    monkeypatch.setattr(action, '_is_doi_published', lambda package: False)
    monkeypatch.setattr(action, 'manage_parent_related_resource', lambda data_dict: None)

    result = action.package_update(_next_action, {}, {
        'id': 'pkg-1',
        'title': 'Updated Instrument',
        'private': 'True',
        'publication_date': '',
    })

    assert result['identifier_source'] == 'external'
    assert result['identifier_url'] == 'https://example.org/id/original'


def test_package_update_external_identifier_ignores_stale_doi_table_state(monkeypatch):
    package = _Package({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/original',
    }, private=False)
    monkeypatch.setattr(action, 'get_package_object', lambda context, data_dict: package)
    monkeypatch.setattr(action, '_is_doi_published', lambda package: True)
    monkeypatch.setattr(action, 'manage_parent_related_resource', lambda data_dict: None)

    result = action.package_update(_next_action, {}, {
        'id': 'pkg-1',
        'title': 'Updated Instrument',
        'private': 'True',
        'publication_date': '',
    })

    assert result['identifier_source'] == 'external'
    assert result['identifier_url'] == 'https://example.org/id/original'
    assert result['private'] == 'True'


def test_identifier_source_cannot_be_changed_after_creation(monkeypatch):
    package = _Package({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/original',
    })
    monkeypatch.setattr(action, 'get_package_object', lambda context, data_dict: package)

    with pytest.raises(tk.ValidationError):
        action.package_patch(_next_action, {}, {
            'id': 'pkg-1',
            'identifier_source': 'system',
        })


def test_pidinst_identifier_url_validator_requires_external_identifier_url():
    data = {('identifier_source',): 'external', ('identifier_url',): ''}
    errors = {}

    validators.pidinst_identifier_url_validator(('identifier_url',), data, errors, {})

    assert ('identifier_url',) in errors


def test_lifecycle_actions_are_hidden_for_external_identifier_records():
    template_dir = Path(__file__).parents[2] / 'templates'
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    env.globals['_'] = lambda value: value

    pkg = SimpleNamespace(
        publication_status='',
        identifier_source='external',
        identifier_url='https://example.org/id/external',
        private=False,
        doi='',
        id='pkg-1',
        name='pkg-1',
    )
    h = SimpleNamespace(
        check_access=lambda *args, **kwargs: True,
        pidinst_is_manual_record=helpers.pidinst_is_manual_record,
    )

    rendered = env.get_template('package/snippets/lifecycle_actions.html').render(
        pkg=pkg,
        h=h,
    )

    assert 'Withdraw' not in rendered
    assert 'Mark as duplicate' not in rendered


def test_external_identifier_withdraw_does_not_deactivate_datacite(monkeypatch):
    package = _Package({
        'identifier_source': 'external',
        'identifier_url': 'https://example.org/id/external',
    }, private=False)
    monkeypatch.setattr(action.tk, 'check_access', lambda *args, **kwargs: None)
    monkeypatch.setattr(action, 'get_package_object', lambda context, data_dict: package)
    monkeypatch.setattr(action, '_is_doi_published', lambda package: True)
    monkeypatch.setattr(action.tk, 'get_action', lambda name: _next_action)

    called = {'deactivate': False}
    monkeypatch.setattr(
        action,
        '_deactivate_doi_on_datacite',
        lambda package_id: called.__setitem__('deactivate', True),
    )

    with pytest.raises(tk.ValidationError):
        action.package_withdraw({}, {
            'id': 'pkg-1',
            'withdrawal_reason': 'External identifier is not managed here.',
        })

    assert called['deactivate'] is False
