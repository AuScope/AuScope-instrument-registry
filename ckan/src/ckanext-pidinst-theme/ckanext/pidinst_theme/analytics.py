"""
Analytics tracking helpers for backend events
Integrates with RudderStack for server-side event tracking
"""

import os
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event name constants — always use these; never hard-code event strings.
# Names match the requirements table exactly.
# ---------------------------------------------------------------------------
EVENT_SEARCH = 'Search'
EVENT_EMPTY_RESULT_SEARCH = 'Empty-Result Search'
EVENT_SEARCH_RESULT_CLICK_THROUGH = 'Search Result Click-Through'
EVENT_DATASET_PAGE_VIEW = 'Dataset Page View'
EVENT_DOWNLOAD = 'Download'
EVENT_TIME_TO_FIRST_DOWNLOAD = 'Time To First Download'
EVENT_DATASET_CREATED = 'Dataset Created'
EVENT_DATASET_PUBLISHED_WITH_DOI = 'Dataset Published With DOI'
EVENT_UPDATE_EXISTING_DATASET = 'Update Existing Dataset'
EVENT_DOI_BASED_CITATION = 'DOI-Based Citation'
EVENT_RESOURCE_PREVIEW_OPENED = 'Resource Preview Opened'
EVENT_DATASET_VIEW_DURATION = 'Dataset View Duration'
EVENT_DATASET_REUSE_CREATED = 'Dataset Reuse Created'

# ---------------------------------------------------------------------------
# Known frontend event names — used to whitelist the /api/analytics/track
# endpoint.  Only events defined above are accepted from the browser.
# ---------------------------------------------------------------------------
KNOWN_FRONTEND_EVENTS = frozenset({
    EVENT_SEARCH,
    EVENT_EMPTY_RESULT_SEARCH,
    EVENT_SEARCH_RESULT_CLICK_THROUGH,
    EVENT_DATASET_PAGE_VIEW,
    EVENT_DOWNLOAD,
    EVENT_TIME_TO_FIRST_DOWNLOAD,
    EVENT_DATASET_CREATED,
    EVENT_DATASET_PUBLISHED_WITH_DOI,
    EVENT_UPDATE_EXISTING_DATASET,
    EVENT_DOI_BASED_CITATION,
    EVENT_RESOURCE_PREVIEW_OPENED,
    EVENT_DATASET_VIEW_DURATION,
})

# Try to import RudderStack SDK
try:
    from rudderstack.analytics import Client
    RUDDERSTACK_AVAILABLE = True
except ImportError:
    RUDDERSTACK_AVAILABLE = False
    log.error(
        "RudderStack Python SDK not available — ALL backend analytics events will be "
        "silently dropped. Fix: add 'rudder-sdk-python' to requirements.txt and rebuild "
        "the Docker image."
    )


class AnalyticsTracker:
    """Server-side analytics event tracker using RudderStack"""
    
    _client = None
    _enabled = False
    _initialized = False  # guard: prevent repeated init attempts

    @classmethod
    def initialize(cls):
        """Initialize RudderStack client from environment variables.
        Safe to call multiple times; only runs once.
        """
        if cls._initialized:
            return
        cls._initialized = True

        if not RUDDERSTACK_AVAILABLE:
            log.error(
                "AnalyticsTracker.initialize(): RudderStack SDK unavailable — "
                "backend events will not be sent."
            )
            return

        write_key = os.environ.get('RUDDERSTACK_WRITE_KEY', '')
        data_plane_url = os.environ.get('RUDDERSTACK_DATA_PLANE_URL', '')
        enabled = os.environ.get('RUDDERSTACK_ENABLED', 'false').lower() == 'true'

        if enabled and write_key and data_plane_url:
            try:
                cls._client = Client(
                    write_key=write_key,
                    host=data_plane_url,
                    gzip=True,
                    max_retries=3
                )
                cls._enabled = True
                log.info("RudderStack analytics initialized successfully")
            except Exception as e:
                log.error(f"Failed to initialize RudderStack: {e}")
                cls._enabled = False
        elif not enabled:
            log.warning(
                "AnalyticsTracker.initialize(): RUDDERSTACK_ENABLED is not 'true' — "
                "backend events will not be sent."
            )
        else:
            log.error(
                "AnalyticsTracker.initialize(): RUDDERSTACK_ENABLED=true but "
                "WRITE_KEY or DATA_PLANE_URL is missing — backend events will not be sent."
            )

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if analytics tracking is enabled"""
        if not cls._initialized:
            cls.initialize()
        return cls._enabled
    
    @classmethod
    def track(cls, event: str, properties: Dict[str, Any]) -> bool:
        """Track an event. Returns True if the event was sent successfully.

        Uses get_analytics_user_id() to resolve the user_id:
        - Logged-in users: CKAN internal user UUID.
        - Anonymous users: stable pidinst_browser_id browser UUID.
        Never sends anonymous_id; user_id always carries the stable identifier.
        A copy of properties is made before adding context fields so that the
        caller's dict is never mutated.
        """
        if not cls.is_enabled():
            log.debug(f"Analytics disabled, skipping event: {event}")
            return False

        try:
            props = dict(properties)

            if 'user_type' not in props:
                props['user_type'] = get_user_type()
            if 'timestamp' not in props:
                props['timestamp'] = datetime.utcnow().isoformat()
            props['environment'] = os.environ.get('CKAN_SITE_URL', 'unknown')

            cls._client.track(
                user_id=get_analytics_user_id(),
                event=event,
                properties=props
            )

            log.debug(f"Tracked event: {event}")
            return True

        except Exception as e:
            log.error(f"Failed to track event {event}: {e}")
            return False


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

def get_logged_in_user_id() -> Optional[str]:
    """Return the CKAN internal user UUID when a user is currently logged in.

    Resolution order:
    1. ``ckan.common.current_user.id`` — flask-login user (CKAN 2.9+).
    2. ``toolkit.c.userobj.id``         — legacy CKAN context object.

    Returns ``None`` for anonymous users, when no request context exists
    (CLI, background jobs), or when any lookup raises an exception.
    Never returns a username, email, or display name — only the UUID field.
    """
    try:
        from ckan.common import current_user  # noqa: PLC0415
        if current_user and current_user.is_authenticated:
            uid = getattr(current_user, 'id', None)
            if uid:
                return str(uid)
    except Exception:
        pass
    try:
        from ckan.plugins import toolkit as _toolkit  # noqa: PLC0415
        userobj = getattr(_toolkit.c, 'userobj', None)
        if userobj and getattr(userobj, 'id', None):
            return str(userobj.id)
    except Exception:
        pass
    return None


def get_analytics_user_id() -> str:
    """Return the analytics user_id for the current request.

    For logged-in users: returns the CKAN internal user UUID via
    ``get_logged_in_user_id()``.
    For anonymous users: returns the stable ``pidinst_browser_id`` browser
    UUID via ``get_browser_id()``.

    A string is *always* returned — ``None`` is never returned.
    """
    logged_in_id = get_logged_in_user_id()
    if logged_in_id:
        return logged_in_id
    return get_browser_id()


def get_user_type() -> str:
    """Return 'logged_in' when a user is authenticated, 'anonymous' otherwise.

    Use this single helper to resolve the user_type property that is
    automatically injected into every backend analytics event by
    ``AnalyticsTracker.track()``.  Never returns PII.
    """
    return 'logged_in' if get_logged_in_user_id() else 'anonymous'


def get_browser_id() -> str:
    """Return the stable browser UUID for anonymous users.

    Resolution order (within a Flask request context):
    1. Existing ``pidinst_browser_id`` cookie — reuse it unchanged.
    2. ``flask.g.pidinst_browser_id_to_set`` — a UUID already generated earlier
       in this same request (ensures two events in one request share the same ID).
    3. Generate a fresh ``uuid.uuid4()``, store it on ``g`` so the
       ``after_app_request`` hook can write it as a cookie on the response.

    Outside a Flask request context (CLI, background jobs, tests without a
    request context) a fresh UUID is returned without touching ``g``.
    A string is *always* returned — ``None`` is never returned.
    """
    try:
        from flask import request as _flask_request, g as _flask_g  # noqa: PLC0415
        existing = _flask_request.cookies.get('pidinst_browser_id')
        if existing:
            return existing
        # Re-use the ID already generated for this request (e.g. second event).
        stored = getattr(_flask_g, 'pidinst_browser_id_to_set', None)
        if stored:
            return stored
        # First event in this request with no cookie — generate and stash.
        new_id = str(uuid.uuid4())
        _flask_g.pidinst_browser_id_to_set = new_id
        return new_id
    except Exception:
        # Outside a request context — return a UUID without touching g.
        return str(uuid.uuid4())


def set_browser_id_cookie(response):
    """Set pidinst_browser_id on *response* when a new UUID was generated this request.

    Called by the ``after_app_request`` hook registered in views.py.  When
    ``get_browser_id()`` had to generate a fresh UUID (no incoming cookie), it
    stored the value on ``flask.g.pidinst_browser_id_to_set``.  This function
    reads that value and writes it as a long-lived first-party cookie so that
    subsequent requests and frontend JS use the same stable identifier.

    The cookie is intentionally readable by JavaScript (no ``httponly``) because
    ``analytics-tracking.js`` passes it to ``rudderanalytics.setAnonymousId()``.
    ``samesite='Lax'`` prevents cross-site request forgery for the cookie itself.
    """
    try:
        from flask import g as _flask_g  # noqa: PLC0415
        browser_id = getattr(_flask_g, 'pidinst_browser_id_to_set', None)
        if browser_id:
            response.set_cookie(
                'pidinst_browser_id',
                browser_id,
                max_age=365 * 24 * 60 * 60,  # 1 year
                samesite='Lax',
            )
    except Exception:
        pass
    return response


# ---------------------------------------------------------------------------
# Property helpers
# ---------------------------------------------------------------------------

def _dataset_type_from_pkg(pkg_dict: Dict[str, Any]) -> str:
    """Derive dataset_type from the is_platform field.

    Returns 'platform', 'instrument', or 'unknown'.
    Handles both boolean and string representations stored by CKAN extras.
    """
    val = pkg_dict.get('is_platform')
    if val in (True, 'true', 'True', '1', 1):
        return 'platform'
    if val in (False, 'false', 'False', '0', 0):
        return 'instrument'
    return 'unknown'


def _is_public_from_pkg(pkg_dict: Dict[str, Any]) -> Optional[bool]:
    """Derive is_public from the private field.

    Returns True, False, or None when the field is absent.
    """
    if 'private' not in pkg_dict:
        return None
    return not pkg_dict['private']


def _has_doi_from_pkg(pkg_dict: Dict[str, Any]) -> bool:
    """Return True only when a non-empty DOI value exists in the package dict."""
    return bool(pkg_dict.get('doi'))


def minimal_dataset_props(pkg_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Return the minimal analytics property dict for a dataset/package event.

    Sends only: dataset_id, dataset_type, is_public, has_doi.
    Never sends title, name, description, username, email, or the full DOI value.
    """
    return {
        'dataset_id': pkg_dict.get('id'),
        'dataset_type': _dataset_type_from_pkg(pkg_dict),
        'is_public': _is_public_from_pkg(pkg_dict),
        'has_doi': _has_doi_from_pkg(pkg_dict),
    }


def file_size_group(size_bytes: Optional[int]) -> str:
    """Bucket a raw file size into a named group for analytics.

    Returns 'small' (< 10 MB), 'medium' (< 500 MB), 'large' (>= 500 MB),
    or 'unknown' when the size is not available or cannot be parsed.
    The raw byte value must not be sent in the analytics payload.
    """
    if size_bytes is None:
        return 'unknown'
    try:
        size_bytes = int(size_bytes)
    except (TypeError, ValueError):
        return 'unknown'
    if size_bytes < 10 * 1024 * 1024:
        return 'small'
    if size_bytes < 500 * 1024 * 1024:
        return 'medium'
    return 'large'



# ---------------------------------------------------------------------------
# Event tracking helper functions
# ---------------------------------------------------------------------------

def track_dataset_created(dataset_dict: Dict[str, Any]):
    """Track dataset creation event (EVENT_DATASET_CREATED)."""
    AnalyticsTracker.track(
        event=EVENT_DATASET_CREATED,
        properties=minimal_dataset_props(dataset_dict),
    )


def track_dataset_updated(dataset_dict: Dict[str, Any]):
    """Track dataset update event (EVENT_UPDATE_EXISTING_DATASET)."""
    AnalyticsTracker.track(
        event=EVENT_UPDATE_EXISTING_DATASET,
        properties=minimal_dataset_props(dataset_dict),
    )


def _doi_status_from_db(package_id: str):
    """Query the ckanext-doi DB table for a package's DOI published status.

    Returns a ``(is_published, status_str)`` tuple:

    * ``(True,  'published')`` – ``doi.published`` timestamp is set.
    * ``(False, 'minted')``    – DOI record exists but ``published`` is None.
    * ``(False, 'none')``      – No DOI record found for this package.
    * ``(False, 'unknown')``   – DOIQuery unavailable or query raised an exception.

    The full DOI identifier value is intentionally never returned.

    NOTE: requires ckanext-doi to be installed.  The import is deferred so
    that analytics.py can be imported in environments where ckanext-doi is
    absent (e.g. minimal unit-test setups).
    """
    try:
        from ckanext.doi.model.crud import DOIQuery  # noqa: PLC0415
        record = DOIQuery.read_package(package_id)
        if record is None:
            return False, 'none'
        if record.published is not None:
            return True, 'published'
        return False, 'minted'
    except Exception:
        return False, 'unknown'


def track_doi_published(dataset_dict: Dict[str, Any],
                        doi_status: Optional[str] = None):
    """Track DOI publication event (EVENT_DATASET_PUBLISHED_WITH_DOI).

    The full DOI value is intentionally NOT sent in the payload.
    """
    props = minimal_dataset_props(dataset_dict)
    props['doi_status'] = doi_status or 'unknown'
    AnalyticsTracker.track(
        event=EVENT_DATASET_PUBLISHED_WITH_DOI,
        properties=props,
    )


# ---------------------------------------------------------------------------
# Stage 3B: Dataset Reuse Created helpers
# ---------------------------------------------------------------------------

def _reuse_source_from_pkg(pkg_dict: Dict[str, Any]) -> Optional[str]:
    """Extract the source (predecessor) dataset ID from a new-version package.

    Looks for the first ``IsNewVersionOf`` entry in ``related_identifier_obj``
    and returns its ``related_instrument_package_id`` value, which is the CKAN
    UUID of the immediate predecessor package.

    Returns ``None`` when:
    - ``related_identifier_obj`` is absent, empty, or unparseable.
    - No ``IsNewVersionOf`` entry exists.
    - The entry has no ``related_instrument_package_id``.

    The related_identifier value (DOI / URL) is intentionally not returned.
    """
    import json as _json  # noqa: PLC0415

    raw = pkg_dict.get('related_identifier_obj')
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, list):
        return None
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if entry.get('relation_type') == 'IsNewVersionOf':
            pkg_id = entry.get('related_instrument_package_id')
            if pkg_id:
                return str(pkg_id)
    return None


def _is_new_version_pkg(pkg_dict: Dict[str, Any]) -> bool:
    """Return True when this package is a new version of an existing one.

    Detection rule:
    - ``version_handler_id`` is set (non-empty) AND differs from the
      package's own ``id``.

    ``version_handler_id`` is set to the original's ``version_handler_id``
    (the root of the version chain) by ``prepare_dataset_for_cloning``.
    For a brand-new dataset ``after_dataset_create`` sets it equal to
    ``pkg_dict['id']``, so the two being different is the safe distinguisher.

    This function is called AFTER the ``version_handler_id`` normalisation
    block in ``after_dataset_create`` so the local ``pkg_dict`` copy is
    always up-to-date.
    """
    vhid = pkg_dict.get('version_handler_id')
    pkg_id = pkg_dict.get('id')
    return bool(vhid and pkg_id and vhid != pkg_id)


def track_dataset_reuse_created(dataset_dict: Dict[str, Any],
                                source_dataset_id: Optional[str] = None):
    """Track dataset reuse event (EVENT_DATASET_REUSE_CREATED).

    Fires only when a new dataset was explicitly created as a new version of
    (or derived from) an existing dataset via the new_version workflow.
    """
    props = minimal_dataset_props(dataset_dict)
    props['reuse_type'] = 'new_version'
    if source_dataset_id:
        props['source_dataset_id'] = source_dataset_id
    AnalyticsTracker.track(
        event=EVENT_DATASET_REUSE_CREATED,
        properties=props,
    )


def track_resource_download(resource_id: str,
                            dataset_id: str, resource_format: str,
                            size_bytes: Optional[int] = None,
                            dataset_type: Optional[str] = None):
    """Track resource download event (EVENT_DOWNLOAD).

    Raw file size is bucketed via file_size_group; the byte value is not sent.
    resource_name is intentionally omitted from the payload.
    """
    props: Dict[str, Any] = {
        'resource_id': resource_id,
        'dataset_id': dataset_id,
        'resource_format': resource_format,
        'file_size_group': file_size_group(size_bytes),
    }
    if dataset_type is not None:
        props['dataset_type'] = dataset_type
    AnalyticsTracker.track(
        event=EVENT_DOWNLOAD,
        properties=props,
    )


# ---------------------------------------------------------------------------
# Filter analytics — safe field whitelist and keyword helpers
# ---------------------------------------------------------------------------

# Internal CKAN facet fields that are safe to include in analytics.
# Do NOT add: fq, q, page, sort, owner_org, id, name, or any field that
# might carry PII or internal identifiers.
_SAFE_FILTER_FIELDS: Dict[str, str] = {
    'vocab_instrument_type_gcmd':      'instrument_type_gcmd',
    'vocab_instrument_type_custom':    'instrument_type_custom',
    'vocab_measured_variable_gcmd':    'measured_variable_gcmd',
    'vocab_measured_variable_custom':  'measured_variable_custom',
    'vocab_instrument_classification': 'instrument_classification',
    'vocab_manufacturer_party':        'manufacturer',
    'owner_party':                     'owner',
}

_FILTER_VALUE_MAX_LEN = 200  # characters; prevents runaway values
_KEYWORD_MAX_LEN = 100       # characters per search keyword
_KEYWORD_MAX_COUNT = 20      # total keywords in search_keywords


def extract_filter_values(params: Any) -> List[str]:
    """Return a flat list of selected filter values from whitelisted CKAN facet fields.

    Only fields in ``_SAFE_FILTER_FIELDS`` are included.  All other keys are
    silently ignored so that internal CKAN fields (``fq``, ``id``,
    ``owner_org``, etc.) can never reach analytics events.

    ``params`` may be:
    - A plain ``dict`` (e.g. ``fields_grouped`` from ``_instrument_platform_search``).
    - A Werkzeug ``MultiDict`` (``request.args``) supporting ``.getlist()``.

    Values are returned raw (not cleaned); callers should pass them through
    ``build_search_keywords()`` which applies ``clean_search_value()`` before
    including them in events.
    """
    values: List[str] = []
    for internal_field in _SAFE_FILTER_FIELDS:
        if hasattr(params, 'getlist'):
            raw: List[Any] = params.getlist(internal_field)
        else:
            raw_val = params.get(internal_field)
            if raw_val is None:
                raw = []
            elif isinstance(raw_val, list):
                raw = raw_val
            else:
                raw = [raw_val]
        values.extend(str(v)[:_FILTER_VALUE_MAX_LEN] for v in raw if v)
    return values


def clean_search_value(value: str) -> str:
    """Return a normalised, chart-friendly version of a search value.

    Applies: strip, lowercase, replace hyphens and underscores with spaces,
    collapse multiple spaces.  Returns an empty string for blank input.
    """
    if not value:
        return ''
    cleaned = value.strip().lower()
    cleaned = cleaned.replace('-', ' ').replace('_', ' ')
    cleaned = ' '.join(cleaned.split())
    return cleaned


def build_search_keywords(search_term: str,
                          selected_filter_values: List[str]) -> List[str]:
    """Build the ``search_keywords`` array for the Search analytics event.

    Combines the typed search term with selected safe filter values into a
    deduplicated, cleaned keyword list bounded by ``_KEYWORD_MAX_COUNT``.

    Rules:
    - The cleaned search term is included first (if non-empty after cleaning).
    - Each filter value is cleaned via ``clean_search_value()`` and appended
      if it is non-empty and not already present.
    - Duplicates are removed (case-insensitive after cleaning).
    - Total keywords are capped at ``_KEYWORD_MAX_COUNT``.
    - Each keyword is capped at ``_KEYWORD_MAX_LEN`` characters.
    """
    keywords: List[str] = []
    seen: set = set()

    term = clean_search_value(search_term)[:_KEYWORD_MAX_LEN]
    if term:
        keywords.append(term)
        seen.add(term)

    for v in selected_filter_values:
        if len(keywords) >= _KEYWORD_MAX_COUNT:
            break
        cleaned = clean_search_value(v)[:_KEYWORD_MAX_LEN]
        if cleaned and cleaned not in seen:
            keywords.append(cleaned)
            seen.add(cleaned)

    return keywords


def build_search_context(search_term: str,
                         search_keywords: Optional[List[str]] = None) -> str:
    """Build a short human-readable summary of the current search for Amplitude grouping.

    Combines the cleaned search term with any extra keywords (from filter
    values) into a single pipe-separated string.

    Format:
        "seismometer"                                    — term only
        "no search term"                                 — neither term nor filters
        "seismometer | sensor"                           — term + one filter value
        "no search term | geophysics | curtin university" — filters only
        "temperature | sensor | pressure"                — term + multiple filters

    ``search_keywords`` is the list returned by ``build_search_keywords()``.
    """
    term = clean_search_value(search_term)
    keywords = search_keywords or []

    if term:
        # Extra keywords are those not equal to the term itself.
        others = [kw for kw in keywords if kw != term]
        parts: List[str] = [term] + others
    else:
        parts = ['no search term'] + keywords

    return ' | '.join(parts)


def track_dataset_search(search_term: str,
                         result_count: int,
                         dataset_type: Optional[str] = None,
                         page_number: Optional[int] = None,
                         sort_by: Optional[str] = None,
                         filter_values: Optional[List[str]] = None):
    """Track search event (EVENT_SEARCH).

    Fires EVENT_SEARCH always.
    Also fires EVENT_EMPTY_RESULT_SEARCH when result_count == 0.

    ``filter_values`` should be the list returned by ``extract_filter_values()``.
    Search keywords and the combined search_context are derived automatically.

    Event properties:
        search_term      — the raw typed query string
        search_keywords  — cleaned list: [term] + cleaned filter values
        search_context   — pipe-joined summary for Amplitude grouping
        result_count     — number of results returned
        is_empty         — True when result_count == 0
    """
    keywords = build_search_keywords(search_term, filter_values or [])

    properties: Dict[str, Any] = {
        'search_term': search_term,
        'search_keywords': keywords,
        'search_context': build_search_context(search_term, keywords),
        'result_count': result_count,
        'is_empty': result_count == 0,
    }

    if dataset_type is not None:
        properties['dataset_type'] = dataset_type
    if page_number is not None:
        properties['page_number'] = page_number
    if sort_by is not None:
        properties['sort_by'] = sort_by

    AnalyticsTracker.track(
        event=EVENT_SEARCH,
        properties=properties,
    )

    if result_count == 0:
        AnalyticsTracker.track(
            event=EVENT_EMPTY_RESULT_SEARCH,
            properties=properties,
        )
