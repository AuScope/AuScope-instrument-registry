from flask import session
import requests
from ckan.plugins.toolkit import get_action
import ckan.plugins.toolkit as toolkit
from datetime import date
import pandas as pd
import logging
import json
import re
from ckanext.pidinst_theme.logic.batch_validation import validate_parent_instruments, is_numeric, is_cell_empty, is_url, validate_related_resources, validate_user_keywords, validate_authors, validate_samples, generate_sample_name, generate_sample_title
log = logging.getLogger(__name__)


def generate_location_geojson(coordinates_list):
        features = []
        for lat, lng in coordinates_list:
            point_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lng, lat]
                },
                "properties": {}
            }
            features.append(point_feature)

        feature_collection = {
            "type": "FeatureCollection",
            "features": features
        }
        return feature_collection

def process_author_emails(sample, authors_df):
        author_emails = [email.strip() for email in sample.get("author_emails", "").split(";")]
        matched_authors = authors_df[authors_df["author_email"].isin(author_emails)]
        return json.dumps(matched_authors.to_dict("records"))

def prepare_samples_data(samples_df, authors_df, related_resources_df, funding_df, org_id):
        samples_data = []
        for _, row in samples_df.iterrows():
            sample = row.to_dict()
            sample["author"] = process_author_emails(sample, authors_df)
            sample["related_resource"] = process_related_resources(sample, related_resources_df)
            sample["funder"] = process_funding_info(sample, funding_df)
            sample['user_keywords'] = validate_user_keywords(sample['user_keywords'])
            sample['publication_date'] = date.today().isoformat()
            sample['private']=False
            sample['notes'] = sample['description']
            sample['location_choice'] = 'noLocation'
            sample['parent_instrument'] = sample['parent_instrument']
            sample['parent'] = ''

            sample['acquisition_start_date'] = row['acquisition_start_date'].strftime('%Y-%m-%d') if pd.notnull(row['acquisition_start_date']) else None
            sample['acquisition_end_date'] = row['acquisition_end_date'].strftime('%Y-%m-%d') if pd.notnull(row['acquisition_end_date']) else None

            org = toolkit.get_action('organization_show')({}, {'id': org_id})
            sample['owner_org'] = org_id
            sample['sample_repository_contact_name'] = org.get('contact_name', 'test')
            sample['sample_repository_contact_email'] = org.get('contact_email', '')
            
            if 'point_latitude' in sample and sample['point_latitude'] != '' and 'point_longitude' in sample and sample['point_longitude'] != '':
                if not is_numeric(sample['point_latitude']) or not is_numeric(sample['point_longitude']):
                    raise ValueError("Latitude and Longitude must be numeric.")
                sample['location_choice'] = 'point'
                coordinates = [(sample['point_latitude'], sample['point_longitude'])]
                sample['location_data'] = generate_location_geojson(coordinates)
            sample['epsg'] = get_epsg_name(sample['epsg_code'])
            defaults = {
                "publisher_identifier_type": "ROR",
                "publisher_identifier": "https://ror.org/04s1m4564",
                "publisher": "AuScope",
                "resource_type": "PhysicalObject",
            }
            sample.update(defaults)
            
            sample["name"] = generate_sample_name(org_id, sample['sample_type'], sample['sample_number'])
            sample["title"] = generate_sample_title(org_id, sample['sample_type'], sample['sample_number'])
            samples_data.append(sample)
        return samples_data
    
def process_related_resources(sample, related_resources_df):
    related_resources_urls = sample.get("related_resources_urls")
    if is_cell_empty(related_resources_urls):
        return "[]"
    
    related_resource_urls = [url.strip() for url in related_resources_urls.split(";")]
    for url in related_resource_urls:
        is_url(url)  # Check if the URL is valid
        related_resources = related_resources_df[related_resources_df['related_resource_url'] == url]
        required_fields = ['related_resource_type', 'related_resource_url', 'related_resource_title', 'relation_type']
        if related_resources[required_fields].map(is_cell_empty).any().any():
            raise ValueError(f"Missing required fields for related resource URL: {url}")

    matched_resources = related_resources_df[related_resources_df["related_resource_url"].isin(related_resource_urls)]
    return json.dumps(matched_resources.to_dict("records"))

def process_funding_info(sample, funding_df):
    if not is_cell_empty(sample.get("project_ids")):
        project_ids = [project_id.strip() for project_id in sample.get("project_ids").split(";")]
        for project_id in project_ids:
            funding_info = funding_df[funding_df['project_identifier'] == project_id]
            if funding_info.empty:
                raise ValueError(f"Missing funding information for project ID: {project_id}")
            for _, row in funding_info.iterrows():
                if is_cell_empty(row["funder_name"]):
                    raise ValueError(f"Row for project ID {project_id} must include a funder_name")
                if not is_cell_empty(row["funder_identifier"]) and is_cell_empty(row["funder_identifier_type"]):
                    raise ValueError(f"Row for project ID {project_id} with funder_identifier must include funder_identifier_type")
                if not is_cell_empty(row["funder_name"]):
                    if is_cell_empty(row["project_name"]) or is_cell_empty(row["project_identifier"]) or is_cell_empty(row["project_identifier_type"]):
                        raise ValueError(f"Row for funder_name {row['funder_name']} must include project_name, project_identifier, and project_identifier_type")

        matched_funder = funding_df[funding_df["project_identifier"].isin(project_ids)]
        return json.dumps(matched_funder.to_dict("records"))

        # matched_funder_name = funding_df.loc[funding_df["project_identifier"].isin(project_ids), "funder_name"]
        # return matched_funder_name.tolist()
    return "[]"
def get_epsg_name(epsg_code):
        external_url = f'https://apps.epsg.org/api/v1/CoordRefSystem/?includeDeprecated=false&pageSize=50&page={0}&keywords={epsg_code}'
        response = requests.get(external_url)
        if response.ok:
            espg_data = json.loads(response.content.decode('utf-8'))
            return espg_data['Results'][0]['Name']
        else:
            return None
        
def set_parent_instrument(context):
        """
        Sets the parent sample for each created sample.
        The 'parent_instrument' field can be a DOI or a sample number.
        """
        preview_data = session.get('preview_data', {})
        samples = preview_data.get('samples', [])

        created_samples = session.get('created_samples', [])
        log = logging.getLogger(__name__)
        for sample in samples:
            # log.info(f"set_parent_instrument sample : {sample}")

            parent_instrument = sample.get('parent_instrument')
            if not parent_instrument:
                continue

            # log.info(f"set_parent_instrument parent_instrument : {parent_instrument}")

            # Attempt to find the parent sample by DOI or sample number
            parent_package = find_parent_package(parent_instrument, context, samples, created_samples)
            if not parent_package:
                continue

            # log.info(f"parent_package : {parent_package}")

            # Update the sample with the parent sample ID
            sample_id = get_created_sample_id(sample)
            # log.info(f"sample_id : {sample_id}")

            if 'id' not in parent_package:
                parent_package['id'] = get_created_sample_id(parent_package)

            # log.info(f"parent_package['id'] : {parent_package['id']}")

            if sample_id and 'id' in parent_package:
                try:
                    existing_sample = toolkit.get_action('package_show')(context, {'id': sample_id})
                    existing_sample['parent'] = parent_package['id']
                    toolkit.get_action('package_update')(context, existing_sample)
                except Exception as e:
                    log.error(f"Failed to update sample {sample_id} with parent sample {parent_package['id']}: {e}")
                    
def find_parent_package(parent_instrument, context, preview_samples, created_samples):
        """
        Finds the parent package based on DOI or sample number.
        """
        # Attempt to find by DOI
        try:
            package = toolkit.get_action('package_search')(context, {'q': f'doi:{parent_instrument}'})
            if package['results']:
                return package['results'][0]
        except Exception as e:
            log.warning(f"Failed to find parent package by DOI {parent_instrument}: {e}")

        # Attempt to find by sample number within preview_data
        for sample in preview_samples:
            if sample.get('sample_number') == parent_instrument:
                # Check if the sample has been created and has an ID
                for created_sample in created_samples:
                    if created_sample['sample_number'] == sample.get('sample_number'):
                        return created_sample

        log.warning(f"Parent sample {parent_instrument} not found by DOI or sample number.")
        return None

def get_created_sample_id(preview_sample):
    """
    Finds the created sample ID corresponding to the preview sample.
    """
    created_samples = session.get('created_samples', [])
    for created_sample in created_samples:
        if created_sample['sample_number'] == preview_sample.get('sample_number'):
            return created_sample['id']
    return None

def read_excel_sheets(excel_data, sheets):
    dfs = {}
    for sheet in sheets:
        excel_data.seek(0)
        try:
            df = pd.read_excel(excel_data, sheet_name=sheet, na_filter=False, engine="openpyxl")
            dfs[sheet] = df if not df.empty else pd.DataFrame()
        except Exception as e:
            dfs[sheet] = pd.DataFrame()
            print(f"Error processing sheet {sheet}: {str(e)}")
    return dfs