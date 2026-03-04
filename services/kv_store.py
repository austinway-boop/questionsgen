"""
Storage abstraction: Neon Postgres when DATABASE_URL is set,
local JSON file fallback for development.
"""

import json
import os
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

USE_DB = bool(os.environ.get("DATABASE_URL"))

# ---------------------------------------------------------------------------
# Postgres backend (Neon)
# ---------------------------------------------------------------------------

_pool = None
_db_init_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _db_init_lock:
            if _pool is None:
                import psycopg2.pool
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    1, 10,
                    os.environ["DATABASE_URL"],
                )
                _init_table()
    return _pool


def _init_table():
    conn = _pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL
                )
            """)
        conn.commit()
    finally:
        _pool.putconn(conn)


def _db_get(key: str):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        pool.putconn(conn)


def _db_set(key: str, value):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kv_store (key, value) VALUES (%s, %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (key, json.dumps(value)),
            )
        conn.commit()
    finally:
        pool.putconn(conn)


def _db_delete(key: str):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kv_store WHERE key = %s", (key,))
        conn.commit()
    finally:
        pool.putconn(conn)


def _db_keys(prefix: str) -> list:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT key FROM kv_store WHERE key LIKE %s", (prefix + "%",))
            return [row[0] for row in cur.fetchall()]
    finally:
        pool.putconn(conn)


def _db_get_namespace(namespace: str) -> dict:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT key, value FROM kv_store WHERE key LIKE %s",
                (namespace + ":%",),
            )
            result = {}
            for key, value in cur.fetchall():
                sub = key.split(":", 1)[1] if ":" in key else key
                result[sub] = value
            return result
    finally:
        pool.putconn(conn)


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
    with _lock_for(namespace):
        return _json_load(namespace)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get(key: str):
    """Get a value by key (e.g. 'skill:U1S1')."""
    if USE_DB:
        return _db_get(key)
    return _json_get(key)


def set(key: str, value):  # noqa: A001
    """Set a value by key."""
    if USE_DB:
        _db_set(key, value)
    else:
        _json_set(key, value)


def delete(key: str):
    """Delete a key."""
    if USE_DB:
        _db_delete(key)
    else:
        _json_delete(key)


def keys(prefix: str) -> list:
    """List all keys with a given prefix (e.g. 'skill:')."""
    if USE_DB:
        return _db_keys(prefix)
    return _json_keys(prefix)


def get_namespace(namespace: str) -> dict:
    """Get all entries in a namespace as {sub_key: value}."""
    if USE_DB:
        return _db_get_namespace(namespace)
    return _json_get_all(namespace)


def set_in_namespace(namespace: str, sub_key: str, value):
    """Set a single entry in a namespace. Thread-safe for JSON mode."""
    set(f"{namespace}:{sub_key}", value)


def get_from_namespace(namespace: str, sub_key: str):
    """Get a single entry from a namespace."""
    return get(f"{namespace}:{sub_key}")
