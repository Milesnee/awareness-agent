# OpenClaw 互动追踪

觉察助手通过 OpenClaw 与用户互动，记录互动数据有双重价值：
1. **用户洞察** — 了解用户的觉察习惯（频率、时段、持续时长），个性化引导
2. **产品迭代** — 量化觉察助手的使用情况，评估效果

## 追踪指标

| 指标 | 说明 | 用途 |
|------|------|------|
| 日期/时段 | morning/evening | 习惯规律分析 |
| 对话轮数 | Round 1-N 的数量 | 引导深度评估 |
| 互动时长 | 从首条到末条（秒） | 投入度参考 |
| 触发方式 | heartbeat/manual | 主动性分析 |
| 模型 | 使用的LLM | 效果差异追踪 |
| PERMA完成度 | 5个维度是否都打分 | 数据质量指标 |
| 改写确认 | 是否有新反应记录 | 效果验证 |

## 嵌入对话流程

**对话开始**（Round 1 前）：记录 `start_time = time.time()`

**对话结束**（最后一个Round后）：
```bash
python3 projects/awareness-agent/scripts/session_tracker.py log \
  --user {user_id} --date {date} --rounds {n} \
  --duration {seconds} --trigger {heartbeat|manual}
```

## 统计输出示例
```
📊 觉察互动周报 (5/8 - 5/14)
- 完成率: 晨间 6/7 (86%) | 晚间 5/7 (71%)
- 平均轮数: 晨间 3.2轮 | 晚间 4.8轮
- 平均时长: 晨间 45秒 | 晚间 90秒
- 最活跃时段: 08:00-08:30 (晨间), 21:30-22:00 (晚间)
- PERMA完整率: 71% (5/7天完成了5维度评分)
- 触发方式: heartbeat 80% | manual 20%
- 模型分布: GLM-5-Turbo 60% | Claude 40%
```

## 数据存储位置
- 互动记录：`projects/awareness-agent/data/sessions/{date}.json`
- 聚合统计：`projects/awareness-agent/data/stats/weekly.json` / `monthly.json`
