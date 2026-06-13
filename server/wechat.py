"""微信服务号接入层：验签 / XML 解析 / access_token 缓存 / 客服消息下发。

注意：支持明文/兼容/安全模式。安全模式（AES）通过 WECHAT_AES_KEY 自动启用。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

import httpx

from .config import settings

log = logging.getLogger("wechat")
API = "https://api.weixin.qq.com/cgi-bin"





def verify_signature(signature: str, timestamp: str, nonce: str) -> bool:
    raw = "".join(sorted([settings.wechat_token, timestamp, nonce]))
    return hashlib.sha1(raw.encode()).hexdigest() == signature


def verify_msg_signature(msg_signature: str, token: str, timestamp: str, nonce: str, encrypted: str) -> bool:
    """安全模式：msg_signature = SHA1(token + timestamp + nonce + encrypted)。"""
    raw = "".join([token, timestamp, nonce, encrypted])
    return hashlib.sha1(raw.encode()).hexdigest() == msg_signature


def _aes_key() -> bytes:
    return base64.b64decode(settings.wechat_aes_key + "=")


def decrypt_aes(encrypted_base64: str, appid: str) -> str:
    """解密微信 AES 加密消息，返回 XML 明文。"""
    key = _aes_key()
    raw = base64.b64decode(encrypted_base64)
    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    decryptor = cipher.decryptor()
    padded = decryptor.update(raw) + decryptor.finalize()
    # PKCS7 unpad
    pad_len = padded[-1]
    content = padded[:-pad_len]
    # 微信格式：random(16) + length(4, big-endian) + xml + appid
    msg_len = int.from_bytes(content[16:20], "big")
    xml_text = content[20:20 + msg_len].decode("utf-8")
    got_appid = content[20 + msg_len:].decode("utf-8")
    if got_appid != appid:
        raise ValueError(f"AES 解密 appid 不匹配: got={got_appid}, expected={appid}")
    return xml_text


def encrypt_aes(xml_text: str, appid: str) -> str:
    """加密回复 XML（安全模式），返回 base64。"""
    key = _aes_key()
    random_bytes = os.urandom(16)
    msg_len = len(xml_text.encode("utf-8"))
    raw = random_bytes + msg_len.to_bytes(4, "big") + xml_text.encode("utf-8") + appid.encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
    encryptor = cipher.encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


@dataclass
class InboundMsg:
    msg_type: str          # text / event / voice ...
    from_user: str         # openid
    to_user: str
    content: str = ""
    event: str = ""        # subscribe / unsubscribe ...
    media_id: str = ""
    recognition: str = ""  # 公众平台开启「接收语音识别结果」后微信附带
    msg_id: str = ""
    create_time: str = ""


def parse_xml(body: bytes) -> InboundMsg:
    root = ET.fromstring(body)
    g = lambda tag: (root.findtext(tag) or "").strip()  # noqa: E731
    return InboundMsg(
        msg_type=g("MsgType"),
        from_user=g("FromUserName"),
        to_user=g("ToUserName"),
        content=g("Content"),
        event=g("Event"),
        media_id=g("MediaId"),
        recognition=g("Recognition"),
        msg_id=g("MsgId") or f"{g('FromUserName')}-{g('CreateTime')}-{g('Event')}",
        create_time=g("CreateTime"),
    )


def build_encrypted_reply(to_user: str, from_user: str, content: str, nonce: str) -> str:
    """安全模式：回复内容用 AES 加密后包装。"""
    timestamp = str(int(time.time()))
    encrypted = encrypt_aes(content, to_user)
    raw = "".join([settings.wechat_token, timestamp, nonce, encrypted])
    msg_signature = hashlib.sha1(raw.encode()).hexdigest()
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{timestamp}</CreateTime>"
        f"<MsgType><![CDATA[text]]></MsgType>"
        f"<Encrypt><![CDATA[{encrypted}]]></Encrypt>"
        f"<MsgSignature><![CDATA[{msg_signature}]]></MsgSignature>"
        f"<Nonce><![CDATA[{nonce}]]></Nonce>"
        "</xml>"
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
            r = await client.post(
                f"{API}/message/custom/send",
                params={"access_token": token},
                json={"touser": openid, "msgtype": "text", "text": {"content": chunk}},
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


async def download_media(media_id: str) -> bytes:
    token = await token_manager.get()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{API}/media/get",
                             params={"access_token": token, "media_id": media_id})
        r.raise_for_status()
        return r.content


async def upload_voice(audio: bytes, filename: str = "reply.mp3") -> str:
    """上传临时素材（voice，3天有效）→ media_id。"""
    token = await token_manager.get()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API}/media/upload",
                              params={"access_token": token, "type": "voice"},
                              files={"media": (filename, audio, "audio/mpeg")})
        data = r.json()
    if "media_id" not in data:
        raise RuntimeError(f"上传语音素材失败: {data}")
    return data["media_id"]


async def send_voice(openid: str, media_id: str) -> None:
    token = await token_manager.get()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{API}/message/custom/send",
                              params={"access_token": token},
                              json={"touser": openid, "msgtype": "voice",
                                    "voice": {"media_id": media_id}})
        data = r.json()
        if data.get("errcode"):
            raise RuntimeError(f"语音客服消息失败: {data}")
