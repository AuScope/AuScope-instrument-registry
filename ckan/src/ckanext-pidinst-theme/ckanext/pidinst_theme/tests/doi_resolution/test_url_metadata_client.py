"""Tests for the URL metadata client and URL resolution flow."""

import json

import pytest

from ckanext.pidinst_theme.doi_resolution.input_normalizer import normalize_input
from ckanext.pidinst_theme.doi_resolution.mapper import Mapper
from ckanext.pidinst_theme.doi_resolution.providers import (
    ProviderLookup,
    ProviderResponse,
)
from ckanext.pidinst_theme.doi_resolution.resolver import resolve
from ckanext.pidinst_theme.doi_resolution.url_metadata_client import (
    UrlFetchResult,
    UrlFetchStatus,
    _is_unsafe_hostname,
    _is_unsafe_ip,
    _parse_crossref_json,
    _parse_datacite_json,
    _validate_url_safe,
    fetch_url_metadata,
)


# --- StubClient for resolver tests ---


class StubClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def lookup(self, bare_doi):
        self.calls.append(bare_doi)
        return self.response


# =============================================================================
# Input normalizer: URL acceptance
# =============================================================================


class TestNormalizerUrlAcceptance:
    """Arbitrary http/https URLs are accepted by the normaliser."""

    def test_https_url_accepted(self):
        result = normalize_input('https://example.com/api/instruments/123')
        assert result.is_valid is True
        assert result.input_type == 'url'
        assert result.identifier_url == 'https://example.com/api/instruments/123'
        assert result.bare_doi == ''

    def test_http_url_accepted(self):
        result = normalize_input('http://metadata.example.org/record/456')
        assert result.is_valid is True
        assert result.input_type == 'url'
        assert result.identifier_url == 'http://metadata.example.org/record/456'

    def test_random_text_invalid(self):
        result = normalize_input('not a url or doi')
        assert result.is_valid is False
        assert result.input_type == ''

    def test_ftp_url_invalid(self):
        result = normalize_input('ftp://files.example.com/data')
        assert result.is_valid is False

    def test_existing_bare_doi_still_works(self):
        result = normalize_input('10.1234/example')
        assert result.is_valid is True
        assert result.input_type == 'doi'
        assert result.bare_doi == '10.1234/example'

    def test_existing_doi_url_still_works(self):
        result = normalize_input('https://doi.org/10.1234/example')
        assert result.is_valid is True
        assert result.input_type == 'doi'
        assert result.bare_doi == '10.1234/example'

    def test_existing_datacite_test_doi_url_still_works(self):
        result = normalize_input(
            'https://api.test.datacite.org/dois/10.83627/5fpt3jtq'
        )
        assert result.is_valid is True
        assert result.input_type == 'doi'
        assert result.bare_doi == '10.83627/5fpt3jtq'


# =============================================================================
# SSRF protection
# =============================================================================


class TestSsrfProtection:
    """Localhost/private/internal URLs are rejected safely."""

    @pytest.mark.parametrize(
        'ip',
        [
            '127.0.0.1',
            '127.0.0.2',
            '10.0.0.1',
            '172.16.0.1',
            '172.31.255.255',
            '192.168.0.1',
            '192.168.1.1',
            '169.254.169.254',
            '0.0.0.0',
            '::1',
            'fe80::1',
        ],
    )
    def test_unsafe_ips_rejected(self, ip):
        assert _is_unsafe_ip(ip) is True

    @pytest.mark.parametrize(
        'ip',
        [
            '8.8.8.8',
            '1.1.1.1',
            '203.0.113.1',
        ],
    )
    def test_public_ips_allowed(self, ip):
        assert _is_unsafe_ip(ip) is False

    @pytest.mark.parametrize(
        'hostname',
        [
            'localhost',
            'myapp.local',
            'service.internal',
            'api.svc',
            'backend.cluster.local',
            'metadata.google.internal',
            'host.localhost',
        ],
    )
    def test_unsafe_hostnames_rejected(self, hostname):
        assert _is_unsafe_hostname(hostname) is True

    @pytest.mark.parametrize(
        'hostname',
        [
            'example.com',
            'api.datacite.org',
            'metadata.example.org',
        ],
    )
    def test_safe_hostnames_allowed(self, hostname):
        assert _is_unsafe_hostname(hostname) is False


# =============================================================================
# URL metadata client: parsing
# =============================================================================


class TestDataCiteJsonParsing:
    """A valid arbitrary URL returning DataCite-style JSON maps successfully."""

    def test_datacite_json_parsed(self):
        payload = {
            'data': {
                'attributes': {
                    'titles': [{'title': 'Test Instrument'}],
                    'descriptions': [
                        {
                            'descriptionType': 'Abstract',
                            'description': 'A test instrument.',
                        }
                    ],
                    'creators': [{'name': 'Researcher A'}],
                    'publisher': 'Example Publisher',
                    'publicationYear': 2024,
                }
            }
        }
        record = _parse_datacite_json(payload)
        assert record is not None
        assert record.source == 'datacite'
        assert record.title == 'Test Instrument'
        assert record.description == 'A test instrument.'
        assert record.creators == ['Researcher A']
        assert record.publisher == 'Example Publisher'
        assert record.publication_year == '2024'

    def test_non_datacite_json_returns_none(self):
        payload = {'random': 'data'}
        assert _parse_datacite_json(payload) is None

    def test_missing_data_key_returns_none(self):
        payload = {'attributes': {'titles': [{'title': 'Test'}]}}
        assert _parse_datacite_json(payload) is None


class TestCrossrefJsonParsing:
    """A valid arbitrary URL returning Crossref-style JSON maps successfully."""

    def test_crossref_json_parsed(self):
        payload = {
            'status': 'ok',
            'message': {
                'title': ['Crossref Title'],
                'abstract': 'A crossref abstract.',
                'author': [
                    {'given': 'Jane', 'family': 'Doe'},
                ],
                'publisher': 'Crossref Publisher',
                'issued': {'date-parts': [[2023]]},
            },
        }
        record = _parse_crossref_json(payload)
        assert record is not None
        assert record.source == 'crossref'
        assert record.title == 'Crossref Title'
        assert record.description == 'A crossref abstract.'
        assert record.creators == ['Jane Doe']
        assert record.publisher == 'Crossref Publisher'
        assert record.publication_year == '2023'

    def test_non_crossref_json_returns_none(self):
        payload = {'data': 'something'}
        assert _parse_crossref_json(payload) is None


class TestUnsupportedFormats:
    """A valid arbitrary URL returning unsupported JSON returns unsupported_format."""

    def test_unsupported_json_returns_unsupported_format(self):
        """JSON that doesn't match any known format."""
        # Simulate via the resolver
        def fake_fetcher(url, **kwargs):
            return UrlFetchResult(status=UrlFetchStatus.UNSUPPORTED_FORMAT)

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://example.com/api/unknown-format',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )
        assert result.status == 'unsupported_format'
        # DOI providers should NOT be called for URL inputs
        assert datacite.calls == []
        assert crossref.calls == []

    def test_html_returns_unsupported_format(self):
        """HTML/non-JSON responses return unsupported_format."""

        def fake_fetcher(url, **kwargs):
            return UrlFetchResult(status=UrlFetchStatus.UNSUPPORTED_FORMAT)

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://example.com/page.html',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )
        assert result.status == 'unsupported_format'


# =============================================================================
# Resolver: URL flow
# =============================================================================


class TestResolverUrlFlow:
    """URL resolution through the resolver."""

    def test_url_with_datacite_json_returns_ok(self):
        """A URL returning DataCite JSON maps and returns ok."""
        datacite_payload = {
            'data': {
                'attributes': {
                    'titles': [{'title': 'Remote Instrument'}],
                    'descriptions': [
                        {'descriptionType': 'Abstract', 'description': 'Remote desc.'}
                    ],
                    'creators': [{'name': 'Remote Author'}],
                    'publisher': 'Remote Publisher',
                    'publicationYear': 2024,
                }
            }
        }
        from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord

        record = ProviderRecord(
            source='datacite',
            title='Remote Instrument',
            description='Remote desc.',
            creators=['Remote Author'],
            publisher='Remote Publisher',
            publication_year='2024',
            provider_metadata=datacite_payload,
        )

        def fake_fetcher(url, **kwargs):
            return UrlFetchResult(
                status=UrlFetchStatus.OK, record=record, source='datacite'
            )

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://my-repo.example.com/api/instrument/999',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )

        assert result.status == 'ok'
        assert result.source == 'datacite'
        assert result.doi == ''  # No DOI for URL inputs
        assert result.identifier_url == 'https://my-repo.example.com/api/instrument/999'
        assert result.resolved_fields.identifier_url == (
            'https://my-repo.example.com/api/instrument/999'
        )
        assert result.resolved_fields.title == 'Remote Instrument'

    def test_url_with_crossref_json_returns_ok(self):
        """A URL returning Crossref JSON maps and returns ok."""
        from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord

        crossref_payload = {
            'status': 'ok',
            'message': {
                'title': ['Crossref Instrument'],
                'abstract': 'Crossref desc.',
                'author': [{'given': 'John', 'family': 'Smith'}],
                'publisher': 'Crossref Publisher',
                'issued': {'date-parts': [[2023]]},
            },
        }
        record = ProviderRecord(
            source='crossref',
            title='Crossref Instrument',
            description='Crossref desc.',
            creators=['John Smith'],
            publisher='Crossref Publisher',
            publication_year='2023',
            provider_metadata=crossref_payload,
        )

        def fake_fetcher(url, **kwargs):
            return UrlFetchResult(
                status=UrlFetchStatus.OK, record=record, source='crossref'
            )

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://other-repo.example.com/works/123',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )

        assert result.status == 'ok'
        assert result.source == 'crossref'
        assert result.doi == ''
        assert result.identifier_url == 'https://other-repo.example.com/works/123'
        assert result.resolved_fields.title == 'Crossref Instrument'

    def test_unsafe_url_returns_fetch_error(self):
        """An unsafe URL returns fetch_error."""

        def fake_fetcher(url, **kwargs):
            return UrlFetchResult(status=UrlFetchStatus.UNSAFE_URL)

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'http://localhost:8080/metadata',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )

        assert result.status == 'fetch_error'
        assert datacite.calls == []

    def test_network_error_returns_fetch_error(self):
        """A network error from the URL fetcher returns fetch_error."""

        def fake_fetcher(url, **kwargs):
            return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://unreachable.example.com/api/instrument/1',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )

        assert result.status == 'fetch_error'


# =============================================================================
# DOI resolution still works unchanged
# =============================================================================


class TestDOIResolutionUnchanged:
    """DOI resolution behaviour remains unchanged."""

    def test_bare_doi_still_uses_doi_flow(self):
        from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord

        record = ProviderRecord(source='datacite', title='DOI Title')
        datacite = StubClient(ProviderResponse(ProviderLookup.FOUND, record))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        url_fetcher_called = []

        def fake_fetcher(url, **kwargs):
            url_fetcher_called.append(url)
            return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)

        result = resolve(
            '10.1234/example',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )

        assert result.status == 'ok'
        assert result.source == 'datacite'
        assert result.doi == '10.1234/example'
        assert url_fetcher_called == []  # URL fetcher NOT called for DOIs

    def test_doi_url_still_uses_doi_flow(self):
        from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord

        record = ProviderRecord(source='datacite', title='DOI URL Title')
        datacite = StubClient(ProviderResponse(ProviderLookup.FOUND, record))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://doi.org/10.1234/example', datacite, crossref, Mapper()
        )

        assert result.status == 'ok'
        assert result.doi == '10.1234/example'

    def test_datacite_test_doi_still_uses_doi_flow(self):
        from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord

        record = ProviderRecord(source='datacite', title='Test DOI Title')
        datacite = StubClient(ProviderResponse(ProviderLookup.FOUND, record))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://api.test.datacite.org/dois/10.83627/5fpt3jtq',
            datacite,
            crossref,
            Mapper(),
        )

        assert result.status == 'ok'
        assert result.doi == '10.83627/5fpt3jtq'

    def test_invalid_text_returns_invalid_input(self):
        datacite = StubClient(ProviderResponse(ProviderLookup.ERROR))
        crossref = StubClient(ProviderResponse(ProviderLookup.ERROR))

        result = resolve('random garbage text', datacite, crossref, Mapper())

        assert result.status == 'invalid_input'
        assert datacite.calls == []
        assert crossref.calls == []


# =============================================================================
# Redirect safety
# =============================================================================


class TestRedirectSafety:
    """Redirects to unsafe/internal URLs are rejected."""

    def test_redirect_to_internal_blocked(self):
        """If the URL fetcher detects a redirect to an internal IP, it's rejected."""

        def fake_fetcher(url, **kwargs):
            # Simulate the adapter detecting a redirect to localhost
            return UrlFetchResult(status=UrlFetchStatus.UNSAFE_URL)

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://evil.example.com/redirect-to-internal',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )
        assert result.status == 'fetch_error'


# =============================================================================
# ResolveResult.to_dict() for unsupported_format
# =============================================================================


class TestResolveResultUnsupportedFormat:
    """ResolveResult.to_dict() supports the new unsupported_format status."""

    def test_unsupported_format_to_dict(self):
        from ckanext.pidinst_theme.doi_resolution.types import ResolveResult

        result = ResolveResult(status='unsupported_format')
        d = result.to_dict()
        assert d['status'] == 'unsupported_format'
        assert d['warnings'] == []

    def test_ok_to_dict_still_works(self):
        from ckanext.pidinst_theme.doi_resolution.types import (
            FetchedMetadata,
            ResolveResult,
            ResolvedFields,
        )

        result = ResolveResult(
            status='ok',
            source='datacite',
            doi='10.1234/test',
            identifier_url='https://doi.org/10.1234/test',
            fetched=FetchedMetadata(title='Test'),
            resolved_fields=ResolvedFields(
                identifier_url='https://doi.org/10.1234/test', title='Test'
            ),
        )
        d = result.to_dict()
        assert d['status'] == 'ok'
        assert d['source'] == 'datacite'
        assert d['doi'] == '10.1234/test'
        assert d['resolved_fields']['title'] == 'Test'


# =============================================================================
# URL result: identifier_url is the original URL, doi is empty
# =============================================================================


class TestUrlResultFields:
    """For non-DOI URLs, resolved_fields.identifier_url is the original URL."""

    def test_url_result_identifier_url_is_original(self):
        from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord

        record = ProviderRecord(
            source='datacite',
            title='Remote',
            provider_metadata={
                'data': {
                    'attributes': {
                        'titles': [{'title': 'Remote'}],
                        'publisher': 'P',
                        'publicationYear': 2024,
                    }
                }
            },
        )

        def fake_fetcher(url, **kwargs):
            return UrlFetchResult(
                status=UrlFetchStatus.OK, record=record, source='datacite'
            )

        datacite = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))
        crossref = StubClient(ProviderResponse(ProviderLookup.NOT_FOUND))

        result = resolve(
            'https://my-custom-repo.org/instrument/42',
            datacite,
            crossref,
            Mapper(),
            url_fetcher=fake_fetcher,
        )

        assert result.status == 'ok'
        d = result.to_dict()
        # doi must be empty for non-DOI URLs
        assert d['doi'] == ''
        # identifier_url must be the original user-entered URL
        assert d['identifier_url'] == 'https://my-custom-repo.org/instrument/42'
        assert d['resolved_fields']['identifier_url'] == (
            'https://my-custom-repo.org/instrument/42'
        )
