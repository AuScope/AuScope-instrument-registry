from ckan.plugins import toolkit
import ckan.logic as logic
import ckan.authz as authz
from datetime import date
from ckan.logic import NotFound
from ckan.lib.munge import munge_title_to_name
import simplejson as json
import logging
import os
from markupsafe import Markup

# ---------------------------------------------------------------------------
# Taxonomy name configuration – single source of truth
# ---------------------------------------------------------------------------
# Logical keys used in instrument_schema.yaml  →  CKAN config keys  →  defaults
# Override via env vars, e.g. CKANEXT__PIDINST_THEME__TAXONOMY__INSTRUMENT=Instruments
_TAXONOMY_CONFIG_KEYS = {
    'instrument':        'ckanext.pidinst_theme.taxonomy.instrument',
    'platform':          'ckanext.pidinst_theme.taxonomy.platform',
    'measured_variable':  'ckanext.pidinst_theme.taxonomy.measured_variable',
}
_TAXONOMY_DEFAULTS = {
    'instrument':        'instruments',
    'platform':          'platforms',
    'measured_variable':  'measured-variables',
}


def get_taxonomy_name(logical_key):
    """Resolve a logical taxonomy key to the actual DB taxonomy name.

    Reads from CKAN config (which is populated from env vars).  If the key
    is not recognised it is returned unchanged so that a literal name still
    works as a passthrough.
    """
    config_key = _TAXONOMY_CONFIG_KEYS.get(logical_key)
    if config_key:
        return toolkit.config.get(config_key, _TAXONOMY_DEFAULTS[logical_key])
    return logical_key


def get_allowed_taxonomies():
    """Return the set of all configured taxonomy DB names."""
    return {get_taxonomy_name(k) for k in _TAXONOMY_CONFIG_KEYS}

def pidinst_theme_hello():
    return "Hello, pidinst_theme!"


def pidinst_parse_json_list(value):
    """
    Parse a value that might be a JSON array string, Python list, or fallback to empty list.
    Used by templates to safely parse field values for prepopulating Select2.

    Args:
        value: Can be a JSON string like '["a","b"]', a Python list, or other formats

    Returns:
        list: A list of string values
    """
    if not value:
        return []

    # If already a list, return it
    if isinstance(value, list):
        return [str(v).strip() for v in value if v and str(v).strip()]

    # If string, try to parse as JSON
    if isinstance(value, str):
        value = value.strip()
        if not value or value in ('[]', '""', 'null', 'None'):
            return []

        if value.startswith('['):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if v and str(v).strip()]
            except (json.JSONDecodeError, ValueError):
                # Try Python-style single quotes
                try:
                    fixed = value.replace("'", '"')
                    parsed = json.loads(fixed)
                    if isinstance(parsed, list):
                        return [str(v).strip() for v in parsed if v and str(v).strip()]
                except (json.JSONDecodeError, ValueError):
                    pass

        # Comma-separated fallback
        if ',' in value:
            return [v.strip() for v in value.split(',') if v.strip()]

        # Single value
        if value.strip():
            return [value.strip()]

    return []


def is_creating_or_editing_dataset():
    """Determine if the user is creating or editing a dataset."""
    current_path = toolkit.request.path
    if current_path.startswith('/dataset/new'):
        return True
    elif "/dataset/edit/" in current_path:
        return True
    return False

def is_creating_or_editing_org():
    """Determine if the user is creating or editing an organization."""
    current_path = toolkit.request.path
    if (
        current_path.startswith('/organization/request_join_organisation') or
        current_path.startswith('/organization/request_new_organisation') or
        current_path.startswith('/organization/new') or
        current_path.startswith('/organization/edit') or
        current_path.startswith('/organization/members') or
        current_path.startswith('/organization/bulk_process') or
        current_path == '/organization/'
    ):
        return True
    return False

def get_search_facets():
    context = {'ignore_auth': True}
    data_dict = {
        'q': '*:*',
        'facet.field': toolkit.h.facets(),
        'rows': 4,
        'start': 0,
        'sort': 'view_recent desc',
        'fq': 'capacity:"public"'
    }
    try:
        query = logic.get_action('package_search')(context, data_dict)
        return query['search_facets']
    except toolkit.ObjectNotFound:
        return {}


def get_org_list():
    return toolkit.get_action('organization_list_for_user')()


def users_role_in_org(user_name, org_id=None):
    # If no org_id supplied, fall back to 'auscope-org' for backward compatibility
    if not org_id:
        org_id = 'auscope-org'
    return authz.users_role_for_group_or_org(group_id=org_id, user_name=user_name)

def current_date():
    return date.today().isoformat()

def get_package(package_id):
    """Retrieve package details given an ID or return None if not found."""
    context = {'ignore_auth': True}
    try:
        return toolkit.get_action('package_show')(context, {'id': package_id})
    except NotFound:
        return None
    except toolkit.NotAuthorized:
        return None


def get_user_role_in_organization(org_id):
    if not toolkit.c.user:
        return None

    user_role = authz.users_role_for_group_or_org(org_id, toolkit.c.user)
    return user_role

def custom_structured_data(dataset_id, profiles=None, _format='jsonld'):
    '''
    Returns a string containing the structured data of the given
    dataset id and using the given profiles (if no profiles are supplied
    the default profiles are used).

    This string can be used in the frontend.
    '''
    context = {'ignore_auth': True}

    if not profiles:
        profiles = ['schemaorg']

    data = toolkit.get_action('dcat_dataset_show')(
        context,
        {
            'id': dataset_id,
            'profiles': profiles,
            'format': _format,
        }
    )
    # parse result again to prevent UnicodeDecodeError and add formatting
    try:
        json_data = json.loads(data)
        return json.dumps(json_data, sort_keys=True,
                          indent=4, separators=(',', ': '), cls=json.JSONEncoderForHTML)
    except ValueError:
        # result was not JSON, return anyway
        return data


def rudderstack_script():
    """
    Generate RudderStack analytics script tag with configuration from environment variables.
    Returns the script as safe HTML if RudderStack is enabled, empty string otherwise.
    """
    # Check if RudderStack is enabled
    rudderstack_enabled = toolkit.asbool(os.environ.get('RUDDERSTACK_ENABLED', 'false'))

    if not rudderstack_enabled:
        return Markup('')

    # Get configuration from environment variables
    write_key = os.environ.get('RUDDERSTACK_WRITE_KEY', '')
    data_plane_url = os.environ.get('RUDDERSTACK_DATA_PLANE_URL', '')

    if not write_key or not data_plane_url:
        logging.warning('RudderStack enabled but WRITE_KEY or DATA_PLANE_URL not configured')
        return Markup('')

    script = f'''
<script type="text/javascript">
(function() {{
  "use strict";
  window.RudderSnippetVersion = "3.2.0";
  var identifier = "rudderanalytics";
  if (!window[identifier]) {{
    window[identifier] = [];
  }}
  var rudderanalytics = window[identifier];
  if (Array.isArray(rudderanalytics)) {{
    if (rudderanalytics.snippetExecuted === true && window.console && console.error) {{
      console.error("RudderStack JavaScript SDK snippet included more than once.");
    }} else {{
      rudderanalytics.snippetExecuted = true;
      window.rudderAnalyticsBuildType = "legacy";
      var sdkBaseUrl = "https://cdn.rudderlabs.com";
      var sdkVersion = "v3";
      var sdkFileName = "rsa.min.js";
      var scriptLoadingMode = "async";
      var methods = [ "setDefaultInstanceKey", "load", "ready", "page", "track", "identify", "alias", "group", "reset", "setAnonymousId", "startSession", "endSession", "consent", "addCustomIntegration" ];
      for (var i = 0; i < methods.length; i++) {{
        var method = methods[i];
        rudderanalytics[method] = function(methodName) {{
          return function() {{
            if (Array.isArray(window[identifier])) {{
              rudderanalytics.push([ methodName ].concat(Array.prototype.slice.call(arguments)));
            }} else {{
              var _methodName;
              (_methodName = window[identifier][methodName]) === null || _methodName === undefined || _methodName.apply(window[identifier], arguments);
            }}
          }};
        }}(method);
      }}
      try {{
        new Function('class Test{{field=()=>{{}};test({{prop=[]}}={{}}){{return prop?(prop?.property??[...prop]):import("");}}}}');
        window.rudderAnalyticsBuildType = "modern";
      }} catch (e) {{}}
      var head = document.head || document.getElementsByTagName("head")[0];
      var body = document.body || document.getElementsByTagName("body")[0];
      window.rudderAnalyticsAddScript = function(url, extraAttributeKey, extraAttributeVal) {{
        var scriptTag = document.createElement("script");
        scriptTag.src = url;
        scriptTag.setAttribute("data-loader", "RS_JS_SDK");
        if (extraAttributeKey && extraAttributeVal) {{
          scriptTag.setAttribute(extraAttributeKey, extraAttributeVal);
        }}
        if (scriptLoadingMode === "async") {{
          scriptTag.async = true;
        }} else if (scriptLoadingMode === "defer") {{
          scriptTag.defer = true;
        }}
        if (head) {{
          head.insertBefore(scriptTag, head.firstChild);
        }} else {{
          body.insertBefore(scriptTag, body.firstChild);
        }}
      }};
      window.rudderAnalyticsMount = function() {{
        (function() {{
          if (typeof globalThis === "undefined") {{
            var getGlobal = function getGlobal() {{
              if (typeof self !== "undefined") {{
                return self;
              }}
              if (typeof window !== "undefined") {{
                return window;
              }}
              return null;
            }};
            var global = getGlobal();
            if (global) {{
              Object.defineProperty(global, "globalThis", {{
                value: global,
                configurable: true
              }});
            }}
          }}
        }})();
        window.rudderAnalyticsAddScript("".concat(sdkBaseUrl, "/").concat(sdkVersion, "/").concat(window.rudderAnalyticsBuildType, "/").concat(sdkFileName), "data-rsa-write-key", "{write_key}");
      }};
      if (typeof Promise === "undefined" || typeof globalThis === "undefined") {{
        window.rudderAnalyticsAddScript("https://polyfill-fastly.io/v3/polyfill.min.js?version=3.111.0&features=Symbol%2CPromise&callback=rudderAnalyticsMount");
      }} else {{
        window.rudderAnalyticsMount();
      }}
      var loadOptions = {{}};
      rudderanalytics.load("{write_key}", "{data_plane_url}", loadOptions);
      // Automatically track page view when SDK is ready
      rudderanalytics.ready(function() {{
        rudderanalytics.page();
      }});    }}
  }}
}})();
</script>
'''
    return Markup(script)


def analytics_enabled():
    """Check if analytics tracking is enabled"""
    return toolkit.asbool(os.environ.get('RUDDERSTACK_ENABLED', 'false'))


def get_analytics_config():
    """Get analytics configuration for frontend"""
    return {
        'enabled': analytics_enabled(),
        'write_key': os.environ.get('RUDDERSTACK_WRITE_KEY', ''),
        'data_plane_url': os.environ.get('RUDDERSTACK_DATA_PLANE_URL', ''),
    }


def prepare_dataset_for_cloning(original_pkg_dict, original_pkg_id):
    """
    Prepare a dataset dict for cloning as a new version.
    Removes fields that should not be copied and adds IsNewVersionOf relationship.

    Args:
        original_pkg_dict: The original package dictionary
        original_pkg_id: The ID of the original package

    Returns:
        A modified copy of the package dict ready for creating a new version
    """
    import copy
    import re
    from datetime import datetime

    # Create a deep copy to avoid modifying the original
    cloned_data = copy.deepcopy(original_pkg_dict)

    # Fields to remove (these should be generated fresh for the new version)
    fields_to_remove = [
        'id',
        'name',  # Will be auto-generated
        'doi',   # DOI should be generated for new version
        'revision_id',
        'metadata_created',
        'metadata_modified',
        'creator_user_id',
        'num_resources',
        'num_tags',
        'organization',  # Will be set from form
        'relationships_as_subject',
        'relationships_as_object',
        'state',  # Start fresh as draft
        'version',  # User should specify new version
    ]

    for field in fields_to_remove:
        cloned_data.pop(field, None)

    # Generate a better default title with date
    original_title = original_pkg_dict.get('title', '')
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Check if title already has a date pattern like [YYYY-MM-DD] or (YYYY-MM-DD)
    date_pattern = r'[\[\(]?\d{4}-\d{2}-\d{2}[\]\)]?'
    if re.search(date_pattern, original_title):
        # Replace existing date with new date
        new_title = re.sub(date_pattern, f'[{current_date}]', original_title)
    else:
        # Append new date
        new_title = f"{original_title} [{current_date}]"

    cloned_data['title'] = new_title

    # bump version number
    cloned_data['version_number'] = int(original_pkg_dict.get('version_number', 1)) + 1

    # add version grouping id
    cloned_data['version_handler_id'] = original_pkg_dict.get('version_handler_id', original_pkg_id)

    # Generate a slug for the URL so the form starts with a valid default
    cloned_data['name'] = munge_title_to_name(new_title)

    # Set visibility to private by default to prevent accidental DOI minting
    cloned_data['private'] = True

    # Get or initialize related_identifier_obj field (composite repeating field)
    related_identifiers = cloned_data.get('related_identifier_obj', [])
    if isinstance(related_identifiers, str):
        try:
            related_identifiers = json.loads(related_identifiers)
        except:
            related_identifiers = []
    elif not isinstance(related_identifiers, list):
        related_identifiers = []

    # Prepare IsNewVersionOf relationship to the original instrument
    original_doi = original_pkg_dict.get('doi', '')
    original_title = original_pkg_dict.get('title', '')

    # Create the new relationship entry with all required fields matching schema
    new_relationship = {
        'related_identifier': original_doi if original_doi else toolkit.url_for('dataset.read',
                                                                                  id=original_pkg_id,
                                                                                  qualified=True),
        'related_identifier_name': original_title,
        'related_identifier_type': 'DOI' if original_doi else 'URL',
        'relation_type': 'IsNewVersionOf',
        'related_resource_type': 'Version',
        '_is_version_relationship': True  # Mark this as a version relationship
    }

    # Find and remove existing IsNewVersionOf relationship from the list
    related_identifiers = [rel for rel in related_identifiers if rel.get('relation_type') != 'IsNewVersionOf']

    # Add the new IsNewVersionOf relationship at the START of the list
    related_identifiers.insert(0, new_relationship)

    cloned_data['related_identifier_obj'] = related_identifiers
    cloned_data['resources'] = []

    return cloned_data

def pidinst_upload_help_html():
    return toolkit.literal(
        '<div class="info-block pidinst-upload-help" style="font-size: 0.9em; margin-bottom: 20px;">'
        '<i class="fa fa-info-circle"></i> '
        'There is a time limit of 10 minutes for each upload. '
        'If you experience a timeout error due to a large upload, please contact us via the '
        '<a href="/contact" target="_blank">Contact Form</a>. '
        'We will assist you with data migration.<br>'
        '<b>'
        'Uploading via the browser can take time, please be patient and do not navigate away from this page while uploading.'
        '</b>'
        '</div>'
    )

def get_cover_photo_info(package_id, current_resource_id=None):
    """Return info about the existing cover photo resource for a dataset,
    excluding *current_resource_id* (the resource being edited).

    Returns a dict ``{'id': ..., 'name': ...}`` or ``None``.
    """
    if not package_id:
        return None
    context = {'ignore_auth': True}
    try:
        pkg = toolkit.get_action('package_show')(context, {'id': package_id})
    except Exception:
        return None
    for r in pkg.get('resources', []):
        cover_val = (r.get('extras') or {}).get('pidinst_is_cover_image') or r.get('pidinst_is_cover_image')
        if cover_val in (True, 'true', 'True'):
            if current_resource_id and r['id'] == current_resource_id:
                continue
            return {'id': r['id'], 'name': r.get('name') or 'Unnamed resource'}
    return None


def pidinst_instrument_meta(pkg_dict):
    """Return a dict with display-ready model name and serial/alternate identifier
    for the given package dict.

    ``model``                  – composite_repeating; first record wins.
    ``alternate_identifier_obj`` – composite_repeating; SerialNumber-type entry
                                   has priority, otherwise first record.

    Returns::

        {
          'model_name': str | None,
          'alt_identifier': str | None,   # the actual identifier value
          'alt_identifier_label': str,    # human-readable type label
        }
    """
    def _parse_composite(pkg_dict, field_name):
        """Return a list of dicts for a composite_repeating field."""
        value = pkg_dict.get(field_name)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [v for v in parsed if isinstance(v, dict)]
            except (ValueError, TypeError):
                pass
        if isinstance(value, dict):
            return [value]
        return []

    # --- Model name: first record ---
    models = _parse_composite(pkg_dict, 'model')
    model_name = models[0].get('model_name') if models else None

    # --- Alternate identifier: SerialNumber priority, then first ---
    alt_ids = _parse_composite(pkg_dict, 'alternate_identifier_obj')
    chosen = next(
        (a for a in alt_ids if a.get('alternate_identifier_type') == 'SerialNumber'),
        alt_ids[0] if alt_ids else None
    )

    alt_identifier = None
    alt_identifier_label = 'Identifier'
    if chosen:
        alt_identifier = chosen.get('alternate_identifier') or chosen.get('alternate_identifier_name')
        raw_type = chosen.get('alternate_identifier_type', '')
        _type_labels = {
            'SerialNumber': 'Serial #',
            'InventoryNumber': 'Inventory #',
            'Other': chosen.get('alternate_identifier_name') or 'Identifier',
        }
        alt_identifier_label = _type_labels.get(raw_type, raw_type)

    return {
        'model_name': model_name,
        'alt_identifier': alt_identifier,
        'alt_identifier_label': alt_identifier_label,
    }


def pidinst_cover_image_url(pkg_dict):
    resources = pkg_dict.get("resources") or []
    cover = None
    for r in resources:
        extras = r.get("extras") or {}
        # Check for boolean True, string "true", or string "True"
        cover_img_value = extras.get("pidinst_is_cover_image") or r.get("pidinst_is_cover_image")
        if cover_img_value in (True, "true", "True"):
            cover = r
            break

    if not cover:
        return None
    return toolkit.url_for("resource.download", id=pkg_dict["name"], resource_id=cover["id"])


def json_loads(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


def get_party_list():
    """Return all Party groups with flattened extras for template use.

    Each item in the returned list is a dict with at minimum:
        name   – CKAN group name (slug)
        title  – display title
    Plus any extras stored on the group (e.g. party_contact, ror_id …).
    The list is sorted alphabetically by title.

    Uses group_show per party (not group_list) because group_list's
    include_extras parameter is unreliable across CKAN versions — it may
    return an empty extras list even when extras exist.
    """
    try:
        context = {'ignore_auth': True}
        # Get the list of party slugs first
        names = toolkit.get_action('group_list')(context, {
            'type': 'party',
        })
        result = []
        for name in names:
            try:
                g = toolkit.get_action('group_show')(context, {
                    'id': name,
                    'include_extras': True,
                })
                # Start with ALL top-level keys — ckanext-scheming returns
                # custom fields (e.g. party_contact) as top-level keys on
                # group_show, not inside the extras list.
                item = dict(g)
                # Also flatten extras list in case any extras weren't promoted
                for e in g.get('extras', []):
                    item[e['key']] = e['value']
                result.append(item)
            except Exception:
                pass
        return sorted(result, key=lambda x: x.get('title', '').lower())
    except Exception:
        return []


_PARTY_LABELS = {
    'default label': 'Party',
    'default label plural': 'Parties',
    'create label': 'Add Party',
    'update label': 'Update Party',
    'breadcrumb': 'Parties',
    'main nav': 'Parties',
    'no label found': 'Party',
}


def humanize_entity_type(entity_type, object_type, purpose):
    """Override CKAN's core humanize_entity_type to return proper labels for
    the 'party' group type (avoiding the naive 'partys' pluralization).
    Falls through to CKAN's own implementation for all other types."""
    if object_type == 'party':
        return _PARTY_LABELS.get(purpose, 'Party')
    # Let CKAN's built-in helper handle everything else
    from ckan.lib.helpers import humanize_entity_type as _core
    return _core(entity_type, object_type, purpose)


def doi_resolver_url():
    return toolkit.config.get('ckanext.doi.resolver_url', 'https://doi.org/').rstrip('/')


def get_helpers():
    return {
        "pidinst_theme_hello": pidinst_theme_hello,
        "pidinst_parse_json_list": pidinst_parse_json_list,
        "is_creating_or_editing_dataset" :is_creating_or_editing_dataset,
        "is_creating_or_editing_org" : is_creating_or_editing_org,
        'get_org_list': get_org_list,
        'users_role_in_org': users_role_in_org,
        "get_search_facets" : get_search_facets,
        'current_date': current_date,
        "get_package": get_package,
        "get_user_role_in_organization" : get_user_role_in_organization,
        "custom_structured_data" : custom_structured_data,
        "rudderstack_script": rudderstack_script,
        "analytics_enabled": analytics_enabled,
        "get_analytics_config": get_analytics_config,
        "prepare_dataset_for_cloning": prepare_dataset_for_cloning,
        "pidinst_upload_help_html": pidinst_upload_help_html,
        "pidinst_cover_image_url": pidinst_cover_image_url,
        "get_cover_photo_info": get_cover_photo_info,
        "pidinst_instrument_meta": pidinst_instrument_meta,
        "json_loads": json_loads,
        "humanize_entity_type": humanize_entity_type,
        "get_party_list": get_party_list,
        "doi_resolver_url": doi_resolver_url,
        "get_taxonomy_name": get_taxonomy_name,
    }
