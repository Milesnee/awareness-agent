#!/usr/bin/env python3
"""
awareness_intervention — L3 primitive: decide if/how to change guidance behavior.

The most "meta" primitive: the system observes its own interaction quality
and decides whether to adjust its approach — tone, frequency, depth.

Usage:
  echo '{"user_id":"laomai","quality_trend":[0.75,0.70,0.65,0.55]}' \
    | python3 awareness_intervention.py

Input:
{
  "user_id": str,
  "quality_trend": [0.75, 0.70, 0.65, 0.55],  // last N session quality scores
  "flags": ["连续2天晚间缺失", "E持续偏低"],
  "streak_current": 3,
  "streak_at_risk": true
}

Output:
{
  "intervention_needed": true,
  "level": "gentle",           // gentle | firm | crisis
  "action": "shift_tone",       // shift_tone | reduce_rounds | pause_push | escalate
  "suggested_approach": "...",
  "dont_do": [...],
  "escalation_rule": "..."
}
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STREAKS_DIR = DATA_DIR / "streaks"
JOURNALS_DIR = DATA_DIR / "journals"


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def compute_intervention(
    quality_trend: list[float],
    flags: list[str],
    streak_current: int,
    streak_risk: bool,
) -> dict:
    """Core decision logic."""
    intervention_needed = False
    level = "gentle"
    action = None
    reasons = []

    # ── Quality degradation detection ──────────────────────────
    if len(quality_trend) >= 3:
        # Check for consistent decline
        if quality_trend[-1] < 0.5:
            intervention_needed = True
            level = "firm"
            reasons.append(f"最近一次质量评分过低({quality_trend[-1]})")

        declining = all(
            quality_trend[i] > quality_trend[i + 1]
            for i in range(len(quality_trend) - 1)
        )
        if declining:
            intervention_needed = True
            if quality_trend[0] - quality_trend[-1] > 0.2:
                level = "firm"
                reasons.append(f"质量连续下降({quality_trend[0]}→{quality_trend[-1]})")
            else:
                level = "gentle"
                reasons.append(f"质量轻微下降({quality_trend[0]}→{quality_trend[-1]})")

    # ── Flag-driven intervention ───────────────────────────────
    has_missing_evening = any("晚间缺失" in f or "missing_evening" in f for f in flags)
    has_low_dimension = any("偏低" in f or "low_dimension" in f for f in flags)
    has_no_rewrite = any("无改写" in f or "no_rewrite" in f for f in flags)

    if has_missing_evening and streak_current >= 3:
        intervention_needed = True
        reasons.append("连续缺失晚间复盘 + streak≥3——觉察疲劳可能")
        action = "reduce_rounds"

    if has_low_dimension and not has_missing_evening:
        intervention_needed = True
        reasons.append("某维度持续偏低——需要调整引导焦点")
        action = "shift_focus"

    if has_no_rewrite:
        intervention_needed = True
        level = "firm" if len(flags) >= 3 else "gentle"
        reasons.append("长期无改写事件——引导深度不足")
        action = "deepen_rewrite_guidance"

    # ── Streak risk ────────────────────────────────────────────
    if streak_risk and streak_current >= 5:
        intervention_needed = True
        level = max(level, "firm")
        reasons.append("长streak面临中断风险——需要轻度干预")

    # ── No issues ──────────────────────────────────────────────
    if not intervention_needed:
        return {
            "intervention_needed": False,
            "level": "none",
            "action": None,
            "suggested_approach": "当前互动质量良好，保持现有策略。",
            "dont_do": [],
            "escalation_rule": None,
            "reasons": ["各指标在正常范围"],
        }

    # ── Determine action ──────────────────────────────────────
    if action is None:
        if level == "firm":
            action = "shift_tone"
        else:
            action = "light_adjust"

    # ── Build approach ────────────────────────────────────────
    approaches = {
        "reduce_rounds": {
            "suggested": "减少引导轮数：晨间从3轮减为2轮，晚间从5轮减为3轮。更轻、更短、更低压力。",
            "dont_do": ["追问深度问题", "强调连续天数", "用'你该...'句式"],
            "escalation": "如果连续3天仍无晚间复盘，暂停晚间推送1天，改为次日晨间合并回顾。",
        },
        "shift_focus": {
            "suggested": "调整晨间引导焦点：从'锚点设定'转向'今日最小可行一步'——更具体、更低门槛。",
            "dont_do": ["问抽象的'意义感'问题", "比较用户与过去的自己"],
            "escalation": "如果该维度又持续3天无改善，启动L3 pattern_review做专门分析。",
        },
        "deepen_rewrite_guidance": {
            "suggested": "晚间Round 2增加具体的改写提示：'今天有没有一个瞬间，你做了和平时不一样的选择？哪怕很小。'",
            "dont_do": ["接受'没有改写'作为正常", "跳过Round 2直接打分"],
            "escalation": "如果3天内仍无改写，在晨间增加'预演'环节：'今天可能触发老反应的是什么？'",
        },
        "shift_tone": {
            "suggested": "语气转向更轻盈：减少理论引用，增加口语化。多用'聊聊'替代'觉察'。",
            "dont_do": ["用PERMA术语", "问多于2个问题", "引用Huberman/EBP理论"],
            "escalation": "如果质量继续下降，暂停1天推送，让用户有空间。",
        },
        "light_adjust": {
            "suggested": "微调：在引导结尾增加一句'今天不用想太多，随便聊聊就好'，降低心理门槛。",
            "dont_do": [],
            "escalation": None,
        },
    }

    approach = approaches.get(action, approaches["light_adjust"])

    return {
        "intervention_needed": True,
        "level": level,
        "action": action,
        "suggested_approach": approach["suggested"],
        "dont_do": approach["dont_do"],
        "escalation_rule": approach["escalation"],
        "reasons": reasons,
    }


def main():
    raw = ""
    if len(sys.argv) >= 3 and sys.argv[1] == "--data":
        raw = sys.argv[2]
    elif not sys.stdin.isatty():
        for line in sys.stdin:
            raw += line

    if not raw.strip():
        raw = "{}"

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}, ensure_ascii=False))
        sys.exit(1)

    quality_trend = params.get("quality_trend", [])
    flags = params.get("flags", [])
    streak_current = params.get("streak_current", 0)
    streak_risk = params.get("streak_at_risk", False)

    result = compute_intervention(quality_trend, flags, streak_current, streak_risk)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
