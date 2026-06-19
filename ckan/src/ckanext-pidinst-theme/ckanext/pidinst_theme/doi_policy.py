import logging
import re
from urllib.parse import urlparse

import ckan.plugins.toolkit as tk


log = logging.getLogger(__name__)

SYSTEM = 'system'
EXTERNAL = 'external'
VALID_SOURCES = {SYSTEM, EXTERNAL}

IDENTIFIER_SOURCE_FIELD = 'identifier_source'
IDENTIFIER_URL_FIELD = 'identifier_url'
DOI_FIELD = 'doi'
STALE_SOURCE_FIELD = 'doi_source'
STALE_EXTERNAL_URL_FIELD = 'external_identifier_url'
STALE_IDENTIFIER_FIELDS = (STALE_SOURCE_FIELD, STALE_EXTERNAL_URL_FIELD)

_DOI_RE = re.compile(r'^10\.\d{4,9}/[-._;()/:A-Z0-9]+$', re.IGNORECASE)
_DOI_PREFIX_RE = re.compile(
    r'^(?:'
    r'doi:\s*|'
    r'https?://(?:dx\.)?doi\.org/|'
    r'https?://(?:handle(?:\.test)?|doi\.test|api(?:\.test)?)\.datacite\.org/(?:dois/)?'
    r')',
    re.IGNORECASE,
)


def _as_str(value, default=''):
    if isinstance(value, list):
        value = next((v for v in value if v not in (None, '')), default)
    if value is None or value is tk.missing:
        return default
    return str(value).strip()


def doi_resolver_url():
    return tk.config.get('ckanext.doi.resolver_url', 'https://doi.org/').rstrip('/')


def normalize_doi(value):
    """Return a bare DOI string, e.g. ``10.xxxx/yyyy``."""
    doi = _as_str(value)
    doi = _DOI_PREFIX_RE.sub('', doi).strip()
    return doi


def is_valid_doi(value):
    return bool(_DOI_RE.match(normalize_doi(value)))


def normalize_identifier_url(value):
    """Return the submitted identifier URL with only surrounding whitespace removed."""
    return _as_str(value)


def is_valid_identifier_url(value):
    url = normalize_identifier_url(value)
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def _source_from_fields(pkg_dict, default=None):
    if not pkg_dict:
        return default
    raw = _as_str(pkg_dict.get(IDENTIFIER_SOURCE_FIELD), '').lower()
    if raw:
        return raw if raw in VALID_SOURCES else default
    stale_raw = _as_str(pkg_dict.get(STALE_SOURCE_FIELD), '').lower()
    if stale_raw:
        return stale_raw if stale_raw in VALID_SOURCES else default
    return default


def get_identifier_source(pkg_dict):
    return _source_from_fields(pkg_dict, SYSTEM)


def is_external_identifier(pkg_dict):
    return get_identifier_source(pkg_dict) == EXTERNAL


def _system_doi_from_store(pkg_dict):
    package_id = _as_str((pkg_dict or {}).get('id'))
    if not package_id:
        return ''

    try:
        from ckanext.doi.model.crud import DOIQuery
    except ImportError:
        log.debug('ckanext-doi unavailable while resolving system DOI')
        return ''

    try:
        doi_record = DOIQuery.read_package(package_id, create_if_none=False)
    except Exception:
        log.exception(
            'Could not read system DOI for package id=%r',
            package_id,
        )
        return ''

    return normalize_doi(getattr(doi_record, 'identifier', '')) if doi_record else ''


def _system_doi(pkg_dict):
    doi = normalize_doi((pkg_dict or {}).get(DOI_FIELD))
    return doi or _system_doi_from_store(pkg_dict)


def _external_identifier_url(pkg_dict):
    for field_name in (IDENTIFIER_URL_FIELD, STALE_EXTERNAL_URL_FIELD):
        url = normalize_identifier_url((pkg_dict or {}).get(field_name))
        if is_valid_identifier_url(url):
            return url

    doi = normalize_doi((pkg_dict or {}).get(DOI_FIELD))
    if doi:
        return '{}/{}'.format(doi_resolver_url(), doi)

    return ''


def get_identifier_url(pkg_dict):
    if is_external_identifier(pkg_dict):
        return _external_identifier_url(pkg_dict)

    doi = _system_doi(pkg_dict)
    if not doi:
        return ''
    return '{}/{}'.format(doi_resolver_url(), doi)


def get_identifier_display_value(pkg_dict):
    if is_external_identifier(pkg_dict):
        return get_identifier_url(pkg_dict)
    return _system_doi(pkg_dict)


def get_identifier_label(pkg_dict):
    return 'External identifier' if is_external_identifier(pkg_dict) else 'System DOI'


def should_manage_doi(pkg_dict):
    should_manage = not is_external_identifier(pkg_dict)
    log.debug(
        'PIDINST doi_policy.should_manage_doi id=%r name=%r '
        'identifier_source=%r identifier_url=%r doi=%r result=%s',
        (pkg_dict or {}).get('id'),
        (pkg_dict or {}).get('name'),
        (pkg_dict or {}).get(IDENTIFIER_SOURCE_FIELD),
        (pkg_dict or {}).get(IDENTIFIER_URL_FIELD),
        (pkg_dict or {}).get(DOI_FIELD),
        should_manage,
    )
    return should_manage


def _requested_identifier_source(data_dict, existing_source=None):
    raw_source = _as_str(data_dict.get(IDENTIFIER_SOURCE_FIELD), '').lower()
    if raw_source and raw_source not in VALID_SOURCES:
        raise tk.ValidationError({
            IDENTIFIER_SOURCE_FIELD: ['Identifier source must be system or external.']
        })
    return raw_source or existing_source or SYSTEM


def _submitted_identifier_url(data_dict, existing_pkg=None):
    url = normalize_identifier_url(data_dict.get(IDENTIFIER_URL_FIELD))
    if url:
        return url

    if existing_pkg:
        return _external_identifier_url(existing_pkg)

    return ''


def prepare_for_write(data_dict, existing_pkg=None):
    """Validate and normalize identifier fields before package writes.

    ``identifier_source`` is immutable once a package exists. System-managed
    records must not persist submitted ``doi`` or external identifier URL
    extras because ckanext-doi owns their DOI.
    """
    existing_source = _source_from_fields(existing_pkg, None)
    log.debug(
        'PIDINST doi_policy.prepare_for_write incoming id=%r type=%r '
        'identifier_source=%r identifier_url=%r doi=%r '
        'existing_source=%r existing_identifier_url=%r existing_doi=%r',
        data_dict.get('id'),
        data_dict.get('type'),
        data_dict.get(IDENTIFIER_SOURCE_FIELD),
        data_dict.get(IDENTIFIER_URL_FIELD),
        data_dict.get(DOI_FIELD),
        existing_source,
        (existing_pkg or {}).get(IDENTIFIER_URL_FIELD),
        (existing_pkg or {}).get(DOI_FIELD),
    )

    source_submitted = IDENTIFIER_SOURCE_FIELD in data_dict
    requested_source = (
        _requested_identifier_source(data_dict, existing_source)
        if source_submitted
        else (existing_source or SYSTEM)
    )

    if existing_source and source_submitted and requested_source != existing_source:
        raise tk.ValidationError({
            IDENTIFIER_SOURCE_FIELD: ['Identifier source cannot be changed after creation.']
        })

    source = existing_source or requested_source
    data_dict[IDENTIFIER_SOURCE_FIELD] = source
    for field_name in STALE_IDENTIFIER_FIELDS:
        data_dict.pop(field_name, None)

    if source == SYSTEM:
        data_dict.pop(IDENTIFIER_URL_FIELD, None)
        data_dict.pop(DOI_FIELD, None)
        log.debug(
            'PIDINST doi_policy.prepare_for_write system output id=%r '
            'identifier_source=%r identifier_url_present=%s doi_present=%s',
            data_dict.get('id'),
            data_dict.get(IDENTIFIER_SOURCE_FIELD),
            IDENTIFIER_URL_FIELD in data_dict,
            DOI_FIELD in data_dict,
        )
        return data_dict

    identifier_url = normalize_identifier_url(
        _submitted_identifier_url(data_dict, existing_pkg)
    )
    if not identifier_url:
        raise tk.ValidationError({
            IDENTIFIER_URL_FIELD: ['Identifier URL is required for manual records.']
        })
    if not is_valid_identifier_url(identifier_url):
        raise tk.ValidationError({
            IDENTIFIER_URL_FIELD: ['Enter a valid http or https identifier URL.']
        })

    data_dict[IDENTIFIER_URL_FIELD] = identifier_url
    data_dict.pop(DOI_FIELD, None)
    log.debug(
        'PIDINST doi_policy.prepare_for_write external output id=%r '
        'identifier_source=%r identifier_url=%r doi_present=%s',
        data_dict.get('id'),
        data_dict.get(IDENTIFIER_SOURCE_FIELD),
        data_dict.get(IDENTIFIER_URL_FIELD),
        DOI_FIELD in data_dict,
    )
    return data_dict


def decorate_external_show(pkg_dict):
    """Backward-compatible wrapper."""
    return decorate_show(pkg_dict)


def decorate_show(pkg_dict):
    source = get_identifier_source(pkg_dict)
    pkg_dict[IDENTIFIER_SOURCE_FIELD] = source
    pkg_dict['identifier_source_label'] = get_identifier_label(pkg_dict)
    pkg_dict['manual_record'] = source == EXTERNAL

    if source == EXTERNAL:
        identifier_url = get_identifier_url(pkg_dict)
        if identifier_url:
            pkg_dict[IDENTIFIER_URL_FIELD] = identifier_url
        # External/manual records must not expose a bare/system DOI value.
        pkg_dict.pop(DOI_FIELD, None)
        pkg_dict['doi_external'] = True
        log.debug(
            'PIDINST doi_policy.decorate_show external id=%r '
            'identifier_source=%r identifier_url=%r',
            pkg_dict.get('id'),
            pkg_dict.get(IDENTIFIER_SOURCE_FIELD),
            pkg_dict.get(IDENTIFIER_URL_FIELD),
        )
    else:
        doi = get_identifier_display_value(pkg_dict)
        if doi:
            pkg_dict[DOI_FIELD] = doi

    return pkg_dict


def decorate_index(pkg_dict):
    source = get_identifier_source(pkg_dict)
    pkg_dict[IDENTIFIER_SOURCE_FIELD] = source
    if source == EXTERNAL:
        identifier_url = get_identifier_url(pkg_dict)
        if identifier_url:
            pkg_dict[IDENTIFIER_URL_FIELD] = identifier_url
        pkg_dict.pop(DOI_FIELD, None)
    return pkg_dict
