"""
Daily routine view: orchestrated guided session.

Single-page guided experience:
- See today's progress at a glance
- Top 3 smart suggestions
- One-tap workflow start (daily/recovery/onboarding)
- Active workflow indicator
- Quick stats

Acts as the new home page for returning users.
"""
from __future__ import annotations
import streamlit as st

import ui
from auth import get_session_user


def view_daily_routine():
    """Daily orchestrated routine landing page."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]
    name = user.get("username") or user.get("name") or ""

    st.title(
        f"👋 {('歡迎回來' if lang == 'zh' else 'Welcome back')}, {name}!"
    )

    with ui.app_section(
        "今日狀態" if lang == "zh" else "Today",
        icon="📅",
    ):
        _render_today_stats(user_id, lang)

    with ui.app_section(
        "智慧建議" if lang == "zh" else "Smart Suggestions",
        ("根據你的訓練紀錄推薦下一步" if lang == "zh"
         else "Next steps tailored to your activity"),
        icon="✨",
    ):
        _render_smart_suggestions(user_id, lang)

    with ui.app_section(
        "一鍵開始" if lang == "zh" else "One-Tap Routines",
        icon="🚀",
    ):
        _render_workflow_starters(user_id, lang)

    with ui.app_section(
        "快速導航" if lang == "zh" else "Quick Links",
        icon="⚡",
    ):
        _render_quick_links(lang)

    _render_undo_indicator(user_id, lang)


def _render_today_stats(user_id: str, lang: str) -> None:
    """Render today's quick stats grid."""
    from db import execute_query
    from datetime import date

    today = date.today().isoformat()

    s_rows = execute_query(
        """
        SELECT COUNT(*) as c, AVG(score) as avg_s
        FROM sessions WHERE user_id = ? AND DATE(created_at) = ?
        """,
        (user_id, today),
    )

    streak = 0
    try:
        from smart_routing import _compute_streak
        streak = _compute_streak(user_id)
    except Exception:
        pass

    quest_xp = 0
    try:
        from quests import get_quest_xp_total
        quest_xp = get_quest_xp_total(user_id)
    except Exception:
        pass

    unread = 0
    try:
        from notifications import get_unread_count
        unread = get_unread_count(user_id)
    except Exception:
        pass

    cols = st.columns(4)
    with cols[0]:
        st.metric(
            "今日訓練" if lang == "zh" else "Today's Sessions",
            s_rows[0]["c"] if s_rows else 0,
            delta=(
                f"{s_rows[0]['avg_s']:.1f} 分" if s_rows and s_rows[0]["avg_s"]
                else None
            ),
        )
    with cols[1]:
        st.metric(
            "連續天數" if lang == "zh" else "Streak",
            f"{streak} 🔥",
        )
    with cols[2]:
        st.metric(
            "任務 XP" if lang == "zh" else "Quest XP",
            quest_xp,
        )
    with cols[3]:
        st.metric(
            "未讀通知" if lang == "zh" else "Unread",
            unread,
        )


def _render_smart_suggestions(user_id: str, lang: str) -> None:
    """Render top 3 contextual suggestions."""
    try:
        from smart_routing import render_suggestions
        render_suggestions(user_id, lang=lang, limit=3)
    except ImportError:
        st.info(
            "智慧建議模組未載入" if lang == "zh"
            else "Smart routing not loaded"
        )


def _render_workflow_starters(user_id: str, lang: str) -> None:
    """Buttons to start preset workflows."""
    cols = st.columns(3)

    flows = [
        ("daily_session", "🏃", "每日訓練", "Daily Session",
         "熱身 → 訓練 → 紀錄 → 領獎勵",
         "Warm-up → Train → Log → Rewards"),
        ("recovery_check", "🔍", "復原檢查", "Recovery Check",
         "生命徵象 → 疼痛 → 睡眠 → 分析",
         "Vitals → Pain → Sleep → Analytics"),
        ("onboarding", "✨", "新手引導", "Onboarding",
         "完善資料、目標、首次訓練",
         "Profile, goals, first session"),
    ]

    try:
        from workflow import start_workflow, advance_workflow
        from app_state import goto

        for i, (key, icon, zh, en, desc_zh, desc_en) in enumerate(flows):
            with cols[i]:
                with st.container(border=True):
                    title = zh if lang == "zh" else en
                    desc = desc_zh if lang == "zh" else desc_en
                    st.markdown(f"### {icon} {title}")
                    st.caption(desc)
                    if st.button(
                        "▶ " + ("開始" if lang == "zh" else "Start"),
                        key=f"flow_{key}",
                        use_container_width=True,
                        type="primary",
                    ):
                        if start_workflow(user_id, key):
                            step = advance_workflow(user_id)
                            if step:
                                goto(step.route)
                                st.rerun()
    except ImportError:
        st.info(
            "工作流模組未載入" if lang == "zh"
            else "Workflow module not loaded"
        )


def _render_quick_links(lang: str) -> None:
    """Quick navigation links to popular features."""
    from app_state import goto

    links = [
        ("auto_exercise", "🤖", "AI 自動分析", "Auto Analysis"),
        ("live_enhanced", "✨", "即時教練", "Live Coach"),
        ("analytics", "📊", "分析", "Analytics"),
        ("games", "🎮", "遊戲", "Games"),
        ("ai_chat", "💬", "AI 對話", "AI Chat"),
        ("quests", "🎯", "任務", "Quests"),
    ]

    cols = st.columns(6)
    for i, (route, icon, zh, en) in enumerate(links):
        with cols[i]:
            label = zh if lang == "zh" else en
            if st.button(
                f"{icon}\n{label}",
                key=f"qlink_{route}",
                use_container_width=True,
            ):
                goto(route)


def _render_undo_indicator(user_id: str, lang: str) -> None:
    """Show undo toast if there's a recent action."""
    try:
        from undo_redo import render_undo_toast
        render_undo_toast(user_id, lang=lang)
    except ImportError:
        pass
