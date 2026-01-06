import ckan.plugins.toolkit as tk
import ckan.authz as authz
from ckan.lib.plugins import get_permission_labels
from ckan.logic.auth import get_package_object, get_resource_object

import logging


@tk.auth_allow_anonymous_access
def pidinst_theme_get_sum(context, data_dict):
    return {"success": True}


def user_is_member_of_package_org(user, package):
    """
    Return True if the package is in an organization and the user has the member role in
    that organization.

    :param user: A user object
    :param package: A package object
    :returns: True if the user has the 'member' role in the organization that owns the
              package, False otherwise
    """
    if package.owner_org:
        role_in_org = authz.users_role_for_group_or_org(package.owner_org, user.name)
        if role_in_org == 'member':
            return True
    return False


def user_owns_package_as_member(user, package):
    """
    Checks that the given user created the package, and has the 'member' role in the
    organization that owns the package.

    :param user: A user object
    :param package: A package object
    :returns: True if the user created the package and has the 'member' role in the
              organization to which package belongs. False otherwise.
    """
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
def package_update(next_auth, context, data_dict):
    user = context.get('auth_user_obj')

    try:
        package = get_package_object(context, data_dict)
    except:
        return {'success': False, 'msg': 'Unable to retrieve package'}

    if package.owner_org:
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        # Editors and admins can always edit a package
        if user_role in ['editor', 'admin']:
            return {'success': True}
        # Members can edit package if it hasn't been published (is private)
        elif user_role == 'member' and package.creator_user_id and package.creator_user_id == user.id and package.private:
            return {'success': True}
        else:
            return {'success': False, 'msg': 'Unauthorized to update dataset'}

    return next_auth(context, data_dict)


@tk.chained_auth_function
def package_delete(next_auth, context, data_dict):
    user = context['auth_user_obj']
    try:
        package = get_package_object(context, data_dict)
    except:
        return {'success': False, 'msg': 'Unable to retrieve package'}
    user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
    if user_role == 'admin':
        return {'success': True}
    elif not package.private:
        return {'success': False, 'msg': 'You are not authorised to delete a published dataset'}
    elif (user_role == 'member' or user_role == 'editor') and package.creator_user_id and user.id == package.creator_user_id:
        return {'success': True}
    else:
        return {'success': False, 'msg': 'Unauthorized to delete dataset'}

    return next_auth(context, data_dict)


@tk.chained_auth_function
def package_show(next_auth, context, data_dict):
    """
    Override package_show authorization to ignore auth if the package is public.
    """
    package = get_package_object(context, data_dict)
    package_id = data_dict.get('id')
    user = context.get('auth_user_obj')

    logger = logging.getLogger(__name__)
    # logger.info('Entering package_show auth override')

    if package:
        # logger.info(f'Package {package_id} found, private: {package.private}')
        if not package.private:
            return {'success': True}

    # if user:
    #     logger.info(f'User {user.name} with ID {user.id} is attempting to access package {package_id}')
    # else:
    #     logger.info(f'Anonymous user is attempting to access package {package_id}')
        
    if package and package.owner_org:
        user_role = authz.users_role_for_group_or_org(package.owner_org, user.name)
        if user_role == 'member' and package.private and hasattr(user, 'id') and package.creator_user_id != user.id:       
            return {'success': False, 'msg': 'This dataset is private.'}

    return next_auth(context, data_dict)


@tk.chained_auth_function
def package_list(next_auth, context, data_dict):
    """
    Let any user bring up a package list
    """
    return {'success': True}

def get_auth_functions():
    return {
        "pidinst_theme_get_sum": pidinst_theme_get_sum,
        "package_create": package_create,
        "package_update": package_update,
        "package_delete": package_delete,
        "package_show": package_show,
        "package_list": package_list,
    }
