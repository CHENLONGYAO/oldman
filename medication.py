"""
藥物追蹤與管理。
存儲於 user_data/{name}.json 的 medications 和 medication_log 列表。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List
from uuid import uuid4

import history as hist


def add_medication(name: str, med: Dict[str, Any]) -> None:
    """新增藥物。med: {name, dose, unit, frequency, times[], start_date, notes}"""
    meds = list_medications(name)
    times = med.get("times", [])
    if isinstance(times, str):
        times = [times]
    med_with_id = {
        **med,
        "id": f"med_{uuid4().hex[:10]}",
        "times": times or [datetime.now().strftime("%H:%M")],
        "start_date": med.get("start_date") or datetime.now().date().isoformat(),
        "created": int(time.time()),
    }
    meds.append(med_with_id)
    hist.save_user_section(name, "medications", meds)


def list_medications(name: str) -> List[Dict[str, Any]]:
    """列出所有藥物。"""
    meds = hist.load_user_section(name, "medications", [])
    if isinstance(meds, dict):  # Single medication stored
        return [meds]
    return meds if isinstance(meds, list) else []


def remove_medication(name: str, med_id: str) -> None:
    """刪除藥物。"""
    meds = list_medications(name)
    filtered = [m for m in meds if m.get("id") != med_id]
    hist.save_user_section(name, "medications", filtered)


def log_taken(name: str, med_id: str, scheduled_time: str | None = None) -> None:
    """記錄服藥。"""
    log_entry = {
        "ts": int(time.time()),
        "date": datetime.now().date().isoformat(),
        "time": datetime.now().time().isoformat(),
        "med_id": med_id,
    }
    if scheduled_time:
        log_entry["scheduled_time"] = scheduled_time
    hist.save_user_section(name, "medication_log", log_entry)


def today_taken(
    name: str,
    med_id: str,
    scheduled_time: str | None = None,
) -> bool:
    """今天是否已服用此藥物。"""
    logs = hist.load_user_section(name, "medication_log", [])
    if isinstance(logs, dict):
        logs = [logs]

    today = datetime.now().date().isoformat()
    for log in logs:
        same_med = log.get("date") == today and log.get("med_id") == med_id
        same_time = (
            scheduled_time is None
            or log.get("scheduled_time") == scheduled_time
        )
        if same_med and same_time:
            return True
    return False


def medication_adherence(name: str, days: int = 14) -> Dict[str, Dict[str, Any]]:
    """計算藥物依順性百分比（過去 N 天）。"""
    meds = list_medications(name)
    logs = hist.load_user_section(name, "medication_log", [])
    if isinstance(logs, dict):
        logs = [logs]

    cutoff = (datetime.now() - timedelta(days=days)).date()
    adherence = {}

    for med in meds:
        med_id = med.get("id")
        times = med.get("times", [])
        if isinstance(times, str):
            times = [times]
        expected = days * max(1, len(times))
        actual = sum(
            1 for log in logs
            if log.get("med_id") == med_id
            and datetime.fromisoformat(log.get("date", "1900-01-01")).date() >= cutoff
        )
        pct = (actual / expected * 100) if expected > 0 else 0
        adherence[med_id] = {
            "name": med.get("name"),
            "adherence": min(100, pct),
            "taken": actual,
            "expected": expected,
        }

    return adherence


def upcoming_medications(name: str) -> List[Dict[str, Any]]:
    """取得今日即將服用的藥物（按時間順序）。"""
    meds = list_medications(name)
    today_meds = []

    for med in meds:
        times = med.get("times", [])
        if isinstance(times, str):
            times = [times]

        for time_str in times:
            today_meds.append({
                **med,
                "scheduled_time": time_str,
                "taken": today_taken(name, med.get("id"), time_str),
            })

    # Sort by time
    today_meds.sort(key=lambda x: x.get("scheduled_time", ""))
    return today_meds
