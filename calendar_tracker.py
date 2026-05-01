"""
預約行事曆管理。
存儲於 user_data/{name}.json 的 appointments 列表。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List
from uuid import uuid4

import history as hist


APPT_TYPES = ["物理治療", "回診", "X光/檢查", "藥物領取", "其他"]


def add_appointment(name: str, appt: Dict[str, Any]) -> None:
    """
    新增預約。
    appt: {date (YYYY-MM-DD), time (HH:MM), type, doctor, location, notes}
    """
    appts = list_appointments(name, upcoming_only=False)
    appt_with_id = {
        **appt,
        "id": f"appt_{uuid4().hex[:10]}",
        "date": str(appt.get("date", datetime.now().date().isoformat())),
        "time": str(appt.get("time", "09:00"))[:5],
        "created": int(time.time()),
    }
    appts.append(appt_with_id)
    hist.save_user_section(name, "appointments", appts)


def list_appointments(name: str, upcoming_only: bool = True) -> List[Dict[str, Any]]:
    """列出所有預約（可選擇只顯示未來的）。"""
    appts = hist.load_user_section(name, "appointments", [])
    if isinstance(appts, dict):
        appts = [appts]
    appts = appts if isinstance(appts, list) else []

    appts.sort(key=lambda a: (a.get("date", "9999-12-31"), a.get("time", "23:59")))
    if not upcoming_only:
        return appts

    today = datetime.now().date().isoformat()
    return [a for a in appts if a.get("date", "1900-01-01") >= today]


def remove_appointment(name: str, appt_id: str) -> None:
    """刪除預約。"""
    appts = list_appointments(name, upcoming_only=False)
    filtered = [a for a in appts if a.get("id") != appt_id]
    hist.save_user_section(name, "appointments", filtered)


def upcoming_count(name: str, days: int = 7) -> int:
    """計算 N 天內有多少預約。"""
    appts = list_appointments(name, upcoming_only=True)
    cutoff = (datetime.now() + timedelta(days=days)).date().isoformat()
    return sum(1 for a in appts if a.get("date", "9999-12-31") <= cutoff)


def next_appointment(name: str) -> Dict[str, Any] | None:
    """取得最近的一個預約。"""
    appts = list_appointments(name, upcoming_only=True)
    if not appts:
        return None

    appts.sort(key=lambda a: (a.get("date", "9999-12-31"), a.get("time", "23:59")))
    return appts[0] if appts else None


def appointments_by_type(name: str) -> Dict[str, List[Dict[str, Any]]]:
    """按類型分組所有預約。"""
    appts = list_appointments(name, upcoming_only=False)
    grouped = {}

    for appt_type in APPT_TYPES:
        grouped[appt_type] = [a for a in appts if a.get("type") == appt_type]

    return grouped


def appointment_reminders(name: str, days_before: int = 1) -> List[Dict[str, Any]]:
    """取得需要提醒的預約（距今 N 天內）。"""
    appts = list_appointments(name, upcoming_only=True)
    today = datetime.now().date()
    cutoff = (today + timedelta(days=days_before)).isoformat()

    reminders = []
    for appt in appts:
        appt_date = appt.get("date", "9999-12-31")
        if today.isoformat() <= appt_date <= cutoff:
            reminders.append(appt)

    reminders.sort(key=lambda a: a.get("date"))
    return reminders
