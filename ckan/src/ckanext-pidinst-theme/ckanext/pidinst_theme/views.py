from flask import Blueprint, request, Response, render_template, redirect, url_for, session , jsonify
from flask.views import MethodView
from functools import partial
import requests
import os
import time
from werkzeug.utils import secure_filename
from ckan.plugins.toolkit import get_action, h
import ckan.plugins.toolkit as toolkit
from ckan.common import g
from ckan.common import _, current_user
import ckan.lib.base as base
import ckan.lib.helpers as ckan_helpers
import ckan.logic as logic
import logging
from io import BytesIO
import json
import pandas as pd
from datetime import date
import re
from ckanext.pidinst_theme.logic import (
    email_notifications
)
from ckanext.pidinst_theme.logic.schema import _parse_date_bound, _DATE_FILTER_DEFS
from ckanext.pidinst_theme import analytics_views
from ckanext.pidinst_theme import analytics

check_access = logic.check_access
NotAuthorized = logic.NotAuthorized
NotFound = logic.NotFound
ValidationError = logic.ValidationError

log = logging.getLogger(__name__)

try:
    from ckanext.contact.routes import _helpers
    contact_plugin_available = True
except ImportError:
    contact_plugin_available = False
    log.warning("ckanext-contact plugin is not available. The contact form functionality will be disabled.")


pidinst_theme = Blueprint("pidinst_theme", __name__)


def page():
    return "Hello, pidinst_theme!"


pidinst_theme.add_url_rule("/pidinst_theme/page", view_func=page)


def convert_to_serializable(obj):
    """
    Recursively convert pandas objects to JSON-serializable formats.
    """
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    elif isinstance(obj, pd.Series):
        return obj.to_dict()
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(i) for i in obj]
    else:
        return obj

@pidinst_theme.route('/get_preview_data', methods=['GET'])
def get_preview_data():
    """
    Endpoint to fetch the preview data.
    """
    preview_data = session.get('preview_data', {})
    preview_data_serializable = convert_to_serializable(preview_data)
    return jsonify(preview_data_serializable)

@pidinst_theme.route('/remove_preview_data', methods=['POST'])
def remove_preview_data():
    """
    Endpoint to remove the preview data.
    """
    session.pop('preview_data', None)
    session.pop('file_name', None)
    return "Preview data removed successfully", 200

@pidinst_theme.route('/organization/request_new_organisation', methods=['GET', 'POST'])
def request_new_organisation():
    """
    Form based interaction for requesting a new organisation.
    """
    if not g.user:
        toolkit.abort(403, toolkit._('Unauthorized to send request'))

    extra_vars = {
        'data': {},
        'errors': {},
        'error_summary': {},
    }

    logger = logging.getLogger(__name__)

    try:
        if toolkit.request.method == 'POST':
            email_body = email_notifications.generate_new_organisation_admin_email_body(request)
            request.values = request.values.copy()
            request.values['content'] = email_body

            if contact_plugin_available:
                result = _helpers.submit()
                if result.get('success', False):
                    try:
                        email_notifications.send_new_organisation_requester_confirmation_email(request)
                    except Exception as email_error:
                        logger.error('An error occurred while sending the email to the requester: {}'.format(str(email_error)))

                    return toolkit.render('contact/success.html')
                else:
                    if result.get('recaptcha_error'):
                        toolkit.h.flash_error(result['recaptcha_error'])
                    extra_vars.update(result)
            else:
                toolkit.h.flash_error(toolkit._('Contact functionality is currently unavailable.'))
                return toolkit.redirect_to('/organization')
        else:
            try:
                extra_vars['data']['name'] = g.userobj.fullname or g.userobj.name
                extra_vars['data']['email'] = g.userobj.email
            except AttributeError:
                extra_vars['data']['name'] = extra_vars['data']['email'] = None

        return toolkit.render('contact/req_new_organisation.html', extra_vars=extra_vars)

    except Exception as e:
        toolkit.h.flash_error(toolkit._('An error occurred while processing your request.'))
        logger.error('An error occurred while processing your request: {}'.format(str(e)))
        return toolkit.abort(500, toolkit._('Internal server error'))

@pidinst_theme.route('/organization/request_join_organisation', methods=['GET', 'POST'])
def request_join_organisation():
    """
    Form based interaction for requesting to jon in a organisation.
    """
    if not g.user:
        toolkit.abort(403, toolkit._('Unauthorized to send request'))

    org_id = toolkit.request.args.get('org_id')
    organization = get_action('organization_show')({}, {'id': org_id})
    org_name = organization['name']

    extra_vars = {
        'data': {},
        'errors': {},
        'error_summary': {},
    }
    logger = logging.getLogger(__name__)

    try:
        if toolkit.request.method == 'POST':

            email_body = email_notifications.generate_join_organisation_admin_email_body(request, org_id,org_name)
            request.values = request.values.copy()
            request.values['content'] = email_body

            if contact_plugin_available:
                result = _helpers.submit()
                if result.get('success', False):
                    try:
                        email_notifications.send_join_organisation_requester_confirmation_email(request, organization)
                    except Exception as email_error:
                        logger.error('An error occurred while sending the email to the requester: {}'.format(str(email_error)))

                    return toolkit.render('contact/success.html')
                else:
                    if result.get('recaptcha_error'):
                        toolkit.h.flash_error(result['recaptcha_error'])
                    extra_vars.update(result)
            else:
                toolkit.h.flash_error(toolkit._('Contact functionality is currently unavailable.'))
                return toolkit.redirect_to('/organization')
        else:
            try:
                extra_vars['data']['name'] = g.userobj.fullname or g.userobj.name
                extra_vars['data']['email'] = g.userobj.email
                extra_vars['data']['organisation_id'] = org_id
                extra_vars['data']['organisation_name'] = org_name

            except AttributeError:
                extra_vars['data']['name'] = extra_vars['data']['email'] = None

        return toolkit.render('contact/req_join_organisation.html', extra_vars=extra_vars)
    except Exception as e:
        toolkit.h.flash_error(toolkit._('An error occurred while processing your request.'))
        logger.error('An error occurred while processing your request: {}'.format(str(e)))
        return toolkit.abort(500, toolkit._('Internal server error'))

# Add the proxy route
@pidinst_theme.route('/api/proxy/fetch_epsg', methods=['GET'])
def fetch_epsg():
    page = request.args.get('page', 0)
    keywords = request.args.get('keywords', '')
    external_url = f'https://apps.epsg.org/api/v1/CoordRefSystem/?includeDeprecated=false&pageSize=50&page={page}&keywords={keywords}'

    response = requests.get(external_url)
    if response.ok:
        return Response(response.content, content_type=response.headers['Content-Type'], status=response.status_code)
    else:
        return {"error": "Failed to fetch EPSG codes"}, 502

@pidinst_theme.route('/api/proxy/fetch_terms', methods=['GET'])
def fetch_terms( ):
    page = request.args.get('page', 0)
    keywords = request.args.get('keywords', '')
    external_url = f'https://vocabs.ardc.edu.au/repository/api/lda/anzsrc-2020-for/concept.json?_page={page}&labelcontains={keywords}'

    response = requests.get(external_url)
    if response.ok:
        return Response(response.content, content_type=response.headers['Content-Type'], status=response.status_code)
    else:
        return {"error": "Failed to fetch terms"}, 502

@pidinst_theme.route('/api/proxy/fetch_gcmd', methods=['GET'])
def fetch_gcmd():

    VOCAB_ENDPOINTS = {
        'science': 'ardc-curated/gcmd-sciencekeywords/17-5-2023-12-21',
        'measured_variables': 'ardc-curated/gcmd-measurementname/21-5-2025-06-06',
        'platforms': 'ardc-curated/gcmd-platforms/21-5-2025-06-17',
        'instruments': 'ardc-curated/gcmd-instruments/22-8-2026-02-13',
    }

    try:
        page = int(request.args.get('page', 0))
    except (ValueError, TypeError):
        page = 0

    keywords = request.args.get('keywords', '')
    scheme = request.args.get('scheme', 'science')

    if scheme not in VOCAB_ENDPOINTS:
        log.warning(f"Unknown vocab scheme requested: {scheme}")
        return {"error": f"Unknown scheme: {scheme}"}, 400

    vocab_path = VOCAB_ENDPOINTS[scheme]
    base_url = 'https://vocabs.ardc.edu.au/repository/api/lda'
    external_url = f'{base_url}/{vocab_path}/concept.json?_page={page}&labelcontains={requests.utils.quote(keywords)}'

    log.debug(f"Fetching GCMD vocab: scheme={scheme}, url={external_url}")

    try:
        response = requests.get(external_url, timeout=10)
        if response.ok:
            return Response(response.content, content_type=response.headers['Content-Type'], status=response.status_code)
        else:
            log.error(f"ARDC vocab fetch failed: {response.status_code} - {external_url}")
            return {"error": f"Failed to fetch {scheme} vocabulary", "status": response.status_code}, 502
    except requests.exceptions.RequestException as e:
        log.error(f"ARDC vocab request error: {str(e)} - {external_url}")
        return {"error": "Vocabulary service unavailable"}, 503


@pidinst_theme.route('/api/proxy/fetch_gcmd_narrower', methods=['GET'])
def fetch_gcmd_narrower():
    """Return immediate narrower (child) concepts for a given concept URI.

    Query params:
        uri    – the canonical concept URI (e.g. a NASA CMR URI)
        scheme – one of instruments, platforms, measured_variables

    Uses the ARDC ``resource.json?uri=`` endpoint to look up the concept
    by its canonical URI within the correct ARDC vocabulary.
    """
    VOCAB_ENDPOINTS = {
        'instruments':        'ardc-curated/gcmd-instruments/22-8-2026-02-13',
        'platforms':          'ardc-curated/gcmd-platforms/21-5-2025-06-17',
        'measured_variables': 'ardc-curated/gcmd-measurementname/21-5-2025-06-06',
    }

    concept_uri = request.args.get('uri', '').strip()
    scheme = request.args.get('scheme', '').strip()

    if not concept_uri:
        return jsonify({'items': [], 'error': 'Missing uri parameter'}), 400
    if scheme not in VOCAB_ENDPOINTS:
        return jsonify({'items': [], 'error': 'Invalid scheme'}), 400

    vocab_path = VOCAB_ENDPOINTS[scheme]
    base_url = 'https://vocabs.ardc.edu.au/repository/api/lda'

    try:
        # Use the ARDC resource endpoint to look up the concept by canonical URI
        resource_url = f'{base_url}/{vocab_path}/resource.json?uri={requests.utils.quote(concept_uri, safe="")}'
        resp = requests.get(resource_url, timeout=15)
        if not resp.ok:
            log.error(f"ARDC resource fetch failed: {resp.status_code} - {resource_url}")
            return jsonify({'items': [], 'error': 'Upstream error'}), 502

        data = resp.json()
        primary = data.get('result', {}).get('primaryTopic', {})
        narrower_list = primary.get('narrower', [])

        items = []
        for entry in narrower_list:
            about = entry.get('_about', '')
            pref = entry.get('prefLabel', {})
            label = pref.get('_value', '') if isinstance(pref, dict) else str(pref) if pref else ''

            # If the inline entry doesn't have a label, fetch it individually
            if not label and about:
                try:
                    child_url = f'{base_url}/{vocab_path}/resource.json?uri={requests.utils.quote(about, safe="")}'
                    child_resp = requests.get(child_url, timeout=8)
                    if child_resp.ok:
                        child_data = child_resp.json()
                        child_primary = child_data.get('result', {}).get('primaryTopic', {})
                        child_pref = child_primary.get('prefLabel', {})
                        label = child_pref.get('_value', '') if isinstance(child_pref, dict) else str(child_pref) if child_pref else ''
                        child_narrower = child_primary.get('narrower', [])
                        items.append({
                            '_about': about,
                            'prefLabel': {'_value': label},
                            'narrower': child_narrower,
                        })
                        continue
                except Exception:
                    pass

            items.append({
                '_about': about,
                'prefLabel': {'_value': label or about.rsplit('/', 1)[-1]},
                'narrower': entry.get('narrower', []),
            })

        items.sort(key=lambda x: (x.get('prefLabel', {}).get('_value', '') or '').lower())
        return jsonify({'items': items})

    except requests.exceptions.RequestException as e:
        log.error(f"ARDC narrower fetch error: {str(e)}")
        return jsonify({'items': [], 'error': 'Vocabulary service unavailable'}), 503


ALLOWED_FIELD_TERMS = {'user_keywords', 'measured_variable'}


# ---------------------------------------------------------------------------
# Custom taxonomy terms proxy (ckanext-taxonomy)
# ---------------------------------------------------------------------------

@pidinst_theme.route('/api/proxy/taxonomy_terms/<taxonomy_name>', methods=['GET'])
def taxonomy_terms_search(taxonomy_name):
    """Search terms from a ckanext-taxonomy vocabulary for Select2 dropdowns.

    Query params:
        q – search string (optional, filters by label substring)

    Returns JSON: {"results": [{"id": "<uri>", "text": "<label>", "uri": "<uri>"}]}
    """
    from ckanext.pidinst_theme.helpers import get_allowed_taxonomies
    if taxonomy_name not in get_allowed_taxonomies():
        return jsonify({'results': [], 'error': 'Taxonomy not allowed'}), 400

    query_term = request.args.get('q', '').strip().lower()

    def _flatten(terms):
        """Recursively flatten a hierarchical term list."""
        flat = []
        for term in (terms or []):
            flat.append(term)
            flat.extend(_flatten(term.get('children', [])))
        return flat

    try:
        context = {'ignore_auth': True}
        terms = get_action('taxonomy_term_list')(context, {
            'id': taxonomy_name,
        })

        results = []
        for term in _flatten(terms):
            label = term.get('label', '')
            uri = term.get('uri', '')
            if query_term and query_term not in label.lower():
                continue
            results.append({
                'id': uri or label,
                'text': label,
                'uri': uri,
            })

        results.sort(key=lambda x: x['text'].lower())
        return jsonify({'results': results[:100]})

    except Exception as e:
        log.error(f"Error fetching taxonomy terms for {taxonomy_name}: {e}")
        return jsonify({'results': [], 'error': 'Failed to fetch terms'}), 500


# ---------------------------------------------------------------------------
# ROR (Research Organization Registry) proxy – Owner (ROR) feature
# ---------------------------------------------------------------------------

# Only return Australian organisations with these types.
ROR_ALLOWED_TYPES = {'education', 'government', 'facility'}
ROR_API_BASE = 'https://api.ror.org/v2/organizations'


@pidinst_theme.route('/api/proxy/ror_search', methods=['GET'])
def ror_search():
    """Search the ROR API and return simplified results for Select2.

    Query params:
        q            – search term (required, min 2 chars)
        manufacturer – 'true' to search globally (no country / type filter)

    When manufacturer is falsy the search is scoped to Australian orgs of
    type education / government / facility.  When manufacturer is truthy
    the search is global with no type filter, since manufacturers can be
    anywhere in the world.

    If q looks like a ROR ID (starts with https://ror.org/) the endpoint
    fetches that single record directly instead of doing a keyword search.
    """
    query_term = request.args.get('q', '').strip()
    if len(query_term) < 2:
        return jsonify({'results': []})

    is_manufacturer = request.args.get('manufacturer', '').lower() == 'true'

    try:
        items = []

        # --- Direct ROR ID lookup ---
        if query_term.startswith('https://ror.org/'):
            ror_url = f'{ROR_API_BASE}/{query_term}'
            resp = requests.get(ror_url, timeout=10)
            if resp.ok:
                items = [resp.json()]
            else:
                log.warning('ROR direct lookup failed for %s: %s',
                            query_term, resp.status_code)
        else:
            # --- Keyword search ---
            params = {
                'query': query_term,
                'page': 1,
            }
            if not is_manufacturer:
                type_filter = ','.join(
                    f'types:{t}' for t in sorted(ROR_ALLOWED_TYPES)
                )
                params['filter'] = f'country.country_code:AU,{type_filter}'
            # else: no filter → global search

            resp = requests.get(ROR_API_BASE, params=params, timeout=10)
            if not resp.ok:
                log.error('ROR search failed: %s %s',
                          resp.status_code, resp.text[:200])
                return jsonify({'results': [], 'error': 'ROR API error'}), 502

            data = resp.json()
            items = data.get('items', [])

        results = []
        for item in items:
            fields = _extract_ror_fields(item)
            hierarchy_display, parents_json = _resolve_ror_hierarchy(item)

            results.append({
                'id': fields['id'],
                'text': fields['name'],
                'ror_id': fields['id'],
                'name': fields['name'],
                'types': fields['types'],
                'country': fields['country'],
                'party_state': fields['party_state'],
                'website': fields['website'],
                'parents_json': parents_json,
                'hierarchy_display': hierarchy_display,
            })

        return jsonify({'results': results})

    except requests.exceptions.RequestException as e:
        log.error('ROR search request error: %s', e)
        return jsonify({'results': [], 'error': 'ROR service unavailable'}), 503
    except Exception as e:
        log.error('ROR search unexpected error: %s', e)
        return jsonify({'results': [], 'error': 'Internal error'}), 500


# --- Party tree cache ---
# State lives in party_cache.py so action.py can import it without circular deps.
from ckanext.pidinst_theme import party_cache as _party_cache_mod
from ckanext.pidinst_theme import propagation_helpers as _propagation_helpers


def _party_cache_get(key):
    return _party_cache_mod.cache_get(key)


def _party_cache_set(key, value):
    _party_cache_mod.cache_set(key, value)


def invalidate_party_cache():
    """Clear the party tree cache.  Call after party or ownership changes."""
    _party_cache_mod.invalidate()


def _load_all_party_metadata():
    """Load all party groups with merged extras.  Returns {slug: merged_dict}.

    Uses two raw SQL queries total, bypassing the CKAN group_list action
    layer which computes package counts, member counts and image URLs for
    every group — a significant source of latency we don't need here.
    """
    cached = _party_cache_get('_party_metadata')
    if cached is not None:
        log.info('[PERF] _load_all_party_metadata: cache HIT')
        return cached

    import ckan.model as _model  # local import to keep module-level imports clean

    _t0 = time.time()

    # Query 1: only the three columns we actually use — no computed fields.
    group_rows = (
        _model.Session.query(
            _model.Group.id,
            _model.Group.name,
            _model.Group.title,
        )
        .filter(_model.Group.type == 'party')
        .filter(_model.Group.state == 'active')
        .all()
    )
    _t1 = time.time()
    log.info('[PERF] _load_all_party_metadata: SQL group query returned %d parties in %.3fs',
             len(group_rows), _t1 - _t0)

    # Query 2: all extras for those groups in a single IN(...) query.
    group_ids = [row.id for row in group_rows]
    extras_by_group = {}
    if group_ids:
        extra_rows = (
            _model.Session.query(_model.GroupExtra)
            .filter(_model.GroupExtra.group_id.in_(group_ids))
            .filter(_model.GroupExtra.state == 'active')
            .all()
        )
        for row in extra_rows:
            extras_by_group.setdefault(row.group_id, {})[row.key] = row.value
    _t2 = time.time()
    log.info('[PERF] _load_all_party_metadata: batched extras query returned %d rows in %.3fs',
             sum(len(v) for v in extras_by_group.values()), _t2 - _t1)

    parties = {}
    for row in group_rows:
        merged = {
            'id':    row.id,
            'name':  row.name,
            'title': row.title or row.name,
        }
        merged.update(extras_by_group.get(row.id, {}))
        parties[row.name] = merged

    _party_cache_set('_party_metadata', parties)
    log.info('[PERF] _load_all_party_metadata: total MISS path %.3fs', time.time() - _t0)
    return parties


def _parse_party_roles(merged):
    """Parse party_role field into a list of lowercase role strings."""
    role_raw = merged.get('party_role') or []
    if isinstance(role_raw, str) and role_raw.strip():
        try:
            role_raw = json.loads(role_raw) if role_raw.strip().startswith('[') else [role_raw]
        except Exception:
            role_raw = [role_raw]
    return [
        str(r).strip().lower()
        for r in (role_raw if isinstance(role_raw, list) else [])
        if str(r).strip()
    ]


def _build_party_trees(is_platform, is_logged_in):
    """Build owner and manufacturer party node lists.

    Returns (owner_nodes, manufacturer_nodes).  Uses a single rows=0 Solr
    facet query to count both trees; Solr computes counts server-side without
    transferring package documents.  Cached for _PARTY_CACHE_TTL seconds.
    """
    cache_key = ('party_trees', is_platform, is_logged_in)
    cached = _party_cache_get(cache_key)
    if cached is not None:
        log.info('[PERF] _build_party_trees(is_platform=%s): cache HIT', is_platform)
        return cached

    _t0 = time.time()
    log.info('[PERF] _build_party_trees(is_platform=%s): cache MISS — building', is_platform)

    all_parties = _load_all_party_metadata()
    _t1 = time.time()
    log.info('[PERF] _build_party_trees: _load_all_party_metadata done in %.3fs (%d parties)',
             _t1 - _t0, len(all_parties))

    # Pre-parse roles once for all parties
    roles_by_slug = {slug: _parse_party_roles(m) for slug, m in all_parties.items()}

    # --- Owner party map (exclude manufacturer-only parties) ---
    owner_map = {}
    for slug, merged in all_parties.items():
        roles = roles_by_slug[slug]
        if roles and all(r == 'manufacturer' for r in roles):
            continue
        owner_map[slug] = {
            'id':        slug,
            'title':     merged.get('title') or slug,
            'parent_id': merged.get('parent_party') or None,
            'contact':   merged.get('party_contact', ''),
            'count':     0,
        }

    # --- Manufacturer party map ---
    title_map = {slug: (m.get('title') or slug) for slug, m in all_parties.items()}
    parent_slug_map = {slug: (m.get('parent_party') or None) for slug, m in all_parties.items()}
    mfr_slugs = {slug for slug, roles in roles_by_slug.items() if 'manufacturer' in roles}

    mfr_map = {}
    for slug in mfr_slugs:
        title = title_map[slug]
        parent_slug = parent_slug_map.get(slug)
        parent_title = title_map[parent_slug] if parent_slug in mfr_slugs else None
        mfr_map[slug] = {
            'id':        title,
            'title':     title,
            'parent_id': parent_title,
            'count':     0,
        }
    _t2 = time.time()
    log.info('[PERF] _build_party_trees: maps built (%d owners, %d mfrs) in %.3fs',
             len(owner_map), len(mfr_map), _t2 - _t1)

    # --- Single rows=0 Solr facet query for counting both owners and manufacturers ---
    # Solr computes the aggregated counts server-side in one round-trip without
    # transferring any package documents, replacing the previous paginated while-loop.
    context = {'ignore_auth': True}
    fq = f'dataset_type:instrument AND extras_is_platform:{is_platform}'
    try:
        facet_result = toolkit.get_action('package_search')(context, {
            'q': '*:*',
            'fq': fq,
            'rows': 0,
            'facet': 'true',
            'facet.field': ['vocab_owner_party', 'vocab_manufacturer_party'],
            'facet.limit': -1,    # return all values, not just top-N
            'facet.mincount': 1,
            'include_private': is_logged_in,
        })
    except Exception as e:
        log.warning('Party count facet query failed: %s', e)
        facet_result = {'search_facets': {}}
    _t3 = time.time()
    log.info('[PERF] _build_party_trees: Solr facet query done in %.3fs', _t3 - _t2)

    search_facets = facet_result.get('search_facets', {})

    # vocab_owner_party indexes owner_name (display title); map back to slug via
    # a reverse title→slug lookup built from the same all_parties metadata.
    title_to_slug = {(m.get('title') or slug): slug for slug, m in all_parties.items()}
    for item in search_facets.get('vocab_owner_party', {}).get('items', []):
        name = item.get('name', '')
        slug = title_to_slug.get(name)
        if slug and slug in owner_map:
            owner_map[slug]['count'] = item['count']

    # vocab_manufacturer_party indexes the manufacturer title, which is also
    # the node id in mfr_map, so the lookup is direct.
    mfr_title_to_slug = {title_map[slug]: slug for slug in mfr_slugs}
    for item in search_facets.get('vocab_manufacturer_party', {}).get('items', []):
        name = item.get('name', '')
        slug = mfr_title_to_slug.get(name)
        if slug and slug in mfr_map:
            mfr_map[slug]['count'] = item['count']

    result_pair = (list(owner_map.values()), list(mfr_map.values()))
    _party_cache_set(cache_key, result_pair)
    log.info('[PERF] _build_party_trees(is_platform=%s): TOTAL %.3fs', is_platform, time.time() - _t0)
    return result_pair


def _build_instrument_party_nodes(is_platform, is_logged_in):
    """Build the nodes list for the instrument parties (Owners/Funders) tree."""
    return _build_party_trees(is_platform, is_logged_in)[0]


def _build_manufacturer_party_nodes(is_platform, is_logged_in):
    """Build the nodes list for the manufacturer parties tree."""
    return _build_party_trees(is_platform, is_logged_in)[1]


@pidinst_theme.route('/api/party_cache_version')
def party_cache_version():
    """Return the current party cache version.

    Lightweight endpoint used by the JS tree widget to detect when the
    server-side party data has changed so the sessionStorage cache can
    be invalidated.
    """
    return jsonify({'version': _party_cache_mod.get_version()})


@pidinst_theme.route('/api/propagation_progress/<path:entity_key>')
def propagation_progress(entity_key):
    """Return the current progress of a background propagation job.

    *entity_key* is the same key used when the job was created, e.g.
    ``party=phoenix-geophysics``.

    Response schema:
      {status: 'pending'|'running'|'done'|'no_job',
       job_id: <str|null>,
       total: <int|null>, done: <int>, updated: <int>, failures: <int>}
    """
    # Werkzeug usually decodes percent-encoded path segments, but apply an
    # explicit unquote so the lookup always uses the decoded form (e.g.
    # "party=slug" not "party%3Dslug") regardless of proxy/Flask version.
    from urllib.parse import unquote as _unquote
    entity_key = _unquote(entity_key)
    log.debug('[propagation_progress] polling entity_key=%r', entity_key)
    job = _propagation_helpers.job_get_by_entity(entity_key)
    if job is None:
        log.debug('[propagation_progress] no_job for entity_key=%r', entity_key)
        return jsonify({'status': 'no_job', 'job_id': None}), 200
    log.debug(
        '[propagation_progress] entity_key=%r status=%s done=%s/%s updated=%s',
        entity_key, job['status'], job['done'], job['total'], job['updated'],
    )
    return jsonify({
        'status':      job['status'],
        'job_id':      job.get('job_id'),
        'finished_at': job.get('finished_at'),
        'total':       job['total'],
        'done':        job['done'],
        'updated':     job['updated'],
        'failures':    job['failures'],
    })


@pidinst_theme.route('/api/instrument_parties')
def instrument_parties():
    """Return party nodes for the owner/funder tree widget.
    Query param: is_platform ('true'/'false', default 'false').
    """
    _t0 = time.time()
    try:
        is_platform = request.args.get('is_platform', 'false')
        is_logged_in = bool(toolkit.c.user)
        nodes = _build_instrument_party_nodes(is_platform, is_logged_in)
        log.info('[PERF] GET /api/instrument_parties?is_platform=%s -> %d nodes in %.3fs',
                 is_platform, len(nodes), time.time() - _t0)
        return jsonify({'nodes': nodes, 'cache_version': _party_cache_mod.get_version()})
    except Exception as e:
        log.error('[PERF] instrument_parties error after %.3fs: %s', time.time() - _t0, e)
        return jsonify({'nodes': [], 'error': str(e)}), 500


@pidinst_theme.route('/api/manufacturer_parties')
def manufacturer_parties():
    """Return manufacturer party nodes for the manufacturer tree widget.
    Query param: is_platform ('true'/'false', default 'false').
    """
    _t0 = time.time()
    try:
        is_platform = request.args.get('is_platform', 'false')
        is_logged_in = bool(toolkit.c.user)
        nodes = _build_manufacturer_party_nodes(is_platform, is_logged_in)
        log.info('[PERF] GET /api/manufacturer_parties?is_platform=%s -> %d nodes in %.3fs',
                 is_platform, len(nodes), time.time() - _t0)
        return jsonify({'nodes': nodes, 'cache_version': _party_cache_mod.get_version()})
    except Exception as e:
        log.error('[PERF] manufacturer_parties error after %.3fs: %s', time.time() - _t0, e)
        return jsonify({'nodes': [], 'error': str(e)}), 500


@pidinst_theme.route('/api/party/create_from_ror', methods=['POST'])
def create_party_from_ror():
    """Create a Party group from a ROR record, including parent parties.

    Expects JSON body:
        {ror_id, name, types, country, party_state, website, parents_json, hierarchy_display,
         party_role (optional list, e.g. ["Owner", "Funder"])}

    Automatically creates parent parties that don't yet exist.
    Propagates party_role to parents and the leaf party.
    Returns the created (or already existing) party.
    """
    if not toolkit.c.user:
        return jsonify({'error': 'Authentication required'}), 403

    data = request.get_json(silent=True) or {}
    ror_id   = (data.get('ror_id') or '').strip()
    ror_name = (data.get('name') or '').strip()
    if not ror_id or not ror_name:
        return jsonify({'error': 'ror_id and name are required'}), 400

    # Optional roles to propagate to parents and the leaf party
    child_roles = data.get('party_role') or []
    if isinstance(child_roles, str):
        try:
            child_roles = json.loads(child_roles)
        except (json.JSONDecodeError, ValueError):
            child_roles = []

    context = {
        'user': toolkit.c.user,
        'auth_user_obj': toolkit.c.userobj,
    }

    try:
        parents_json_str = data.get('parents_json', '[]')
        parents = json.loads(parents_json_str) if isinstance(parents_json_str, str) else (parents_json_str or [])

        # Parents are root-first.  We need to ensure each exists before creating
        # children so parent_party references are valid.
        created_parties = []
        previous_name = None

        for parent in parents:
            pid   = (parent.get('id') or '').strip()
            pname = (parent.get('name') or '').strip()
            if not pid or not pname:
                continue
            slug = _ror_name_to_slug(pname)
            existing = _get_party_by_name(context, slug)
            if existing:
                _reactivate_if_deleted(context, existing)
                if child_roles:
                    _merge_party_roles(context, existing, child_roles)
            else:
                fac_data = {
                    'name': slug,
                    'title': pname,
                    'type': 'party',
                    'party_identifier_type': 'ROR',
                    'party_identifier_ror': pid,
                    'ror_hierarchy_display': '',
                    'ror_parents_json': '[]',
                    'ror_types': parent.get('types', ''),
                    'ror_country': parent.get('country', ''),
                    'party_state': parent.get('party_state', ''),
                    'website': parent.get('website', ''),
                    'parent_party': previous_name or '',
                    'party_role': child_roles,
                }
                toolkit.get_action('group_create')(context, fac_data)
                created_parties.append(slug)
            previous_name = slug

        # Now create the leaf party itself
        slug = _ror_name_to_slug(ror_name)
        existing = _get_party_by_name(context, slug)
        if existing:
            # Reactivate if soft-deleted and return
            _reactivate_if_deleted(context, existing)
            if child_roles:
                _merge_party_roles(context, existing, child_roles)
            return jsonify({
                'status': 'exists',
                'party': {
                    'name': existing['name'],
                    'title': existing.get('title', ''),
                    'contact': _get_extra(existing, 'party_contact', ''),
                },
            })

        fac_data = {
            'name': slug,
            'title': ror_name,
            'type': 'party',
            'party_identifier_type': 'ROR',
            'party_identifier_ror': ror_id,
            'ror_hierarchy_display': data.get('hierarchy_display', ''),
            'ror_parents_json': parents_json_str,
            'ror_types': data.get('types', ''),
            'ror_country': data.get('country', ''),
            'party_state': data.get('party_state', ''),
            'website': data.get('website', ''),
            'parent_party': previous_name or '',
            'party_role': child_roles,
        }
        new_fac = toolkit.get_action('group_create')(context, fac_data)
        created_parties.append(slug)

        return jsonify({
            'status': 'created',
            'party': {
                'name': new_fac['name'],
                'title': new_fac.get('title', ''),
                'contact': '',
            },
            'also_created': created_parties,
        })

    except toolkit.NotAuthorized:
        return jsonify({'error': 'Not authorized to create parties'}), 403
    except Exception as e:
        log.error('create_party_from_ror error: %s', e)
        return jsonify({'error': str(e)}), 500


@pidinst_theme.route('/api/party/ensure_ror_parents', methods=['POST'])
def ensure_ror_parents():
    """Ensure that all ROR parent parties in a parents_json chain exist.

    Called by the party form's JS before submit so that the new
    party's parent_party reference is valid.

    Expects JSON body:   { parents_json: '<JSON string>' }
    parents_json is a root-first array of {id, name} dicts.
    """
    if not toolkit.c.user:
        return jsonify({'error': 'Authentication required'}), 403

    data = request.get_json(silent=True) or {}
    parents_json_str = data.get('parents_json', '[]')
    try:
        parents = json.loads(parents_json_str) if isinstance(parents_json_str, str) else (parents_json_str or [])
    except (json.JSONDecodeError, ValueError):
        parents = []

    # Roles to propagate from the child being created to its parents
    child_roles = data.get('party_role') or []
    if isinstance(child_roles, str):
        try:
            child_roles = json.loads(child_roles)
        except (json.JSONDecodeError, ValueError):
            child_roles = []

    if not parents:
        return jsonify({'status': 'ok', 'created': []})

    context = {
        'user': toolkit.c.user,
        'auth_user_obj': toolkit.c.userobj,
    }

    try:
        created = []
        previous_name = None

        for parent in parents:
            pid   = (parent.get('id') or '').strip()
            pname = (parent.get('name') or '').strip()
            if not pid or not pname:
                continue
            slug = _ror_name_to_slug(pname)
            existing = _get_party_by_name(context, slug)
            if existing:
                # Reactivate if it was soft-deleted
                _reactivate_if_deleted(context, existing)
                # Merge child roles into existing parent
                if child_roles:
                    _merge_party_roles(context, existing, child_roles)
            else:
                fac_data = {
                    'name': slug,
                    'title': pname,
                    'type': 'party',
                    'party_identifier_type': 'ROR',
                    'party_identifier_ror': pid,
                    'ror_hierarchy_display': '',
                    'ror_parents_json': '[]',
                    'ror_types': parent.get('types', ''),
                    'ror_country': parent.get('country', ''),
                    'party_state': parent.get('party_state', ''),
                    'website': parent.get('website', ''),
                    'parent_party': previous_name or '',
                    'party_role': child_roles,
                }
                toolkit.get_action('group_create')(context, fac_data)
                created.append(slug)
            previous_name = slug

        return jsonify({'status': 'ok', 'created': created})

    except toolkit.NotAuthorized:
        return jsonify({'error': 'Not authorized to create parties'}), 403
    except Exception as e:
        log.error('ensure_ror_parents error: %s', e)
        return jsonify({'error': str(e)}), 500


@pidinst_theme.route('/api/party/sync_parent_roles', methods=['POST'])
def sync_parent_roles():
    """Merge the child party's roles into its parent party.

    Called by the party form JS before/after submit so that the
    parent party inherits the child's roles and appears in the
    correct role-filtered dropdowns.

    Expects JSON body:  { parent_name: '<slug>', roles: ['Owner', ...] }
    """
    if not toolkit.c.user:
        return jsonify({'error': 'Authentication required'}), 403

    data = request.get_json(silent=True) or {}
    parent_name = (data.get('parent_name') or '').strip()
    roles = data.get('roles') or []

    if not parent_name or not roles:
        return jsonify({'status': 'ok', 'updated': False})

    context = {
        'user': toolkit.c.user,
        'auth_user_obj': toolkit.c.userobj,
    }

    try:
        parent_dict = toolkit.get_action('group_show')(
            context, {'id': parent_name, 'type': 'party', 'include_extras': True}
        )
        _merge_party_roles(context, parent_dict, roles)
        return jsonify({'status': 'ok', 'updated': True})
    except toolkit.ObjectNotFound:
        return jsonify({'error': 'Parent party not found'}), 404
    except toolkit.NotAuthorized:
        return jsonify({'error': 'Not authorized'}), 403
    except Exception as e:
        log.error('sync_parent_roles error: %s', e)
        return jsonify({'error': str(e)}), 500


def _ror_name_to_slug(name):
    """Convert a ROR organisation name to a CKAN-safe URL slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    # CKAN requires min 2 chars and max 100 chars
    if len(slug) < 2:
        slug = slug + '-party'
    return slug[:100]


def _get_party_by_name(context, name):
    """Try to fetch a party group by name.  Returns None if not found.

    Also finds soft-deleted groups (state='deleted') so callers can
    decide whether to reactivate them.
    """
    try:
        return toolkit.get_action('group_show')(
            dict(context, include_datasets=False),
            {'id': name},
        )
    except (toolkit.ObjectNotFound, Exception):
        return None


def _reactivate_if_deleted(context, group_dict):
    """If a group is soft-deleted, set its state back to 'active'.

    CKAN group_delete only sets state='deleted' but keeps the name
    reserved.  This helper re-activates such groups so they become
    visible again in group_list.
    """
    if not group_dict:
        return group_dict
    if group_dict.get('state') == 'deleted':
        log.info('Reactivating soft-deleted party group: %s', group_dict['name'])
        group_dict['state'] = 'active'
        result = toolkit.get_action('group_update')(context, group_dict)
        invalidate_party_cache()
        return result
    return group_dict


def _merge_party_roles(context, group_dict, new_roles):
    """Merge *new_roles* into an existing party's ``party_role`` field.

    Only performs an update when there are genuinely new roles to add.
    """
    if not new_roles:
        return

    existing_raw = group_dict.get('party_role', '[]')
    try:
        existing_roles = json.loads(existing_raw) if isinstance(existing_raw, str) else (existing_raw or [])
    except (json.JSONDecodeError, ValueError):
        existing_roles = []

    merged = list(set(existing_roles) | set(new_roles))
    if set(merged) == set(existing_roles):
        return  # nothing new

    toolkit.get_action('group_patch')(context, {
        'id': group_dict['id'],
        'party_role': merged,
    })
    invalidate_party_cache()


def _get_extra(group_dict, key, default=''):
    """Extract an extra value from a CKAN group dict."""
    for e in group_dict.get('extras', []):
        if e.get('key') == key:
            return e.get('value', default)
    return default


def _get_ror_display_name(ror_item):
    """Extract the display name from a ROR v2 item dict."""
    for n in ror_item.get('names', []):
        if 'ror_display' in n.get('types', []):
            return n.get('value', '')
    names = ror_item.get('names', [])
    return names[0].get('value', '') if names else ''


def _extract_ror_fields(ror_item):
    """Extract all display-relevant fields from a ROR v2 API item dict.

    Returns a plain dict with keys:
        id, name, types, country, party_state, website
    """
    ror_id = ror_item.get('id', '')
    name = _get_ror_display_name(ror_item)

    org_types = ', '.join(t.lower() for t in ror_item.get('types', []))

    locations = ror_item.get('locations', [])
    country = ''
    party_state = ''
    if locations:
        geonames = locations[0].get('geonames_details', {})
        country = geonames.get('country_name', '')
        party_state = geonames.get('country_subdivision_name', '')

    links = ror_item.get('links', [])
    website = ''
    for link in links:
        if isinstance(link, dict) and link.get('type') == 'website':
            website = link.get('value', '')
            break
    if not website and links:
        first = links[0]
        website = first.get('value', '') if isinstance(first, dict) else str(first)

    return {
        'id': ror_id,
        'name': name,
        'types': org_types,
        'country': country,
        'party_state': party_state,
        'website': website,
    }


def _resolve_ror_hierarchy(item):
    """Resolve the parent hierarchy for a ROR organisation record.

    Walks the ``relationships`` array (type = "parent") upward, fetching each
    parent from the ROR API, until there are no more parents.

    Returns:
        (hierarchy_display, parents_json)
            hierarchy_display: str  – e.g. "Curtin University > Faculty of ..."
            parents_json: str       – JSON array of full parent field dicts
    """
    parents = []
    visited = set()

    current = item
    selected_name = _get_ror_display_name(current)

    # Walk up to 10 levels to avoid infinite loops
    for _ in range(10):
        rels = current.get('relationships', [])
        parent_rel = None
        for rel in rels:
            if rel.get('type', '').lower() == 'parent':
                parent_rel = rel
                break

        if not parent_rel:
            break

        parent_id = parent_rel.get('id', '')
        if not parent_id or parent_id in visited:
            break
        visited.add(parent_id)

        # Fetch the full parent record from ROR so we can store all fields
        try:
            resp = requests.get(f'{ROR_API_BASE}/{parent_id}', timeout=10)
            if not resp.ok:
                log.warning('Could not fetch ROR parent %s: %s', parent_id, resp.status_code)
                parent_name = parent_rel.get('label', parent_id)
                parents.append({'id': parent_id, 'name': parent_name,
                                'types': '', 'country': '', 'party_state': '', 'website': ''})
                break

            parent_data = resp.json()
            parents.append(_extract_ror_fields(parent_data))
            current = parent_data
        except requests.exceptions.RequestException as e:
            log.warning('ROR parent resolution failed for %s: %s', parent_id, e)
            parent_name = parent_rel.get('label', parent_id)
            parents.append({'id': parent_id, 'name': parent_name,
                            'types': '', 'country': '', 'party_state': '', 'website': ''})
            break

    # parents is ordered child->root; reverse for display root->child
    parents.reverse()

    # Build hierarchy display string: root > ... > selected
    hierarchy_parts = [p['name'] for p in parents] + [selected_name]
    hierarchy_display = ' > '.join(hierarchy_parts)

    parents_json = json.dumps(parents)

    return hierarchy_display, parents_json
# Mapping for nested fields: subfield_name -> parent_field_name
NESTED_FIELD_TERMS = {'instrument_type_name': 'instrument_type'}

@pidinst_theme.route('/api/field_terms/<field_name>', methods=['GET'])
def field_terms_autocomplete(field_name):
    # Check both simple and nested allowed fields
    is_nested = field_name in NESTED_FIELD_TERMS
    if field_name not in ALLOWED_FIELD_TERMS and not is_nested:
        return jsonify({"error": "Field not allowed", "terms": []}), 400

    query_term = request.args.get('q', '').strip().lower()

    try:
        context = {'ignore_auth': True}
        search_result = get_action('package_search')(context, {
            'q': '*:*',
            'rows': 1000,
            'fl': 'id,validated_data_dict',
        })

        all_terms = set()
        for pkg in search_result.get('results', []):
            vdd_str = pkg.get('validated_data_dict', '')
            if not vdd_str:
                continue
            try:
                vdd = json.loads(vdd_str) if isinstance(vdd_str, str) else vdd_str
            except json.JSONDecodeError:
                continue

            # Handle nested fields (composite_repeating)
            if is_nested:
                parent_field = NESTED_FIELD_TERMS[field_name]
                parent_value = vdd.get(parent_field, [])
                # parent_value is a list of dicts
                if isinstance(parent_value, list):
                    for item in parent_value:
                        if isinstance(item, dict):
                            term = item.get(field_name, '')
                            if isinstance(term, str) and term.strip():
                                all_terms.add(term.strip())
            else:
                # Handle simple fields
                field_value = vdd.get(field_name, '')
                if not field_value:
                    continue
                terms = []
                if isinstance(field_value, str):
                    if field_value.startswith('['):
                        try:
                            terms = json.loads(field_value)
                        except json.JSONDecodeError:
                            terms = [t.strip() for t in field_value.split(',') if t.strip()]
                    else:
                        terms = [t.strip() for t in field_value.split(',') if t.strip()]
                elif isinstance(field_value, list):
                    terms = field_value
                for term in terms:
                    if isinstance(term, str) and term.strip():
                        all_terms.add(term.strip())

        if query_term:
            matching = sorted([t for t in all_terms if query_term in t.lower()])[:20]
        else:
            matching = sorted(all_terms)[:20]
        return jsonify({"terms": matching})

    except Exception as e:
        log.error(f"Error fetching field terms for {field_name}: {e}")
        return jsonify({"error": str(e), "terms": []}), 500


@pidinst_theme.route('/instrument/<id>/new_version', methods=['GET', 'POST'])
def new_version(id):
    """
    Create a new version of an existing instrument.
    Clones the current instrument with prepopulated data and adds IsNewVersionOf relationship.
    """
    context = {'user': current_user.name}

    try:
        # Check if user has permission to create packages
        check_access('package_create', context)
    except NotAuthorized:
        return base.abort(403, toolkit._('Unauthorized to create instruments'))

    try:
        # Get the original package data
        original_pkg = get_action('package_show')(context, {'id': id})

        # Prepare cloned data using helper function
        cloned_data = h.prepare_dataset_for_cloning(original_pkg, id)

        # Add metadata to track this is a new version
        cloned_data['_is_new_version'] = True
        cloned_data['_original_package_id'] = id
        cloned_data['_original_package_name'] = original_pkg.get('name', '')
        cloned_data['_original_package_title'] = original_pkg.get('title', '')

        # Store in session for the form to pick up
        session['package_new_version_data'] = cloned_data
        session.modified = True

        # Get the instrument type
        dataset_type = original_pkg.get('type', 'instrument')

        # Set up proper context for template rendering
        # Set form action to the standard package create endpoint
        g.form_action = toolkit.url_for(dataset_type + '.new')

        extra_vars = {
            'data': cloned_data,
            'errors': {},
            'error_summary': {},
            'dataset_type': dataset_type,
            'stage': ['active', ''],
            'form_style': 'new',
            'pkg_dict': {},
        }

        # Render using the proper package/new template structure
        return toolkit.render('package/new_version.html', extra_vars=extra_vars)

    except NotFound:
        return base.abort(404, toolkit._('Instrument not found'))
    except Exception as e:
        log.error(f'Error creating new version: {str(e)}')
        toolkit.h.flash_error(toolkit._('An error occurred while preparing the new version'))
        return toolkit.redirect_to('instrument.read', id=id)


# Facet fields rendered as checkboxes on instrument/platform/org/party pages.
# Shared between the search handler, the stable-facet baseline query, and the
# group-page OR-within-block FQ rewrite.
_CHECKBOX_FACET_FIELDS = [
    'vocab_instrument_type_gcmd',
    'vocab_instrument_type_custom',
    'vocab_measured_variable_gcmd',
    'vocab_measured_variable_custom',
    'vocab_instrument_classification',
    'vocab_manufacturer_party',
]


def _build_filter_facet_items(filter_facets, fields_grouped):
    """
    Build the stable facet-item dicts used by checkbox templates.

    Uses the unfiltered baseline facets as the source of items so the list
    never shrinks when filters are applied.  Each item's ``active`` flag is
    set explicitly from ``fields_grouped`` (current request params) rather
    than relying on CKAN's c.fields_grouped which is not set in Blueprint views.

    Any selected value that is absent from the baseline facets is injected
    with count=0 so it remains visible and checked (e.g. stale bookmarks).

    Returns:  dict  field_name -> [{'name', 'display_name', 'count', 'active'}, ...]
    """
    result = {}
    for field, facet_data in filter_facets.items():
        active_values = set(fields_grouped.get(field, []))
        items = []
        seen = set()
        for item in facet_data.get('items', []):
            name = item.get('name', '')
            if name:
                seen.add(name)
                items.append({
                    'name': name,
                    'display_name': item.get('display_name', name),
                    'count': item.get('count', 0),
                    'active': name in active_values,
                })
        for val in active_values:
            if val not in seen:
                items.append({
                    'name': val,
                    'display_name': val,
                    'count': 0,
                    'active': True,
                })
        result[field] = items
    return result


def _build_group_stable_facets(forced_fq, fields_grouped, is_logged_in):
    """Perform a rows=0 baseline Solr query and return stable filter_facet_items.

    Used by org/party group pages so checkboxes remain stable after filtering,
    matching the behaviour of the instruments/platforms pages.
    """
    try:
        baseline = toolkit.get_action('package_search')({'ignore_auth': True}, {
            'q': '*:*',
            'fq': forced_fq,
            'rows': 0,
            'facet': 'true',
            'facet.field': _CHECKBOX_FACET_FIELDS,
            'facet.limit': 200,
            'facet.mincount': 1,
            'include_private': is_logged_in,
        })
        return _build_filter_facet_items(baseline.get('search_facets', {}), fields_grouped)
    except Exception as e:
        log.warning('_build_group_stable_facets failed: %s', e)
        return None


def _instrument_platform_search(is_platform_value, template, named_route, display_type='instrument'):
    """Shared search handler for /instruments and /platforms routes."""
    _page_t0 = time.time()
    q = toolkit.request.args.get('q', '')
    try:
        page = int(toolkit.request.args.get('page', 1))
    except ValueError:
        page = 1

    sort_by = toolkit.request.args.get('sort', 'score desc, metadata_modified desc')
    limit = int(toolkit.config.get('ckan.datasets_per_page', 20))

    forced_fq = f'dataset_type:instrument AND extras_is_platform:{is_platform_value}'

    is_logged_in = bool(toolkit.c.user)

    # Params handled explicitly (not forwarded as Solr FQ)
    reserved = {
        'q', 'page', 'sort',
        'owner_party',
        'commissioned_from', 'commissioned_to',
        'decommissioned_from', 'decommissioned_to'
    }
    fields = []
    fields_grouped = {}
    extra_fq_parts = []
    search_extras = {}

    # --- party owner filter: OR across CKAN group membership ---
    owner_parties = toolkit.request.args.getlist('owner_party')
    if owner_parties:
        for fac in owner_parties:
            fields.append(('owner_party', fac))
            fields_grouped.setdefault('owner_party', []).append(fac)
        or_clauses = ['groups:"{}"'.format(f) for f in owner_parties]
        if len(or_clauses) == 1:
            extra_fq_parts.append('+' + or_clauses[0])
        else:
            extra_fq_parts.append('+(' + ' OR '.join(or_clauses) + ')')

    # --- standard facet filters: group by field for OR-within / AND-between ---
    # Collect all values per field first so that multiple selections in the
    # same field become a single OR clause instead of separate AND clauses.
    facet_param_values = {}  # field -> [values]
    for param, value in toolkit.request.args.items(multi=True):
        if param in reserved or not value or param.startswith('_'):
            continue
        if param.startswith('ext_'):
            search_extras[param] = value
        else:
            facet_param_values.setdefault(param, []).append(value)
            fields.append((param, value))
            fields_grouped.setdefault(param, []).append(value)

    for field, values in facet_param_values.items():
        if len(values) == 1:
            extra_fq_parts.append(f'+{field}:"{values[0]}"')
        else:
            # Multiple selections in the same facet block → OR
            or_parts = ' OR '.join(f'{field}:"{v}"' for v in values)
            extra_fq_parts.append(f'+({or_parts})')

    # --- date interval overlap filters ---
    for from_param, to_param, start_field, end_field in _DATE_FILTER_DEFS:
        from_val = toolkit.request.args.get(from_param, '').strip()
        to_val = toolkit.request.args.get(to_param, '').strip()
        q_start = _parse_date_bound(from_val, is_end=False)
        q_end = _parse_date_bound(to_val, is_end=True)
        if q_start is not None:
            extra_fq_parts.append(f'+{end_field}:[{q_start} TO *]')
        if q_end is not None:
            extra_fq_parts.append(f'+{start_field}:[* TO {q_end}]')

    fq = forced_fq
    if extra_fq_parts:
        fq += ' ' + ' '.join(extra_fq_parts)

    facet_fields = _CHECKBOX_FACET_FIELDS

    data_dict = {
        'q': q or '*:*',
        'fq': fq,
        'rows': limit,
        'start': (page - 1) * limit,
        'sort': sort_by,
        'facet': 'true',
        'facet.field': facet_fields,
        'facet.limit': 50,
        'facet.mincount': 1,
        'include_private': is_logged_in,
        'extras': search_extras,
    }

    query_error = False
    _solr_t0 = time.time()
    try:
        context = {
            'user': toolkit.c.user,
            'auth_user_obj': toolkit.c.userobj,
        }
        query = toolkit.get_action('package_search')(context, data_dict)
        log.info('[PERF] %s package_search returned %d results in %.3fs',
                 template, query.get('count', 0), time.time() - _solr_t0)
        # --- Analytics: track search event after successful package_search ---
        try:
            result_count = query.get('count', 0)
            filter_vals = analytics.extract_filter_values(fields_grouped)
            analytics.track_dataset_search(
                search_term=q,
                result_count=result_count,
                dataset_type=display_type,
                page_number=page,
                sort_by=sort_by,
                filter_values=filter_vals,
            )
        except Exception as _ae:
            log.warning('Search analytics tracking failed: %s', _ae, exc_info=True)
    except Exception as e:
        log.error('[PERF] Search error on %s after %.3fs: %s', template, time.time() - _solr_t0, e)
        query = {'results': [], 'count': 0, 'search_facets': {}}
        query_error = True

    # --- Stable baseline facets for checkbox rendering ---
    # A separate rows=0 query with only the scope filter (no checkbox / date
    # filters) keeps the checkbox option list stable: items never disappear
    # when filters are applied.  Active-but-missing values are injected below.
    _baseline_t0 = time.time()
    try:
        baseline_query = toolkit.get_action('package_search')(context, {
            'q': '*:*',
            'fq': forced_fq,
            'rows': 0,
            'facet': 'true',
            'facet.field': facet_fields,
            'facet.limit': 200,
            'facet.mincount': 1,
            'include_private': is_logged_in,
        })
        _raw_filter_facets = baseline_query.get('search_facets', {})
        log.info('[PERF] %s baseline facet query done in %.3fs',
                 template, time.time() - _baseline_t0)
    except Exception as _be:
        log.warning('[PERF] %s baseline facet query failed (%.3fs): %s; using filtered facets',
                    template, time.time() - _baseline_t0, _be)
        _raw_filter_facets = query.get('search_facets', {})

    filter_facet_items = _build_filter_facet_items(_raw_filter_facets, fields_grouped)

    def pager_url(q=None, page=None):
        params = dict(toolkit.request.args)
        if page is not None:
            params['page'] = page
        return toolkit.url_for(named_route, **params)

    pager = ckan_helpers.Page(
        collection=query.get('results', []),
        page=page,
        url=pager_url,
        item_count=query.get('count', 0),
        items_per_page=limit,
    )
    pager.items = query.get('results', [])

    search_facets = query.get('search_facets', {})
    facet_titles = {
        'vocab_instrument_type_gcmd': toolkit._('Instrument Type (GCMD)'),
        'vocab_instrument_type_custom': toolkit._('Instrument Type (Custom)'),
        'vocab_measured_variable_gcmd': toolkit._('Measured Variable (GCMD)'),
        'vocab_measured_variable_custom': toolkit._('Measured Variable (Custom)'),
        'vocab_instrument_classification': toolkit._('Instrument Class'),
        'vocab_manufacturer_party': toolkit._('Manufacturers'),
    }

    remove_field = partial(h.remove_url_param, alternative_url=toolkit.url_for(named_route))

    # Do NOT embed party nodes in the page HTML.  The JS party-tree-module
    # uses sessionStorage to cache tree data across filter-change reloads in
    # the same tab, so embedding would force an expensive _build_party_trees
    # call on EVERY page render — even when the data is already in the
    # browser.  With empty lists the templates fall into async API mode;
    # the first load fetches /api/instrument_parties (or /api/manufacturer_parties)
    # and caches the result in sessionStorage for all subsequent reloads.
    owner_party_nodes = []
    manufacturer_party_nodes = []

    extra_vars = {
        'dataset_type': display_type,
        'q': q,
        'fields': fields,
        'fields_grouped': fields_grouped,
        'search_facets': search_facets,
        'filter_facet_items': filter_facet_items,  # stable, unfiltered – for checkbox rendering
        'facet_titles': facet_titles,
        'translated_fields': {},
        'remove_field': remove_field,
        'sort_by_selected': sort_by,
        'page': pager,
        'query_error': query_error,
        'is_platform': is_platform_value,
        'active_party_filters': owner_parties,
        'owner_party_nodes': owner_party_nodes,
        'manufacturer_party_nodes': manufacturer_party_nodes,
    }

    log.info('[PERF] %s page render ready in %.3fs (total handler time)',
             template, time.time() - _page_t0)
    return base.render(template, extra_vars=extra_vars)


@pidinst_theme.route('/instruments')
def instruments_search():
    return _instrument_platform_search('false', 'instruments/search.html', 'pidinst_theme.instruments_search', display_type='instrument')


@pidinst_theme.route('/platforms')
def platforms_search():
    return _instrument_platform_search('true', 'platforms/search.html', 'pidinst_theme.platforms_search', display_type='platform')


@pidinst_theme.route('/lifecycle/<pkg_name>/withdraw', methods=['GET', 'POST'])
def withdraw(pkg_name):
    context = {'user': g.user, 'auth_user_obj': g.userobj}
    try:
        pkg = get_action('package_show')(context, {'id': pkg_name})
    except (NotFound, NotAuthorized):
        toolkit.abort(404)

    try:
        check_access('package_withdraw', context, {'id': pkg['id']})
    except NotAuthorized:
        toolkit.abort(403, _('Not authorized to withdraw this record.'))

    errors = {}
    if toolkit.request.method == 'POST':
        reason = toolkit.request.form.get('withdrawal_reason', '').strip()
        if not reason:
            errors = {'withdrawal_reason': [_('A withdrawal reason is required.')]}
        else:
            try:
                get_action('package_withdraw')(context, {
                    'id': pkg['id'],
                    'withdrawal_reason': reason,
                })
                h.flash_success(_('Record has been withdrawn.'))
                return toolkit.redirect_to(h.url_for(pkg['type'] + '.read', id=pkg['name']))
            except ValidationError as e:
                errors = e.error_dict

    return toolkit.render('package/lifecycle_withdraw.html', {
        'pkg': pkg,
        'pkg_dict': pkg,
        'errors': errors,
    })


@pidinst_theme.route('/lifecycle/<pkg_name>/mark-duplicate', methods=['GET', 'POST'])
def mark_duplicate(pkg_name):
    context = {'user': g.user, 'auth_user_obj': g.userobj}
    try:
        pkg = get_action('package_show')(context, {'id': pkg_name})
    except (NotFound, NotAuthorized):
        toolkit.abort(404)

    try:
        check_access('package_mark_duplicate', context, {'id': pkg['id']})
    except NotAuthorized:
        toolkit.abort(403, _('Not authorized to mark this record as duplicate.'))

    errors = {}
    if toolkit.request.method == 'POST':
        duplicate_of = toolkit.request.form.get('duplicate_of', '').strip()
        if not duplicate_of:
            errors = {'duplicate_of': [_('duplicate_of is required.')]}
        else:
            try:
                get_action('package_mark_duplicate')(context, {
                    'id': pkg['id'],
                    'duplicate_of': duplicate_of,
                })
                h.flash_success(_('Record has been marked as a duplicate.'))
                return toolkit.redirect_to(h.url_for(pkg['type'] + '.read', id=pkg['name']))
            except ValidationError as e:
                errors = e.error_dict

    return toolkit.render('package/lifecycle_mark_duplicate.html', {
        'pkg': pkg,
        'pkg_dict': pkg,
        'errors': errors,
    })


@pidinst_theme.after_app_request
def _set_browser_id_cookie_on_response(response):
    """Delegate to analytics.set_browser_id_cookie to persist the browser UUID."""
    return analytics.set_browser_id_cookie(response)


def get_blueprints():
    return [pidinst_theme, analytics_views.analytics_bp]
