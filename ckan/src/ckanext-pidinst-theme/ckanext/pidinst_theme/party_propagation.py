"""Party (facility) update/delete propagation helpers."""

import json
import logging

import ckan.plugins.toolkit as toolkit

from .propagation_helpers import (
    parse_composite, search_instruments, load_fresh_package,
    patch_package, run_propagation,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Set ``ckanext.pidinst_theme.always_sync_owner_contact = true`` in your
# CKAN .ini file to have the party's contact email always overwrite the
# instrument's owner_contact field on every propagation pass.
#
# Default (false): contact is only copied when the instrument entry's contact
# field is currently empty, preserving any manually entered value.
#
# WARNING: changing this to ``true`` will silently overwrite any
# instrument-specific contact that was entered manually.
_CONFIG_KEY = 'ckanext.pidinst_theme.always_sync_owner_contact'


def _always_sync_owner_contact() -> bool:
    """Return the runtime value of the always_sync_owner_contact config flag."""
    return toolkit.asbool(toolkit.config.get(_CONFIG_KEY, False))

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


def propagate_party_update(party_dict, old_name=None, _job_id=None):
    """Propagate party changes into every referencing instrument.

    Returns summary dict with party_name, instruments_checked,
    instruments_updated, failures.

    When a party is renamed, a post-propagation verification pass re-scans
    for any instruments that still carry the old slug (e.g. because a
    transient patch failure left them stale) and retries patching them once.
    This ensures a partial failure does not permanently leave instruments
    pointing to the old slug.
    """
    party_name = party_dict.get('name', '')
    name_changed = bool(old_name and old_name != party_name)
    search_name = old_name if name_changed else party_name

    instruments = find_instruments_referencing_party(search_name)
    summary = run_propagation(
        instruments,
        lambda pkg: _update_instrument_party_fields(pkg, party_dict, old_name=old_name),
        f'party={party_name}',
        job_id=_job_id,
    )
    summary['party_name'] = party_name

    # Verification pass: when a rename occurred, re-query for instruments that
    # still reference the old slug.  This catches any packages that were
    # skipped or failed during the initial propagation sweep.
    if name_changed:
        stale = find_instruments_referencing_party(old_name)
        if stale:
            log.warning(
                'Party rename %r → %r: %d instrument(s) still reference the old '
                'slug after initial propagation; retrying.',
                old_name, party_name, len(stale),
            )
            retry_summary = run_propagation(
                stale,
                lambda pkg: _update_instrument_party_fields(pkg, party_dict, old_name=old_name),
                f'party={party_name} (retry)',
                job_id=None,
            )
            summary['instruments_updated'] += retry_summary['instruments_updated']
            # Surface only the instruments that still failed after the retry.
            summary['failures'] = retry_summary['failures']
            if retry_summary['failures']:
                log.error(
                    'Party rename %r → %r: %d instrument(s) still point to old '
                    'slug after retry and require manual correction: %s',
                    old_name, party_name, len(retry_summary['failures']),
                    [f['id'] for f in retry_summary['failures']],
                )

    return summary


def _update_instrument_party_fields(pkg, party_dict, old_name=None):
    """Update composite entries matching the party. Returns True if patched."""
    party_name = party_dict.get('name', '')
    name_changed = bool(old_name and old_name != party_name)
    search_name = old_name if name_changed else party_name

    fresh_pkg = load_fresh_package(pkg['id'], fallback=pkg)
    patch_payload = {}

    log.debug('[propagation DEBUG] pkg_id=%s search_name=%r name_changed=%s party_name=%r',
              pkg['id'], search_name, name_changed, party_name)
    log.debug('[propagation DEBUG] party_dict keys=%s title=%r id_type=%r id_ror=%r id_other=%r',
              list(party_dict.keys()),
              party_dict.get('title'),
              party_dict.get('party_identifier_type'),
              party_dict.get('party_identifier_ror'),
              party_dict.get('party_identifier'))

    for comp_field, cfg in _FIELD_MAP.items():
        raw = fresh_pkg.get(comp_field)
        entries = parse_composite(raw)
        log.debug('[propagation DEBUG] comp_field=%r raw_type=%s entries_count=%d raw_preview=%r',
                  comp_field, type(raw).__name__, len(entries), str(raw)[:200])
        changed = False

        for entry in entries:
            entry_id = (entry.get(cfg['party_id_key']) or '').strip()
            log.debug('[propagation DEBUG]   entry party_id_key=%r value=%r vs search_name=%r',
                      cfg['party_id_key'], entry_id, search_name)
            if entry_id != search_name:
                continue

            if name_changed:
                entry[cfg['party_id_key']] = party_name
                changed = True

            for party_key, instr_key in cfg['fields']:
                new_val = _resolve_party_field(party_dict, party_key)
                old_val = (entry.get(instr_key) or '').strip()
                log.debug('[propagation DEBUG]     field %r: new=%r old=%r match=%s',
                          instr_key, new_val, old_val, new_val == old_val)
                if new_val != old_val:
                    entry[instr_key] = new_val
                    changed = True

            contact_key = cfg.get('contact')
            if contact_key:
                party_contact = (party_dict.get('party_contact') or '').strip()
                current_contact = (entry.get(contact_key) or '').strip()
                if _always_sync_owner_contact():
                    if party_contact != current_contact:
                        entry[contact_key] = party_contact
                        changed = True
                elif not current_contact and party_contact:
                    entry[contact_key] = party_contact
                    changed = True

        if changed:
            patch_payload[comp_field] = json.dumps(entries)

    if not patch_payload:
        log.debug('[propagation DEBUG] pkg_id=%s no changes detected — skipping patch', pkg['id'])
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
