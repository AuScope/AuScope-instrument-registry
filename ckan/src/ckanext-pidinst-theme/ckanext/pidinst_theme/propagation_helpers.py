"""Shared low-level helpers for party and taxonomy propagation."""

import json
import logging

import ckan.plugins.toolkit as toolkit

log = logging.getLogger(__name__)


def parse_composite(raw):
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


def search_instruments():
    """Return all instrument packages via package_search."""
    try:
        return toolkit.get_action('package_search')({'ignore_auth': True}, {
            'q': '*:*', 'fq': 'dataset_type:instrument', 'rows': 10000,
        }).get('results', [])
    except Exception:
        log.exception('package_search failed')
        return []


def load_fresh_package(pkg_id, fallback=None):
    """Load a package via package_show, with fallback on error."""
    try:
        return toolkit.get_action('package_show')(
            {'ignore_auth': True}, {'id': pkg_id}
        )
    except Exception:
        log.warning('package_show failed for %s; using fallback', pkg_id)
        return fallback if fallback is not None else {}


def patch_package(pkg_id, payload):
    """Issue a package_patch for the given package."""
    toolkit.get_action('package_patch')(
        {'ignore_auth': True}, {**payload, 'id': pkg_id}
    )


def run_propagation(instruments, update_fn, entity_label):
    """Execute propagation over *instruments*, return summary dict."""
    log.info('Propagation START for %s: %d instrument(s)',
             entity_label, len(instruments))
    summary = {
        'instruments_checked': len(instruments),
        'instruments_updated': 0,
        'failures': [],
    }
    for pkg in instruments:
        try:
            if update_fn(pkg):
                summary['instruments_updated'] += 1
        except Exception as exc:
            pkg_id = pkg.get('id', '?')
            log.error('Propagation FAILED for %s (%s): %s',
                      pkg_id, entity_label, exc)
            summary['failures'].append({'id': pkg_id, 'error': str(exc)})
    log.info('Propagation END for %s: updated=%d, failures=%d',
             entity_label, summary['instruments_updated'],
             len(summary['failures']))
    return summary
