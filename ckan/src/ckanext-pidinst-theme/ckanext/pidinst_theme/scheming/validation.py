#from ckantoolkit import _


from typing import Any
import ckan.lib.navl.dictization_functions as df
import ckan.logic as logic
import ckan.authz as authz

from ckan.types import (
    FlattenDataDict, FlattenKey, Context, FlattenErrorDict
)

from organisations import OrderedDict
import ckan.model as model
from typing import Any, Optional

from logging import getLogger

log = getLogger(__name__)

Invalid = df.Invalid
StopOnError = df.StopOnError
Missing = df.Missing
missing = df.missinglog = getLogger(__name__)


UPDATED_ROLE_PERMISSIONS: dict[str, list[str]] = OrderedDict([
    ('admin', ['admin', 'membership']),
    ('editor', ['read', 'delete_dataset', 'create_dataset',
                'update_dataset', 'manage_group']),
    ('member', ['read', 'delete_dataset', 'create_dataset',
                'update_dataset', 'manage_group']),
])

def has_user_permission_for_group_or_org(group_id: Optional[str],
                                         user_name: Optional[str],
                                         permission: str) -> bool:
    if not group_id:
        return False
    group = model.Group.get(group_id)
    if not group:
        return False
    group_id = group.id

    # Sys admins can do anything
    if authz.is_sysadmin(user_name):
        return True

    user_id = authz.get_user_id_for_username(user_name, allow_none=True)
    if not user_id:
        return False
    if _has_user_permission_for_groups(user_id, permission, [group_id]):
        return True
    capacities = check_config_permission('roles_that_cascade_to_sub_groups')
    assert isinstance(capacities, list)
    # Handle when permissions cascade. Check the user's roles on groups higher
    # in the group hierarchy for permission.
    for capacity in capacities:
        parent_groups = group.get_parent_group_hierarchy(type=group.type)
        group_ids = [group_.id for group_ in parent_groups]
        if _has_user_permission_for_groups(user_id, permission, group_ids,
                                           capacity=capacity):
            return True
    return False


def _has_user_permission_for_groups(
        user_id: str, permission: str, group_ids: list[str],
        capacity: Optional[str]=None) -> bool:
    ''' Check if the user has the given permissions for the particular
    group (ignoring permissions cascading in a group hierarchy).
    Can also be filtered by a particular capacity.
    '''
    if not group_ids:
        return False
    # get any roles the user has for the group
    q: Any = (model.Session.query(model.Member.capacity)
         # type_ignore_reason: attribute has no method
         .filter(model.Member.group_id.in_(group_ids))
         .filter(model.Member.table_name == 'user')
         .filter(model.Member.state == 'active')
         .filter(model.Member.table_id == user_id))

    if capacity:
        q = q.filter(model.Member.capacity == capacity)
    # see if any role has the required permission
    # admin permission allows anything for the group
    for row in q:
        perms = UPDATED_ROLE_PERMISSIONS.get(row.capacity, [])
        if 'admin' in perms or permission in perms:
            return True
    return False


# A dictionary to store your validators
all_validators = {}

def register_validator(fn):
    """
    collect validator functions into ckanext.scheming.all_helpers dict
    """
    all_validators[fn.__name__] = fn
    return fn


def scheming_validator(fn):
    """
    Decorate a validator that needs to have the scheming fields
    passed with this function. When generating navl validator lists
    the function decorated will be called passing the field
    and complete schema to produce the actual validator for each field.
    """
    fn.is_a_scheming_validator = True
    return fn
