"""
智能提醒系統：根據進度、藥物、預約自動生成提醒。
支持訓練提醒、服藥提醒、預約提醒、達成里程碑提醒。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, time as dt_time
from typing import Any, Dict, List

import calendar_tracker
import history as hist
import medication
import programs


def get_pending_reminders(name: str) -> List[Dict[str, Any]]:
    """取得所有待處理的提醒。"""
    reminders = []

    # 1. 訓練提醒 - 根據目標和進度
    reminders.extend(_training_reminders(name))

    # 2. 服藥提醒 - 今日應服但未服
    reminders.extend(_medication_reminders(name))

    # 3. 預約提醒 - 24小時內的預約
    reminders.extend(_appointment_reminders(name))

    # 4. 計劃里程碑提醒 - 計劃進度達成
    reminders.extend(_program_milestone_reminders(name))

    # 5. 健康數據提醒 - 需要記錄的健康數據
    reminders.extend(_health_data_reminders(name))

    # Sort by priority (high first) then by timestamp
    reminders.sort(key=lambda r: (-r.get("priority", 0), r.get("ts", 0)))

    return reminders


def _training_reminders(name: str) -> List[Dict[str, Any]]:
    """訓練提醒：根據每日目標和進度。"""
    reminders = []
    settings = hist.load_user_section(name, "settings", {})
    daily_goal = settings.get("daily_goal", 1)
    today_sessions = hist.today_session_count(name)

    if today_sessions < daily_goal:
        remaining = daily_goal - today_sessions
        reminders.append({
            "ts": int(time.time()),
            "type": "training",
            "priority": 2,
            "icon": "🎯",
            "title": f"今日訓練目標 ({today_sessions}/{daily_goal})",
            "description": f"還有 {remaining} 次訓練，加油！",
            "action": "record",
        })

    return reminders


def _medication_reminders(name: str) -> List[Dict[str, Any]]:
    """服藥提醒：今日應服但未服。"""
    reminders = []
    meds = medication.upcoming_medications(name)
    now = datetime.now()

    for med in meds:
        if not med.get("taken"):
            scheduled_time = med.get("scheduled_time", "09:00")
            med_time = datetime.strptime(scheduled_time, "%H:%M").time()

            # Only remind if within 2 hours before or after scheduled time
            time_diff = abs(
                (datetime.combine(now.date(), now.time()) -
                 datetime.combine(now.date(), med_time)).total_seconds()
            )

            if time_diff < 7200:  # 2 hours
                reminders.append({
                    "ts": int(time.time()),
                    "type": "medication",
                    "priority": 3,
                    "icon": "💊",
                    "title": f"服藥提醒：{med.get('name')}",
                    "description": f"{med.get('dose')} @ {scheduled_time}",
                    "action": "medication",
                    "med_id": med.get("id"),
                })

    return reminders


def _appointment_reminders(name: str) -> List[Dict[str, Any]]:
    """預約提醒：24小時內即將到來的預約。"""
    reminders = []
    upcoming = calendar_tracker.appointment_reminders(name, days_before=1)

    for appt in upcoming:
        appt_datetime = datetime.fromisoformat(
            f"{appt.get('date')}T{appt.get('time', '09:00')}"
        )
        hours_until = (appt_datetime - datetime.now()).total_seconds() / 3600

        # High priority if less than 1 hour away
        priority = 3 if hours_until < 1 else 2

        reminders.append({
            "ts": int(time.time()),
            "type": "appointment",
            "priority": priority,
            "icon": "📅",
            "title": f"預約提醒：{appt.get('type')}",
            "description": f"{appt.get('date')} {appt.get('time')} - {appt.get('doctor')} @ {appt.get('location')}",
            "action": "calendar",
        })

    return reminders


def _program_milestone_reminders(name: str) -> List[Dict[str, Any]]:
    """計劃里程碑提醒。"""
    reminders = []
    current = programs.current_program(name)

    if not current:
        return reminders

    completion = programs.program_completion(name)
    milestones = [25, 50, 75, 100]

    for milestone in milestones:
        if completion >= milestone:
            # Check if already notified (store in user data)
            notified = hist.load_user_section(name, "milestone_notified", [])
            milestone_key = f"{current.get('key')}__{milestone}"

            if milestone_key not in notified:
                reminders.append({
                    "ts": int(time.time()),
                    "type": "milestone",
                    "priority": 1,
                    "icon": "🎉",
                    "title": f"里程碑達成：{milestone}%",
                    "description": f"{current.get('name')} 進度已達 {int(completion)}%，太棒了！",
                    "action": "programs",
                })
                # Mark as notified
                notified.append(milestone_key)
                hist.save_user_section(name, "milestone_notified", notified)

    return reminders


def _health_data_reminders(name: str) -> List[Dict[str, Any]]:
    """健康數據記錄提醒。"""
    reminders = []
    today = datetime.now().date().isoformat()

    # Check if today's journal was logged
    journal_entry = hist.load_user_section(name, "journal", [])
    if isinstance(journal_entry, dict):
        journal_entry = [journal_entry]

    has_today_journal = any(
        e.get("date") == today for e in journal_entry if isinstance(journal_entry, list)
    )

    if not has_today_journal:
        reminders.append({
            "ts": int(time.time()),
            "type": "journal",
            "priority": 1,
            "icon": "📝",
            "title": "填寫今日日記",
            "description": "記錄今日心情、精力、睡眠有助追蹤進度",
            "action": "journal",
        })

    # Check vitals (at least once per week)
    vitals = hist.load_user_section(name, "vitals", [])
    if isinstance(vitals, dict):
        vitals = [vitals]

    week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
    recent_vitals = [
        v for v in vitals
        if isinstance(vitals, list) and v.get("date", "1900-01-01") >= week_ago
    ]

    if not recent_vitals:
        reminders.append({
            "ts": int(time.time()),
            "type": "vitals",
            "priority": 1,
            "icon": "🌡️",
            "title": "記錄生命跡象",
            "description": "一周未記錄生命跡象，建議記錄血壓、心率等",
            "action": "vitals",
        })

    return reminders


def dismiss_reminder(name: str, reminder_type: str) -> None:
    """忽略某個類型的提醒（今日）。"""
    dismissed = hist.load_user_section(name, "dismissed_reminders", {})
    today = datetime.now().date().isoformat()

    if today not in dismissed:
        dismissed[today] = []

    if reminder_type not in dismissed[today]:
        dismissed[today].append(reminder_type)

    hist.save_user_section(name, "dismissed_reminders", dismissed)


def is_reminder_dismissed(name: str, reminder_type: str) -> bool:
    """檢查今日是否已忽略此提醒。"""
    dismissed = hist.load_user_section(name, "dismissed_reminders", {})
    today = datetime.now().date().isoformat()
    return reminder_type in dismissed.get(today, [])


def get_reminder_stats(name: str) -> Dict[str, Any]:
    """取得提醒統計。"""
    reminders = get_pending_reminders(name)

    return {
        "total": len(reminders),
        "by_type": {
            "training": sum(1 for r in reminders if r.get("type") == "training"),
            "medication": sum(1 for r in reminders if r.get("type") == "medication"),
            "appointment": sum(1 for r in reminders if r.get("type") == "appointment"),
            "milestone": sum(1 for r in reminders if r.get("type") == "milestone"),
            "journal": sum(1 for r in reminders if r.get("type") == "journal"),
            "vitals": sum(1 for r in reminders if r.get("type") == "vitals"),
        },
        "high_priority": sum(1 for r in reminders if r.get("priority", 0) >= 2),
    }
