# -*- coding: utf-8 -*-
"""SQLite 连接与建表。

并发模型
--------
- 每线程一个连接（``threading.local``），``check_same_thread=False`` 不需要。
- 写操作用全局 ``WRITE_LOCK`` 串行化，配合 WAL 保证读不被写阻塞。
- 所有时间戳统一 ``YYYY-MM-DD HH:MM:SS``（本地时区），便于 SQL 比较与前端展示。
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from . import settings as settings_mod

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    source      TEXT NOT NULL DEFAULT 'manual',
    is_active   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id      INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    qtype          TEXT NOT NULL,
    title          TEXT NOT NULL,
    original_title TEXT,
    options_json   TEXT NOT NULL DEFAULT '[]',
    answer_json    TEXT NOT NULL,
    canonical_key  TEXT NOT NULL,
    legacy_key     TEXT,
    source         TEXT NOT NULL DEFAULT 'manual',
    verified       INTEGER NOT NULL DEFAULT 0,
    hit_count      INTEGER NOT NULL DEFAULT 0,
    last_hit_at    TEXT,
    note           TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE(course_id, canonical_key)
);
CREATE INDEX IF NOT EXISTS idx_q_course_type ON questions(course_id, qtype);
CREATE INDEX IF NOT EXISTS idx_q_legacy      ON questions(legacy_key);
CREATE INDEX IF NOT EXISTS idx_q_title       ON questions(course_id, title);

CREATE TABLE IF NOT EXISTS answer_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id        TEXT NOT NULL,
    ts                TEXT NOT NULL,
    protocol          TEXT NOT NULL,
    course_id         INTEGER,
    qtype             TEXT,
    title             TEXT NOT NULL,
    options_json      TEXT,
    hit_source        TEXT NOT NULL,
    answer            TEXT,
    matched_qid       INTEGER,
    similarity        REAL,
    model_id          TEXT,
    model_name        TEXT,
    reasoning         INTEGER NOT NULL DEFAULT 0,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_cny          REAL NOT NULL DEFAULT 0,
    latency_ms        INTEGER NOT NULL DEFAULT 0,
    images_count      INTEGER NOT NULL DEFAULT 0,
    success           INTEGER NOT NULL DEFAULT 1,
    error             TEXT,
    remote_addr       TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_ts     ON answer_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_log_source ON answer_logs(hit_source);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_local = threading.local()
WRITE_LOCK = threading.RLock()
_db_path: Optional[str] = None


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db_path() -> str:
    global _db_path
    if _db_path is None:
        _db_path = os.path.join(settings_mod.ensure_data_dir(), "bank.db")
    return _db_path


def set_db_path(path: str) -> None:
    """测试用：切换数据库文件并重置连接。"""
    global _db_path
    _db_path = path
    _local.__dict__.clear()


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    path = db_path()
    if conn is not None and getattr(_local, "path", None) == path:
        return conn
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    _local.conn = conn
    _local.path = path
    return conn


def close_thread_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None


@contextmanager
def write() -> Iterator[sqlite3.Connection]:
    """写事务：全局锁 → BEGIN IMMEDIATE → commit/rollback。"""
    conn = connect()
    with WRITE_LOCK:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")


def query(sql: str, params: Any = ()) -> List[sqlite3.Row]:
    return connect().execute(sql, params).fetchall()


def query_one(sql: str, params: Any = ()) -> Optional[sqlite3.Row]:
    return connect().execute(sql, params).fetchone()


def scalar(sql: str, params: Any = (), default: Any = 0) -> Any:
    row = query_one(sql, params)
    if row is None:
        return default
    value = row[0]
    return default if value is None else value


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def meta_get(key: str, default: Optional[str] = None) -> Optional[str]:
    row = query_one("SELECT value FROM meta WHERE key = ?", (key,))
    return row["value"] if row else default


def meta_set(key: str, value: str) -> None:
    with write() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def init_db() -> str:
    """建表 + 完整性检查。返回 'ok' 或 'recovered'。"""
    path = db_path()
    state = "ok"
    try:
        conn = connect()
        conn.executescript(SCHEMA_SQL)
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if row and str(row[0]).lower() != "ok":
            raise sqlite3.DatabaseError(f"integrity_check: {row[0]}")
    except sqlite3.DatabaseError:
        # 损坏：备份后重建空库
        close_thread_conn()
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        try:
            os.replace(path, f"{path}.corrupt-{stamp}")
        except OSError:
            pass
        for suffix in ("-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except OSError:
                pass
        conn = connect()
        conn.executescript(SCHEMA_SQL)
        state = "recovered"

    version = meta_get("schema_version")
    if version is None:
        meta_set("schema_version", str(SCHEMA_VERSION))
    return state