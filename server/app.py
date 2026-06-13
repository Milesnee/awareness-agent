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

from . import orchestrator, scheduler, store, wechat

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
    if not wechat.verify_signature(signature, timestamp, nonce):
        return Response(content="forbidden", status_code=403)

    body = await request.body()

    # AES 加密模式：先解密再解析 XML
    if encrypt_type == "aes":
        try:
            body = wechat.decrypt_message(body, msg_signature, timestamp, nonce)
        except Exception as e:
            log.error("AES 解密失败: %s", e)
            return Response(content="success", media_type="text/plain")

    msg = wechat.parse_xml(body)

    # 去重：微信超时重试会重复投递
    if store.is_duplicate(msg.msg_id):
        return Response(content="success", media_type="text/plain")

    # 关注事件：同步回欢迎语
    if msg.msg_type == "event":
        if msg.event.lower() == "subscribe":
            reply_xml = wechat.build_text_reply(msg.from_user, msg.to_user,
                                                orchestrator.welcome_message())
            if encrypt_type == "aes":
                reply_xml = wechat.encrypt_message(reply_xml, nonce, timestamp)
            return Response(content=reply_xml, media_type="application/xml")
        return Response(content="success", media_type="text/plain")

    # 文本消息：立即确认，后台生成并经客服消息下发
    if msg.msg_type == "text" and msg.content:
        background.add_task(_process_and_reply, msg.from_user, msg.content)
        return Response(content="success", media_type="text/plain")

    # 语音等其他类型：暂未支持
    reply_xml = wechat.build_text_reply(msg.from_user, msg.to_user,
                                        "现在先用文字聊吧，语音我还在学 🙂")
    if encrypt_type == "aes":
        reply_xml = wechat.encrypt_message(reply_xml, nonce, timestamp)
    return Response(content=reply_xml, media_type="application/xml")


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
