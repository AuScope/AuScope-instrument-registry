"""Shared low-level helpers for party and taxonomy propagation."""

import json
import logging
import threading
import time
import uuid
from datetime import datetime

import ckan.plugins.toolkit as toolkit

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Job registry – database-backed progress tracking
#
# Job state is stored in CKAN's ``task_status`` table so that any worker
# process can read the progress of a job started on another worker.  An
# in-process write-through cache keyed by entity_key avoids issuing a DB
# query on every progress poll from the same worker.
#
# NOTE: ``task_status`` is a core CKAN model table that exists in every
# deployment, so no migration is needed.
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
# Maps entity_key -> job_id for same-process lookups (avoids one DB round-trip).
_entity_to_job_cache: dict = {}

# Jobs are cleaned up this many seconds after they finish.
_JOB_TTL = 120

_TASK_TYPE = 'pidinst_propagation'


def _task_id(job_id: str) -> str:
    """Stable task_status entity_id for a propagation job."""
    return f'propagation:{job_id}'


def _write_task(job_id: str, state_dict: dict) -> None:
    """Persist *state_dict* to task_status (upsert)."""
    import ckan.model as model
    from ckan.model import TaskStatus
    task_id = _task_id(job_id)
    task = (model.Session.query(TaskStatus)
            .filter_by(id=task_id).first())
    if task is None:
        task = TaskStatus(
            id=task_id,
            entity_id=job_id,
            entity_type='propagation_job',
            task_type=_TASK_TYPE,
            key='state',
        )
        model.Session.add(task)
    task.value = json.dumps(state_dict)
    task.state = state_dict.get('status', 'pending')
    task.last_updated = datetime.utcnow()
    try:
        model.Session.commit()
    except Exception:
        model.Session.rollback()
        log.exception('task_status write failed for job %s', job_id)


def _read_task(job_id: str) -> dict | None:
    """Read job state from task_status, or None if not found."""
    import ckan.model as model
    from ckan.model import TaskStatus
    task = (model.Session.query(TaskStatus)
            .filter_by(id=_task_id(job_id)).first())
    if task is None:
        return None
    try:
        return json.loads(task.value)
    except (json.JSONDecodeError, TypeError):
        return None


def _delete_task(job_id: str) -> None:
    """Remove the task_status row for a finished job."""
    import ckan.model as model
    from ckan.model import TaskStatus
    try:
        (model.Session.query(TaskStatus)
         .filter_by(id=_task_id(job_id))
         .delete(synchronize_session=False))
        model.Session.commit()
    except Exception:
        model.Session.rollback()
        log.warning('task_status delete failed for job %s', job_id)


def job_create(entity_key: str) -> str:
    """Create a new propagation job. Returns the job_id string.

    Call this *before* starting the background thread so the polling
    endpoint can return a 'pending' status immediately.
    Job state is written to the ``task_status`` table so every worker
    process can observe it.
    """
    job_id = str(uuid.uuid4())
    state = {
        'status': 'pending',
        'job_id': job_id,
        'entity_key': entity_key,
        'total': None,
        'done': 0,
        'updated': 0,
        'failures': 0,
        'created_at': time.time(),
        'finished_at': None,
    }
    _write_task(job_id, state)
    with _cache_lock:
        _entity_to_job_cache[entity_key] = job_id
    log.info('job_create: entity_key=%r job_id=%s', entity_key, job_id)
    return job_id


def _update_task_field(job_id: str, **fields) -> None:
    """Read-modify-write a subset of fields in the persisted job state."""
    state = _read_task(job_id)
    if state is None:
        return
    state.update(fields)
    _write_task(job_id, state)


def job_set_total(job_id: str, total: int) -> None:
    """Called once the total instrument count is known."""
    _update_task_field(job_id, total=total, status='running')


def job_tick(job_id: str, updated: bool) -> None:
    """Record one processed instrument."""
    state = _read_task(job_id)
    if state is None:
        return
    state['done'] = state.get('done', 0) + 1
    if updated:
        state['updated'] = state.get('updated', 0) + 1
    _write_task(job_id, state)


def job_fail(job_id: str) -> None:
    """Record one failed instrument."""
    state = _read_task(job_id)
    if state is None:
        return
    state['failures'] = state.get('failures', 0) + 1
    _write_task(job_id, state)


def job_finish(job_id: str) -> None:
    """Mark the job as done."""
    _update_task_field(job_id, status='done', finished_at=time.time())


def _find_job_id_by_entity_key(entity_key: str) -> str | None:
    """Scan ``task_status`` for the most recent non-expired propagation job
    that matches *entity_key*.

    Used as a DB fallback when the in-process cache misses (e.g. after a
    Werkzeug reloader restart or on a different gunicorn worker).
    """
    import ckan.model as model
    from ckan.model import TaskStatus
    try:
        tasks = (
            model.Session.query(TaskStatus)
            .filter_by(entity_type='propagation_job', task_type=_TASK_TYPE, key='state')
            .order_by(TaskStatus.last_updated.desc())
            .limit(50)
            .all()
        )
        now = time.time()
        for task in tasks:
            try:
                state = json.loads(task.value)
            except (json.JSONDecodeError, TypeError):
                continue
            if state.get('entity_key') != entity_key:
                continue
            # Skip jobs that have already expired.
            if (
                state.get('status') == 'done'
                and state.get('finished_at')
                and (now - state['finished_at']) > _JOB_TTL
            ):
                continue
            log.debug(
                '_find_job_id_by_entity_key: found job %s (status=%s) for %r via DB scan',
                task.entity_id, state.get('status'), entity_key,
            )
            return task.entity_id
    except Exception:
        log.exception('_find_job_id_by_entity_key: DB scan failed for entity_key=%r', entity_key)
    return None


def job_get_by_entity(entity_key: str) -> dict | None:
    """Return a snapshot of the job for *entity_key*, or None.

    First consults the same-process cache to find the job_id, then falls
    back to a ``task_status`` DB scan so that progress polls on any worker
    (or after a reloader restart) can still find jobs started by a
    different process.  Expired (done + TTL elapsed) jobs are cleaned up
    lazily.
    """
    with _cache_lock:
        job_id = _entity_to_job_cache.get(entity_key)

    if not job_id:
        # Cache miss – try the DB so multi-worker / reloader scenarios work.
        job_id = _find_job_id_by_entity_key(entity_key)
        if job_id:
            with _cache_lock:
                _entity_to_job_cache[entity_key] = job_id
        else:
            log.debug('job_get_by_entity: no job found for entity_key=%r', entity_key)
            return None

    state = _read_task(job_id)
    if state is None:
        with _cache_lock:
            _entity_to_job_cache.pop(entity_key, None)
        return None

    # Lazy TTL cleanup
    if (state.get('status') == 'done'
            and state.get('finished_at')
            and (time.time() - state['finished_at']) > _JOB_TTL):
        _delete_task(job_id)
        with _cache_lock:
            _entity_to_job_cache.pop(entity_key, None)
        return None

    return state


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


_SEARCH_PAGE_SIZE = 500


def search_instruments():
    """Return all instrument packages via paginated package_search.

    Fetches in pages of ``_SEARCH_PAGE_SIZE`` records so that the function
    remains correct as the registry grows beyond a few thousand instruments,
    rather than relying on a fixed ``rows=10000`` cap.
    """
    results = []
    start = 0
    action = toolkit.get_action('package_search')
    ctx = {'ignore_auth': True}
    try:
        while True:
            page = action(ctx, {
                'q': '*:*',
                'fq': 'dataset_type:instrument',
                'rows': _SEARCH_PAGE_SIZE,
                'start': start,
            })
            batch = page.get('results', [])
            results.extend(batch)
            if len(results) >= page.get('count', 0) or not batch:
                break
            start += len(batch)
    except Exception:
        log.exception('package_search failed (fetched %d so far)', len(results))
    return results


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


def run_propagation(instruments, update_fn, entity_label, job_id=None):
    """Execute propagation over *instruments*, return summary dict."""
    log.info('Propagation START for %s: %d instrument(s)',
             entity_label, len(instruments))

    if job_id:
        job_set_total(job_id, len(instruments))

    summary = {
        'instruments_checked': len(instruments),
        'instruments_updated': 0,
        'failures': [],
    }
    for pkg in instruments:
        updated = False
        try:
            updated = update_fn(pkg)
            if updated:
                summary['instruments_updated'] += 1
        except Exception as exc:
            pkg_id = pkg.get('id', '?')
            log.error('Propagation FAILED for %s (%s): %s',
                      pkg_id, entity_label, exc)
            summary['failures'].append({'id': pkg_id, 'error': str(exc)})
            if job_id:
                job_fail(job_id)
        finally:
            if job_id:
                job_tick(job_id, updated=updated)

    if job_id:
        job_finish(job_id)

    log.info('Propagation END for %s: updated=%d, failures=%d',
             entity_label, summary['instruments_updated'],
             len(summary['failures']))
    return summary
