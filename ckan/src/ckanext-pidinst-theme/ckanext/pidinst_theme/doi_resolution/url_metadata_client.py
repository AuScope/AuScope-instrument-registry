"""URL metadata client for fetching metadata from arbitrary http/https URLs.

This module fetches a user-supplied URL directly (no DOI resolution) and
attempts to parse the response as a supported metadata format (DataCite-style
JSON or Crossref-style JSON).

SSRF Protection:
- Only http and https schemes are allowed.
- Localhost, private, link-local, and metadata service IPs are rejected.
- Obvious internal hostnames (.local, .internal, .svc, .cluster.local) are rejected.
- Redirects are followed up to a limit, with each hop validated.
- Response size is capped.

This module is free of CKAN imports and independently testable.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

from .types import ProviderRecord


# --- Configuration constants ---

DEFAULT_TIMEOUT = 10.0
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB

# Content types we consider JSON-parseable
_JSON_CONTENT_TYPES = frozenset({
    'application/json',
    'application/vnd.api+json',
    'application/vnd.datacite.datacite+json',
})

# Hostnames considered internal/unsafe
_UNSAFE_HOSTNAME_SUFFIXES = (
    '.local',
    '.internal',
    '.svc',
    '.cluster.local',
    '.localhost',
)

_UNSAFE_HOSTNAMES = frozenset({
    'localhost',
    'metadata.google.internal',
    'metadata.internal',
})


class UrlFetchStatus:
    """Possible outcomes of a URL metadata fetch."""
    OK = 'ok'
    UNSUPPORTED_FORMAT = 'unsupported_format'
    FETCH_ERROR = 'fetch_error'
    UNSAFE_URL = 'unsafe_url'


@dataclass
class UrlFetchResult:
    """Result of fetching and parsing metadata from a URL."""
    status: str
    record: Optional[ProviderRecord] = None
    source: str = ''


def _is_unsafe_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, link-local, or metadata."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except (ValueError, TypeError):
        return False

    if addr.is_loopback:
        return True
    if addr.is_private:
        return True
    if addr.is_link_local:
        return True
    if addr.is_reserved:
        return True

    # AWS/GCP/Azure metadata service
    metadata_ips = {
        ipaddress.ip_address('169.254.169.254'),
        ipaddress.ip_address('fd00:ec2::254'),
    }
    if addr in metadata_ips:
        return True

    return False


def _is_unsafe_hostname(hostname: str) -> bool:
    """Check if a hostname is obviously internal."""
    if not hostname:
        return True

    lower = hostname.lower().rstrip('.')

    if lower in _UNSAFE_HOSTNAMES:
        return True

    for suffix in _UNSAFE_HOSTNAME_SUFFIXES:
        if lower.endswith(suffix):
            return True

    return False


def _validate_url_safe(url: str) -> bool:
    """Validate that a URL is safe to fetch (not internal/private).

    Returns True if safe, False if unsafe.
    """
    parsed = urlparse(url)

    if parsed.scheme.lower() not in ('http', 'https'):
        return False

    hostname = (parsed.hostname or '').lower().rstrip('.')
    if not hostname:
        return False

    if _is_unsafe_hostname(hostname):
        return False

    # Resolve hostname to check IPs
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443)
    except (socket.gaierror, OSError):
        # Can't resolve - treat as unsafe
        return False

    for family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        if _is_unsafe_ip(ip_str):
            return False

    return True


def _stringify(value) -> str:
    """Coerce a scalar provider value into a stripped string."""
    if value is None:
        return ''
    return str(value).strip()


def _parse_datacite_json(payload: dict) -> Optional[ProviderRecord]:
    """Try to parse as DataCite-style JSON (data.attributes structure)."""
    if not isinstance(payload, dict):
        return None
    data = payload.get('data')
    if not isinstance(data, dict):
        return None
    attributes = data.get('attributes')
    if not isinstance(attributes, dict):
        return None

    # Looks like DataCite format
    title = ''
    titles = attributes.get('titles')
    if isinstance(titles, list):
        for entry in titles:
            if isinstance(entry, dict):
                t = _stringify(entry.get('title'))
                if t:
                    title = t
                    break

    description = ''
    descriptions = attributes.get('descriptions')
    if isinstance(descriptions, list):
        for entry in descriptions:
            if isinstance(entry, dict):
                d = _stringify(entry.get('description'))
                if d:
                    description = d
                    break

    creators = []
    raw_creators = attributes.get('creators')
    if isinstance(raw_creators, list):
        for entry in raw_creators:
            if isinstance(entry, dict):
                name = _stringify(entry.get('name'))
                if name:
                    creators.append(name)

    return ProviderRecord(
        source='datacite',
        title=title,
        description=description,
        creators=creators,
        publisher=_stringify(attributes.get('publisher')),
        publication_year=_stringify(attributes.get('publicationYear')),
        provider_metadata=payload,
    )


def _parse_crossref_json(payload: dict) -> Optional[ProviderRecord]:
    """Try to parse as Crossref-style JSON (message structure)."""
    if not isinstance(payload, dict):
        return None
    message = payload.get('message')
    if not isinstance(message, dict):
        return None

    # Looks like Crossref format
    title = ''
    raw_title = message.get('title')
    if isinstance(raw_title, list) and raw_title:
        title = _stringify(raw_title[0])
    elif isinstance(raw_title, str):
        title = _stringify(raw_title)

    description = _stringify(message.get('abstract'))

    creators = []
    authors = message.get('author')
    if isinstance(authors, list):
        for entry in authors:
            if not isinstance(entry, dict):
                continue
            given = _stringify(entry.get('given'))
            family = _stringify(entry.get('family'))
            if given and family:
                creators.append('{} {}'.format(given, family))
            elif family:
                creators.append(family)
            elif given:
                creators.append(given)
            else:
                name = _stringify(entry.get('name'))
                if name:
                    creators.append(name)

    publisher = _stringify(message.get('publisher'))

    year = ''
    for key in ('issued', 'published'):
        container = message.get(key)
        if not isinstance(container, dict):
            continue
        date_parts = container.get('date-parts')
        if isinstance(date_parts, list) and date_parts:
            first = date_parts[0]
            if isinstance(first, list) and first:
                year = _stringify(first[0])
                if year:
                    break

    return ProviderRecord(
        source='crossref',
        title=title,
        description=description,
        creators=creators,
        publisher=publisher,
        publication_year=year,
        provider_metadata=payload,
    )


class _SafeRedirectAdapter(HTTPAdapter):
    """Adapter that validates each redirect target for SSRF safety."""

    def send(self, request, stream=False, timeout=None, verify=True,
             cert=None, proxies=None):
        # Validate the request URL before sending
        if not _validate_url_safe(request.url):
            raise requests.exceptions.ConnectionError(
                'Redirect to unsafe/internal URL blocked: {}'.format(request.url)
            )
        return super().send(
            request, stream=stream, timeout=timeout, verify=verify,
            cert=cert, proxies=proxies,
        )


def fetch_url_metadata(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = MAX_REDIRECTS,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> UrlFetchResult:
    """Fetch a URL and attempt to parse the response as supported metadata.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.
        max_redirects: Maximum number of redirects to follow.
        max_response_bytes: Maximum response body size to read.

    Returns:
        A UrlFetchResult with status and optional ProviderRecord.
    """
    # Validate the initial URL
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ('http', 'https'):
        return UrlFetchResult(status=UrlFetchStatus.UNSAFE_URL)

    if not _validate_url_safe(url):
        return UrlFetchResult(status=UrlFetchStatus.UNSAFE_URL)

    # Create a session with redirect safety
    session = requests.Session()
    session.max_redirects = max_redirects
    adapter = _SafeRedirectAdapter()
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    try:
        response = session.get(
            url,
            timeout=timeout,
            headers={'Accept': 'application/json'},
            allow_redirects=True,
            stream=True,
        )
    except requests.Timeout:
        return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)
    except requests.TooManyRedirects:
        return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)
    except requests.RequestException:
        return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)
    finally:
        session.close()

    # Validate final URL after redirects
    if response.url and not _validate_url_safe(response.url):
        return UrlFetchResult(status=UrlFetchStatus.UNSAFE_URL)

    if not (200 <= response.status_code < 300):
        return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)

    # Check content type - only parse JSON
    content_type = (response.headers.get('content-type') or '').lower().split(';')[0].strip()
    if content_type not in _JSON_CONTENT_TYPES:
        return UrlFetchResult(status=UrlFetchStatus.UNSUPPORTED_FORMAT)

    # Read response with size limit
    content_length = response.headers.get('content-length')
    if content_length:
        try:
            if int(content_length) > max_response_bytes:
                return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)
        except (ValueError, TypeError):
            pass

    # Read the body with a size cap
    chunks = []
    total_read = 0
    for chunk in response.iter_content(chunk_size=8192):
        total_read += len(chunk)
        if total_read > max_response_bytes:
            return UrlFetchResult(status=UrlFetchStatus.FETCH_ERROR)
        chunks.append(chunk)

    body = b''.join(chunks)

    # Parse JSON
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return UrlFetchResult(status=UrlFetchStatus.UNSUPPORTED_FORMAT)

    if not isinstance(payload, dict):
        return UrlFetchResult(status=UrlFetchStatus.UNSUPPORTED_FORMAT)

    # Try DataCite format first, then Crossref format
    record = _parse_datacite_json(payload)
    if record is not None:
        return UrlFetchResult(
            status=UrlFetchStatus.OK,
            record=record,
            source='datacite',
        )

    record = _parse_crossref_json(payload)
    if record is not None:
        return UrlFetchResult(
            status=UrlFetchStatus.OK,
            record=record,
            source='crossref',
        )

    # JSON but not a recognized metadata format
    return UrlFetchResult(status=UrlFetchStatus.UNSUPPORTED_FORMAT)
