"""
Home tab: daily routine + smart actions + glanceable status.

Mobile-first layout:
1. Hero greeting card with today's status
2. Stat chips (sessions, streak, XP, score)
3. Smart suggestion (top-1 only on mobile)
4. Quick start cards (3 primary actions)
5. Active workflow if any
6. Today's plan checklist
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Dict, Optional

import streamlit as st

import ui
from auth import get_session_user


def view_home():
    """4-tab Home landing page."""
    user = get_session_user()
    if not user:
        from auth_views import show_auth_page
        show_auth_page()
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]
    name = user.get("username") or user.get("name") or ""

    _render_hero(name, lang, user_id)

    with ui.app_section(
        "今日狀態" if lang == "zh" else "Today",
        icon="📊",
    ):
        _render_stat_chips(user_id, lang)

    _render_active_workflow(user_id, lang)

    with ui.app_section(
        "下一步建議" if lang == "zh" else "Next Best Action",
        icon="✨",
    ):
        _render_top_suggestion(user_id, lang)

    with ui.app_section(
        "快速開始" if lang == "zh" else "Quick Start",
        icon="🚀",
    ):
        _render_quick_actions(lang)

    with ui.app_section(
        "今日計畫" if lang == "zh" else "Today's Plan",
        icon="📋",
    ):
        _render_today_plan(user_id, lang)

    with ui.app_section(
        "最近活動" if lang == "zh" else "Recent Activity",
        icon="🕒",
    ):
        _render_recent_activity(user_id, lang)


def _render_hero(name: str, lang: str, user_id: str) -> None:
    """Greeting hero card."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        greet_zh, greet_en = "早安", "Good morning"
    elif 12 <= hour < 18:
        greet_zh, greet_en = "午安", "Good afternoon"
    else:
        greet_zh, greet_en = "晚安", "Good evening"

    today_zh = date.today().strftime("%m月%d日")
    today_en = date.today().strftime("%b %d")

    sub_zh = "今天又是進步的好日子 ✨"
    sub_en = "Another good day to grow ✨"

    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM sessions
            WHERE user_id = ? AND DATE(created_at) = ?
            """,
            (user_id, date.today().isoformat()),
        )
        if rows and rows[0]["c"] > 0:
            sub_zh = f"今天已完成 {rows[0]['c']} 次訓練 💪"
            sub_en = f"{rows[0]['c']} session(s) done today 💪"
    except Exception:
        pass

    st.markdown(
        f'''
        <div class="hero-card">
            <h2>{greet_zh if lang == "zh" else greet_en}, {name}!</h2>
            <p>{today_zh if lang == "zh" else today_en} — {sub_zh if lang == "zh" else sub_en}</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def _render_stat_chips(user_id: str, lang: str) -> None:
    """Horizontally scrollable stat chips."""
    today = date.today().isoformat()

    today_count = 0
    avg_score = 0.0
    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT COUNT(*) as c, AVG(score) as a FROM sessions
            WHERE user_id = ? AND DATE(created_at) = ?
            """,
            (user_id, today),
        )
        if rows:
            today_count = rows[0]["c"] or 0
            avg_score = float(rows[0]["a"] or 0)
    except Exception:
        pass

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

    chips = [
        ("📊", str(today_count), "今日訓練" if lang == "zh" else "Today"),
        ("🔥", f"{streak}", ("連續天數" if lang == "zh" else "Streak")),
        ("⭐", f"{avg_score:.0f}", ("今日平均" if lang == "zh" else "Avg")),
        ("🎯", str(quest_xp), ("任務 XP" if lang == "zh" else "Quest XP")),
    ]

    chips_html = '<div class="stat-chips">'
    for icon, num, lbl in chips:
        chips_html += f'''
            <div class="stat-chip">
                <div class="num">{icon} {num}</div>
                <div class="lbl">{lbl}</div>
            </div>
        '''
    chips_html += '</div>'
    st.markdown(chips_html, unsafe_allow_html=True)


def _render_active_workflow(user_id: str, lang: str) -> None:
    try:
        from workflow import render_workflow_indicator
        render_workflow_indicator()
    except ImportError:
        pass


def _render_top_suggestion(user_id: str, lang: str) -> None:
    """One prominent next-best-action card."""
    try:
        from smart_routing import get_suggestions
        suggestions = get_suggestions(user_id, lang=lang, limit=1)
    except ImportError:
        suggestions = []

    if not suggestions:
        return

    s = suggestions[0]
    title = s.title_zh if lang == "zh" else s.title_en
    reason = s.reason_zh if lang == "zh" else s.reason_en
    cta = s.cta_zh if lang == "zh" else s.cta_en

    with st.container(border=True):
        col_a, col_b = st.columns([4, 1])
        with col_a:
            st.markdown(f"### {s.icon} {title}")
            st.caption(reason)
        with col_b:
            if st.button(cta, key=f"home_sugg_{s.route}",
                         use_container_width=True, type="primary"):
                from app_state import goto
                goto(s.route)


def _render_quick_actions(lang: str) -> None:
    """Three primary actions in a 3-column grid."""
    actions = [
        ("auto_exercise", "🤖", "AI 分析", "AI Analysis"),
        ("live_enhanced", "✨", "即時教練", "Live Coach"),
        ("ai_chat", "💬", "問 AI", "Ask AI"),
    ]

    cols = st.columns(3)
    for i, (route, icon, zh, en) in enumerate(actions):
        with cols[i]:
            label = zh if lang == "zh" else en
            if st.button(
                f"{icon}\n{label}",
                key=f"home_qa_{route}",
                use_container_width=True,
            ):
                from app_state import goto
                goto(route)


def _render_today_plan(user_id: str, lang: str) -> None:
    """Today's plan: training, logging, and quest checklist."""
    today = date.today().isoformat()
    items = []

    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM sessions
            WHERE user_id = ? AND DATE(created_at) = ?
            """,
            (user_id, today),
        )
        sessions_today = rows[0]["c"] if rows else 0
        items.append({
            "icon": "🎬",
            "title": "完成 1 次訓練" if lang == "zh"
                     else "Complete 1 session",
            "done": sessions_today > 0,
            "route": "auto_exercise",
        })
    except Exception:
        pass

    try:
        from quests import get_active_quests
        quests = get_active_quests(user_id, lang)
        daily = [q for q in quests if q["type"] == "daily"][:3]
        for q in daily:
            items.append({
                "icon": q["icon"],
                "title": q["name"],
                "done": q["completed"],
                "route": "quests",
            })
    except Exception:
        pass

    for item in items:
        check = "✅" if item["done"] else "⬜"
        with st.container(border=True):
            cols = st.columns([1, 5, 1])
            with cols[0]:
                st.markdown(f"### {check}")
            with cols[1]:
                st.markdown(f"{item['icon']} {item['title']}")
            with cols[2]:
                if not item["done"]:
                    if st.button(
                        "→",
                        key=f"plan_{item['title'][:20]}",
                    ):
                        from app_state import goto
                        goto(item["route"])


def _render_recent_activity(user_id: str, lang: str) -> None:
    """Last 3 sessions with auto-summary."""
    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT exercise, score, created_at, session_id FROM sessions
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 3
            """,
            (user_id,),
        )
    except Exception:
        return

    if not rows:
        st.caption(
            "尚無活動紀錄" if lang == "zh" else "No activity yet"
        )
        return

    for row in rows:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{row['exercise']}**")
                st.caption(str(row["created_at"])[:16])
            with c2:
                score = row["score"] or 0
                color = "#34c759" if score >= 80 else "#ffcc00" if score >= 60 else "#ff3b30"
                st.markdown(
                    f"<div style='font-size:24px;font-weight:700;color:{color};text-align:right'>"
                    f"{score:.0f}</div>",
                    unsafe_allow_html=True,
                )
