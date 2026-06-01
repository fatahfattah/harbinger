import sqlite3
import json
import os
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "cache", "harbinger.db")

TTL_2H = 7200
TTL_12H = 43200
TTL_24H = 86400
TTL_7D = 86400 * 7

_conn = None


def _db():
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def init_db():
    db = _db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS kv_cache (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            expires_at REAL NOT NULL,
            PRIMARY KEY (namespace, key)
        );
        CREATE INDEX IF NOT EXISTS idx_cache_expires ON kv_cache(expires_at);
    """)
    db.commit()


def get(namespace, key):
    row = _db().execute(
        "SELECT value FROM kv_cache WHERE namespace=? AND key=? AND expires_at > ?",
        (namespace, key, time.time())
    ).fetchone()
    return json.loads(row["value"]) if row else None


def set(namespace, key, value, ttl):
    _db().execute(
        "INSERT OR REPLACE INTO kv_cache (namespace, key, value, expires_at) VALUES (?, ?, ?, ?)",
        (namespace, key, json.dumps(value, default=str), time.time() + ttl)
    )
    _db().commit()


def get_or_fetch(namespace, key, ttl, fn):
    cached = get(namespace, key)
    if cached is not None:
        return cached
    value = fn()
    if value is not None:
        set(namespace, key, value, ttl)
    return value


def delete_expired():
    _db().execute("DELETE FROM kv_cache WHERE expires_at < ?", (time.time(),))
    _db().commit()
