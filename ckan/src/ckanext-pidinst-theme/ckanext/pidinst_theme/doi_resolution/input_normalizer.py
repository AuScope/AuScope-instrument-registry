"""DOI and URL input detection and normalisation for the resolution pipeline.

This module is a thin, pure wrapper around the existing ``doi_policy`` DOI
helpers so that DOI parsing stays consistent across the extension
(Requirement 16.3). It contains no network calls and uses no CKAN
request-context state; it only reuses ``doi_policy``'s regex-based parsing and
the configured resolver host.

Accepted input forms (Requirements 2.1-2.4), with arbitrary surrounding
whitespace stripped:

- bare ``10.xxxx/yyyy``
- ``doi:10.xxxx/yyyy``
- ``https://doi.org/10.xxxx/yyyy``
- ``http://dx.doi.org/10.xxxx/yyyy``
- DataCite resolver URLs such as
  ``https://handle.test.datacite.org/10.xxxx/yyyy``
- DataCite test API URLs such as
  ``https://api.test.datacite.org/dois/10.xxxx/yyyy``
- Any valid ``http://`` or ``https://`` URL (treated as a URL input, not DOI)

Any other string -- random free text that is not a DOI or a valid http(s) URL
-- is reported as ``is_valid == False`` (invalid_input).
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from .. import doi_policy
from .types import NormalizedInput


PRODUCTION_DOI_HOSTS = frozenset({
    'doi.org',
    'dx.doi.org',
})

DATACITE_TEST_RESOLVER_HOSTS = frozenset({
    'api.test.datacite.org',
    'doi.test.datacite.org',
    'handle.test.datacite.org',
})

ALLOWED_DOI_URL_HOSTS = PRODUCTION_DOI_HOSTS | DATACITE_TEST_RESOLVER_HOSTS


def uses_datacite_test_api(identifier: str) -> bool:
    """Return whether ``identifier`` came from a DataCite test resolver URL."""
    parsed = urlparse((identifier or '').strip())
    return (parsed.hostname or '').lower() in DATACITE_TEST_RESOLVER_HOSTS


def normalize_input(identifier: str) -> NormalizedInput:
    """Normalise a raw identifier string into a :class:`NormalizedInput`.

    For URL inputs from allowed DOI hosts, the DOI path is extracted and the
    result has ``input_type='doi'``.

    For URL inputs from non-DOI hosts, the result has ``input_type='url'`` and
    ``identifier_url`` set to the original URL.

    For non-URL inputs, bare DOI and ``doi:`` forms are validated using the
    existing ``doi_policy`` helpers.

    Anything else is ``is_valid=False``.
    """
    raw = (identifier or '').strip()
    if not raw:
        return NormalizedInput(is_valid=False)

    parsed = urlparse(raw)

    # Full URL input: check host allow-list first, then validate the DOI path.
    if parsed.scheme.lower() in ('http', 'https') and parsed.netloc:
        bare_doi = _extract_doi_from_allowed_url(parsed)
        if bare_doi:
            return _build_doi_normalized_input(bare_doi)

        # Valid http/https URL that is NOT a DOI resolver URL.
        return NormalizedInput(
            is_valid=True,
            input_type='url',
            bare_doi='',
            identifier_url=raw,
        )

    # Non-URL input: accept bare DOI or doi:10.xxxx/yyyy forms.
    if not doi_policy.is_valid_doi(raw):
        return NormalizedInput(is_valid=False)

    bare_doi = doi_policy.normalize_doi(raw)
    return _build_doi_normalized_input(bare_doi)


def _extract_doi_from_allowed_url(parsed) -> str:
    """Extract a bare DOI from an allowed DOI resolver URL.

    Rejects arbitrary hosts even if their path contains a DOI-looking value.
    """
    host = (parsed.hostname or '').lower()
    if host not in ALLOWED_DOI_URL_HOSTS:
        return ''

    path = unquote(parsed.path or '').lstrip('/')
    if not path:
        return ''

    candidates = [path]

    # Support DataCite API-style URLs:
    # https://api.test.datacite.org/dois/10.xxxx/yyyy
    if path.lower().startswith('dois/'):
        candidates.append(path[5:])

    for candidate in candidates:
        if doi_policy.is_valid_doi(candidate):
            return doi_policy.normalize_doi(candidate)

    return ''


def _build_doi_normalized_input(bare_doi: str) -> NormalizedInput:
    """Build the standard NormalizedInput from a bare DOI."""
    identifier_url = '{}/{}'.format(doi_policy.doi_resolver_url(), bare_doi)
    return NormalizedInput(
        is_valid=True,
        input_type='doi',
        bare_doi=bare_doi,
        identifier_url=identifier_url,
    )