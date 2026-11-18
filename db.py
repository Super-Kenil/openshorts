import json
import os
import sqlite3
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_lock = threading.Lock()
_ready = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS live_sessions (
    id TEXT PRIMARY KEY,
    dir TEXT NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_buckets (
    stream TEXT NOT NULL,
    t INTEGER NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (stream, t)
);
CREATE TABLE IF NOT EXISTS chat_spikes (
    stream TEXT NOT NULL,
    onset REAL NOT NULL,
    peak REAL NOT NULL,
    ending REAL NOT NULL,
    ratio REAL NOT NULL,
    count INTEGER NOT NULL,
    found REAL NOT NULL,
    PRIMARY KEY (stream, onset)
);
"""


def path():
    return os.environ.get("OPENSHORTS_DB") or os.path.join(_HERE, "data", "openshorts.db")


def connect():
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    conn = sqlite3.connect(p, timeout=15)
    conn.row_factory = sqlite3.Row
    with _lock:
        if p not in _ready:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
            conn.executescript(SCHEMA)
            conn.commit()
            _ready.add(p)
    return conn


def _run(sql, args=(), many=False):
    conn = connect()
    try:
        with conn:
            if many:
                conn.executemany(sql, args)
            else:
                conn.execute(sql, args)
    finally:
        conn.close()


def _all(sql, args=()):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def get_setting(key, default=None):
    rows = _all("SELECT value FROM settings WHERE key = ?", (key,))
    if not rows:
        return default
    try:
        return json.loads(rows[0]["value"])
    except ValueError:
        return default


def set_setting(key, value):
    _run("INSERT INTO settings(key, value, updated) VALUES(?, ?, ?) "
         "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
         (key, json.dumps(value, ensure_ascii=False), time.time()))


def delete_setting(key):
    _run("DELETE FROM settings WHERE key = ?", (key,))


def all_settings():
    out = {}
    for row in _all("SELECT key, value FROM settings"):
        try:
            out[row["key"]] = json.loads(row["value"])
        except ValueError:
            continue
    return out


def live_registry():
    return {r["id"]: r["dir"] for r in _all("SELECT id, dir FROM live_sessions")}


def live_registry_set(session_id, directory):
    _run("INSERT INTO live_sessions(id, dir, updated) VALUES(?, ?, ?) "
         "ON CONFLICT(id) DO UPDATE SET dir = excluded.dir, updated = excluded.updated",
         (session_id, directory, time.time()))


def live_registry_remove(session_id):
    _run("DELETE FROM live_sessions WHERE id = ?", (session_id,))


def chat_add(stream, counts):
    rows = [(stream, int(t), int(n)) for t, n in counts.items() if n]
    if rows:
        _run("INSERT INTO chat_buckets(stream, t, n) VALUES(?, ?, ?) "
             "ON CONFLICT(stream, t) DO UPDATE SET n = n + excluded.n", rows, many=True)


def chat_replace(stream, counts):
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM chat_buckets WHERE stream = ?", (stream,))
            conn.executemany("INSERT INTO chat_buckets(stream, t, n) VALUES(?, ?, ?)",
                             [(stream, int(t), int(n)) for t, n in counts.items() if n])
    finally:
        conn.close()


def chat_series(stream, start, end):
    rows = _all("SELECT t, n FROM chat_buckets WHERE stream = ? AND t >= ? AND t < ?",
                (stream, int(start), int(end)))
    return {r["t"]: r["n"] for r in rows}


def chat_has(stream):
    return bool(_all("SELECT 1 FROM chat_buckets WHERE stream = ? LIMIT 1", (stream,)))


def chat_spikes_save(stream, spikes):
    rows = [(stream, float(s["onset"]), float(s["peak"]), float(s["end"]),
             float(s["ratio"]), int(s["count"]), time.time()) for s in spikes]
    if rows:
        _run("INSERT OR REPLACE INTO chat_spikes(stream, onset, peak, ending, ratio, count, found) "
             "VALUES(?, ?, ?, ?, ?, ?, ?)", rows, many=True)
