"""Party (facility) update/delete propagation helpers."""

import json
import logging

from .propagation_helpers import (
    parse_composite, search_instruments, load_fresh_package,
    patch_package, run_propagation,
)

log = logging.getLogger(__name__)

# When True, owner_contact is always synced from party_contact.
# When False, only filled when the instrument's contact is empty.
ALWAYS_SYNC_OWNER_CONTACT = False

_FIELD_MAP = {
    'owner': {
        'party_id_key': 'owner_party_id',
        'fields': [
            ('title', 'owner_name'),
            ('_identifier', 'owner_identifier'),
            ('party_identifier_type', 'owner_identifier_type'),
        ],
        'contact': 'owner_contact',
    },
    'manufacturer': {
        'party_id_key': 'manufacturer_party_id',
        'fields': [
            ('title', 'manufacturer_name'),
            ('_identifier', 'manufacturer_identifier'),
            ('party_identifier_type', 'manufacturer_identifier_type'),
        ],
        'contact': None,
    },
    'funder': {
        'party_id_key': 'funder_party_id',
        'fields': [
            ('title', 'funder_name'),
            ('_identifier', 'funder_identifier'),
            ('party_identifier_type', 'funder_identifier_type'),
        ],
        'contact': None,
    },
}


def _resolve_party_identifier(party_dict):
    """ROR parties use party_identifier_ror; others use party_identifier."""
    id_type = (party_dict.get('party_identifier_type') or '').strip()
    if id_type == 'ROR':
        return (party_dict.get('party_identifier_ror') or '').strip()
    return (party_dict.get('party_identifier') or '').strip()


def _resolve_party_field(party_dict, field_key):
    """Resolve a logical field key (_identifier is special-cased)."""
    if field_key == '_identifier':
        return _resolve_party_identifier(party_dict)
    return (party_dict.get(field_key) or '').strip()


def _package_references_party(pkg, party_name):
    for comp_field, cfg in _FIELD_MAP.items():
        for entry in parse_composite(pkg.get(comp_field)):
            if (entry.get(cfg['party_id_key']) or '').strip() == party_name:
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_instruments_referencing_party(party_name):
    """Return instrument package dicts that reference *party_name*."""
    return [pkg for pkg in search_instruments()
            if _package_references_party(pkg, party_name)]


def propagate_party_update(party_dict, old_name=None):
    """Propagate party changes into every referencing instrument.

    Returns summary dict with party_name, instruments_checked,
    instruments_updated, failures.
    """
    party_name = party_dict.get('name', '')
    name_changed = bool(old_name and old_name != party_name)
    search_name = old_name if name_changed else party_name

    instruments = find_instruments_referencing_party(search_name)
    summary = run_propagation(
        instruments,
        lambda pkg: _update_instrument_party_fields(pkg, party_dict, old_name=old_name),
        f'party={party_name}',
    )
    summary['party_name'] = party_name
    return summary


def _update_instrument_party_fields(pkg, party_dict, old_name=None):
    """Update composite entries matching the party. Returns True if patched."""
    party_name = party_dict.get('name', '')
    name_changed = bool(old_name and old_name != party_name)
    search_name = old_name if name_changed else party_name

    fresh_pkg = load_fresh_package(pkg['id'], fallback=pkg)
    patch_payload = {}

    for comp_field, cfg in _FIELD_MAP.items():
        entries = parse_composite(fresh_pkg.get(comp_field))
        changed = False

        for entry in entries:
            if (entry.get(cfg['party_id_key']) or '').strip() != search_name:
                continue

            if name_changed:
                entry[cfg['party_id_key']] = party_name
                changed = True

            for party_key, instr_key in cfg['fields']:
                new_val = _resolve_party_field(party_dict, party_key)
                if new_val != (entry.get(instr_key) or '').strip():
                    entry[instr_key] = new_val
                    changed = True

            contact_key = cfg.get('contact')
            if contact_key:
                party_contact = (party_dict.get('party_contact') or '').strip()
                current_contact = (entry.get(contact_key) or '').strip()
                if ALWAYS_SYNC_OWNER_CONTACT:
                    if party_contact != current_contact:
                        entry[contact_key] = party_contact
                        changed = True
                elif not current_contact and party_contact:
                    entry[contact_key] = party_contact
                    changed = True

        if changed:
            patch_payload[comp_field] = json.dumps(entries)

    if not patch_payload:
        return False

    patch_package(pkg['id'], patch_payload)
    log.info('Propagated party=%s to %s (fields: %s)',
             party_name, pkg['id'], ', '.join(patch_payload))
    return True


# ---------------------------------------------------------------------------
# Delete guard
# ---------------------------------------------------------------------------

def check_party_deletable(party_name):
    """Check whether a party can be safely deleted.

    Returns dict with deletable, reference_count, message.
    """
    instruments = find_instruments_referencing_party(party_name)
    count = len(instruments)

    if count == 0:
        return {'deletable': True, 'reference_count': 0, 'message': ''}

    noun = 'instrument' if count == 1 else 'instruments'
    return {
        'deletable': False,
        'reference_count': count,
        'message': (
            f'Cannot delete party "{party_name}": '
            f'it is still referenced by {count} {noun}. '
            f'Remove or reassign the party from those instruments first.'
        ),
    }
