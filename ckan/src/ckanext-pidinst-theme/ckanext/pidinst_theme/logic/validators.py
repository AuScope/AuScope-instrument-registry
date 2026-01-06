import ckan.plugins.toolkit as tk
from ckantoolkit import ( _, missing , get_validator )
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
        elevation_key = ('elevation',)

        location_choice = data.get(location_choice_key, missing)
        location_data = data.get(location_data_key, missing)
        epsg_code = data.get(epsg_code_key, missing)
        elevation = data.get(elevation_key, missing)

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

        if elevation is not missing and elevation is not None and str(elevation).strip():
            try:
                elevation = float(elevation)
            except (ValueError, TypeError):
                add_error(errors, elevation_key, invalid_error)
   
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

def composite_not_empty_subfield(key, subfield_label, value, errors):
    '''
    Validates that a specified subfield is not empty. If the subfield is empty,
    appends a custom error message that includes the subfield label.
    
    Parameters:
        key (tuple): The key in the data dictionary that corresponds to the main field.
        subfield_label (str): The label of the subfield to be included in the error message.
        value (str): The value of the subfield to validate.
        errors (dict): A dictionary where validation errors are collected.
    '''
    if not value or value is missing:
        if key not in errors:
            errors[key] = []
        
        if errors[key] and "Missing value at required subfields:" in errors[key][-1]:
            errors[key][-1] += f", {subfield_label}"
        else:
            errors[key].append(f"Missing value at required subfields: {subfield_label}")

def composite_all_empty(field, item):
    all_empty = True
    for schema_subfield in field['subfields']:
        subfield_value = item.get(schema_subfield.get('field_name', ''), "")
        if subfield_value and subfield_value is not missing:
            all_empty = False
    return all_empty

def author_validator(key, item, index, field, errors):
    author_identifier_key = 'author_identifier'
    author_identifier_type_key = 'author_identifier_type'
    author_email_key = 'author_email'
    author_affiliation_identifier_key = 'author_affiliation_identifier'

    author_identifier = item.get(author_identifier_key, "")
    author_identifier_type = item.get(author_identifier_type_key, "")
    author_email = item.get(author_email_key, "")
    author_affiliation_identifier = item.get(author_affiliation_identifier_key, "")

    if author_identifier:
        tk.get_validator('url_validator')(key, {key: author_identifier}, errors, {})
        
        for subfield in field['subfields']:
            if subfield.get('field_name') == 'author_identifier_type':
                author_identifier_type_label = subfield.get('label', 'Default Label') + " " + str(index)
                break
        composite_not_empty_subfield(key, author_identifier_type_label, author_identifier_type, errors)

    if author_email:
        try:
            tk.get_validator('email_validator')(author_email, {})
        except tk.ValidationError:
            errors[author_email_key] = errors.get(author_email_key, [])
            errors[author_email_key].append(f"Author Email {index} must be a valid email address.")

    if author_affiliation_identifier:
        tk.get_validator('url_validator')(key, {key: author_affiliation_identifier}, errors, {})
         

def funder_validator(key, item, index, field, errors):
    funder_identifier_key = f'funder_identifier'
    funder_identifier_type_key = f'funder_identifier_type'

    funder_identifier = item.get(funder_identifier_key, "")
    funder_identifier_type = item.get(funder_identifier_type_key, "")

    if funder_identifier and funder_identifier is not missing:
        tk.get_validator('url_validator')(key, {key: funder_identifier}, errors, {})
        for subfield in field['subfields']:
            if subfield.get('field_name') == 'funder_identifier_type':
                funder_identifier_type_label = subfield.get('label', 'Default Label') + " " + str(index)
                break
        composite_not_empty_subfield(key,  funder_identifier_type_label , funder_identifier_type, errors)

def project_validator(key, item, index, field, errors):
    project_name_key = f'project_name'
    project_identifier_key = f'project_identifier'
    project_identifier_type_key = f'project_identifier_type'

    project_name = item.get(project_name_key, "")
    project_identifier = item.get(project_identifier_key, "")
    project_identifier_type = item.get(project_identifier_type_key, "")
    
    if project_identifier and project_identifier is not missing:
        tk.get_validator('url_validator')(key, {key: project_identifier}, errors, {})

    if project_name and project_name is not missing:
        for subfield in field['subfields']:
            if subfield.get('field_name') == 'project_identifier':
                project_identifier_label = subfield.get('label', 'Default Label') + " " + str(index)
            if subfield.get('field_name') == 'project_identifier_type':
                project_identifier_type_label = subfield.get('label', 'Default Label') + " " + str(index)                

        composite_not_empty_subfield(key,  project_identifier_label , project_identifier, errors)           
        composite_not_empty_subfield(key,  project_identifier_type_label , project_identifier_type, errors)

def related_resource_validator(key, item, index, field, errors):
    related_resource_url_key = f'related_resource_url'
    related_resource_url = item.get(related_resource_url_key, "")

    if related_resource_url and related_resource_url is not missing:
        tk.get_validator('url_validator')(key, {key: related_resource_url}, errors, {})

@scheming_validator
@register_validator
def composite_repeating_validator(field, schema):
    def validator(key, data, errors, context):
        value = ""

        for name, text in data.items():
            if name == key:
                if text:
                    value = text

        # parse from extra into a list of dictionaries and save it as a json dump
        if not value:
            found = {}
            prefix = key[-1] + '-'
            extras = data.get(key[:-1] + ('__extras',), {})

            extras_to_delete = []
            for name, text in extras.items():
                if not name.startswith(prefix):
                    continue

                # if not text:
                #    continue

                index = int(name.split('-', 2)[1])
                subfield = name.split('-', 2)[2]
                extras_to_delete += [name]

                if index not in found.keys():
                    found[index] = {}
                found[index][subfield] = text
            found_list = [element[1] for element in sorted(found.items())]

            if not found_list:
                data[key] = ""
            else:

                # check if there are required subfields missing for every item
                for index in found:
                    item = found[index]

                    item_is_empty_and_optional = composite_all_empty(field, item) and not sh.scheming_field_required(field)
                    for schema_subfield in field['subfields']:
                        if schema_subfield.get('required', False) and not item_is_empty_and_optional:
                            if type(schema_subfield.get('label', '')) is dict:
                                subfield_label = schema_subfield.get('field_name', '') + " " + str(index)
                            else:
                                subfield_label = schema_subfield.get('label', schema_subfield.get('field_name', '')) + " " + str(index)

                            subfield_value = item.get(schema_subfield.get('field_name', ''), "")
                            composite_not_empty_subfield(key, subfield_label , subfield_value, errors)

                    # Call custom author and funder validation for each item
                    author_validator(key , item, index, field, errors)        
                    funder_validator(key , item, index, field, errors)        
                    project_validator(key , item, index, field, errors)        
                    related_resource_validator(key , item, index, field, errors)        

                # remove empty elements from list
                clean_list = []
                for element in found_list:
                    if not composite_all_empty(field, element):
                        clean_list += [element]
                # dump the list to a string
                data[key] = json.dumps(clean_list, ensure_ascii=False)

                # delete the extras to avoid duplicate fields
                for extra in extras_to_delete:
                    del extras[extra]

        # check if the field is required
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
def sample_number_validator(field, schema):
    def validator(key, data, errors, context):

        sample_number = data.get(key)
        owner_org_key = ('owner_org',)
        owner_org = data.get(owner_org_key, missing)
        current_sample_id = data.get(('id',), None) 

        if owner_org is missing:
            add_error(errors, owner_org_key, missing_error)
            return

        if sample_number is missing or sample_number == '':
            add_error(errors, key, missing_error)
            return

        try:
            package_search = tk.get_action('package_search')
            search_result = package_search(context, {
                'q': f'owner_org:{owner_org} AND sample_number:{sample_number}',
                'rows': 1000  # Retrieve all potential results
            })
            
            if search_result['count'] > 0:
                for result in search_result['results']:
                    if result['id'] != current_sample_id:
                        org_name = tk.get_action('organization_show')({}, {'id': owner_org})['name']
                        add_error(errors, key, f'sample_number "{sample_number}" already exists in collection "{org_name}"')
                        break  # Stop checking after the first duplicate is found
        except NotFound:
            add_error(errors, key, 'Error checking uniqueness of sample_number')
        except Exception as e:
            add_error(errors, key, f'Error querying Solr: {str(e)}')

        return

    return validator

from datetime import datetime

@scheming_validator
@register_validator
def acquisition_date_validator(field, schema):
    """
    A validator to ensure the acquisition_start_date is today or before,
    and that the acquisition_end_date is later than the start date.
    """
    def validator(key, data, errors, context):

        acquisition_start_date_key = ('acquisition_start_date',)
        acquisition_end_date_key = ('acquisition_end_date',)

        acquisition_start_date_str = data.get(acquisition_start_date_key, missing)
        acquisition_end_date_str = data.get(acquisition_end_date_key, missing)

        if ((acquisition_start_date_str is missing and acquisition_end_date_str is missing) or
                (acquisition_start_date_str is None and acquisition_end_date_str is None) or
                (not acquisition_start_date_str.strip() and not acquisition_end_date_str.strip())):
            return

        try:
            acquisition_start_date = datetime.strptime(acquisition_start_date_str, "%Y-%m-%d").date()
        except ValueError:
            add_error(errors, acquisition_start_date_key, 'Invalid date format. Please use YYYY-MM-DD.')
            return

        try:
            acquisition_end_date = datetime.strptime(acquisition_end_date_str, "%Y-%m-%d").date()
        except ValueError:
            add_error(errors, acquisition_end_date_key, 'Invalid date format. Please use YYYY-MM-DD.')
            return

        if acquisition_start_date > datetime.now().date():
            add_error(errors, acquisition_start_date_key, 'Acquisition start date must be today or before.')
            return

        if acquisition_start_date > acquisition_end_date:
            add_error(errors, acquisition_end_date_key, 'Acquisition end date must be later than the start date.')
            return

    return validator

@scheming_validator
@register_validator
def depth_validator(field, schema):
    """
    A validator to ensure the depth_from is less than depth_to
    """
    def validator(key, data, errors, context):

        depth_from_key = ('depth_from',)
        depth_to_key = ('depth_to',)

        depth_from_str = data.get(depth_from_key, missing)
        depth_to_str = data.get(depth_to_key, missing)

        if all(val is missing or val is None or not str(val).strip() for val in [depth_from_str, depth_to_str]):
            return

        try:
            depth_from = float(depth_from_str)
        except (ValueError, TypeError):
            add_error(errors, depth_from_key, invalid_error)
            return

        try:
            depth_to = float(depth_to_str)
        except (ValueError, TypeError):
            add_error(errors, depth_to_key, invalid_error)
            return

        if depth_from >= depth_to:
            add_error(errors, depth_to_key, _("Depth to must be greater than the depth from."))

    return validator

@scheming_validator
@register_validator
def parent_validator(field, schema):
    """
    A validator to ensure that if the parent sample is specified, 
    then the acquisition start date of the sample must be either the same as or later than the acquisition start date of its parent sample.
    Additionally, the sample and its parent must belong to the same organization and cannot be the same.
    """
    def validator(key, data, errors, context):
          
        parent_instrument_id_key = ('parent',)
        parent_instrument_id = data.get(parent_instrument_id_key, missing)
        start_date_key = ('acquisition_start_date',)
        start_date = data.get(start_date_key, missing)
        owner_org_key = ('owner_org',)
        owner_org = data.get(owner_org_key, missing)
        sample_id_key = ('id',)
        sample_id = data.get(sample_id_key, missing)

        if parent_instrument_id is missing or parent_instrument_id is None or not str(parent_instrument_id).strip():
            return
        
        if sample_id == parent_instrument_id:
            add_error(errors, parent_instrument_id_key, _('A sample cannot be its own parent.'))
            return
                    
        try:
            parent_instrument = tk.get_action('package_show')(context, {'id': parent_instrument_id})
        except tk.ObjectNotFound:
            add_error(errors, parent_instrument_id_key, _('Parent sample not found.'))
            return
        except tk.NotAuthorized:
            add_error(errors, parent_instrument_id_key, _('You are not authorized to view the parent sample.'))           
            return
        
        parent_owner_org = parent_instrument.get('owner_org', missing)
        if owner_org is missing or parent_owner_org is missing or owner_org != parent_owner_org:
            add_error(errors, parent_instrument_id_key, _('The sample and its parent must belong to the same organization.'))                      
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
                add_error(errors, parent_instrument_id_key, _('The Acquisition Start Date of the sample must be the same as or later than the acquisition start date of its parent sample.'))           

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
            add_error(errors, key, _('Collection name already exists in database.'))           

    return validator


def get_validators():
    return {
        "pidinst_theme_required": pidinst_theme_required,
        "location_validator": location_validator,
        "composite_repeating_validator": composite_repeating_validator,
        "owner_org_validator": owner_org_validator,
        "sample_number_validator" : sample_number_validator,
        "acquisition_date_validator" : acquisition_date_validator,
        "depth_validator" : depth_validator,
        "parent_validator" : parent_validator,
        "group_name_validator" : group_name_validator
    }
