"""Read-only reconciliation for DOI metadata suggestions.

This module runs after the pure DOI resolver/mapper. It is CKAN-aware, but it
only reads existing parties and taxonomy terms, then compares suggestion
identifiers exactly enough for safe preselection. It must not create, update,
or persist anything.
"""

from __future__ import annotations

import logging
import json
from typing import Any, Dict, Iterable, List, Optional

import ckan.plugins.toolkit as tk

from ckanext.pidinst_theme.helpers import get_taxonomy_name


log = logging.getLogger(__name__)

MATCH_GROUPS = (
    'manufacturer',
    'owner',
    'funder',
    'instrument_type',
    'measured_variable',
)


def reconcile(resolved_fields: Dict[str, Any], context: Optional[dict] = None) -> dict:
    """Return matched_suggestions grouped by target field.

    ``resolved_fields`` is the ``ResolveResult.to_dict()['resolved_fields']``
    payload. All CKAN access here is read-only.
    """
    resolved_fields = resolved_fields or {}
    context = _read_context(context)

    parties = _read_parties(context)
    taxonomy_terms = _read_taxonomy_terms(context)

    return {
        'manufacturer': match_manufacturer(
            resolved_fields.get('manufacturer_suggestions') or [], parties
        ),
        'owner': match_owner(
            resolved_fields.get('owner_suggestions') or [], parties
        ),
        'funder': match_funder(
            resolved_fields.get('funder_suggestions') or [], parties
        ),
        'instrument_type': match_instrument_type(
            resolved_fields.get('instrument_type_suggestions') or [],
            taxonomy_terms,
        ),
        'measured_variable': match_measured_variable(
            resolved_fields.get('taxonomy_suggestions') or [],
            taxonomy_terms,
        ),
    }


def match_manufacturer(suggestions: Iterable[dict], parties: List[dict]) -> List[dict]:
    return _match_party_suggestions(
        suggestions,
        parties,
        suggested_field='manufacturer',
        role='Manufacturer',
        value_keys=('name',),
        identifier_keys=('ror', 'name_identifier', 'nameIdentifier'),
        name_identifier_key='nameIdentifiers',
    )


def match_owner(suggestions: Iterable[dict], parties: List[dict]) -> List[dict]:
    return _match_party_suggestions(
        suggestions,
        parties,
        suggested_field='owner',
        role='Owner',
        value_keys=('name',),
        identifier_keys=('ror', 'name_identifier', 'nameIdentifier'),
        name_identifier_key='nameIdentifiers',
    )


def match_funder(suggestions: Iterable[dict], parties: List[dict]) -> List[dict]:
    return _match_party_suggestions(
        suggestions,
        parties,
        suggested_field='funder',
        role='Funder',
        value_keys=('funderName', 'name'),
        identifier_keys=('funderIdentifier', 'ror', 'name_identifier'),
        name_identifier_key='nameIdentifiers',
    )


def match_instrument_type(
    suggestions: Iterable[dict],
    taxonomy_terms: List[dict],
) -> List[dict]:
    return _match_taxonomy_suggestions(
        suggestions,
        taxonomy_terms,
        suggested_field='instrument_type',
        taxonomy_key='instrument',
        value_keys=('instrument_type_name', 'label', 'subject'),
        identifier_keys=('instrument_type_identifier', 'uri', 'value_uri', 'valueURI'),
    )


def match_measured_variable(
    suggestions: Iterable[dict],
    taxonomy_terms: List[dict],
) -> List[dict]:
    return _match_taxonomy_suggestions(
        suggestions,
        taxonomy_terms,
        suggested_field='measured_variable',
        taxonomy_key='measured_variable',
        value_keys=('subject', 'label', 'name'),
        identifier_keys=('value_uri', 'valueURI', 'uri', 'identifier'),
    )


def _read_context(context: Optional[dict]) -> dict:
    merged = dict(context or {})
    merged['ignore_auth'] = True
    return merged


def _read_parties(context: dict) -> List[dict]:
    try:
        names = tk.get_action('group_list')(context, {'type': 'party'})
    except Exception:
        log.exception('Failed to list local parties for DOI reconciliation')
        return []

    parties = []
    for name in names or []:
        try:
            party = tk.get_action('group_show')(
                context, {'id': name, 'include_extras': True}
            )
        except Exception:
            log.exception('Failed to read party %r for DOI reconciliation', name)
            continue
        parties.append(_flatten_extras(party))
    return parties


def _read_taxonomy_terms(context: dict) -> List[dict]:
    terms = []
    for logical_key in ('instrument', 'platform', 'measured_variable'):
        taxonomy_name = get_taxonomy_name(logical_key)
        try:
            listed = tk.get_action('taxonomy_term_list')(
                context, {'id': taxonomy_name}
            )
        except Exception:
            log.exception(
                'Failed to list taxonomy %r for DOI reconciliation',
                taxonomy_name,
            )
            continue
        for term in _flatten_terms(listed):
            item = dict(term)
            item['taxonomy_key'] = logical_key
            item['taxonomy_name'] = taxonomy_name
            terms.append(item)
    return terms


def _flatten_extras(item: dict) -> dict:
    flattened = dict(item or {})
    for extra in flattened.get('extras') or []:
        if isinstance(extra, dict) and extra.get('key'):
            flattened[extra['key']] = extra.get('value')
    return flattened


def _flatten_terms(terms: Iterable[dict]) -> List[dict]:
    flattened = []
    for term in terms or []:
        if not isinstance(term, dict):
            continue
        item = dict(term)
        children = item.pop('children', []) or []
        flattened.append(item)
        flattened.extend(_flatten_terms(children))
    return flattened


def _match_party_suggestions(
    suggestions: Iterable[dict],
    parties: List[dict],
    *,
    suggested_field: str,
    role: str,
    value_keys: Iterable[str],
    identifier_keys: Iterable[str],
    name_identifier_key: str,
) -> List[dict]:
    records = []
    role_parties = [
        party for party in parties
        if _party_has_role(party, role)
    ]
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        source_value = _first_value(suggestion, value_keys)
        source_identifier = (
            _first_value(suggestion, identifier_keys)
            or _first_name_identifier(suggestion.get(name_identifier_key))
        )
        source_identifier_type = _party_identifier_type(
            source_identifier,
            suggestion,
        )
        matches = _find_party_matches(source_identifier, role_parties)
        records.append(_matched_suggestion(
            suggestion,
            source_value=source_value,
            source_identifier=source_identifier,
            source_identifier_type=source_identifier_type,
            suggested_field=suggested_field,
            matched_local_type='party',
            matches=matches,
        ))
    return records


def _match_taxonomy_suggestions(
    suggestions: Iterable[dict],
    taxonomy_terms: List[dict],
    *,
    suggested_field: str,
    taxonomy_key: str,
    value_keys: Iterable[str],
    identifier_keys: Iterable[str],
) -> List[dict]:
    records = []
    scoped_terms = [
        term for term in taxonomy_terms
        if term.get('taxonomy_key') == taxonomy_key
        or (
            suggested_field == 'instrument_type'
            and term.get('taxonomy_key') == 'platform'
        )
    ]
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        source_value = _first_value(suggestion, value_keys)
        source_identifier = _first_value(suggestion, identifier_keys)
        matches = _find_taxonomy_matches(source_identifier, scoped_terms)
        records.append(_matched_suggestion(
            suggestion,
            source_value=source_value,
            source_identifier=source_identifier,
            source_identifier_type='URI',
            suggested_field=suggested_field,
            matched_local_type='taxonomy_term',
            matches=matches,
        ))
    return records


def _matched_suggestion(
    suggestion: dict,
    *,
    source_value: str,
    source_identifier: str,
    source_identifier_type: str,
    suggested_field: str,
    matched_local_type: str,
    matches: List[dict],
) -> dict:
    status = _match_status(matches)
    unique = status == 'exact_unique'
    matched = matches[0] if unique else {}
    result = {
        'source_value': source_value,
        'source_identifier': source_identifier,
        'source_identifier_type': source_identifier_type,
        'suggested_field': suggested_field,
        'match_status': status,
        'matched_local_id': _local_option_value(matched, matched_local_type),
        'matched_local_name': matched.get('name', ''),
        'matched_local_label': _local_label(matched),
        'matched_local_identifier': _local_identifier(matched, matched_local_type),
        'matched_local_record_id': matched.get('id', ''),
        'matched_local_type': matched_local_type,
        'apply_allowed': unique,
    }
    if suggestion:
        result['source'] = suggestion.get('source', '')
    return result


def _match_status(matches: List[dict]) -> str:
    if len(matches) == 1:
        return 'exact_unique'
    if len(matches) > 1:
        return 'ambiguous'
    return 'no_match'


def _find_party_matches(identifier: str, parties: List[dict]) -> List[dict]:
    normalized = _normalize_identifier(identifier)
    if not normalized:
        return []
    return [
        party for party in parties
        if normalized in {
            _normalize_identifier(party.get('party_identifier_ror')),
            _normalize_identifier(party.get('party_identifier')),
        }
    ]


def _find_taxonomy_matches(identifier: str, terms: List[dict]) -> List[dict]:
    normalized = _normalize_identifier(identifier)
    if not normalized:
        return []
    return [
        term for term in terms
        if normalized in {
            _normalize_identifier(term.get('uri')),
            _normalize_identifier(term.get('identifier')),
            _normalize_identifier(term.get('value_uri')),
            _normalize_identifier(term.get('valueURI')),
        }
    ]


def _party_has_role(party: dict, role: str) -> bool:
    raw_roles = party.get('party_role')
    if not raw_roles:
        return True
    if isinstance(raw_roles, str):
        try:
            parsed = json.loads(raw_roles)
            roles = parsed if isinstance(parsed, list) else [raw_roles]
        except (TypeError, ValueError):
            roles = [
                item.strip(" '\"")
                for item in raw_roles.strip('[]').split(',')
            ]
    elif isinstance(raw_roles, (list, tuple, set)):
        roles = [str(item).strip() for item in raw_roles]
    else:
        return True
    roles = [item for item in roles if item]
    if not roles:
        return True
    return role in roles


def _first_value(item: dict, keys: Iterable[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''


def _first_name_identifier(name_identifiers: Any) -> str:
    if not isinstance(name_identifiers, list):
        return ''
    for entry in name_identifiers:
        if not isinstance(entry, dict):
            continue
        value = entry.get('nameIdentifier')
        if value:
            return str(value).strip()
    return ''


def _party_identifier_type(identifier: str, suggestion: dict) -> str:
    if _is_ror(identifier):
        return 'ROR'
    explicit = (
        suggestion.get('funderIdentifierType')
        or suggestion.get('name_identifier_scheme')
        or suggestion.get('nameIdentifierScheme')
        or ''
    )
    if str(explicit).upper() == 'ROR':
        return 'ROR'
    return 'URL' if identifier else 'ROR'


def _is_ror(identifier: str) -> bool:
    return 'ror.org/' in str(identifier or '').lower()


def _normalize_identifier(identifier: Any) -> str:
    value = str(identifier or '').strip()
    if not value:
        return ''
    return value.rstrip('/').lower()


def _local_label(item: dict) -> str:
    return str(item.get('label') or item.get('title') or item.get('name') or '').strip()


def _local_identifier(item: dict, local_type: str) -> str:
    if local_type == 'party':
        return str(
            item.get('party_identifier_ror')
            or item.get('party_identifier')
            or ''
        ).strip()
    return str(item.get('uri') or item.get('identifier') or '').strip()


def _local_option_value(item: dict, local_type: str) -> str:
    if not item:
        return ''
    if local_type == 'party':
        return str(item.get('name') or item.get('id') or '').strip()
    return str(
        item.get('uri')
        or item.get('identifier')
        or item.get('value_uri')
        or item.get('valueURI')
        or item.get('label')
        or item.get('id')
        or ''
    ).strip()
