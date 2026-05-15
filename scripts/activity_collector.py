#!/usr/bin/env python3
"""
activity_collector.py — 每日活动自动收集器

从多处数据源聚合用户当日活动，写入觉察助手的 journal.daily_context，
为周洞察的 AAR「行为 vs 叙事偏差」提供"行为数据"。

用法:
  # 收集今天活动
  python3 activity_collector.py collect --user ou_xxx

  # 收集指定日期
  python3 activity_collector.py collect --user ou_xxx --date 2026-05-15

  # 查看已收集的活动
  python3 activity_collector.py show --user ou_xxx --date 2026-05-15

  # 补收最近N天
  python3 activity_collector.py backfill --user ou_xxx --days 7

数据源（按优先级）:
  1. memory/YYYY-MM-DD.md        — 每日手动/自动日报
  2. memory/agent-productivity/   — 生产力日报（cron 自动生成）
  3. awareness data/sessions/     — 觉察互动记录
  4. HEARTBEAT.md 执行记录       — 定时任务执行情况
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent.parent.parent  # workspace root
DATA_DIR = Path(__file__).parent.parent / "data"

# 数据源路径
MEMORY_DIR = WORKSPACE / "memory"
PRODUCTIVITY_DIR = MEMORY_DIR / "agent-productivity"
HEARTBEAT_FILE = WORKSPACE / "HEARTBEAT.md"


def get_user_dir(user_id: str) -> Path:
    return DATA_DIR / "users" / user_id


def get_journal_path(user_id: str, date_str: str) -> Path:
    return get_user_dir(user_id) / "journals" / f"{date_str}.json"


def extract_from_daily_memory(date_str: str) -> dict:
    """从 memory/YYYY-MM-DD.md 提取活动"""
    path = MEMORY_DIR / f"{date_str}.md"
    if not path.exists():
        return {"source": "memory_daily", "available": False, "note": "日报尚未生成"}

    with open(path) as f:
        content = f.read()

    # 提取关键段落
    sections = {}
    current_section = "header"

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections[current_section] = []
        elif not line.startswith("#"):
            sections.setdefault(current_section, []).append(line)

    # 尝试识别关键信息
    activities = []
    decisions = []
    projects_active = set()

    for section, lines in sections.items():
        section_lower = section.lower()
        if any(kw in section_lower for kw in ["完成", "done", "今日完成"]):
            for l in lines:
                l = re.sub(r'^[\s•\-\*✅]+', '', l).strip()
                if l and len(l) > 3:
                    activities.append({"activity": l, "section": section, "status": "completed"})
        elif any(kw in section_lower for kw in ["进行", "doing", "in_progress", "待办", "todo"]):
            for l in lines:
                l = re.sub(r'^[\s•\-\*📝⬜\[\]\s]+', '', l).strip()
                if l and len(l) > 3:
                    activities.append({"activity": l, "section": section, "status": "in_progress"})
        elif any(kw in section_lower for kw in ["决策", "决策", "重要"]):
            for l in lines:
                l = re.sub(r'^[\s•\-\*]+', '', l).strip()
                if l and len(l) > 3:
                    decisions.append(l)

        # 检测项目名
        for proj in ["论文", "量化", "觉察助手", "swarmart", "zhidaya", "简历", "税务"]:
            if proj in section or any(proj in l for l in lines):
                projects_active.add(proj)

    return {
        "source": "memory_daily",
        "available": True,
        "sections_found": list(sections.keys()),
        "activities": activities[:20],  # 最多20条
        "decisions": decisions[:5],
        "projects_active": list(projects_active),
    }


def extract_from_productivity(date_str: str) -> dict:
    """从 productivity 日报提取"""
    path = PRODUCTIVITY_DIR / f"{date_str}.md"
    if not path.exists():
        return {"source": "productivity", "available": False}

    with open(path) as f:
        content = f.read()

    # 提取指标
    metrics = {}
    for line in content.split("\n"):
        m = re.search(r'[-•]\s*\*{0,2}([^*]+?)\*{0,2}\s*[:：]\s*(.+)', line)
        if m:
            metrics[m.group(1).strip()] = m.group(2).strip()

    return {
        "source": "productivity",
        "available": True,
        "metrics": metrics,
        "content_preview": content[:500],
    }


def extract_from_awareness_sessions(user_id: str, date_str: str) -> dict:
    """从觉察助手 sessions 记录提取"""
    path = get_user_dir(user_id) / "sessions" / f"{date_str}.json"
    if not path.exists():
        return {"source": "awareness_sessions", "available": False}

    with open(path) as f:
        data = json.load(f)

    sessions = data.get("sessions", [])
    summary = {
        "source": "awareness_sessions",
        "available": True,
        "total_sessions": len(sessions),
        "periods_done": [s["period"] for s in sessions],
        "total_duration_seconds": sum(s.get("duration_seconds", 0) for s in sessions),
        "triggers": [s.get("trigger") for s in sessions],
    }

    return summary


def extract_from_heartbeat(date_str: str) -> dict:
    """从 HEARTBEAT.md 读取当天执行过的任务（粗略估计）"""
    # heartbeat 是任务定义，不是执行记录
    # 这里只做简单检测——如果 heartbeat 有觉察相关配置，说明系统在跑
    if not HEARTBEAT_FILE.exists():
        return {"source": "heartbeat", "available": False}

    with open(HEARTBEAT_FILE) as f:
        content = f.read()

    tasks_active = []
    if "觉察助手" in content:
        tasks_active.append("觉察助手定时推送")
    if "资本周期" in content:
        tasks_active.append("资本周期观察池")
    if "ClawCast" in content:
        tasks_active.append("ClawCast学习")
    if "feishu-briefing" in content:
        tasks_active.append("飞书简报")

    return {
        "source": "heartbeat",
        "available": True,
        "tasks_configured": tasks_active,
    }


def collect_daily_activity(user_id: str, date_str: str) -> dict:
    """聚合所有数据源，生成 daily_context"""
    collected_at = datetime.now().isoformat()

    # 收集各数据源
    memory_data = extract_from_daily_memory(date_str)
    productivity_data = extract_from_productivity(date_str)
    awareness_data = extract_from_awareness_sessions(user_id, date_str)
    heartbeat_data = extract_from_heartbeat(date_str)

    # 聚合
    all_activities = memory_data.get("activities", [])
    all_decisions = memory_data.get("decisions", [])
    all_projects = set(memory_data.get("projects_active", []))
    all_sources = []

    for src in [memory_data, productivity_data, awareness_data, heartbeat_data]:
        if src.get("available"):
            all_sources.append(src["source"])

    daily_context = {
        "collected_at": collected_at,
        "date": date_str,
        "sources_available": all_sources,
        "projects_active": sorted(all_projects),
        "activities": all_activities,
        "decisions": all_decisions,
        "awareness_sessions": awareness_data if awareness_data.get("available") else None,
        "productivity_metrics": productivity_data.get("metrics", {}) if productivity_data.get("available") else {},
        "heartbeat_tasks": heartbeat_data.get("tasks_configured", []) if heartbeat_data.get("available") else [],
        "activity_count": len(all_activities),
        "note": "auto-collected by activity_collector.py",
    }

    # 写入 journal
    journal_path = get_journal_path(user_id, date_str)
    if journal_path.exists():
        with open(journal_path) as f:
            journal = json.load(f)
    else:
        journal = {
            "date": date_str,
            "streak": 0,
            "level": "seed",
            "morning": {"timestamp": None, "extracted_insights": []},
            "evening": {"timestamp": None, "extracted_insights": []},
        }

    journal["daily_context"] = daily_context

    get_user_dir(user_id).mkdir(parents=True, exist_ok=True)
    (get_user_dir(user_id) / "journals").mkdir(parents=True, exist_ok=True)

    with open(journal_path, "w") as f:
        json.dump(journal, f, indent=2, ensure_ascii=False)

    return daily_context


def show_activity(user_id: str, date_str: str):
    """查看已收集的活动"""
    path = get_journal_path(user_id, date_str)
    if not path.exists():
        print(f"📭 {date_str} 无 journal 记录")
        return

    with open(path) as f:
        journal = json.load(f)

    context = journal.get("daily_context")
    if not context:
        print(f"📭 {date_str} 无 daily_context，请先运行 collect")
        return

    print(f"📅 {date_str} 活动概览")
    print(f"   数据源: {', '.join(context.get('sources_available', []))}")
    print(f"   活跃项目: {', '.join(context.get('projects_active', []))}")
    print(f"   活动记录: {context.get('activity_count', 0)} 条")
    print()

    for act in context.get("activities", []):
        status_icon = "✅" if act["status"] == "completed" else "🔄"
        print(f"   {status_icon} [{act.get('section', '')}] {act['activity']}")

    if context.get("decisions"):
        print(f"\n   💡 重要决策:")
        for d in context["decisions"]:
            print(f"      • {d}")

    if context.get("awareness_sessions"):
        aw = context["awareness_sessions"]
        print(f"\n   🌱 觉察互动: {aw.get('total_sessions', 0)} 次 "
              f"({', '.join(aw.get('periods_done', []))})")

    if context.get("productivity_metrics"):
        print(f"\n   📊 生产力指标:")
        for k, v in context["productivity_metrics"].items():
            print(f"      {k}: {v}")

    print()


def backfill(user_id: str, days: int):
    """补收最近N天"""
    today = datetime.now().date()
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        print(f"📥 收集 {date_str}...", end=" ")
        context = collect_daily_activity(user_id, date_str)
        print(f"✅ {context['activity_count']} 条活动 "
              f"(来源: {', '.join(context['sources_available'])})")


def main():
    parser = argparse.ArgumentParser(description="觉察助手每日活动收集器")
    parser.add_argument("--user", required=True, help="用户ID")
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("collect").add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))

    show_cmd = sub.add_parser("show")
    show_cmd.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))

    backfill_cmd = sub.add_parser("backfill")
    backfill_cmd.add_argument("--days", type=int, default=7)

    args = parser.parse_args()

    if args.action == "collect":
        context = collect_daily_activity(args.user, args.date)
        print(f"✅ 已收集 {args.date} 活动: {context['activity_count']} 条 "
              f"(来源: {', '.join(context['sources_available'])})")
        if context["projects_active"]:
            print(f"   活跃项目: {', '.join(context['projects_active'])}")

    elif args.action == "show":
        show_activity(args.user, args.date)

    elif args.action == "backfill":
        backfill(args.user, args.days)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
