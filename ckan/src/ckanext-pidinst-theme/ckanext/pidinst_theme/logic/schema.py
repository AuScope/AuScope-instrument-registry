import ckan.authz as authz
import ckan.plugins.toolkit as tk
import json
import re
import calendar
from datetime import datetime
import ckanext.pidinst_theme.helpers as h


def _parse_date_bound(val, is_end=False):
    """Parse YYYY, YYYY-MM, or YYYY-MM-DD into a YYYYMMDD integer.
    Returns first day for 'from', last day for 'to'.  None on invalid input.
    """
    s = (val or '').strip()
    if not s:
        return None
    try:
        if len(s) == 4:
            datetime.strptime(s, '%Y')
            y = int(s)
            return y * 10000 + 1231 if is_end else y * 10000 + 101
        elif len(s) == 7:
            d = datetime.strptime(s, '%Y-%m')
            last_day = calendar.monthrange(d.year, d.month)[1]
            return (d.year * 10000 + d.month * 100 + last_day
                    if is_end else d.year * 10000 + d.month * 100 + 1)
        elif len(s) == 10:
            d = datetime.strptime(s, '%Y-%m-%d')
            return d.year * 10000 + d.month * 100 + d.day
    except (ValueError, TypeError):
        pass
    return None


_DATE_PARAMS = frozenset({
    'commissioned_from', 'commissioned_to',
    'decommissioned_from', 'decommissioned_to',
})

_DATE_FILTER_DEFS = [
    ('commissioned_from', 'commissioned_to',
     'commissioned_start_i', 'commissioned_end_i'),
    ('decommissioned_from', 'decommissioned_to',
     'decommissioned_start_i', 'decommissioned_end_i'),
]


def pidinst_theme_get_sum():
    not_empty = tk.get_validator("not_empty")
    convert_int = tk.get_validator("convert_int")

    return {
        "left": [not_empty, convert_int],
        "right": [not_empty, convert_int]
    }

@tk.chained_action
def before_dataset_search(search_params):
    """
    Exclude withdrawn/duplicate records.  Handle date range filter params.
    """
    search_params['include_private'] = 'True'
    # Append to any existing fq rather than overwriting it.
    existing_fq = search_params.get('fq', '')
    exclude_statuses = '-extras_publication_status:withdrawn -extras_publication_status:duplicate'
    fq = (existing_fq + ' ' + exclude_statuses).strip()

    # --- Date range filters ---
    # Strip invalid fq clauses CKAN's group controller may have added,
    # then apply proper integer range queries.
    try:
        request_args = tk.request.args
    except RuntimeError:
        # No active Flask request (CLI or background call)
        search_params['fq'] = fq
        return search_params

    if any(request_args.get(p) for p in _DATE_PARAMS):
        # Strip invalid fq clauses CKAN's group controller may have added
        for param in _DATE_PARAMS:
            fq = re.sub(r'\s*\+?' + re.escape(param) + r':"[^"]*"', '', fq)

        for from_param, to_param, start_field, end_field in _DATE_FILTER_DEFS:
            from_val = request_args.get(from_param, '').strip()
            to_val = request_args.get(to_param, '').strip()
            q_start = _parse_date_bound(from_val, is_end=False)
            q_end = _parse_date_bound(to_val, is_end=True)
            # Only add if not already present (avoids double-applying on /instruments)
            if q_start is not None and f'{end_field}:[{q_start}' not in fq:
                fq += f' +{end_field}:[{q_start} TO *]'
            if q_end is not None and f'{start_field}:[* TO {q_end}]' not in fq:
                fq += f' +{start_field}:[* TO {q_end}]'

    search_params['fq'] = fq
    return search_params

@tk.chained_action
def after_dataset_show(context, pkg_dict):
    """
    Add the Citation details to the pkg_dict so it can be displayed
    Format:
        owners (PublicationYear): Title. Publisher. (ResourceType). Identifier
    Example:
        Irino, T; Tada, R (2009): Chemical and mineral compositions of sediments from ODP Site 127-797. V. 2.1. Geological Institute, University of Tokyo. (instrument). https://doi.org/10.1594/PANGAEA.726855
    """
    citation = ''

    # Check if owner field exists before processing
    if 'manufacturer' in pkg_dict and pkg_dict['manufacturer']:
        manufacturer_list = json.loads(pkg_dict['manufacturer'])
        for i in range(0, len(manufacturer_list)):
            citation += manufacturer_list[i]['manufacturer_name']
            if i != len(manufacturer_list) - 1:
                citation += ', '
            elif 'publication_date' in pkg_dict and pkg_dict['publication_date'] != '':
                #publication_date = datetime.strptime(pkg_dict['publication_date'], '%Y-%m-%d')
                publication_date = datetime.strptime(pkg_dict['publication_date'].split(' ', 1)[0], '%Y-%m-%d')
                #citation += ' (' + pkg_dict['publication_date'].year + '): '
                citation += ' (' + str(publication_date.year) + '): '

    citation += pkg_dict['title']

    if citation[len(citation) -1] != '.':
        citation += '.'
    citation += ' '

    if 'publisher' in pkg_dict:
        citation += pkg_dict['publisher'] + '. '
    if 'resource_type' in pkg_dict:
        citation += '(' + pkg_dict['resource_type'] +'). '
    if 'doi' in pkg_dict:
        doi_resolver_url = h.doi_resolver_url()
        citation += doi_resolver_url + '/' + pkg_dict['doi']

    pkg_dict['citation'] = citation
