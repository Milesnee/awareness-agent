#!/usr/bin/env python3
"""
awareness_record — L2 primitive: structured recording + streak + quality validation.

Usage:
  echo '{"user_id":"test","date":"2026-05-21","period":"morning",...}' \
    | python3 awareness_record.py

Input schema (JSON via stdin or --data):
{
  "user_id": str,
  "date": "YYYY-MM-DD",
  "period": "morning" | "evening",
  "extracted": {
    "perma": {"P": 1-10, "E": 1-10, "R": 1-10, "M": 1-10, "A": 1-10},
    "strengths_called": ["毅力", "创造力", ...],
    "flow_moments": ["描述..."],
    "emotional_arc": {"dominant": "满足", "secondary": "轻微焦虑"},
    "rewrite_event": {
      "occurred": true|false,
      "old_pattern": "...",
      "new_response": "...",
      "technique": "..."
    } | null,
    "gratitude": "..." | null
  },
  "session_meta": {
    "rounds": int,
    "duration_seconds": int,
    "trigger": "heartbeat" | "manual",
    "model": "deepseek-v4-pro"
  }
}

Output (JSON to stdout):
{
  "saved": true,
  "path": "data/journals/{user_id}/{date}_{period}.json",
  "streak_updated": {"current": 8, "milestone": "🎋", "milestone_name": "茂盛"},
  "data_quality": {"perma_complete": true, "rewrite_captured": true, "score": 0.95},
  "new_insight_triggers": ["P连续3天上升", "首次识别签名优势'创造力'"],
  "validation_warnings": [...]
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

# ── PERMA dimensions ──────────────────────────────────────────────
PERMA_DIMS = ["P", "E", "R", "M", "A"]
PERMA_RANGES = {d: (1, 10) for d in PERMA_DIMS}

# 24 VIA strengths (Chinese names)
VIA_STRENGTHS = [
    "创造力", "好奇心", "批判性思维", "好学", "洞察力",
    "勇敢", "毅力", "真诚", "热情",
    "善良", "爱", "社会智慧",
    "公平", "领导力", "团队合作",
    "宽恕", "谦逊", "谨慎", "自我调节",
    "美感", "感恩", "希望", "幽默", "灵性",
]

# Milestone system
MILESTONES = [
    ("seed", "🌱", "种子", "首次回复觉察引导"),
    ("sprout", "🌿", "发芽", "完成晨间+晚间双觉察（1天）"),
    ("growth", "🌳", "成长", "连续3天觉察"),
    ("lush", "🎋", "茂盛", "连续7天 + 首份周报"),
    ("bloom", "🌸", "绽放", "识别出签名优势"),
]


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def validate_input(data: dict) -> list[str]:
    """Return list of validation warnings."""
    warnings = []
    required = ["user_id", "date", "period"]
    for k in required:
        if k not in data:
            raise ValueError(f"Missing required field: {k}")

    if data["period"] not in ("morning", "evening"):
        raise ValueError(f"Invalid period: {data['period']}")

    # Validate date format
    try:
        datetime.strptime(data["date"], "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {data['date']}")

    extracted = data.get("extracted", {})
    perma = extracted.get("perma", {})

    # PERMA completeness check
    for dim in PERMA_DIMS:
        if dim not in perma:
            warnings.append(f"PERMA.{dim} 缺失")
        elif not (1 <= perma[dim] <= 10):
            warnings.append(f"PERMA.{dim} 值超出范围: {perma[dim]}")

    # Strengths validation
    strengths = extracted.get("strengths_called", [])
    unknown = [s for s in strengths if s not in VIA_STRENGTHS]
    if unknown:
        warnings.append(f"未知品格优势: {unknown}")

    # Rewrite event validation
    rewrite = extracted.get("rewrite_event")
    if rewrite and rewrite.get("occurred"):
        if not rewrite.get("new_response"):
            warnings.append("改写事件标记为已发生但缺少 new_response")

    return warnings


def compute_data_quality(extracted: dict, period: str) -> dict:
    """Score data completeness and quality 0-1."""
    perma = extracted.get("perma", {})
    perma_complete = all(dim in perma and 1 <= perma[dim] <= 10 for dim in PERMA_DIMS)

    has_strengths = len(extracted.get("strengths_called", [])) > 0
    has_flow = len(extracted.get("flow_moments", [])) > 0
    emotion = extracted.get("emotional_arc")
    has_emotion = bool(emotion and emotion.get("dominant"))

    rewrite = extracted.get("rewrite_event")
    rewrite_captured = rewrite is not None
    rewrite_complete = rewrite_captured and (not rewrite.get("occurred") or bool(rewrite.get("new_response")))

    has_gratitude = bool(extracted.get("gratitude"))

    # Weighted scoring
    score = 0.0
    score += 0.35 if perma_complete else (0.1 * sum(1 for d in PERMA_DIMS if d in perma))
    score += 0.15 if has_strengths else 0
    score += 0.10 if has_flow else 0
    score += 0.10 if has_emotion else 0
    score += 0.10 if has_gratitude else 0
    score += 0.20 if (period == "morning" or (period == "evening" and rewrite_complete)) else (0.10 if rewrite_captured else 0)

    return {
        "perma_complete": perma_complete,
        "rewrite_captured": rewrite_captured,
        "score": round(score, 2),
    }


def update_streak(user_id: str, date_str: str, period: str) -> dict:
    """Update streak tracking. Returns {current, milestone, milestone_name}."""
    path = STREAKS_DIR / f"{user_id}.json"
    streak_data = load_json(path) or {
        "current": 0,
        "longest": 0,
        "history": [],
        "last_date": None,
        "milestone": "seed",
        "signature_strengths_identified": False,
        "completed_days": [],
    }

    today = datetime.strptime(date_str, "%Y-%m-%d").date()

    # Determine if today is now complete (both periods done)
    completed_days = set(streak_data.get("completed_days", []))
    if period == "morning":
        # Check if evening already exists for today
        evening_path = JOURNALS_DIR / user_id / f"{date_str}_evening.json"
        if evening_path.exists():
            completed_days.add(date_str)
    elif period == "evening":
        # Check if morning already exists for today
        morning_path = JOURNALS_DIR / user_id / f"{date_str}_morning.json"
        if morning_path.exists():
            completed_days.add(date_str)

    streak_data["completed_days"] = sorted(completed_days)

    # Compute consecutive days ending at today
    current = 0
    check_date = today
    while str(check_date) in completed_days:
        current += 1
        check_date -= timedelta(days=1)

    # If today not complete but yesterday was, streak is yesterday's + (pending)
    if date_str not in completed_days and current > 0:
        pass  # current already computed; today may complete later

    longest = max(streak_data.get("longest", 0), current)
    streak_data["current"] = current
    streak_data["longest"] = longest
    streak_data["last_date"] = date_str
    streak_data["history"].append({"date": date_str, "period": period, "streak": current})

    # Milestone check
    milestone = streak_data.get("milestone", "seed")
    if current >= 7:
        milestone = "lush"
    elif current >= 3:
        milestone = "growth"
    elif current >= 1:
        milestone = "sprout"
    else:
        milestone = "seed"

    # Find milestone emoji+name
    milestone_info = next((m for m in MILESTONES if m[0] == milestone), MILESTONES[0])
    streak_data["milestone"] = milestone

    save_json(path, streak_data)

    return {
        "current": current,
        "longest": longest,
        "milestone": milestone_info[1],
        "milestone_name": milestone_info[2],
    }


def detect_insight_triggers(user_id: str, date_str: str, extracted: dict) -> list[str]:
    """Detect notable patterns that should trigger deeper analysis."""
    triggers = []

    # Check last 7 days of journals
    user_dir = JOURNALS_DIR / user_id
    if not user_dir.exists():
        return triggers

    journal_files = sorted(user_dir.glob("*.json"))
    recent = []
    for f in journal_files:
        try:
            d = load_json(f)
            if d and d.get("extracted"):
                recent.append(d)
        except Exception:
            continue

    if len(recent) < 2:
        return triggers

    # PERMA trend detection (last 3 entries)
    perma_series = []
    for entry in recent[-7:]:
        p = entry.get("extracted", {}).get("perma", {})
        if all(dim in p for dim in PERMA_DIMS):
            perma_series.append(p)

    if len(perma_series) >= 3:
        last3 = perma_series[-3:]
        for dim in PERMA_DIMS:
            vals = [p[dim] for p in last3]
            if len(set(vals)) >= 3 and vals == sorted(vals) and vals[-1] - vals[0] >= 2:
                triggers.append(f"{dim}连续{len(last3)}天上升（{vals[0]}→{vals[-1]}）")
            elif len(set(vals)) >= 3 and vals == sorted(vals, reverse=True) and vals[0] - vals[-1] >= 2:
                triggers.append(f"{dim}连续{len(last3)}天下降（{vals[0]}→{vals[-1]}）")

    # Strengths — any new signature strength emerging?
    all_strengths = []
    for entry in recent[-7:]:
        strengths = entry.get("extracted", {}).get("strengths_called", [])
        all_strengths.extend(strengths)

    from collections import Counter
    strength_counts = Counter(all_strengths)
    # Check for strengths that appear 3+ times in last 7 days
    for strength, count in strength_counts.most_common():
        if count >= 3:
            # Check if this is the first time hitting 3
            older = recent[:-3] if len(recent) > 3 else []
            older_counts = Counter(
                s for e in older
                for s in e.get("extracted", {}).get("strengths_called", [])
            )
            if older_counts.get(strength, 0) < 3:
                triggers.append(f"首次识别签名优势'{strength}'（近7天出现{count}次）")

    # Rewrite pattern
    rewrites = [
        e for e in recent[-7:]
        if (rew := e.get("extracted", {}).get("rewrite_event")) and rew.get("occurred")
    ]
    if len(recent) >= 5 and len(rewrites) == 0:
        triggers.append("连续5次记录无改写事件——用户可能陷入旧模式")
    elif len(rewrites) >= 3:
        triggers.append(f"改写活跃：近7天发生{len(rewrites)}次改写")

    return triggers


def update_profile(user_id: str, extracted: dict, date_str: str):
    """Update user profile with running aggregates."""
    path = PROFILES_DIR / f"{user_id}.json"
    profile = load_json(path) or {
        "user_id": user_id,
        "created_at": date_str,
        "perma_baseline": {},
        "signature_strengths": [],
        "dominant_states": {},
        "state_history": [],
        "preferences": {},
    }

    # Update PERMA baseline (exponential moving average-like)
    perma = extracted.get("perma", {})
    if perma:
        existing = profile.get("perma_baseline", {})
        count = profile.get("perma_record_count", 0) + 1
        for dim in PERMA_DIMS:
            if dim in perma:
                alpha = 0.3  # weight for new value
                old = existing.get(dim, perma[dim])
                existing[dim] = round(old * (1 - alpha) + perma[dim] * alpha, 1)
        profile["perma_baseline"] = existing
        profile["perma_record_count"] = count

    # Update strengths frequency
    strengths = extracted.get("strengths_called", [])
    if strengths:
        freq = profile.get("strengths_frequency", {})
        for s in strengths:
            freq[s] = freq.get(s, 0) + 1
        profile["strengths_frequency"] = freq
        # Top 5 = signature strengths
        top5 = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]
        profile["signature_strengths"] = [s for s, _ in top5]

    # Track emotional arc
    emotion = extracted.get("emotional_arc")
    if emotion and emotion.get("dominant"):
        profile.setdefault("state_history", []).append({
            "date": date_str,
            "dominant": emotion["dominant"],
        })
        # Keep last 30
        profile["state_history"] = profile["state_history"][-30:]

    save_json(path, profile)


def main():
    # Read input
    if len(sys.argv) > 2 and sys.argv[1] == "--data":
        raw = sys.argv[2]
    elif not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
    else:
        print(json.dumps({"error": "No input. Pipe JSON to stdin or use --data '...'"}, ensure_ascii=False))
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}, ensure_ascii=False))
        sys.exit(1)

    # Validate
    try:
        warnings = validate_input(data)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    user_id = data["user_id"]
    date_str = data["date"]
    period = data["period"]
    extracted = data.get("extracted", {})

    # Save journal
    journal_path = JOURNALS_DIR / user_id / f"{date_str}_{period}.json"
    save_json(journal_path, {
        "user_id": user_id,
        "date": date_str,
        "period": period,
        "extracted": extracted,
        "session_meta": data.get("session_meta", {}),
        "saved_at": datetime.now().isoformat(),
    })

    # Update streak
    streak_info = update_streak(user_id, date_str, period)

    # Data quality
    quality = compute_data_quality(extracted, period)

    # Insight triggers
    triggers = detect_insight_triggers(user_id, date_str, extracted)

    # Update profile
    update_profile(user_id, extracted, date_str)

    # Assemble result
    result = {
        "saved": True,
        "path": str(journal_path.relative_to(PROJECT_ROOT)),
        "streak_updated": streak_info,
        "data_quality": quality,
        "new_insight_triggers": triggers,
        "validation_warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
