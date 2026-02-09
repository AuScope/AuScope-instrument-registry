import ckan.plugins.toolkit as tk
from ckantoolkit import ( _, missing , get_validator )
import inspect
import json

import ckanext.scheming.helpers as sh
import ckan.lib.navl.dictization_functions as df
from typing import Any, Union, Optional

from ckanext.scheming.validation import scheming_validator, register_validator
from ckan.logic import NotFound


from ckan.logic.validators import owner_org_validator as ckan_owner_org_validator
from ckan.authz import users_role_for_group_or_org

from pprint import pformat
import geojson
from shapely.geometry import shape, mapping
from datetime import datetime

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

StopOnError = df.StopOnError
not_empty = get_validator('not_empty')
missing_error = _("Missing value")
invalid_error = _("Invalid value")
# A dictionary to store your validators
all_validators = {}


def add_error(errors, key, error_message):
    errors[key] = errors.get(key, [])
    errors[key].append(error_message)

@scheming_validator
@register_validator
def location_validator(field, schema):
    def validator(key, data, errors, context):
        location_choice_key = ('location_choice',)
        location_data_key = ('location_data',)
        epsg_code_key = ('epsg_code',)

        location_choice = data.get(location_choice_key, missing)
        location_data = data.get(location_data_key, missing)
        epsg_code = data.get(epsg_code_key, missing)

        # Exit the validation for noLocation choice
        if location_choice == 'noLocation':
            for key in [location_data_key]:
                data[key] = None
            return

        # Check if location_data needs parsing or is already a dict
        if isinstance(location_data, str):
            try:
                location_data = json.loads(location_data)
            except ValueError:
                add_error(errors,location_data_key, invalid_error)
                return
        elif not isinstance(location_data, dict):
            add_error(errors,location_data_key, invalid_error)
            return


        features = location_data.get('features', [])
        if not features:
            add_error(errors,location_data_key, missing_error)
            return

        if location_choice == 'point':
            for feature in features:
                if feature['geometry']['type'] == 'Point':
                    coords = feature['geometry']['coordinates']
                    if not is_valid_longitude(coords[0]) or not is_valid_latitude(coords[1]):
                        add_error(errors,location_data_key, invalid_error)
                        break

        elif location_choice == 'area':
            for feature in features:
                if feature['geometry']['type'] == 'Polygon':
                    for polygon in feature['geometry']['coordinates']:
                        for coords in polygon:
                            if not is_valid_longitude(coords[0]) or not is_valid_latitude(coords[1]):
                                add_error(errors,location_data_key, invalid_error)
                                return

        else:
            add_error(errors, location_data_key, missing_error)

        if location_choice is missing and field.get('required', False):
            add_error(errors, location_choice_key, missing_error)

        if epsg_code is missing:
            add_error(errors, epsg_code_key, missing_error)

        log = logging.getLogger(__name__)
        try:
            log.debug("location_data: %s", location_data)

            geom = shape(location_data['features'][0]['geometry'])
            log.debug("WKT for spatial field: %s", geom.wkt)

            geojson_geom = geojson.dumps(mapping(geom))
            log.debug("GeoJSON for spatial field: %s", geojson_geom)

            data['spatial',] = geojson_geom


            log.debug("Data after setting spatial: %s", pformat(data))

        except Exception as e:
            log.error("Error processing GeoJSON: %s", e)
            add_error(errors, location_data_key, f"Error processing GeoJSON: {e}")

    return validator

def is_valid_latitude(lat):
    try:
        lat = float(lat)
        return -90 <= lat <= 90
    except (ValueError, TypeError):
        return False

def is_valid_longitude(lng):
    try:
        lng = float(lng)
        return -180 <= lng <= 180
    except (ValueError, TypeError):
        return False

def is_valid_bounding_box(bbox):
    try:
        # If bbox is a list with one element, extract the string
        if isinstance(bbox, list) and len(bbox) == 1:
            bbox = bbox[0]

        # Check if bbox is a string in the correct format
        if not isinstance(bbox, str) or len(bbox.split(',')) != 4:
            return False

        # Split the string and convert each part to float
        min_lng , min_lat, max_lng , max_lat = map(float, bbox.split(','))

        return all(-90 <= lat <= 90 for lat in [min_lat, max_lat]) and \
               all(-180 <= lng <= 180 for lng in [min_lng, max_lng]) and \
               min_lat < max_lat and min_lng < max_lng
    except (ValueError, TypeError):
        return False

def composite_all_empty(field, item):
    for schema_subfield in field.get("subfields", []):
        name = schema_subfield.get("field_name", "")
        v = item.get(name, "")
        if v is not None and v is not missing and str(v).strip() != "":
            return False
    return True


def _subfield_label(field, subfield_name, index):
    # Find label from schema, fall back to field_name
    for sf in field.get("subfields", []):
        if sf.get("field_name") == subfield_name:
            label = sf.get("label") or subfield_name
            # label can be i18n dict sometimes
            if isinstance(label, dict):
                label = subfield_name
            return f"{label} {index}"
    return f"{subfield_name} {index}"


def composite_not_empty_subfield(main_key, subfield_label, value, errors):
    if value is missing or value is None or str(value).strip() == "":
        # Keep a single aggregated message (your existing UX)
        errors[main_key] = errors.get(main_key, [])
        if errors[main_key] and "Missing value at required subfields:" in errors[main_key][-1]:
            errors[main_key][-1] += f", {subfield_label}"
        else:
            errors[main_key].append(f"Missing value at required subfields: {subfield_label}")


def _apply_navl_validators_to_value(validators_str, value, context):
    """
    Apply CKAN NAVL validators (space-separated) to a single value.
    Returns (new_value, error_messages[])
    """
    if not validators_str:
        return value, []

    tmp_key = ("__tmp__",)
    tmp_data = {tmp_key: value}
    tmp_errors = {}

    for vname in validators_str.split():
        v = get_validator(vname)

        # Prefer NAVL invocation; fallback to value-style if signature mismatch
        try:
            v(tmp_key, tmp_data, tmp_errors, context)
        except TypeError:
            try:
                # Some validators accept (value, context)
                tmp_data[tmp_key] = v(tmp_data[tmp_key], context)
            except TypeError:
                # Simple value transformer: (value)
                tmp_data[tmp_key] = v(tmp_data[tmp_key])
            except tk.Invalid as e:
                tmp_errors.setdefault(tmp_key, []).append(str(e))
        except tk.Invalid as e:
            tmp_errors.setdefault(tmp_key, []).append(str(e))
        except StopOnError:
            tmp_errors.setdefault(tmp_key, []).append(str(invalid_error))

    return tmp_data.get(tmp_key), tmp_errors.get(tmp_key, [])


def _parse_composite_from_extras(key, data):
    """
    Extract composite repeating rows from __extras (scheming composite pattern).
    Returns (found_list, extras_to_delete, extras_dict)
    """
    found = {}
    prefix = key[-1] + "-"
    extras_key = key[:-1] + ("__extras",)
    extras = data.get(extras_key, {})

    extras_to_delete = []
    for name, text in list(extras.items()):
        if not name.startswith(prefix):
            continue

        # name format: "{field}-{index}-{subfield}"
        # eg: "owner-1-owner_name"
        parts = name.split("-", 2)
        if len(parts) != 3:
            continue

        index = int(parts[1])
        subfield = parts[2]
        extras_to_delete.append(name)

        found.setdefault(index, {})
        found[index][subfield] = text

    found_list = [row for _, row in sorted(found.items(), key=lambda kv: kv[0])]
    return found, found_list, extras_to_delete, extras


def _apply_required_subfields(field, key, item, index, errors):
    item_is_empty_and_optional = composite_all_empty(field, item) and not sh.scheming_field_required(field)
    if item_is_empty_and_optional:
        return

    for sf in field.get("subfields", []):
        if sf.get("required", False):
            name = sf.get("field_name")
            label = _subfield_label(field, name, index)
            composite_not_empty_subfield(key, label, item.get(name, ""), errors)


def _apply_subfield_validators(field, key, item, index, errors, context):
    """
    Runs each subfield's validators string (if present) against the item's value.
    Stores transformed values back into item (eg strip_value).
    """
    for sf in field.get("subfields", []):
        name = sf.get("field_name")
        validators_str = sf.get("validators")
        if not validators_str:
            continue

        raw = item.get(name, "")
        new_value, msgs = _apply_navl_validators_to_value(validators_str, raw, context)
        item[name] = new_value

        if msgs:
            label = _subfield_label(field, name, index)
            for m in msgs:
                add_error(errors, key, f"{label}: {m}")


def _apply_composite_rules(field, key, item, index, errors):
    """
    Generic conditional requirements based on field['composite_rules'].
    Supports:
      - when_present: <field>
      - when_equals: {field: <field>, value: <value>}
      - require: [<field>, ...]
    """
    rules = field.get("composite_rules") or []
    if not rules:
        return

    def is_present(v):
        return v is not missing and v is not None and str(v).strip() != ""

    for rule in rules:
        required_fields = rule.get("require") or []

        should_apply = False

        if "when_present" in rule:
            trigger = rule["when_present"]
            should_apply = is_present(item.get(trigger, ""))

        elif "when_equals" in rule:
            we = rule["when_equals"] or {}
            f = we.get("field")
            expected = we.get("value")
            actual = item.get(f, "")
            should_apply = is_present(actual) and str(actual) == str(expected)

        if not should_apply:
            continue

        for req_name in required_fields:
            label = _subfield_label(field, req_name, index)
            composite_not_empty_subfield(key, label, item.get(req_name, ""), errors)


@scheming_validator
@register_validator
def composite_repeating_validator(field, schema):
    def validator(key, data, errors, context):
        # If field already posted as JSON (API clients), validate that too.
        raw_value = data.get(key, "")
        items = None

        if raw_value and raw_value is not missing:
            if isinstance(raw_value, str):
                try:
                    items = json.loads(raw_value)
                    if not isinstance(items, list):
                        add_error(errors, key, invalid_error)
                        items = None
                except Exception:
                    add_error(errors, key, invalid_error)
                    items = None

        found = {}
        extras_to_delete = []
        extras = None

        # Typical form submission path (composite extras)
        if items is None:
            found, found_list, extras_to_delete, extras = _parse_composite_from_extras(key, data)
            items = found_list

        # If empty
        if not items:
            data[key] = ""
            if sh.scheming_field_required(field):
                not_empty(key, data, errors, context)
            return

        clean_list = []
        # Indices are 1-based in your UI messages; match your old behaviour
        # If we parsed from extras, we have original indices; otherwise enumerate.
        if found:
            iterable = [(idx, found[idx]) for idx in sorted(found.keys())]
        else:
            iterable = [(i + 1, it) for i, it in enumerate(items)]

        for index, item in iterable:
            if not isinstance(item, dict):
                add_error(errors, key, invalid_error)
                continue

            if composite_all_empty(field, item):
                continue

            _apply_required_subfields(field, key, item, index, errors)
            _apply_subfield_validators(field, key, item, index, errors, context)
            _apply_composite_rules(field, key, item, index, errors)

            clean_list.append(item)

        data[key] = json.dumps(clean_list, ensure_ascii=False) if clean_list else ""

        # delete extras to avoid duplicates in package_dict
        if extras is not None and extras_to_delete:
            for extra_name in extras_to_delete:
                extras.pop(extra_name, None)

        if sh.scheming_field_required(field):
            not_empty(key, data, errors, context)

    return validator

def pidinst_theme_required(value):
    if not value or value is tk.missing:
        raise tk.Invalid(tk._("Required"))
    return value

def owner_org_validator(key, data, errors, context):
    owner_org = data.get(key)

    if owner_org is not tk.missing and owner_org is not None and owner_org != '':
        if context.get('auth_user_obj', None) is not None:
            username = context['auth_user_obj'].name
        else:
            username = context['user']
        role = users_role_for_group_or_org(owner_org, username)
        if role == 'member':
            return
    ckan_owner_org_validator(key, data, errors, context)


@scheming_validator
@register_validator
def parent_validator(field, schema):
    """
    A validator to ensure that if the parent instrument is specified,
    then the acquisition start date of the instrument must be either the same as or later than the acquisition start date of its parent instrument.
    Additionally, the instrument and its parent must belong to the same organization and cannot be the same.
    """
    def validator(key, data, errors, context):

        parent_instrument_id_key = ('parent',)
        parent_instrument_id = data.get(parent_instrument_id_key, missing)
        start_date_key = ('acquisition_start_date',)
        start_date = data.get(start_date_key, missing)
        owner_org_key = ('owner_org',)
        owner_org = data.get(owner_org_key, missing)
        instrument_id_key = ('id',)
        instrument_id = data.get(instrument_id_key, missing)

        if parent_instrument_id is missing or parent_instrument_id is None or not str(parent_instrument_id).strip():
            return

        if instrument_id == parent_instrument_id:
            add_error(errors, parent_instrument_id_key, _('A instrument cannot be its own parent.'))
            return

        try:
            parent_instrument = tk.get_action('package_show')(context, {'id': parent_instrument_id})
        except tk.ObjectNotFound:
            add_error(errors, parent_instrument_id_key, _('Parent instrument not found.'))
            return
        except tk.NotAuthorized:
            add_error(errors, parent_instrument_id_key, _('You are not authorized to view the parent instrument.'))
            return

        parent_owner_org = parent_instrument.get('owner_org', missing)
        if owner_org is missing or parent_owner_org is missing or owner_org != parent_owner_org:
            add_error(errors, parent_instrument_id_key, _('The instrument and its parent must belong to the same organization.'))
            return

        parent_start_date = parent_instrument.get('acquisition_start_date', missing)

        if start_date and parent_start_date and str(start_date).strip() and str(parent_start_date).strip():
            try:
                start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
                parent_start_date_dt = datetime.strptime(parent_start_date, "%Y-%m-%d")
            except ValueError:
                add_error(errors, parent_instrument_id_key, _('Invalid date format. Use YYYY-MM-DD.'))
                return

            if start_date_dt < parent_start_date_dt:
                add_error(errors, parent_instrument_id_key, _('The Acquisition Start Date of the instrument must be the same as or later than the acquisition start date of its parent instrument.'))

    return validator


@scheming_validator
@register_validator
def group_name_validator(field, schema):

    def validator(key, data,errors, context):
        """Ensures that value can be used as a group's name
        """

        model = context['model']
        session = context['session']
        group = context.get('group')

        query = session.query(model.Group.name).filter(
            model.Group.name == data[key],
            model.Group.state != model.State.DELETED
        )

        if group:
            group_id: Union[Optional[str], df.Missing] = group.id
        else:
            group_id = data.get(key[:-1] + ('id',))

        if group_id and group_id is not missing:
            query = query.filter(model.Group.id != group_id)

        result = query.first()
        if result:
            add_error(errors, key, _('Organisation name already exists in database.'))

    return validator


def get_validators():
    return {
        "pidinst_theme_required": pidinst_theme_required,
        "location_validator": location_validator,
        "composite_repeating_validator": composite_repeating_validator,
        "owner_org_validator": owner_org_validator,
        "parent_validator" : parent_validator,
        "group_name_validator" : group_name_validator
    }
