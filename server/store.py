"""服务态存储（SQLite，stdlib）。

原语层的 JSON 数据契约保持不变（data/profiles|journals|streaks/{user_id}）；
这里只管服务端状态：openid↔user_id 映射、消息去重、会话轮次、对话历史。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid

from .config import settings

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  openid TEXT PRIMARY KEY,
  user_id TEXT UNIQUE NOT NULL,
  nickname TEXT DEFAULT '',
  created_at REAL NOT NULL,
  last_active REAL
);
CREATE TABLE IF NOT EXISTS seen_msgs (
  msg_id TEXT PRIMARY KEY,
  ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  user_id TEXT PRIMARY KEY,
  period TEXT NOT NULL,
  date TEXT NOT NULL,
  round INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dialog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dialog_user_ts ON dialog(user_id, ts);
"""


def _conn() -> sqlite3.Connection:
    if getattr(_local, "conn", None) is None:
        c = sqlite3.connect(settings.sqlite_path, timeout=10, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=10000")
        c.executescript(SCHEMA)
        _local.conn = c
    return _local.conn


def get_or_create_user(openid: str) -> str:
    c = _conn()
    row = c.execute("SELECT user_id FROM users WHERE openid=?", (openid,)).fetchone()
    if row:
        return row[0]
    user_id = "u_" + uuid.uuid4().hex[:12]
    c.execute("INSERT INTO users(openid, user_id, created_at, last_active) VALUES (?,?,?,?)",
              (openid, user_id, time.time(), time.time()))
    c.commit()
    return user_id


def is_duplicate(msg_id: str) -> bool:
    """微信 5 秒未响应会重试 3 次 → 必须按 MsgId 去重。"""
    if not msg_id:
        return False
    c = _conn()
    try:
        c.execute("INSERT INTO seen_msgs(msg_id, ts) VALUES (?,?)", (msg_id, time.time()))
        c.commit()
        c.execute("DELETE FROM seen_msgs WHERE ts < ?", (time.time() - 600,))
        c.commit()
        return False
    except sqlite3.IntegrityError:
        return True


def bump_round(user_id: str, period: str, date: str) -> int:
    """同一 (date, period) 内轮次自增；跨期重置为 1。"""
    c = _conn()
    row = c.execute("SELECT period, date, round FROM sessions WHERE user_id=?", (user_id,)).fetchone()
    if row and row[0] == period and row[1] == date:
        rnd = row[2] + 1
        c.execute("UPDATE sessions SET round=?, updated_at=? WHERE user_id=?",
                  (rnd, time.time(), user_id))
    else:
        rnd = 1
        c.execute("INSERT OR REPLACE INTO sessions(user_id, period, date, round, updated_at)"
                  " VALUES (?,?,?,?,?)", (user_id, period, date, rnd, time.time()))
    c.commit()
    return rnd


def append_dialog(user_id: str, role: str, content: str) -> None:
    c = _conn()
    c.execute("INSERT INTO dialog(user_id, role, content, ts) VALUES (?,?,?,?)",
              (user_id, role, content, time.time()))
    c.commit()


def recent_dialog(user_id: str, limit: int = 12) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT role, content FROM dialog WHERE user_id=? ORDER BY ts DESC LIMIT ?",
        (user_id, limit)).fetchall()
    return [{"role": r, "content": ct} for r, ct in reversed(rows)]


def dump_user(user_id: str) -> str:
    """调试用。"""
    return json.dumps(recent_dialog(user_id), ensure_ascii=False, indent=2)


def touch_user(user_id: str) -> None:
    _conn().execute("UPDATE users SET last_active=? WHERE user_id=?", (time.time(), user_id))
