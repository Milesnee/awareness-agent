#!/usr/bin/env python3
"""
task_manager.py — 从 knowledge_fragments 到行动的闭环管理器

核心理念：
  knowledge_fragments 收集用户碎片信息 → 达到一定频次/重要性后
  → 引导用户确认是否转化为 task → 跟踪执行 → 直到完成/循环/放弃

用法:
  # 从 knowledge_fragments 中提取可转化为 task 的候选项
  python3 task_manager.py suggest --user ou_xxx --days 14

  # 创建 task
  python3 task_manager.py create --user ou_xxx --data '{json}'

  # 查看活跃 task
  python3 task_manager.py list --user ou_xxx --status active

  # 更新 task 状态/进度
  python3 task_manager.py update --user ou_xxx --task-id xxx --status completed

  # 添加检查点/进度记录
  python3 task_manager.py checkpoint --user ou_xxx --task-id xxx --note "已完成第一步"

  # 在觉察对话中做每日 recheck
  python3 task_manager.py recheck --user ou_xxx
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TASKS_DIR = DATA_DIR / "tasks"

TASK_STATUSES = ["pending", "active", "completed", "abandoned", "cycling"]
# pending: 已创建但未激活
# active: 正在推进
# completed: 已完成
# abandoned: 已放弃（需记录原因）
# cycling: 持续迭代中（如"保持觉察习惯"这类长期事项）

MAX_ACTIVE_TASKS = 3  # 最多同时 3 个活跃任务，避免压力


def get_tasks_path(user_id: str) -> Path:
    return TASKS_DIR / f"{user_id}.json"


def load_tasks(user_id: str) -> list:
    path = get_tasks_path(user_id)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def save_tasks(user_id: str, tasks: list):
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(get_tasks_path(user_id), "w") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)


def create_task(user_id: str, data: dict) -> dict:
    """创建一个新 task"""
    tasks = load_tasks(user_id)

    # 检查活跃任务数
    active_count = sum(1 for t in tasks if t["status"] == "active")
    if active_count >= MAX_ACTIVE_TASKS and data.get("status") != "pending":
        return {
            "error": f"已有 {active_count} 个活跃任务（上限 {MAX_ACTIVE_TASKS}），请先完成或暂停一个再创建新的",
            "active_tasks": [t["title"] for t in tasks if t["status"] == "active"],
        }

    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    task = {
        "id": task_id,
        "title": data.get("title", "未命名任务"),
        "source": {
            "type": data.get("source_type", "manual"),
            "field": data.get("source_field", ""),
            "date": data.get("source_date", datetime.now().strftime("%Y-%m-%d")),
            "fragment": data.get("source_fragment", ""),
        },
        "status": data.get("status", "pending"),
        "priority": data.get("priority", "medium"),
        "plan_steps": data.get("plan_steps", []),
        "deadline": data.get("deadline"),
        "created": datetime.now().isoformat(),
        "activated": None,
        "completed": None,
        "checkpoints": [],
        "reflections": [],
        "abandon_reason": data.get("abandon_reason", ""),
    }

    tasks.append(task)
    save_tasks(user_id, tasks)
    return task


def update_task(user_id: str, task_id: str, updates: dict) -> dict:
    """更新 task"""
    tasks = load_tasks(user_id)
    for t in tasks:
        if t["id"] == task_id:
            old_status = t["status"]
            t.update(updates)

            if updates.get("status") == "active" and old_status != "active":
                t["activated"] = datetime.now().isoformat()
            elif updates.get("status") in ["completed", "abandoned"]:
                t["completed"] = datetime.now().isoformat()
                if updates.get("status") == "abandoned":
                    t["abandon_reason"] = updates.get("abandon_reason", t.get("abandon_reason", ""))

            save_tasks(user_id, tasks)
            return t

    return {"error": f"task {task_id} not found"}


def add_checkpoint(user_id: str, task_id: str, status: str, note: str) -> dict:
    """添加检查点"""
    tasks = load_tasks(user_id)
    for t in tasks:
        if t["id"] == task_id:
            t.setdefault("checkpoints", []).append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "timestamp": datetime.now().isoformat(),
                "status": status,
                "note": note,
            })
            save_tasks(user_id, tasks)
            return t
    return {"error": f"task {task_id} not found"}


def list_tasks(user_id: str, status: str = None, limit: int = 20) -> list:
    """列出 tasks"""
    tasks = load_tasks(user_id)
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    return tasks[-limit:]


def get_tasks_for_recheck(user_id: str) -> dict:
    """获取每日觉察时需要的 task recheck 信息"""
    tasks = load_tasks(user_id)
    today = datetime.now().strftime("%Y-%m-%d")

    active = [t for t in tasks if t["status"] == "active"]
    overdue = [t for t in tasks if t["status"] == "active"
               and t.get("deadline") and t["deadline"] < today]
    pending = [t for t in tasks if t["status"] == "pending"]

    # 最近完成的
    recent_completed = [t for t in tasks if t["status"] == "completed"
                        and t.get("completed")
                        and t["completed"][:10] >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")]

    # 需要复查的（超过 3 天没 check 的活跃任务）
    stale = []
    for t in active:
        last_check = None
        if t.get("checkpoints"):
            last_check = t["checkpoints"][-1]["date"]
        elif t.get("activated"):
            last_check = t["activated"][:10]
        else:
            last_check = t["created"][:10]
        if last_check and last_check < (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"):
            stale.append(t)

    return {
        "active_count": len(active),
        "active": [{"id": t["id"], "title": t["title"], "deadline": t.get("deadline"),
                     "plan_steps": t.get("plan_steps", []),
                     "last_check": t["checkpoints"][-1]["date"] if t.get("checkpoints") else (t.get("activated") or "")[:10]}
                   for t in active],
        "overdue": [{"id": t["id"], "title": t["title"], "deadline": t["deadline"]} for t in overdue],
        "pending": [{"id": t["id"], "title": t["title"]} for t in pending],
        "stale": [{"id": t["id"], "title": t["title"], "days_since_check": (
            datetime.now().date() - datetime.strptime(
                t["checkpoints"][-1]["date"] if t.get("checkpoints") else t.get("activated", "")[:10],
                "%Y-%m-%d"
            ).date()
        ).days} for t in stale],
        "recent_completed": [{"id": t["id"], "title": t["title"],
                               "completed": t.get("completed", "")[:10]} for t in recent_completed],
        "total_tasks": len(tasks),
    }


def suggest_tasks_from_fragments(user_id: str, days: int = 14) -> list:
    """从觉察 journals 中智能提取可转化为 task 的候选项

    Note: 旧版依赖 journal_manager.py（已废弃）。现改用 awareness_journal_query 原语。
    """
    import importlib.util, subprocess, json

    # 调用 awareness_journal_query 原语获取近期记录
    query_script = Path(__file__).parent / "awareness_journal_query.py"
    if not query_script.exists():
        return [{"type": "error", "suggestion": "awareness_journal_query.py 不存在，无法提取建议", "priority": "low"}]

    try:
        result = subprocess.run(
            ["python3", str(query_script)],
            input=json.dumps({"user_id": user_id, "timespan": f"{days}d"}),
            capture_output=True, text=True, timeout=10
        )
        graph = json.loads(result.stdout)
    except Exception as e:
        return [{"type": "error", "suggestion": f"查询失败: {e}", "priority": "low"}]

    suggestions = []

    suggestions = []

    # 1. 从 rewrite events 识别反复出现的困扰
    rewrite_events = []
    for entry in graph.get("entries", []):
        rw = (entry.get("extracted") or {}).get("rewrite_event")
        if rw and rw.get("occurred"):
            rewrite_events.append(rw.get("pattern", rw.get("description", "")))

    from collections import Counter
    concern_counts = Counter(rewrite_events)
    for concern, count in concern_counts.items():
        if count >= 2:
            suggestions.append({
                "type": "concern_pattern",
                "source": concern,
                "frequency": count,
                "suggestion": f"'{concern}' 在 {days} 天内出现了 {count} 次，要不要当做一个待解决的问题？",
                "priority": "high" if count >= 3 else "medium",
            })

    # 2. 从记录中提取低成就感维度 → 建议关注
    low_perma = []
    for entry in graph.get("entries", []):
        perma = (entry.get("extracted") or {}).get("perma") or {}
        for dim, score in perma.items():
            if isinstance(score, (int, float)) and score <= 3:
                low_perma.append({"dim": dim, "date": entry.get("date", ""), "score": score})

    if low_perma:
        dim_counts = Counter(d["dim"] for d in low_perma)
        for dim, count in dim_counts.most_common(3):
            suggestions.append({
                "type": "low_perma_dimension",
                "source": dim,
                "frequency": count,
                "suggestion": f"PERMA 维度 '{dim}' 在 {days} 天内有 {count} 次低分（≤3），想聊聊吗？",
                "priority": "medium",
            })

    # 3. 未完成改写事件 → 建议关注
    no_rewrite_days = []
    for entry in graph.get("entries", []):
        rw = (entry.get("extracted") or {}).get("rewrite_event")
        if not rw or not rw.get("occurred"):
            no_rewrite_days.append(entry.get("date", ""))

    if no_rewrite_days:
        suggestions.append({
            "type": "no_rewrite",
            "source": f"{len(no_rewrite_days)} days without rewrite",
            "suggestion": f"最近 {days} 天有 {len(no_rewrite_days)} 天没有记录改写事件，觉察到就好",
            "priority": "low",
        })

    # 4. 高 flow days → 肯定并建议保持
    for entry in graph.get("entries", []):
        flow = (entry.get("extracted") or {}).get("flow_moments", [])
        if flow:
            suggestions.append({
                "type": "flow_moment",
                "source": entry.get("date", ""),
                "suggestion": f"{entry.get('date', '')} 有 {len(flow)} 个心神合一瞬间，这是你的 E 维度亮点",
                "priority": "low",
            })

    return suggestions

    return suggestions


def get_task_stats(user_id: str, days: int = 30) -> dict:
    """获取任务统计"""
    tasks = load_tasks(user_id)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    recent = [t for t in tasks if t["created"] >= cutoff]
    completed = [t for t in recent if t["status"] == "completed"]
    abandoned = [t for t in recent if t["status"] == "abandoned"]
    cycling = [t for t in recent if t["status"] == "cycling"]
    active = [t for t in recent if t["status"] == "active"]

    # 平均完成时间
    completion_times = []
    for t in completed:
        if t.get("created") and t.get("completed"):
            created = datetime.fromisoformat(t["created"])
            completed_dt = datetime.fromisoformat(t["completed"])
            completion_times.append((completed_dt - created).total_seconds() / 3600)

    return {
        "period_days": days,
        "total": len(recent),
        "completed": len(completed),
        "abandoned": len(abandoned),
        "cycling": len(cycling),
        "active": len(active),
        "completion_rate": round(len(completed) / max(len(recent), 1) * 100, 1),
        "avg_completion_hours": round(sum(completion_times) / max(len(completion_times), 1), 1) if completion_times else None,
        "sources": {
            "from_fragments": sum(1 for t in recent if t.get("source", {}).get("type") != "manual"),
            "manual": sum(1 for t in recent if t.get("source", {}).get("type") == "manual"),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="觉察助手 Task 闭环管理")
    parser.add_argument("--user", required=True, help="用户ID")
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("suggest").add_argument("--days", type=int, default=14)

    create_cmd = sub.add_parser("create")
    create_cmd.add_argument("--data", required=True, help="JSON task 数据")

    update_cmd = sub.add_parser("update")
    update_cmd.add_argument("--task-id", required=True)
    update_cmd.add_argument("--data", required=True, help="JSON 更新字段")

    checkpoint_cmd = sub.add_parser("checkpoint")
    checkpoint_cmd.add_argument("--task-id", required=True)
    checkpoint_cmd.add_argument("--status", default="rechecked")
    checkpoint_cmd.add_argument("--note", default="")

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--status", default=None)
    list_cmd.add_argument("--limit", type=int, default=20)

    sub.add_parser("recheck")

    stats_cmd = sub.add_parser("stats")
    stats_cmd.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    if args.action == "suggest":
        suggestions = suggest_tasks_from_fragments(args.user, args.days)
        print(f"📋 从 knowledge_fragments 中发现 {len(suggestions)} 个可转化 task：")
        for s in suggestions:
            prio_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["priority"], "⚪")
            print(f"  {prio_icon} [{s['type']}] {s['suggestion']}")

    elif args.action == "create":
        data = json.loads(args.data)
        task = create_task(args.user, data)
        if "error" in task:
            print(f"❌ {task['error']}")
        else:
            print(f"✅ 已创建 task: {task['title']} ({task['id']})")

    elif args.action == "update":
        updates = json.loads(args.data)
        task = update_task(args.user, args.task_id, updates)
        if "error" in task:
            print(f"❌ {task['error']}")
        else:
            print(f"✅ 已更新 task: {task['title']} → {task['status']}")

    elif args.action == "checkpoint":
        task = add_checkpoint(args.user, args.task_id, args.status, args.note)
        if "error" in task:
            print(f"❌ {task['error']}")
        else:
            print(f"✅ 已添加检查点: {args.note}")

    elif args.action == "list":
        tasks = list_tasks(args.user, args.status, args.limit)
        for t in tasks:
            status_icon = {"active": "🔄", "completed": "✅", "abandoned": "❌",
                          "pending": "📝", "cycling": "🔁"}.get(t["status"], "❓")
            deadline = f" ⏰ {t['deadline']}" if t.get("deadline") else ""
            source = f" ← {t.get('source',{}).get('field','')}" if t.get("source", {}).get("type") == "knowledge_fragment" else ""
            print(f"  {status_icon} [{t['status']}] {t['title']}{deadline}{source}")

    elif args.action == "recheck":
        data = get_tasks_for_recheck(args.user)
        print(json.dumps(data, indent=2, ensure_ascii=False))

    elif args.action == "stats":
        stats = get_task_stats(args.user, args.days)
        print(f"📊 任务统计 ({stats['period_days']}天)")
        print(f"  总计: {stats['total']} | 完成: {stats['completed']} | 放弃: {stats['abandoned']} | 循环: {stats['cycling']} | 活跃: {stats['active']}")
        print(f"  完成率: {stats['completion_rate']}%")
        if stats['avg_completion_hours']:
            print(f"  平均完成时间: {stats['avg_completion_hours']:.1f} 小时")
        print(f"  来源: {stats['sources']['from_fragments']} 从碎片, {stats['sources']['manual']} 手动")


if __name__ == "__main__":
    main()
