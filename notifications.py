"""
Notification system: email, SMS, browser push, in-app inbox.

Channels:
- email: SMTP (configurable via env vars)
- sms: Twilio (optional)
- push: Web Push (optional)
- in_app: Always works, stored in DB

Schedule notifications, send reminders, handle digest emails.
"""
from __future__ import annotations
import json
import os
import smtplib
from datetime import datetime, timedelta, time
from email.message import EmailMessage
from typing import Dict, List, Optional

from db import execute_query, execute_update


NOTIFICATION_TYPES = {
    "training_reminder": {"icon": "🏃", "priority": "normal"},
    "medication_reminder": {"icon": "💊", "priority": "high"},
    "appointment_reminder": {"icon": "📅", "priority": "high"},
    "quest_unlocked": {"icon": "🎯", "priority": "low"},
    "achievement": {"icon": "🏆", "priority": "low"},
    "high_risk_alert": {"icon": "⚠️", "priority": "high"},
    "therapist_message": {"icon": "💬", "priority": "normal"},
    "weekly_digest": {"icon": "📊", "priority": "low"},
    "system": {"icon": "🔔", "priority": "low"},
}


def send_in_app(user_id: str, notif_type: str, title: str, body: str,
                action_url: Optional[str] = None) -> bool:
    """Store in-app notification."""
    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, 'notification', ?, datetime('now', '+30 days'))
            """,
            (user_id, json.dumps({
                "type": notif_type,
                "title": title,
                "body": body,
                "action_url": action_url,
                "read": False,
                "created_at": datetime.now().isoformat(),
            }, ensure_ascii=False)),
        )
        return True
    except Exception:
        return False


def send_email(to_addr: str, subject: str, body: str,
               html: Optional[str] = None) -> bool:
    """Send email via SMTP. Requires env vars: SMTP_HOST, SMTP_USER, SMTP_PASS."""
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("SMTP_FROM", user)

    if not (host and user and password):
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        return False


def send_sms(phone: str, body: str) -> bool:
    """Send SMS via Twilio. Requires TWILIO_* env vars."""
    sid = os.environ.get("TWILIO_SID")
    token = os.environ.get("TWILIO_TOKEN")
    from_phone = os.environ.get("TWILIO_FROM")

    if not (sid and token and from_phone):
        return False

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(body=body, from_=from_phone, to=phone)
        return True
    except Exception:
        return False


def send_to_user(user_id: str, notif_type: str, title: str, body: str,
                 channels: Optional[List[str]] = None) -> Dict:
    """Send notification to user via all enabled channels."""
    if channels is None:
        channels = _get_user_channels(user_id, notif_type)

    results = {}

    if "in_app" in channels:
        results["in_app"] = send_in_app(user_id, notif_type, title, body)

    rows = execute_query(
        """
        SELECT u.email, p.contact_phone as phone FROM users u
        LEFT JOIN user_profiles p ON u.user_id = p.user_id
        WHERE u.user_id = ?
        """,
        (user_id,),
    )
    if rows:
        contact = rows[0]
        if "email" in channels and contact.get("email"):
            results["email"] = send_email(contact["email"], title, body)
        if "sms" in channels and contact.get("phone"):
            results["sms"] = send_sms(contact["phone"], f"{title}\n{body}")

    return results


def _get_user_channels(user_id: str, notif_type: str) -> List[str]:
    """Get user's preferred channels for this notification type."""
    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = 'notif_prefs'
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )

    if rows:
        try:
            prefs = json.loads(rows[0]["data_json"])
            return prefs.get(notif_type, ["in_app"])
        except Exception:
            pass

    type_def = NOTIFICATION_TYPES.get(notif_type, {})
    if type_def.get("priority") == "high":
        return ["in_app", "email"]
    return ["in_app"]


def save_user_channels(user_id: str, prefs: Dict) -> bool:
    """Save user's notification channel preferences."""
    try:
        execute_update(
            """
            DELETE FROM offline_cache
            WHERE user_id = ? AND cache_type = 'notif_prefs'
            """,
            (user_id,),
        )
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, 'notif_prefs', ?, datetime('now', '+1 year'))
            """,
            (user_id, json.dumps(prefs, ensure_ascii=False)),
        )
        return True
    except Exception:
        return False


def get_inbox(user_id: str, unread_only: bool = False, limit: int = 50) -> List[Dict]:
    """Get user's notification inbox."""
    rows = execute_query(
        """
        SELECT id, data_json, created_at FROM offline_cache
        WHERE user_id = ? AND cache_type = 'notification'
        ORDER BY created_at DESC LIMIT ?
        """,
        (user_id, limit),
    )

    inbox = []
    for r in rows:
        try:
            data = json.loads(r["data_json"])
            data["id"] = r["id"]
            data["created_at"] = data.get("created_at", r["created_at"])
            if unread_only and data.get("read"):
                continue
            inbox.append(data)
        except Exception:
            continue
    return inbox


def mark_read(notif_id: int) -> bool:
    """Mark notification as read."""
    rows = execute_query(
        "SELECT data_json FROM offline_cache WHERE id = ?",
        (notif_id,),
    )
    if not rows:
        return False
    try:
        data = json.loads(rows[0]["data_json"])
        data["read"] = True
        execute_update(
            "UPDATE offline_cache SET data_json = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), notif_id),
        )
        return True
    except Exception:
        return False


def mark_all_read(user_id: str) -> int:
    """Mark all user notifications as read."""
    rows = execute_query(
        """
        SELECT id, data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = 'notification'
        """,
        (user_id,),
    )
    count = 0
    for r in rows:
        try:
            data = json.loads(r["data_json"])
            if not data.get("read"):
                data["read"] = True
                execute_update(
                    "UPDATE offline_cache SET data_json = ? WHERE id = ?",
                    (json.dumps(data, ensure_ascii=False), r["id"]),
                )
                count += 1
        except Exception:
            continue
    return count


def get_unread_count(user_id: str) -> int:
    """Quick count of unread notifications."""
    return len(get_inbox(user_id, unread_only=True, limit=200))


def schedule_training_reminders(user_id: str) -> int:
    """Schedule reminders based on user preferences. Run periodically."""
    rows = execute_query(
        """
        SELECT preferred_training_time FROM user_profiles WHERE user_id = ?
        """,
        (user_id,),
    )

    if not rows or not rows[0].get("preferred_training_time"):
        return 0

    today_sessions = execute_query(
        """
        SELECT COUNT(*) as c FROM sessions
        WHERE user_id = ? AND DATE(created_at) = DATE('now')
        """,
        (user_id,),
    )

    if today_sessions and today_sessions[0]["c"] > 0:
        return 0

    sent = send_to_user(
        user_id,
        "training_reminder",
        "今天還沒訓練哦！",
        "今天還沒做復健訓練，現在做一次吧！💪",
    )
    return 1 if sent.get("in_app") else 0


def generate_weekly_digest(user_id: str, lang: str = "zh") -> Dict:
    """Generate weekly summary email."""
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()

    rows = execute_query(
        """
        SELECT COUNT(*) as sessions, AVG(score) as avg_score,
               MAX(score) as best_score
        FROM sessions WHERE user_id = ? AND created_at >= ?
        """,
        (user_id, week_ago),
    )

    if not rows or not rows[0]["sessions"]:
        return {
            "subject": "週報" if lang == "zh" else "Weekly Digest",
            "body": "本週尚無訓練記錄" if lang == "zh"
                   else "No training this week",
        }

    s = rows[0]
    if lang == "zh":
        subject = f"週報：{s['sessions']} 次訓練"
        body = (
            f"本週訓練摘要：\n\n"
            f"• 訓練次數：{s['sessions']}\n"
            f"• 平均分數：{s['avg_score']:.1f}\n"
            f"• 最高分：{s['best_score']:.1f}\n\n"
            f"繼續加油！💪"
        )
    else:
        subject = f"Weekly: {s['sessions']} sessions"
        body = (
            f"Your week:\n\n"
            f"• Sessions: {s['sessions']}\n"
            f"• Avg Score: {s['avg_score']:.1f}\n"
            f"• Best: {s['best_score']:.1f}\n\n"
            f"Keep going! 💪"
        )

    return {"subject": subject, "body": body}
