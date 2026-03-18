from flask import Blueprint, request, Response, render_template, redirect, url_for, session , jsonify
from flask.views import MethodView
from functools import partial
import requests
import os
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
from ckanext.pidinst_theme import analytics_views

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

ALLOWED_TAXONOMIES = toolkit.config.get('ckanext.taxonomy.allowed_taxonomies', ['instruments', 'platforms', 'measured-variables'])


@pidinst_theme.route('/api/proxy/taxonomy_terms/<taxonomy_name>', methods=['GET'])
def taxonomy_terms_search(taxonomy_name):
    """Search terms from a ckanext-taxonomy vocabulary for Select2 dropdowns.

    Query params:
        q – search string (optional, filters by label substring)

    Returns JSON: {"results": [{"id": "<uri>", "text": "<label>", "uri": "<uri>"}]}
    """
    if taxonomy_name not in ALLOWED_TAXONOMIES:
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


@pidinst_theme.route('/api/instrument_parties')
def instrument_parties():
    """Return a flat list of party nodes for the parties tree widget.

    Each node: {id, name, title, parent_id, contact, count}
      - id/name   = CKAN group name (URL slug)
      - title     = human-readable name
      - parent_id = name of the parent party group, or null
      - contact   = party_contact value
      - count     = number of instruments/platforms that list this party as owner

    Query params:
        is_platform – 'true' or 'false' (default 'false')
    """
    try:
        is_platform = request.args.get('is_platform', 'false')
        context = {
            'user': toolkit.c.user,
            'auth_user_obj': toolkit.c.userobj,
        }

        # 1) Fetch all parties (CKAN groups of type "party")
        # Use group_show per party — group_list with include_extras is
        # unreliable in some CKAN versions, and ckanext-scheming promotes
        # custom fields to top-level keys on group_show anyway.
        group_names = toolkit.get_action('group_list')(context, {
            'type': 'party',
        })

        # Build a quick lookup  name -> party dict
        party_map = {}
        for gname in group_names:
            try:
                g = toolkit.get_action('group_show')(context, {
                    'id': gname,
                    'include_extras': True,
                })
            except Exception:
                continue
            # Merge top-level keys + extras (scheming fields are top-level)
            merged = dict(g)
            for e in g.get('extras', []):
                merged.setdefault(e['key'], e['value'])
            party_map[g['name']] = {
                'id':       g['name'],
                'title':    g.get('title') or g['name'],
                'parent_id': merged.get('parent_party') or None,
                'contact':  merged.get('party_contact', ''),
                'count':    0,
            }

        # 2) Count instruments per party via owner field
        fq = f'dataset_type:instrument AND extras_is_platform:{is_platform}'
        result = toolkit.get_action('package_search')(context, {
            'q': '*:*',
            'fq': fq,
            'rows': 2000,
            'include_private': bool(toolkit.c.user),
        })

        for pkg in result.get('results', []):
            owner_raw = pkg.get('owner')
            if not owner_raw:
                continue
            if isinstance(owner_raw, str):
                try:
                    owner_list = json.loads(owner_raw)
                except (json.JSONDecodeError, ValueError):
                    continue
            elif isinstance(owner_raw, list):
                owner_list = owner_raw
            else:
                continue

            for entry in owner_list:
                fac_id = (entry.get('owner_party_id') or '').strip()
                if fac_id and fac_id in party_map:
                    party_map[fac_id]['count'] += 1

        return jsonify({'nodes': list(party_map.values())})

    except Exception as e:
        log.error('instrument_parties error: %s', e)
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
        return toolkit.get_action('group_update')(context, group_dict)
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


def _instrument_platform_search(is_platform_value, template, named_route, display_type='instrument'):
    """Shared search handler for /instruments and /platforms routes."""
    q = toolkit.request.args.get('q', '')
    try:
        page = int(toolkit.request.args.get('page', 1))
    except ValueError:
        page = 1

    sort_by = toolkit.request.args.get('sort', 'score desc, metadata_modified desc')
    limit = int(toolkit.config.get('ckan.datasets_per_page', 20))

    # Forced server-side filter — cannot be overridden by query params
    # Anonymous users only see public packages; logged-in users see public + their own private ones
    # capacity_filter = '' if toolkit.c.user else ' +capacity:public'
    forced_fq = f'dataset_type:instrument AND extras_is_platform:{is_platform_value}'

    is_logged_in = bool(toolkit.c.user)

    # Collect facet field filters and search extras from request args
    # owner_party is handled specially – maps to CKAN group membership
    reserved = {'q', 'page', 'sort', 'owner_party'}
    fields = []
    fields_grouped = {}
    extra_fq_parts = []
    search_extras = {}

    # --- party owner filter: OR logic across CKAN group membership ---
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

    for param, value in toolkit.request.args.items(multi=True):
        if param in reserved or not value or param.startswith('_'):
            continue
        if param.startswith('ext_'):
            search_extras[param] = value
        else:
            fields.append((param, value))
            fields_grouped.setdefault(param, []).append(value)
            extra_fq_parts.append(f'+{param}:"{value}"')

    fq = forced_fq
    if extra_fq_parts:
        fq += ' ' + ' '.join(extra_fq_parts)

    # organization removed – replaced by parties tree widget
    facet_fields = ['tags', 'instrument_type', 'locality']

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
    try:
        context = {
            'user': toolkit.c.user,
            'auth_user_obj': toolkit.c.userobj,
        }
        query = toolkit.get_action('package_search')(context, data_dict)
    except Exception as e:
        log.error('Search error on %s: %s', template, e)
        query = {'results': [], 'count': 0, 'search_facets': {}}
        query_error = True

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
        'tags': toolkit._('Tags'),
        'instrument_type': toolkit._('Instrument Type'),
        'locality': toolkit._('Locality'),
    }

    remove_field = partial(h.remove_url_param, alternative_url=toolkit.url_for(named_route))

    extra_vars = {
        'dataset_type': display_type,
        'q': q,
        'fields': fields,
        'fields_grouped': fields_grouped,
        'search_facets': search_facets,
        'facet_titles': facet_titles,
        'translated_fields': {},
        'remove_field': remove_field,
        'sort_by_selected': sort_by,
        'page': pager,
        'query_error': query_error,
        'is_platform': is_platform_value,
        'active_party_filters': owner_parties,
    }

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


def get_blueprints():
    return [pidinst_theme, analytics_views.analytics_bp]
