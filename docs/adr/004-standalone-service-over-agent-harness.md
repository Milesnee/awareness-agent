# ADR-004: 生产底座——专用轻服务 vs Agent Harness（Hermes/OpenClaw）

> 日期：2026-06-12
> 状态：已接受
> 关联：ADR-001（SKILL 驱动）、ADR-002（JSON 存储）、`server/` 实现、IMPLEMENT.md Phase 3

## 背景

Phase 1 MVP 以 SKILL 形式运行在 Hermes/OpenClaw agent harness 内（飞书 Bot、heartbeat 推送、MCP 工具化原语），单用户验证通过。Phase 3 目标变为：微信服务号面向公众上线，多用户、可运营、可合规。需要决定生产环境的运行底座。

## 选项

### A: 继续以 OpenClaw/Hermes 为生产底座
- 复用 heartbeat、session、SKILL 加载、多渠道连接器
- 迭代快，已有运行经验

### B: 每用户一个 OpenClaw 实例（社区多租户模式）
- 容器/VM 级隔离（AWS EKS + Kata、Docker per-user 等参考实现）
- 不改 OpenClaw 本体

### C: 专用轻服务（选择）
- FastAPI 网关 + 确定性编排流水线 + 多模型 LLM 客户端
- 原语保持 JSON-in/JSON-out 契约，零改动复用

## 决策

选择 C。OpenClaw/Hermes 降级为个人开发台（dev bench），不进入生产链路。

## 理由

1. **安全边界错配**：OpenClaw 官方安全文档明确其边界假设是"每 gateway 一个受信任操作者"的个人助理模型，**不支持**互不信任用户共享同一 gateway/agent 的对抗性多租户场景。服务号用户正是成千上万互不信任的陌生人。
2. **攻击面与数据敏感度不匹配**：凭证明文存储于 `~/.openclaw/`（已被 RedLine/Lumma 等窃密木马针对性扫描）、历史命令注入漏洞（CVE-2026-25253，CVSS 8.8）、harness 自带 shell/文件系统工具。本产品存储用户心理觉察数据，属高敏感，不可承受此攻击面。
3. **成本结构错误**：社区多租户方案（选项 B）均为"每用户一实例"，单机约支撑 50+ 用户，适合"每人一个全能 agent"的企业场景。本产品每用户只需一条轻量觉察对话流水线，按实例隔离是百倍冗余。
4. **微信 5 秒回调约束**：完整 agent loop（多轮 LLM + 工具调用）延迟与 token 成本远高于定向编排（每消息 1-2 次 LLM 调用）。
5. **合规可审计性**：境内 to-C 生成式 AI 需要确定性、可审计的内容生成链路（输入→上下文装配→单次生成→安全兜底→输出）。自主 agent harness 的行为不可枚举，难以向监管说明。
6. **依赖风险**：OpenClaw 为快速演进的开源项目，breaking change 频繁，路线图不受控；生产链路应只依赖自有代码 + 稳定基础库。

## 架构后果

```
┌─ 生产线（server/）──────────────────────────────┐
│ 微信服务号 → FastAPI 网关（5s内ack，异步客服消息回复） │
│   → 编排层：safety兜底 → guide/state_detect 原语    │
│   → LLM（多模型链，OpenAI兼容，故障转移）            │
│   → 5轮后结构化提取 → record 落库（journal/streak）  │
└──────────────────────────────────────────────┘
┌─ 个人线（dev bench）────────────────────────────┐
│ OpenClaw/Hermes + mcp_server.py + 飞书           │
│ 用途：老麦 dogfooding、prompt/引导策略实验           │
│ 验证有效的策略 → 下沉到生产线编排层（PERSONA/decision）│
└──────────────────────────────────────────────┘
共享核心 IP：9 个原语 + JSON 数据契约 + SKILL 人格设定
```

## 不变量（两条线必须共同遵守）

1. 原语 JSON-in/JSON-out 契约是唯一接口，任何一侧不得绕过原语直写 `data/`
2. 人格与引导策略以 SKILL.md / PERSONA 为单一事实源，双线同步
3. 用户数据目录结构 `data/{profiles,journals,streaks}/{user_id}` 不变（ADR-002 延续）

## 重新评估触发条件

- 用户量使 SQLite + JSON 文件成为瓶颈（约 1 万 DAU 量级）→ 启动存储迁移（届时另立 ADR，原语契约不变）
- OpenClaw 官方提供受支持的对抗性多租户边界 → 可重评估选项 A/B
- 产品形态变为"每用户需要自主工具调用的全能 agent" → 重评估
