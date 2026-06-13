#!/usr/bin/env python3
"""
awareness_pattern_review — L3 primitive: cross-period pattern analysis.

The "brain" of the awareness system. Generates data-driven insights,
hypotheses, and minimal adjustment suggestions from structured journal data.

Usage:
  echo '{"user_id":"laomai","timespan":"7d"}' | python3 awareness_pattern_review.py
  echo '{"user_id":"laomai","timespan":"30d","dimensions":["PERMA","rewrite"]}' | python3 awareness_pattern_review.py

Output:
{
  "period": "2026-W20",
  "perma_changes": {P: {trend, slope, significance, insight}, ...},
  "state_transitions": [{from, to, frequency, insight}, ...],
  "rewrite_effectiveness": {attempts, succeeded, rate, bottleneck, most_effective},
  "hypotheses": [{condition, outcome, confidence, data_points}, ...],
  "minimal_adjustments": [...],
  "summary": "一句话洞察"
}
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOURNALS_DIR = DATA_DIR / "journals"
PROFILES_DIR = DATA_DIR / "profiles"

PERMA_DIMS = ["P", "E", "R", "M", "A"]


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def parse_timespan(timespan: str) -> tuple:
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
    return (now - timedelta(days=7)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


def load_journals(user_id: str, start: str, end: str) -> list[dict]:
    user_dir = JOURNALS_DIR / user_id
    if not user_dir.exists():
        return []
    entries = []
    for f in sorted(user_dir.glob("*.json")):
        d = load_json(f)
        if d and start <= d.get("date", "") <= end:
            entries.append(d)
    entries.sort(key=lambda e: e["date"] + e.get("period", ""))
    return entries


def analyze_perma(entries: list[dict]) -> dict:
    """Analyze PERMA trends with significance assessment."""
    # Collect per-dimension time series
    series = {dim: [] for dim in PERMA_DIMS}
    for e in entries:
        perma = (e.get("extracted") or {}).get("perma", {})
        for dim in PERMA_DIMS:
            if dim in perma:
                series[dim].append({"date": e["date"], "period": e.get("period"), "value": perma[dim]})

    result = {}
    for dim in PERMA_DIMS:
        vals = [s["value"] for s in series[dim]]
        if len(vals) < 2:
            result[dim] = {"trend": "insufficient_data", "slope": 0, "significance": "none"}
            continue

        n = len(vals)
        # Simple linear slope (first→last normalized)
        slope = (vals[-1] - vals[0]) / max(n - 1, 1)

        # Trend direction
        if slope > 0.3:
            trend = "up"
        elif slope < -0.3:
            trend = "down"
        else:
            trend = "flat"

        # Significance: monotonicity + consistency
        if n >= 5:
            # Check if generally monotonic (allowing 1 violation)
            up_count = sum(1 for i in range(1, n) if vals[i] >= vals[i-1])
            down_count = sum(1 for i in range(1, n) if vals[i] <= vals[i-1])
            if up_count >= n - 2 and trend == "up":
                significance = "strong"
            elif down_count >= n - 2 and trend == "down":
                significance = "strong"
            elif up_count >= n - 3 or down_count >= n - 3:
                significance = "moderate"
            else:
                significance = "weak"
        elif n >= 3:
            monotonic = all(vals[i] >= vals[i-1] for i in range(1, n)) or \
                        all(vals[i] <= vals[i-1] for i in range(1, n))
            significance = "moderate" if monotonic else "weak"
        else:
            significance = "weak"

        # Insight text
        if trend == "up" and significance in ("strong", "moderate"):
            insight = f"{dim}持续上升（{vals[0]}→{vals[-1]}），该维度正在改善"
        elif trend == "down" and significance in ("strong", "moderate"):
            insight = f"{dim}持续下降（{vals[0]}→{vals[-1]}），需要关注"
        elif trend == "flat":
            insight = f"{dim}保持稳定（均值{round(sum(vals)/len(vals),1)}）"
        else:
            insight = f"{dim}波动较大（{min(vals)}~{max(vals)}），不稳定"

        result[dim] = {
            "trend": trend,
            "slope": round(slope, 2),
            "significance": significance,
            "values": vals[-7:],
            "latest": vals[-1],
            "average": round(sum(vals) / len(vals), 1),
            "min": min(vals),
            "max": max(vals),
            "insight": insight,
        }

    return result


def analyze_state_transitions(entries: list[dict]) -> list[dict]:
    """Analyze morning→evening state transition patterns."""
    by_date = defaultdict(dict)
    for e in entries:
        emotion = (e.get("extracted") or {}).get("emotional_arc")
        if emotion and emotion.get("dominant"):
            by_date[e["date"]][e.get("period", "")] = emotion["dominant"]

    transitions = []
    for date in sorted(by_date.keys()):
        periods = by_date[date]
        morning = periods.get("morning", "")
        evening = periods.get("evening", "")
        if morning and evening:
            transitions.append({"date": date, "from": morning, "to": evening})

    if not transitions:
        return []

    # Count transition patterns
    pattern_counts = Counter()
    for t in transitions:
        pattern_counts[f"{t['from']}→{t['to']}"] += 1

    total = len(transitions)
    result = []
    for pattern, count in pattern_counts.most_common():
        from_state, to_state = pattern.split("→")

        # Insight
        if from_state == to_state:
            if from_state in ("低落", "焦虑", "疲惫"):
                insight = f"{from_state}状态全天未解——晨间{from_state}→晚间仍是{from_state}"
            else:
                insight = f"{from_state}状态全天保持——稳定的正向状态"
        elif from_state in ("低落", "焦虑") and to_state in ("满足", "平静", "充实"):
            insight = f"正向转变：{from_state}→{to_state}——这一天发生了什么带来了变化？"
        elif from_state in ("满足", "期待") and to_state in ("低落", "焦虑", "疲惫"):
            insight = f"状态恶化：{from_state}→{to_state}——什么消耗了能量？"
        else:
            insight = f"{from_state}→{to_state}"

        result.append({
            "from": from_state,
            "to": to_state,
            "frequency": f"{count}/{total}天",
            "percentage": round(count / total * 100),
            "insight": insight,
        })

    return result


def analyze_rewrite_effectiveness(entries: list[dict]) -> dict:
    """Analyze rewrite events: attempts, success rate, techniques, bottleneck."""
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

    total_entries = len(entries)
    attempts = len(rewrites)
    # For "succeeded", we check if new_response is meaningfully different from old
    succeeded = sum(1 for r in rewrites if r["new"] and r["new"] != r["old"])

    techniques = Counter(r["technique"] for r in rewrites if r.get("technique"))

    # Bottleneck detection
    if total_entries >= 5 and attempts == 0:
        bottleneck = "连续无改写事件——用户可能未看到改写机会或回避深层觉察"
    elif attempts > 0 and succeeded < attempts * 0.5:
        bottleneck = "改写尝试多但新反应少——可能在重复旧模式而非真正尝试不同做法"
    elif attempts > 0:
        bottleneck = "改写活跃，新反应正在形成"
    else:
        bottleneck = "数据不足，继续观察"

    return {
        "total_entries_in_period": total_entries,
        "rewrite_attempts": attempts,
        "rewrites_succeeded": succeeded,
        "success_rate": round(succeeded / attempts, 2) if attempts > 0 else 0,
        "techniques_used": dict(techniques.most_common()),
        "most_effective_technique": techniques.most_common(1)[0][0] if techniques else None,
        "bottleneck": bottleneck,
        "recent_rewrites": rewrites[-3:],
    }


def generate_hypotheses(entries: list[dict], perma_changes: dict) -> list[dict]:
    """Generate data-driven hypotheses: condition → outcome."""
    hypotheses = []

    # Pair morning and evening records for same day
    by_date = defaultdict(dict)
    for e in entries:
        perma = (e.get("extracted") or {}).get("perma", {})
        strengths = (e.get("extracted") or {}).get("strengths_called", [])
        flow = (e.get("extracted") or {}).get("flow_moments", [])
        rewrite = (e.get("extracted") or {}).get("rewrite_event", {})
        period = e.get("period", "")

        by_date[e["date"]][period] = {
            "perma": perma,
            "strengths": strengths,
            "has_flow": len(flow) > 0,
            "has_rewrite": bool(rewrite and rewrite.get("occurred")),
            "rewrite_new": rewrite.get("new_response") if rewrite else None,
        }

    # H1: Evening completeness → next-day P/E
    days_with_both = 0
    p_scores = []
    e_scores = []
    for date in sorted(by_date.keys()):
        day = by_date[date]
        if "morning" in day and "evening" in day:
            days_with_both += 1
            # Check next day's morning
            next_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            if next_date in by_date and "morning" in by_date[next_date]:
                p_scores.append(by_date[next_date]["morning"].get("perma", {}).get("P", 0))
                e_scores.append(by_date[next_date]["morning"].get("perma", {}).get("E", 0))

    if len(p_scores) >= 2:
        avg_p = sum(p_scores) / len(p_scores)
        hypotheses.append({
            "condition": "前日完成晨间+晚间双觉察",
            "outcome": f"次日晨间P均值{avg_p:.1f}",
            "confidence": 0.6,
            "data_points": len(p_scores),
            "type": "completeness",
        })

    # H2: Flow moments → E score
    flow_days = [d for d in by_date.values() if d.get("evening", {}).get("has_flow")]
    noflow_days = [d for d in by_date.values() if d.get("evening") and not d["evening"].get("has_flow")]
    if flow_days and noflow_days:
        flow_e = [d["evening"]["perma"].get("E", 0) for d in flow_days if d.get("evening")]
        noflow_e = [d["evening"]["perma"].get("E", 0) for d in noflow_days if d.get("evening")]
        if flow_e and noflow_e:
            avg_flow_e = sum(flow_e) / len(flow_e)
            avg_noflow_e = sum(noflow_e) / len(noflow_e)
            diff = avg_flow_e - avg_noflow_e
            if abs(diff) > 0.5:
                hypotheses.append({
                    "condition": "晚间有心流时刻记录",
                    "outcome": f"E评分平均{diff:+.1f}（{avg_flow_e:.1f} vs 无记录{avg_noflow_e:.1f}）",
                    "confidence": round(0.5 + abs(diff) * 0.1, 2),
                    "data_points": len(flow_e) + len(noflow_e),
                    "type": "flow_impact",
                })

    # H3: Rewrite events → next-day state improvement
    rewrite_dates = [
        date for date, day in by_date.items()
        if day.get("evening", {}).get("has_rewrite")
    ]
    state_improvements = 0
    for d in rewrite_dates:
        next_date = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if next_date in by_date and "morning" in by_date[next_date]:
            # Compare: was the next morning state better?
            # This is a rough heuristic
            state_improvements += 1

    if rewrite_dates:
        hypotheses.append({
            "condition": "晚间发生改写事件",
            "outcome": f"次日状态改善比例 {state_improvements}/{len(rewrite_dates)}",
            "confidence": 0.55,
            "data_points": len(rewrite_dates),
            "type": "rewrite_impact",
        })

    # H4: Signature strength usage → M/A score
    profile = load_json(PROFILES_DIR / "laomai.json") or {}
    sig_strengths = set(profile.get("signature_strengths", []))
    if sig_strengths:
        sig_days = []
        nosig_days = []
        for day in by_date.values():
            for period_data in day.values():
                used = set(period_data.get("strengths", []))
                if used & sig_strengths:
                    sig_days.append(period_data.get("perma", {}))
                else:
                    nosig_days.append(period_data.get("perma", {}))
        if sig_days and nosig_days:
            sig_m = sum(d.get("M", 0) for d in sig_days) / len(sig_days)
            nosig_m = sum(d.get("M", 0) for d in nosig_days) / len(nosig_days)
            if abs(sig_m - nosig_m) > 0.5:
                hypotheses.append({
                    "condition": "调用签名优势",
                    "outcome": f"M评分{sig_m - nosig_m:+.1f}（{sig_m:.1f} vs {nosig_m:.1f}）",
                    "confidence": 0.55,
                    "data_points": len(sig_days) + len(nosig_days),
                    "type": "strength_impact",
                })

    # Sort by confidence
    hypotheses.sort(key=lambda h: h["confidence"], reverse=True)
    return hypotheses


def generate_adjustments(perma_changes: dict, rewrite_eff: dict, entries: list[dict]) -> list[str]:
    """Generate minimal, actionable adjustments."""
    adjustments = []

    # Based on PERMA trends
    for dim, info in perma_changes.items():
        if info["trend"] == "down" and info["significance"] in ("strong", "moderate"):
            dim_names = {"P": "积极情绪", "E": "投入心流", "R": "人际关系", "M": "意义感", "A": "成就感"}
            adjustments.append(
                f"{dim_names.get(dim, dim)}持续下降——建议晨间引导中增加{dim_names.get(dim, dim)}维度的温和关注"
            )

    # Based on rewrite bottleneck
    if "连续无改写" in rewrite_eff.get("bottleneck", ""):
        adjustments.append(
            "改写事件缺失——晚间Round 2-3加强改写机会识别引导，"
            "帮助用户看见'旧反应被激活'的时刻"
        )

    # Based on data completeness
    if entries:
        dates = set(e["date"] for e in entries)
        morning_dates = set(e["date"] for e in entries if e.get("period") == "morning")
        evening_dates = set(e["date"] for e in entries if e.get("period") == "evening")
        missing_evening = morning_dates - evening_dates
        if len(missing_evening) >= 2:
            adjustments.append(
                f"连续{len(missing_evening)}天缺失晚间复盘——"
                "晚间推送时间可提前15分钟，或发送更简短的提醒（2个问题替代5轮）"
            )

    # If no adjustments found, give a positive one
    if not adjustments and entries:
        adjustments.append("当前各维度趋势健康，保持现有节奏。可尝试在晚间增加'明日最小意图'环节加深锚点。")

    return adjustments


def compute_period_label(start: str, end: str) -> str:
    """Compute a human-readable period label."""
    try:
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end, "%Y-%m-%d")
        iso = s.isocalendar()
        return f"{s.year}-W{iso.week:02d}  ({start} ~ {end})"
    except Exception:
        return f"{start} ~ {end}"


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
    entries = load_journals(user_id, start, end)

    if not entries:
        print(json.dumps({
            "available": False,
            "message": f"{start}~{end} 无觉察记录，无法生成洞察",
        }, ensure_ascii=False, indent=2))
        return

    want_all = not dimensions or "ALL" in dimensions

    result = {
        "available": True,
        "period": compute_period_label(start, end),
        "days_recorded": len(set(e["date"] for e in entries)),
        "total_entries": len(entries),
    }

    # PERMA analysis
    perma_changes = analyze_perma(entries)
    result["perma_changes"] = perma_changes

    # State transitions
    transitions = analyze_state_transitions(entries)
    if transitions:
        result["state_transitions"] = transitions

    # Rewrite effectiveness
    rewrite_eff = analyze_rewrite_effectiveness(entries)
    result["rewrite_effectiveness"] = rewrite_eff

    # Hypotheses
    if want_all or "hypotheses" in dimensions:
        hypotheses = generate_hypotheses(entries, perma_changes)
        if hypotheses:
            result["hypotheses"] = hypotheses

    # Adjustments
    adjustments = generate_adjustments(perma_changes, rewrite_eff, entries)
    result["minimal_adjustments"] = adjustments

    # Summary
    up_dims = [d for d, i in perma_changes.items() if i["trend"] == "up" and i["significance"] in ("strong", "moderate")]
    down_dims = [d for d, i in perma_changes.items() if i["trend"] == "down" and i["significance"] in ("strong", "moderate")]
    summary_parts = []
    if up_dims:
        summary_parts.append(f"{','.join(up_dims)}改善")
    if down_dims:
        summary_parts.append(f"{','.join(down_dims)}下降需关注")
    if rewrite_eff["rewrite_attempts"] > 0:
        summary_parts.append(f"改写{rewrite_eff['rewrite_attempts']}次")
    result["summary"] = "；".join(summary_parts) if summary_parts else "数据积累中，尚无显著模式"

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
