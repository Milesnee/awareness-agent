"""FastAPI 网关。

微信回调约束：5 秒内必须响应，否则重试 3 次。
策略：收到消息立即返回空串（微信视为已处理），后台任务生成回复，
通过客服消息接口异步下发（依赖已认证服务号 + 48h 互动窗口）。
关注事件（subscribe）走同步 XML 直接回欢迎语（生成快，无需异步）。
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, Query, Request, Response

import asyncio

from . import orchestrator, scheduler, store, voice, wechat
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="xiaocheng-gateway", docs_url=None, redoc_url=None)


@app.on_event("startup")
async def _start_scheduler():
    asyncio.get_event_loop().create_task(scheduler.run_forever())


@app.get("/wechat")
async def verify(signature: str = Query(""), timestamp: str = Query(""),
                 nonce: str = Query(""), echostr: str = Query("")):
    """服务器配置验证。"""
    if wechat.verify_signature(signature, timestamp, nonce):
        return Response(content=echostr, media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@app.post("/wechat")
async def inbound(request: Request, background: BackgroundTasks,
                  signature: str = Query(""), timestamp: str = Query(""),
                  nonce: str = Query(""),
                  encrypt_type: str = Query(""),
                  msg_signature: str = Query("")):
    body = await request.body()

    # 调试日志
    log.info(f"Received wechat request: encrypt_type={encrypt_type}, signature_len={len(signature)}, msg_signature_len={len(msg_signature)}")
    log.info(f"Body length: {len(body)}, body preview: {body.decode()[:100] if body else 'empty'}")

    # 安全模式/兼容模式：先解密
    is_encrypted = encrypt_type.lower() == "aes"
    if is_encrypted:
        log.info(f"Processing encrypted message, token={settings.wechat_token}")
        if not wechat.verify_msg_signature(msg_signature, settings.wechat_token,
                                            timestamp, nonce, body.decode()):
            log.error(f"Signature verification failed for encrypted message")
            return Response(content="forbidden", status_code=403)
        try:
            xml_text = wechat.decrypt_aes(body.decode(), settings.wechat_appid)
            body = xml_text.encode("utf-8")
            log.info(f"Successfully decrypted message, xml preview: {xml_text[:100]}")
        except Exception as e:
            log.error(f"Decryption failed: {e}")
            return Response(content="decryption_error", status_code=500)
    else:
        if not wechat.verify_signature(signature, timestamp, nonce):
            log.error(f"Signature verification failed for plain message")
            return Response(content="forbidden", status_code=403)

    msg = wechat.parse_xml(body)

    # 去重：微信超时重试会重复投递
    if store.is_duplicate(msg.msg_id):
        return Response(content="success", media_type="text/plain")

    # 关注事件：同步回欢迎语
    if msg.msg_type == "event":
        if msg.event.lower() == "subscribe":
            welcome = orchestrator.welcome_message()
            if is_encrypted:
                xml = wechat.build_encrypted_reply(msg.from_user, msg.to_user, welcome, nonce)
            else:
                xml = wechat.build_text_reply(msg.from_user, msg.to_user, welcome)
            return Response(content=xml, media_type="application/xml")
        return Response(content="success", media_type="text/plain")

    # 文本消息：立即确认，后台生成并经客服消息下发
    if msg.msg_type == "text" and msg.content:
        background.add_task(_process_and_reply, msg.from_user, msg.content)
        return Response(content="success", media_type="text/plain")

    # 语音消息：转写后走同一编排，回复语音+文字
    if msg.msg_type == "voice":
        background.add_task(_process_voice, msg.from_user, msg.recognition, msg.media_id)
        return Response(content="success", media_type="text/plain")

    # 其他类型暂不支持
    if is_encrypted:
        xml = wechat.build_encrypted_reply(msg.from_user, msg.to_user,
                                           "图片我还看不懂，先用文字或语音聊吧 🙂", nonce)
    else:
        xml = wechat.build_text_reply(msg.from_user, msg.to_user,
                                      "图片我还看不懂，先用文字或语音聊吧 🙂")
    return Response(content=xml, media_type="application/xml")


async def _process_voice(openid: str, recognition: str, media_id: str) -> None:
    log.info("语音消息 openid=%s recognition=%r media_id=%s", openid, recognition, media_id)
    try:
        text = await voice.transcribe(recognition, media_id)
        log.info("转写结果 openid=%s text=%r", openid, text)
        if not text:
            await wechat.send_text(openid, "这条语音我没听清，再说一次，或打字也行 🙂")
            return
        reply = await orchestrator.handle_text(openid, text)
        log.info("语音回复 openid=%s reply=%r", openid, reply[:80])
        await voice.reply_with_voice(openid, reply)
        await orchestrator.maybe_finalize(openid)
    except Exception as e:  # noqa: BLE001
        log.exception("语音处理失败 openid=%s: %s", openid, e)


async def _process_and_reply(openid: str, text: str) -> None:
    try:
        reply = await orchestrator.handle_text(openid, text)
        await wechat.send_text(openid, reply)
        await orchestrator.maybe_finalize(openid)
    except Exception as e:  # noqa: BLE001
        log.exception("处理失败 openid=%s: %s", openid, e)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
