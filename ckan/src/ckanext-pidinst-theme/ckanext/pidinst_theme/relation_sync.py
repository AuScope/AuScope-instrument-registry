"""Reciprocal instrument relationship management.

Handles:
  - Publishing: add IsPartOf on each child when parent goes public
  - Delete/withdraw: remove stale reciprocal entries
"""
import json
import logging
import ckan.plugins.toolkit as tk

log = logging.getLogger(__name__)

# Context flag to prevent recursion
_SYNCING_RELATIONS = '_pidinst_syncing_relations'


def _parse_rel_list(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
    return raw if isinstance(raw, list) else []


def _has_reciprocal(child_rels, parent_pkg_id):
    """Check if child already has IsPartOf pointing to parent."""
    for r in child_rels:
        if not isinstance(r, dict):
            continue
        if r.get('relation_type') == 'IsPartOf' and r.get('related_instrument_package_id') == parent_pkg_id:
            return True
    return False


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
    children = []
    current_child_ids = set()
    for r in rel_list:
        if not isinstance(r, dict):
            continue
        if r.get('relation_type') == 'HasPart':
            child_id = r.get('related_instrument_package_id', '').strip()
            if child_id:
                current_child_ids.add(child_id)
                children.append({
                    'child_id': child_id,
                    'parent_identifier': r.get('related_identifier', ''),
                    'parent_identifier_type': r.get('related_identifier_type', 'URL'),
                    'parent_name': pkg_dict.get('title') or pkg_dict.get('name', ''),
                })

    ctx = {'ignore_auth': True, _SYNCING_RELATIONS: True}

    # Add IsPartOf on current children
    for child_info in children:
        try:
            child_pkg = tk.get_action('package_show')(ctx, {'id': child_info['child_id']})
            child_rels = _parse_rel_list(child_pkg.get('related_identifier_obj'))

            if _has_reciprocal(child_rels, parent_id):
                continue

            child_rels.append({
                'related_identifier': child_info['parent_identifier'],
                'related_identifier_type': child_info['parent_identifier_type'],
                'related_identifier_name': child_info['parent_name'],
                'related_resource_type': 'Instrument',
                'relation_type': 'IsPartOf',
                'related_instrument_package_id': parent_id,
                'instrument_relation_role': 'parent',
            })

            tk.get_action('package_patch')(ctx, {
                'id': child_info['child_id'],
                'related_identifier_obj': json.dumps(child_rels),
            })
            log.info('Added IsPartOf→%s on child %s', parent_id, child_info['child_id'])
        except Exception:
            log.exception('Failed to add reciprocal IsPartOf on child %s', child_info['child_id'])

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

    ctx = {'ignore_auth': True, _SYNCING_RELATIONS: True}

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
