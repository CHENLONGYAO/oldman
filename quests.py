"""
Quest/mission system: time-bound challenges with rewards.

Quest types:
- daily: Reset every day
- weekly: Reset every Monday
- one_time: Lifetime achievement quests

Each quest has a goal (e.g., "complete 3 sessions", "score >= 85")
and grants XP + optional badge on completion.
"""
from __future__ import annotations
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from db import execute_query, execute_update


QUEST_DEFINITIONS = {
    # Daily quests
    "daily_session": {
        "type": "daily",
        "name_zh": "每日訓練", "name_en": "Daily Training",
        "desc_zh": "完成 1 次訓練", "desc_en": "Complete 1 session",
        "goal": 1, "xp": 50, "icon": "🌅",
        "metric": "sessions_today",
    },
    "daily_streak_logger": {
        "type": "daily",
        "name_zh": "今日記錄", "name_en": "Log Today",
        "desc_zh": "記錄心情或疼痛", "desc_en": "Log mood or pain",
        "goal": 1, "xp": 20, "icon": "📝",
        "metric": "logs_today",
    },
    "daily_high_score": {
        "type": "daily",
        "name_zh": "高分挑戰", "name_en": "High Score",
        "desc_zh": "今天獲得 ≥85 分", "desc_en": "Score 85+ today",
        "goal": 1, "xp": 80, "icon": "🌟",
        "metric": "high_score_today",
    },
    # Weekly quests
    "weekly_sessions": {
        "type": "weekly",
        "name_zh": "週訓練", "name_en": "Weekly Sessions",
        "desc_zh": "本週完成 5 次訓練", "desc_en": "5 sessions this week",
        "goal": 5, "xp": 200, "icon": "📅",
        "metric": "sessions_week",
    },
    "weekly_variety": {
        "type": "weekly",
        "name_zh": "多樣化", "name_en": "Variety",
        "desc_zh": "本週做 3 種不同動作", "desc_en": "3 different exercises",
        "goal": 3, "xp": 150, "icon": "🎨",
        "metric": "unique_exercises_week",
    },
    "weekly_game_master": {
        "type": "weekly",
        "name_zh": "遊戲大師", "name_en": "Game Master",
        "desc_zh": "玩 3 次互動遊戲", "desc_en": "Play 3 games",
        "goal": 3, "xp": 100, "icon": "🎮",
        "metric": "games_week",
    },
    # One-time achievement quests
    "first_pb": {
        "type": "one_time",
        "name_zh": "個人最佳", "name_en": "Personal Best",
        "desc_zh": "刷新個人最高分", "desc_en": "Set a new personal best",
        "goal": 1, "xp": 500, "icon": "🏆",
        "metric": "personal_best",
        "badge": "first_pb",
    },
    "ten_sessions_total": {
        "type": "one_time",
        "name_zh": "十次堅持", "name_en": "Ten Sessions",
        "desc_zh": "完成 10 次訓練", "desc_en": "Complete 10 sessions",
        "goal": 10, "xp": 300, "icon": "🥉",
        "metric": "total_sessions",
        "badge": "ten_sessions",
    },
    "fifty_sessions_total": {
        "type": "one_time",
        "name_zh": "五十堅持", "name_en": "Fifty Sessions",
        "desc_zh": "完成 50 次訓練", "desc_en": "Complete 50 sessions",
        "goal": 50, "xp": 1500, "icon": "🥈",
        "metric": "total_sessions",
        "badge": "fifty_sessions",
    },
    "century_club": {
        "type": "one_time",
        "name_zh": "百次俱樂部", "name_en": "Century Club",
        "desc_zh": "完成 100 次訓練", "desc_en": "Complete 100 sessions",
        "goal": 100, "xp": 5000, "icon": "🥇",
        "metric": "total_sessions",
        "badge": "century",
    },
}


def get_metric_value(user_id: str, metric: str) -> int:
    """Compute current value for a quest metric."""
    today = date.today().isoformat()
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()

    if metric == "sessions_today":
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM sessions
            WHERE user_id = ? AND DATE(created_at) = ?
            """,
            (user_id, today),
        )
        return rows[0]["c"] if rows else 0

    if metric == "logs_today":
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM health_data
            WHERE user_id = ?
              AND DATE(created_at) = ?
              AND data_type IN ('journal', 'pain_map', 'pain_records')
            """,
            (user_id, today),
        )
        return rows[0]["c"] if rows else 0

    if metric == "high_score_today":
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM sessions
            WHERE user_id = ? AND DATE(created_at) = ? AND score >= 85
            """,
            (user_id, today),
        )
        return rows[0]["c"] if rows else 0

    if metric == "sessions_week":
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM sessions
            WHERE user_id = ? AND DATE(created_at) >= ?
            """,
            (user_id, week_start),
        )
        return rows[0]["c"] if rows else 0

    if metric == "unique_exercises_week":
        rows = execute_query(
            """
            SELECT COUNT(DISTINCT exercise) as c FROM sessions
            WHERE user_id = ? AND DATE(created_at) >= ?
            """,
            (user_id, week_start),
        )
        return rows[0]["c"] if rows else 0

    if metric == "games_week":
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM games
            WHERE user_id = ? AND DATE(played_at) >= ?
            """,
            (user_id, week_start),
        )
        return rows[0]["c"] if rows else 0

    if metric == "personal_best":
        rows = execute_query(
            """
            SELECT MAX(score) as best, MAX(created_at) as last_ts FROM sessions
            WHERE user_id = ?
            """,
            (user_id,),
        )
        if not rows or rows[0]["best"] is None:
            return 0
        recent_pb = execute_query(
            """
            SELECT 1 FROM sessions
            WHERE user_id = ? AND score = ? ORDER BY created_at DESC LIMIT 1
            """,
            (user_id, rows[0]["best"]),
        )
        return 1 if recent_pb else 0

    if metric == "total_sessions":
        rows = execute_query(
            "SELECT COUNT(*) as c FROM sessions WHERE user_id = ?",
            (user_id,),
        )
        return rows[0]["c"] if rows else 0

    return 0


def get_active_quests(user_id: str, lang: str = "zh") -> List[Dict]:
    """Get all active quests with current progress."""
    completed_keys = _get_completed_quest_keys(user_id)
    quests = []

    for key, qdef in QUEST_DEFINITIONS.items():
        period_key = _quest_period_key(key, qdef["type"])

        is_completed = period_key in completed_keys
        current = get_metric_value(user_id, qdef["metric"])

        quests.append({
            "key": key,
            "type": qdef["type"],
            "name": qdef["name_zh"] if lang == "zh" else qdef["name_en"],
            "desc": qdef["desc_zh"] if lang == "zh" else qdef["desc_en"],
            "icon": qdef["icon"],
            "current": min(current, qdef["goal"]),
            "goal": qdef["goal"],
            "xp": qdef["xp"],
            "progress_pct": min(100, (current / qdef["goal"]) * 100) if qdef["goal"] else 0,
            "completed": is_completed,
            "ready_to_claim": current >= qdef["goal"] and not is_completed,
            "badge": qdef.get("badge"),
        })

    return sorted(quests,
                  key=lambda q: (q["completed"], -q["ready_to_claim"], q["type"]))


def claim_quest(user_id: str, quest_key: str) -> Dict:
    """Claim a completed quest. Returns reward info."""
    if quest_key not in QUEST_DEFINITIONS:
        return {"success": False, "error": "unknown_quest"}

    qdef = QUEST_DEFINITIONS[quest_key]
    current = get_metric_value(user_id, qdef["metric"])
    if current < qdef["goal"]:
        return {"success": False, "error": "not_complete"}

    period_key = _quest_period_key(quest_key, qdef["type"])
    completed = _get_completed_quest_keys(user_id)
    if period_key in completed:
        return {"success": False, "error": "already_claimed"}

    _record_completion(user_id, quest_key, period_key, qdef["xp"])

    if qdef.get("badge"):
        try:
            execute_update(
                """
                INSERT OR IGNORE INTO badges (user_id, badge_type)
                VALUES (?, ?)
                """,
                (user_id, qdef["badge"]),
            )
        except Exception:
            pass

    return {
        "success": True,
        "xp_gained": qdef["xp"],
        "badge": qdef.get("badge"),
        "name": qdef["name_zh"],
    }


def _quest_period_key(quest_key: str, quest_type: str) -> str:
    """Generate period-scoped key for quest completion tracking."""
    if quest_type == "daily":
        return f"{quest_key}::{date.today().isoformat()}"
    if quest_type == "weekly":
        week_start = date.today() - timedelta(days=date.today().weekday())
        return f"{quest_key}::{week_start.isoformat()}"
    return quest_key


def _get_completed_quest_keys(user_id: str) -> set:
    """Get set of completed quest period keys."""
    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = 'quest_completion'
        """,
        (user_id,),
    )
    keys = set()
    for r in rows:
        try:
            data = json.loads(r["data_json"])
            keys.add(data.get("period_key"))
        except Exception:
            continue
    return keys


def _record_completion(user_id: str, quest_key: str, period_key: str,
                        xp: int) -> None:
    """Record a quest completion."""
    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, ?, ?, datetime('now', '+90 days'))
            """,
            (
                user_id,
                "quest_completion",
                json.dumps({
                    "quest_key": quest_key,
                    "period_key": period_key,
                    "xp": xp,
                    "completed_at": datetime.now().isoformat(),
                }),
            ),
        )
    except Exception:
        pass


def get_quest_xp_total(user_id: str) -> int:
    """Sum all XP earned from quests."""
    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = 'quest_completion'
        """,
        (user_id,),
    )

    total = 0
    for r in rows:
        try:
            total += json.loads(r["data_json"]).get("xp", 0)
        except Exception:
            continue
    return total
