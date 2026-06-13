#!/usr/bin/env python3
"""
session_tracker.py — 觉察助手与 OpenClaw 互动统计追踪

用法:
  # 记录一次互动
  python3 session_tracker.py log --user ou_xxx --date 2026-05-14 --period morning \
    --duration-seconds 45 --rounds 3 --model GLM-5-Turbo --trigger heartbeat

  # 查看统计
  python3 session_tracker.py stats --user ou_xxx --days 7
  python3 session_tracker.py stats --user ou_xxx --days 30

  # 查看原始记录
  python3 session_tracker.py list --user ou_xxx --days 7
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
STATS_DIR = DATA_DIR / "stats"


def ensure_dirs():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    STATS_DIR.mkdir(parents=True, exist_ok=True)


def log_session(user_id: str, date: str, period: str, duration_seconds: int,
                rounds: int, model: str, trigger: str,
                perma_complete: bool = False, rewrite_confirmed: bool = False):
    """记录一次觉察互动"""
    ensure_dirs()
    path = SESSIONS_DIR / f"{date}.json"

    # 加载或创建
    if path.exists():
        with open(path) as f:
            data = json.load(f)
    else:
        data = {"date": date, "sessions": []}

    session = {
        "user_id": user_id,
        "period": period,
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": duration_seconds,
        "rounds": rounds,
        "model": model,
        "trigger": trigger,
        "perma_complete": perma_complete,
        "rewrite_confirmed": rewrite_confirmed,
    }

    # 如果同一天同一period已有记录，覆盖
    data["sessions"] = [s for s in data["sessions"]
                        if not (s["period"] == period and s["user_id"] == user_id)]
    data["sessions"].append(session)

    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Logged: {date} {period} ({duration_seconds}s, {rounds} rounds, {model}, {trigger})")


def compute_stats(user_id: str, days: int):
    """计算互动统计"""
    ensure_dirs()
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    all_sessions = []
    morning_count = 0
    evening_count = 0

    current = start_date
    while current <= end_date:
        path = SESSIONS_DIR / f"{current.isoformat()}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            for s in data.get("sessions", []):
                if s["user_id"] == user_id:
                    all_sessions.append(s)
                    if s["period"] == "morning":
                        morning_count += 1
                    elif s["period"] == "evening":
                        evening_count += 1
        current += timedelta(days=1)

    if not all_sessions:
        print(f"📊 No sessions found for user {user_id} in the last {days} days")
        return

    # 计算统计
    durations = [s["duration_seconds"] for s in all_sessions if s.get("duration_seconds")]
    rounds_list = [s["rounds"] for s in all_sessions if s.get("rounds")]
    models = [s["model"] for s in all_sessions if s.get("model")]
    triggers = [s["trigger"] for s in all_sessions if s.get("trigger")]
    perma_complete_count = sum(1 for s in all_sessions if s.get("perma_complete"))
    rewrite_count = sum(1 for s in all_sessions if s.get("rewrite_confirmed"))

    # 按period分组统计
    morning_sessions = [s for s in all_sessions if s["period"] == "morning"]
    evening_sessions = [s for s in all_sessions if s["period"] == "evening"]

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    def fmt_duration(seconds):
        if seconds < 60:
            return f"{seconds}s"
        return f"{seconds // 60}m {seconds % 60}s"

    # 模型分布
    model_counts = {}
    for m in models:
        model_counts[m] = model_counts.get(m, 0) + 1

    # 触发方式分布
    trigger_counts = {}
    for t in triggers:
        trigger_counts[t] = trigger_counts.get(t, 0) + 1

    total_days = days
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    print(f"📊 觉察互动统计 ({start_str} ~ {end_str}, {total_days}天)")
    print(f"")
    print(f"完成率: 晨间 {morning_count}/{total_days} ({morning_count/total_days*100:.0f}%) | "
          f"晚间 {evening_count}/{total_days} ({evening_count/total_days*100:.0f}%)")
    print(f"总互动次数: {len(all_sessions)}")
    print(f"")

    if morning_sessions:
        m_dur = [s["duration_seconds"] for s in morning_sessions if s.get("duration_seconds")]
        m_rnd = [s["rounds"] for s in morning_sessions if s.get("rounds")]
        print(f"晨间平均: {fmt_duration(int(avg(m_dur)))} | {avg(m_rnd):.1f}轮")

    if evening_sessions:
        e_dur = [s["duration_seconds"] for s in evening_sessions if s.get("duration_seconds")]
        e_rnd = [s["rounds"] for s in evening_sessions if s.get("rounds")]
        print(f"晚间平均: {fmt_duration(int(avg(e_dur)))} | {avg(e_rnd):.1f}轮")

    print(f"")
    print(f"PERMA完整率: {perma_complete_count}/{len(all_sessions)} ({perma_complete_count/len(all_sessions)*100:.0f}%)")
    print(f"改写确认率: {rewrite_count}/{len(all_sessions)} ({rewrite_count/len(all_sessions)*100:.0f}%)")
    print(f"")
    print(f"模型分布: {', '.join(f'{k} {v}' for k, v in sorted(model_counts.items(), key=lambda x: -x[1]))}")
    print(f"触发方式: {', '.join(f'{k} {v}' for k, v in sorted(trigger_counts.items(), key=lambda x: -x[1]))}")

    # 保存统计
    stats_data = {
        "period": f"{start_str} ~ {end_str}",
        "user_id": user_id,
        "total_sessions": len(all_sessions),
        "morning_count": morning_count,
        "evening_count": evening_count,
        "avg_duration_seconds": int(avg(durations)),
        "avg_rounds": round(avg(rounds_list), 1),
        "perma_complete_rate": round(perma_complete_count / len(all_sessions) * 100, 1),
        "rewrite_confirmed_rate": round(rewrite_count / len(all_sessions) * 100, 1),
        "model_distribution": model_counts,
        "trigger_distribution": trigger_counts,
        "generated_at": datetime.now().isoformat(),
    }
    stats_path = STATS_DIR / f"{'weekly' if days <= 7 else 'monthly'}_{end_str}.json"
    with open(stats_path, "w") as f:
        json.dump(stats_data, f, indent=2, ensure_ascii=False)
    print(f"\n📁 Stats saved to {stats_path}")


def list_sessions(user_id: str, days: int):
    """列出原始互动记录"""
    ensure_dirs()
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days - 1)

    current = start_date
    while current <= end_date:
        path = SESSIONS_DIR / f"{current.isoformat()}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            for s in data.get("sessions", []):
                if s["user_id"] == user_id:
                    print(f"  {s['period']:8s} | {s.get('duration_seconds', '?'):>4}s | "
                          f"{s.get('rounds', '?'):>2} rounds | {s.get('model', '?'):20s} | "
                          f"{s.get('trigger', '?'):10s} | perma:{s.get('perma_complete', False)} | "
                          f"rewrite:{s.get('rewrite_confirmed', False)}")
        current += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser(description="觉察助手互动统计追踪")
    subparsers = parser.add_subparsers(dest="command")

    # log
    log_p = subparsers.add_parser("log", help="记录一次互动")
    log_p.add_argument("--user", required=True)
    log_p.add_argument("--date", required=True)
    log_p.add_argument("--period", required=True, choices=["morning", "evening"])
    log_p.add_argument("--duration-seconds", type=int, default=0)
    log_p.add_argument("--rounds", type=int, default=0)
    log_p.add_argument("--model", default="unknown")
    log_p.add_argument("--trigger", default="heartbeat")
    log_p.add_argument("--perma-complete", action="store_true")
    log_p.add_argument("--rewrite-confirmed", action="store_true")

    # stats
    stats_p = subparsers.add_parser("stats", help="查看统计")
    stats_p.add_argument("--user", required=True)
    stats_p.add_argument("--days", type=int, default=7)

    # list
    list_p = subparsers.add_parser("list", help="列出原始记录")
    list_p.add_argument("--user", required=True)
    list_p.add_argument("--days", type=int, default=7)

    args = parser.parse_args()

    if args.command == "log":
        log_session(args.user, args.date, args.period,
                     args.duration_seconds, args.rounds, args.model, args.trigger,
                     args.perma_complete, args.rewrite_confirmed)
    elif args.command == "stats":
        compute_stats(args.user, args.days)
    elif args.command == "list":
        list_sessions(args.user, args.days)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
