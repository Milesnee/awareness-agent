#!/usr/bin/env python3
"""
awareness_state_detect — L1 primitive: detect user's current state from natural language.

Four-state model:
  停不下来 (can't stop) — 排满日程、不敢休息、用忙碌回避焦虑
  启动不了 (can't start) — 拖延、刷手机、自我批评消耗能量
  硬撑着   (holding on)  — 表面正常、回家垮掉、压抑真实感受
  一直在找 (searching)  — 换方向、空洞感反复、用外部改变回避内在

Usage:
  echo '{"text":"我今天又拖延了，刷了一上午手机，感觉自己真没用"}' \
    | python3 awareness_state_detect.py
  echo '{"text":"..."}' | python3 awareness_state_detect.py --explain

Output:
{
  "primary_state": "启动不了",
  "confidence": 0.82,
  "secondary_states": [{"state":"硬撑着", "confidence":0.25}, ...],
  "signals": ["拖延", "刷手机", "自我批评"],
  "severity": "moderate",    // mild | moderate | high
  "suggested_approach": "引导带着不想做的感觉做一小步",
  "guiding_question": "如果今天不骂自己，而是对自己说'今天尽力了'，会怎样？"
}
"""

import json
import re
import sys
from collections import Counter

# ── State signal definitions ─────────────────────────────────────

STATE_SIGNALS = {
    "停不下来": {
        "primary": [
            "停不下来", "排满", "日程满", "不敢休息", "休息时心虚", "一直在忙",
            "不停", "连轴转", "没时间休息", "怕停下来", "闲不下来",
            "忙到", "赶场", "一个接一个", "没空",
        ],
        "secondary": [
            "忙碌", "忙", "日程", "效率", "产出", "推进", "赶",
            "加速", "冲刺", "多线程", "同时",
        ],
        "negative_signals": [],  # absence of these increases confidence
    },
    "启动不了": {
        "primary": [
            "启动不了", "拖延", "不想动", "没动力", "懒得", "动不了",
            "刷手机", "刷视频", "刷了一天", "一边刷一边烦",
            "起不来", "不想做", "做不下去", "没劲",
        ],
        "secondary": [
            "手机", "视频", "躺", "困", "累得不想", "没精神",
            "拖", "搁置", "放着", "等等再做",
        ],
        "negative_signals": [],
    },
    "硬撑着": {
        "primary": [
            "硬撑", "强撑", "撑着", "死撑", "撑下去", "硬扛",
            "回家就垮", "回家垮掉", "表面正常", "装正常", "维持正常",
            "很累但", "疲惫但继续", "咬牙", "硬着头皮",
        ],
        "secondary": [
            "累", "疲惫", "累死", "撑", "装", "正常", "维持",
            "耗竭", "透支", "强打精神", "硬来",
        ],
        "negative_signals": [],
    },
    "一直在找": {
        "primary": [
            "一直在找", "换方向", "又换了", "又换", "空洞感", "空洞",
            "这次不一样", "新鲜感过了", "新鲜感", "下一个",
            "换赛道", "改方向", "又开始了", "重新开始",
        ],
        "secondary": [
            "方向", "迷茫", "不知道做什么", "不确定", "试试",
            "探索", "找", "寻", "换", "新",
        ],
        "negative_signals": [],
    },
}

# Self-criticism patterns (amplify "启动不了" and "硬撑着")
SELF_CRITICISM = [
    "真没用", "废物", "没用", "差劲", "不行", "失败",
    "骂自己", "恨自己", "讨厌自己", "嫌弃", "自责", "自己不好",
    "又这样", "老样子", "改不了", "没救了", "废了",
]

# Exhaustion patterns (amplify "硬撑着")
EXHAUSTION = [
    "累死", "累坏", "虚脱", "撑不住", "快不行了", "极限",
    "到极限", "崩溃", "受不了", "扛不住",
]

# Avoidance patterns (amplify "停不下来")
AVOIDANCE = [
    "不敢想", "不想面对", "回避", "转移注意力", "用忙来",
    "不敢停", "怕空下来", "怕安静",
]


def tokenize(text: str) -> list[str]:
    """Simple Chinese tokenizer: split on punctuation, keep phrases."""
    # Remove punctuation for matching
    cleaned = re.sub(r"[，。！？、；：\"'“”‘’（）\s]+", " ", text)
    return cleaned.strip()


def match_signals(text: str, signal_list: list[str]) -> int:
    """Count how many signals from the list appear in the text."""
    count = 0
    for signal in signal_list:
        if signal in text:
            count += 1
    return count


def detect_state(text: str, explain: bool = False) -> dict:
    """Main detection logic."""
    cleaned = tokenize(text)

    # Score each state
    scores = {}
    all_signals_found = {}

    for state, signals in STATE_SIGNALS.items():
        primary_count = match_signals(cleaned, signals["primary"])
        secondary_count = match_signals(cleaned, signals["secondary"])

        # Weighted score: primary = 3pts, secondary = 1pt
        raw_score = primary_count * 3 + secondary_count * 1
        # Normalize to 0-1 range (max plausible is ~15)
        normalized = min(raw_score / 15.0, 1.0)

        scores[state] = normalized
        all_signals_found[state] = {
            "primary_matches": [s for s in signals["primary"] if s in cleaned],
            "secondary_matches": [s for s in signals["secondary"] if s in cleaned],
        }

    # Apply modifiers
    modifiers = {}

    # Self-criticism: boost "启动不了" and "硬撑着"
    sc_count = match_signals(cleaned, SELF_CRITICISM)
    if sc_count > 0:
        scores["启动不了"] = min(scores["启动不了"] + sc_count * 0.1, 1.0)
        scores["硬撑着"] = min(scores["硬撑着"] + sc_count * 0.05, 1.0)
        modifiers["self_criticism"] = sc_count

    # Exhaustion: boost "硬撑着"
    ex_count = match_signals(cleaned, EXHAUSTION)
    if ex_count > 0:
        scores["硬撑着"] = min(scores["硬撑着"] + ex_count * 0.15, 1.0)
        modifiers["exhaustion"] = ex_count

    # Avoidance: boost "停不下来"
    av_count = match_signals(cleaned, AVOIDANCE)
    if av_count > 0:
        scores["停不下来"] = min(scores["停不下来"] + av_count * 0.15, 1.0)
        modifiers["avoidance"] = av_count

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    primary_state = ranked[0][0]
    primary_score = ranked[0][1]

    # Confidence: if top score is clearly ahead, higher confidence
    if len(ranked) >= 2:
        gap = ranked[0][1] - ranked[1][1]
        confidence = min(0.5 + gap * 2, 0.95) if primary_score > 0 else 0.3
    else:
        confidence = min(primary_score * 1.2, 0.9)

    # If no signals matched at all, low confidence
    if primary_score < 0.1:
        confidence = 0.15
        primary_state = "无法判断"

    # Secondary states
    secondary = [
        {"state": s, "confidence": round(sc, 2)}
        for s, sc in ranked[1:4] if sc > 0.05
    ]

    # Severity
    if primary_score >= 0.6:
        severity = "high"
    elif primary_score >= 0.3:
        severity = "moderate"
    else:
        severity = "mild"

    # Signals
    signals_list = (
        all_signals_found.get(primary_state, {}).get("primary_matches", []) +
        all_signals_found.get(primary_state, {}).get("secondary_matches", [])
    )[:5]

    # Suggested approach
    approaches = {
        "停不下来": {
            "approach": "引导觉察：休息时的焦虑是什么？不做什么比做什么更难",
            "question": "如果今天什么都不做，只是安静地待着——那个焦虑感是什么样的？",
        },
        "启动不了": {
            "approach": "引导改写：带着不想做的感觉，做一小步",
            "question": "如果今天不骂自己，而是对自己说'今天尽力了'，会怎样？",
        },
        "硬撑着": {
            "approach": "引导觉察：你在撑着什么？不撑会怎样？",
            "question": "撑了这么久，累吗？有没有人可以帮你分担一点点？",
        },
        "一直在找": {
            "approach": "引导觉察：每次'这次不一样'的感觉是什么？找到后又是什么感觉？",
            "question": "如果不需要'找'了——就停在这里——你感受到了什么？",
        },
        "无法判断": {
            "approach": "温和探索，不做状态假设",
            "question": "今天的状态，用一句话形容的话是什么？",
        },
    }
    approach = approaches.get(primary_state, approaches["无法判断"])

    result = {
        "primary_state": primary_state,
        "confidence": round(confidence, 2),
        "secondary_states": secondary,
        "signals": signals_list,
        "severity": severity,
        "suggested_approach": approach["approach"],
        "guiding_question": approach["question"],
    }

    if explain:
        result["_explain"] = {
            "raw_scores": {s: round(sc, 2) for s, sc in scores.items()},
            "modifiers": modifiers,
            "all_signals": all_signals_found,
            "token_count": len(cleaned),
        }

    return result


def main():
    explain = "--explain" in sys.argv

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

    text = params.get("text", "")
    if not text:
        print(json.dumps({"error": "Missing 'text' field"}, ensure_ascii=False))
        sys.exit(1)

    result = detect_state(text, explain=explain)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
