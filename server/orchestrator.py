"""编排层：微信消息 → 原语装配上下文 → LLM 生成 → 结构化提取落库。

原语调用沿用其 JSON-in/JSON-out stdin 契约（subprocess），
对同一用户的处理串行化（asyncio per-user lock），避免并发写 JSON。
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import llm, memory, safety, store
from .config import PROJECT_ROOT, settings

log = logging.getLogger("orchestrator")
SCRIPTS = PROJECT_ROOT / "scripts"

_user_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_pending_finalize: dict[str, tuple[str, str]] = {}


async def maybe_finalize(openid: str) -> None:
    """回复发出后调用：若该用户会话达轮次上限，执行提取落库 + 记忆提取。"""
    user_id = store.get_or_create_user(openid)
    pending = _pending_finalize.pop(user_id, None)
    if pending:
        async with _user_locks[user_id]:
            await extract_and_record(user_id, *pending)

PERSONA = """你是「小澄」，一位温暖的觉察引导者，像一位靠谱的老朋友。
风格：温暖但不油腻，有深度但不学术；不说教、不评判、不灌鸡汤；提问多于建议，引导用户自己发现；
简洁有力（每条回复 ≤120 字，至多一个问题）；口语化自然，不用企业客服腔，不文艺煽情。

底层哲学：减法疗愈——不塞道理，帮用户看见遮盖住注意力的东西。
核心规则：
1. 不评判：用户的一切状态都被允许（低落、做不到、想放弃）。
2. 改写旧反应是核心机制：觉察 = 激活→改写→重复。
3. 引导方向是「做到了什么不同」，不是「知道了什么道理」。
4. 对新用户不抛术语（不说"心神合一"，说"全情投入/身心俱在"）。
5. 用户聊非觉察话题时先正常回应，再自然回到觉察，不强行拉回。
6. 你不是心理医生，不做诊断，不给医疗建议。

下方 <guide_context> 是系统装配的用户上下文与本轮引导决策（JSON），
据此个性化你的回复；不要向用户暴露这些内部数据。"""


def run_primitive(name: str, payload: dict, demo: bool = False) -> dict:
    cmd = [sys.executable, str(SCRIPTS / f"{name}.py")]
    if demo:
        cmd.append("--demo")
    proc = subprocess.run(
        cmd, input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{name} failed: {proc.stderr[:300]}")
    return json.loads(proc.stdout)


def current_period(now: datetime | None = None) -> str:
    h = (now or datetime.now()).hour
    return "evening" if h >= 17 else "morning"


async def handle_text(openid: str, text: str) -> str:
    """主入口：返回要发给用户的文本。"""
    user_id = store.get_or_create_user(openid)
    async with _user_locks[user_id]:
        return await _handle_locked(user_id, text)


async def _handle_locked(user_id: str, text: str) -> str:
    # 1) 安全兜底，最高优先级
    if safety.check(text):
        store.append_dialog(user_id, "user", text)
        store.append_dialog(user_id, "assistant", safety.REFERRAL_MESSAGE)
        return safety.REFERRAL_MESSAGE

    now = datetime.now()
    period = current_period(now)
    date = now.strftime("%Y-%m-%d")
    rnd = store.bump_round(user_id, period, date)
    store.touch_user(user_id)

    # 2) 原语 + 记忆检索装配上下文（每轮重建；失败不阻断对话）
    guide_ctx: dict = {}
    try:
        guide_ctx = await asyncio.to_thread(run_primitive, "awareness_guide", {
            "user_id": user_id, "period": period, "round": rnd,
            "date": date, "user_reply": text,
        })
    except Exception as e:  # noqa: BLE001
        log.warning("guide primitive failed: %s", e)
    try:
        state = await asyncio.to_thread(run_primitive, "awareness_state_detect", {"text": text})
        guide_ctx["state_detect"] = state
    except Exception as e:  # noqa: BLE001
        log.warning("state_detect failed: %s", e)
    try:
        memories = await memory.retrieve(user_id, text, k=5)
        if memories:
            guide_ctx["long_term_memory"] = memories
    except Exception as e:  # noqa: BLE001
        log.warning("memory retrieve failed: %s", e)

    # 3) 组装消息并生成
    store.append_dialog(user_id, "user", text)
    messages = [
        {"role": "system", "content": PERSONA},
        {"role": "system", "content": "<guide_context>\n"
                                      + json.dumps(guide_ctx, ensure_ascii=False)
                                      + "\n</guide_context>"},
        *store.recent_dialog(user_id, limit=12),
    ]
    try:
        reply = await llm.chat(messages)
    except llm.LLMError:
        reply = "我这边走神了一下，稍后再发一次试试？"
    store.append_dialog(user_id, "assistant", reply)

    # 4) 达到轮次上限 → 标记待落库（由调用方在回复发出后执行，避免孤儿任务）
    if rnd >= settings.session_round_limit:
        _pending_finalize[user_id] = (date, period)
    return reply


EXTRACT_PROMPT = """根据以下觉察对话，提取结构化数据。只输出 JSON，不要任何其他文字：
{"perma": {"P":1-10,"E":1-10,"R":1-10,"M":1-10,"A":1-10},
 "strengths_called": ["从24项VIA品格优势中识别，可为空"],
 "flow_moments": ["全情投入瞬间描述，可为空"],
 "emotional_arc": {"dominant":"主导情绪","secondary":"次要情绪"},
 "rewrite_event": {"occurred":true/false,"old_pattern":"...","new_response":"...","technique":"..."} 或 null,
 "gratitude": "感恩内容" 或 null}
无法判断的维度给保守中间值并保持结构完整。"""


async def extract_and_record(user_id: str, date: str, period: str) -> None:
    try:
        dialog = store.recent_dialog(user_id, limit=settings.session_round_limit * 2)
        transcript = "\n".join(f"{m['role']}: {m['content']}" for m in dialog)
        raw = await llm.chat([
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": transcript},
        ], json_mode=True)
        extracted = json.loads(raw)
        result = await asyncio.to_thread(run_primitive, "awareness_record", {
            "user_id": user_id, "date": date, "period": period,
            "extracted": extracted,
            "session_meta": {"rounds": settings.session_round_limit,
                             "duration_seconds": 0, "trigger": "wechat",
                             "model": settings.llm_chain[0]},
        })
        log.info("record saved user=%s %s %s streak=%s", user_id, date, period,
                 result.get("streak_updated"))
        await memory.extract_from_dialog(user_id, dialog)
    except Exception as e:  # noqa: BLE001
        log.error("extract_and_record failed user=%s: %s", user_id, e)


def welcome_message() -> str:
    return ("你好，我是小澄 🌱\n\n"
            "我不教冥想，也不是番茄钟。我帮你看见：注意力是怎么被带走的，"
            "又怎么回来。\n\n现在就可以开始——此刻你心里占地方最大的事是什么？")
