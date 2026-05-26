#!/usr/bin/env python3
"""
awareness_quality_score — L3 primitive: score a single awareness dialogue session.

Evaluates the depth and effectiveness of one awareness conversation.
Used by the system to self-monitor and detect quality degradation.

Usage:
  echo '{"session_data":{...}}' | python3 awareness_quality_score.py

Input (same schema as awareness_record input):
{
  "session_data": {
    "extracted": {perma, strengths_called, flow_moments, emotional_arc, rewrite_event, gratitude},
    "session_meta": {rounds, duration_seconds, trigger, model}
  },
  "baseline": {"overall": 0.72}  // optional: 7-day baseline for comparison
}

Output:
{
  "overall": 0.78,
  "dimensions": {
    "depth": 0.85, "completeness": 0.90, "rewrite_quality": 0.60,
    "data_quality": 0.95, "engagement": 0.70
  },
  "flags": ["rewrite未发生新反应，连续3次相同模式"],
  "comparison_to_baseline": {"overall": "+0.05 vs 7日均值"}
}
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOURNALS_DIR = DATA_DIR / "journals"

PERMA_DIMS = ["P", "E", "R", "M", "A"]


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def compute_baseline(user_id: str = None) -> dict:
    """Compute 7-day average quality baseline from saved journals."""
    if not user_id:
        return None

    user_dir = JOURNALS_DIR / user_id
    if not user_dir.exists():
        return None

    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    entries = []
    for f in sorted(user_dir.glob("*.json")):
        d = load_json(f)
        if d and d.get("date", "") >= cutoff:
            entries.append(d)

    if len(entries) < 2:
        return None

    # Score each historical entry (lightweight version)
    scores = []
    for e in entries:
        extracted = e.get("extracted") or {}
        s = score_session(extracted, e.get("session_meta", {}))
        scores.append(s["overall"])

    avg = sum(scores) / len(scores)
    return {
        "overall": round(avg, 2),
        "sample_size": len(scores),
        "min": round(min(scores), 2),
        "max": round(max(scores), 2),
    }


def score_session(extracted: dict, meta: dict) -> dict:
    """Score a single session."""
    perma = extracted.get("perma", {})
    strengths = extracted.get("strengths_called", [])
    flow = extracted.get("flow_moments", [])
    emotion = extracted.get("emotional_arc")
    rewrite = extracted.get("rewrite_event")
    gratitude = extracted.get("gratitude")

    rounds = meta.get("rounds", 0)
    duration = meta.get("duration_seconds", 0)

    # 1. Depth (0-1): emotional specificity + flow moments + rewrite depth
    depth = 0.0
    if emotion and emotion.get("dominant") and emotion.get("secondary"):
        depth += 0.25  # has both primary and secondary emotion
    elif emotion and emotion.get("dominant"):
        depth += 0.15
    if flow and len(flow) > 0:
        depth += 0.25
        # Bonus for detailed flow descriptions
        if any(len(f) > 15 for f in flow):
            depth += 0.15
    if rewrite and rewrite.get("occurred"):
        old = rewrite.get("old_pattern", "")
        new = rewrite.get("new_response", "")
        if old and new and old != new:
            depth += 0.25
            if len(new) > 20:  # detailed new response
                depth += 0.10
    depth = min(depth, 1.0)

    # 2. Completeness (0-1): all rounds + all PERMA dims
    completeness = 0.0
    expected_rounds = 5 if "evening" in str(meta) else 3
    completeness += min(rounds / expected_rounds, 1.0) * 0.4
    perma_count = sum(1 for d in PERMA_DIMS if d in perma and 1 <= perma[d] <= 10)
    completeness += (perma_count / 5) * 0.4
    if gratitude or (rewrite is not None):
        completeness += 0.2
    completeness = min(completeness, 1.0)

    # 3. Rewrite quality (0-1): genuinely new response?
    rewrite_quality = 0.0
    if rewrite and rewrite.get("occurred"):
        rewrite_quality += 0.4  # attempted
        old = rewrite.get("old_pattern", "")
        new = rewrite.get("new_response", "")
        if old and new and old != new:
            rewrite_quality += 0.4  # genuinely different
            if len(new) > 20:
                rewrite_quality += 0.2  # detailed
    elif rewrite is not None:
        rewrite_quality += 0.2  # at least captured
    rewrite_quality = min(rewrite_quality, 1.0)

    # 4. Data quality (0-1): same scale as awareness_record
    data_quality = 0.0
    data_quality += 0.35 * (perma_count / 5)
    data_quality += 0.15 * (1.0 if strengths else 0.0)
    data_quality += 0.10 * (1.0 if flow else 0.0)
    data_quality += 0.10 * (1.0 if emotion and emotion.get("dominant") else 0.0)
    data_quality += 0.10 * (1.0 if gratitude else 0.0)
    data_quality += 0.20 * (1.0 if rewrite is not None else 0.0)
    data_quality = min(data_quality, 1.0)

    # 5. Engagement (0-1): rounds + duration
    engagement = 0.0
    engagement += min(rounds / 5, 1.0) * 0.5
    # ~60s for engaged morning, ~150s for engaged evening
    expected_duration = 120 if rounds >= 4 else 60
    engagement += min(duration / expected_duration, 1.0) * 0.5
    engagement = min(engagement, 1.0)

    overall = round(
        depth * 0.30 + completeness * 0.20 + rewrite_quality * 0.20 +
        data_quality * 0.15 + engagement * 0.15, 2
    )

    return {
        "overall": overall,
        "dimensions": {
            "depth": round(depth, 2),
            "completeness": round(completeness, 2),
            "rewrite_quality": round(rewrite_quality, 2),
            "data_quality": round(data_quality, 2),
            "engagement": round(engagement, 2),
        },
    }


def detect_flags(extracted: dict, meta: dict, history_rewrites: list = None) -> list[str]:
    """Detect quality flags."""
    flags = []

    # PERMA incomplete
    perma = extracted.get("perma", {})
    missing = [d for d in PERMA_DIMS if d not in perma or not (1 <= perma[d] <= 10)]
    if missing:
        flags.append(f"PERMA缺失: {','.join(missing)}")

    # Too few rounds
    rounds = meta.get("rounds", 0)
    if rounds <= 2:
        flags.append(f"对话轮数过少({rounds}轮)——用户可能匆忙或缺乏投入")

    # No flow moments
    if not extracted.get("flow_moments"):
        flags.append("无心神合一时刻记录——投入感缺失")

    # Rewrite same as previous
    rewrite = extracted.get("rewrite_event")
    if rewrite and rewrite.get("occurred") and history_rewrites:
        new_resp = rewrite.get("new_response", "")
        if any(new_resp == r.get("new") for r in history_rewrites[-3:]):
            flags.append("改写新反应与历史重复——可能未真正尝试新行为")

    # Very short duration
    duration = meta.get("duration_seconds", 0)
    if duration < 20:
        flags.append(f"互动时长极短({duration}s)——可能为敷衍式回复")

    return flags


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

    session_data = params.get("session_data", {})
    user_id = params.get("user_id")

    extracted = session_data.get("extracted") or {}
    meta = session_data.get("session_meta") or {}

    # Load recent rewrites for flag detection
    history_rewrites = []
    if user_id:
        user_dir = JOURNALS_DIR / user_id
        if user_dir.exists():
            for f in sorted(user_dir.glob("*.json"), reverse=True)[:5]:
                d = load_json(f)
                if d:
                    rew = (d.get("extracted") or {}).get("rewrite_event")
                    if rew and rew.get("occurred"):
                        history_rewrites.append({"date": d["date"], "new": rew.get("new_response")})

    # Score
    scores = score_session(extracted, meta)
    flags = detect_flags(extracted, meta, history_rewrites)

    # Baseline comparison
    baseline = params.get("baseline") or (compute_baseline(user_id) if user_id else None)
    comparison = None
    if baseline:
        diff = scores["overall"] - baseline["overall"]
        comparison = {
            "overall": f"{diff:+.2f} vs 7日均值({baseline['overall']})",
            "baseline_sample": baseline.get("sample_size", 0),
        }

    result = {
        **scores,
        "flags": flags if flags else ["无明显质量标志"],
    }
    if comparison:
        result["comparison_to_baseline"] = comparison

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
