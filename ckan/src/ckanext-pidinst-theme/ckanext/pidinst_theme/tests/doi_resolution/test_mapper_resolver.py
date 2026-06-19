from pathlib import Path

from ckanext.pidinst_theme.doi_resolution.mapper import (
    Mapper,
    extract_datacite_alternate_identifiers,
    extract_datacite_funder_suggestions,
    extract_datacite_geo_location_suggestions,
    extract_datacite_instrument_type_suggestions,
    extract_datacite_lifecycle_dates,
    extract_datacite_manufacturer_suggestions,
    extract_datacite_model_descriptions,
    extract_datacite_owner_suggestions,
    extract_datacite_party_identifier_suggestions,
    extract_datacite_publication_metadata_suggestions,
    extract_datacite_related_identifiers,
    extract_datacite_resource_type_classification,
    extract_datacite_taxonomy_suggestions,
)
from ckanext.pidinst_theme.doi_resolution.providers import (
    ProviderLookup,
    ProviderResponse,
)
from ckanext.pidinst_theme.doi_resolution.resolver import resolve
from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord, ResolvedFields


class StubClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def lookup(self, bare_doi):
        self.calls.append(bare_doi)
        return self.response


def _datacite_sample_attributes(**overrides):
    attributes = {
        'titles': [{'title': 'Instrument title'}],
        'descriptions': [
            {'descriptionType': 'Abstract', 'description': 'Instrument description'},
            {
                'descriptionType': 'TechnicalInfo',
                'description': 'Model: GeoProbe 2000 (URL: https://example.test/model)',
            },
        ],
        'creators': [{'name': 'A. Researcher'}],
        'contributors': [{'name': 'A. Manufacturer', 'contributorType': 'HostingInstitution'}],
        'publisher': 'Example Publisher',
        'publicationYear': 2026,
        'types': {
            'resourceType': 'Geochemistry',
            'resourceTypeGeneral': 'Instrument',
        },
        'identifiers': [
            {'identifier': '10.1234/example', 'identifierType': 'DOI'},
            {'identifier': 'DUPLICATE-1', 'identifierType': 'SerialNumber'},
        ],
        'alternateIdentifiers': [
            {
                'alternateIdentifier': 'INV-123',
                'alternateIdentifierType': 'InventoryNumber',
            },
            {
                'alternateIdentifier': 'SER-456',
                'alternateIdentifierType': 'SerialNumber',
            },
            {
                'alternateIdentifier': 'LEGACY-789',
                'alternateIdentifierType': 'LegacyCode',
            },
            {
                'alternateIdentifier': 'DUPLICATE-1',
                'alternateIdentifierType': 'SerialNumber',
            },
        ],
        'dates': [
            {
                'date': '2012',
                'dateType': 'Other',
                'dateInformation': 'Commissioned',
            },
            {'date': '2026-01-01', 'dateType': 'Created'},
            {'date': '2026-02-01', 'dateType': 'Updated'},
            {'date': '2026-03-01', 'dateType': 'Issued'},
        ],
        'relatedIdentifiers': [
            {
                'relatedIdentifier': '10.9999/manual',
                'relatedIdentifierType': 'DOI',
                'relationType': 'IsDescribedBy',
            }
        ],
        'fundingReferences': [{'funderName': 'Example Funder'}],
    }
    attributes.update(overrides)
    return attributes


def _datacite_record(attributes=None):
    payload = {'data': {'attributes': attributes or _datacite_sample_attributes()}}
    return ProviderRecord(
        source='datacite',
        title='Instrument title',
        description='Instrument description',
        creators=['A. Researcher'],
        publisher='Example Publisher',
        publication_year='2026',
        provider_metadata=payload,
    )


def test_mapper_limits_resolved_fields_and_warns_for_missing_metadata():
    fetched, resolved, warnings = Mapper().map(
        ProviderRecord(
            source='datacite',
            title='Title',
            publisher='Provider Publisher',
            publication_year='2026',
            provider_metadata={
                'data': {
                    'attributes': {
                        'publisher': 'Provider Publisher',
                        'publicationYear': 2026,
                        'types': {'resourceTypeGeneral': 'Dataset'},
                    }
                }
            },
        ),
        'https://doi.org/10.1234/example',
    )

    assert fetched.title == 'Title'
    resolved_dict = resolved.to_dict()
    assert resolved_dict['identifier_url'] == 'https://doi.org/10.1234/example'
    assert resolved_dict['title'] == 'Title'
    assert resolved_dict['notes'] == ''
    assert len(warnings) == 2
    assert all(
        forbidden not in resolved.to_dict()
        for forbidden in ('owner', 'manufacturer', 'funder', 'taxonomy')
    )
    assert 'publisher' not in resolved.to_dict()
    assert 'publication_date' not in resolved.to_dict()
    assert fetched.provider_metadata['data']['attributes']['types'] == {
        'resourceTypeGeneral': 'Dataset'
    }
    assert fetched.available_unmapped['publisher'] == 'Provider Publisher'
    assert fetched.available_unmapped['publication_year'] == '2026'
    assert fetched.available_unmapped['resource_type'] == {
        'resourceTypeGeneral': 'Dataset'
    }


def test_datacite_resource_type_classification_helper_exact_match_only():
    assert extract_datacite_resource_type_classification(
        _datacite_sample_attributes()
    ) == 'Geochemistry'
    assert extract_datacite_resource_type_classification(
        _datacite_sample_attributes(types={'resourceType': 'geochemistry'})
    ) == ''


def test_datacite_alternate_identifier_helper_maps_types_and_deduplicates():
    """alternateIdentifiers drive the output; values in both arrays produce one row."""
    # The sample has:
    #   identifiers: [DOI, DUPLICATE-1 (SerialNumber)]
    #   alternateIdentifiers: [INV-123, SER-456, LEGACY-789, DUPLICATE-1]
    # Expected: INV-123, SER-456, LEGACY-789 all appear; DUPLICATE-1 appears once.
    result = extract_datacite_alternate_identifiers(_datacite_sample_attributes())
    assert {r['alternate_identifier'] for r in result} == {
        'INV-123', 'SER-456', 'LEGACY-789', 'DUPLICATE-1'
    }
    types_by_value = {r['alternate_identifier']: r['alternate_identifier_type'] for r in result}
    assert types_by_value['INV-123'] == 'InventoryNumber'
    assert types_by_value['SER-456'] == 'SerialNumber'
    assert types_by_value['LEGACY-789'] == 'Other'
    assert types_by_value['DUPLICATE-1'] == 'SerialNumber'


def test_inventory_number_in_both_arrays_produces_exactly_one_row():
    """Bug-fix regression: InventoryNumber in identifiers AND alternateIdentifiers → one row."""
    attributes = _datacite_sample_attributes(
        identifiers=[
            {'identifier': '10.83627/5fpt3jtq', 'identifierType': 'DOI'},
            {'identifier': 'ARGUS VI JdLC-WAAIF', 'identifierType': 'InventoryNumber'},
        ],
        alternateIdentifiers=[
            {
                'alternateIdentifier': 'ARGUS VI JdLC-WAAIF',
                'alternateIdentifierType': 'InventoryNumber',
            },
        ],
    )
    result = extract_datacite_alternate_identifiers(attributes)
    # Exactly one row for the InventoryNumber
    inv_rows = [r for r in result if r.get('alternate_identifier') == 'ARGUS VI JdLC-WAAIF']
    assert len(inv_rows) == 1
    assert inv_rows[0]['alternate_identifier_type'] == 'InventoryNumber'


def test_datacite_alternate_identifier_missing_type_maps_to_other_without_name():
    """A non-empty value with no type maps to Other with no alternate_identifier_name."""
    result = extract_datacite_alternate_identifiers(
        _datacite_sample_attributes(
            identifiers=[],
            alternateIdentifiers=[
                {
                    'alternateIdentifier': 'MISSING-TYPE',
                    'alternateIdentifierType': '',
                }
            ]
        )
    )
    assert result == [
        {
            'alternate_identifier_type': 'Other',
            'alternate_identifier': 'MISSING-TYPE',
        }
    ]
    # No supplementary name when the original type was absent.
    assert 'alternate_identifier_name' not in result[0]


def test_datacite_alternate_identifier_skips_entries_without_value():
    """Entries with no usable identifier value are skipped entirely."""
    result = extract_datacite_alternate_identifiers(
        _datacite_sample_attributes(
            identifiers=[],
            alternateIdentifiers=[
                {'alternateIdentifier': '', 'alternateIdentifierType': 'SerialNumber'},
                {'alternateIdentifierType': 'InventoryNumber'},
            ]
        )
    )
    assert result == []


def test_datacite_alternate_identifier_prefers_more_specific_type():
    """When a value appears with different types, the most specific wins."""
    # Same value 'XYZ' present as empty-type in alternateIdentifiers and as
    # SerialNumber in identifiers -> SerialNumber wins, one row only.
    result = extract_datacite_alternate_identifiers(
        _datacite_sample_attributes(
            identifiers=[
                {'identifier': '10.1234/example', 'identifierType': 'DOI'},
                {'identifier': 'XYZ', 'identifierType': 'SerialNumber'},
            ],
            alternateIdentifiers=[
                {'alternateIdentifier': 'XYZ', 'alternateIdentifierType': ''},
            ]
        )
    )
    xyz_rows = [r for r in result if r['alternate_identifier'] == 'XYZ']
    assert len(xyz_rows) == 1
    assert xyz_rows[0]['alternate_identifier_type'] == 'SerialNumber'


def test_datacite_lifecycle_date_helper_maps_only_supported_lifecycle_dates():
    mapped, unmapped = extract_datacite_lifecycle_dates(_datacite_sample_attributes())

    assert mapped == [{'date_value': '2012', 'date_type': 'Commissioned'}]
    assert unmapped == []

    mapped, unmapped = extract_datacite_lifecycle_dates(
        _datacite_sample_attributes(
            dates=[
                {
                    'date': 'not-a-date',
                    'dateType': 'Other',
                    'dateInformation': 'Decommissioned',
                },
                {'date': '2026-01-01', 'dateType': 'Created'},
            ]
        )
    )
    assert mapped == []
    assert unmapped == [
        {
            'date': 'not-a-date',
            'dateType': 'Other',
            'dateInformation': 'Decommissioned',
        }
    ]


def test_datacite_created_updated_issued_dates_are_ignored():
    mapped, unmapped = extract_datacite_lifecycle_dates(
        _datacite_sample_attributes(
            dates=[
                {'date': '2026-01-01', 'dateType': 'Created'},
                {'date': '2026-02-01', 'dateType': 'Updated'},
                {'date': '2026-03-01', 'dateType': 'Issued'},
            ]
        )
    )

    assert mapped == []
    assert unmapped == []


def test_datacite_model_description_helper_parses_only_known_convention():
    mapped, unmapped = extract_datacite_model_descriptions(
        _datacite_sample_attributes()
    )

    assert mapped == [
        {
            'model_name': 'GeoProbe 2000',
            'model_identifier': 'https://example.test/model',
            'model_identifier_type': 'URL',
        }
    ]
    assert unmapped == []

    mapped, unmapped = extract_datacite_model_descriptions(
        _datacite_sample_attributes(
            descriptions=[
                {
                    'descriptionType': 'TechnicalInfo',
                    'description': 'GeoProbe 2000 with support URL',
                }
            ]
        )
    )
    assert mapped == []
    assert unmapped == [
        {
            'descriptionType': 'TechnicalInfo',
            'description': 'GeoProbe 2000 with support URL',
        }
    ]


def test_instrument_type_technical_info_does_not_produce_model_warnings():
    """Bug-fix regression: 'Instrument Type:' TechnicalInfo must NOT add to model unmapped."""
    from ckanext.pidinst_theme.doi_resolution.mapper import (
        extract_datacite_instrument_type_suggestions,
    )

    descriptions_with_inst_type = [
        {
            'descriptionType': 'TechnicalInfo',
            'description': 'Instrument Type: MASS SPECTROMETERS (URI: http://vocab.nerc.ac.uk/collection/L05/current/MSS/)',
        },
        {
            'descriptionType': 'TechnicalInfo',
            'description': 'Instrument Type: Multi collector noble gas mass spectrometer (URI: https://www.wikidata.org/wiki/Q51687050)',
        },
        {
            'descriptionType': 'TechnicalInfo',
            'description': 'Model: Argus VI Noble Gas Mass Spectrometer (URL: https://documents.thermofisher.com/model.pdf)',
        },
    ]
    attributes = _datacite_sample_attributes(descriptions=descriptions_with_inst_type)

    mapped, unmapped = extract_datacite_model_descriptions(attributes)
    # Only the Model entry maps; Instrument Type entries do NOT appear in unmapped
    assert len(mapped) == 1
    assert mapped[0]['model_name'] == 'Argus VI Noble Gas Mass Spectrometer'
    assert unmapped == [], (
        'Instrument Type TechnicalInfo entries must not appear in model unmapped list'
    )

    # Instrument type suggestions parse separately
    suggestions = extract_datacite_instrument_type_suggestions(attributes)
    assert len(suggestions) == 2
    names = {s['instrument_type_name'] for s in suggestions}
    assert 'MASS SPECTROMETERS' in names
    assert 'Multi collector noble gas mass spectrometer' in names
    for s in suggestions:
        assert s.get('instrument_type_identifier_type') == 'URL'


def test_instrument_type_suggestions_are_not_auto_applied(monkeypatch):
    """instrument_type_suggestions must NOT appear in the auto-apply RESOLVED_FIELDS table."""
    # Import the JS module constants via the source file
    import os, json
    js_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'assets', 'js', 'doi-resolve-module.js'
    )
    js_src = open(js_path).read()
    # RESOLVED_FIELDS should not list instrument_type_suggestions as an auto-applied key
    assert 'instrument_type_suggestions' not in js_src.split('RESOLVED_FIELDS')[1].split('];')[0], (
        'instrument_type_suggestions must NOT be in the RESOLVED_FIELDS auto-apply table'
    )


def test_datacite_related_identifier_helper_preserves_safe_fields():
    assert extract_datacite_related_identifiers(_datacite_sample_attributes()) == [
        {
            'related_identifier': '10.9999/manual',
            'related_identifier_type': 'DOI',
            'relation_type': 'IsDescribedBy',
        }
    ]


def test_datacite_related_identifier_helper_requires_all_parts():
    assert extract_datacite_related_identifiers(
        _datacite_sample_attributes(
            relatedIdentifiers=[
                {
                    'relatedIdentifier': '10.9999/manual',
                    'relatedIdentifierType': 'DOI',
                },
                {
                    'relatedIdentifierType': 'URL',
                    'relationType': 'IsDescribedBy',
                },
            ]
        )
    ) == []


def test_resolved_fields_to_dict_keeps_backward_compatible_keys():
    resolved = ResolvedFields(
        identifier_url='https://doi.org/10.1234/example',
        title='Instrument title',
        notes='Instrument description',
        instrument_classification='Geochemistry',
        alternate_identifier_obj=[
            {
                'alternate_identifier_type': 'InventoryNumber',
                'alternate_identifier': 'INV-123',
            }
        ],
        date=[{'date_value': '2012', 'date_type': 'Commissioned'}],
        model=[{'model_name': 'GeoProbe 2000'}],
        related_identifier_obj=[
            {
                'related_identifier': '10.9999/manual',
                'related_identifier_type': 'DOI',
                'relation_type': 'IsDescribedBy',
            }
        ],
        instrument_type_suggestions=[
            {'instrument_type_name': 'MASS SPECTROMETERS'},
        ],
    )

    result = resolved.to_dict()
    # Backward-compatible keys must always be present
    assert 'identifier_url' in result
    assert 'title' in result
    assert 'notes' in result
    # Advanced keys must be present
    assert 'instrument_classification' in result
    assert 'alternate_identifier_obj' in result
    assert 'date' in result
    assert 'model' in result
    assert 'related_identifier_obj' in result
    assert 'instrument_type_suggestions' in result
    # Values correct
    assert result['identifier_url'] == 'https://doi.org/10.1234/example'
    assert result['instrument_classification'] == 'Geochemistry'
    assert result['instrument_type_suggestions'] == [{'instrument_type_name': 'MASS SPECTROMETERS'}]
    # Forbidden keys absent
    assert 'owner' not in result
    assert 'manufacturer' not in result
    assert 'funder_party_id' not in result


def test_datacite_sample_maps_safe_fields_and_keeps_parties_as_suggestions():
    fetched, resolved, warnings = Mapper().map(
        _datacite_record(),
        'https://doi.org/10.1234/example',
    )
    resolved_dict = resolved.to_dict()

    assert resolved_dict['instrument_classification'] == 'Geochemistry'
    assert resolved_dict['alternate_identifier_obj'][0] == {
        'alternate_identifier_type': 'InventoryNumber',
        'alternate_identifier': 'INV-123',
    }
    assert resolved_dict['date'] == [
        {'date_value': '2012', 'date_type': 'Commissioned'}
    ]
    assert resolved_dict['model'] == [
        {
            'model_name': 'GeoProbe 2000',
            'model_identifier': 'https://example.test/model',
            'model_identifier_type': 'URL',
        }
    ]
    assert resolved_dict['related_identifier_obj'] == [
        {
            'related_identifier': '10.9999/manual',
            'related_identifier_type': 'DOI',
            'relation_type': 'IsDescribedBy',
        }
    ]
    assert 'owner' not in resolved_dict
    assert 'manufacturer' not in resolved_dict
    assert 'funder_party_id' not in resolved_dict
    assert fetched.available_unmapped['creators'] == [{'name': 'A. Researcher'}]
    assert fetched.available_unmapped['contributors'] == [
        {'name': 'A. Manufacturer', 'contributorType': 'HostingInstitution'}
    ]
    assert fetched.available_unmapped['funding_references'] == [
        {'funderName': 'Example Funder'}
    ]
    assert not any('Created' in str(value) for value in resolved_dict['date'])
    assert warnings == []


def test_argus_vi_sample_expected_resolved_fields():
    """Full regression test matching the documented expected output for 10.83627/5fpt3jtq."""
    from ckanext.pidinst_theme.doi_resolution.mapper import (
        extract_datacite_instrument_type_suggestions,
    )
    # Build a ProviderRecord that mirrors what the DataCite client would return for
    # DOI 10.83627/5fpt3jtq (Argus VI Noble Gas Mass Spectrometer).
    attributes = {
        'titles': [{'title': 'Argus VI Noble Gas Mass Spectrometer'}],
        'descriptions': [
            {
                'descriptionType': 'Abstract',
                'description': (
                    'CO2 laser step-heating extraction line attached to a new generation, '
                    'high-precision multi-collector mass spectrometer configured for '
                    'Ar isotope analysis.'
                ),
            },
            {
                'descriptionType': 'TechnicalInfo',
                'description': (
                    'Model: Argus VI Noble Gas Mass Spectrometer '
                    '(URL: https://documents.thermofisher.com/TFS-Assets/CMD/'
                    'Specification-Sheets/PS-30167-MS-ARGUS-VI-Noble-Gas-PS30167-EN.pdf)'
                ),
            },
            {
                'descriptionType': 'TechnicalInfo',
                'description': (
                    'Instrument Type: MASS SPECTROMETERS '
                    '(URI: http://vocab.nerc.ac.uk/collection/L05/current/MSS/)'
                ),
            },
            {
                'descriptionType': 'TechnicalInfo',
                'description': (
                    'Instrument Type: Multi collector noble gas mass spectrometer '
                    '(URI: https://www.wikidata.org/wiki/Q51687050)'
                ),
            },
        ],
        'creators': [{'name': 'AuScope'}],
        'publisher': 'AuScope',
        'publicationYear': 2012,
        'types': {
            'resourceType': 'Geochemistry',
            'resourceTypeGeneral': 'Instrument',
        },
        # The InventoryNumber appears in BOTH identifiers and alternateIdentifiers
        'identifiers': [
            {'identifier': '10.83627/5fpt3jtq', 'identifierType': 'DOI'},
            {'identifier': 'ARGUS VI JdLC-WAAIF', 'identifierType': 'InventoryNumber'},
        ],
        'alternateIdentifiers': [
            {
                'alternateIdentifier': 'ARGUS VI JdLC-WAAIF',
                'alternateIdentifierType': 'InventoryNumber',
            },
        ],
        'dates': [
            {
                'date': '2012',
                'dateType': 'Other',
                'dateInformation': 'Commissioned',
            },
        ],
        'relatedIdentifiers': [],
    }
    payload = {'data': {'attributes': attributes}}
    record = ProviderRecord(
        source='datacite',
        title='Argus VI Noble Gas Mass Spectrometer',
        description=(
            'CO2 laser step-heating extraction line attached to a new generation, '
            'high-precision multi-collector mass spectrometer configured for '
            'Ar isotope analysis.'
        ),
        creators=['AuScope'],
        publisher='AuScope',
        publication_year='2012',
        provider_metadata=payload,
    )

    fetched, resolved, warnings = Mapper().map(
        record, 'https://doi.org/10.83627/5fpt3jtq'
    )
    resolved_dict = resolved.to_dict()

    # Core fields
    assert resolved_dict['identifier_url'] == 'https://doi.org/10.83627/5fpt3jtq'
    assert resolved_dict['title'] == 'Argus VI Noble Gas Mass Spectrometer'
    assert 'CO2 laser' in resolved_dict['notes']
    assert resolved_dict['instrument_classification'] == 'Geochemistry'

    # Alternate identifier: exactly ONE row for the InventoryNumber
    alt_ids = resolved_dict['alternate_identifier_obj']
    assert len(alt_ids) == 1
    assert alt_ids[0] == {
        'alternate_identifier_type': 'InventoryNumber',
        'alternate_identifier': 'ARGUS VI JdLC-WAAIF',
    }

    # Lifecycle date
    assert resolved_dict['date'] == [{'date_value': '2012', 'date_type': 'Commissioned'}]

    # Model
    assert resolved_dict['model'] == [
        {
            'model_name': 'Argus VI Noble Gas Mass Spectrometer',
            'model_identifier': (
                'https://documents.thermofisher.com/TFS-Assets/CMD/'
                'Specification-Sheets/PS-30167-MS-ARGUS-VI-Noble-Gas-PS30167-EN.pdf'
            ),
            'model_identifier_type': 'URL',
        }
    ]

    # Related identifiers
    assert resolved_dict['related_identifier_obj'] == []

    # Instrument type suggestions (suggestion-only, NOT auto-applied)
    suggestions = resolved_dict['instrument_type_suggestions']
    assert len(suggestions) == 2
    names = {s['instrument_type_name'] for s in suggestions}
    assert 'MASS SPECTROMETERS' in names
    assert 'Multi collector noble gas mass spectrometer' in names

    # No spurious warnings from instrument type TechnicalInfo
    assert not any('TechnicalInfo' in w for w in warnings)


def test_creators_contributors_funding_not_mapped_to_owner_manufacturer_funder():
    """Requirement 17: DataCite party fields must NEVER appear as resolved form fields."""
    fetched, resolved, warnings = Mapper().map(
        _datacite_record(),
        'https://doi.org/10.1234/example',
    )
    resolved_dict = resolved.to_dict()

    # These keys must be absent from resolved_fields entirely
    for forbidden in (
        'owner', 'manufacturer', 'funder', 'funder_party_id',
        'instrument_type', 'measured_variable',
    ):
        assert forbidden not in resolved_dict, (
            f'"{forbidden}" must NOT appear in resolved_fields'
        )

    # The party-like data should only appear in available_unmapped
    assert 'creators' in fetched.available_unmapped or 'authors' in fetched.available_unmapped
    assert 'contributors' in fetched.available_unmapped or 'funding_references' in fetched.available_unmapped


def test_unsupported_classification_remains_unmapped_with_warning():
    fetched, resolved, warnings = Mapper().map(
        _datacite_record(
            _datacite_sample_attributes(types={'resourceType': 'Sensor'})
        ),
        'https://doi.org/10.1234/example',
    )

    assert resolved.instrument_classification == ''
    assert fetched.available_unmapped['resource_type'] == {'resourceType': 'Sensor'}
    assert any('does not match' in warning for warning in warnings)


def test_invalid_lifecycle_date_is_not_mapped_and_warns():
    fetched, resolved, warnings = Mapper().map(
        _datacite_record(
            _datacite_sample_attributes(
                dates=[
                    {
                        'date': 'March 2026',
                        'dateType': 'Other',
                        'dateInformation': 'Commissioned',
                    }
                ]
            )
        ),
        'https://doi.org/10.1234/example',
    )

    assert resolved.date == []
    assert fetched.available_unmapped['lifecycle_dates'] == [
        {
            'date': 'March 2026',
            'dateType': 'Other',
            'dateInformation': 'Commissioned',
        }
    ]
    assert any('lifecycle dates' in warning for warning in warnings)


def test_malformed_model_technical_info_is_not_guessed():
    fetched, resolved, warnings = Mapper().map(
        _datacite_record(
            _datacite_sample_attributes(
                descriptions=[
                    {
                        'descriptionType': 'TechnicalInfo',
                        'description': 'Model GeoProbe, support URL https://example.test',
                    }
                ]
            )
        ),
        'https://doi.org/10.1234/example',
    )

    assert resolved.model == []
    assert fetched.available_unmapped['technical_info_descriptions'] == [
        {
            'descriptionType': 'TechnicalInfo',
            'description': 'Model GeoProbe, support URL https://example.test',
        }
    ]
    assert any('TechnicalInfo descriptions' in warning for warning in warnings)


def test_invalid_input_short_circuits_both_providers():
    datacite = StubClient(ProviderResponse(ProviderLookup.ERROR))
    crossref = StubClient(ProviderResponse(ProviderLookup.ERROR))

    result = resolve('not a doi', datacite, crossref, Mapper())

    assert result.status == 'invalid_input'
    assert datacite.calls == []
    assert crossref.calls == []


def test_datacite_is_preferred_without_crossref_lookup():
    record = ProviderRecord(source='datacite', title='DataCite title')
    datacite = StubClient(ProviderResponse(ProviderLookup.FOUND, record))
    crossref = StubClient(ProviderResponse(ProviderLookup.ERROR))

    result = resolve('10.1234/example', datacite, crossref, Mapper())

    assert result.status == 'ok'
    assert result.source == 'datacite'
    assert crossref.calls == []


def test_crossref_is_used_only_after_datacite_not_found():
    record = ProviderRecord(
        source='crossref',
        title='Crossref title',
        provider_metadata={
            'status': 'ok',
            'message': {
                'subject': ['instrumentation'],
                'license': [{'URL': 'https://example.test/license'}],
            },
        },
    )
    datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
    crossref = StubClient(ProviderResponse(ProviderLookup.FOUND, record))

    result = resolve('doi:10.1234/example', datacite, crossref, Mapper())

    assert result.status == 'ok'
    assert result.source == 'crossref'
    assert datacite.calls == ['10.1234/example']
    assert crossref.calls == ['10.1234/example']
    assert result.to_dict()['resolved_fields']['title'] == 'Crossref title'
    assert result.to_dict()['provider_metadata']['status'] == 'ok'
    assert result.to_dict()['available_unmapped']['subjects'] == ['instrumentation']
    assert result.to_dict()['available_unmapped']['rights'] == [
        {'URL': 'https://example.test/license'}
    ]


def test_provider_error_and_double_not_found_have_distinct_statuses():
    error = StubClient(ProviderResponse(ProviderLookup.ERROR))
    unused = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
    assert resolve('10.1234/example', error, unused, Mapper()).status == 'fetch_error'
    assert unused.calls == []

    datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
    crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
    assert resolve('10.1234/example', datacite, crossref, Mapper()).status == 'not_found'


def test_resolve_dialog_template_has_full_metadata_and_unmapped_sections():
    template = (
        Path(__file__).parents[2]
        / 'templates'
        / 'scheming'
        / 'package'
        / 'snippets'
        / 'doi_resolve_dialog.html'
    ).read_text()

    assert 'All provider metadata' in template
    assert 'data-doi-resolve="provider_metadata"' in template
    assert 'Available provider metadata not mapped' in template
    assert 'data-doi-resolve="available_unmapped"' in template
    assert 'data-doi-resolve="manual_resolved"' in template
    assert 'data-doi-resolve="manual_groups"' in template


# ---------------------------------------------------------------------------
# Tier 3 — suggestion-only field extractors
# ---------------------------------------------------------------------------


def test_manufacturer_suggestions_from_organisational_creators():
    attributes = _datacite_sample_attributes(
        creators=[
            {
                'name': 'Thermo Fisher Scientific',
                'nameType': 'Organizational',
                'nameIdentifiers': [
                    {
                        'nameIdentifier': 'https://ror.org/008e2cd64',
                        'nameIdentifierScheme': 'ROR',
                    }
                ],
                'affiliation': [{'name': 'United States'}],
            },
            {'name': 'A. Person', 'nameType': 'Personal',
             'givenName': 'A.', 'familyName': 'Person'},
        ]
    )
    suggestions = extract_datacite_manufacturer_suggestions(attributes)

    assert len(suggestions) == 1
    s = suggestions[0]
    assert s['name'] == 'Thermo Fisher Scientific'
    assert s['source'] == 'creator'
    assert s['suggested_role'] == 'manufacturer'
    assert s['ror'] == 'https://ror.org/008e2cd64'
    assert s['affiliation'] == ['United States']


def test_owner_suggestions_from_hosting_institution_contributors():
    attributes = _datacite_sample_attributes(
        contributors=[
            {
                'name': 'University of Example',
                'contributorType': 'HostingInstitution',
                'nameIdentifiers': [
                    {
                        'nameIdentifier': 'https://ror.org/05gq02987',
                        'nameIdentifierScheme': 'ROR',
                    }
                ],
            },
            {'name': 'Someone Else', 'contributorType': 'DataCurator'},
        ]
    )
    suggestions = extract_datacite_owner_suggestions(attributes)

    assert len(suggestions) == 1
    s = suggestions[0]
    assert s['name'] == 'University of Example'
    assert s['contributorType'] == 'HostingInstitution'
    assert s['source'] == 'contributor'
    assert s['suggested_role'] == 'owner'
    assert s['ror'] == 'https://ror.org/05gq02987'


def test_funder_suggestions_from_funding_references():
    attributes = _datacite_sample_attributes(
        fundingReferences=[
            {
                'funderName': 'Example Funder',
                'funderIdentifier': 'https://doi.org/10.13039/501100000923',
                'funderIdentifierType': 'Crossref Funder ID',
                'schemeUri': 'https://doi.org/10.13039/',
                'awardNumber': 'GR-1234',
                'awardTitle': 'Big Grant',
            }
        ]
    )
    suggestions = extract_datacite_funder_suggestions(attributes)

    assert len(suggestions) == 1
    s = suggestions[0]
    assert s['funderName'] == 'Example Funder'
    assert s['funderIdentifierType'] == 'Crossref Funder ID'
    assert s['awardNumber'] == 'GR-1234'
    assert s['awardTitle'] == 'Big Grant'
    assert s['source'] == 'fundingReference'
    assert s['suggested_role'] == 'funder'


def test_party_identifier_suggestions_collect_name_identifiers():
    attributes = _datacite_sample_attributes(
        creators=[
            {
                'name': 'A. Researcher',
                'nameIdentifiers': [
                    {
                        'nameIdentifier': 'https://orcid.org/0000-0002-1825-0097',
                        'nameIdentifierScheme': 'ORCID',
                    }
                ],
            }
        ],
        contributors=[
            {
                'name': 'University of Example',
                'contributorType': 'HostingInstitution',
                'nameIdentifiers': [
                    {
                        'nameIdentifier': 'https://ror.org/05gq02987',
                        'nameIdentifierScheme': 'ROR',
                    }
                ],
            }
        ],
    )
    suggestions = extract_datacite_party_identifier_suggestions(attributes)

    values = {s['name_identifier'] for s in suggestions}
    assert 'https://orcid.org/0000-0002-1825-0097' in values
    assert 'https://ror.org/05gq02987' in values


def test_taxonomy_suggestions_from_subjects():
    attributes = _datacite_sample_attributes(
        subjects=[
            {
                'subject': 'Geochemistry',
                'subjectScheme': 'ANZSRC',
                'valueURI': 'https://example.test/anzsrc/geochem',
            }
        ]
    )
    suggestions = extract_datacite_taxonomy_suggestions(attributes)

    assert suggestions == [
        {
            'subject': 'Geochemistry',
            'source': 'subject',
            'subject_scheme': 'ANZSRC',
            'value_uri': 'https://example.test/anzsrc/geochem',
        }
    ]


def test_geo_location_suggestions_preserved():
    geo = [{'geoLocationPlace': 'Perth, Australia'}]
    attributes = _datacite_sample_attributes(geoLocations=geo)
    assert extract_datacite_geo_location_suggestions(attributes) == geo


def test_publication_metadata_suggestions_collect_lifecycle_dates():
    attributes = _datacite_sample_attributes(
        publisher='AuScope',
        publicationYear=2026,
        dates=[
            {'date': '2026-01-01', 'dateType': 'Created'},
            {'date': '2026-03-01', 'dateType': 'Issued'},
            {'date': '2026-02-01', 'dateType': 'Updated'},
            {'date': '2012', 'dateType': 'Other', 'dateInformation': 'Commissioned'},
        ],
    )
    suggestion = extract_datacite_publication_metadata_suggestions(attributes)

    assert suggestion['publisher'] == 'AuScope'
    assert suggestion['publication_year'] == '2026'
    assert suggestion['created_date'] == '2026-01-01'
    assert suggestion['issued_date'] == '2026-03-01'
    assert suggestion['updated_date'] == '2026-02-01'
    assert suggestion['source'] == 'datacite'
    # The Commissioned lifecycle date must not leak into publication metadata.
    assert '2012' not in suggestion.values()


def test_suggestions_never_appear_as_party_form_fields():
    """Tier 3 suggestions must never produce owner/manufacturer/funder form keys."""
    attributes = _datacite_sample_attributes(
        creators=[{'name': 'Thermo Fisher Scientific', 'nameType': 'Organizational'}],
        contributors=[{'name': 'University of Example',
                       'contributorType': 'HostingInstitution'}],
    )
    fetched, resolved, warnings = Mapper().map(
        _datacite_record(attributes), 'https://doi.org/10.1234/example'
    )
    resolved_dict = resolved.to_dict()

    # Suggestions present
    assert resolved_dict['manufacturer_suggestions'][0]['name'] == 'Thermo Fisher Scientific'
    assert resolved_dict['owner_suggestions'][0]['name'] == 'University of Example'
    assert resolved_dict['funder_suggestions'][0]['funderName'] == 'Example Funder'

    # Party-backed form field keys absent
    for forbidden in ('owner', 'manufacturer', 'funder', 'funder_party_id',
                      'owner_party_id', 'manufacturer_party_id'):
        assert forbidden not in resolved_dict


def _argus_vi_attributes():
    """Argus VI DataCite sample fixture exercising every tier."""
    return {
        'titles': [{'title': 'Argus VI Noble Gas Mass Spectrometer'}],
        'descriptions': [
            {
                'descriptionType': 'TechnicalInfo',
                'description': (
                    'Model: Argus VI Noble Gas Mass Spectrometer '
                    '(URL: https://documents.thermofisher.com/TFS-Assets/CMD/'
                    'Specification-Sheets/PS-30167-MS-ARGUS-VI-Noble-Gas-PS30167-EN.pdf)'
                ),
            },
            {
                'descriptionType': 'Abstract',
                'description': (
                    'CO2 laser step-heating extraction line attached to a new '
                    'generation, high-precision multi-collector mass spectrometer '
                    'configured for Ar isotope analysis.'
                ),
            },
            {
                'descriptionType': 'TechnicalInfo',
                'description': (
                    'Instrument Type: MASS SPECTROMETERS '
                    '(URI: http://vocab.nerc.ac.uk/collection/L05/current/MSS/)'
                ),
            },
            {
                'descriptionType': 'TechnicalInfo',
                'description': (
                    'Instrument Type: Multi collector noble gas mass spectrometer '
                    '(URI: https://www.wikidata.org/wiki/Q51687050)'
                ),
            },
        ],
        'creators': [
            {
                'name': 'Thermo Fisher Scientific',
                'nameType': 'Organizational',
                'affiliation': [{'name': 'United States'}],
            }
        ],
        'contributors': [
            {
                'name': 'University of Western Australia',
                'contributorType': 'HostingInstitution',
            }
        ],
        'publisher': 'AuScope',
        'publicationYear': 2026,
        'types': {'resourceType': 'Geochemistry', 'resourceTypeGeneral': 'Instrument'},
        'identifiers': [
            {'identifier': '10.83627/5fpt3jtq', 'identifierType': 'DOI'},
            {'identifier': 'ARGUS VI JdLC-WAAIF', 'identifierType': 'InventoryNumber'},
        ],
        'alternateIdentifiers': [
            {'alternateIdentifier': 'ARGUS VI JdLC-WAAIF',
             'alternateIdentifierType': 'InventoryNumber'},
        ],
        'dates': [
            {'date': '2012', 'dateType': 'Other', 'dateInformation': 'Commissioned'},
            {'date': '2026-01-01', 'dateType': 'Created'},
            {'date': '2026-02-01', 'dateType': 'Updated'},
            {'date': '2026-03-01', 'dateType': 'Issued'},
        ],
        'fundingReferences': [{'funderName': 'Australian Research Council'}],
        'relatedIdentifiers': [],
    }


def test_argus_vi_full_regression():
    """End-to-end mapper regression for the Argus VI sample (all tiers)."""
    attributes = _argus_vi_attributes()
    # Provider description prefers the Abstract over TechnicalInfo.
    from ckanext.pidinst_theme.doi_resolution.providers import DataCiteClient
    abstract = DataCiteClient._first_description(attributes['descriptions'])
    assert abstract.startswith('CO2 laser step-heating')

    record = ProviderRecord(
        source='datacite',
        title='Argus VI Noble Gas Mass Spectrometer',
        description=abstract,
        creators=['Thermo Fisher Scientific'],
        publisher='AuScope',
        publication_year='2026',
        provider_metadata={'data': {'attributes': attributes}},
    )
    fetched, resolved, warnings = Mapper().map(
        record, 'https://doi.org/10.83627/5fpt3jtq'
    )
    rf = resolved.to_dict()

    # Tier 1
    assert rf['identifier_url'] == 'https://doi.org/10.83627/5fpt3jtq'
    assert rf['title'] == 'Argus VI Noble Gas Mass Spectrometer'
    assert rf['notes'].startswith('CO2 laser step-heating')
    assert 'Model:' not in rf['notes']
    assert rf['instrument_classification'] == 'Geochemistry'

    # Tier 2 — alternate identifier (exactly one InventoryNumber row)
    assert rf['alternate_identifier_obj'] == [
        {'alternate_identifier_type': 'InventoryNumber',
         'alternate_identifier': 'ARGUS VI JdLC-WAAIF'}
    ]
    # Tier 2 — lifecycle date (Commissioned only; Created/Updated/Issued ignored)
    assert rf['date'] == [{'date_value': '2012', 'date_type': 'Commissioned'}]
    # Tier 2 — model
    assert rf['model'] == [{
        'model_name': 'Argus VI Noble Gas Mass Spectrometer',
        'model_identifier': (
            'https://documents.thermofisher.com/TFS-Assets/CMD/'
            'Specification-Sheets/PS-30167-MS-ARGUS-VI-Noble-Gas-PS30167-EN.pdf'
        ),
        'model_identifier_type': 'URL',
    }]
    assert rf['related_identifier_obj'] == []

    # Tier 3 — instrument type suggestions (suggestion-only)
    inst_names = {s['instrument_type_name'] for s in rf['instrument_type_suggestions']}
    assert inst_names == {
        'MASS SPECTROMETERS', 'Multi collector noble gas mass spectrometer'
    }
    # Tier 3 — party suggestions
    assert rf['manufacturer_suggestions'][0]['name'] == 'Thermo Fisher Scientific'
    assert rf['owner_suggestions'][0]['name'] == 'University of Western Australia'
    assert rf['funder_suggestions'][0]['funderName'] == 'Australian Research Council'
    # Tier 3 — publication metadata
    assert rf['publication_metadata_suggestions']['publisher'] == 'AuScope'
    assert rf['publication_metadata_suggestions']['publication_year'] == '2026'

    # No model warnings from Instrument Type TechnicalInfo
    assert not any('TechnicalInfo' in w for w in warnings)

    # No party/taxonomy form-field keys
    for forbidden in ('owner', 'manufacturer', 'funder', 'funder_party_id',
                      'instrument_type', 'measured_variable'):
        assert forbidden not in rf


def test_related_identifier_obj_uses_suggestions_not_direct_extract():
    """Safety: related_identifier_obj must NOT include related_resource_type.

    DataCite relatedIdentifiers lack related_resource_type, which is a required
    PIDINST schema field. The Mapper uses extract_datacite_related_identifier_suggestions
    (same output format) so the data is surfaced for manual review only, not for
    auto-apply by the frontend composite field writer.
    """
    attributes = _datacite_sample_attributes(
        relatedIdentifiers=[
            {
                'relatedIdentifier': '10.9999/test',
                'relatedIdentifierType': 'DOI',
                'relationType': 'IsDescribedBy',
            }
        ]
    )
    record = _datacite_record(attributes)
    _, resolved, _ = Mapper().map(record, 'https://doi.org/10.1234/test')
    rd = resolved.to_dict()

    # Data is present for display/manual review
    assert len(rd['related_identifier_obj']) == 1
    row = rd['related_identifier_obj'][0]
    assert row['related_identifier'] == '10.9999/test'
    assert row['relation_type'] == 'IsDescribedBy'

    # Critical: related_resource_type must NOT be present (DataCite doesn't provide it)
    assert 'related_resource_type' not in row, (
        'related_identifier_obj rows must not include related_resource_type '
        '(DataCite cannot safely fill this required PIDINST field)'
    )
