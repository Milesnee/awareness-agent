# 觉察助手 · 专用原语架构设计

> 2026-05-21 | 小麦 🌾 | v1.0

基于 Hermes Agent 原语设计理念（L1感知/L2行动/L3元认知），为觉察助手设计的 9 个专用原语。

---

## 设计原则

| 原则 | 含义 | 实施 |
|------|------|------|
| 最小惊奇 | 行为可预测，LLM 不需猜测效果 | 每个原语有明确 JSON schema |
| 组合优于覆盖 | 用少量原语组合应对长尾场景 | 9 个原语覆盖全流程，不新增专用工具 |
| 信息密度不对称 | 输入简练，输出丰富 | 一次调用替代 3-5 次 `read_file` + `terminal` |
| 幂等性 | 可安全重复调用 | `user_id+date+period` 天然唯一键 |

---

## L1 感知层 — 系统"看到"用户什么

### 1. `awareness_profile` — 觉察档案加载

```
输入: user_id
输出: {streak, signature_strengths, perma_baseline, milestone, preferences}
```

**价值**：替代 3-5 次手工文件读取。信息密度从 raw JSON → 结构化摘要。

**状态**：`awareness_guide` 原语内部调用，暂未独立暴露。

### 2. `awareness_journal_query` — 历史觉察查询

```
输入: user_id, timespan, dimensions
输出: {perma_trend, state_sequence, strength_calls, rewrite_events, gaps}
```

**价值**：周洞察复盘的输入源。"从原始数据到洞察素材"的转换在系统层完成。

**状态**：`awareness_guide` 原语内部调用 `compute_recent_patterns()`。

### 3. `awareness_state_detect` — 状态识别

```
输入: user_input (自然语言)
输出: {primary_state, confidence, signals, suggested_approach}
```

识别四种状态（停不下来/启动不了/硬撑着/一直在找），带置信度。

**状态**：🟡 设计完成，待实现。当前靠 LLM 读 skill 描述手工判断。

---

## L2 行动层 — 系统对用户"做"什么

### 4. `awareness_guide` — 引导上下文装配

```
输入: {user_id, period, round, user_reply?}
输出: {context: {profile_summary, recent_patterns, streak, flags},
        decision: {focus_dimension, approach, science_hooks, dont_do, template_hint},
        suggested_question: "..."}  // --demo 模式
```

**已实现** ✅ — `scripts/awareness_guide.py`

### 5. `awareness_record` — 结构化记录保存

```
输入: {user_id, date, period, extracted: {perma, strengths, ...}, session_meta}
输出: {saved, streak_updated, data_quality, new_insight_triggers}
```

自动完成：schema校验 → 保存journal → 更新streak → 更新profile → 检测趋势触发。

**已实现** ✅ — `scripts/awareness_record.py`

### 6. `awareness_rewrite_surface` — 改写机会识别

```
输入: {user_id, emotional_statement, today_states, history}
输出: {rewrite_opportunity: {old_reaction, suggested_new_response, guiding_question},
        history_match: {what_worked_before}}
```

**价值**：把"改写识别"从对话生成中解耦——同一个改写机会可以用不同风格呈现，可 A/B 测试。

**状态**：🟡 设计完成，待实现。

---

## L3 元认知层 — 系统"学到"什么

### 7. `awareness_pattern_review` — 跨时段模式分析

```
输入: user_id, timespan, dimensions
输出: {perma_changes, state_transitions, rewrite_effectiveness,
        hypotheses: [{condition, outcome, confidence, data_points}],
        minimal_adjustments: [...]}
```

**价值**：周洞察报告的自动化引擎。输出可直接消费——LLM 只需润色语言，不需手工分析数据。

**状态**：🟡 设计完成，待实现。

### 8. `awareness_quality_score` — 对话质量评估

```
输入: session_data
输出: {overall: 0.78, dimensions: {depth, completeness, rewrite_quality, ...}}
```

**价值**：系统知道自己什么时候在"敷衍"（用户回复越来越短），触发引导策略调整。可作 A/B 测试 dependent variable。

**状态**：🟡 设计完成，待实现。

### 9. `awareness_intervention` — 干预决策

```
输入: {user_id, current_state, quality_trend, streak_risk}
输出: {intervention_needed, level: "gentle"|"firm"|"crisis",
        suggested_approach, dont_do, escalation_rule}
```

**价值**：系统观察自己与用户的互动质量，决定是否改变行为。类比自动驾驶监控传感器。

**状态**：🟡 设计完成，待实现。

---

## 原语组合：一次完整的晨间觉察

```
1. awareness_guide(period=morning, round=1) → context + question
2. [用户回复]
3. awareness_guide(period=morning, round=2, user_reply=...) → context
4. [用户回复]
5. awareness_guide(period=morning, round=3, user_reply=...) → context
6. awareness_record(period=morning, extracted={...}) → streak + quality + triggers
```

**对比旧版**：LLM 通读 300 行 skill → 9 次原语调用。LLM 只做"决策"和"对话生成"，不做"数据理解"和"规则推理"。

---

## 实施路径

| 阶段 | 内容 | 状态 |
|------|------|------|
| v1 | L2 核心：`awareness_record` + `awareness_guide` | ✅ 完成 |
| v2 | L1 全部：`profile` + `journal_query` + `state_detect` | 待实现 |
| v3 | L3 全部：`pattern_review` + `quality_score` + `intervention` | 待实现 |
| v4 | 注册为 Hermes 原生 toolset | 待实现 |

---

## 文件结构

```
projects/awareness-agent/
├── scripts/
│   ├── awareness_record.py    # L2: 结构化记录 + streak + 质量校验
│   ├── awareness_guide.py     # L2: 上下文感知引导生成
│   └── test_e2e.py            # 端到端测试
├── data/
│   ├── journals/{uid}/        # {date}_{period}.json
│   ├── profiles/{uid}.json    # PERMA基线 + 签名优势
│   └── streaks/{uid}.json     # 连续天数 + 里程碑
├── docs/
│   └── service-account-prototype-v1.md
└── references/ (via skill)
    └── primitive-design.md    # 本文档
```
