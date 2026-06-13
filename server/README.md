# 小澄微信服务号网关（server/）

把现有 9 个觉察原语包装成可部署的微信服务号后端。原语 JSON 契约零改动。

## 架构

```
微信服务号 → POST /wechat（5秒内回 success）
                └─ 后台任务: orchestrator
                     ├─ safety 危机兜底（最高优先级）
                     ├─ awareness_guide / state_detect 原语装配上下文
                     ├─ LLM（多模型链路，OpenAI 兼容，故障转移）
                     ├─ 客服消息接口异步回复用户
                     └─ 5 轮后: LLM 结构化提取 → awareness_record 落库（journal/streak/profile）
存储: 原语数据仍为 data/{profiles,journals,streaks}/ JSON；
     服务态（openid映射/去重/轮次/对话历史）在 data/server/server.db (SQLite WAL)
```

## 环境变量

| 变量 | 说明 |
|---|---|
| `WECHAT_TOKEN` | 公众平台-服务器配置中的 Token |
| `WECHAT_APPID` / `WECHAT_SECRET` | 服务号开发者 ID/密钥（客服消息需要） |
| `LLM_CHAIN` | 路由链，如 `glm,deepseek`（依序故障转移）；本地联调用 `mock` |
| `GLM_API_KEY` / `DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` | 按启用的 provider 配置 |
| `GLM_MODEL` 等 | 可覆盖默认模型名 |
| `LLM_EXTRA_PROVIDERS` | JSON 数组注册自定义 provider（任何 OpenAI 兼容端点） |
| `SESSION_ROUND_LIMIT` | 触发结构化落库的轮次，默认 5 |

自定义 provider 示例：
```bash
export LLM_EXTRA_PROVIDERS='[{"name":"kimi","base_url":"https://api.moonshot.cn/v1","model":"moonshot-v1-8k","api_key_env":"MOONSHOT_API_KEY"}]'
export LLM_CHAIN="kimi,glm"
```

## 本地验证（不需要任何密钥）

```bash
pip install -r requirements-server.txt
LLM_CHAIN=mock WECHAT_TOKEN=testtoken python3 -m server.simulate
```

## 部署

```bash
pip install -r requirements-server.txt
uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1
# nginx 反代 443 → 8000，域名需 ICP 备案 + HTTPS
```

> workers 必须为 1（access_token 缓存与 per-user 锁为进程内）。
> 量级上来后：token 缓存迁 Redis、任务队列化，再开多 worker。

公众平台配置：开发 → 基本配置 → 服务器配置
- URL: `https://你的域名/wechat`，Token 与 `WECHAT_TOKEN` 一致
- 消息加解密方式：明文模式（安全模式的 AES 加解密已预留 `WECHAT_AES_KEY`，未实现）
- IP 白名单中加入服务器出口 IP（客服消息接口要求）

## 已实现（R0+R1）

- 晨/晚推送 + 周日周报（客服消息 48h 窗口内，`scheduler.py`，幂等）
- 记忆系统 v1（`memory.py`）：会话后提取 fact/preference/vibe → 嵌入入库；每轮向量检索 top-k 注入上下文（memory-as-retrieval，对标 Tolan）

## 已知边界

- 断签用户（>48h）推送跳过，订阅通知召回在 R3
- 语音消息未支持（R2）
- 安全模式加解密未实现
- 危机检测为关键词版，后续升级 LLM 分类
