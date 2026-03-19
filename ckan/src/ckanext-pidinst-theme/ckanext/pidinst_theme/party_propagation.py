"""Party (facility) update/delete propagation helpers.

When a party group is updated (e.g. name change, identifier change),
the copied metadata inside every instrument that references that party
must be updated too.  This module provides reusable helpers for:

* Finding all instruments that reference a party.
* Propagating party field changes into instrument composite fields.
* Blocking party deletion when instruments still reference it.

The module is intentionally kept free of Flask/Blueprint concerns so it
can be called from CKAN chained actions, CLI commands, or tests.
"""

import json
import logging

import ckan.plugins.toolkit as toolkit

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

#: When True, ``owner_contact`` is always overwritten with the party's
#: ``party_contact`` value during propagation – even if the instrument
#: already has a non-empty contact.  When False, ``owner_contact`` is
#: only filled in when the current value is empty/blank.
ALWAYS_SYNC_OWNER_CONTACT = False

# ---------------------------------------------------------------------------
# Field mapping: composite field name → (party_id subfield, field mappings)
#
# Each mapping tuple is (party_field, instrument_subfield).
# "party_field" is resolved via ``_resolve_party_field``.
# ---------------------------------------------------------------------------

_FIELD_MAP = {
    'owner': {
        'party_id_key': 'owner_party_id',
        'fields': [
            ('title', 'owner_name'),
            ('_identifier', 'owner_identifier'),
            ('party_identifier_type', 'owner_identifier_type'),
        ],
        'contact': 'owner_contact',   # special: conditional sync
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
    """Return the effective identifier string for a party.

    ROR parties store their identifier in ``party_identifier_ror``;
    all other types use ``party_identifier``.
    """
    id_type = (party_dict.get('party_identifier_type') or '').strip()
    if id_type == 'ROR':
        return (party_dict.get('party_identifier_ror') or '').strip()
    return (party_dict.get('party_identifier') or '').strip()


def _resolve_party_field(party_dict, field_key):
    """Resolve a logical field key to its value from *party_dict*.

    The special key ``_identifier`` is resolved via
    ``_resolve_party_identifier``; everything else is a direct dict
    lookup.
    """
    if field_key == '_identifier':
        return _resolve_party_identifier(party_dict)
    return (party_dict.get(field_key) or '').strip()


def _parse_composite(raw):
    """Parse a composite-repeating field value into a list of dicts."""
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [e for e in parsed if isinstance(e, dict)]
        except (json.JSONDecodeError, ValueError):
            pass
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_instruments_referencing_party(party_name):
    """Return a list of package dicts for instruments that reference *party_name*.

    Searches across ``owner``, ``manufacturer`` and ``funder`` composite
    fields.  Only instruments (``dataset_type:instrument``) are returned.
    """
    ctx = {'ignore_auth': True}

    # Search for instruments that are members of the party group.
    # This is the fast path – the plugin already maintains group membership.
    # Fall back to a broader scan if group membership is inconsistent.
    try:
        result = toolkit.get_action('package_search')(ctx, {
            'q': '*:*',
            'fq': 'dataset_type:instrument',
            'rows': 10000,
        })
    except Exception:
        log.exception('package_search failed while looking for party references')
        return []

    matching = []
    for pkg in result.get('results', []):
        if _package_references_party(pkg, party_name):
            matching.append(pkg)

    return matching


def _package_references_party(pkg, party_name):
    """Return True if *pkg* references *party_name* in any composite field."""
    for comp_field, cfg in _FIELD_MAP.items():
        entries = _parse_composite(pkg.get(comp_field))
        for entry in entries:
            pid = (entry.get(cfg['party_id_key']) or '').strip()
            if pid == party_name:
                return True
    return False


def _package_references_party(pkg, party_name):
    """Return True if *pkg* references *party_name* in any composite field."""
    for comp_field, cfg in _FIELD_MAP.items():
        entries = _parse_composite(pkg.get(comp_field))
        for entry in entries:
            pid = (entry.get(cfg['party_id_key']) or '').strip()
            if pid == party_name:
                return True
    return False


def propagate_party_update(party_dict, old_name=None):
    """Propagate changes from *party_dict* into every referencing instrument.

    *party_dict* should be a full group dict as returned by ``group_show``
    (with scheming fields promoted to top-level keys).

    *old_name* is the party's previous ``name`` slug.  Pass it whenever the
    slug may have changed so that instruments holding the old reference can
    still be found.  When *old_name* equals the current name (no rename) it
    is ignored.

    Returns a summary dict::

        {
            'party_name': str,
            'instruments_checked': int,
            'instruments_updated': int,
            'failures': [{'id': str, 'error': str}, ...],
        }
    """
    party_name = party_dict.get('name', '')
    name_changed = bool(old_name and old_name != party_name)
    # Search by the old slug when renamed, otherwise by the current slug
    search_name = old_name if name_changed else party_name

    log.info(
        'Party update propagation START for party=%s (old_name=%s, renamed=%s)',
        party_name, old_name, name_changed,
    )

    instruments = find_instruments_referencing_party(search_name)
    log.info('Party %s: found %d instrument(s) to check', party_name, len(instruments))

    summary = {
        'party_name': party_name,
        'instruments_checked': len(instruments),
        'instruments_updated': 0,
        'failures': [],
    }

    for pkg in instruments:
        try:
            updated = _update_instrument_party_fields(pkg, party_dict, old_name=old_name)
            if updated:
                summary['instruments_updated'] += 1
        except Exception as exc:
            pkg_id = pkg.get('id', '?')
            log.error(
                'Party propagation FAILED for instrument %s (party=%s): %s',
                pkg_id, party_name, exc,
            )
            summary['failures'].append({'id': pkg_id, 'error': str(exc)})

    log.info(
        'Party update propagation END for party=%s: updated=%d, failures=%d',
        party_name, summary['instruments_updated'], len(summary['failures']),
    )
    return summary


def _update_instrument_party_fields(pkg, party_dict, old_name=None):
    """Update composite fields in *pkg* with values from *party_dict*.

    When *old_name* differs from ``party_dict['name']`` (a rename), each
    matching entry's ``*_party_id`` subfield is updated to the new slug so
    the instrument keeps a valid reference.

    Returns True if a ``package_patch`` was performed, False if no
    changes were needed.
    """
    party_name = party_dict.get('name', '')
    name_changed = bool(old_name and old_name != party_name)
    # When renamed, entries still hold the old slug → match against it
    search_name = old_name if name_changed else party_name
    patch_payload = {}

    # Use package_show to get the canonical, fully-resolved instrument data.
    # package_search results may be stale (Solr delay) or return composite
    # fields in a different format.  package_show always gives us the
    # current DB state with all composite fields present as JSON strings.
    try:
        fresh_pkg = toolkit.get_action('package_show')(
            {'ignore_auth': True}, {'id': pkg['id']}
        )
    except Exception:
        log.warning(
            'package_show failed for instrument %s; falling back to search result',
            pkg.get('id', '?'),
        )
        fresh_pkg = pkg

    for comp_field, cfg in _FIELD_MAP.items():
        entries = _parse_composite(fresh_pkg.get(comp_field))
        changed = False

        for entry in entries:
            pid = (entry.get(cfg['party_id_key']) or '').strip()
            if pid != search_name:
                continue

            # If the slug changed, update the *_party_id reference so the
            # instrument points to the new party slug going forward.
            if name_changed:
                entry[cfg['party_id_key']] = party_name
                changed = True

            # Map standard display fields
            for party_key, instr_key in cfg['fields']:
                new_val = _resolve_party_field(party_dict, party_key)
                old_val = (entry.get(instr_key) or '').strip()
                if new_val != old_val:
                    entry[instr_key] = new_val
                    changed = True

            # Conditional contact sync (owner only)
            contact_key = cfg.get('contact')
            if contact_key:
                party_contact = (party_dict.get('party_contact') or '').strip()
                current_contact = (entry.get(contact_key) or '').strip()
                if ALWAYS_SYNC_OWNER_CONTACT:
                    if party_contact != current_contact:
                        entry[contact_key] = party_contact
                        changed = True
                else:
                    # Only fill when empty
                    if not current_contact and party_contact:
                        entry[contact_key] = party_contact
                        changed = True

        if changed:
            patch_payload[comp_field] = json.dumps(entries)

    if not patch_payload:
        return False

    ctx = {'ignore_auth': True}
    patch_payload['id'] = pkg['id']
    toolkit.get_action('package_patch')(ctx, patch_payload)

    log.info(
        'Propagated party=%s changes to instrument %s (fields: %s)',
        party_name, pkg['id'], ', '.join(k for k in patch_payload if k != 'id'),
    )
    return True


# ---------------------------------------------------------------------------
# Delete guard
# ---------------------------------------------------------------------------

def check_party_deletable(party_name):
    """Check whether a party can be safely deleted.

    Returns a dict::

        {
            'deletable': bool,
            'reference_count': int,
            'message': str,          # human-readable explanation
        }

    When ``deletable`` is False the caller should raise a
    ``ValidationError`` with the message.
    """
    instruments = find_instruments_referencing_party(party_name)
    count = len(instruments)

    if count == 0:
        return {
            'deletable': True,
            'reference_count': 0,
            'message': '',
        }

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
