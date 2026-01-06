from ckan.plugins import toolkit
import ckan.logic as logic
import ckan.authz as authz
from datetime import date
from ckan.logic import NotFound
import simplejson as json
import logging

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
        current_path.startswith('/organization/request_join_collection') or 
        current_path.startswith('/organization/request_new_collection') or
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
        "custom_structured_data" : custom_structured_data
    }
