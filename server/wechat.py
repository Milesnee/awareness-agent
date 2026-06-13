# -*- coding: utf-8 -*-
"""微信服务号接入层：验签 / AES 加解密 / XML 解析 / access_token 缓存 / 客服消息下发。

注意：支持「安全模式」(AES) 和「明文模式」。根据 query param encrypt_type 自动切换。
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
from wechatpy.crypto import WeChatCrypto

from .config import settings

log = logging.getLogger("wechat")
API = "https://api.weixin.qq.com/cgi-bin"

_crypto: WeChatCrypto | None = None


def _get_crypto() -> WeChatCrypto | None:
    """惰性初始化 AES 加解密实例。"""
    global _crypto
    if _crypto is not None:
        return _crypto
    if settings.wechat_aes_key and settings.wechat_token and settings.wechat_appid:
        _crypto = WeChatCrypto(settings.wechat_token, settings.wechat_aes_key, settings.wechat_appid)
        return _crypto
    return None


def decrypt_message(body: bytes, msg_signature: str, timestamp: str, nonce: str) -> bytes:
    """AES 解密，返回明文 XML。"""
    crypto = _get_crypto()
    if crypto is None:
        raise RuntimeError("AES 解密失败：WECHAT_AES_KEY 未配置")
    return crypto.decrypt_message(body, msg_signature, timestamp, nonce)


def verify_signature(signature: str, timestamp: str, nonce: str) -> bool:
    raw = "".join(sorted([settings.wechat_token, timestamp, nonce]))
    return hashlib.sha1(raw.encode()).hexdigest() == signature


@dataclass
class InboundMsg:
    msg_type: str          # text / event / voice ...
    from_user: str         # openid
    to_user: str
    content: str = ""
    event: str = ""        # subscribe / unsubscribe ...
    msg_id: str = ""
    create_time: str = ""
    recognition: str = ""  # 语音识别结果（微信自带ASR）
    media_id: str = ""     # 语音/视频/图片等媒体ID


def parse_xml(body: bytes) -> InboundMsg:
    root = ET.fromstring(body)
    g = lambda tag: (root.findtext(tag) or "").strip()  # noqa: E731
    return InboundMsg(
        msg_type=g("MsgType"),
        from_user=g("FromUserName"),
        to_user=g("ToUserName"),
        content=g("Content"),
        event=g("Event"),
        msg_id=g("MsgId") or f"{g('FromUserName')}-{g('CreateTime')}-{g('Event')}",
        create_time=g("CreateTime"),
        recognition=g("Recognition"),  # 语音识别结果
        media_id=g("MediaId"),        # 媒体文件ID
    )


def build_text_reply(to_user: str, from_user: str, content: str) -> str:
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{int(time.time())}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        "</xml>"
    )


class TokenManager:
    """access_token 进程内缓存（多实例部署时改为 Redis/中控服务）。"""

    def __init__(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    async def get(self) -> str:
        if self._token and time.time() < self._expires_at - 120:
            return self._token
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{API}/token", params={
                "grant_type": "client_credential",
                "appid": settings.wechat_appid,
                "secret": settings.wechat_secret,
            })
            data = r.json()
        if "access_token" not in data:
            raise RuntimeError(f"获取 access_token 失败: {data}")
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 7200))
        return self._token


token_manager = TokenManager()


async def send_text(openid: str, content: str) -> None:
    """客服消息（48h 互动窗口内可用）——异步回复的主通道。"""
    # 微信单条文本上限约 2048 字节，超长切分
    chunks = _split_utf8(content, 2000)
    token = await token_manager.get()
    async with httpx.AsyncClient(timeout=15) as client:
        for chunk in chunks:
            body = json.dumps({"touser": openid, "msgtype": "text", "text": {"content": chunk}},
                            ensure_ascii=False)
            r = await client.post(
                f"{API}/message/custom/send",
                params={"access_token": token},
                content=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            data = r.json()
            if data.get("errcode"):
                log.error("客服消息发送失败 openid=%s err=%s", openid, data)
                return


def _split_utf8(text: str, max_bytes: int) -> list[str]:
    out, buf, size = [], [], 0
    for ch in text:
        b = len(ch.encode("utf-8"))
        if size + b > max_bytes:
            out.append("".join(buf))
            buf, size = [], 0
        buf.append(ch)
        size += b
    if buf:
        out.append("".join(buf))
    return out or [""]
