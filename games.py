"""
Game engine: core logic for rehab mini-games.

Games available:
- reaction_time: Reaction time challenge
- memory_match: Cognitive memory match
- balance_challenge: Hold balance positions
- rhythm_match: Music rhythm follow

Each game saves results to the games table for leaderboards.
"""
from __future__ import annotations
import json
import time
import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from db import execute_update, execute_query


GAME_REGISTRY = {
    "reaction_time": {
        "name_zh": "反應時間", "name_en": "Reaction Time",
        "icon": "⚡", "xp_per_play": 15,
        "desc_zh": "測試您的反應速度",
        "desc_en": "Test your reaction speed",
    },
    "memory_match": {
        "name_zh": "記憶配對", "name_en": "Memory Match",
        "icon": "🧠", "xp_per_play": 20,
        "desc_zh": "翻牌找配對訓練記憶",
        "desc_en": "Flip cards to find pairs",
    },
    "balance_challenge": {
        "name_zh": "平衡挑戰", "name_en": "Balance Challenge",
        "icon": "🤸", "xp_per_play": 25,
        "desc_zh": "保持姿勢挑戰",
        "desc_en": "Hold balance positions",
    },
    "rhythm_match": {
        "name_zh": "節奏挑戰", "name_en": "Rhythm Match",
        "icon": "🎵", "xp_per_play": 20,
        "desc_zh": "跟隨節奏完成動作",
        "desc_en": "Follow rhythm prompts",
    },
}


def save_game_score(user_id: str, game_type: str, score: float,
                    game_data: Optional[Dict] = None) -> bool:
    """Save game result to database."""
    try:
        execute_update(
            """
            INSERT INTO games (user_id, game_type, score, game_data_json)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, game_type, score, json.dumps(game_data or {}))
        )
        return True
    except Exception:
        return False


def get_user_game_history(user_id: str, game_type: Optional[str] = None,
                          limit: int = 20) -> List[Dict]:
    """Get user's game history."""
    if game_type:
        rows = execute_query(
            """
            SELECT * FROM games
            WHERE user_id = ? AND game_type = ?
            ORDER BY played_at DESC LIMIT ?
            """,
            (user_id, game_type, limit)
        )
    else:
        rows = execute_query(
            """
            SELECT * FROM games WHERE user_id = ?
            ORDER BY played_at DESC LIMIT ?
            """,
            (user_id, limit)
        )
    return [dict(r) for r in rows]


def get_user_best_score(user_id: str, game_type: str) -> Optional[float]:
    """Get user's best score for a game."""
    rows = execute_query(
        """
        SELECT MAX(score) as best FROM games
        WHERE user_id = ? AND game_type = ?
        """,
        (user_id, game_type)
    )
    if rows and rows[0]["best"] is not None:
        return float(rows[0]["best"])
    return None


def get_user_total_games(user_id: str) -> Dict:
    """Get aggregate game stats for user."""
    rows = execute_query(
        """
        SELECT game_type, COUNT(*) as plays, MAX(score) as best,
               AVG(score) as avg_score
        FROM games WHERE user_id = ?
        GROUP BY game_type
        """,
        (user_id,)
    )

    stats = {}
    for r in rows:
        stats[r["game_type"]] = {
            "plays": r["plays"],
            "best": float(r["best"]) if r["best"] else 0,
            "avg": round(float(r["avg_score"]), 1) if r["avg_score"] else 0,
        }
    return stats


# ============================================================
# Reaction Time game logic
# ============================================================
def reaction_time_start() -> Dict:
    """Initialize reaction time game state."""
    delay = random.uniform(1.5, 4.0)
    return {
        "started_at": time.time(),
        "stimulus_at": time.time() + delay,
        "delay_s": delay,
        "stimulus_shown": False,
        "reaction_ms": None,
    }


def reaction_time_register_click(state: Dict) -> Dict:
    """Register click and compute reaction time."""
    now = time.time()
    if not state.get("stimulus_shown"):
        return {**state, "false_start": True}
    reaction_ms = (now - state["stimulus_at"]) * 1000
    return {**state, "reaction_ms": reaction_ms, "completed": True}


def reaction_time_score(reaction_ms: float) -> float:
    """Convert reaction time to game score (0-100)."""
    if reaction_ms <= 250:
        return 100.0
    if reaction_ms <= 350:
        return 90.0
    if reaction_ms <= 500:
        return 75.0
    if reaction_ms <= 700:
        return 60.0
    if reaction_ms <= 1000:
        return 40.0
    return 20.0


# ============================================================
# Memory Match game logic
# ============================================================
def memory_match_init(grid_size: int = 4) -> Dict:
    """Initialize memory match grid."""
    pairs = (grid_size * grid_size) // 2
    icons = ["🌟", "❤️", "🌸", "🍎", "🎈", "🌈", "⚽", "🎵",
             "🎁", "🦋", "🌻", "🍀", "🚀", "🎨", "🐶", "🐱"]
    chosen = icons[:pairs] * 2
    random.shuffle(chosen)

    return {
        "grid": chosen,
        "size": grid_size,
        "revealed": [False] * len(chosen),
        "matched": [False] * len(chosen),
        "first_pick": None,
        "moves": 0,
        "started_at": time.time(),
    }


def memory_match_pick(state: Dict, idx: int) -> Dict:
    """Process a card pick."""
    if state["matched"][idx] or state["revealed"][idx]:
        return state

    new_state = {**state}
    new_state["revealed"] = list(state["revealed"])
    new_state["matched"] = list(state["matched"])

    if state["first_pick"] is None:
        new_state["first_pick"] = idx
        new_state["revealed"][idx] = True
    else:
        new_state["revealed"][idx] = True
        new_state["moves"] = state["moves"] + 1
        first_idx = state["first_pick"]
        if state["grid"][first_idx] == state["grid"][idx]:
            new_state["matched"][first_idx] = True
            new_state["matched"][idx] = True
        new_state["first_pick"] = None
        new_state["pending_hide"] = (
            None if state["grid"][first_idx] == state["grid"][idx]
            else (first_idx, idx)
        )

    if all(new_state["matched"]):
        new_state["completed"] = True
        new_state["elapsed_s"] = time.time() - state["started_at"]

    return new_state


def memory_match_score(moves: int, elapsed_s: float, pairs: int) -> float:
    """Score based on moves and time (lower = better)."""
    optimal = pairs
    move_eff = max(0, 100 - (moves - optimal) * 5)
    time_bonus = max(0, 50 - elapsed_s)
    score = (move_eff * 0.7) + (time_bonus * 0.6)
    return min(100.0, max(0.0, score))


# ============================================================
# Balance Challenge game logic
# ============================================================
def balance_challenge_score(hold_seconds: float, target_seconds: float = 15.0,
                             stability: float = 1.0) -> float:
    """Score balance hold based on duration and stability."""
    duration_pct = min(1.0, hold_seconds / target_seconds)
    score = duration_pct * 80 + stability * 20
    return min(100.0, max(0.0, score))


# ============================================================
# Rhythm Match game logic
# ============================================================
def rhythm_match_init(num_beats: int = 12) -> Dict:
    """Initialize rhythm sequence."""
    moves = ["⬆️", "⬇️", "⬅️", "➡️"]
    sequence = [random.choice(moves) for _ in range(num_beats)]
    return {
        "sequence": sequence,
        "current_idx": 0,
        "hits": 0,
        "misses": 0,
        "started_at": time.time(),
    }


def rhythm_match_register(state: Dict, move: str) -> Dict:
    """Register player's move."""
    if state["current_idx"] >= len(state["sequence"]):
        return {**state, "completed": True}

    new_state = {**state}
    expected = state["sequence"][state["current_idx"]]
    if move == expected:
        new_state["hits"] = state["hits"] + 1
    else:
        new_state["misses"] = state["misses"] + 1
    new_state["current_idx"] = state["current_idx"] + 1

    if new_state["current_idx"] >= len(state["sequence"]):
        new_state["completed"] = True

    return new_state


def rhythm_match_score(hits: int, total: int) -> float:
    """Score rhythm match based on accuracy."""
    if total == 0:
        return 0.0
    accuracy = hits / total
    return round(accuracy * 100, 1)
