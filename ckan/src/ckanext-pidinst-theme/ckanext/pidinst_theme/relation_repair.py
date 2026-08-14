"""Reconcile child-side IsPartOf rows from authoritative HasPart claims."""
import json
import logging
from dataclasses import dataclass, field

import ckan.plugins.toolkit as tk

from ckanext.pidinst_theme import relation_sync


log = logging.getLogger(__name__)


@dataclass
class RepairPlan:
    new_rows: list
    actions: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)

    @property
    def changed(self):
        return any(action['action'] in ('fix', 'create', 'remove') for action in self.actions)


@dataclass
class RepairReport:
    records: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    fixed: int = 0
    created: int = 0
    removed: int = 0
    unchanged: int = 0
    unresolved: int = 0
    reexported: int = 0
    reexport_failed: int = 0
    dry_run: bool = False

    def add_record(self, pkg, plan):
        counts = {
            name: sum(1 for item in plan.actions if item['action'] == name)
            for name in ('fix', 'create', 'remove', 'unchanged')
        }
        self.fixed += counts['fix']
        self.created += counts['create']
        self.removed += counts['remove']
        self.unchanged += counts['unchanged']
        self.unresolved += len(plan.unresolved)
        record = {
            'id': pkg.get('id'),
            'name': pkg.get('name'),
            'title': pkg.get('title'),
            'changed': plan.changed,
            'counts': counts,
            'actions': plan.actions,
            'unresolved': plan.unresolved,
        }
        self.records.append(record)
        return record

    def to_dict(self):
        return {
            'dry_run': self.dry_run,
            'totals': {
                'fixed': self.fixed,
                'created': self.created,
                'removed': self.removed,
                'unchanged': self.unchanged,
                'unresolved': self.unresolved,
                'reexported': self.reexported,
                'reexport_failed': self.reexport_failed,
            },
            'records': self.records,
            'failures': self.failures,
        }


def build_hasPart_index(instrument_pkgs):
    """Return child -> parent -> package for active HasPart claims.

    Private parents are intentionally included. Unlike live sync, repair is an
    explicit operator action and must not mistake a private survey for an orphan.
    """
    index = {}
    for parent in instrument_pkgs:
        if parent.get('state', 'active') != 'active' or parent.get('deleted'):
            continue
        parent_id = parent.get('id')
        if not parent_id:
            continue
        for row in relation_sync._parse_rel_list(parent.get('related_identifier_obj')):
            if not isinstance(row, dict) or row.get('relation_type') != 'HasPart':
                continue
            child_id = (row.get('related_instrument_package_id') or '').strip()
            if child_id:
                index.setdefault(child_id, {})[parent_id] = parent
    return index


def plan_record(child_pkg, expected_parents):
    """Purely plan reconciliation of one package's IsPartOf rows."""
    rows = relation_sync._parse_rel_list(child_pkg.get('related_identifier_obj'))
    new_rows = []
    actions = []
    unresolved = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict) or row.get('relation_type') != 'IsPartOf':
            new_rows.append(row)
            continue

        parent_id = (row.get('related_instrument_package_id') or '').strip()
        # An IsPartOf without a package id is user-entered metadata, not an
        # internal instrument reciprocal. It is outside the repair's scope.
        if not parent_id:
            new_rows.append(row)
            continue
        parent = expected_parents.get(parent_id)
        if parent is None:
            actions.append({'action': 'remove', 'parent_id': parent_id})
            continue
        if parent_id in seen:
            actions.append({'action': 'remove', 'parent_id': parent_id, 'reason': 'duplicate'})
            continue
        seen.add(parent_id)

        canonical = relation_sync._reciprocal_row(parent, parent_id)
        if canonical is None:
            new_rows.append(row)
            unresolved.append({'parent_id': parent_id, 'reason': 'identifier_unresolved'})
        elif relation_sync._reciprocal_matches(row, canonical):
            new_rows.append(row)
            actions.append({'action': 'unchanged', 'parent_id': parent_id})
        else:
            new_rows.append(canonical)
            actions.append({'action': 'fix', 'parent_id': parent_id})

    for parent_id, parent in expected_parents.items():
        if parent_id in seen:
            continue
        canonical = relation_sync._reciprocal_row(parent, parent_id)
        if canonical is None:
            unresolved.append({'parent_id': parent_id, 'reason': 'identifier_unresolved'})
            continue
        new_rows.append(canonical)
        actions.append({'action': 'create', 'parent_id': parent_id})

    return RepairPlan(new_rows=new_rows, actions=actions, unresolved=unresolved)


def apply_plan(ctx, child_pkg, plan, dry_run=False):
    """Apply a plan under the reciprocal-sync recursion guard."""
    if dry_run or not plan.changed:
        return False
    patch_ctx = relation_sync._sync_context()
    patch_ctx.update(ctx or {})
    patch_ctx[relation_sync._SYNCING_RELATIONS] = True
    tk.get_action('package_patch')(patch_ctx, {
        'id': child_pkg['id'],
        'related_identifier_obj': json.dumps(plan.new_rows),
    })
    return True


def reexport_to_datacite(child_pkg):
    """Re-export a changed package if it has a published system DOI."""
    from ckanext.doi.lib.api import DataciteClient
    from ckanext.doi.lib.metadata import build_metadata_dict, build_xml_dict
    from ckanext.doi.model.crud import DOIQuery

    doi_record = DOIQuery.read_package(child_pkg['id'])
    if doi_record is None or doi_record.published is None:
        return False
    current_pkg = tk.get_action('package_show')(
        {'ignore_auth': True}, {'id': child_pkg['id']}
    )
    DataciteClient().set_metadata(
        doi_record.identifier,
        build_xml_dict(build_metadata_dict(current_pkg)),
    )
    return True


def _load_instruments(ctx, page_size=100):
    packages = []
    start = 0
    while True:
        result = tk.get_action('package_search')(ctx, {
            'q': '*:*', 'fq': 'type:instrument', 'rows': page_size, 'start': start,
        })
        page = result.get('results', [])
        packages.extend(page)
        start += len(page)
        if not page or start >= result.get('count', start):
            break
    return packages


def run_repair(ids=None, limit=None, dry_run=False, reexport=True, context=None):
    """Plan and optionally apply catalogue-wide IsPartOf reconciliation."""
    ctx = {'ignore_auth': True}
    ctx.update(context or {})
    packages = _load_instruments(ctx)
    haspart_index = build_hasPart_index(packages)
    selected = packages
    if ids:
        wanted = set(ids)
        selected = [p for p in packages if p.get('id') in wanted or p.get('name') in wanted]
    if limit is not None:
        selected = selected[:limit]

    report = RepairReport(dry_run=dry_run)
    for child in selected:
        plan = plan_record(child, haspart_index.get(child.get('id'), {}))
        record = report.add_record(child, plan)
        if not plan.changed:
            continue
        try:
            apply_plan(ctx, child, plan, dry_run=dry_run)
        except Exception as exc:
            message = str(exc)
            record['apply_error'] = message
            report.failures.append({'id': child.get('id'), 'stage': 'apply', 'error': message})
            continue
        if dry_run or not reexport:
            continue
        try:
            if reexport_to_datacite(child):
                report.reexported += 1
        except Exception as exc:
            message = str(exc)
            report.reexport_failed += 1
            record['reexport_error'] = message
            report.failures.append({'id': child.get('id'), 'stage': 'reexport', 'error': message})
            log.exception('DataCite re-export failed for %s', child.get('id'))
    return report
