"""Server-side party tree cache.

Extracted into its own module so it can be imported by both views.py
(cache population) and logic/action.py (invalidation) without creating
circular imports.
"""

import time

_cache = {}
_PARTY_CACHE_TTL = 300  # seconds

_version = 0  # incremented on every invalidation


def cache_get(key):
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _PARTY_CACHE_TTL:
        return entry[1]
    return None


def cache_set(key, value):
    _cache[key] = (time.time(), value)


def invalidate():
    """Clear the party tree cache.  Call after any party create/update/delete."""
    global _version
    _cache.clear()
    _version += 1


def get_version():
    """Return the current cache version number.

    Increments on every invalidation; clients can use this to detect
    when their cached copy is stale.
    """
    return _version
