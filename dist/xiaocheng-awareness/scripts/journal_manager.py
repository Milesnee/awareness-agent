#!/usr/bin/env python3
"""
journal_manager.py — 觉察助手每日记录管理

用法:
  python3 journal_manager.py save --user ou_xxx --date 2026-05-11 --period morning --data '{json}'
  python3 journal_manager.py get --user ou_xxx --date 2026-05-11
  python3 journal_manager.py history --user ou_xxx --days 7
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def get_user_dir(user_id: str) -> Path:
    """获取用户私有数据目录"""
    return DATA_DIR / "users" / user_id


def get_journals_dir(user_id: str) -> Path:
    return get_user_dir(user_id) / "journals"


def get_insights_dir(user_id: str) -> Path:
    return get_user_dir(user_id) / "insights" / "weekly"


def get_journal_path(user_id: str, date_str: str) -> Path:
    return get_journals_dir(user_id) / f"{date_str}.json"


def get_journal(user_id: str, date_str: str) -> dict:
    path = get_journal_path(user_id, date_str)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    # 创建新记录
    return {
        "date": date_str,
        "streak": 0,
        "level": "seed",
        "morning": {
            "timestamp": None,
            "sleep_quality": None,
            "today_intention": "",
            "mindfulness_anchor": "",
            "perma_check": {"P": None, "E": None, "R": None, "M": None, "A": None},
            "raw_dialog": [],
            "extracted_insights": [],
        },
        "evening": {
            "timestamp": None,
            "presence_moments": [],
            "distraction_moments": [],
            "emotion_awareness": "",
            "strengths_used": [],
            "gratitude": [],
            "perma_rating": {"P": None, "E": None, "R": None, "M": None, "A": None},
            "lessons": "",
            "raw_dialog": [],
            "extracted_insights": [],
        },
        "feedback": {
            "milestone_unlocked": None,
            "positive_ack": "",
            "streak_days": 0,
            "weekly_progress": "0/7",
        },
        "knowledge_fragments": {
            "decisions": [],
            "projects_mentioned": [],
            "recurring_concerns": [],
            "open_questions": [],
            "principles_stated": [],
            "people_mentioned": [],
            "topics_tracked": [],
        },
    }


def save_journal(user_id: str, date_str: str, journal: dict):
    get_journals_dir(user_id).mkdir(parents=True, exist_ok=True)
    with open(get_journal_path(user_id, date_str), "w") as f:
        json.dump(journal, f, indent=2, ensure_ascii=False)


def update_period(user_id: str, date_str: str, period: str, data: dict) -> dict:
    """更新晨间或晚间记录"""
    journal = get_journal(user_id, date_str)

    # 更新对应时段
    journal[period]["timestamp"] = datetime.now().isoformat()
    for key, value in data.items():
        if key in journal[period]:
            journal[period][key] = value
        else:
            journal[period][key] = value

    save_journal(user_id, date_str, journal)
    return journal


def update_knowledge_fragments(user_id: str, date_str: str, fragments: dict) -> dict:
    """更新 knowledge_fragments，智能合并而非覆盖
    
    fragments 结构:
    {
        "decisions": ["数据层先定，底座随时换"],
        "projects_mentioned": [{"name": "养龙虾PPT", "deadline": "下周六", "status": "准备中"}],
        "recurring_concerns": ["信息过载"],
        "open_questions": ["考试是否冲突"],
        "principles_stated": ["不杜撰"],
        "people_mentioned": ["Marc Lou"],
        "topics_tracked": ["OpenClaw vs Hermes-Agent"]
    }
    """
    journal = get_journal(user_id, date_str)
    existing = journal.get("knowledge_fragments", {})

    # 对列表字段做智能追加（去重）
    list_fields = ["decisions", "recurring_concerns", "open_questions",
                   "principles_stated", "people_mentioned", "topics_tracked"]

    for field in list_fields:
        new_items = fragments.get(field, [])
        if new_items:
            existing.setdefault(field, [])
            for item in new_items:
                if item not in existing[field]:
                    existing[field].append(item)

    # 对 projects_mentioned 做按名称去重
    new_projects = fragments.get("projects_mentioned", [])
    if new_projects:
        existing.setdefault("projects_mentioned", [])
        existing_names = {p.get("name") for p in existing["projects_mentioned"]}
        for proj in new_projects:
            if proj.get("name") not in existing_names:
                existing["projects_mentioned"].append(proj)
            else:
                # 更新已有项目信息（如状态变化）
                for ep in existing["projects_mentioned"]:
                    if ep.get("name") == proj.get("name"):
                        ep.update(proj)

    journal["knowledge_fragments"] = existing
    save_journal(user_id, date_str, journal)
    return journal


def get_user_knowledge_graph(user_id: str, days: int = 30) -> dict:
    """聚合一段时间内的 knowledge_fragments，形成用户知识图谱"""
    journals = get_history(user_id, days)

    graph = {
        "decisions": [],
        "projects_mentioned": {},
        "recurring_concerns": {},
        "open_questions": [],
        "principles_stated": [],
        "people_mentioned": {},
        "topics_tracked": {},
        "date_range": {
            "start": journals[-1]["date"] if journals else None,
            "end": journals[0]["date"] if journals else None,
        },
        "journal_count": len(journals),
    }

    for j in journals:
        kf = j.get("knowledge_fragments", {})
        for field in ["decisions", "open_questions", "principles_stated"]:
            for item in kf.get(field, []):
                if item not in graph[field]:
                    graph[field].append(item)

        for proj in kf.get("projects_mentioned", []):
            name = proj.get("name", "unknown")
            if name not in graph["projects_mentioned"]:
                graph["projects_mentioned"][name] = proj

        for field in ["recurring_concerns", "people_mentioned", "topics_tracked"]:
            for item in kf.get(field, []):
                graph[field][item] = graph[field].get(item, 0) + 1

    return graph


def add_dialog(user_id: str, date_str: str, period: str, role: str, content: str):
    """添加对话记录"""
    journal = get_journal(user_id, date_str)
    journal[period]["raw_dialog"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })
    save_journal(user_id, date_str, journal)


def add_insight(user_id: str, date_str: str, period: str, insight: str):
    """添加提取的洞察"""
    journal = get_journal(user_id, date_str)
    journal[period]["extracted_insights"].append(insight)
    save_journal(user_id, date_str, journal)


def get_history(user_id: str, days: int = 7) -> list:
    """获取最近N天的觉察记录"""
    journals = []
    today = datetime.now().date()

    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        path = get_journal_path(user_id, date_str)
        if path.exists():
            with open(path) as f:
                journals.append(json.load(f))

    return journals


def get_perma_trend(user_id: str, days: int = 7) -> dict:
    """获取PERMA趋势数据"""
    journals = get_history(user_id, days)
    trend = {"P": [], "E": [], "R": [], "M": [], "A": [], "dates": []}

    for j in reversed(journals):
        date = j["date"]
        trend["dates"].append(date)
        for dim in ["P", "E", "R", "M", "A"]:
            # 优先取晚间评分，其次晨间
            score = j.get("evening", {}).get("perma_rating", {}).get(dim)
            if score is None:
                score = j.get("morning", {}).get("perma_check", {}).get(dim)
            trend[dim].append(score)

    return trend


def get_strengths_summary(user_id: str, days: int = 7) -> dict:
    """获取品格优势使用统计"""
    journals = get_history(user_id, days)
    counts = {}

    for j in journals:
        for period in ["morning", "evening"]:
            strengths = j.get(period, {}).get("strengths_used", [])
            for s in strengths:
                counts[s] = counts.get(s, 0) + 1

    return sorted(counts.items(), key=lambda x: -x[1])


def save_weekly_insight(user_id: str, week: str, insight_data: dict) -> dict:
    """保存周洞察笔记"""
    insights_dir = get_insights_dir(user_id)
    insights_dir.mkdir(parents=True, exist_ok=True)
    path = insights_dir / f"{week}.json"

    insight_data.setdefault("week", week)
    insight_data.setdefault("created", datetime.now().isoformat())
    insight_data.setdefault("user_id", user_id)

    with open(path, "w") as f:
        json.dump(insight_data, f, indent=2, ensure_ascii=False)

    return insight_data


def get_weekly_insight(user_id: str, week: str) -> dict:
    """读取周洞察笔记"""
    path = get_insights_dir(user_id) / f"{week}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def list_weekly_insights(user_id: str, limit: int = 12) -> list:
    """列出最近的周洞察"""
    insights_dir = get_insights_dir(user_id)
    if not insights_dir.exists():
        return []
    files = sorted(insights_dir.glob("*.json"), reverse=True)[:limit]
    results = []
    for f in files:
        with open(f) as fp:
            results.append(json.load(fp))
    return results


def aggregate_weekly_data(user_id: str, week_start: str, week_end: str) -> dict:
    """聚合一周的日记和PERMA数据，为周洞察提供输入"""
    start = datetime.strptime(week_start, "%Y-%m-%d").date()
    end = datetime.strptime(week_end, "%Y-%m-%d").date()

    journals = []
    perma_scores = {"P": [], "E": [], "R": [], "M": [], "A": []}
    strengths_all = []
    insights_all = []
    presence_moments = []
    distractions = []

    d = start
    while d <= end:
        date_str = d.strftime("%Y-%m-%d")
        path = get_journal_path(user_id, date_str)
        if path.exists():
            with open(path) as f:
                j = json.load(f)
            journals.append(j)

            for period in ["morning", "evening"]:
                pd = j.get(period, {})
                if pd.get("timestamp"):
                    insights_all.extend(pd.get("extracted_insights", []))
                    strengths_all.extend(pd.get("strengths_used", []))
                    presence_moments.extend(pd.get("presence_moments", []))
                    distractions.extend(pd.get("distraction_moments", []))

                    rating = pd.get("perma_rating") or pd.get("perma_check")
                    if rating:
                        for dim in ["P", "E", "R", "M", "A"]:
                            if rating.get(dim) is not None:
                                perma_scores[dim].append(rating[dim])
        d += timedelta(days=1)

    # 计算PERMA均值
    perma_avg = {}
    for dim, scores in perma_scores.items():
        perma_avg[dim] = round(sum(scores) / len(scores), 1) if scores else None

    # 品格优势统计
    from collections import Counter
    strengths_counter = Counter(strengths_all)

    # 聚合 knowledge_fragments
    all_decisions = []
    all_concerns = Counter()
    all_topics = Counter()
    all_questions = []
    all_principles = []
    all_projects = {}

    for j in journals:
        kf = j.get("knowledge_fragments", {})
        for d in kf.get("decisions", []):
            if d not in all_decisions:
                all_decisions.append(d)
        for c in kf.get("recurring_concerns", []):
            all_concerns[c] += 1
        for t in kf.get("topics_tracked", []):
            all_topics[t] += 1
        for q in kf.get("open_questions", []):
            if q not in all_questions:
                all_questions.append(q)
        for p in kf.get("principles_stated", []):
            if p not in all_principles:
                all_principles.append(p)
        for proj in kf.get("projects_mentioned", []):
            name = proj.get("name", "unknown")
            if name not in all_projects:
                all_projects[name] = proj

    return {
        "date_range": {"start": week_start, "end": week_end},
        "journal_count": len(journals),
        "perma_avg": perma_avg,
        "perma_raw": {k: v for k, v in perma_scores.items() if v},
        "top_strengths": strengths_counter.most_common(5),
        "insights_all": insights_all,
        "presence_moments": presence_moments,
        "distractions": distractions,
        "knowledge_graph": {
            "decisions": all_decisions,
            "recurring_concerns": dict(all_concerns.most_common(10)),
            "topics_tracked": dict(all_topics.most_common(10)),
            "open_questions": all_questions,
            "principles_stated": all_principles,
            "projects_mentioned": all_projects,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="觉察助手 Journal 管理")
    parser.add_argument("--user", required=True)
    sub = parser.add_subparsers(dest="action")

    save_cmd = sub.add_parser("save")
    save_cmd.add_argument("--date", required=True)
    save_cmd.add_argument("--period", required=True, choices=["morning", "evening"])
    save_cmd.add_argument("--data", required=True, help="JSON string")

    get_cmd = sub.add_parser("get")
    get_cmd.add_argument("--date", required=True)

    history_cmd = sub.add_parser("history")
    history_cmd.add_argument("--days", type=int, default=7)

    insight_cmd = sub.add_parser("insight")
    insight_cmd.add_argument("--action", required=True, choices=["save", "get", "list", "aggregate"], dest="insight_action")
    insight_cmd.add_argument("--week", default="")
    insight_cmd.add_argument("--data", default="{}", help="JSON string for save")
    insight_cmd.add_argument("--week-start", default="")
    insight_cmd.add_argument("--week-end", default="")
    insight_cmd.add_argument("--limit", type=int, default=12)

    # knowledge fragments
    kf_cmd = sub.add_parser("knowledge")
    kf_cmd.add_argument("--action", required=True, choices=["save", "get", "graph"], dest="kf_action")
    kf_cmd.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    kf_cmd.add_argument("--data", default="{}", help="JSON string for save")
    kf_cmd.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    if args.action == "save":
        data = json.loads(args.data)
        journal = update_period(args.user, args.date, args.period, data)
        print(json.dumps(journal, indent=2, ensure_ascii=False))
    elif args.action == "get":
        journal = get_journal(args.user, args.date)
        print(json.dumps(journal, indent=2, ensure_ascii=False))
    elif args.action == "history":
        journals = get_history(args.user, args.days)
        for j in journals:
            print(f"📅 {j['date']}")
            if j.get("morning", {}).get("extracted_insights"):
                print(f"  晨间: {', '.join(j['morning']['extracted_insights'][:3])}")
            if j.get("evening", {}).get("extracted_insights"):
                print(f"  晚间: {', '.join(j['evening']['extracted_insights'][:3])}")
    elif args.action == "insight":
        if args.insight_action == "save":
            data = json.loads(args.data)
            result = save_weekly_insight(args.user, args.week, data)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.insight_action == "get":
            result = get_weekly_insight(args.user, args.week)
            if result:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"周洞察 {args.week} 不存在")
        elif args.insight_action == "list":
            results = list_weekly_insights(args.user, args.limit)
            for r in results:
                print(f"📊 {r.get('week')}: {r.get('title', '未命名')}")
        elif args.insight_action == "aggregate":
            data = aggregate_weekly_data(args.user, args.week_start, args.week_end)
            print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.action == "knowledge":
        if args.kf_action == "save":
            fragments = json.loads(args.data)
            journal = update_knowledge_fragments(args.user, args.date, fragments)
            kf = journal.get("knowledge_fragments", {})
            total = sum(len(v) for v in kf.values() if isinstance(v, list))
            print(f"✅ 已更新 knowledge_fragments: {total} 条碎片")
        elif args.kf_action == "get":
            journal = get_journal(args.user, args.date)
            kf = journal.get("knowledge_fragments", {})
            print(json.dumps(kf, indent=2, ensure_ascii=False))
        elif args.kf_action == "graph":
            graph = get_user_knowledge_graph(args.user, args.days)
            print(json.dumps(graph, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
