"""Server configuration — env-first, optional YAML overlay.

Multi-LLM: providers are declared in config; routing order via LLM_CHAIN.
All providers use the OpenAI-compatible /chat/completions contract,
so GLM / DeepSeek / Qwen / Moonshot / 本地 vLLM 均可直接接入。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA_DIR = PROJECT_ROOT / "data" / "server"
SERVER_DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class LLMProvider:
    name: str
    base_url: str          # e.g. https://open.bigmodel.cn/api/paas/v4
    model: str             # e.g. glm-4-flash
    api_key_env: str       # env var holding the key
    timeout: float = 30.0
    temperature: float = 0.7
    max_tokens: int = 800

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")


# ── Built-in provider presets（按需启用，密钥走环境变量）──────────
PRESETS: dict[str, LLMProvider] = {
    "glm": LLMProvider("glm", "https://open.bigmodel.cn/api/paas/v4",
                       os.environ.get("GLM_MODEL", "glm-4-flash"), "GLM_API_KEY"),
    "deepseek": LLMProvider("deepseek", "https://api.deepseek.com/v1",
                            os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"), "DEEPSEEK_API_KEY"),
    "qwen": LLMProvider("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        os.environ.get("QWEN_MODEL", "qwen-plus"), "DASHSCOPE_API_KEY"),
    # mock：本地联调用，零网络依赖
    "mock": LLMProvider("mock", "mock://", "mock", "MOCK_KEY"),
}


@dataclass
class Settings:
    # WeChat 服务号
    wechat_token: str = field(default_factory=lambda: os.environ.get("WECHAT_TOKEN", ""))
    wechat_appid: str = field(default_factory=lambda: os.environ.get("WECHAT_APPID", ""))
    wechat_secret: str = field(default_factory=lambda: os.environ.get("WECHAT_SECRET", ""))
    wechat_aes_key: str = field(default_factory=lambda: os.environ.get("WECHAT_AES_KEY", ""))  # 明文模式可留空

    # LLM 路由链：逗号分隔，依序故障转移，如 "glm,deepseek"
    llm_chain: list[str] = field(default_factory=lambda: [
        s.strip() for s in os.environ.get("LLM_CHAIN", "mock").split(",") if s.strip()
    ])
    # 额外自定义 provider（JSON 数组，见 config.example.json）
    extra_providers_json: str = field(default_factory=lambda: os.environ.get("LLM_EXTRA_PROVIDERS", ""))

    session_round_limit: int = int(os.environ.get("SESSION_ROUND_LIMIT", "5"))
    sqlite_path: Path = SERVER_DATA_DIR / "server.db"

    def providers(self) -> dict[str, LLMProvider]:
        out = dict(PRESETS)
        if self.extra_providers_json:
            for item in json.loads(self.extra_providers_json):
                p = LLMProvider(**item)
                out[p.name] = p
        return out

    def chain(self) -> list[LLMProvider]:
        provs = self.providers()
        sel = [provs[n] for n in self.llm_chain if n in provs]
        if not sel:
            raise RuntimeError(f"LLM_CHAIN 无有效 provider: {self.llm_chain}")
        return sel


settings = Settings()
