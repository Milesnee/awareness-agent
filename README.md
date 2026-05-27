# 小澄觉察助手（Awareness Guide）

<p align="center">
  <b>不逃离，回来。</b>
</p>

<p align="center">
  <b>AI 驱动的觉察引导系统</b> — 基于积极心理学 + 中华哲学减法疗愈框架<br>
  <a href="#理论基础">PERMA · VIA · MBCT · 庄子→清静经→王阳明</a>
</p>

---

> 不是冥想 App，不是时间管理工具。帮用户逐步找到并建立稳定的内核。

**小澄觉察助手**是一个零外部依赖、纯 JSON 原语架构的 AI 觉察引导系统。通过 9 个专用原语（Primitives）实现上下文感知的对话引导、结构化觉察记录、连续天数追踪和跨时段模式分析。

底层哲学：**减法疗愈** — 不是塞更多道理，是帮用户看见遮盖住本有注意力的东西。

## ✨ 特色

- 🧠 **理论三角**：庄子（为什么要放下）→ 清静经（怎么放下）→ 王阳明（放下后怎么行动）
- 📐 **原语架构**：9 个 JSON-in/JSON-out 原语替代 LLM 手工读文件，确定性行为 + 高信息密度
- 🔗 **MCP 原生集成**：通过 Model Context Protocol 嵌入 Hermes Agent，即插即用
- 📊 **PERMA + VIA 量化**：五维幸福度量 × 24 项品格优势，觉察可追踪、可回顾
- 🎯 **四状态识别**：停不下来 / 启动不了 / 硬撑着 / 一直在找 — 自动检测 + 差异化引导
- 🔥 **Streak 机制**：连续觉察天数追踪 + 里程碑奖励系统（种子→发芽→成长→茂盛→绽放）
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

## 项目结构

```
awareness-agent/
├── scripts/           # 9 个原语脚本 + MCP server
├── data/              # 用户数据（gitignored）
│   ├── profiles/      # 用户觉察档案
│   ├── journals/      # 觉察日记（JSON）
│   └── streaks/       # 连续天数追踪
├── docs/
│   ├── SDD.md         # 规范文档（需求/架构/验收标准）
│   ├── IMPLEMENT.md   # 实施追踪
│   ├── 项目介绍.md     # 产品定位
│   └── adr/           # 架构决策记录
├── references/
│   ├── CONTEXT.md     # 领域术语表
│   ├── examples.md    # 对话示例
│   └── primitive-design.md  # 原语架构设计文档
└── skills/            # OpenClaw / Hermes SKILL 定义
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

## License

[MIT](LICENSE) © 2026 Milesnee
