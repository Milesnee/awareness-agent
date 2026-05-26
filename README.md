# 小澄觉察助手（Awareness Guide）

> *不逃离，回来。*

AI 驱动的觉察引导系统，帮用户逐步找到并建立稳定的内核。

底层哲学：**减法疗愈** — 不是塞更多道理，是帮用户看见遮盖住本有注意力的东西。
理论三角：庄子（为什么要放下）→ 清静经（怎么放下）→ 王阳明（放下后怎么行动）。

## 核心架构

**原语系统（Primitives）**：脚本化 JSON-in/JSON-out 接口，替代 LLM 手工读文件。

| 层 | 原语 | 脚本 | 作用 |
|----|------|------|------|
| L1 | `awareness_profile` | `scripts/awareness_profile.py` | 加载觉察档案 |
| L1 | `awareness_journal_query` | `scripts/awareness_journal_query.py` | 历史觉察查询 |
| L1 | `awareness_state_detect` | `scripts/awareness_state_detect.py` | 四状态识别 |
| L2 | `awareness_guide` | `scripts/awareness_guide.py` | 上下文装配 + 策略决策 |
| L2 | `awareness_record` | `scripts/awareness_record.py` | 结构化记录 + streak |
| L2 | `awareness_intervention` | `scripts/awareness_intervention.py` | 干预决策引擎 |
| L2 | `awareness_pattern_review` | `scripts/awareness_pattern_review.py` | 跨时段模式分析 |
| L2 | `awareness_quality_score` | `scripts/awareness_quality_score.py` | 对话质量评分 |
| MCP | `mcp_server` | `scripts/mcp_server.py` | Hermes MCP 集成 |

## 快速开始

```bash
# 获取引导上下文
echo '{"user_id":"laomai","period":"morning","round":1,"user_name":"老麦"}' \
  | python3 scripts/awareness_guide.py --demo

# 加载档案
echo '{"user_id":"laomai"}' | python3 scripts/awareness_profile.py

# 识别状态
echo '{"text":"今天又拖延了，刷了一上午手机"}' \
  | python3 scripts/awareness_state_detect.py
```

## 项目结构

```
awareness-agent/
├── scripts/           # 原语脚本
├── data/              # 用户数据（gitignored）
│   ├── profiles/      # 用户档案
│   ├── journals/      # 觉察日记
│   └── streaks/       # 连续天数追踪
├── docs/              # 项目文档
│   ├── SDD.md         # 规范文档
│   ├── IMPLEMENT.md   # 实施追踪
│   ├── 项目介绍.md     # 产品定位
│   └── adr/           # 架构决策记录
└── references/        # 参考资料
    ├── CONTEXT.md     # 领域术语表
    ├── examples.md    # 对话示例
    └── primitive-design.md  # 原语架构设计
```

## 理论基础

- **PERMA 模型**（Seligman, 2011）— 五维幸福度量
- **VIA 品格优势**（Peterson & Seligman, 2004）— 24项优势
- **MBCT 正念认知疗法** — 神经改写：激活→改写→重复
- **庄子→清静经→王阳明** — 减法疗愈理论三角

## 技术栈

Python 标准库 · JSON 文件存储 · 零外部依赖 · Hermes Agent / OpenClaw SKILL 框架
