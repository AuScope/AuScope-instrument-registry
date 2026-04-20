import ckan.plugins.toolkit as tk
import ckan.authz as authz
import ckan.model as model
from ckan.logic.auth import get_package_object, get_resource_object
from ckanext.doi.model.crud import DOIQuery


def get_resource_view_object(context, data_dict=None):
    """Fetch a ResourceView model object by id, mirroring CKAN's get_*_object helpers."""
    resource_view = context.get('resource_view')
    if not resource_view:
        id_ = (data_dict or {}).get('id') or (data_dict or {}).get('resource_view_id')
        if id_:
            resource_view = model.ResourceView.get(id_)
        if not resource_view:
            raise tk.ObjectNotFound
    return resource_view

import logging


# ---------------------------------------------------------------------------
# DOI / Publication lifecycle helpers
# ---------------------------------------------------------------------------

def _package_extra_value(package, key):
    """Return the value of a package extra by key.

    Handles both the CKAN association proxy (dict-like mapping of key→value)
    and the legacy case where extras is a list of PackageExtra ORM objects.
    """
    extras = package.extras
    if not extras:
        return None
    if hasattr(extras, 'get'):
        return extras.get(key)
    for extra in extras:
        if extra.key == key:
            return extra.value
    return None


def _is_doi_published(package):
    """Return True if the package is public and has a published DOI record."""
    if package.private:
        return False
    doi_record = DOIQuery.read_package(package.id)
    return doi_record is not None and doi_record.published is not None


# ---------------------------------------------------------------------------
# Admin orgs configuration helpers
# Reads from config key ``ckanext.admin.orgs``
# (env var: ``CKANEXT__ADMIN__ORGS``, comma-separated org names/IDs).
# ---------------------------------------------------------------------------

def _get_configured_admin_orgs():
    """Return a list of org names/IDs from the ``ckanext.admin.orgs`` config key.

    Corresponds to the ``CKANEXT__ADMIN__ORGS`` environment variable.
    Comma-separated; whitespace trimmed; empty items ignored.
    """
    raw = tk.config.get('ckanext.admin.orgs') or ''
    return [o.strip() for o in raw.split(',') if o.strip()]


def _user_is_admin_of_org(user_name, org_id_or_name):
    """Return True if *user_name* holds the ``admin`` role in *org_id_or_name*."""
    try:
        role = authz.users_role_for_group_or_org(org_id_or_name, user_name)
        return role == 'admin'
    except Exception:
        return False


def _user_is_admin_of_any_configured_admin_org(user_name):
    """Return True if *user_name* is an admin of at least one org listed in
    ``ckanext.admin.orgs`` (env: ``CKANEXT__ADMIN__ORGS``).
    """
    configured_orgs = _get_configured_admin_orgs()
    if not configured_orgs:
        return False
    return any(_user_is_admin_of_org(user_name, org) for org in configured_orgs)


@tk.auth_allow_anonymous_access
def pidinst_theme_get_sum(context, data_dict):
    return {"success": True}


def user_is_member_of_package_org(user, package):
    """Return True if the user has the 'member' role in the package's organisation."""
    if package.owner_org:
        role_in_org = authz.users_role_for_group_or_org(package.owner_org, user.name)
        if role_in_org == 'member':
            return True
    return False


def user_owns_package_as_member(user, package):
    """Return True if the user created the package and has the 'member' role in its organisation."""
    if user_is_member_of_package_org(user, package):
        return package.creator_user_id and user.id == package.creator_user_id

    return False


@tk.chained_auth_function
def package_create(next_auth, context, data_dict):
    user = context.get('auth_user_obj')
    if data_dict and 'owner_org' in data_dict:
        user_role = authz.users_role_for_group_or_org(data_dict['owner_org'], user.name)
        # userdatasets only checks for 'member' here
        if user_role in ['admin', 'editor', 'member']:
            return {'success': True}
    else:
        if authz.has_user_permission_for_some_org(user.name, 'read'):
            return {'success': True}
    return next_auth(context, data_dict)
@tk.chained_auth_function
def resource_create(next_auth, context, data_dict):
    user = context['auth_user_obj']
    package = get_package_object(context, {'id': data_dict['package_id']})

    if package.owner_org:
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        # Admins can always edit a resource
        if user_role == 'admin':
            return {'success': True}
        # Can't edit a published resource unless admin
        elif not package.private:
            return {'success': False, 'msg': 'You are not authorised to add a resource to a published instrument'}
        # Members and editors can only update their own resources IF the instrument has not been published (private)
        elif (user_role == 'member' or user_role == 'editor') and package.creator_user_id and package.creator_user_id == user.id:
            return {'success': True}

    return next_auth(context, data_dict)


@tk.chained_auth_function
def resource_view_create(next_auth, context, data_dict):
    user = context['auth_user_obj']
    # data_dict provides 'resource_id', while get_resource_object expects 'id'. This is
    # not consistent with the rest of the API - so future proof it by catering for both
    # cases in case the API is made consistent (one way or the other) later.
    if data_dict and 'resource_id' in data_dict:
        dc = {'id': data_dict['resource_id'], 'resource_id': data_dict['resource_id']}
    elif data_dict and 'id' in data_dict:
        dc = {'id': data_dict['id'], 'resource_id': data_dict['id']}
    else:
        dc = data_dict
    resource = get_resource_object(context, dc)

    if resource and resource.package and resource.package.owner_org:
        package = resource.package
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        # Editors and admins can always view a resoure
        if user_role in ['editor', 'admin']:
            return {'success': True}
        # Members can view their own resources
        elif user_role == 'member' and package.creator_user_id and package.creator_user_id == user.id:
            return {'success': True}
        # Member is an editing collaborator
        elif hasattr(user, 'id') and authz.user_is_collaborator_on_dataset(user.id, package.id, ['editor']):
            return {'success': True}
        else:
            return {'success': False, 'msg': 'Unauthorized to view instrument'}

    return next_auth(context, data_dict)

@tk.chained_auth_function
def package_update(next_auth, context, data_dict):
    user = context.get('auth_user_obj')

    try:
        package = get_package_object(context, data_dict)
    except:
        return {'success': False, 'msg': 'Unable to retrieve package'}

    # Block editing of withdrawn/duplicate records for all roles.
    # To allow admins later, add: `and not _is_org_admin(user, package)` to the condition.
    pub_status = _package_extra_value(package, 'publication_status') or ''
    if pub_status in ('withdrawn', 'duplicate'):
        return {
            'success': False,
            'msg': 'This record cannot be edited because it has been withdrawn or marked as duplicate.',
        }

    if package.owner_org:
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        # Editors and admins can always edit a package
        if user_role in ['editor', 'admin']:
            return {'success': True}
        # Members can edit package if it hasn't been published (is private)
        elif user_role == 'member' and package.creator_user_id and package.creator_user_id == user.id and package.private:
            return {'success': True}
        else:
            return {'success': False, 'msg': 'Unauthorized to update instrument'}

    return next_auth(context, data_dict)

@tk.chained_auth_function
def resource_update(next_auth, context, data_dict):
    user = context['auth_user_obj']
    resource = get_resource_object(context, data_dict)
    package = resource.package

    if package.owner_org:
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        # Admins and editors can always edit a resource
        if user_role == 'admin':
            return {'success': True}
        # Can't edit a published resource unless admin/editor
        elif not package.private:
            return {'success': False, 'msg': 'You are not authorised to edit a resource of a published instrument'}
        # Members and editors can only update their own resources IF the instrument has not been published (private)
        elif (user_role == 'member' or user_role=='editor') and package.creator_user_id and package.creator_user_id == user.id:
            return {'success': True}
        # Member is an editing collaborator and package has not been published
        elif hasattr(user, 'id') and authz.user_is_collaborator_on_dataset(user.id, package.id, ['editor']):
            return {'success': True}

    return next_auth(context, data_dict)


@tk.chained_auth_function
def resource_view_update(next_auth, context, data_dict):
    user = context['auth_user_obj']
    resource_view = get_resource_view_object(context, data_dict)
    resource = get_resource_object(context, {'id': resource_view.resource_id})
    package = resource.package

    if package.owner_org:
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        # Admins can always edit a resource
        if user_role == 'admin':
            return {'success': True}
        # Can't edit a published resource unless admin
        elif not package.private:
            return {'success': False, 'msg': 'You are not authorised to edit a resource view of a published instrument'}
        # Members and editors can only update their own resources IF the instrument has not been published (private)
        elif (user_role == 'member' or user_role == 'editor') and package.creator_user_id and package.creator_user_id == user.id:
            return {'success': True}

    return next_auth(context, data_dict)

@tk.chained_auth_function
def package_delete(next_auth, context, data_dict):
    user = context['auth_user_obj']
    try:
        package = get_package_object(context, data_dict)
    except:
        return {'success': False, 'msg': 'Unable to retrieve package'}

    if not package.private:
        return {'success': False, 'msg': 'Public records cannot be deleted. Use the withdraw workflow instead.'}

    user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
    if user_role == 'admin':
        return {'success': True}
    elif (user_role == 'member' or user_role == 'editor') and package.creator_user_id and user.id == package.creator_user_id:
        return {'success': True}
    else:
        return {'success': False, 'msg': 'Unauthorized to delete instrument'}

@tk.chained_auth_function
def resource_delete(next_auth, context, data_dict):
    user = context['auth_user_obj']
    resource = get_resource_object(context, data_dict)
    package = resource.package

    user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
    if user_role == 'admin':
        return {'success': True}
    elif not package.private:
            return {'success': False, 'msg': 'You are not authorised to delete a published resource'}
    elif (user_role == 'member' or user_role == 'editor') and package.creator_user_id and user.id == package.creator_user_id:
        return {'success': True}
    else:
        return {'success': False, 'msg': 'Unauthorized to delete resource'}

    return next_auth(context, data_dict)


@tk.chained_auth_function
def resource_view_delete(next_auth, context, data_dict):
    user = context['auth_user_obj']
    resource_view = get_resource_view_object(context, data_dict)
    resource = get_resource_object(context, {'id': resource_view.resource_id})
    package = resource.package

    user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
    if user_role == 'admin':
        return {'success': True}
    elif not package.private:
            return {'success': False, 'msg': 'You are not authorised to delete a published resource view'}
    elif (user_role == 'member' or user_role == 'editor') and package.creator_user_id and user.id == package.creator_user_id:
        return {'success': True}
    else:
        return {'success': False, 'msg': 'Unauthorized to delete resource view'}

    return next_auth(context, data_dict)

@tk.chained_auth_function
@tk.auth_allow_anonymous_access
def package_show(next_auth, context, data_dict):
    package = get_package_object(context, data_dict)
    user = context.get('auth_user_obj')

    if package:
        if not package.private:
            return {'success': True}

    if package and package.owner_org and user:
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        if user_role == 'member' and package.private and hasattr(user, 'id') and package.creator_user_id != user.id:
            return {'success': False, 'msg': 'This instrument is private.'}

    return next_auth(context, data_dict)


@tk.chained_auth_function
@tk.auth_allow_anonymous_access
def package_list(next_auth, context, data_dict):
    """
    Let any user bring up a package list
    """
    return {'success': True}


def _require_org_admin_or_editor(context, data_dict, action_label):
    """Shared auth check: allow only org admins/editors."""
    user = context.get('auth_user_obj')
    if not user:
        return {'success': False, 'msg': f'Must be logged in to {action_label}.'}
    try:
        package = get_package_object(context, data_dict)
    except Exception:
        return {'success': False, 'msg': 'Unable to retrieve package.'}
    if not package.owner_org:
        return {'success': False, 'msg': 'Package has no organisation.'}
    user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
    if user_role in ('admin', 'editor'):
        return {'success': True}
    return {'success': False, 'msg': f'Only org admins or editors can {action_label}.'}


def package_mark_duplicate(context, data_dict):
    return _require_org_admin_or_editor(context, data_dict, 'mark a record as duplicate')


def package_withdraw(context, data_dict):
    return _require_org_admin_or_editor(context, data_dict, 'withdraw a record')


# ---------------------------------------------------------------------------
# Group auth functions
# Allow sysadmins (handled by core), any user already allowed by core auth,
# and users who are admins of at least one ``CKANEXT__ADMIN__ORGS`` org.
# ---------------------------------------------------------------------------

def _group_auth(next_auth, context, data_dict, action_label):
    """Shared logic for group_create and group_update."""
    user = context.get('auth_user_obj')
    if not user:
        return {'success': False, 'msg': f'Must be logged in to {action_label} a group.'}

    # Let core auth decide first (covers sysadmin and any other defaults).
    core_result = next_auth(context, data_dict)
    if core_result.get('success'):
        return core_result

    # Extend: allow if user is admin of any configured admin org.
    if _user_is_admin_of_any_configured_admin_org(user.name):
        return {'success': True}

    return {'success': False, 'msg': f'Not authorized to {action_label} groups.'}


@tk.chained_auth_function
def group_create(next_auth, context, data_dict):
    return _group_auth(next_auth, context, data_dict, 'create')


@tk.chained_auth_function
def group_update(next_auth, context, data_dict):
    return _group_auth(next_auth, context, data_dict, 'update')


def get_auth_functions():
    return {
        "pidinst_theme_get_sum": pidinst_theme_get_sum,
        "package_create": package_create,
        "resource_create": resource_create,
        "resource_view_create": resource_view_create,
        "package_update": package_update,
        "resource_update": resource_update,
        "resource_view_update": resource_view_update,
        "package_delete": package_delete,
        "resource_delete": resource_delete,
        "resource_view_delete": resource_view_delete,
        "package_show": package_show,
        "package_list": package_list,
        "package_withdraw": package_withdraw,
        "package_mark_duplicate": package_mark_duplicate,
        "group_create": group_create,
        "group_update": group_update,
    }
