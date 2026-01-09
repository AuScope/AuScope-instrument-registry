import ckan.authz as authz
import ckan.plugins.toolkit as tk
import json
from datetime import datetime


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
    Force private datasets appear in search results
    """
    search_params['include_private'] = 'True'
    return search_params

@tk.chained_action
def after_dataset_show(context, pkg_dict):
    """
    Add the Citation details to the pkg_dict so it can be displayed
    Format:
        Authors (PublicationYear): Title. Publisher. (ResourceType). Identifier
    Example:
        Irino, T; Tada, R (2009): Chemical and mineral compositions of sediments from ODP Site 127-797. V. 2.1. Geological Institute, University of Tokyo. (dataset). https://doi.org/10.1594/PANGAEA.726855
    """
    citation = ''
    # author_list = json.loads(pkg_dict['author'])
    # for i in range(0, len(author_list)):
    #     citation += author_list[i]['author_name']
    #     if i != len(author_list) - 1:
    #         citation += ', '
    #     elif 'publication_date' in pkg_dict and pkg_dict['publication_date'] != '':
    #         #publication_date = datetime.strptime(pkg_dict['publication_date'], '%Y-%m-%d')
    #         publication_date = datetime.strptime(pkg_dict['publication_date'].split(' ', 1)[0], '%Y-%m-%d')
    #         #citation += ' (' + pkg_dict['publication_date'].year + '): '
    #         citation += ' (' + str(publication_date.year) + '): '
    # citation += pkg_dict['title']

    # if citation[len(citation) -1] != '.':
    #     citation += '.'
    # citation += ' '

    # if 'publisher' in pkg_dict:
    #     citation += pkg_dict['publisher'] + '. '
    # if 'resource_type' in pkg_dict:
    #     citation += '(' + pkg_dict['resource_type'] +'). '
    # if 'doi' in pkg_dict:
    #     citation += 'https://doi.org/' + pkg_dict['doi']

    pkg_dict['citation'] = citation
