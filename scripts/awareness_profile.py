#!/usr/bin/env python3
"""
awareness_profile — L1 primitive: load user awareness profile + streak.

Usage:
  echo '{"user_id":"laomai"}' | python3 awareness_profile.py

Output:
{
  "profile": {perma_baseline, signature_strengths, state_history, ...},
  "streak": {current, longest, milestone, milestone_name, completed_days},
  "summary": {
    "一句话": "连续3天觉察🌳, PERMA基线P=5.0/E=4.6/R=6.6/M=5.5/A=5.4, 签名优势: 毅力,勇敢",
    "risk_flags": ["E持续偏低(4.6)", "晚间复盘偶尔缺失"],
    "growth_signals": ["改写事件3次", "连续天数稳定"]
  }
}
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROFILES_DIR = DATA_DIR / "profiles"
STREAKS_DIR = DATA_DIR / "streaks"
JOURNALS_DIR = DATA_DIR / "journals"

PERMA_DIMS = ["P", "E", "R", "M", "A"]


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def compute_summary(profile: dict, streak: dict, journals_exist: bool) -> dict:
    """Generate human-readable summary + risk/growth signals."""
    risks = []
    growths = []

    perma = profile.get("perma_baseline", {})
    if perma:
        low_dims = [d for d in PERMA_DIMS if perma.get(d, 10) <= 5]
        if low_dims:
            risks.append(f"{','.join(low_dims)}偏低({', '.join(f'{d}={perma[d]}' for d in low_dims)})")

    streak_current = streak.get("current", 0)
    if streak_current >= 3:
        growths.append(f"连续{streak_current}天稳定")
    elif streak_current == 0:
        risks.append("streak中断")

    # Count rewrite events from profile
    strengths_freq = profile.get("strengths_frequency", {})
    sig = profile.get("signature_strengths", [])

    # Check journal gaps (last 7 days)
    # This is lightweight — just count what we can see
    if journals_exist:
        # Check if the profile has state history
        states = profile.get("state_history", [])
        if len(states) >= 5:
            negative_states = sum(1 for s in states[-7:] if s.get("dominant") in ("低落", "焦虑", "疲惫"))
            if negative_states >= 3:
                risks.append(f"近7天负面状态占比高({negative_states}/{min(7,len(states))})")

    milestone_map = {
        "seed": "🌱种子", "sprout": "🌿发芽", "growth": "🌳成长",
        "lush": "🎋茂盛", "bloom": "🌸绽放",
    }
    milestone_emoji = milestone_map.get(streak.get("milestone", "seed"), "🌱种子")

    parts = [f"连续{streak_current}天觉察{milestone_emoji}"]
    if perma:
        parts.append(f"PERMA基线{'/'.join(f'{d}={perma[d]}' for d in PERMA_DIMS)}")
    if sig:
        parts.append(f"签名优势: {','.join(sig[:4])}")
    oneline = "，".join(parts)

    return {
        "一句话": oneline,
        "risk_flags": risks if risks else ["无明显风险"],
        "growth_signals": growths if growths else ["数据积累中"],
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

    user_id = params.get("user_id", "default")

    profile = load_json(PROFILES_DIR / f"{user_id}.json") or {}
    streak = load_json(STREAKS_DIR / f"{user_id}.json") or {}

    journals_exist = (JOURNALS_DIR / user_id).exists()
    summary = compute_summary(profile, streak, journals_exist)

    result = {
        "profile": {
            "perma_baseline": profile.get("perma_baseline", {}),
            "signature_strengths": profile.get("signature_strengths", []),
            "strengths_frequency": profile.get("strengths_frequency", {}),
            "state_history": profile.get("state_history", [])[-14:],
            "perma_record_count": profile.get("perma_record_count", 0),
        },
        "streak": {
            "current": streak.get("current", 0),
            "longest": streak.get("longest", 0),
            "milestone": streak.get("milestone", "seed"),
            "milestone_name": {
                "seed": "种子", "sprout": "发芽", "growth": "成长",
                "lush": "茂盛", "bloom": "绽放",
            }.get(streak.get("milestone", "seed"), "种子"),
            "completed_days": streak.get("completed_days", []),
        },
        "summary": summary,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
