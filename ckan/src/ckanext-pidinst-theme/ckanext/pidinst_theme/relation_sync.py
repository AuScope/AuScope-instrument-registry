"""Reciprocal instrument relationship management.

Handles:
  - Publishing: add IsPartOf on each child when parent goes public
  - Delete/withdraw: remove stale reciprocal entries
"""
import json
import logging
import ckan.plugins.toolkit as tk
from ckanext.pidinst_theme import analytics, doi_policy

log = logging.getLogger(__name__)

# Context flag to prevent recursion
_SYNCING_RELATIONS = '_pidinst_syncing_relations'


def _sync_context():
    return {
        'ignore_auth': True,
        _SYNCING_RELATIONS: True,
        '_analytics_update_origin': analytics.UPDATE_ORIGIN_INTERNAL_SYNC,
        '_analytics_is_initialization_update': False,
    }


def _parse_rel_list(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
    return raw if isinstance(raw, list) else []


def _find_reciprocal(child_rels, parent_pkg_id):
    """Return the first IsPartOf row index for ``parent_pkg_id``."""
    for index, r in enumerate(child_rels):
        if not isinstance(r, dict):
            continue
        if r.get('relation_type') == 'IsPartOf' and r.get('related_instrument_package_id') == parent_pkg_id:
            return index
    return None


def _resolve_pkg_identifier(pkg_dict):
    """Return ``(identifier, type, resolution_level)`` for a package."""
    system_doi = doi_policy._system_doi(pkg_dict)
    if doi_policy.is_valid_doi(system_doi):
        return doi_policy.normalize_doi(system_doi), 'DOI', 'doi'

    if doi_policy.is_external_identifier(pkg_dict):
        external_url = doi_policy.get_identifier_url(pkg_dict)
        if doi_policy.is_valid_identifier_url(external_url):
            return external_url, 'URL', 'external'

    package_name = pkg_dict.get('name') or pkg_dict.get('id')
    if package_name:
        try:
            landing_page = tk.url_for(
                'instrument.read', id=package_name, qualified=True
            )
        except Exception:
            landing_page = ''
        if doi_policy.is_valid_identifier_url(landing_page):
            return landing_page, 'URL', 'landing_page'

    return '', '', 'unresolved'


def _reciprocal_row(parent_pkg, parent_id=None):
    """Build the canonical child-side IsPartOf row for ``parent_pkg``."""
    identifier, identifier_type, level = _resolve_pkg_identifier(parent_pkg)
    if level == 'unresolved':
        return None
    return {
        'related_identifier': identifier,
        'related_identifier_type': identifier_type,
        'related_identifier_name': parent_pkg.get('title') or parent_pkg.get('name', ''),
        'related_resource_type': 'Instrument',
        'relation_type': 'IsPartOf',
        'related_instrument_package_id': parent_id or parent_pkg.get('id', ''),
        'instrument_relation_role': 'parent',
    }


def _reciprocal_matches(row, canonical_row):
    """Whether the value-bearing parent fields are already canonical."""
    return all(
        row.get(field_name) == canonical_row.get(field_name)
        for field_name in (
            'related_identifier',
            'related_identifier_type',
            'related_identifier_name',
        )
    )


def _clean_stale_children(ctx, parent_id, current_child_ids):
    """Remove IsPartOf→parent_id from instruments no longer in the parent's HasPart list."""
    try:
        results = tk.get_action('package_search')(ctx, {
            'q': '*:*',
            'fq': 'type:instrument',
            'rows': 1000,
        })
        for pkg in results.get('results', []):
            if pkg['id'] in current_child_ids:
                continue
            rels = _parse_rel_list(pkg.get('related_identifier_obj'))
            cleaned = [
                r for r in rels
                if not (isinstance(r, dict)
                        and r.get('relation_type') == 'IsPartOf'
                        and r.get('related_instrument_package_id') == parent_id)
            ]
            if len(cleaned) != len(rels):
                tk.get_action('package_patch')(ctx, {
                    'id': pkg['id'],
                    'related_identifier_obj': json.dumps(cleaned),
                })
                log.info('Removed stale IsPartOf→%s from %s', parent_id, pkg['id'])
    except Exception:
        log.exception('Failed to clean stale children for parent %s', parent_id)


def sync_publish_reciprocals(context, pkg_dict):
    """When parent is published (public + active), ensure each HasPart child has IsPartOf back.

    Idempotent. Guarded against recursion via context flag.
    """
    if context.get(_SYNCING_RELATIONS):
        return

    # Only act on public, active instruments
    if pkg_dict.get('private') in (True, 'True', 'true'):
        return
    if pkg_dict.get('state') != 'active':
        return

    parent_id = pkg_dict.get('id')
    if not parent_id:
        return

    rel_list = _parse_rel_list(pkg_dict.get('related_identifier_obj'))
    child_ids = []
    current_child_ids = set()
    for r in rel_list:
        if not isinstance(r, dict):
            continue
        if r.get('relation_type') == 'HasPart':
            child_id = r.get('related_instrument_package_id', '').strip()
            if child_id:
                current_child_ids.add(child_id)
                child_ids.append(child_id)

    ctx = _sync_context()
    canonical_row = _reciprocal_row(pkg_dict, parent_id)
    if canonical_row is None:
        log.warning(
            'Skipping reciprocal sync for parent %s: identifier is unresolved',
            parent_id,
        )
        # Identifier resolution only gates additions/corrections. Removal of
        # stale internal rows remains safe and must retain its old behaviour.
        _clean_stale_children(ctx, parent_id, current_child_ids)
        return

    # Add IsPartOf on current children
    for child_id in child_ids:
        try:
            child_pkg = tk.get_action('package_show')(ctx, {'id': child_id})
            child_rels = _parse_rel_list(child_pkg.get('related_identifier_obj'))

            reciprocal_index = _find_reciprocal(child_rels, parent_id)
            if reciprocal_index is None:
                child_rels.append(dict(canonical_row))
            elif _reciprocal_matches(child_rels[reciprocal_index], canonical_row):
                continue
            else:
                child_rels[reciprocal_index] = dict(canonical_row)

            tk.get_action('package_patch')(ctx, {
                'id': child_id,
                'related_identifier_obj': json.dumps(child_rels),
            })
            log.info('Synced IsPartOf to %s on child %s', parent_id, child_id)
        except Exception:
            log.exception('Failed to sync reciprocal IsPartOf on child %s', child_id)

    # Clean stale IsPartOf from former children no longer in HasPart
    _clean_stale_children(ctx, parent_id, current_child_ids)


def cleanup_reciprocals(context, pkg_dict):
    """Remove reciprocal IsPartOf/HasPart entries when an instrument is deleted or withdrawn.

    Called after state change. Idempotent. Guarded against recursion.
    """
    if context.get(_SYNCING_RELATIONS):
        return

    pkg_id = pkg_dict.get('id')
    if not pkg_id:
        return

    rel_list = _parse_rel_list(pkg_dict.get('related_identifier_obj'))
    related_ids = set()
    for r in rel_list:
        if not isinstance(r, dict):
            continue
        rt = r.get('relation_type', '')
        if rt in ('HasPart', 'IsPartOf'):
            rid = r.get('related_instrument_package_id', '').strip()
            if rid:
                related_ids.add(rid)

    if not related_ids:
        return

    ctx = _sync_context()

    for related_id in related_ids:
        try:
            related_pkg = tk.get_action('package_show')(ctx, {'id': related_id})
            related_rels = _parse_rel_list(related_pkg.get('related_identifier_obj'))

            cleaned = [
                r for r in related_rels
                if not (isinstance(r, dict)
                        and r.get('relation_type') in ('HasPart', 'IsPartOf')
                        and r.get('related_instrument_package_id') == pkg_id)
            ]

            if len(cleaned) != len(related_rels):
                tk.get_action('package_patch')(ctx, {
                    'id': related_id,
                    'related_identifier_obj': json.dumps(cleaned),
                })
                log.info('Cleaned reciprocal relations to %s from %s', pkg_id, related_id)
        except tk.ObjectNotFound:
            pass
        except Exception:
            log.exception('Failed to clean reciprocal on %s for %s', related_id, pkg_id)
