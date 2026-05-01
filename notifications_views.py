"""
Notification UI: inbox, channel preferences, test sending.
"""
import streamlit as st

from auth import get_session_user
from notifications import (
    NOTIFICATION_TYPES, get_inbox, mark_read, mark_all_read,
    save_user_channels, send_to_user, generate_weekly_digest,
)


def view_notifications():
    """Notification center."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    st.title("🔔 " + ("通知中心" if lang == "zh" else "Notifications"))

    tab_inbox, tab_prefs = st.tabs([
        "📥 " + ("收件匣" if lang == "zh" else "Inbox"),
        "⚙️ " + ("偏好設定" if lang == "zh" else "Preferences"),
    ])

    with tab_inbox:
        _render_inbox(user_id, lang)

    with tab_prefs:
        _render_prefs(user_id, lang)


def _render_inbox(user_id: str, lang: str) -> None:
    inbox = get_inbox(user_id, limit=50)
    unread = [n for n in inbox if not n.get("read")]

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(
            f"📨 {len(unread)} {'未讀' if lang == 'zh' else 'unread'} "
            f"/ {len(inbox)} {'總計' if lang == 'zh' else 'total'}"
        )
    with col2:
        if unread and st.button(
            "✓ " + ("全部已讀" if lang == "zh" else "Mark all read"),
            use_container_width=True,
        ):
            mark_all_read(user_id)
            st.rerun()

    if not inbox:
        st.info("沒有通知" if lang == "zh" else "No notifications yet")
        return

    for notif in inbox:
        type_def = NOTIFICATION_TYPES.get(notif.get("type", ""), {})
        icon = type_def.get("icon", "🔔")
        is_read = notif.get("read", False)

        bg = "#f8f9fa" if is_read else "#e7f5ff"
        border = "#dee2e6" if is_read else "#74c0fc"

        st.markdown(
            f"<div style='background:{bg};border-left:4px solid {border};"
            f"padding:12px;border-radius:6px;margin-bottom:8px'>"
            f"<div style='font-weight:{'400' if is_read else '600'}'>"
            f"{icon} {notif['title']}</div>"
            f"<div style='font-size:13px;color:#6c757d;margin-top:4px'>"
            f"{notif['body']}</div>"
            f"<div style='font-size:11px;color:#adb5bd;margin-top:6px'>"
            f"{notif.get('created_at', '')[:19]}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if not is_read:
            if st.button(
                "✓ " + ("標記已讀" if lang == "zh" else "Mark read"),
                key=f"mark_{notif['id']}",
            ):
                mark_read(notif["id"])
                st.rerun()


def _render_prefs(user_id: str, lang: str) -> None:
    st.subheader("📡 " + ("通知通道" if lang == "zh" else "Channels"))
    st.caption(
        "設定每種通知的傳送方式（站內 / 電郵 / 簡訊）"
        if lang == "zh" else
        "Set how each notification type is delivered"
    )

    channels = ["in_app", "email", "sms"]
    channel_labels = {
        "in_app": "站內" if lang == "zh" else "In-App",
        "email": "電郵" if lang == "zh" else "Email",
        "sms": "簡訊" if lang == "zh" else "SMS",
    }

    type_labels = {
        "training_reminder": "訓練提醒" if lang == "zh" else "Training Reminder",
        "medication_reminder": "服藥提醒" if lang == "zh" else "Medication",
        "appointment_reminder": "預約提醒" if lang == "zh" else "Appointment",
        "quest_unlocked": "任務解鎖" if lang == "zh" else "Quest Unlocked",
        "achievement": "成就" if lang == "zh" else "Achievement",
        "high_risk_alert": "高風險警示" if lang == "zh" else "High Risk Alert",
        "therapist_message": "治療師訊息" if lang == "zh" else "Therapist Msg",
        "weekly_digest": "週報" if lang == "zh" else "Weekly Digest",
    }

    prefs = {}
    for ntype in NOTIFICATION_TYPES:
        if ntype not in type_labels:
            continue
        cols = st.columns([2, 3])
        with cols[0]:
            st.markdown(f"**{NOTIFICATION_TYPES[ntype]['icon']} "
                       f"{type_labels[ntype]}**")
        with cols[1]:
            selected = st.multiselect(
                "通道" if lang == "zh" else "Channels",
                options=channels,
                default=["in_app"],
                format_func=lambda c: channel_labels[c],
                key=f"prefs_{ntype}",
                label_visibility="collapsed",
            )
            prefs[ntype] = selected

    if st.button(
        "💾 " + ("儲存偏好" if lang == "zh" else "Save Preferences"),
        type="primary",
        use_container_width=True,
    ):
        if save_user_channels(user_id, prefs):
            st.success("✓ " + ("已儲存" if lang == "zh" else "Saved"))

    st.divider()
    st.subheader("🧪 " + ("測試通知" if lang == "zh" else "Test Notification"))

    test_type = st.selectbox(
        "類型" if lang == "zh" else "Type",
        options=list(type_labels.keys()),
        format_func=lambda k: type_labels[k],
    )

    if st.button(
        "📤 " + ("發送測試" if lang == "zh" else "Send Test"),
        use_container_width=True,
    ):
        results = send_to_user(
            user_id, test_type,
            f"測試：{type_labels[test_type]}" if lang == "zh"
            else f"Test: {type_labels[test_type]}",
            "這是測試訊息" if lang == "zh" else "This is a test",
        )
        st.success(f"結果: {results}" if lang == "zh" else f"Results: {results}")

    st.divider()
    st.subheader("📊 " + ("週報預覽" if lang == "zh" else "Weekly Digest Preview"))

    digest = generate_weekly_digest(user_id, lang)
    st.markdown(f"**{digest['subject']}**")
    st.text(digest["body"])
