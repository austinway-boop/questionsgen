"""
Storage abstraction: Upstash Redis (Vercel KV) when KV_REST_API_URL is set,
local JSON file fallback for development.
"""

import json
import os
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

USE_KV = bool(os.environ.get("KV_REST_API_URL"))

# ---------------------------------------------------------------------------
# Upstash Redis backend
# ---------------------------------------------------------------------------

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        from upstash_redis import Redis
        _redis = Redis(
            url=os.environ["KV_REST_API_URL"],
            token=os.environ["KV_REST_API_TOKEN"],
        )
    return _redis


def _kv_get(key: str):
    val = _get_redis().get(key)
    if val is None:
        return None
    if isinstance(val, str):
        return json.loads(val)
    return val


def _kv_set(key: str, value):
    _get_redis().set(key, json.dumps(value))


def _kv_delete(key: str):
    _get_redis().delete(key)


def _kv_keys(prefix: str) -> list:
    """Return all keys matching prefix*. Uses SCAN to avoid blocking."""
    r = _get_redis()
    cursor = 0
    result = []
    while True:
        cursor, keys = r.scan(cursor, match=f"{prefix}*", count=500)
        result.extend(keys)
        if cursor == 0:
            break
    return result


# ---------------------------------------------------------------------------
# JSON file backend (local development)
# ---------------------------------------------------------------------------

_json_locks = {}
_meta_lock = threading.Lock()


def _lock_for(namespace: str) -> threading.Lock:
    with _meta_lock:
        if namespace not in _json_locks:
            _json_locks[namespace] = threading.Lock()
        return _json_locks[namespace]


def _json_path(namespace: str) -> Path:
    mapping = {
        "skill": _ROOT / "skill_data.json",
        "bank": _ROOT / "question_bank.json",
    }
    return mapping.get(namespace, _ROOT / f"{namespace}.json")


def _json_load(namespace: str) -> dict:
    p = _json_path(namespace)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _json_save(namespace: str, data: dict):
    _json_path(namespace).write_text(json.dumps(data, indent=2))


def _json_get(key: str):
    ns, _, sub = key.partition(":")
    with _lock_for(ns):
        data = _json_load(ns)
        return data.get(sub)


def _json_set(key: str, value):
    ns, _, sub = key.partition(":")
    with _lock_for(ns):
        data = _json_load(ns)
        data[sub] = value
        _json_save(ns, data)


def _json_delete(key: str):
    ns, _, sub = key.partition(":")
    with _lock_for(ns):
        data = _json_load(ns)
        data.pop(sub, None)
        _json_save(ns, data)


def _json_keys(prefix: str) -> list:
    ns, _, sub_prefix = prefix.partition(":")
    data = _json_load(ns)
    return [f"{ns}:{k}" for k in data if k.startswith(sub_prefix)]


def _json_get_all(namespace: str) -> dict:
    """Get the entire namespace dict (JSON-only convenience)."""
    with _lock_for(namespace):
        return _json_load(namespace)


def _json_set_all(namespace: str, data: dict):
    """Set the entire namespace dict (JSON-only convenience)."""
    with _lock_for(namespace):
        _json_save(namespace, data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get(key: str):
    """Get a value by key (e.g. 'skill:U1S1')."""
    if USE_KV:
        return _kv_get(key)
    return _json_get(key)


def set(key: str, value):  # noqa: A001
    """Set a value by key."""
    if USE_KV:
        _kv_set(key, value)
    else:
        _json_set(key, value)


def delete(key: str):
    """Delete a key."""
    if USE_KV:
        _kv_delete(key)
    else:
        _json_delete(key)


def keys(prefix: str) -> list:
    """List all keys with a given prefix (e.g. 'skill:')."""
    if USE_KV:
        return _kv_keys(prefix)
    return _json_keys(prefix)


def get_namespace(namespace: str) -> dict:
    """Get all entries in a namespace as {sub_key: value}.
    For KV, scans all keys with the namespace prefix.
    For JSON, returns the full file dict.
    """
    if USE_KV:
        result = {}
        for key in _kv_keys(f"{namespace}:"):
            sub = key.split(":", 1)[1] if ":" in key else key
            result[sub] = _kv_get(key)
        return result
    return _json_get_all(namespace)


def set_in_namespace(namespace: str, sub_key: str, value):
    """Set a single entry in a namespace. Thread-safe for JSON mode."""
    set(f"{namespace}:{sub_key}", value)


def get_from_namespace(namespace: str, sub_key: str):
    """Get a single entry from a namespace."""
    return get(f"{namespace}:{sub_key}")
