#!/usr/bin/env python3
"""
awareness_journal_query — L1 primitive: query historical awareness records.

Usage:
  echo '{"user_id":"laomai","timespan":"7d"}' | python3 awareness_journal_query.py
  echo '{"user_id":"laomai","timespan":"30d","dimensions":["PERMA","rewrite"]}' | python3 awareness_journal_query.py

Output:
{
  "period": "2026-05-15 ~ 2026-05-21",
  "days_recorded": 5,
  "total_entries": 8,
  "perma_trend": {P: {trend:"up", values:[...]}, ...},
  "state_sequence": [...],
  "strength_calls": {毅力:4, 好奇心:2, ...},
  "rewrite_events": [{date, old, new, technique}, ...],
  "gaps": {missing_morning:[...], missing_evening:[...]},
  "data_quality": {perma_complete_rate: 0.88, rewrite_capture_rate: 0.5}
}
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOURNALS_DIR = DATA_DIR / "journals"

PERMA_DIMS = ["P", "E", "R", "M", "A"]


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def parse_timespan(timespan: str) -> tuple:
    """Parse timespan string. Returns (start_date, end_date)."""
    now = datetime.now()
    if timespan.endswith("d"):
        days = int(timespan[:-1])
        return (now - timedelta(days=days)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
    if timespan == "this_week":
        monday = now - timedelta(days=now.weekday())
        return monday.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
    if timespan == "last_week":
        monday = now - timedelta(days=now.weekday() + 7)
        sunday = monday + timedelta(days=6)
        return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
    # Default: 7 days
    return (now - timedelta(days=7)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


def query_journals(user_id: str, start: str, end: str, dimensions: list[str]) -> dict:
    user_dir = JOURNALS_DIR / user_id
    if not user_dir.exists():
        return {"available": False, "message": "无觉察记录"}

    entries = []
    for f in sorted(user_dir.glob("*.json")):
        d = load_json(f)
        if d and start <= d.get("date", "") <= end:
            entries.append(d)

    if not entries:
        return {"available": False, "message": f"{start}~{end} 无记录"}

    entries.sort(key=lambda e: e.get("date", "") + (e.get("period", "")))

    result = {
        "available": True,
        "period": f"{start} ~ {end}",
        "days_recorded": len(set(e["date"] for e in entries)),
        "total_entries": len(entries),
    }

    want_all = not dimensions or "ALL" in dimensions

    # PERMA trend
    if want_all or "PERMA" in dimensions:
        perma_series = []
        for e in entries:
            p = (e.get("extracted") or {}).get("perma", {})
            if all(dim in p for dim in PERMA_DIMS):
                perma_series.append({"date": e["date"], "period": e.get("period"), "values": p})

        perma_trend = {}
        for dim in PERMA_DIMS:
            vals = [s["values"][dim] for s in perma_series]
            if vals:
                trend = "up" if len(vals) >= 3 and vals[-1] > vals[0] + 1 else (
                    "down" if len(vals) >= 3 and vals[-1] < vals[0] - 1 else "flat"
                )
                perma_trend[dim] = {
                    "trend": trend,
                    "values": vals,
                    "latest": vals[-1],
                    "average": round(sum(vals) / len(vals), 1),
                    "min": min(vals),
                    "max": max(vals),
                }
        result["perma_trend"] = perma_trend

    # State sequence
    if want_all or "states" in dimensions:
        states = []
        for e in entries:
            emotion = (e.get("extracted") or {}).get("emotional_arc")
            if emotion and emotion.get("dominant"):
                states.append({
                    "date": e["date"],
                    "period": e.get("period"),
                    "state": emotion["dominant"],
                })
        result["state_sequence"] = states

    # Strength calls
    if want_all or "strengths" in dimensions:
        all_strengths = []
        for e in entries:
            strengths = (e.get("extracted") or {}).get("strengths_called", [])
            all_strengths.extend(strengths)
        result["strength_calls"] = dict(Counter(all_strengths).most_common())

    # Rewrite events
    if want_all or "rewrite" in dimensions:
        rewrites = []
        for e in entries:
            rew = (e.get("extracted") or {}).get("rewrite_event")
            if rew and rew.get("occurred"):
                rewrites.append({
                    "date": e["date"],
                    "old": rew.get("old_pattern"),
                    "new": rew.get("new_response"),
                    "technique": rew.get("technique"),
                })
        result["rewrite_events"] = rewrites

    # Gaps
    if want_all or "gaps" in dimensions:
        date_periods = {}
        for e in entries:
            d = e["date"]
            p = e.get("period")
            date_periods.setdefault(d, set()).add(p)

        gaps = {"missing_morning": [], "missing_evening": []}
        all_dates = sorted(set(e["date"] for e in entries))
        for d in all_dates:
            periods = date_periods.get(d, set())
            if "morning" not in periods:
                gaps["missing_morning"].append(d)
            if "evening" not in periods:
                gaps["missing_evening"].append(d)
        result["gaps"] = gaps

    # Data quality
    perma_complete = sum(
        1 for e in entries
        if all(dim in (e.get("extracted") or {}).get("perma", {}) for dim in PERMA_DIMS)
    )
    rewrite_captured = sum(
        1 for e in entries
        if (e.get("extracted") or {}).get("rewrite_event") is not None
    )
    result["data_quality"] = {
        "perma_complete_rate": round(perma_complete / len(entries), 2) if entries else 0,
        "rewrite_capture_rate": round(rewrite_captured / len(entries), 2) if entries else 0,
    }

    return result


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
    timespan = params.get("timespan", "7d")
    dimensions = params.get("dimensions", [])

    start, end = parse_timespan(timespan)
    result = query_journals(user_id, start, end, dimensions)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
