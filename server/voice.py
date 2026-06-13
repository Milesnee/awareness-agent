"""R2 语音：ASR（微信自带识别优先）+ TTS 语音回复。

ASR 链路：
1. 首选：公众平台开启「接收语音识别结果」→ 语音 XML 自带 Recognition 字段，免费、零延迟
2. fallback：下载临时素材 → OpenAI 兼容 /audio/transcriptions（如 SiliconFlow/阿里 ASR）
   未配置 fallback 且无 Recognition 时返回 None，由上层回引导文案

TTS 链路：
OpenAI 兼容 /audio/speech → MP3 → 上传微信临时素材(voice) → 客服消息 msgtype=voice
微信语音限制：≤60s、≤2MB → 超长文本自动降级为纯文字回复
"""
from __future__ import annotations

import logging
import os

import httpx

from . import wechat

log = logging.getLogger("voice")

ASR_BASE_URL = os.environ.get("ASR_BASE_URL", "")          # 留空=仅用微信 Recognition
ASR_MODEL = os.environ.get("ASR_MODEL", "whisper-1")
ASR_API_KEY = os.environ.get("ASR_API_KEY", "")

TTS_BASE_URL = os.environ.get("TTS_BASE_URL", "")          # 留空=不回语音，仅文字
TTS_MODEL = os.environ.get("TTS_MODEL", "")
TTS_VOICE = os.environ.get("TTS_VOICE", "alloy")
TTS_API_KEY = os.environ.get("TTS_API_KEY", "")
TTS_MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "180"))  # ~60s 上限的保守值


async def transcribe(recognition: str, media_id: str) -> str | None:
    """优先微信自带识别；否则走 fallback ASR；都没有返回 None。"""
    if recognition.strip():
        return recognition.strip()
    if not ASR_BASE_URL:
        return None
    try:
        audio = await wechat.download_media(media_id)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{ASR_BASE_URL.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {ASR_API_KEY}"},
                files={"file": ("voice.amr", audio, "audio/amr")},
                data={"model": ASR_MODEL},
            )
            r.raise_for_status()
        return r.json().get("text", "").strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning("ASR fallback failed media=%s: %s", media_id, e)
        return None


async def synthesize(text: str) -> bytes | None:
    """文本 → MP3。未配置 TTS 或文本超长返回 None（上层降级纯文字）。"""
    if not TTS_BASE_URL or len(text) > TTS_MAX_CHARS:
        return None
    if TTS_BASE_URL.startswith("mock://"):
        return b"MOCK_MP3" + text.encode("utf-8")[:64]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TTS_BASE_URL.rstrip('/')}/audio/speech",
                headers={"Authorization": f"Bearer {TTS_API_KEY}"},
                json={"model": TTS_MODEL, "voice": TTS_VOICE,
                      "input": text, "response_format": "mp3"},
            )
            r.raise_for_status()
        audio = r.content
        if len(audio) > 2 * 1024 * 1024:  # 微信 2MB 上限
            return None
        return audio
    except Exception as e:  # noqa: BLE001
        log.warning("TTS failed: %s", e)
        return None


async def reply_with_voice(openid: str, text: str) -> None:
    """语音进 → 语音+文字出；TTS 不可用时降级纯文字。"""
    audio = await synthesize(text)
    if audio:
        try:
            media_id = await wechat.upload_voice(audio)
            await wechat.send_voice(openid, media_id)
        except Exception as e:  # noqa: BLE001
            log.warning("voice send failed, fallback to text: %s", e)
    await wechat.send_text(openid, text)
