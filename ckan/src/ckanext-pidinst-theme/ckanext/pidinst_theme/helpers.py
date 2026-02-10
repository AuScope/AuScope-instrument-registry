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

def pidinst_theme_hello():
    return "Hello, pidinst_theme!"

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


def users_role_in_org(user_name):
    # TODO: Get org name from config and pass in
    return authz.users_role_for_group_or_org(group_id='auscope', user_name=user_name)

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


    cloned_data['version_number'] = int(original_pkg_dict.get('version_number', 1)) + 1

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


def get_helpers():
    return {
        "pidinst_theme_hello": pidinst_theme_hello,
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
    }
