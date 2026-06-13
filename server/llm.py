"""OpenAI 兼容多模型客户端：按 LLM_CHAIN 依序故障转移。"""
from __future__ import annotations

import json
import logging

import httpx

from .config import LLMProvider, settings

log = logging.getLogger("llm")


class LLMError(RuntimeError):
    pass


async def _call(provider: LLMProvider, messages: list[dict], *, json_mode: bool = False) -> str:
    if provider.base_url.startswith("mock://"):
        return _mock_reply(messages, json_mode)
    payload: dict = {
        "model": provider.model,
        "messages": messages,
        "temperature": provider.temperature,
        "max_tokens": provider.max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=provider.timeout) as client:
        r = await client.post(
            f"{provider.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {provider.api_key}"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]


async def chat(messages: list[dict], *, json_mode: bool = False) -> str:
    """依链路尝试，全部失败抛 LLMError。"""
    last_err: Exception | None = None
    for provider in settings.chain():
        try:
            return await _call(provider, messages, json_mode=json_mode)
        except Exception as e:  # noqa: BLE001 — 故障转移需要兜住一切
            log.warning("provider %s failed: %s", provider.name, e)
            last_err = e
    raise LLMError(f"所有 LLM provider 均失败: {last_err}")


def _mock_reply(messages: list[dict], json_mode: bool) -> str:
    """本地联调：不出网，返回可预测内容。"""
    system = " ".join(m["content"] for m in messages if m["role"] == "system")
    if json_mode and "长期记住" in system:
        return json.dumps([
            {"kind": "fact", "content": "用户在写代码项目"},
            {"kind": "vibe", "content": "工作时容易陷入'怕不够好'的焦虑"},
        ], ensure_ascii=False)
    if json_mode:
        return json.dumps({
            "perma": {"P": 6, "E": 5, "R": 6, "M": 6, "A": 5},
            "strengths_called": ["毅力"],
            "flow_moments": [],
            "emotional_arc": {"dominant": "平静", "secondary": ""},
            "rewrite_event": None,
            "gratitude": None,
        }, ensure_ascii=False)
    user_last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return f"[mock] 收到：{user_last[:40]}……这个感受背后，你觉得自己在怕什么？"
