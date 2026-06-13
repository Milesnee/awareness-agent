"""主动推送调度器（R0/M2）—— 晨/晚觉察引导 + 周日晚周报。

通道策略（微信服务号约束）：
- 客服消息：仅限用户最近 48h 内有互动（昨天聊过今天就能推 → 与 streak 习惯天然契合）
- 超出 48h 窗口的断签用户：跳过并记录，待 R3 接入「订阅通知」召回（占位 TODO）

实现：asyncio 常驻循环（app startup 启动），每分钟检查到点用户。
晨/晚开场白由 awareness_guide 原语生成（round=1 suggested_question），
周报由 awareness_pattern_review 原语 + LLM 摘要生成。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time

from . import llm, store, wechat
from .orchestrator import run_primitive

log = logging.getLogger("scheduler")

MORNING_HOUR = 8       # 默认推送时点（R3 做用户级偏好设置）
EVENING_HOUR = 21
WEEKLY_DOW, WEEKLY_HOUR = 6, 20   # 周日 20:00
WINDOW_48H = 48 * 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS push_log (
  user_id TEXT NOT NULL,
  date TEXT NOT NULL,
  slot TEXT NOT NULL,             -- morning / evening / weekly
  status TEXT NOT NULL,           -- sent / skipped_window / failed
  ts REAL NOT NULL,
  PRIMARY KEY (user_id, date, slot)
);
"""


def _ensure_schema() -> None:
    store._conn().executescript(SCHEMA)


def _due_slot(now: dt.datetime) -> str | None:
    if now.hour == MORNING_HOUR:
        return "morning"
    if now.hour == EVENING_HOUR:
        return "evening"
    if now.weekday() == WEEKLY_DOW and now.hour == WEEKLY_HOUR:
        return "weekly"
    return None


def _all_users() -> list[tuple[str, str, float]]:
    return store._conn().execute(
        "SELECT openid, user_id, COALESCE(last_active, created_at) FROM users").fetchall()


def _already_pushed(user_id: str, date: str, slot: str) -> bool:
    return store._conn().execute(
        "SELECT 1 FROM push_log WHERE user_id=? AND date=? AND slot=?",
        (user_id, date, slot)).fetchone() is not None


def _log_push(user_id: str, date: str, slot: str, status: str) -> None:
    store._conn().execute(
        "INSERT OR REPLACE INTO push_log(user_id, date, slot, status, ts) VALUES (?,?,?,?,?)",
        (user_id, date, slot, status, time.time()))


async def _morning_evening_text(user_id: str, period: str, date: str) -> str:
    try:
        guide = await asyncio.to_thread(run_primitive, "awareness_guide", {
            "user_id": user_id, "period": period, "round": 1, "date": date,
        })
        q = guide.get("suggested_question", "")
        if q:
            return q
    except Exception as e:  # noqa: BLE001
        log.warning("guide for push failed user=%s: %s", user_id, e)
    return ("早上好 🌅 今天打算把注意力放在哪件事上？" if period == "morning"
            else "晚上好 🌙 回顾今天，有哪个瞬间你完全沉浸在做的事里？")


WEEKLY_PROMPT = """你是觉察助手小澄。基于以下周度模式分析数据（JSON），给用户写一段周报，要求：
口语化、温暖不油腻、≤200字；包含：1)本周一个具体的成长信号 2)一个被看见的模式（不评判）
3)下周一个最小调整建议（一句话）。不出现JSON字段名，不说教。"""


async def _weekly_text(user_id: str) -> str | None:
    try:
        review = await asyncio.to_thread(run_primitive, "awareness_pattern_review",
                                         {"user_id": user_id, "timespan": "7d"})
    except Exception as e:  # noqa: BLE001
        log.warning("pattern_review failed user=%s: %s", user_id, e)
        return None
    if not review or review.get("available") is False:
        return None
    try:
        return await llm.chat([
            {"role": "system", "content": WEEKLY_PROMPT},
            {"role": "user", "content": json.dumps(review, ensure_ascii=False)},
        ])
    except llm.LLMError:
        return None


async def tick(now: dt.datetime | None = None) -> int:
    """单次检查（可被测试直接调用）。返回成功推送数。"""
    _ensure_schema()
    now = now or dt.datetime.now()
    slot = _due_slot(now)
    if not slot:
        return 0
    date = now.strftime("%Y-%m-%d")
    sent = 0
    for openid, user_id, last_active in _all_users():
        if _already_pushed(user_id, date, slot):
            continue
        if time.time() - last_active > WINDOW_48H:
            # TODO(R3): 订阅通知召回断签用户
            _log_push(user_id, date, slot, "skipped_window")
            continue
        if slot == "weekly":
            text = await _weekly_text(user_id)
            if not text:
                _log_push(user_id, date, slot, "skipped_window")
                continue
            text = "📊 你的本周觉察\n\n" + text
        else:
            text = await _morning_evening_text(user_id, slot, date)
        try:
            await wechat.send_text(openid, text)
            _log_push(user_id, date, slot, "sent")
            sent += 1
        except Exception as e:  # noqa: BLE001
            log.error("push failed user=%s: %s", user_id, e)
            _log_push(user_id, date, slot, "failed")
    return sent


async def run_forever() -> None:
    log.info("scheduler started (morning=%d evening=%d weekly=周日%d点)",
             MORNING_HOUR, EVENING_HOUR, WEEKLY_HOUR)
    last_minute = ""
    while True:
        now = dt.datetime.now()
        key = now.strftime("%Y%m%d%H")
        if key != last_minute:
            last_minute = key
            try:
                await tick(now)
            except Exception as e:  # noqa: BLE001
                log.exception("scheduler tick error: %s", e)
        await asyncio.sleep(60)
