"""Taxonomy term update propagation and delete protection."""

import json
import logging

from .propagation_helpers import (
    parse_composite, search_instruments, load_fresh_package,
    patch_package, run_propagation,
)

log = logging.getLogger(__name__)

# Central field mapping: composite field name → subfield keys.
# Shared by delete-guard, update-propagation, and term_to_entry.
_FIELD_MAP = {
    'instrument_type': {
        'name_key': 'instrument_type_name',
        'identifier_key': 'instrument_type_identifier',
        'identifier_type_key': 'instrument_type_identifier_type',
    },
    'measured_variable': {
        'name_key': 'measured_variable_name',
        'identifier_key': 'measured_variable_identifier',
        'identifier_type_key': 'measured_variable_identifier_type',
    },
}


def _entry_matches_term(entry, cfg, term_uri, term_label):
    """Match by identifier first, fall back to label."""
    if term_uri and (entry.get(cfg['identifier_key']) or '').strip() == term_uri:
        return True
    if term_label and (entry.get(cfg['name_key']) or '').strip() == term_label:
        return True
    return False


def _package_references_term(pkg, term_uri, term_label):
    for field_name, cfg in _FIELD_MAP.items():
        for entry in parse_composite(pkg.get(field_name)):
            if _entry_matches_term(entry, cfg, term_uri, term_label):
                return True
    return False


def _term_match_values(term_dict, old_term=None):
    """Return (uri, label) to search for, preferring old_term when given."""
    source = old_term if old_term else term_dict
    return (source.get('uri') or '').strip(), (source.get('label') or '').strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_packages_referencing_term(term_dict, old_term=None):
    """Return [{id, name, title}] for instruments referencing *term_dict*."""
    term_uri, term_label = _term_match_values(term_dict, old_term)
    return [
        {'id': pkg['id'], 'name': pkg.get('name', ''),
         'title': pkg.get('title') or pkg.get('name', '')}
        for pkg in search_instruments()
        if _package_references_term(pkg, term_uri, term_label)
    ]


def check_term_deletable(term_dict):
    """Check whether a taxonomy term can be safely deleted.

    Returns dict with deletable, reference_count, message, packages.
    """
    packages = find_packages_referencing_term(term_dict)
    count = len(packages)

    if count == 0:
        return {'deletable': True, 'reference_count': 0, 'message': '', 'packages': []}

    label = term_dict.get('label') or term_dict.get('id', '')
    noun = 'instrument' if count == 1 else 'instruments'
    return {
        'deletable': False,
        'reference_count': count,
        'message': (
            f'Cannot delete term "{label}": '
            f'it is still referenced by {count} {noun}. '
            f'Remove the term from those instruments first.'
        ),
        'packages': packages,
    }


def check_terms_deletable(terms):
    """Check whether a collection of taxonomy terms can all be safely deleted.

    Used when a delete operation cascades to multiple terms (e.g. deleting a
    parent term with children, or deleting an entire taxonomy).

    Returns dict with deletable, reference_count, message, packages.
    """
    blocking_packages = {}   # keyed by package id to deduplicate
    blocking_term_labels = []

    for term in terms:
        pkgs = find_packages_referencing_term(term)
        if pkgs:
            blocking_term_labels.append(term.get('label') or term.get('id', ''))
            for pkg in pkgs:
                blocking_packages[pkg['id']] = pkg

    all_blocking = list(blocking_packages.values())
    count = len(all_blocking)

    if count == 0:
        return {'deletable': True, 'reference_count': 0, 'message': '', 'packages': []}

    noun = 'instrument' if count == 1 else 'instruments'
    shown = blocking_term_labels[:3]
    suffix = f' (and {len(blocking_term_labels) - 3} more)' if len(blocking_term_labels) > 3 else ''
    term_labels_str = ', '.join(f'"{l}"' for l in shown) + suffix
    return {
        'deletable': False,
        'reference_count': count,
        'message': (
            f'Cannot delete: term(s) {term_labels_str} '
            f'are still referenced by {count} {noun}. '
            f'Remove those terms from the instruments first.'
        ),
        'packages': all_blocking,
    }


def propagate_term_update(term_dict, old_term=None, _job_id=None):
    """Propagate changed term metadata into every referencing instrument.

    Returns summary dict with term_label, instruments_checked,
    instruments_updated, failures.
    """
    term_label = term_dict.get('label', '')
    instruments = find_packages_referencing_term(term_dict, old_term=old_term)
    summary = run_propagation(
        instruments,
        lambda pkg: _update_package_term_fields(pkg, term_dict, old_term=old_term),
        f'term={term_label}',
        job_id=_job_id,
    )
    summary['term_label'] = term_label
    return summary


def _update_package_term_fields(pkg, term_dict, old_term=None):
    """Update composite entries matching the term. Returns True if patched."""
    search_uri, search_label = _term_match_values(term_dict, old_term)
    new_uri = (term_dict.get('uri') or '').strip()
    new_label = (term_dict.get('label') or '').strip()

    fresh_pkg = load_fresh_package(pkg['id'], fallback=pkg)
    patch_payload = {}

    for field_name, cfg in _FIELD_MAP.items():
        entries = parse_composite(fresh_pkg.get(field_name))
        changed = False

        for entry in entries:
            if not _entry_matches_term(entry, cfg, search_uri, search_label):
                continue

            if new_label and (entry.get(cfg['name_key']) or '').strip() != new_label:
                entry[cfg['name_key']] = new_label
                changed = True
            if new_uri and (entry.get(cfg['identifier_key']) or '').strip() != new_uri:
                entry[cfg['identifier_key']] = new_uri
                changed = True

        if changed:
            patch_payload[field_name] = json.dumps(entries)

    if not patch_payload:
        return False

    patch_package(pkg['id'], patch_payload)
    log.info('Propagated term=%s to %s (fields: %s)',
             new_label, pkg['id'], ', '.join(patch_payload))
    return True


def term_to_entry(term_dict, field_name):
    """Build a composite entry dict from a taxonomy term.

    Returns None if *field_name* is not in the field map.
    """
    cfg = _FIELD_MAP.get(field_name)
    if cfg is None:
        return None
    return {
        cfg['name_key']: term_dict.get('label') or '',
        cfg['identifier_key']: term_dict.get('uri') or '',
        cfg['identifier_type_key']: 'URL',
    }
