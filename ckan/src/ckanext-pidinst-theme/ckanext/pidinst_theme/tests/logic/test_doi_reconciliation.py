from ckanext.pidinst_theme.logic import doi_reconciliation


def test_reconcile_matches_existing_records_by_exact_identifier(monkeypatch):
    actions_called = []

    def fake_get_action(name):
        actions_called.append(name)

        def group_list(context, data_dict):
            assert data_dict == {'type': 'party'}
            return ['maker-party', 'owner-party', 'other-maker']

        def group_show(context, data_dict):
            parties = {
                'maker-party': {
                    'id': 'maker-id',
                    'name': 'maker-party',
                    'title': 'Maker Party',
                    'party_role': ['Manufacturer'],
                    'party_identifier_type': 'ROR',
                    'party_identifier_ror': 'https://ror.org/abc123',
                },
                'owner-party': {
                    'id': 'owner-id',
                    'name': 'owner-party',
                    'title': 'Owner Party',
                    'party_role': ['Owner'],
                    'party_identifier_type': 'ROR',
                    'party_identifier_ror': 'https://ror.org/own123',
                },
                'other-maker': {
                    'id': 'other-maker-id',
                    'name': 'other-maker',
                    'title': 'Other Maker',
                    'party_role': ['Manufacturer'],
                    'party_identifier_type': 'ROR',
                    'party_identifier_ror': 'https://ror.org/other',
                },
            }
            return parties[data_dict['id']]

        def taxonomy_term_list(context, data_dict):
            if data_dict['id'] == 'instruments':
                return [{
                    'id': 'term-id',
                    'label': 'Mass spectrometer',
                    'uri': 'https://example.test/term/mass',
                }]
            if data_dict['id'] == 'measured-variables':
                return [{
                    'id': 'variable-id',
                    'label': 'Helium',
                    'uri': 'https://example.test/term/helium',
                }]
            return []

        return {
            'group_list': group_list,
            'group_show': group_show,
            'taxonomy_term_list': taxonomy_term_list,
        }[name]

    monkeypatch.setattr(doi_reconciliation.tk, 'get_action', fake_get_action)
    monkeypatch.setattr(
        doi_reconciliation,
        'get_taxonomy_name',
        lambda key: {
            'instrument': 'instruments',
            'platform': 'platforms',
            'measured_variable': 'measured-variables',
        }[key],
    )

    result = doi_reconciliation.reconcile({
        'manufacturer_suggestions': [{
            'name': 'Maker Party',
            'ror': 'https://ror.org/abc123',
        }],
        'owner_suggestions': [{
            'name': 'Name-only Owner',
            'ror': '',
        }],
        'funder_suggestions': [],
        'instrument_type_suggestions': [{
            'instrument_type_name': 'Mass spectrometer',
            'instrument_type_identifier': 'https://example.test/term/mass',
        }],
        'taxonomy_suggestions': [{
            'subject': 'Helium',
            'value_uri': 'https://example.test/term/helium',
        }],
    }, {})

    assert set(result) == {
        'manufacturer',
        'owner',
        'funder',
        'instrument_type',
        'measured_variable',
    }
    assert result['manufacturer'][0]['match_status'] == 'exact_unique'
    assert result['manufacturer'][0]['apply_allowed'] is True
    assert result['manufacturer'][0]['matched_local_id'] == 'maker-party'
    assert result['manufacturer'][0]['matched_local_record_id'] == 'maker-id'
    assert result['manufacturer'][0]['matched_local_name'] == 'maker-party'
    assert result['owner'][0]['match_status'] == 'no_match'
    assert result['owner'][0]['apply_allowed'] is False
    assert result['instrument_type'][0]['matched_local_type'] == 'taxonomy_term'
    assert result['instrument_type'][0]['match_status'] == 'exact_unique'
    assert result['measured_variable'][0]['matched_local_id'] == (
        'https://example.test/term/helium'
    )
    assert result['measured_variable'][0]['matched_local_record_id'] == 'variable-id'
    assert 'group_create' not in actions_called
    assert 'group_update' not in actions_called
    assert 'package_update' not in actions_called


def test_match_status_marks_duplicate_exact_identifier_as_ambiguous():
    suggestions = [{
        'name': 'Duplicated Maker',
        'ror': 'https://ror.org/dup',
    }]
    parties = [
        {
            'id': 'one',
            'name': 'one',
            'title': 'One',
            'party_role': ['Manufacturer'],
            'party_identifier_ror': 'https://ror.org/dup',
        },
        {
            'id': 'two',
            'name': 'two',
            'title': 'Two',
            'party_role': ['Manufacturer'],
            'party_identifier_ror': 'https://ror.org/dup',
        },
    ]

    result = doi_reconciliation.match_manufacturer(suggestions, parties)

    assert result[0]['match_status'] == 'ambiguous'
    assert result[0]['apply_allowed'] is False
    assert result[0]['matched_local_id'] == ''
