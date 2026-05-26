# Hermes 觉察助手（Awareness Guide）

> 基于PERMA幸福模型 + 24项品格优势 + 心神合一理论的AI觉察伴侣
> 版本：0.1.0 MVP

## 项目结构

```
hermes-awareness/
├── README.md                          ← 你正在读
├── skills/
│   └── awareness-guide/               ← 核心：对话引擎
│       ├── SKILL.md                   ← 对话引导逻辑 + prompt模板
│       ├── CONTEXT.md                 ← 领域术语表（防止概念歧义）
│       └── references/
│           ├── perma-model.md         ← PERMA五维评分标准
│           └── character-strengths.md ← 24项品格优势完整列表
├── scripts/
│   ├── profile_manager.py             ← 用户Profile管理
│   └── journal_manager.py             ← 每日觉察记录管理
├── data/
│   ├── profiles/
│   │   └── example_user.json          ← 示例Profile（已匿名）
│   └── journals/
│       └── 2026-05-11.json            ← 示例觉察记录（已匿名）
└── docs/
    └── adr/                           ← 架构决策记录
        ├── 001-skill-driven.md
        ├── 002-json-over-sqlite.md
        └── 003-progressive-init.md
```

## 快速开始

### 1. 初始化用户Profile

```bash
python3 scripts/profile_manager.py init --user <user_id> --nickname "用户昵称"
```

### 2. 晨间觉察（~3轮对话）

流程：读取Profile + 今日Journal → 按SKILL.md模板引导 → 保存记录

```bash
# 读取用户状态
python3 scripts/profile_manager.py get --user <user_id>
python3 scripts/journal_manager.py get --date YYYY-MM-DD

# 对话结束后保存
python3 scripts/journal_manager.py save --date YYYY-MM-DD --period morning \
  --data '{"sleep_quality": "...", "today_intention": "...", "mindfulness_anchor": "..."}'

# 更新streak和里程碑
python3 scripts/profile_manager.py milestone --user <user_id>
```

### 3. 晚间觉察（~5轮对话）

流程同上，period改为evening，提取更多结构化数据

```bash
python3 scripts/journal_manager.py save --date YYYY-MM-DD --period evening \
  --data '{"presence_moments": [], "emotion_awareness": "...", "strengths_used": [], "gratitude": [], "perma_rating": {"P": 7, "E": 6, "R": 5, "M": 7, "A": 8}}'
```

### 4. 查看趋势

```bash
# 连续天数
python3 scripts/profile_manager.py streak --user <user_id>

# PERMA趋势
python3 scripts/journal_manager.py history --days 7
```

## 理论基础

### 三位一体

| 层次 | 作用 | 文件 |
|------|------|------|
| PERMA幸福模型 | 量化刻度（1-10分五维评分） | `references/perma-model.md` |
| 24项品格优势 | 行为词汇（命名用户调用的力量） | `references/character-strengths.md` |
| 心神合一 | 实践锚点（全情投入的瞬间） | 融入SKILL.md对话模板 |

### 核心设计：微小正反馈系统

觉察本身是反人性的，必须用行为心理学让用户**愿意回来**：

- **即时认可**：具体点出用户做到了什么（不说"你很棒"）
- **进度量化**：连续天数、本周完成度、PERMA趋势、品格优势调用次数
- **里程碑等级**：🌱种子 → 🌿发芽 → 🌳成长 → 🎋茂盛 → 🌸绽放
- **每次对话结尾**带进度提示，像游戏NPC

## 对话模板摘要

### 晨间（3轮）
1. 早安 + 睡眠 + "今天有什么事全情投入？"
2. 认可回复 + 引导PERMA某维度
3. 设小意图 + 正反馈 + 进度

### 晚间（5轮）
1. "有几个瞬间完全沉浸在当下？" + "有没有焦虑未来或反刍过去？"
2. 情绪觉察（"谁在XX？"技巧）
3. 品格优势识别
4. PERMA五维评分
5. 感恩 + 正反馈 + 进度

> ⚠️ 完整模板见 `SKILL.md`，不要对新用户用术语，建立关系后再引入

## 数据格式

### Profile（用户画像）
```json
{
  "user_id": "example_user",
  "persona": {"nickname": "...", "life_context": "..."},
  "perma_baseline": {"P": {"score": null}, ...},
  "character_strengths": {"signature": [], "usage_count": {}},
  "progress": {"current_streak": 0, "milestones_unlocked": []}
}
```

### Journal（每日觉察）
```json
{
  "date": "2026-05-11",
  "morning": {
    "sleep_quality": "...", "today_intention": "...",
    "mindfulness_anchor": "...", "perma_check": {"P": null, ...},
    "extracted_insights": []
  },
  "evening": {
    "presence_moments": [], "distraction_moments": [],
    "emotion_awareness": "...", "strengths_used": [],
    "gratitude": [], "perma_rating": {"P": 7, ...},
    "extracted_insights": []
  }
}
```

## 迁移到 Hermes-Agent 的注意事项

1. **SKILL.md 是核心** — 对话逻辑全在这里，Hermes加载这个文件即可驱动
2. **脚本独立运行** — `profile_manager.py` 和 `journal_manager.py` 不依赖OpenClaw，纯Python + JSON
3. **CONTEXT.md 须同步** — 术语表是对话一致性的保障，放在SKILL同级目录
4. **references 按需加载** — PERMA和品格优势资料较大，只在需要时读取
5. **数据目录结构保持** — `data/profiles/` + `data/journals/`，脚本里用相对路径
6. **心跳/定时触发** — Hermes有自己的调度机制，参照SKILL.md中的晨间08:00/晚间21:30

## 依赖

- Python 3.10+
- 无第三方依赖（纯标准库）

## License

MIT
