"""
復健計畫系統：內建課程 + 多週進度追蹤。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import history as hist


BUILTIN_PROGRAMS = {
    "knee_replacement": {
        "name": "膝關節置換術後復健",
        "name_en": "Knee Replacement Recovery",
        "icon": "🦵",
        "weeks": 6,
        "description": "術後逐步恢復膝關節活動能力，增加肌力與柔軟度。",
        "description_en": "Gradual knee recovery post-surgery.",
        "target_group": "膝關節置換手術患者",
        "schedule": [
            {
                "week": 1,
                "sessions_per_week": 3,
                "intensity": "easy",
                "exercises": ["knee_extension", "hip_abduction"],
                "focus": "活動度恢復，緩解腫脹",
            },
            {
                "week": 2,
                "sessions_per_week": 3,
                "intensity": "easy",
                "exercises": ["knee_extension", "mini_squat"],
                "focus": "膝關節曲伸範圍",
            },
            {
                "week": 3,
                "sessions_per_week": 4,
                "intensity": "easy",
                "exercises": ["mini_squat", "sit_to_stand"],
                "focus": "站立起身動作",
            },
            {
                "week": 4,
                "sessions_per_week": 4,
                "intensity": "normal",
                "exercises": ["sit_to_stand", "march_in_place"],
                "focus": "行走能力",
            },
            {
                "week": 5,
                "sessions_per_week": 4,
                "intensity": "normal",
                "exercises": ["march_in_place", "sit_to_stand"],
                "focus": "樓梯訓練",
            },
            {
                "week": 6,
                "sessions_per_week": 3,
                "intensity": "normal",
                "exercises": ["sit_to_stand", "hip_abduction"],
                "focus": "平衡與日常活動",
            },
        ],
    },
    "shoulder_recovery": {
        "name": "肩關節修復計畫",
        "name_en": "Shoulder Recovery",
        "icon": "💪",
        "weeks": 8,
        "description": "針對肩膀疼痛、旋轉肌損傷的漸進式復健。",
        "description_en": "Progressive shoulder and rotator cuff recovery.",
        "target_group": "肩膀損傷、旋轉肌症候群患者",
        "schedule": [
            {
                "week": 1,
                "sessions_per_week": 3,
                "intensity": "easy",
                "exercises": ["shoulder_abduction"],
                "focus": "外展活動度",
            },
            {
                "week": 2,
                "sessions_per_week": 3,
                "intensity": "easy",
                "exercises": ["shoulder_abduction", "arm_raise"],
                "focus": "肩膀抬舉",
            },
            {
                "week": 3,
                "sessions_per_week": 4,
                "intensity": "easy",
                "exercises": ["arm_raise", "elbow_flexion"],
                "focus": "前舉與肘屈",
            },
            {
                "week": 4,
                "sessions_per_week": 4,
                "intensity": "normal",
                "exercises": ["elbow_flexion", "shoulder_abduction"],
                "focus": "內旋肌力",
            },
            {
                "week": 5,
                "sessions_per_week": 4,
                "intensity": "normal",
                "exercises": ["shoulder_abduction", "arm_raise"],
                "focus": "旋轉肌訓練",
            },
            {
                "week": 6,
                "sessions_per_week": 4,
                "intensity": "normal",
                "exercises": ["arm_raise", "wall_pushup"],
                "focus": "推動肌力",
            },
            {
                "week": 7,
                "sessions_per_week": 3,
                "intensity": "hard",
                "exercises": ["wall_pushup"],
                "focus": "推動爆發力",
            },
            {
                "week": 8,
                "sessions_per_week": 3,
                "intensity": "hard",
                "exercises": ["wall_pushup"],
                "focus": "日常活動獨立性",
            },
        ],
    },
    "general_elderly": {
        "name": "長者日常活動復健",
        "name_en": "Elderly Daily Living",
        "icon": "🧓",
        "weeks": 4,
        "description": "維持或改善日常生活動作能力，預防跌倒。",
        "description_en": "Maintain mobility and prevent falls.",
        "target_group": "老年患者、跌倒高風險族群",
        "schedule": [
            {
                "week": 1,
                "sessions_per_week": 3,
                "intensity": "easy",
                "exercises": ["march_in_place"],
                "focus": "行走協調",
            },
            {
                "week": 2,
                "sessions_per_week": 3,
                "intensity": "easy",
                "exercises": ["march_in_place", "sit_to_stand"],
                "focus": "起身能力",
            },
            {
                "week": 3,
                "sessions_per_week": 4,
                "intensity": "normal",
                "exercises": ["sit_to_stand", "hip_abduction"],
                "focus": "平衡訓練",
            },
            {
                "week": 4,
                "sessions_per_week": 4,
                "intensity": "normal",
                "exercises": ["seated_march", "march_in_place"],
                "focus": "日常活動獨立",
            },
        ],
    },
}


def start_program(name: str, program_key: str) -> Dict[str, Any]:
    """開始新計畫。"""
    if program_key not in BUILTIN_PROGRAMS:
        raise ValueError(f"Unknown program: {program_key}")
    program = BUILTIN_PROGRAMS[program_key]
    active = {
        "key": program_key,
        "name": program["name"],
        "weeks": program["weeks"],
        "start_date": datetime.now().date().isoformat(),
        "start_ts": int(time.time()),
        "current_week": 1,
    }
    hist.save_user_section(name, "active_program", active)
    return active


def current_program(name: str) -> Dict[str, Any] | None:
    """讀取進行中的計畫。"""
    active = hist.load_user_section(name, "active_program")
    if not active or not isinstance(active, dict):
        return None
    # 計算當前週數
    start_date = datetime.fromisoformat(active.get("start_date", "2000-01-01")).date()
    days_elapsed = (datetime.now().date() - start_date).days
    current_week = max(1, (days_elapsed // 7) + 1)
    active["current_week"] = min(current_week, active.get("weeks", 1))
    return active


def program_details(program_key: str) -> Dict[str, Any] | None:
    """取得計畫詳細資訊。"""
    return BUILTIN_PROGRAMS.get(program_key)


def program_week_schedule(
    program_key: str, week: int,
) -> Dict[str, Any] | None:
    """取得某週的課程安排。"""
    program = BUILTIN_PROGRAMS.get(program_key)
    if not program:
        return None
    for item in program.get("schedule", []):
        if item.get("week") == week:
            return item
    return None


def end_program(name: str) -> None:
    """結束進行中的計畫。"""
    hist.save_user_section(name, "active_program", None)


def program_completion(name: str) -> float:
    """計畫完成百分比（0-100）。"""
    active = current_program(name)
    if not active:
        return 0.0
    weeks = active.get("weeks", 1)
    current = active.get("current_week", 1)
    return (current / weeks) * 100
