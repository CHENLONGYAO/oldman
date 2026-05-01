"""
每位使用者的訓練紀錄（以 JSON 儲存於 user_data/）。
提供進度追蹤、連續日、徽章計算。
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

DATA_DIR = Path(os.environ.get("SMART_REHAB_DATA_DIR", Path(__file__).parent / "user_data"))


# -------- 內部工具 --------
_ALLOWED = "-_一二三四五六七八九十"


def _safe_name(name: str) -> str:
    cleaned = "".join(
        c for c in (name or "") if c.isalnum() or c in _ALLOWED
    )
    return cleaned or "anon"


def _user_file(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{_safe_name(name)}.json"


# -------- 讀寫 --------
def load(name: str) -> Dict[str, Any]:
    f = _user_file(name)
    if not f.exists():
        return {"name": name, "sessions": []}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"name": name, "sessions": []}


def load_profile(name: str) -> Dict[str, Any]:
    """讀取使用者基本資料；舊資料沒有 profile 時回傳可用的最小資料。"""
    data = load(name)
    profile = data.get("profile") or {}
    profile.setdefault("name", data.get("display_name") or data.get("name", name))
    if data.get("age") is not None:
        profile.setdefault("age", data.get("age"))
    return profile


def save_profile(
    profile: Dict[str, Any],
    storage_key: str | None = None,
) -> Dict[str, Any]:
    """保存使用者基本資料，與訓練 sessions 放在同一份 JSON。"""
    name = str(profile.get("name", "")).strip()
    if not name:
        raise ValueError("profile name is required")
    key = str(storage_key or name).strip()
    data = load(key)
    data["name"] = name
    data["display_name"] = name
    data["storage_key"] = key
    data["age"] = profile.get("age")
    data["profile"] = profile
    data.setdefault("sessions", [])
    _user_file(key).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data


def ensure_account_storage(
    storage_key: str,
    profile: Dict[str, Any] | None = None,
    legacy_names: list[str] | None = None,
) -> bool:
    """Create an isolated history file for an authenticated account.

    If an older display-name JSON file exists, copy it once into the account
    scoped file so existing local progress remains available without showing
    other local users as login choices.
    """
    key = str(storage_key or "").strip()
    if not key:
        return False
    target = _user_file(key)
    if target.exists():
        return True

    for legacy in legacy_names or []:
        legacy_key = str(legacy or "").strip()
        if not legacy_key or legacy_key == key:
            continue
        source = _user_file(legacy_key)
        if source.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
            data = load(key)
            merged_profile = data.get("profile") or {}
            if profile:
                merged_profile.update({
                    k: v for k, v in profile.items()
                    if v not in (None, "", [])
                })
            display_name = (
                merged_profile.get("name")
                or data.get("display_name")
                or data.get("name")
                or legacy_key
            )
            data["name"] = display_name
            data["display_name"] = display_name
            data["storage_key"] = key
            data["profile"] = merged_profile
            target.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True

    if profile:
        save_profile(profile, storage_key=key)
        return True

    return False


def profile_completion(profile: Dict[str, Any]) -> int:
    """回傳基本資料完成度百分比，供 UI 顯示。"""
    fields = [
        "name", "age", "gender", "height_cm", "weight_kg",
        "affected_side", "condition", "diagnosis", "pain_area",
        "mobility_aid", "activity_level", "weekly_goal", "daily_goal",
        "preferred_training_time",
    ]
    done = 0
    for key in fields:
        val = profile.get(key)
        if isinstance(val, list):
            done += int(bool(val))
        else:
            done += int(val not in (None, "", "—"))
    return round(done / len(fields) * 100)


def save_session(
    name: str,
    exercise: str,
    score: float,
    joint_scores: Dict[str, Dict[str, float]],
    age: int,
    rep_count: int | None = None,
    neural_scores: Dict[str, float] | None = None,
    pain_before: int | None = None,
    pain_after: int | None = None,
    safety_flag: str | None = None,
    display_name: str | None = None,
) -> Dict[str, Any]:
    data = load(name)
    data["storage_key"] = name
    if display_name:
        data["name"] = display_name
        data["display_name"] = display_name
    else:
        data["name"] = data.get("display_name") or data.get("name") or name
    data["age"] = age
    entry: Dict[str, Any] = {
        "ts": int(time.time()),
        "exercise": exercise,
        "score": float(score),
        "joints": joint_scores,
    }
    if rep_count is not None:
        entry["rep_count"] = int(rep_count)
    if neural_scores:
        entry["neural_scores"] = {
            k: float(v) for k, v in neural_scores.items()
        }
    if pain_before is not None:
        entry["pain_before"] = int(pain_before)
    if pain_after is not None:
        entry["pain_after"] = int(pain_after)
    if safety_flag:
        entry["safety_flag"] = safety_flag
    data.setdefault("sessions", []).append(entry)
    _user_file(name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data


def update_last_session(name: str, **fields: Any) -> bool:
    """更新最後一筆訓練紀錄的指定欄位（例如 pain_after）。"""
    data = load(name)
    sessions = data.get("sessions", [])
    if not sessions:
        return False
    sessions[-1].update(fields)
    _user_file(name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def personal_best(name: str, exercise: str) -> float | None:
    """指定動作的個人最佳分數（無紀錄時回傳 None）。"""
    data = load(name)
    scores = [
        s["score"] for s in data.get("sessions", [])
        if s.get("exercise") == exercise
    ]
    return max(scores) if scores else None


def is_new_personal_best(name: str, exercise: str,
                         new_score: float) -> bool:
    """判斷新分數是否為該動作的個人新高（不含本筆）。"""
    pb = personal_best(name, exercise)
    return pb is None or new_score > pb


def today_session_count(name: str) -> int:
    """今日已完成的訓練次數。"""
    data = load(name)
    today = datetime.now().date()
    return sum(
        1 for s in data.get("sessions", [])
        if datetime.fromtimestamp(s["ts"]).date() == today
    )


def _template_category_priority(profile: Dict[str, Any]) -> list[str]:
    goals = " ".join(str(v) for v in profile.get("condition", []))
    diagnosis = str(profile.get("diagnosis", ""))
    text = f"{goals} {diagnosis}".lower()
    if any(k in text for k in ("上肢", "肩", "手", "upper", "shoulder", "arm")):
        return ["upper", "balance", "lower"]
    if any(k in text for k in ("下肢", "膝", "髖", "lower", "knee", "hip")):
        return ["lower", "balance", "upper"]
    if any(k in text for k in ("平衡", "balance", "步態")):
        return ["balance", "lower", "upper"]
    return ["upper", "lower", "balance", "custom"]


def _exercise_key_from_session(session: Dict[str, Any], templates: Dict[str, Dict]) -> str | None:
    exercise = str(session.get("exercise", ""))
    if exercise in templates:
        return exercise
    for key, tpl in templates.items():
        if exercise == tpl.get("name") or key in exercise:
            return key
    return None


def today_plan(
    name: str,
    templates: Dict[str, Dict],
    profile: Dict[str, Any] | None = None,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a small in-app rehab plan for today.

    The plan favors the user's goals, avoids repeating very recent exercises,
    and keeps the first version intentionally local and deterministic.
    """
    profile = profile or load_profile(name)
    settings = settings or {}
    data = load(name)
    sessions = data.get("sessions", [])
    today = datetime.now().date()
    today_sessions = [
        s for s in sessions
        if datetime.fromtimestamp(s["ts"]).date() == today
    ]
    daily_goal = int(
        profile.get("daily_goal")
        or settings.get("daily_goal")
        or 1
    )
    daily_goal = max(1, min(5, daily_goal))
    plan_size = max(1, min(3, daily_goal))

    completed_keys = {
        k for k in (
            _exercise_key_from_session(s, templates) for s in today_sessions
        )
        if k
    }
    counts: Dict[str, int] = {k: 0 for k in templates}
    recent_keys: set[str] = set()
    recent_cutoff = today - timedelta(days=5)
    for s in sessions:
        key = _exercise_key_from_session(s, templates)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        if datetime.fromtimestamp(s["ts"]).date() >= recent_cutoff:
            recent_keys.add(key)

    category_order = _template_category_priority(profile)
    category_rank = {cat: idx for idx, cat in enumerate(category_order)}

    def sort_key(item: tuple[str, Dict]) -> tuple:
        key, tpl = item
        category = tpl.get("category", "custom")
        return (
            key in completed_keys,
            category_rank.get(category, 99),
            key in recent_keys,
            counts.get(key, 0),
            tpl.get("name", key),
        )

    ordered = sorted(templates.items(), key=sort_key)
    task_keys = [key for key, _ in ordered[:plan_size]]
    tasks = []
    for key in task_keys:
        tpl = templates[key]
        tasks.append({
            "key": key,
            "name": tpl.get("name", key),
            "description": tpl.get("description", ""),
            "cue": tpl.get("cue", ""),
            "category": tpl.get("category", "custom"),
            "completed": key in completed_keys,
        })

    completed_count = len(today_sessions)
    next_key = next((t["key"] for t in tasks if not t["completed"]), None)
    if next_key is None and ordered:
        next_key = ordered[0][0]

    last_session = sessions[-1] if sessions else {}
    last_flag = last_session.get("safety_flag")
    reminder_enabled = bool(
        profile.get("reminder_enabled", settings.get("reminder_enabled", True))
    )
    preferred_time = (
        profile.get("preferred_training_time")
        or settings.get("preferred_training_time")
        or "09:00"
    )
    if last_flag:
        reminder = "上次疼痛偏高，今天先用低強度並留意身體反應。"
    elif completed_count >= daily_goal:
        reminder = "今天的復健目標已完成，記得補水和休息。"
    elif reminder_enabled:
        left = max(0, daily_goal - completed_count)
        reminder = f"今天還差 {left} 次，建議在 {preferred_time} 前完成今日復健。"
    else:
        reminder = ""

    return {
        "date": today.isoformat(),
        "daily_goal": daily_goal,
        "completed_count": completed_count,
        "tasks": tasks,
        "next_key": next_key,
        "reminder": reminder,
        "last_safety_flag": last_flag,
    }


def recommend_exercise(name: str,
                       available_keys: List[str]) -> str | None:
    """依過往紀錄推薦下一個動作：
    - 偏向選擇較少做過的動作
    - 若都未做過，回傳第一個
    """
    if not available_keys:
        return None
    data = load(name)
    counts: Dict[str, int] = {k: 0 for k in available_keys}
    for s in data.get("sessions", []):
        # 用 exercise 名稱反查 key 並不直接，這裡退而求其次：
        # 推薦時直接按 exercise 名稱比對；找不到的視為 0 次
        ex_name = s.get("exercise", "")
        for k in available_keys:
            if ex_name and k in ex_name:
                counts[k] += 1
    return min(counts, key=counts.get)


def list_recent_users(limit: int = 5) -> List[Dict[str, Any]]:
    """最近活動的使用者（依最後訓練時間排序）。"""
    users = list_users()
    users.sort(key=lambda u: u.get("last_ts", 0), reverse=True)
    return users[:limit]


def list_users() -> List[Dict[str, Any]]:
    """列出所有使用者摘要（供臨床端）。"""
    if not DATA_DIR.exists():
        return []
    out: List[Dict[str, Any]] = []
    for f in sorted(DATA_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        sessions = d.get("sessions", [])
        avg = (
            sum(s.get("score", 0.0) for s in sessions) / len(sessions)
            if sessions else 0.0
        )
        profile = d.get("profile") or {}
        profile.setdefault("name", d.get("name", f.stem))
        out.append({
            "name": profile.get("name") or d.get("display_name") or d.get("name", f.stem),
            "storage_key": d.get("storage_key") or f.stem,
            "age": profile.get("age", d.get("age")),
            "profile": profile,
            "session_count": len(sessions),
            "avg_score": avg,
            "last_ts": sessions[-1]["ts"] if sessions else 0,
        })
    return out


# -------- 連續日 --------
def _session_date(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def streak_days(sessions: List[Dict[str, Any]]) -> int:
    """目前連續訓練日數（以本地時間為準）。"""
    if not sessions:
        return 0
    dates: Set[str] = {_session_date(s["ts"]) for s in sessions}
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    latest = max(
        datetime.strptime(d, "%Y-%m-%d").date() for d in dates
    )
    if latest != today and latest != yesterday:
        return 0
    streak = 0
    cursor = latest
    while cursor.strftime("%Y-%m-%d") in dates:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


# -------- 徽章 --------
BADGES: Dict[str, Tuple[str, str]] = {
    "first_session": ("🌱 踏出第一步", "完成首次訓練"),
    "streak_3": ("🔥 連續三日", "連續 3 天訓練"),
    "streak_7": ("⭐ 七日達人", "連續 7 天訓練"),
    "streak_30": ("🏅 月度堅持", "連續 30 天訓練"),
    "high_score_80": ("👍 穩定表現", "單次分數達 80"),
    "high_score_90": ("💎 動作達標", "單次分數達 90"),
    "ten_sessions": ("🏆 堅持不懈", "累積完成 10 次訓練"),
    "fifty_sessions": ("🎖 百練成鋼", "累積完成 50 次訓練"),
    "variety_3": ("🌈 多元訓練", "完成 3 種不同動作"),
    "today_goal": ("✅ 今日達標", "完成今日復健目標"),
    "weekly_goal": ("📅 本週穩定", "達成本週訓練目標"),
    "return_training": ("↩ 回到節奏", "中斷後重新開始訓練"),
    "pain_down": ("🫶 疼痛下降", "訓練後疼痛分數下降"),
}


def compute_badges(name: str) -> Tuple[Set[str], int]:
    data = load(name)
    sessions = data.get("sessions", [])
    profile = data.get("profile") or {}
    earned: Set[str] = set()
    if sessions:
        earned.add("first_session")
    streak = streak_days(sessions)
    if streak >= 3:
        earned.add("streak_3")
    if streak >= 7:
        earned.add("streak_7")
    if streak >= 30:
        earned.add("streak_30")
    if any(s.get("score", 0) >= 80 for s in sessions):
        earned.add("high_score_80")
    if any(s.get("score", 0) >= 90 for s in sessions):
        earned.add("high_score_90")
    if len(sessions) >= 10:
        earned.add("ten_sessions")
    if len(sessions) >= 50:
        earned.add("fifty_sessions")
    if len({s.get("exercise") for s in sessions}) >= 3:
        earned.add("variety_3")
    today = datetime.now().date()
    today_count = sum(
        1 for s in sessions
        if datetime.fromtimestamp(s["ts"]).date() == today
    )
    daily_goal = int(profile.get("daily_goal") or 1)
    if today_count >= max(1, daily_goal):
        earned.add("today_goal")
    week_start = today - timedelta(days=today.weekday())
    week_count = sum(
        1 for s in sessions
        if datetime.fromtimestamp(s["ts"]).date() >= week_start
    )
    weekly_goal = int(profile.get("weekly_goal") or 3)
    if week_count >= max(1, weekly_goal):
        earned.add("weekly_goal")
    if len(sessions) >= 2:
        prev_day = datetime.fromtimestamp(sessions[-2]["ts"]).date()
        last_day = datetime.fromtimestamp(sessions[-1]["ts"]).date()
        if (last_day - prev_day).days >= 7:
            earned.add("return_training")
    if any(
        "pain_before" in s
        and "pain_after" in s
        and int(s.get("pain_after", 0)) < int(s.get("pain_before", 0))
        for s in sessions
    ):
        earned.add("pain_down")
    return earned, streak


# ============================================================
# 通用資料存儲（日記、生命跡象、藥物等）
# ============================================================
def save_user_section(name: str, section_key: str, data: Any) -> None:
    """
    存儲使用者的任意資料區段（日記、生命跡象、藥物等）。
    若區段不存在則新建；若存在則附加到列表（若 data 是字典），
    或整體替換（若 data 是列表或單一值）。
    """
    user_data = load(name)
    if isinstance(data, dict) and "ts" in data:
        # 時間戳字典 → 附加到列表
        user_data.setdefault(section_key, []).append(data)
    else:
        # 直接替換
        user_data[section_key] = data
    _user_file(name).write_text(
        json.dumps(user_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        from db import mirror_health_data_by_profile_name
        mirror_health_data_by_profile_name(name, section_key, data)
    except Exception:
        pass


def load_user_section(name: str, section_key: str, default: Any = None) -> Any:
    """讀取使用者的任意資料區段。"""
    user_data = load(name)
    return user_data.get(section_key, default)


# ============================================================
# XP 與等級系統
# ============================================================
XP_PER_SESSION = 100
XP_BONUS_PB = 50
XP_BONUS_STREAK = 20
XP_BONUS_PERFECT = 80

LEVELS = [
    (0, "🥉 初學者", "Beginner"),
    (500, "🥈 進階者", "Intermediate"),
    (1500, "🥇 熟練者", "Proficient"),
    (3000, "🏆 高手", "Expert"),
    (6000, "💎 大師", "Master"),
    (10000, "👑 傳說", "Legend"),
]


def compute_xp(name: str) -> int:
    """計算使用者總 XP。"""
    user_data = load(name)
    return int(user_data.get("xp_total", 0))


def add_xp(name: str, amount: int) -> int:
    """增加 XP 並回傳新總值。"""
    user_data = load(name)
    current = int(user_data.get("xp_total", 0))
    new_total = current + amount
    user_data["xp_total"] = new_total
    _user_file(name).write_text(
        json.dumps(user_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return new_total


def current_level(xp: int) -> Dict[str, Any]:
    """根據 XP 回傳當前等級資訊。"""
    level_idx = 0
    for idx, (threshold, _, _) in enumerate(LEVELS):
        if xp >= threshold:
            level_idx = idx
    level = LEVELS[level_idx]
    next_idx = min(level_idx + 1, len(LEVELS) - 1)
    next_threshold = LEVELS[next_idx][0]
    current_xp = xp - level[0]
    xp_for_next = max(0, next_threshold - level[0])
    progress = 100 if xp_for_next == 0 else (current_xp / xp_for_next * 100)
    return {
        "level": level_idx,
        "icon": level[1].split(" ", 1)[0],
        "name_zh": level[1].split(" ", 1)[-1],
        "name_en": level[2],
        "total_xp": xp,
        "current_xp": current_xp,
        "xp_for_next": xp_for_next,
        "next_threshold": next_threshold,
        "progress": min(100, max(0, progress)),
    }


def xp_for_session(score: float, is_pb: bool, streak: int) -> int:
    """根據評分、個人最佳、連續天數計算本次 XP。"""
    xp = XP_PER_SESSION
    if is_pb:
        xp += XP_BONUS_PB
    if streak >= 7:
        xp += XP_BONUS_STREAK
    if score >= 90:
        xp += XP_BONUS_PERFECT
    return xp
