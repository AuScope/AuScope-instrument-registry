import ckan.plugins.toolkit as toolkit
from ckan.plugins.toolkit import get_action
import re
import pandas as pd

def validate_sample_depth(sample_df):
    errors = []

    filtered_df = sample_df.dropna(subset=["depth_from", "depth_to"])
    # Check if depth_from and depth_to are valid numbers
    for column in ["depth_from", "depth_to"]:
        non_empty = sample_df[column].notna() & (sample_df[column].astype(str).str.strip() != '')
        non_numeric = sample_df[non_empty & pd.to_numeric(sample_df[column].astype(str).str.strip(), errors='coerce').isna()]
        for index, value in non_numeric[column].items():
            errors.append(f"Row {index}: '{column}' value '{value.strip()}' is not a valid number")
            
    # Convert 'depth_from' and 'depth_to' to numeric, treating them as strings initially
    filtered_df["depth_from"] = pd.to_numeric(filtered_df["depth_from"].astype(str).str.strip(), errors="coerce")
    filtered_df["depth_to"] = pd.to_numeric(filtered_df["depth_to"].astype(str).str.strip(), errors="coerce")

    # Remove rows where conversion to numeric failed
    filtered_df = filtered_df.dropna(subset=["depth_from", "depth_to"])

    # Compare depth_from and depth_to
    valid_mask = filtered_df["depth_from"] < filtered_df["depth_to"]
    invalid_df = filtered_df[~valid_mask]

    for index, row in invalid_df.iterrows():
        errors.append(f"Row {index}: Depth from {row['depth_from']} to {row['depth_to']} is invalid")
    return errors

def validate_elevation(sample_df):
    errors = []
    # Filter out empty cells
    non_empty_elevations = sample_df["elevation"].dropna().replace('', pd.NA).dropna()

    # Attempt to convert non-empty values to numeric
    numeric_result = pd.to_numeric(non_empty_elevations.astype(str).str.strip(), errors='coerce')
    # Identify rows where conversion failed (resulting in NaN)
    invalid_rows = numeric_result[numeric_result.isna()]

    for index, value in invalid_rows.items():
        original_value = sample_df.loc[index, "elevation"].strip()
        errors.append(f"Row {index}: Elevation '{original_value}' is not a valid number")
    return errors
    

def validate_match_related_resource_url(sample_df, resource_df):
    errors = []
    
    # Extract unique URLs from sample_df
    sample_urls = set()
    for cell in sample_df['related_resources_urls']:
        urls = set(url.strip() for url in cell.split(';') if url.strip())
        sample_urls.update(urls)
    
    # Extract unique URLs from resource_df
    resource_urls = set(url.strip() for url in resource_df['related_resource_url'] if url.strip())
    
    # Check if the URL sets in both dataframes match exactly
    if sample_urls != resource_urls:
        missing_in_sample = resource_urls - sample_urls
        missing_in_resource = sample_urls - resource_urls
        
        if missing_in_sample:
            errors.append("The following related resource URLs are not in the sample sheet:\n" + ', '.join(missing_in_sample))
        
        if missing_in_resource:
            errors.append("The following sample URLs are not in the related resource sheet:\n" + ', '.join(missing_in_resource))
    
    return errors
    
def validate_match_user_email(sample_df, author_df):
    errors = []
    sample_emails = set()
    for cell in sample_df['author_emails']:
        if isinstance(cell, str):
            emails = set(email.strip().lower() for email in cell.split(';') if email.strip())
            sample_emails.update(emails)
        
    # Extract unique emails from author_df
    author_emails = set()
    for email in author_df['author_email']:
        if isinstance(email, str):
            stripped_email = email.strip().lower()
            if stripped_email:
                author_emails.add(stripped_email)
    
    # Check if the email sets in both dataframes match exactly
    if sample_emails != author_emails:
        missing_in_sample = author_emails - sample_emails
        missing_in_author = sample_emails - author_emails
        
        if missing_in_sample:
            errors.append("The following author emails are not in the sample sheet:\n" + ', '.join(missing_in_sample))
        
        if missing_in_author:
            errors.append("The following sample emails are not in the author sheet:\n" + ', '.join(missing_in_author))
    
    return errors

def validate_match_project_identifier(sample_df, project_df):
    errors = []
    
    # Extract unique project IDs from sample_df
    sample_project_ids = set()
    for cell in sample_df['project_ids']:
        if pd.notna(cell) and cell.strip() != '':
            ids = set(id.strip() for id in cell.split(';') if id.strip())
            sample_project_ids.update(ids)
    
    # Extract unique project identifiers from project_df
    project_identifiers = set(id.strip() for id in project_df['project_identifier'] if pd.notna(id) and id.strip())
    
    # Check if the project ID/identifier sets in both dataframes match exactly
    if sample_project_ids != project_identifiers:
        missing_in_sample = project_identifiers - sample_project_ids
        missing_in_project = sample_project_ids - project_identifiers
        
        if missing_in_sample:
            errors.append("The following project identifiers are not in the sample sheet:\n" + ', '.join(missing_in_sample))
        
        if missing_in_project:
            errors.append("The following project IDs from the sample sheet are not in the project sheet:\n" + ', '.join(missing_in_project))
    
    # Optionally, you can add a check to ensure there's at least one project ID/identifier in each dataframe
    if not sample_project_ids:
        errors.append("The sample sheet does not contain any valid project IDs.")
    if not project_identifiers:
        errors.append("The project sheet does not contain any valid project identifiers.")
    
    return errors

def validate_acquisition_date(sample_df):
    errors = []
    
    for column in ['acquisition_start_date', 'acquisition_end_date']:
        # Check for missing dates
        missing_dates = sample_df[column].isna() | (sample_df[column] == '')
        for index in missing_dates[missing_dates].index:
            errors.append(f"Row {index}: '{column}' is missing")
        
        # Check for non-empty cells that are not valid dates
        non_empty = sample_df[column].notna() & (sample_df[column] != '')
        non_date = sample_df[non_empty & pd.to_datetime(sample_df[column], errors='coerce', format='%Y-%m-%d').isna()]
        
        for index, value in non_date[column].items():
            errors.append(f"Row {index}: '{column}' value '{value}' is not a valid date")
    
    # Convert to datetime, coerce errors to NaT, and format as 'YYYY-MM-DD'
    for column in ['acquisition_start_date', 'acquisition_end_date']:
        sample_df[column] = pd.to_datetime(sample_df[column], errors='coerce', format='%Y-%m-%d').dt.strftime('%Y-%m-%d')
    
    # Filter for rows where both dates are not null
    valid_df = sample_df.dropna(subset=['acquisition_start_date', 'acquisition_end_date'])
    
    # Compare dates
    invalid_mask = pd.to_datetime(valid_df["acquisition_start_date"]) >= pd.to_datetime(valid_df["acquisition_end_date"])
    invalid_df = valid_df[invalid_mask]
    
    for index, row in invalid_df.iterrows():
        errors.append(f"Row {index}: acquisition_start_date {row['acquisition_start_date']} is not before acquisition_end_date {row['acquisition_end_date']}")
    
    return errors
    
def validate_parent_instruments(df):
    errors = []
    
    # Convert date columns to datetime
    df['acquisition_start_date'] = pd.to_datetime(df['acquisition_start_date'])
    df['acquisition_end_date'] = pd.to_datetime(df['acquisition_end_date'])
    
    # Create a dictionary of samples in the current DataFrame
    current_samples = dict(zip(df['sample_number'], df['acquisition_start_date']))
    
    # Get list of all packages in CKAN
    try:
        package_list = toolkit.get_action('package_list')({}, {})
        ckan_samples = {}
        collection_sample_numbers = []
        for package in package_list:
            package_data = toolkit.get_action('package_show')({}, {'id': package})
            sample_number = package_data.get('sample_number')
            if sample_number:
                ckan_samples[sample_number] = pd.to_datetime(package_data.get('acquisition_start_date'))
                collection_sample_numbers.append(sample_number)
    except Exception as e:
        errors.append(f"Error fetching CKAN data: {str(e)}")
        raise ValueError("\n".join(errors))

    def validate_sample(row):
        if pd.isnull(row['parent_instrument']) or row['parent_instrument'] == '':
            return True

        if row['parent_instrument'] == row['sample_number']:
            errors.append(f"Sample {row['sample_number']} references itself as parent")
            return False

        parent_start_date = None
        if row['parent_instrument'] in current_samples:
            parent_start_date = current_samples[row['parent_instrument']]
        elif row['parent_instrument'] in ckan_samples:
            parent_start_date = ckan_samples[row['parent_instrument']]
        else:
            errors.append(f"Parent sample {row['parent_instrument']} for sample {row['sample_number']} not found in the sample repository")
            return False

        if pd.isnull(parent_start_date):
            return True

        if row['acquisition_start_date'] < parent_start_date:
            errors.append(f"Sample {row['sample_number']} : {row['acquisition_start_date']} start date is earlier than its parent {row['parent_instrument']} : {parent_start_date}")
            return False

        return True

    df['valid_parent'] = df.apply(validate_sample, axis=1)

    # Additional validation from validate_parent function
    sample_numbers = df["sample_number"].tolist()
    for index, row in df.iterrows():
        parent = row["parent_instrument"]
        if pd.isna(parent) or parent == '':
            continue
        if parent not in sample_numbers and parent not in collection_sample_numbers:
            errors.append(f"Parent sample '{parent}' not found in the uploaded samples or the collection.")

    return errors

def check_required_fields(df, columns_to_check):
    errors = []
    empty_check = df[columns_to_check].isna() | (df[columns_to_check] == '')
    missing_fields = {}

    for col in columns_to_check:
        missing_in_col = empty_check[col]
        if missing_in_col.any():
            missing_fields[col] = df[missing_in_col].index.tolist()

    if missing_fields:
        for col, indexes in missing_fields.items():
            errors.append(f"Missing values in column '{col}': rows {indexes}")
    return errors

def check_unique_sample_number(samples_df):
    errors = []
    duplicates = samples_df[samples_df['sample_number'].duplicated(keep=False)]
    if not duplicates.empty:
        duplicate_values = duplicates['sample_number'].value_counts()
        errors.append(f"Duplicate sample numbers detected: {duplicate_values.index.tolist()}")
    return errors
    
def validate_epsg(samples_df):
    errors = []
    # List of valid EPSG codes
    valid_epsg_codes = [
        4202, 4203, 4283, 4326, 4347, 4348, 4938, 4939, 4979,
        7842, 7843, 7844, 9462, 9463, 9464
    ]
    
    # Identify rows with non-numeric latitude or longitude
    invalid_latitudes = samples_df['point_latitude'].apply(lambda x: not is_cell_empty(x.strip() if isinstance(x, str) else x) and not is_numeric(x.strip() if isinstance(x, str) else x))
    invalid_longitudes = samples_df['point_longitude'].apply(lambda x: not is_cell_empty(x.strip() if isinstance(x, str) else x) and not is_numeric(x.strip() if isinstance(x, str) else x))


    # Raise an error if any invalid rows are found
    if invalid_latitudes.any():
        errors.append(f"Invalid point_latitude values:\n{samples_df[invalid_latitudes]}")
    if invalid_longitudes.any():
        errors.append(f"Invalid point_longitude values:\n{samples_df[invalid_longitudes]}")
    
    
    # Check for missing EPSG when coordinates are provided
    missing_epsg = samples_df[
        (samples_df['point_latitude'].apply(lambda x: not is_cell_empty(x))) &
        (samples_df['point_longitude'].apply(lambda x: not is_cell_empty(x))) &
        (samples_df['epsg_code'].apply(is_cell_empty))
    ]
    if not missing_epsg.empty:
        errors.append("EPSG is required when both point_latitude and point_longitude are specified.")

    invalid_epsg = samples_df[
        samples_df['epsg_code'].apply(lambda x: not is_cell_empty(x) and x not in valid_epsg_codes)
    ]
    if not invalid_epsg.empty:
        invalid_codes = invalid_epsg['epsg_code'].unique()
        errors.append(f"Invalid EPSG codes detected. Valid codes are: {', '.join(map(str, valid_epsg_codes))}. Found invalid codes: {', '.join(map(str, invalid_codes))}")
    return errors

def is_cell_empty(cell):
    return pd.isna(cell) or (isinstance(cell, str) and cell.strip() == '')
def is_numeric(value):
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False
    
def is_url(url: str) -> bool:
    """
    Check if the given string is a valid URL.

    Args:
    url (str): The URL to check.

    Returns:
    bool: True if the URL is valid, False otherwise.
    """
    # use re to check if the url is valid
    url_pattern = re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    return bool(url_pattern.match(url))

def validate_affiliation_identifier(authors_df, valid_affiliation_identifier_types):
    errors = []
    if 'author_affiliation_identifier' in authors_df.columns:
        authors_df['author_affiliation_identifier'] = authors_df['author_affiliation_identifier'].fillna('').astype(str).str.strip()
        authors_df['author_affiliation_identifier_type'] = authors_df['author_affiliation_identifier_type'].fillna('').astype(str).str.strip()

        missing_affil_type = authors_df[
            authors_df['author_affiliation_identifier'].apply(lambda x: not is_cell_empty(x)) & 
            authors_df['author_affiliation_identifier_type'].apply(lambda x: is_cell_empty(x))
        ]
        if not missing_affil_type.empty:
            errors.append("author_affiliation_identifier_type is required when author_affiliation_identifier is provided.")

        invalid_affil_types = authors_df[
            authors_df['author_affiliation_identifier'].apply(lambda x: not is_cell_empty(x)) & 
            ~authors_df['author_affiliation_identifier_type'].isin(valid_affiliation_identifier_types)
        ]
        if not invalid_affil_types.empty:
            errors.append("Invalid author_affiliation_identifier_type. Must be one of: " + ", ".join(valid_affiliation_identifier_types))

        invalid_entries = authors_df[
            authors_df['author_affiliation_identifier'].apply(lambda x: not is_cell_empty(x)) &
            authors_df['author_affiliation_identifier'].apply(lambda x: not is_url(str(x)))
        ]
        if not invalid_entries.empty:
            error_message = "Invalid URLs found at the following entries:\n"
            for idx, value in invalid_entries['author_affiliation_identifier'].items():
                error_message += f"Index {idx}: {value}\n"
            errors.append(error_message)
    return errors

def validate_related_resources(related_resources_df):
    errors = []
    required_fields = ['related_resource_type', 'related_resource_url', 'related_resource_title', 'relation_type']
    valid_resource_types = ["Audiovisual", "Book", "BookChapter", "Collection", "ComputationalNotebook", "ConferencePaper", "ConferenceProceeding", "DataPaper", "Dataset", "Dissertation", "Event", "Image", "Instrument", "InteractiveResource", "Journal", "JournalArticle", "Model", "Other", "OutputManagementPlan", "PeerReview", "PhysicalObject", "Preprint", "Report", "Service", "Software", "Sound", "Standard", "StudyRegistration", "Text", "Workflow"]

    valid_relation_types = [
        "IsCitedBy", "Cites", "IsSupplementTo", "IsSupplementedBy", "IsContinuedBy", "Continues","IsNewVersionOf", "IsPreviousVersionOf","IsPartOf","HasPart","IsPublishedIn","IsReferencedBy","References","IsDocumentedBy","Documents","IsCompiledBy","Compiles","IsVariantFormOf",    "IsOriginalFormOf","IsIdenticalTo","HasMetadata", "IsMetadataFor","Reviews","IsReviewedBy","IsDerivedFrom","IsSourceOf","Describes","IsDescribedBy","HasVersion","IsVersionOf","Requires","IsRequiredBy","Obsoletes","IsObsoletedBy","Collects","IsCollectedBy"
    ]
    
    # Check for any missing required fields in any of the related resources entries
    if related_resources_df[required_fields].applymap(lambda x: is_cell_empty(x.strip() if isinstance(x, str) else x)).any().any():
        errors.append("Missing required fields in related resources entries.")
    
    # make sure the related_resource_url is a valid URL
    invalid_entries = related_resources_df[related_resources_df['related_resource_url'].apply(lambda x: not is_url(str(x).strip()))]
    if not invalid_entries.empty:
        error_message = "Invalid related resources URLs found at the following entries:\n"
        for idx, value in invalid_entries['related_resource_url'].items():
            error_message += f"Index {idx}: {value.strip()}\n"
        errors.append(error_message)

    if not related_resources_df['related_resource_type'].isin(valid_resource_types).all():
        invalid_types = related_resources_df[~related_resources_df['related_resource_type'].isin(valid_resource_types)]['related_resource_type'].unique()
        errors.append(f"Invalid related_resource_type. Must be one of: {', '.join(valid_resource_types)}. Found invalid types: {', '.join(invalid_types)}")
    
    if not related_resources_df['relation_type'].isin(valid_relation_types).all():
        invalid_relations = related_resources_df[~related_resources_df['relation_type'].isin(valid_relation_types)]['relation_type'].unique()
        errors.append(f"Invalid relation_type. Must be one of: {', '.join(valid_relation_types)}. Found invalid types: {', '.join(invalid_relations)}")

    return errors

def validate_author_identifier(authors_df, valid_identifier_types):
    errors = []
    if 'author_identifier' in authors_df.columns:
        valid_identifiers = authors_df[~authors_df['author_identifier'].apply(lambda x: is_cell_empty(x.strip() if isinstance(x, str) else x))]
            
        if not valid_identifiers.empty:
            missing_identifier_type = valid_identifiers[valid_identifiers['author_identifier_type'].apply(lambda x: is_cell_empty(x.strip() if isinstance(x, str) else x))]
            if not missing_identifier_type.empty:
                missing_rows = missing_identifier_type.index.tolist()
                errors.append(f"author_identifier_type is required when author_identifier is provided for the following: rows [{', '.join(map(str, missing_rows))}]")

            invalid_identifier_types = valid_identifiers[~valid_identifiers['author_identifier_type'].apply(lambda x: x.strip() if isinstance(x, str) else x).isin(valid_identifier_types)]
            if not invalid_identifier_types.empty:
                invalid_rows = invalid_identifier_types.index.tolist()
                errors.append(f"author_identifier_type is invalid. Must be one of: {', '.join(valid_identifier_types)}. Invalid types found in: rows [{', '.join(map(str, invalid_rows))}]")
        
        # make sure the author_identifier is a valid URL
        invalid_url = valid_identifiers[~valid_identifiers['author_identifier'].apply(lambda x: is_url(str(x).strip()))]
        if not invalid_url.empty:
            invalid_url_rows = invalid_url.index.tolist()
            errors.append(f"Invalid author identifier URLs found in the following: rows [{', '.join(map(str, invalid_url_rows))}]")
    
    return errors
def validate_sample_type(sample_df):
    errors = []
    sample_types = [
        "AC Chips", "Core", "Core - Friable", "Core Catcher", "Core Half Round",
        "Core Piece", "Core Quarter Round", "Core Section", "Core Section Half",
        "Core Slab", "Core Sub-Piece", "Core U-Channel", "Experimental", "Full Core",
        "Grab", "Heavy Mineral Concentrate", "Individual Sample", "Litter", "Other",
        "Phyllos", "RC Chips", "Rock Powder", "Soil Profile", "Soil", "Surface Soil",
        "Termite Mound", "Vegetation", "Water", "Pisolite", "Hardpan soil",
        "Thin Section", "Polished Block", "Polished Round"
    ]
    # Filter out empty or null values
    valid_samples = sample_df[sample_df['sample_type'].notna() & (sample_df['sample_type'] != '')]
    
    invalid_types = valid_samples[~valid_samples['sample_type'].isin(sample_types)]
    if not invalid_types.empty:
        invalid_type_list = invalid_types['sample_type'].unique().tolist()
        errors.append(f"Invalid sample types found: {invalid_type_list}. Must be one of: {', '.join(sample_types)}")
    
    return errors

def validate_user_keywords(user_keywords):
    # Regular expression pattern for allowed characters
    pattern = r'^[\w\s.-]+$'
    
    # Check if the user_keywords match the pattern
    if re.match(pattern, user_keywords):
        return user_keywords
    else:
        # Remove any characters that are not allowed
        sanitized_keywords = re.sub(r'[^\w\s.-]', ' ', user_keywords)
        return sanitized_keywords   
def validate_authors(authors_df):
    errors = []
    authors_columns_to_check = ['author_email', 'author_name', 'author_affiliation', 'author_name_type']
    valid_identifier_types = ["ORCID", "ISNI", "LCNA", "VIAF", "GND", "DAI", "ResearcherID", "ScopusID", "Other"]
    valid_affiliation_identifier_types = ["ROR", "Other"]
    errors.extend(check_required_fields(authors_df, authors_columns_to_check))
    errors.extend(validate_affiliation_identifier(authors_df, valid_affiliation_identifier_types))
    errors.extend(validate_author_identifier(authors_df, valid_identifier_types))
    return errors
def generate_sample_name(org_id, sample_type, sample_number):
    org_name= get_organization_name(org_id)
    org_name = org_name.replace(' ', '_')
    sample_type = sample_type.replace(' ', '_')
    sample_number = sample_number.replace(' ', '_')
    
    name = f"{org_name}-{sample_type}-Sample-{sample_number}"
    name = re.sub(r'[^a-z0-9-_]', '', name.lower())
    return name 
def generate_sample_title(org_id, sample_type, sample_number):
    org_name= get_organization_name(org_id)
    org_name = org_name
    sample_type = sample_type
    sample_number = sample_number
    title= f"{org_name} - {sample_type} Sample {sample_number}"
    return title  
def get_organization_name(organization_id):
    try:
        organization = get_action('organization_show')({}, {'id': organization_id})
        organization_name = organization['name']
        return organization_name
    except:
        return None
def validate_sample_names(samples_df, org_id):
    samples_data = []
    existing_names = set()
    errors = []
    for _, row in samples_df.iterrows():
        sample = row.to_dict()
        sample["name"] = generate_sample_name(org_id, sample['sample_type'], sample['sample_number'])
        # Check for uniqueness
        if sample["name"] in existing_names:
            errors.append(f"Duplicate sample name: {sample['name']}")
        else:
            existing_names.add(sample["name"])
        samples_data.append(sample)
        try:
            package_list = toolkit.get_action('package_list')({}, {})
            for package in package_list:
                package_data = toolkit.get_action('package_show')({}, {'id': package})
                existing_name = package_data.get('name')
                if existing_name in existing_names:
                    errors.append(f"Sample name {existing_name} already exists in CKAN")
        except Exception as e:
            errors.append(f"Error fetching CKAN data: {str(e)}")
    return errors

def validate_samples(samples_df, related_resources_df, authors_df, funding_df):
    errors = []
    samples_columns_to_check = ['sample_number', 'description', 'user_keywords', 'sample_type', 'author_emails']
    errors.extend(check_required_fields(samples_df, samples_columns_to_check))
    errors.extend(check_unique_sample_number(samples_df))
    errors.extend(validate_epsg(samples_df))
    errors.extend(validate_sample_depth(samples_df))
    errors.extend(validate_elevation(samples_df))
    errors.extend(validate_sample_type(samples_df))
    errors.extend(validate_match_related_resource_url(samples_df, related_resources_df))
    errors.extend(validate_match_user_email(samples_df, authors_df))
    errors.extend(validate_match_project_identifier(samples_df, funding_df))
    errors.extend(validate_acquisition_date(samples_df))
    
    return errors