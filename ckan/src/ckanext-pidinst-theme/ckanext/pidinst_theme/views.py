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


ALLOWED_FIELD_TERMS = {'user_keywords', 'measured_variable'}


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
        q       – search term (required, min 2 chars)

    The endpoint filters to Australian orgs of type education / government /
    facility.  It also resolves the parent hierarchy for each result so the
    frontend can cache it.
    """
    query_term = request.args.get('q', '').strip()
    if len(query_term) < 2:
        return jsonify({'results': []})

    try:
        # ROR v2 API: filter by country code AU and allowed types
        # The types filter uses pipe-delimited values for OR logic
        type_filter = ','.join(f'types:{t}' for t in sorted(ROR_ALLOWED_TYPES))
        params = {
            'query': query_term,
            'filter': f'country.country_code:AU,{type_filter}',
            'page': 1,
        }
        resp = requests.get(ROR_API_BASE, params=params, timeout=10)
        if not resp.ok:
            log.error('ROR search failed: %s %s', resp.status_code, resp.text[:200])
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
                'facility_state': fields['facility_state'],
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


@pidinst_theme.route('/api/instrument_facilities')
def instrument_facilities():
    """Return a flat list of facility nodes for the Facilities tree widget.

    Each node: {id, name, title, parent_id, contact, count}
      - id/name   = CKAN group name (URL slug)
      - title     = human-readable name
      - parent_id = name of the parent facility group, or null
      - contact   = facility_contact value
      - count     = number of instruments/platforms that list this facility as owner

    Query params:
        is_platform – 'true' or 'false' (default 'false')
    """
    try:
        is_platform = request.args.get('is_platform', 'false')
        context = {
            'user': toolkit.c.user,
            'auth_user_obj': toolkit.c.userobj,
        }

        # 1) Fetch all facilities (CKAN groups of type "facility")
        all_groups = toolkit.get_action('group_list')(context, {
            'type': 'facility',
            'all_fields': True,
            'include_extras': True,
        })

        # Build a quick lookup  name -> facility dict
        facility_map = {}
        for g in all_groups:
            extras = {e['key']: e['value'] for e in g.get('extras', [])}
            facility_map[g['name']] = {
                'id': g['name'],
                'title': g.get('title') or g['name'],
                'parent_id': extras.get('parent_facility') or None,
                'contact': extras.get('facility_contact', ''),
                'count': 0,
            }

        # 2) Count instruments per facility via instrument_owner field
        fq = f'dataset_type:instrument AND extras_is_platform:{is_platform}'
        result = toolkit.get_action('package_search')(context, {
            'q': '*:*',
            'fq': fq,
            'rows': 2000,
            'include_private': bool(toolkit.c.user),
        })

        for pkg in result.get('results', []):
            owner_raw = pkg.get('instrument_owner')
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
                fac_id = (entry.get('owner_facility_id') or '').strip()
                if fac_id and fac_id in facility_map:
                    facility_map[fac_id]['count'] += 1

        return jsonify({'nodes': list(facility_map.values())})

    except Exception as e:
        log.error('instrument_facilities error: %s', e)
        return jsonify({'nodes': [], 'error': str(e)}), 500


@pidinst_theme.route('/api/facility/create_from_ror', methods=['POST'])
def create_facility_from_ror():
    """Create a Facility group from a ROR record, including parent facilities.

    Expects JSON body:
        {ror_id, name, types, country, facility_state, website, parents_json, hierarchy_display}

    Automatically creates parent facilities that don't yet exist.
    Returns the created (or already existing) facility.
    """
    if not toolkit.c.user:
        return jsonify({'error': 'Authentication required'}), 403

    data = request.get_json(silent=True) or {}
    ror_id   = (data.get('ror_id') or '').strip()
    ror_name = (data.get('name') or '').strip()
    if not ror_id or not ror_name:
        return jsonify({'error': 'ror_id and name are required'}), 400

    context = {
        'user': toolkit.c.user,
        'auth_user_obj': toolkit.c.userobj,
    }

    try:
        parents_json_str = data.get('parents_json', '[]')
        parents = json.loads(parents_json_str) if isinstance(parents_json_str, str) else (parents_json_str or [])

        # Parents are root-first.  We need to ensure each exists before creating
        # children so parent_facility references are valid.
        created_facilities = []
        previous_name = None

        for parent in parents:
            pid   = (parent.get('id') or '').strip()
            pname = (parent.get('name') or '').strip()
            if not pid or not pname:
                continue
            slug = _ror_name_to_slug(pname)
            existing = _get_facility_by_name(context, slug)
            if existing:
                _reactivate_if_deleted(context, existing)
            else:
                fac_data = {
                    'name': slug,
                    'title': pname,
                    'type': 'facility',
                    'facility_identifier_type': 'ROR',
                    'facility_identifier_ror': pid,
                    'ror_hierarchy_display': '',
                    'ror_parents_json': '[]',
                    'ror_types': parent.get('types', ''),
                    'ror_country': parent.get('country', ''),
                    'facility_state': parent.get('facility_state', ''),
                    'website': parent.get('website', ''),
                    'parent_facility': previous_name or '',
                }
                toolkit.get_action('group_create')(context, fac_data)
                created_facilities.append(slug)
            previous_name = slug

        # Now create the leaf facility itself
        slug = _ror_name_to_slug(ror_name)
        existing = _get_facility_by_name(context, slug)
        if existing:
            # Reactivate if soft-deleted and return
            _reactivate_if_deleted(context, existing)
            return jsonify({
                'status': 'exists',
                'facility': {
                    'name': existing['name'],
                    'title': existing.get('title', ''),
                    'contact': _get_extra(existing, 'facility_contact', ''),
                },
            })

        fac_data = {
            'name': slug,
            'title': ror_name,
            'type': 'facility',
            'facility_identifier_type': 'ROR',
            'facility_identifier_ror': ror_id,
            'ror_hierarchy_display': data.get('hierarchy_display', ''),
            'ror_parents_json': parents_json_str,
            'ror_types': data.get('types', ''),
            'ror_country': data.get('country', ''),
            'facility_state': data.get('facility_state', ''),
            'website': data.get('website', ''),
            'parent_facility': previous_name or '',
        }
        new_fac = toolkit.get_action('group_create')(context, fac_data)
        created_facilities.append(slug)

        return jsonify({
            'status': 'created',
            'facility': {
                'name': new_fac['name'],
                'title': new_fac.get('title', ''),
                'contact': '',
            },
            'also_created': created_facilities,
        })

    except toolkit.NotAuthorized:
        return jsonify({'error': 'Not authorized to create facilities'}), 403
    except Exception as e:
        log.error('create_facility_from_ror error: %s', e)
        return jsonify({'error': str(e)}), 500


@pidinst_theme.route('/api/facility/ensure_ror_parents', methods=['POST'])
def ensure_ror_parents():
    """Ensure that all ROR parent facilities in a parents_json chain exist.

    Called by the facility form's JS before submit so that the new
    facility's parent_facility reference is valid.

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
            existing = _get_facility_by_name(context, slug)
            if existing:
                # Reactivate if it was soft-deleted
                _reactivate_if_deleted(context, existing)
            else:
                fac_data = {
                    'name': slug,
                    'title': pname,
                    'type': 'facility',
                    'facility_identifier_type': 'ROR',
                    'facility_identifier_ror': pid,
                    'ror_hierarchy_display': '',
                    'ror_parents_json': '[]',
                    'ror_types': parent.get('types', ''),
                    'ror_country': parent.get('country', ''),
                    'facility_state': parent.get('facility_state', ''),
                    'website': parent.get('website', ''),
                    'parent_facility': previous_name or '',
                }
                toolkit.get_action('group_create')(context, fac_data)
                created.append(slug)
            previous_name = slug

        return jsonify({'status': 'ok', 'created': created})

    except toolkit.NotAuthorized:
        return jsonify({'error': 'Not authorized to create facilities'}), 403
    except Exception as e:
        log.error('ensure_ror_parents error: %s', e)
        return jsonify({'error': str(e)}), 500


def _ror_name_to_slug(name):
    """Convert a ROR organisation name to a CKAN-safe URL slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    # CKAN requires min 2 chars and max 100 chars
    if len(slug) < 2:
        slug = slug + '-facility'
    return slug[:100]


def _get_facility_by_name(context, name):
    """Try to fetch a facility group by name.  Returns None if not found.

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
        log.info('Reactivating soft-deleted facility group: %s', group_dict['name'])
        group_dict['state'] = 'active'
        return toolkit.get_action('group_update')(context, group_dict)
    return group_dict


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
        id, name, types, country, facility_state, website
    """
    ror_id = ror_item.get('id', '')
    name = _get_ror_display_name(ror_item)

    org_types = ', '.join(t.lower() for t in ror_item.get('types', []))

    locations = ror_item.get('locations', [])
    country = ''
    facility_state = ''
    if locations:
        geonames = locations[0].get('geonames_details', {})
        country = geonames.get('country_name', '')
        facility_state = geonames.get('country_subdivision_name', '')

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
        'facility_state': facility_state,
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
                                'types': '', 'country': '', 'facility_state': '', 'website': ''})
                break

            parent_data = resp.json()
            parents.append(_extract_ror_fields(parent_data))
            current = parent_data
        except requests.exceptions.RequestException as e:
            log.warning('ROR parent resolution failed for %s: %s', parent_id, e)
            parent_name = parent_rel.get('label', parent_id)
            parents.append({'id': parent_id, 'name': parent_name,
                            'types': '', 'country': '', 'facility_state': '', 'website': ''})
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


@pidinst_theme.route('/dataset/<id>/new_version', methods=['GET', 'POST'])
def new_version(id):
    """
    Create a new version of an existing dataset/instrument.
    Clones the current dataset with prepopulated data and adds IsNewVersionOf relationship.
    """
    context = {'user': current_user.name}

    try:
        # Check if user has permission to create packages
        check_access('package_create', context)
    except NotAuthorized:
        return base.abort(403, toolkit._('Unauthorized to create datasets'))

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

        # Get the dataset type
        dataset_type = original_pkg.get('type', 'dataset')

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
        return base.abort(404, toolkit._('Dataset not found'))
    except Exception as e:
        log.error(f'Error creating new version: {str(e)}')
        toolkit.h.flash_error(toolkit._('An error occurred while preparing the new version'))
        return toolkit.redirect_to('dataset.read', id=id)


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
    # owner_facility is handled specially – maps to a text search on extras_instrument_owner
    reserved = {'q', 'page', 'sort', 'owner_facility'}
    fields = []
    fields_grouped = {}
    extra_fq_parts = []
    search_extras = {}

    # --- Facility owner filter: OR logic across extras_instrument_owner text field ---
    owner_facilities = toolkit.request.args.getlist('owner_facility')
    if owner_facilities:
        for fac in owner_facilities:
            fields.append(('owner_facility', fac))
            fields_grouped.setdefault('owner_facility', []).append(fac)
        or_clauses = ['extras_instrument_owner:"{}"'.format(f) for f in owner_facilities]
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

    # organization removed – replaced by Facilities tree widget
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
        'active_facility_filters': owner_facilities,
    }

    return base.render(template, extra_vars=extra_vars)


@pidinst_theme.route('/instruments')
def instruments_search():
    return _instrument_platform_search('false', 'instruments/search.html', 'pidinst_theme.instruments_search', display_type='instrument')


@pidinst_theme.route('/platforms')
def platforms_search():
    return _instrument_platform_search('true', 'platforms/search.html', 'pidinst_theme.platforms_search', display_type='platform')


def get_blueprints():
    return [pidinst_theme, analytics_views.analytics_bp]
