import requests

from ckanext.pidinst_theme.doi_resolution import providers
from ckanext.pidinst_theme.doi_resolution.providers import (
    CrossrefClient,
    DataCiteClient,
    ProviderLookup,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def test_datacite_parses_descriptive_metadata(monkeypatch):
    payload = {
        'data': {
            'attributes': {
                'titles': [{'title': 'Instrument title'}],
                'descriptions': [{'description': 'Instrument description'}],
                'creators': [{'name': 'A. Researcher'}],
                'publisher': 'Example Publisher',
                'publicationYear': 2025,
                'subjects': [{'subject': 'Seismology'}],
                'nested': {'token': 'should-not-leak'},
            }
        },
        'included': [{'type': 'client'}],
    }
    monkeypatch.setattr(
        providers.requests, 'get', lambda *args, **kwargs: FakeResponse(payload=payload)
    )

    response = DataCiteClient('https://example.test/dois/', 3).lookup(
        '10.1234/example'
    )

    assert response.outcome == ProviderLookup.FOUND
    assert response.record.title == 'Instrument title'
    assert response.record.description == 'Instrument description'
    assert response.record.creators == ['A. Researcher']
    assert response.record.publisher == 'Example Publisher'
    assert response.record.publication_year == '2025'
    assert response.record.provider_metadata['included'] == [{'type': 'client'}]
    assert response.record.provider_metadata['data']['attributes']['subjects'] == [
        {'subject': 'Seismology'}
    ]
    assert (
        response.record.provider_metadata['data']['attributes']['nested']['token']
        == '[redacted]'
    )


def test_crossref_parses_descriptive_metadata(monkeypatch):
    payload = {
        'message': {
            'title': ['Instrument title'],
            'abstract': 'Instrument description',
            'author': [
                {'given': 'Ada', 'family': 'Lovelace'},
                {'name': 'Research Team'},
            ],
            'publisher': 'Example Publisher',
            'issued': {'date-parts': [[2024, 1, 2]]},
            'license': [{'URL': 'https://example.test/license'}],
        }
    }
    monkeypatch.setattr(
        providers.requests, 'get', lambda *args, **kwargs: FakeResponse(payload=payload)
    )

    response = CrossrefClient('https://example.test/works', 3).lookup(
        '10.1234/example'
    )

    assert response.outcome == ProviderLookup.FOUND
    assert response.record.creators == ['Ada Lovelace', 'Research Team']
    assert response.record.publication_year == '2024'
    assert response.record.provider_metadata['message']['license'] == [
        {'URL': 'https://example.test/license'}
    ]


def test_provider_outcomes_are_contained(monkeypatch):
    client = DataCiteClient('https://example.test/dois', 3)

    monkeypatch.setattr(
        providers.requests, 'get', lambda *args, **kwargs: FakeResponse(status_code=404)
    )
    assert client.lookup('10.1234/missing').outcome == ProviderLookup.NOT_FOUND

    def timeout(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr(providers.requests, 'get', timeout)
    assert client.lookup('10.1234/timeout').outcome == ProviderLookup.ERROR

    monkeypatch.setattr(
        providers.requests,
        'get',
        lambda *args, **kwargs: FakeResponse(json_error=ValueError('bad json')),
    )
    assert client.lookup('10.1234/bad-json').outcome == ProviderLookup.ERROR
