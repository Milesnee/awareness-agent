"""记忆系统 v1 —— memory-as-retrieval（对标 Tolan 架构）。

设计原则：
- 记忆不是对话记录：会话结束后由 LLM 压缩提取「事实/偏好/vibe 信号」三类记忆
- 每轮重建上下文：对话时按当前输入向量检索 top-k 注入，不堆全量历史
- 嵌入走 OpenAI 兼容 /embeddings 端点（智谱 embedding-3 / 阿里 text-embedding 等），
  mock 模式用确定性哈希向量，本地联调零网络
- 存储：SQLite BLOB + 内存余弦检索。万级记忆/用户内毫秒级；
  量级上来后迁 sqlite-vec / pgvector（接口不变，另立 ADR）
"""
from __future__ import annotations

import array
import hashlib
import json
import logging
import math
import os
import time

import httpx

from . import llm, store

log = logging.getLogger("memory")

EMB_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", "mock://")
EMB_MODEL = os.environ.get("EMBEDDING_MODEL", "embedding-3")
EMB_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
EMB_DIM = int(os.environ.get("EMBEDDING_DIM", "256"))  # mock 维度；真实端点以返回为准

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,            -- fact / preference / vibe
  content TEXT NOT NULL,
  embedding BLOB NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
"""


def _ensure_schema() -> None:
    store._conn().executescript(SCHEMA)


async def embed(texts: list[str]) -> list[list[float]]:
    if EMB_BASE_URL.startswith("mock://"):
        return [_mock_vec(t) for t in texts]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{EMB_BASE_URL.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {EMB_API_KEY}"},
            json={"model": EMB_MODEL, "input": texts},
        )
        r.raise_for_status()
        data = r.json()["data"]
    return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]


def _mock_vec(text: str) -> list[float]:
    """确定性伪向量：同词重叠的文本余弦相似度更高（按词哈希到桶）。"""
    v = [0.0] * EMB_DIM
    for token in text.lower().replace("，", " ").split():
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        v[h % EMB_DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _pack(vec: list[float]) -> bytes:
    return array.array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array.array("f")
    a.frombytes(blob)
    return list(a)


def _cos(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


async def save_memories(user_id: str, items: list[dict]) -> int:
    """items: [{"kind": "fact|preference|vibe", "content": "..."}]"""
    _ensure_schema()
    items = [i for i in items if i.get("content")]
    if not items:
        return 0
    vecs = await embed([i["content"] for i in items])
    c = store._conn()
    now = time.time()
    for item, vec in zip(items, vecs):
        # 去重：同 user 同内容不重复入库
        dup = c.execute("SELECT 1 FROM memories WHERE user_id=? AND content=?",
                        (user_id, item["content"])).fetchone()
        if dup:
            continue
        c.execute("INSERT INTO memories(user_id, kind, content, embedding, ts)"
                  " VALUES (?,?,?,?,?)",
                  (user_id, item.get("kind", "fact"), item["content"], _pack(vec), now))
    return len(items)


async def retrieve(user_id: str, query: str, k: int = 5) -> list[dict]:
    """每轮调用：按当前输入检索最相关记忆（时间衰减加权）。"""
    _ensure_schema()
    rows = store._conn().execute(
        "SELECT kind, content, embedding, ts FROM memories WHERE user_id=?",
        (user_id,)).fetchall()
    if not rows:
        return []
    qv = (await embed([query]))[0]
    now = time.time()
    scored = []
    for kind, content, blob, ts in rows:
        sim = _cos(qv, _unpack(blob))
        decay = 0.85 ** ((now - ts) / 86400 / 7)  # 每周衰减 15%
        scored.append((sim * 0.8 + decay * 0.2, kind, content))
    scored.sort(reverse=True)
    return [{"kind": k_, "content": ct} for _, k_, ct in scored[:k]]


MEMORY_EXTRACT_PROMPT = """从以下对话中提取值得长期记住的内容。只输出 JSON 数组，无其他文字：
[{"kind":"fact","content":"用户是独立开发者，在做一个AI项目"},
 {"kind":"preference","content":"不喜欢被说教，喜欢直接的反馈"},
 {"kind":"vibe","content":"提到工作时容易陷入'怕不够好'的焦虑"}]
规则：
- fact=客观事实（职业/关系/正在做的事）；preference=沟通与偏好；vibe=反复出现的情绪信号/触发点
- 每条 ≤30 字，第三人称，无对话引文
- 只提取跨会话仍有价值的内容；琐碎的当日细节不提取；没有则输出 []"""


async def extract_from_dialog(user_id: str, dialog: list[dict]) -> int:
    """会话结束后调用：压缩提取记忆入库。"""
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in dialog)
    try:
        raw = await llm.chat([
            {"role": "system", "content": MEMORY_EXTRACT_PROMPT},
            {"role": "user", "content": transcript},
        ], json_mode=True)
        parsed = json.loads(raw)
        items = parsed if isinstance(parsed, list) else parsed.get("memories", [])
        n = await save_memories(user_id, items)
        log.info("memory extracted user=%s n=%d", user_id, n)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("memory extract failed user=%s: %s", user_id, e)
        return 0
