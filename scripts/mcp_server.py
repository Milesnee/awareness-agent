#!/usr/bin/env python3
"""
Awareness Agent MCP Server — exposes 7 awareness primitives as MCP tools.

Registered tools (prefixed mcp_awareness_*):
  L1: awareness_profile, awareness_journal_query, awareness_state_detect
  L2: awareness_guide, awareness_record
  L3: awareness_pattern_review, awareness_quality_score, awareness_intervention

Usage:
  python3 mcp_server.py

Hermes config:
  mcp_servers:
    awareness:
      command: "python3"
      args: ["/root/projects/awareness-agent/scripts/mcp_server.py"]
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# ── Add project root to path for imports ────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ── Import primitive functions ──────────────────────────────────
from awareness_profile import main as profile_main, compute_summary
from awareness_journal_query import main as journal_main, query_journals, parse_timespan
from awareness_state_detect import detect_state
from awareness_guide import main as guide_main
from awareness_record import main as record_main
from awareness_pattern_review import main as review_main, analyze_perma, analyze_state_transitions, analyze_rewrite_effectiveness, generate_hypotheses, generate_adjustments
from awareness_quality_score import score_session, detect_flags, compute_baseline
from awareness_intervention import compute_intervention

# ── Helper: load JSON from path ─────────────────────────────────
DATA_DIR = PROJECT_ROOT.parent / "data"


def load_json(path: Path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


# ── Server setup ────────────────────────────────────────────────
server = Server("awareness-agent", version="1.0.0")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # L1 — Perception
        Tool(
            name="awareness_profile",
            description="加载用户觉察档案：PERMA基线、签名优势、streak、风险/成长信号。输入 user_id。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID，如 laomai"}
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="awareness_journal_query",
            description="查询历史觉察记录：PERMA趋势、状态序列、品格优势调用、改写事件、数据间隙。输入 user_id + timespan(如'7d')。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "timespan": {"type": "string", "description": "时间跨度：'7d','30d','this_week'"},
                    "dimensions": {"type": "array", "items": {"type": "string"}, "description": "可选：PERMA,states,strengths,rewrite,gaps. 不传返回全部。"},
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="awareness_state_detect",
            description="从自然语言识别用户当前状态：停不下来/启动不了/硬撑着/一直在找。带置信度和引导建议。",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "用户输入的自然语言文本"},
                },
                "required": ["text"],
            },
        ),
        # L2 — Action
        Tool(
            name="awareness_guide",
            description="上下文感知的觉察引导问题生成。输入 user_id + period(morning/evening) + round(1-5)，输出 context + decision + suggested_question。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "period": {"type": "string", "enum": ["morning", "evening"]},
                    "round": {"type": "integer", "minimum": 1, "maximum": 5},
                    "user_name": {"type": "string", "default": "老麦"},
                    "date": {"type": "string", "description": "YYYY-MM-DD，默认今天"},
                    "user_reply": {"type": "string", "description": "上一轮用户回复（Round 2+）"},
                },
                "required": ["user_id", "period", "round"],
            },
        ),
        Tool(
            name="awareness_record",
            description="保存结构化觉察记录。自动完成 schema校验→保存journal→更新streak→更新profile→检测趋势触发。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "period": {"type": "string", "enum": ["morning", "evening"]},
                    "extracted": {
                        "type": "object",
                        "properties": {
                            "perma": {"type": "object"},
                            "strengths_called": {"type": "array", "items": {"type": "string"}},
                            "flow_moments": {"type": "array", "items": {"type": "string"}},
                            "emotional_arc": {"type": "object"},
                            "rewrite_event": {"type": "object"},
                            "gratitude": {"type": "string"},
                        },
                    },
                    "session_meta": {
                        "type": "object",
                        "properties": {
                            "rounds": {"type": "integer"},
                            "duration_seconds": {"type": "integer"},
                            "trigger": {"type": "string"},
                            "model": {"type": "string"},
                        },
                    },
                },
                "required": ["user_id", "date", "period"],
            },
        ),
        # L3 — Metacognition
        Tool(
            name="awareness_pattern_review",
            description="跨时段模式分析：PERMA趋势+显著性、状态切换、改写效果、假设生成、最小调整建议。是周洞察报告的自动化引擎。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "timespan": {"type": "string", "description": "'7d','30d','this_week'"},
                    "dimensions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="awareness_quality_score",
            description="评估单次觉察对话质量：深度/完整度/改写质量/数据质量/投入度。含7日基线对比。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "session_data": {
                        "type": "object",
                        "properties": {
                            "extracted": {"type": "object"},
                            "session_meta": {"type": "object"},
                        },
                    },
                },
                "required": ["session_data"],
            },
        ),
        Tool(
            name="awareness_intervention",
            description="干预决策引擎：基于质量趋势+标志+streak风险，决定是否改变引导策略。",
            inputSchema={
                "type": "object",
                "properties": {
                    "quality_trend": {"type": "array", "items": {"type": "number"}, "description": "最近N次质量评分"},
                    "flags": {"type": "array", "items": {"type": "string"}, "description": "当前标志列表"},
                    "streak_current": {"type": "integer"},
                    "streak_at_risk": {"type": "boolean", "default": False},
                },
                "required": ["quality_trend", "flags", "streak_current"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch to the correct primitive."""
    try:
        if name == "awareness_profile":
            user_id = arguments["user_id"]
            profile = load_json(DATA_DIR / "profiles" / f"{user_id}.json") or {}
            streak = load_json(DATA_DIR / "streaks" / f"{user_id}.json") or {}
            journals_exist = (DATA_DIR / "journals" / user_id).exists()
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
                },
                "summary": summary,
            }

        elif name == "awareness_journal_query":
            user_id = arguments["user_id"]
            timespan = arguments.get("timespan", "7d")
            dimensions = arguments.get("dimensions", [])
            start, end = parse_timespan(timespan)
            result = query_journals(user_id, start, end, dimensions)

        elif name == "awareness_state_detect":
            text = arguments["text"]
            result = detect_state(text)

        elif name == "awareness_guide":
            # Build params and run through guide logic
            user_id = arguments["user_id"]
            period = arguments["period"]
            round_num = arguments["round"]
            user_name = arguments.get("user_name", "老麦")
            date_str = arguments.get("date", "")
            user_reply = arguments.get("user_reply")

            from datetime import datetime
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")

            # Load data (mirroring guide_main logic)
            profile = load_json(DATA_DIR / "profiles" / f"{user_id}.json") or {}
            streak = load_json(DATA_DIR / "streaks" / f"{user_id}.json") or {}

            from awareness_guide import load_recent_journals, compute_recent_patterns, \
                decide_focus_dimension, detect_intervention_flags, select_science_hooks, \
                determine_dont_do, generate_demo_question

            entries = load_recent_journals(user_id)
            patterns = compute_recent_patterns(entries)
            decision = decide_focus_dimension(profile, patterns, period, round_num)
            flags = detect_intervention_flags(profile, patterns, streak)
            science_hooks = select_science_hooks(flags, period, round_num)
            donts = determine_dont_do(flags, period)
            demo_q = generate_demo_question(decision, profile, patterns, streak, user_name, period, round_num, user_reply)

            result = {
                "context": {
                    "profile_summary": {
                        "perma_baseline": profile.get("perma_baseline", {}),
                        "signature_strengths": profile.get("signature_strengths", []),
                        "recent_states": profile.get("state_history", [])[-5:],
                    },
                    "recent_patterns": patterns,
                    "state_context": {"user_reply": user_reply, "period": period, "round": round_num},
                    "intervention_flags": flags,
                    "streak": {"current": streak.get("current", 0), "milestone": streak.get("milestone", "🌱"), "longest": streak.get("longest", 0)},
                    "user_name": user_name,
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
                "suggested_question": demo_q,
            }

        elif name == "awareness_record":
            user_id = arguments["user_id"]
            date_str = arguments["date"]
            period = arguments["period"]
            extracted = arguments.get("extracted", {})
            session_meta = arguments.get("session_meta", {})

            from awareness_record import (
                validate_input, compute_data_quality, update_streak,
                detect_insight_triggers, update_profile, save_json, JOURNALS_DIR
            )

            data = {"user_id": user_id, "date": date_str, "period": period, "extracted": extracted, "session_meta": session_meta}
            warnings = validate_input(data)

            journal_path = JOURNALS_DIR / user_id / f"{date_str}_{period}.json"
            save_json(journal_path, {
                "user_id": user_id, "date": date_str, "period": period,
                "extracted": extracted, "session_meta": session_meta,
                "saved_at": datetime.now().isoformat(),
            })

            streak_info = update_streak(user_id, date_str, period)
            quality = compute_data_quality(extracted, period)
            triggers = detect_insight_triggers(user_id, date_str, extracted)
            update_profile(user_id, extracted, date_str)

            result = {
                "saved": True,
                "path": str(journal_path.relative_to(PROJECT_ROOT.parent)),
                "streak_updated": streak_info,
                "data_quality": quality,
                "new_insight_triggers": triggers,
                "validation_warnings": warnings,
            }

        elif name == "awareness_pattern_review":
            user_id = arguments["user_id"]
            timespan = arguments.get("timespan", "7d")
            dimensions = arguments.get("dimensions", [])

            start, end = parse_timespan(timespan)
            from awareness_pattern_review import load_journals, compute_period_label

            entries = load_journals(user_id, start, end)
            if not entries:
                result = {"available": False, "message": f"{start}~{end} 无觉察记录"}
            else:
                perma_changes = analyze_perma(entries)
                transitions = analyze_state_transitions(entries)
                rewrite_eff = analyze_rewrite_effectiveness(entries)
                want_all = not dimensions or "ALL" in dimensions

                result = {
                    "available": True,
                    "period": compute_period_label(start, end),
                    "days_recorded": len(set(e["date"] for e in entries)),
                    "total_entries": len(entries),
                    "perma_changes": perma_changes,
                    "state_transitions": transitions,
                    "rewrite_effectiveness": rewrite_eff,
                }
                if want_all or "hypotheses" in dimensions:
                    hyps = generate_hypotheses(entries, perma_changes)
                    if hyps:
                        result["hypotheses"] = hyps
                result["minimal_adjustments"] = generate_adjustments(perma_changes, rewrite_eff, entries)

                up_dims = [d for d, i in perma_changes.items() if i["trend"] == "up" and i["significance"] in ("strong", "moderate")]
                down_dims = [d for d, i in perma_changes.items() if i["trend"] == "down" and i["significance"] in ("strong", "moderate")]
                parts = []
                if up_dims: parts.append(f"{','.join(up_dims)}改善")
                if down_dims: parts.append(f"{','.join(down_dims)}下降需关注")
                if rewrite_eff["rewrite_attempts"] > 0:
                    parts.append(f"改写{rewrite_eff['rewrite_attempts']}次")
                result["summary"] = "；".join(parts) if parts else "数据积累中"

        elif name == "awareness_quality_score":
            user_id = arguments.get("user_id")
            session_data = arguments["session_data"]
            extracted = session_data.get("extracted") or {}
            meta = session_data.get("session_meta") or {}

            scores = score_session(extracted, meta)
            baseline = compute_baseline(user_id) if user_id else None

            history_rewrites = []
            if user_id:
                user_dir = DATA_DIR / "journals" / user_id
                if user_dir.exists():
                    for f in sorted(user_dir.glob("*.json"), reverse=True)[:5]:
                        d = load_json(f)
                        if d:
                            rew = (d.get("extracted") or {}).get("rewrite_event")
                            if rew and rew.get("occurred"):
                                history_rewrites.append({"date": d["date"], "new": rew.get("new_response")})

            flags = detect_flags(extracted, meta, history_rewrites)

            result = {**scores, "flags": flags if flags else ["无明显质量标志"]}
            if baseline:
                diff = scores["overall"] - baseline["overall"]
                result["comparison_to_baseline"] = {
                    "overall": f"{diff:+.2f} vs 7日均值({baseline['overall']})",
                    "baseline_sample": baseline.get("sample_size", 0),
                }

        elif name == "awareness_intervention":
            quality_trend = arguments["quality_trend"]
            flags = arguments["flags"]
            streak_current = arguments["streak_current"]
            streak_risk = arguments.get("streak_at_risk", False)
            result = compute_intervention(quality_trend, flags, streak_current, streak_risk)

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False))]

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
