"""Resolver orchestration for the DOI/URL metadata resolution pipeline.

The Resolver ties the pure pieces of the pipeline together: it normalises the
raw identifier, drives the DataCite-first / Crossref-fallback provider lookup
order for DOIs, or delegates to the URL metadata client for arbitrary URLs,
and asks the Mapper to compute the display metadata and the restricted set of
resolved form fields. It returns a single, uniform
:class:`~ckanext.pidinst_theme.doi_resolution.types.ResolveResult` envelope.

This module is intentionally free of any CKAN imports and performs no network
or HTTP work itself; all I/O is delegated to the injected Provider_Clients or
the URL metadata client (which can be mocked in tests).

Lookup-order semantics for DOIs:

* DataCite is queried first using the bare DOI.
* A DataCite ``FOUND`` is used with ``source='datacite'`` and Crossref is *not*
  queried.
* A DataCite ``ERROR`` short-circuits to ``status='fetch_error'``.
* A DataCite ``NOT_FOUND`` triggers a Crossref lookup with the same bare DOI.
* A Crossref ``FOUND`` is used with ``source='crossref'``; a Crossref ``ERROR``
  yields ``fetch_error``; a Crossref ``NOT_FOUND`` yields ``not_found``.

For non-DOI URLs:

* The URL is fetched directly by the URL metadata client.
* If the response is a recognised metadata format, the result is ``ok``.
* If the format is unsupported, the result is ``unsupported_format``.
* If the URL is unsafe (SSRF) or unreachable, the result is ``fetch_error``.
"""

from __future__ import annotations

from typing import Callable, Optional

from .input_normalizer import normalize_input
from .mapper import Mapper
from .providers import ProviderClient, ProviderLookup, ProviderResponse
from .types import ProviderRecord, ResolveResult
from .url_metadata_client import UrlFetchResult, UrlFetchStatus, fetch_url_metadata


def resolve(
    identifier: str,
    datacite: ProviderClient,
    crossref: ProviderClient,
    mapper: Mapper,
    url_fetcher: Optional[Callable[..., UrlFetchResult]] = None,
) -> ResolveResult:
    """Resolve ``identifier`` into a uniform :class:`ResolveResult`.

    Args:
        identifier: The raw identifier input (bare DOI, ``doi:`` form, DOI URL,
            or arbitrary http/https URL) supplied by the registrar.
        datacite: The Provider_Client queried first for DOI inputs.
        crossref: The Provider_Client queried as a fallback when DataCite
            reports no record (DOI inputs only).
        mapper: The Mapper used to build the fetched metadata and resolved
            form fields for a found record.
        url_fetcher: Optional callable for fetching arbitrary URL metadata.
            Defaults to :func:`fetch_url_metadata` if not provided.

    Returns:
        A :class:`ResolveResult` whose ``status`` is one of ``ok``,
        ``invalid_input``, ``not_found``, ``fetch_error``, or
        ``unsupported_format``.
    """
    # 1. Normalise.
    norm = normalize_input(identifier)
    if not norm.is_valid:
        return ResolveResult(status='invalid_input')

    # 2. Route based on input type.
    if norm.is_doi:
        return _resolve_doi(norm, datacite, crossref, mapper)
    else:
        return _resolve_url(norm, mapper, url_fetcher)


def _resolve_doi(norm, datacite, crossref, mapper) -> ResolveResult:
    """Resolve a DOI via DataCite-first / Crossref-fallback."""
    # DataCite first.
    dc = datacite.lookup(norm.bare_doi)
    if dc.outcome == ProviderLookup.ERROR:
        return ResolveResult(status='fetch_error')
    if dc.outcome == ProviderLookup.FOUND:
        return _build_ok_result(
            source='datacite',
            response=dc,
            norm=norm,
            mapper=mapper,
        )

    # DataCite NOT_FOUND -> Crossref fallback.
    cr = crossref.lookup(norm.bare_doi)
    if cr.outcome == ProviderLookup.ERROR:
        return ResolveResult(status='fetch_error')
    if cr.outcome == ProviderLookup.FOUND:
        return _build_ok_result(
            source='crossref',
            response=cr,
            norm=norm,
            mapper=mapper,
        )

    # Neither provider returned a record.
    return ResolveResult(status='not_found')


def _resolve_url(norm, mapper, url_fetcher) -> ResolveResult:
    """Resolve an arbitrary URL by fetching and parsing it."""
    fetcher = url_fetcher if url_fetcher is not None else fetch_url_metadata

    result = fetcher(norm.identifier_url)

    if result.status == UrlFetchStatus.UNSAFE_URL:
        return ResolveResult(status='fetch_error')

    if result.status == UrlFetchStatus.FETCH_ERROR:
        return ResolveResult(status='fetch_error')

    if result.status == UrlFetchStatus.UNSUPPORTED_FORMAT:
        return ResolveResult(status='unsupported_format')

    if result.status == UrlFetchStatus.OK and result.record is not None:
        return _build_url_ok_result(
            source=result.source or result.record.source,
            record=result.record,
            norm=norm,
            mapper=mapper,
        )

    # Shouldn't reach here, but treat as unsupported
    return ResolveResult(status='unsupported_format')


def _build_ok_result(
    source: str,
    response: ProviderResponse,
    norm,
    mapper: Mapper,
) -> ResolveResult:
    """Assemble an ``ok`` :class:`ResolveResult` from a found DOI provider record."""
    record = response.record if response.record is not None else ProviderRecord(
        source=source,
    )
    fetched, resolved_fields, warnings = mapper.map(record, norm.identifier_url)
    return ResolveResult(
        status='ok',
        source=source,
        doi=norm.bare_doi,
        identifier_url=norm.identifier_url,
        fetched=fetched,
        resolved_fields=resolved_fields,
        warnings=warnings,
    )


def _build_url_ok_result(
    source: str,
    record: ProviderRecord,
    norm,
    mapper: Mapper,
) -> ResolveResult:
    """Assemble an ``ok`` :class:`ResolveResult` from URL-fetched metadata.

    For non-DOI URLs:
    - ``doi`` is left empty (no real DOI present)
    - ``identifier_url`` is the original user-entered URL
    - ``resolved_fields.identifier_url`` is also the original URL
    """
    fetched, resolved_fields, warnings = mapper.map(record, norm.identifier_url)
    return ResolveResult(
        status='ok',
        source=source,
        doi='',  # No DOI for arbitrary URL inputs
        identifier_url=norm.identifier_url,
        fetched=fetched,
        resolved_fields=resolved_fields,
        warnings=warnings,
    )
