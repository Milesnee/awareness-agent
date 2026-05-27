# 小澄觉察助手 · Awareness Guide

<p align="center">
  <b>向外看的人在做梦，向内看的人在觉醒。<br>Who looks outside, dreams; who looks inside, awakes. — Jung</b>
</p>

<p align="center">
  <b>AI 觉察引导系统</b> — 积极心理学 × 中华哲学减法疗愈框架<br>
  <b>AI Awareness Guide</b> — Positive Psychology × Eastern Philosophy Subtractive Healing
</p>

<p align="center">
  <a href="#中文"><img src="https://img.shields.io/badge/简体中文-中文介绍-blue" alt="中文"></a>
  <a href="#english"><img src="https://img.shields.io/badge/English-Documentation-blue" alt="English"></a>
  <a href="https://github.com/Milesnee/awareness-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT"></a>
</p>

---

> 不是冥想 App，不是时间管理工具。帮用户逐步找到并建立稳定的内核。
>
> Not a meditation app, not a time manager. Helping users find and build a stable inner core.

底层哲学：**减法疗愈** — 不是塞更多道理，是帮用户看见遮盖住本有注意力的东西。

Core philosophy: **Subtractive Healing** — not adding more theory, but helping users see what already covers their innate attention.

---

<a name="中文"></a>

## ✨ 特色

- 🧠 **理论三角**：庄子（为什么要放下）→ 清静经（怎么放下）→ 王阳明（放下后怎么行动）
- 📐 **原语架构**：9 个 JSON-in/JSON-out 原语替代 LLM 手工读文件，确定性行为 + 高信息密度
- 🔗 **MCP 原生集成**：通过 Model Context Protocol 嵌入 Hermes Agent，即插即用
- 📊 **PERMA + VIA 量化**：五维幸福度量 × 24 项品格优势，觉察可追踪、可回顾
- 🎯 **四状态识别**：停不下来 / 启动不了 / 硬撑着 / 一直在找 — 自动检测 + 差异化引导
- 🔥 **Streak 机制**：连续觉察天数追踪 + 里程碑奖励（种子→发芽→成长→茂盛→绽放）
- 📈 **周度洞察报告**：跨时段模式分析，PERMA 趋势 + 状态切换 + 改写效果 + 最小调整建议
- 🛡️ **零外部依赖**：Python 标准库 + JSON 文件存储，部署即跑

## 核心架构

**原语系统（Primitives）** — L1 感知 → L2 行动 → MCP 集成

```
┌─────────────────────────────────────────────┐
│              MCP Server (Hermes)             │
│                    │                         │
│    ┌───────────────┼───────────────┐         │
│    │          L2 行动层             │         │
│    │  guide · record · intervention         │
│    │  pattern_review · quality_score         │
│    └───────────────┼───────────────┘         │
│                     │                        │
│    ┌────────────────┼───────────────┐         │
│    │          L1 感知层             │         │
│    │  profile · journal_query · state_detect │
│    └───────────────────────────────┘         │
│                     │                        │
│          data/  (JSON 文件存储)               │
└─────────────────────────────────────────────┘
```

| 层 | 原语 | 作用 |
|----|------|------|
| L1 | `awareness_profile` | 加载觉察档案（PERMA 基线、签名优势、streak） |
| L1 | `awareness_journal_query` | 历史觉察查询（PERMA 趋势、状态序列、改写事件） |
| L1 | `awareness_state_detect` | 四状态识别（停不下来/启动不了/硬撑着/一直在找） |
| L2 | `awareness_guide` | 上下文装配 + 策略决策（核心引导引擎） |
| L2 | `awareness_record` | 结构化记录 + streak 更新 + profile 增量 |
| L2 | `awareness_intervention` | 干预决策引擎（基于质量趋势 + 标志 + streak 风险） |
| L2 | `awareness_pattern_review` | 跨时段模式分析（周洞察报告的自动化引擎） |
| L2 | `awareness_quality_score` | 对话质量评分（深度/完整度/改写质量/数据质量/投入度） |
| MCP | `mcp_server` | Hermes MCP 集成，原语即工具 |

## 快速开始

```bash
git clone https://github.com/Milesnee/awareness-agent.git
cd awareness-agent

# 获取引导上下文（晨间 Round 1）
echo '{"user_id":"demo","period":"morning","round":1,"user_name":"小澄"}' \
  | python3 scripts/awareness_guide.py --demo

# 加载用户档案
echo '{"user_id":"demo"}' | python3 scripts/awareness_profile.py

# 状态识别
echo '{"text":"今天又拖延了，刷了一上午手机"}' \
  | python3 scripts/awareness_state_detect.py

# 查看历史觉察趋势（最近7天）
echo '{"user_id":"demo","timespan":"7d"}' \
  | python3 scripts/awareness_journal_query.py
```

## 对话示例

```
[晨间引导] 🌅 Round 1/5

小澄：早上好。今天的内核锚点是什么？

用户：今天想专注写代码，但感觉有点焦虑。

小澄：感知到焦虑了。焦虑本身不是问题——
你对它的态度才是关键。这个焦虑说的是什么？
它怕你写出什么，还是怕你写不出什么？

用户：...怕写出来不够好。

小澄：好，这是觉察。带着它开工，不需要它消失。
```

## 理论基础

### 积极心理学
- **PERMA 模型**（Seligman, 2011）— 积极情绪(P)、投入(E)、关系(R)、意义(M)、成就(A)
- **VIA 品格优势**（Peterson & Seligman, 2004）— 24 项品格优势分类与度量

### 认知科学
- **MBCT 正念认知疗法** — 神经改写三步：激活→改写→重复

### 中华哲学 · 减法疗愈理论三角
- **庄子** — 为什么要放下（齐物论，"无用之用"）
- **清静经** — 怎么放下（观空，"内观其心，心无其心"）
- **王阳明** — 放下后怎么行动（致良知，"知行合一"）

## 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| 运行时 | Python 3 标准库 | 零外部依赖，部署极简 |
| 数据存储 | JSON 文件 | 用户数据本地化，隐私友好 |
| 通信协议 | MCP (Model Context Protocol) | 与 AI Agent 框架原生集成 |
| 框架 | Hermes Agent / OpenClaw SKILL | 原语即工具，即插即用 |
| 文档 | SDD (Specification-Driven Development) | 需求→架构→验收的完整追踪 |

---

<a name="english"></a>

## English

### ✨ Features

- 🧠 **Theory Triangle**: Zhuangzi (why let go) → Jingjing Jing (how to let go) → Wang Yangming (how to act after letting go)
- 📐 **Primitive Architecture**: 9 JSON-in/JSON-out primitives replace manual LLM file reads — deterministic behavior + high information density
- 🔗 **Native MCP Integration**: Embeds into Hermes Agent via Model Context Protocol — plug and play
- 📊 **PERMA + VIA Quantification**: 5-dimension well-being × 24 character strengths — awareness becomes trackable and reviewable
- 🎯 **Four-State Detection**: Can't stop / Can't start / Pushing through / Always searching — auto-detect + differentiated guidance
- 🔥 **Streak System**: Consecutive awareness day tracking + milestone rewards (Seed → Sprout → Growth → Flourish → Bloom)
- 📈 **Weekly Insight Reports**: Cross-session pattern analysis — PERMA trends + state transitions + rewrite effects + minimal adjustment suggestions
- 🛡️ **Zero Dependencies**: Python stdlib + JSON file storage, deploy and run

### Core Architecture

**Primitive System** — L1 Perception → L2 Action → MCP Integration

| Layer | Primitive | Purpose |
|-------|-----------|---------|
| L1 | `awareness_profile` | Load awareness profile (PERMA baseline, signature strengths, streak) |
| L1 | `awareness_journal_query` | Query history (PERMA trends, state sequences, rewrite events) |
| L1 | `awareness_state_detect` | Four-state detection (Can't stop / Can't start / Pushing through / Always searching) |
| L2 | `awareness_guide` | Context assembly + strategy decision (core guidance engine) |
| L2 | `awareness_record` | Structured recording + streak update + profile increment |
| L2 | `awareness_intervention` | Intervention engine (quality trend + flags + streak risk) |
| L2 | `awareness_pattern_review` | Cross-session pattern analysis (automated weekly insight engine) |
| L2 | `awareness_quality_score` | Session quality scoring (depth/completeness/rewrite quality/data quality/engagement) |
| MCP | `mcp_server` | Hermes MCP integration, primitives as tools |

### Quick Start

```bash
git clone https://github.com/Milesnee/awareness-agent.git
cd awareness-agent

# Get guidance context (Morning Round 1)
echo '{"user_id":"demo","period":"morning","round":1,"user_name":"Xiaocheng"}' \
  | python3 scripts/awareness_guide.py --demo

# Load user profile
echo '{"user_id":"demo"}' | python3 scripts/awareness_profile.py

# State detection
echo '{"text":"I procrastinated again, scrolled on my phone all morning"}' \
  | python3 scripts/awareness_state_detect.py

# View awareness trends (last 7 days)
echo '{"user_id":"demo","timespan":"7d"}' \
  | python3 scripts/awareness_journal_query.py
```

### Conversation Example

```
[Morning Guidance] 🌅 Round 1/5

Xiaocheng: Good morning. What is your inner anchor today?

User: I want to focus on coding, but I feel a bit anxious.

Xiaocheng: I sense the anxiety. Anxiety itself is not the problem —
your attitude toward it is what matters. What is this anxiety saying?
Is it afraid you'll write something, or afraid you won't?

User: ...afraid it won't be good enough.

Xiaocheng: Good, that's awareness. Take it with you and start working.
It doesn't need to disappear.
```

### Theoretical Foundations

#### Positive Psychology
- **PERMA Model** (Seligman, 2011) — Positive Emotion(P), Engagement(E), Relationships(R), Meaning(M), Accomplishment(A)
- **VIA Character Strengths** (Peterson & Seligman, 2004) — Classification and measurement of 24 character strengths

#### Cognitive Science
- **MBCT (Mindfulness-Based Cognitive Therapy)** — Neural rewriting in 3 steps: Activate → Rewrite → Repeat

#### Eastern Philosophy · Subtractive Healing Theory Triangle
- **Zhuangzi** — Why let go (Qi Wu Lun, "the usefulness of the useless")
- **Jingjing Jing (Classic of Purity and Stillness)** — How to let go (contemplating emptiness, "observe the mind, the mind has no self")
- **Wang Yangming** — How to act after letting go (extending innate knowing, "unity of knowledge and action")

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Runtime | Python 3 stdlib | Zero external deps, minimal deployment |
| Storage | JSON files | Local-first, privacy-friendly |
| Protocol | MCP (Model Context Protocol) | Native integration with AI Agent frameworks |
| Framework | Hermes Agent / OpenClaw SKILL | Primitives as tools, plug and play |
| Docs | SDD (Specification-Driven Development) | Full traceability: requirements → architecture → acceptance |

---

## License

[MIT](LICENSE) © 2026 Milesnee
