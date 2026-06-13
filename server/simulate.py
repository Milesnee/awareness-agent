"""本地仿真：不出网，用 mock LLM + 假微信 XML 验证完整链路。

覆盖：验签 → 去重 → 关注欢迎语 → 多轮文本对话（guide/state_detect 原语真实调用）
→ 轮次达上限触发 extract→record（mock LLM 返回固定 JSON）→ streak 落库验证。

运行：LLM_CHAIN=mock WECHAT_TOKEN=testtoken python3 -m server.simulate
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from .app import app
from .config import PROJECT_ROOT


def sig_params(token: str = "testtoken") -> dict:
    ts, nonce = str(int(time.time())), "n0nce"
    sig = hashlib.sha1("".join(sorted([token, ts, nonce])).encode()).hexdigest()
    return {"signature": sig, "timestamp": ts, "nonce": nonce}


def make_xml(openid: str, content: str = "", event: str = "", msg_id: str = "") -> str:
    if event:
        body = f"<MsgType><![CDATA[event]]></MsgType><Event><![CDATA[{event}]]></Event>"
    else:
        body = (f"<MsgType><![CDATA[text]]></MsgType>"
                f"<Content><![CDATA[{content}]]></Content>"
                f"<MsgId>{msg_id or int(time.time()*1000)}</MsgId>")
    return (f"<xml><ToUserName><![CDATA[gh_test]]></ToUserName>"
            f"<FromUserName><![CDATA[{openid}]]></FromUserName>"
            f"<CreateTime>{int(time.time())}</CreateTime>{body}</xml>")


sent: list[tuple[str, str]] = []


async def fake_send_text(openid: str, content: str) -> None:
    sent.append((openid, content))


def main() -> None:
    from . import wechat
    wechat.send_text = fake_send_text          # 拦截客服消息出口
    import server.app as app_module
    app_module.wechat.send_text = fake_send_text

    client = TestClient(app)
    openid = "o_simulated_user"

    # 1) 服务器验证
    p = sig_params()
    r = client.get("/wechat", params={**p, "echostr": "hello"})
    assert r.text == "hello", r.text
    print("✅ 验签/echostr 通过")

    # 2) 关注事件 → 同步欢迎语
    r = client.post("/wechat", params=sig_params(), content=make_xml(openid, event="subscribe"))
    assert "小澄" in r.text
    print("✅ 关注欢迎语 通过")

    # 3) 多轮对话（5 轮触发提取落库）
    turns = [
        "今天想专注写代码，但有点焦虑",
        "怕写出来不够好",
        "嗯…好像是怕别人觉得我不行",
        "试着带着这个感觉先开工",
        "好，今天就到这里",
    ]
    for i, t in enumerate(turns, 1):
        r = client.post("/wechat", params=sig_params(), content=make_xml(openid, content=t))
        assert r.text == "success", r.text
        print(f"  round {i}: 用户「{t[:14]}…」")
    time.sleep(0.5)  # 等后台 extract_and_record

    assert len(sent) == len(turns), f"应有 {len(turns)} 条客服消息，实际 {len(sent)}"
    print(f"✅ {len(sent)} 条异步客服回复全部生成，示例：{sent[0][1][:50]}…")

    # 4) 去重验证
    before = len(sent)
    dup = make_xml(openid, content="重复消息", msg_id="FIXED123")
    client.post("/wechat", params=sig_params(), content=dup)
    client.post("/wechat", params=sig_params(), content=dup)
    time.sleep(0.3)
    assert len(sent) == before + 1, "去重失败"
    print("✅ MsgId 去重 通过")

    # 5) 危机兜底
    client.post("/wechat", params=sig_params(), content=make_xml(openid, content="我不想活了"))
    time.sleep(0.3)
    assert "12356" in sent[-1][1]
    print("✅ 危机转介兜底 通过")

    # 6) 落库验证：journal + streak 文件应存在
    from .store import _conn
    user_id = _conn().execute("SELECT user_id FROM users WHERE openid=?", (openid,)).fetchone()[0]
    journals = list((PROJECT_ROOT / "data" / "journals" / user_id).glob("*.json"))
    streak = PROJECT_ROOT / "data" / "streaks" / f"{user_id}.json"
    assert journals, "journal 未落库"
    assert streak.exists(), "streak 未更新"
    rec = json.loads(journals[0].read_text())
    print(f"✅ 结构化落库 通过：{journals[0].name}, PERMA={rec.get('extracted',{}).get('perma')}")
    print(f"✅ streak: {json.loads(streak.read_text())}")

    # 7) 记忆系统：提取入库 + 每轮检索
    import asyncio as _aio
    from . import memory as mem
    mems = _conn().execute("SELECT kind, content FROM memories WHERE user_id=?", (user_id,)).fetchall()
    assert mems, "记忆未提取入库"
    hits = _aio.get_event_loop().run_until_complete(mem.retrieve(user_id, "写代码 焦虑", k=3))
    assert hits, "记忆检索为空"
    print(f"✅ 记忆系统 通过：库内 {len(mems)} 条，检索示例 [{hits[0]['kind']}] {hits[0]['content']}")

    # 8) 推送调度：模拟晨间 8 点 tick（用户 48h 窗口内 → 应推送）
    import datetime as _dt
    from . import scheduler as sched
    fake_8am = _dt.datetime.now().replace(hour=8)
    n = _aio.get_event_loop().run_until_complete(sched.tick(fake_8am))
    assert n >= 1, f"晨间推送未触发 n={n}"
    assert "？" in sent[-1][1] or "?" in sent[-1][1]
    print(f"✅ 晨间推送 通过：{sent[-1][1][:40]}…")
    # 同日重复 tick 不重发
    n2 = _aio.get_event_loop().run_until_complete(sched.tick(fake_8am))
    assert n2 == 0, "推送幂等失败"
    print("✅ 推送幂等（同日同槽不重发）通过")

    print("\n🎉 微信网关本地仿真全链路通过（含记忆系统 + 推送调度）")


if __name__ == "__main__":
    main()
