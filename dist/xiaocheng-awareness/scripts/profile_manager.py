#!/usr/bin/env python3
"""
profile_manager.py — 觉察助手用户Profile管理

用法:
  python3 profile_manager.py init --user ou_xxx --nickname 老麦
  python3 profile_manager.py get --user ou_xxx
  python3 profile_manager.py streak --user ou_xxx
  python3 profile_manager.py milestone --user ou_xxx
"""

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

def get_user_dir(user_id: str) -> Path:
    """获取用户私有数据目录"""
    return DATA_DIR / "users" / user_id

def get_journals_dir(user_id: str) -> Path:
    return get_user_dir(user_id) / "journals"

# 里程碑定义
MILESTONES = [
    {"level": "seed", "emoji": "🌱", "name": "种子", "condition": "首次觉察", "min_streak": 0},
    {"level": "sprout", "emoji": "🌿", "name": "发芽", "condition": "完成1天双觉察", "min_streak": 0, "min_full_days": 1},
    {"level": "growing", "emoji": "🌳", "name": "成长", "condition": "连续3天觉察", "min_streak": 3},
    {"level": "thriving", "emoji": "🎋", "name": "茂盛", "condition": "连续7天+周报", "min_streak": 7},
    {"level": "blooming", "emoji": "🌸", "name": "绽放", "condition": "识别出签名优势", "min_streak": 0, "require_signature": True},
]

MILESTONE_MESSAGES = {
    "seed": "你今天愿意停下来觉察，这本身就很了不起。",
    "sprout": "一天的完整觉察，就像种子破土而出。🌱→🌿",
    "growing": "你的觉察肌肉正在生长，连续3天了。",
    "thriving": "觉察正在成为你的习惯，这是了不起的改变。",
    "blooming": "你不是学会了觉察，你发现觉察一直都在。",
}


def get_profile_path(user_id: str) -> Path:
    return get_user_dir(user_id) / "profile.json"


def init_profile(user_id: str, nickname: str = "", life_context: str = "") -> dict:
    get_user_dir(user_id).mkdir(parents=True, exist_ok=True)
    profile = {
        "user_id": user_id,
        "created": datetime.now().isoformat(),
        "persona": {
            "nickname": nickname or "朋友",
            "life_context": life_context,
            "communication_style": "简洁直接，口语化",
        },
        "perma_baseline": {k: {"score": None} for k in [
            "P_positive_emotion", "E_engagement", "R_relationships",
            "M_meaning", "A_accomplishment"
        ]},
        "character_strengths": {
            "signature": [],
            "top_5": [],
            "usage_count": {},
        },
        "progress": {
            "total_sessions": 0,
            "total_mornings": 0,
            "total_evenings": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "milestones_unlocked": [],
            "last_active_date": None,
        },
        "preferences": {
            "morning_remind_time": "08:00",
            "evening_remind_time": "21:30",
        },
    }
    path = get_profile_path(user_id)
    with open(path, "w") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    return profile


def get_profile(user_id: str) -> dict:
    path = get_profile_path(user_id)
    if not path.exists():
        return init_profile(user_id)
    with open(path) as f:
        return json.load(f)


def save_profile(user_id: str, profile: dict):
    get_user_dir(user_id).mkdir(parents=True, exist_ok=True)
    with open(get_profile_path(user_id), "w") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def calculate_streak(user_id: str) -> int:
    """计算连续觉察天数"""
    journals_dir = get_journals_dir(user_id)
    if not journals_dir.exists():
        return 0

    streak = 0
    today = datetime.now().date()

    for i in range(365):
        date = today - timedelta(days=i)
        journal_path = journals_dir / f"{date.strftime('%Y-%m-%d')}.json"
        if journal_path.exists():
            with open(journal_path) as f:
                journal = json.load(f)
            has_content = (
                journal.get("morning", {}).get("extracted_insights")
                or journal.get("evening", {}).get("extracted_insights")
            )
            if has_content:
                streak += 1
            else:
                break
        else:
            break

    return streak


def get_current_milestone(streak: int, profile: dict) -> dict:
    """获取当前里程碑等级"""
    current = MILESTONES[0]
    for m in MILESTONES:
        if m.get("require_signature"):
            if not profile.get("character_strengths", {}).get("signature"):
                continue
        if streak >= m.get("min_streak", 0):
            current = m
        else:
            break
    return current


def check_new_milestone(streak: int, profile: dict) -> dict | None:
    """检查是否有新里程碑解锁"""
    current = get_current_milestone(streak, profile)
    unlocked = profile.get("progress", {}).get("milestones_unlocked", [])
    if current["level"] not in unlocked:
        return current
    return None


def update_after_session(user_id: str, period: str, extracted_data: dict = None):
    """一次觉察对话结束后更新profile"""
    profile = get_profile(user_id)
    progress = profile.setdefault("progress", {})

    progress["total_sessions"] = progress.get("total_sessions", 0) + 1
    progress["total_mornings"] = progress.get("total_mornings", 0) + (1 if period == "morning" else 0)
    progress["total_evenings"] = progress.get("total_evenings", 0) + (1 if period == "evening" else 0)
    progress["last_active_date"] = datetime.now().strftime("%Y-%m-%d")

    # 更新连续天数
    streak = calculate_streak(user_id)
    progress["current_streak"] = streak
    progress["longest_streak"] = max(progress.get("longest_streak", 0), streak)

    # 检查里程碑
    new_milestone = check_new_milestone(streak, profile)
    if new_milestone:
        if "milestones_unlocked" not in progress:
            progress["milestones_unlocked"] = []
        progress["milestones_unlocked"].append(new_milestone["level"])

    # 更新品格优势使用计数
    if extracted_data and "strengths_used" in extracted_data:
        usage = profile.setdefault("character_strengths", {}).setdefault("usage_count", {})
        for s in extracted_data["strengths_used"]:
            usage[s] = usage.get(s, 0) + 1

    # 更新PERMA评分
    if extracted_data and "perma_rating" in extracted_data:
        for k, v in extracted_data["perma_rating"].items():
            if v is not None:
                key = f"{k}_{'positive_emotion' if k == 'P' else 'engagement' if k == 'E' else 'relationships' if k == 'R' else 'meaning' if k == 'M' else 'accomplishment'}"
                # 简化：直接用 P/E/R/M/A 存最近评分
                perma = profile.setdefault("perma_baseline", {})
                perma.setdefault(k, {})["score"] = v
                perma[k]["last_updated"] = datetime.now().isoformat()

    save_profile(user_id, profile)

    return {
        "streak": streak,
        "new_milestone": new_milestone,
        "milestone_message": MILESTONE_MESSAGES.get(new_milestone["level"]) if new_milestone else None,
        "current_level": get_current_milestone(streak, profile),
    }


def get_weekly_progress(user_id: str) -> dict:
    """本周觉察进度"""
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    done = 0
    total = 7
    journals_dir = get_journals_dir(user_id)

    for i in range(7):
        date = week_start + timedelta(days=i)
        if date.date() > today.date():
            total = i
            break
        journal_path = journals_dir / f"{date.strftime('%Y-%m-%d')}.json"
        if journal_path.exists():
            with open(journal_path) as f:
                journal = json.load(f)
            if journal.get("morning", {}).get("extracted_insights") or journal.get("evening", {}).get("extracted_insights"):
                done += 1

    return {"done": done, "total": total, "progress": f"{done}/{total}"}


def main():
    parser = argparse.ArgumentParser(description="觉察助手 Profile 管理")
    parser.add_argument("--user", required=True, help="用户ID")
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("init").add_argument("--nickname", default="")
    sub.add_parser("get")
    sub.add_parser("streak")
    sub.add_parser("milestone")

    args = parser.parse_args()

    if args.action == "init":
        profile = init_profile(args.user, args.nickname)
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    elif args.action == "get":
        profile = get_profile(args.user)
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    elif args.action == "streak":
        streak = calculate_streak(args.user)
        print(f"连续觉察天数: {streak}")
    elif args.action == "milestone":
        profile = get_profile(args.user)
        streak = calculate_streak(args.user)
        milestone = get_current_milestone(streak, profile)
        print(f"当前等级: {milestone['emoji']} {milestone['name']}")
        print(f"连续天数: {streak}")
        new = check_new_milestone(streak, profile)
        if new:
            print(f"🎉 新里程碑解锁: {new['emoji']} {new['name']}")


if __name__ == "__main__":
    main()
