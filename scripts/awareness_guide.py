#!/usr/bin/env python3
"""
awareness_guide — L2 primitive: context-aware guidance generator.

Assembles profile + history + quality context so the LLM can generate
a personalized guide question without reading raw data files.

Usage:
  echo '{"user_id":"test","period":"morning","round":1}' \
    | python3 awareness_guide.py

  # With user reply context (for rounds 2+):
  echo '{"user_id":"test","period":"morning","round":2,"user_reply":"..."}' \
    | python3 awareness_guide.py

  # Demo mode: also generates example question text
  echo '{"user_id":"test","period":"morning","round":1}' \
    | python3 awareness_guide.py --demo

Input schema (JSON via stdin):
{
  "user_id": str,
  "period": "morning" | "evening",
  "round": 1-5,
  "user_reply": "...",           // optional, for rounds 2+
  "user_name": "老麦",           // optional, defaults from profile
  "date": "2026-05-21"           // optional, defaults to today
}

Output (JSON to stdout):
{
  "context": {
    "profile_summary": {...},    // distilled profile for LLM consumption
    "recent_patterns": {...},    // patterns from last 7 days
    "state_context": {...},      // current state (if detectable from user_reply)
    "intervention_flags": [...]  // warnings / adjustments needed
  },
  "decision": {
    "focus_dimension": "E",      // which PERMA dimension to focus on
    "approach": "anchor_first",  // guidance strategy
    "tone": "warm",              // default | warm | gentle | firm
    "science_hooks": [...],      // applicable Huberman/EBP insights
    "dont_do": [...],            // things to avoid in this session
    "template_hint": "..."       // structural hint for question framing
  },
  "suggested_question": "..."    // only with --demo flag
}
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOURNALS_DIR = DATA_DIR / "journals"
PROFILES_DIR = DATA_DIR / "profiles"
STREAKS_DIR = DATA_DIR / "streaks"

PERMA_DIMS = ["P", "E", "R", "M", "A"]


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def load_profile(user_id: str) -> dict:
    return load_json(PROFILES_DIR / f"{user_id}.json") or {}


def load_streak(user_id: str) -> dict:
    return load_json(STREAKS_DIR / f"{user_id}.json") or {}


def load_recent_journals(user_id: str, days: int = 7) -> list[dict]:
    """Load journal entries from the last N days."""
    user_dir = JOURNALS_DIR / user_id
    if not user_dir.exists():
        return []

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    entries = []
    for f in sorted(user_dir.glob("*.json"), reverse=True):
        try:
            d = load_json(f)
            if d and d.get("date", "") >= cutoff:
                entries.append(d)
        except Exception:
            continue
    # Sort chronologically
    entries.sort(key=lambda e: e.get("date", ""))
    return entries


def compute_recent_patterns(entries: list[dict]) -> dict:
    """Extract patterns from recent journal entries."""
    if not entries:
        return {"available": False, "message": "无历史觉察记录", "days_recorded": 0}

    perma_series = []
    states = []
    rewrites = []
    gaps = {"morning": [], "evening": []}

    for e in entries:
        # PERMA
        p = e.get("extracted", {}).get("perma", {})
        if all(dim in p for dim in PERMA_DIMS):
            perma_series.append({"date": e["date"], "period": e.get("period"), "perma": p})

        # Emotional state
        emotion = e.get("extracted", {}).get("emotional_arc")
        if emotion and emotion.get("dominant"):
            states.append({"date": e["date"], "period": e.get("period"), "state": emotion["dominant"]})

        # Rewrite events
        rewrite = e.get("extracted", {}).get("rewrite_event")
        if rewrite and rewrite.get("occurred"):
            rewrites.append({
                "date": e["date"],
                "old": rewrite.get("old_pattern"),
                "new": rewrite.get("new_response"),
                "technique": rewrite.get("technique"),
            })

    # Find gap pattern: which dates have morning but no evening (or vice versa)
    dates_seen = set()
    date_periods = {}
    for e in entries:
        d = e["date"]
        p = e.get("period")
        dates_seen.add(d)
        date_periods.setdefault(d, {})[p] = True

    for d in sorted(dates_seen):
        periods = date_periods.get(d, {})
        if "morning" in periods and "evening" not in periods:
            gaps["evening"].append(d)
        if "evening" in periods and "morning" not in periods:
            gaps["morning"].append(d)

    # PERMA trend (last 5 entries)
    perma_trends = {}
    if len(perma_series) >= 3:
        for dim in PERMA_DIMS:
            vals = [p["perma"][dim] for p in perma_series[-5:]]
            if len(vals) >= 3:
                trend = "up" if vals[-1] > vals[0] + 1 else ("down" if vals[-1] < vals[0] - 1 else "flat")
                perma_trends[dim] = {
                    "trend": trend,
                    "latest": vals[-1],
                    "average": round(sum(vals) / len(vals), 1),
                    "min": min(vals),
                    "max": max(vals),
                }

    return {
        "available": True,
        "days_recorded": len(set(e["date"] for e in entries)),
        "total_entries": len(entries),
        "perma_trends": perma_trends,
        "recent_states": states[-5:] if states else [],
        "recent_rewrites": rewrites[-3:] if rewrites else [],
        "gaps": gaps,
        "last_entry": entries[-1]["date"] if entries else None,
    }


def decide_focus_dimension(profile: dict, patterns: dict, period: str, round_num: int) -> dict:
    """Decide which PERMA dimension to focus on and what strategy to use."""
    perma_trends = patterns.get("perma_trends", {})

    # Strategy selection
    if period == "morning" and round_num == 1:
        # Morning Round 1: always start with E (engagement / anchor setting)
        return {
            "focus_dimension": "E",
            "approach": "anchor_first",
            "reasoning": "晨间首轮始终聚焦投入锚点——心神合一是核心",
            "template_hint": "问候 + 睡眠 + 全情投入锚点",
        }

    if period == "morning" and round_num >= 2:
        # Morning Round 2+: choose based on what's low
        if perma_trends:
            lowest = min(perma_trends.items(), key=lambda x: x[1]["latest"])
            if lowest[1]["latest"] <= 5:
                return {
                    "focus_dimension": lowest[0],
                    "approach": "gentle_probe",
                    "reasoning": f"{lowest[0]}近期偏低({lowest[1]['latest']})，温和引导关注",
                    "template_hint": f"具体认可 + 引入{lowest[0]}维度觉察",
                }

    if period == "evening" and round_num == 1:
        return {
            "focus_dimension": "E",
            "approach": "review_anchor",
            "reasoning": "晚间首轮回顾晨间锚点——身心俱在的时刻",
            "template_hint": "问候 + 心神合一回顾 + 今日状态识别",
        }

    if period == "evening" and round_num == 2:
        return {
            "focus_dimension": "P",
            "approach": "emotion_rewrite",
            "reasoning": "情绪觉察 + 旧反应改写",
            "template_hint": "情感觉察 + 改写引导('谁在XX？')",
        }

    if period == "evening" and round_num == 3:
        return {
            "focus_dimension": "R",
            "approach": "strength_recognition",
            "reasoning": "品格优势识别 + 新反应确认",
            "template_hint": "引导识别优势 + 与新反应关联",
        }

    if period == "evening" and round_num == 4:
        return {
            "focus_dimension": "ALL",
            "approach": "quantify",
            "reasoning": "PERMA评分——循证数据采集",
            "template_hint": "五维度直觉打分(1-10)",
        }

    # Default
    chosen = "M"
    if perma_trends:
        lowest = min(perma_trends.items(), key=lambda x: x[1]["latest"])
        chosen = lowest[0]

    return {
        "focus_dimension": chosen,
        "approach": "adaptive",
        "reasoning": f"基于趋势选择最低维度{chosen}",
        "template_hint": "自适应引导",
    }


def detect_intervention_flags(profile: dict, patterns: dict, streak: dict) -> list[dict]:
    """Detect conditions that require intervention."""
    flags = []

    streak_current = streak.get("current", 0)
    gaps = patterns.get("gaps", {})

    # Consecutive missing evenings
    evening_gaps = gaps.get("evening", [])
    if len(evening_gaps) >= 2:
        flags.append({
            "level": "gentle",
            "type": "missing_evening",
            "detail": f"连续{len(evening_gaps)}天缺失晚间复盘（{', '.join(evening_gaps[-3:])}）",
            "action": "晨间引导可简短些，减轻觉察压力",
        })

    # Streak at risk
    if streak_current >= 3 and len(evening_gaps) >= 1:
        flags.append({
            "level": "gentle",
            "type": "streak_at_risk",
            "detail": f"streak={streak_current}但晚间复盘不稳定",
            "action": "不强调streak压力，关注觉察本身的价值",
        })

    # PERMA dimension consistently low
    perma_trends = patterns.get("perma_trends", {})
    for dim, trend in perma_trends.items():
        if trend["latest"] <= 4 and trend["trend"] != "up":
            flags.append({
                "level": "firm" if trend["trend"] == "down" else "gentle",
                "type": "low_dimension",
                "detail": f"{dim}持续偏低({trend['latest']})，趋势{trend['trend']}",
                "action": f"引导关注{dim}维度的微小改善",
            })

    # No rewrites recently
    rewrites = patterns.get("recent_rewrites", [])
    if patterns.get("total_entries", 0) >= 5 and len(rewrites) == 0:
        flags.append({
            "level": "gentle",
            "type": "no_rewrite",
            "detail": "近期无改写事件",
            "action": "晚间引导中增强改写机会识别",
        })

    return flags


def select_science_hooks(flags: list[dict], period: str, round_num: int) -> list[dict]:
    """Select applicable science-backed insights."""
    hooks = []

    # Morning anxiety / energy
    if period == "morning" and round_num == 1:
        hooks.append({
            "trigger": "用户提到焦虑或精力差时可自然带入",
            "content": "试试起床后等一个半小时再喝咖啡，全天精力更平稳。",
            "source": "Huberman Lab",
        })
        hooks.append({
            "trigger": "用户提到难以专注",
            "content": "给自己一个90分钟的深度工作窗口——人体有超昼夜节律，体温上升期是效率峰值。",
            "source": "Huberman Lab",
        })

    if period == "morning" and round_num >= 2:
        hooks.append({
            "trigger": "用户设定了深度工作意图",
            "content": "今天最清醒的时段去冲刺那90分钟吧，体温上升期的效率是全天最高的。",
            "source": "Huberman Lab",
        })
        hooks.append({
            "trigger": "用户在多个任务间犹豫",
            "content": "直觉选——哪一个对用户影响最大，哪一个让你最开心，就做哪个。",
            "source": "Marc Lou",
        })
        hooks.append({
            "trigger": "用户追求完美犹豫不决",
            "content": "先质疑需求→删除→简化，不要急着加速和自动化。今天的任务真的需要做到完美吗？",
            "source": "Musk 五步法",
        })

    if period == "evening":
        hooks.append({
            "trigger": "用户提到拖延",
            "content": "带着不想做的感觉，做了一件事——哪怕只是打开了文档，这也是一种'不同'。",
            "source": "EBP 改写框架",
        })
        hooks.append({
            "trigger": "用户提到自我批评",
            "content": "你注意到自己在骂自己了，这个觉察本身，就是改写的开始。",
            "source": "MBCT",
        })

    return hooks


def determine_dont_do(flags: list[dict], period: str) -> list[str]:
    """Things to avoid given the current state."""
    donts = []

    for flag in flags:
        if flag["type"] == "missing_evening":
            donts.append("追问'为什么没做晚间复盘'")
            donts.append("强调streak数字")
        if flag["type"] == "streak_at_risk":
            donts.append("施加'必须坚持'的压力")
        if flag["type"] == "low_dimension":
            donts.append("用学术语言分析用户状态")
        if flag["type"] == "no_rewrite":
            donts.append("评价用户'没有进步'")

    # Universal don'ts
    donts.extend([
        "空洞表扬（'你很棒'）",
        "说教式建议",
        "灌鸡汤",
    ])

    return donts


def generate_demo_question(decision: dict, profile: dict, patterns: dict,
                            streak: dict, user_name: str, period: str,
                            round_num: int, user_reply: str = None) -> str:
    """Generate an example question for demo/testing purposes.
    In production, the LLM generates this from the context."""
    nickname = user_name or "朋友"
    streak_current = streak.get("current", 0)
    milestone_emoji = streak.get("milestone", "🌱")

    perma_trends = patterns.get("perma_trends", {})
    gaps = patterns.get("gaps", {})

    if period == "morning" and round_num == 1:
        # Check for E trend context
        e_trend = perma_trends.get("E", {})
        e_context = ""
        if e_trend.get("trend") == "down":
            e_context = f"注意到你这周投入感偏低（E≈{e_trend['latest']}），"
        elif e_trend.get("trend") == "flat" and e_trend.get("latest", 10) <= 6:
            e_context = "这几天心神合一的感觉似乎不太明显，"

        return (
            f"早安，{nickname}。🌅\n"
            f"{e_context}今天有什么事，你希望能做到全情投入、不被手机和杂念拉走？"
        )

    if period == "morning" and round_num == 2:
        return (
            f"嗯，我记下来了。{user_reply[:30] if user_reply else ''}\n"
            f"这个锚点很好——当你发现自己走神了，轻轻拉回来就好。不评判，只是拉回来。\n"
            f"🌱 觉察第{streak_current}天"
        )

    if period == "morning" and round_num == 3:
        return (
            f"那今天给自己一个小目标：发现走神时轻拉回来。晚上我们聊聊感觉如何。\n"
            f"🌱 觉察第{streak_current}天 | {milestone_emoji}"
        )

    if period == "evening" and round_num == 1:
        return (
            f"晚上好，{nickname}。🌙 回顾今天：\n"
            f"1. 有几个瞬间你觉得自己完全沉浸在当下的事里？\n"
            f"2. 有没有哪个时刻，你发现自己在焦虑未来或反刍过去？"
        )

    if period == "evening" and round_num == 2:
        return (
            "停一下，轻轻问自己：那些情绪出现的时候，"
            "那个'知道自己在焦虑/自责'的东西，它本身并不焦虑/自责。你能感觉到吗？"
        )

    if period == "evening" and round_num == 4:
        return (
            "如果给今天这5个维度打个分（1-10）：\n"
            "P 积极情绪 / E 投入心流 / R 人际关系 / M 意义感 / A 成就感\n"
            "不用想太多，凭直觉就好。"
        )

    if period == "evening" and round_num == 5:
        return (
            f"今天有什么值得感恩的事？\n"
            f"🌱 觉察第{streak_current}天 | {milestone_emoji}"
        )

    return f"[{period}/round{round_num} question — see context for LLM]"


def main():
    demo_mode = "--demo" in sys.argv

    # Read input
    raw = ""
    if len(sys.argv) >= 3 and sys.argv[1] == "--data":
        raw = sys.argv[2]
    elif not sys.stdin.isatty():
        for line in sys.stdin:
            raw += line
    elif "--demo" in sys.argv and len(sys.argv) == 1:
        # No input at all
        raw = "{}"

    if not raw.strip():
        raw = "{}"

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}, ensure_ascii=False))
        sys.exit(1)

    user_id = params.get("user_id", "default")
    period = params.get("period", "morning")
    round_num = int(params.get("round", 1))
    user_reply = params.get("user_reply")
    user_name = params.get("user_name", "")

    # Load data
    profile = load_profile(user_id)
    streak = load_streak(user_id)
    entries = load_recent_journals(user_id)

    # Compute
    patterns = compute_recent_patterns(entries)
    decision = decide_focus_dimension(profile, patterns, period, round_num)
    flags = detect_intervention_flags(profile, patterns, streak)
    science_hooks = select_science_hooks(flags, period, round_num)
    donts = determine_dont_do(flags, period)

    # Assemble output
    output = {
        "context": {
            "profile_summary": {
                "perma_baseline": profile.get("perma_baseline", {}),
                "signature_strengths": profile.get("signature_strengths", []),
                "recent_states": profile.get("state_history", [])[-5:],
            },
            "recent_patterns": patterns,
            "state_context": {
                "user_reply": user_reply,
                "period": period,
                "round": round_num,
            },
            "intervention_flags": flags,
            "streak": {
                "current": streak.get("current", 0),
                "milestone": streak.get("milestone", "🌱"),
                "longest": streak.get("longest", 0),
            },
            "user_name": user_name or user_id,
        },
        "decision": {
            "focus_dimension": decision["focus_dimension"],
            "approach": decision["approach"],
            "reasoning": decision["reasoning"],
            "tone": "firm" if any(f["level"] == "firm" for f in flags) else "warm",
            "science_hooks": science_hooks,
            "dont_do": donts,
            "template_hint": decision["template_hint"],
        },
    }

    if demo_mode:
        output["suggested_question"] = generate_demo_question(
            decision, profile, patterns, streak, user_name, period, round_num, user_reply
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
