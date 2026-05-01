"""
Leaderboard system: global and per-game rankings.
"""
from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from db import execute_query


def get_global_leaderboard(limit: int = 20, days: int = 7) -> List[Dict]:
    """Get top users by total game XP in last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    rows = execute_query(
        """
        SELECT g.user_id, u.username, p.name,
               COUNT(g.id) as plays,
               SUM(g.score) as total_score,
               AVG(g.score) as avg_score,
               MAX(g.score) as best_score
        FROM games g
        JOIN users u ON g.user_id = u.user_id
        LEFT JOIN user_profiles p ON g.user_id = p.user_id
        WHERE g.played_at >= ?
        GROUP BY g.user_id
        ORDER BY total_score DESC
        LIMIT ?
        """,
        (cutoff, limit)
    )

    leaderboard = []
    for rank, r in enumerate(rows, 1):
        leaderboard.append({
            "rank": rank,
            "user_id": r["user_id"],
            "name": r["name"] or r["username"],
            "plays": r["plays"],
            "total_score": round(float(r["total_score"] or 0), 1),
            "avg_score": round(float(r["avg_score"] or 0), 1),
            "best_score": round(float(r["best_score"] or 0), 1),
        })
    return leaderboard


def get_game_leaderboard(game_type: str, limit: int = 10) -> List[Dict]:
    """Get top scores for a specific game (all-time)."""
    rows = execute_query(
        """
        SELECT g.user_id, u.username, p.name,
               MAX(g.score) as best_score,
               COUNT(g.id) as plays
        FROM games g
        JOIN users u ON g.user_id = u.user_id
        LEFT JOIN user_profiles p ON g.user_id = p.user_id
        WHERE g.game_type = ?
        GROUP BY g.user_id
        ORDER BY best_score DESC
        LIMIT ?
        """,
        (game_type, limit)
    )

    leaderboard = []
    for rank, r in enumerate(rows, 1):
        leaderboard.append({
            "rank": rank,
            "user_id": r["user_id"],
            "name": r["name"] or r["username"],
            "best_score": round(float(r["best_score"] or 0), 1),
            "plays": r["plays"],
        })
    return leaderboard


def get_user_rank(user_id: str, days: int = 7) -> Optional[Dict]:
    """Get current user's rank in global leaderboard."""
    leaderboard = get_global_leaderboard(limit=1000, days=days)
    for entry in leaderboard:
        if entry["user_id"] == user_id:
            return {
                "rank": entry["rank"],
                "total": len(leaderboard),
                "score": entry["total_score"],
            }
    return None


def get_weekly_challenge_status(user_id: str) -> Dict:
    """Get user's progress in current weekly challenge."""
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()

    rows = execute_query(
        """
        SELECT COUNT(*) as plays, SUM(score) as total
        FROM games WHERE user_id = ? AND played_at >= ?
        """,
        (user_id, cutoff)
    )

    if not rows:
        return {"plays": 0, "total_score": 0, "target": 500, "completed": False}

    plays = rows[0]["plays"] or 0
    total = float(rows[0]["total"] or 0)
    target = 500
    return {
        "plays": plays,
        "total_score": round(total, 1),
        "target": target,
        "progress_pct": min(100, (total / target) * 100) if target else 0,
        "completed": total >= target,
    }
