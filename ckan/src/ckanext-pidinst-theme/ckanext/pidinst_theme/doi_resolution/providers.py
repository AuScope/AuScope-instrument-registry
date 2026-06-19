"""Provider_Clients for the DOI metadata resolution pipeline.

Each Provider_Client performs a single HTTP GET against one external DOI
metadata provider (DataCite or Crossref) and normalises the response into a
provider-neutral :class:`~ckanext.pidinst_theme.doi_resolution.types.ProviderRecord`.

This module is intentionally free of any CKAN imports so that each client is
independently unit-testable without a CKAN request context (Requirements 4.6,
16.1). API URLs and the request timeout are injected as constructor parameters
so the clients themselves stay config-agnostic (Requirement 16.4). Only the
``requests`` HTTP library and the standard library ``json`` parser are used; no
new large dependency is introduced (Requirement 16.4).

Each client catches its own network/parse errors and translates them into a
:class:`ProviderResponse` outcome. A client never raises into the Resolver
(Requirements 3.3, 13.1, 13.2):

* HTTP 404 -> ``ProviderLookup.NOT_FOUND``
* ``requests.Timeout``, ``requests.RequestException``, any non-2xx/non-404
  status, or an unparseable response body -> ``ProviderLookup.ERROR``
* a parseable 2xx record -> ``ProviderLookup.FOUND`` with a ``ProviderRecord``
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - exercised implicitly wherever requests is available
    from typing import Protocol
except ImportError:  # pragma: no cover - Python < 3.8 fallback
    from typing_extensions import Protocol  # type: ignore

import requests

from ckanext.pidinst_theme.doi_resolution.types import ProviderRecord


class ProviderLookup(Enum):
    """The three distinguishable outcomes of a single provider lookup."""

    FOUND = 'found'          # a record exists -> ProviderRecord returned
    NOT_FOUND = 'not_found'  # provider reports no such DOI (HTTP 404)
    ERROR = 'error'          # network error / timeout / unexpected status/body


@dataclass
class ProviderResponse:
    """The result of a single :meth:`ProviderClient.lookup` call."""

    outcome: ProviderLookup
    record: Optional[ProviderRecord] = None


class ProviderClient(Protocol):
    """Structural interface implemented by every Provider_Client."""

    source: str  # 'datacite' | 'crossref'

    def lookup(self, bare_doi: str) -> ProviderResponse:
        """Look up ``bare_doi`` and return a provider-neutral response."""
        ...


def _stringify(value) -> str:
    """Coerce a scalar provider value into a stripped string.

    Returns ``''`` for ``None`` so absent fields normalise to empty values.
    """
    if value is None:
        return ''
    return str(value).strip()


_SENSITIVE_KEY_PARTS = (
    'password',
    'secret',
    'token',
    'authorization',
    'credential',
    'api_key',
    'api-key',
    'apikey',
    'access_key',
    'private_key',
    'stack_trace',
    'stacktrace',
    'traceback',
    'trace',
)


def _sanitize_provider_metadata(value):
    """Return a JSON-safe provider metadata copy for UI display.

    The provider APIs should only return public metadata, but this keeps the
    resolver defensive if an upstream response unexpectedly includes internals.
    """
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, child in value.items():
            key_text = _stringify(key)
            lowered = key_text.lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                clean[key_text] = '[redacted]'
            else:
                clean[key_text] = _sanitize_provider_metadata(child)
        return clean
    if isinstance(value, list):
        return [_sanitize_provider_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _stringify(value)


class DataCiteClient:
    """Provider_Client that queries the DataCite REST API.

    Performs ``GET {datacite_api_url}/{bare_doi}`` (default base
    ``https://api.datacite.org/dois``) and maps fields from
    ``data.attributes``.
    """

    source = 'datacite'

    def __init__(self, api_url: str, timeout: float):
        # Trailing slashes are trimmed so URL construction stays predictable.
        self.api_url = api_url.rstrip('/')
        self.timeout = timeout

    def lookup(self, bare_doi: str) -> ProviderResponse:
        url = '{base}/{doi}'.format(base=self.api_url, doi=bare_doi)
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={'Accept': 'application/json'},
            )
        except requests.Timeout:
            return ProviderResponse(ProviderLookup.ERROR)
        except requests.RequestException:
            return ProviderResponse(ProviderLookup.ERROR)

        if response.status_code == 404:
            return ProviderResponse(ProviderLookup.NOT_FOUND)
        if not 200 <= response.status_code < 300:
            return ProviderResponse(ProviderLookup.ERROR)

        try:
            payload = response.json()
        except ValueError:
            return ProviderResponse(ProviderLookup.ERROR)

        record = self._parse(payload)
        if record is None:
            return ProviderResponse(ProviderLookup.ERROR)
        return ProviderResponse(ProviderLookup.FOUND, record)

    def _parse(self, payload) -> Optional[ProviderRecord]:
        """Map a DataCite ``data.attributes`` body into a ``ProviderRecord``."""
        if not isinstance(payload, dict):
            return None
        data = payload.get('data')
        if not isinstance(data, dict):
            return None
        attributes = data.get('attributes')
        if not isinstance(attributes, dict):
            return None

        return ProviderRecord(
            source=self.source,
            title=self._first_title(attributes.get('titles')),
            description=self._first_description(attributes.get('descriptions')),
            creators=self._creators(attributes.get('creators')),
            publisher=_stringify(attributes.get('publisher')),
            publication_year=_stringify(attributes.get('publicationYear')),
            provider_metadata=_sanitize_provider_metadata(payload),
        )

    @staticmethod
    def _first_title(titles) -> str:
        """Extract ``titles[0].title``."""
        if isinstance(titles, list):
            for entry in titles:
                if isinstance(entry, dict):
                    title = _stringify(entry.get('title'))
                    if title:
                        return title
        return ''

    @staticmethod
    def _first_description(descriptions) -> str:
        """Extract a description, preferring ``descriptionType == 'Abstract'``.

        Falls back to the first non-empty description that is not a
        ``TechnicalInfo`` block, and only then to any non-empty description.
        TechnicalInfo carries Model/Instrument Type conventions, so it should
        not become the main description when a real abstract exists.
        """
        if not isinstance(descriptions, list):
            return ''

        abstract = ''
        first_non_technical = ''
        first_any = ''
        for entry in descriptions:
            if not isinstance(entry, dict):
                continue
            text = _stringify(entry.get('description'))
            if not text:
                continue
            dtype = _stringify(entry.get('descriptionType'))
            if not first_any:
                first_any = text
            if dtype == 'Abstract' and not abstract:
                abstract = text
            if dtype != 'TechnicalInfo' and not first_non_technical:
                first_non_technical = text

        return abstract or first_non_technical or first_any

    @staticmethod
    def _creators(creators) -> List[str]:
        """Extract ``creators[].name``, skipping empty/malformed entries."""
        names: List[str] = []
        if isinstance(creators, list):
            for entry in creators:
                if isinstance(entry, dict):
                    name = _stringify(entry.get('name'))
                    if name:
                        names.append(name)
        return names


class CrossrefClient:
    """Provider_Client that queries the Crossref REST API.

    Performs ``GET {crossref_api_url}/{bare_doi}`` (default base
    ``https://api.crossref.org/works``) and maps fields from ``message``.
    """

    source = 'crossref'

    def __init__(self, api_url: str, timeout: float):
        self.api_url = api_url.rstrip('/')
        self.timeout = timeout

    def lookup(self, bare_doi: str) -> ProviderResponse:
        url = '{base}/{doi}'.format(base=self.api_url, doi=bare_doi)
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={'Accept': 'application/json'},
            )
        except requests.Timeout:
            return ProviderResponse(ProviderLookup.ERROR)
        except requests.RequestException:
            return ProviderResponse(ProviderLookup.ERROR)

        if response.status_code == 404:
            return ProviderResponse(ProviderLookup.NOT_FOUND)
        if not 200 <= response.status_code < 300:
            return ProviderResponse(ProviderLookup.ERROR)

        try:
            payload = response.json()
        except ValueError:
            return ProviderResponse(ProviderLookup.ERROR)

        record = self._parse(payload)
        if record is None:
            return ProviderResponse(ProviderLookup.ERROR)
        return ProviderResponse(ProviderLookup.FOUND, record)

    def _parse(self, payload) -> Optional[ProviderRecord]:
        """Map a Crossref ``message`` body into a ``ProviderRecord``."""
        if not isinstance(payload, dict):
            return None
        message = payload.get('message')
        if not isinstance(message, dict):
            return None

        return ProviderRecord(
            source=self.source,
            title=self._first_title(message.get('title')),
            description=_stringify(message.get('abstract')),
            creators=self._authors(message.get('author')),
            publisher=_stringify(message.get('publisher')),
            publication_year=self._year(message),
            provider_metadata=_sanitize_provider_metadata(payload),
        )

    @staticmethod
    def _first_title(title) -> str:
        """Extract ``title[0]`` from the Crossref title array."""
        if isinstance(title, list):
            for entry in title:
                value = _stringify(entry)
                if value:
                    return value
        return _stringify(title) if isinstance(title, str) else ''

    @staticmethod
    def _authors(authors) -> List[str]:
        """Compose ``author[]`` names from ``given``/``family`` or ``name``."""
        names: List[str] = []
        if isinstance(authors, list):
            for entry in authors:
                if not isinstance(entry, dict):
                    continue
                given = _stringify(entry.get('given'))
                family = _stringify(entry.get('family'))
                if given and family:
                    names.append('{given} {family}'.format(
                        given=given, family=family))
                elif family:
                    names.append(family)
                elif given:
                    names.append(given)
                else:
                    name = _stringify(entry.get('name'))
                    if name:
                        names.append(name)
        return names

    @staticmethod
    def _year(message) -> str:
        """Extract the year from ``issued.date-parts[0][0]``.

        Falls back to the same path under ``published`` when ``issued`` carries
        no usable year.
        """
        for key in ('issued', 'published'):
            container = message.get(key)
            if not isinstance(container, dict):
                continue
            date_parts = container.get('date-parts')
            if not isinstance(date_parts, list) or not date_parts:
                continue
            first = date_parts[0]
            if not isinstance(first, list) or not first:
                continue
            year = _stringify(first[0])
            if year:
                return year
        return ''
