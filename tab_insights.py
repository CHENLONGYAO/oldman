"""
Insights tab: analytics + AI chat + health logs.

Layout:
1. Hero: AI summary card
2. Key metrics (4 KPIs)
3. AI chat shortcut
4. Health logs grid (journal/pain/vitals/sleep/nutrition)
5. Calendar & reminders
"""
from __future__ import annotations
from typing import List, Optional

import streamlit as st

from auth import get_session_user


def view_insights():
    """Insights tab landing."""
    user = get_session_user()
    if not user:
        from auth_views import show_auth_page
        show_auth_page()
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    _render_ai_summary_hero(user_id, lang)
    _render_kpi_grid(user_id, lang)
    _render_ai_chat_shortcut(lang)
    _render_full_analytics_link(lang)
    _render_progress_link(lang)
    _render_health_logs(lang)
    _render_schedule(lang)


def _render_ai_summary_hero(user_id: str, lang: str) -> None:
    """AI-generated 1-line summary of user's status."""
    summary_zh = "查看你的訓練進度與洞察"
    summary_en = "Track your progress and insights"

    try:
        from ml_insights import get_personalized_insights
        insights = get_personalized_insights(user_id)
        if insights:
            top = insights[0]
            summary_zh = f"{top['icon']} {top['msg_zh']}"
            summary_en = f"{top['icon']} {top['msg_en']}"
    except Exception:
        pass

    title = "你的洞察" if lang == "zh" else "Your Insights"
    msg = summary_zh if lang == "zh" else summary_en

    st.markdown(
        f'''
        <div class="hero-card">
            <h2>📊 {title}</h2>
            <p>{msg}</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def _render_kpi_grid(user_id: str, lang: str) -> None:
    """4 KPI cards in 2x2 grid."""
    improvement = {"current": 0, "rate": 0}
    adherence = {"adherence_pct": 0}
    risk = {"risk_score": 0, "level_zh": "—", "level": "—"}
    pain_trend = "—"

    try:
        from analytics import (
            calculate_improvement_rate, calculate_adherence,
            get_pain_trend,
        )
        from ml_insights import calculate_risk_score
        improvement = calculate_improvement_rate(user_id)
        adherence = calculate_adherence(user_id)
        risk = calculate_risk_score(user_id)
        pain = get_pain_trend(user_id)
        if pain.get("trend") == "improving":
            pain_trend = "📉 改善" if lang == "zh" else "📉 Improving"
        elif pain.get("trend") == "worsening":
            pain_trend = "📈 加劇" if lang == "zh" else "📈 Worsening"
        elif pain.get("samples", 0) > 0:
            pain_trend = "→ 穩定" if lang == "zh" else "→ Stable"
    except Exception:
        pass

    kpis = [
        {
            "icon": "📈",
            "title_zh": "進步率",
            "title_en": "Improvement",
            "value": f"{improvement.get('rate', 0):+.1f}%",
            "sub_zh": f"目前平均 {improvement.get('current', 0):.1f}",
            "sub_en": f"Avg {improvement.get('current', 0):.1f}",
        },
        {
            "icon": "🎯",
            "title_zh": "參與度",
            "title_en": "Adherence",
            "value": f"{adherence.get('adherence_pct', 0):.0f}%",
            "sub_zh": "近 4 週",
            "sub_en": "Last 4 weeks",
        },
        {
            "icon": "⚠️",
            "title_zh": "風險評分",
            "title_en": "Risk",
            "value": f"{risk.get('risk_score', 0)}",
            "sub_zh": risk.get("level_zh", "—"),
            "sub_en": risk.get("level", "—"),
        },
        {
            "icon": "🩹",
            "title_zh": "疼痛趨勢",
            "title_en": "Pain Trend",
            "value": pain_trend,
            "sub_zh": "",
            "sub_en": "",
        },
    ]

    cols = st.columns(2)
    for i, kpi in enumerate(kpis):
        with cols[i % 2]:
            title = kpi["title_zh"] if lang == "zh" else kpi["title_en"]
            sub = kpi["sub_zh"] if lang == "zh" else kpi["sub_en"]
            with st.container(border=True):
                st.markdown(f"### {kpi['icon']} {title}")
                st.markdown(
                    f"<div style='font-size:28px;font-weight:700;color:#1c1c1e'>"
                    f"{kpi['value']}</div>",
                    unsafe_allow_html=True,
                )
                if sub:
                    st.caption(sub)


def _render_ai_chat_shortcut(lang: str) -> None:
    """Prominent AI chat entry."""
    st.markdown("")
    with st.container(border=True):
        cols = st.columns([1, 4, 2])
        with cols[0]:
            st.markdown(
                "<div style='font-size:36px;text-align:center'>💬</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown(
                "**" + ("問 AI 教練" if lang == "zh"
                        else "Ask AI Coach") + "**"
            )
            st.caption(
                "關於分數、姿勢、疼痛的任何問題"
                if lang == "zh"
                else "Any question about score, form, pain"
            )
        with cols[2]:
            if st.button(
                "→ " + ("對話" if lang == "zh" else "Chat"),
                key="insights_ai_chat",
                use_container_width=True,
                type="primary",
            ):
                from app_state import goto
                goto("ai_chat")


def _render_full_analytics_link(lang: str) -> None:
    if st.button(
        "📊 " + ("查看完整分析儀表板" if lang == "zh"
                 else "Open Full Analytics Dashboard"),
        key="insights_full",
        use_container_width=True,
    ):
        from app_state import goto
        goto("analytics")


def _render_progress_link(lang: str) -> None:
    if st.button(
        "📈 " + ("分數趨勢與徽章" if lang == "zh"
                 else "Score Trends & Badges"),
        key="insights_progress",
        use_container_width=True,
    ):
        from app_state import goto
        goto("progress")


def _render_health_logs(lang: str) -> None:
    """Grid of health-tracking entry points."""
    st.markdown(
        f'<div class="section-hdr">'
        f'{"健康紀錄" if lang == "zh" else "HEALTH LOGS"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    logs = [
        ("journal", "📝", "心情日記", "Journal"),
        ("pain_map", "🗺️", "疼痛地圖", "Pain Map"),
        ("vitals", "🌡️", "生命徵象", "Vitals"),
        ("sleep", "😴", "睡眠", "Sleep"),
        ("nutrition", "🍎", "營養", "Nutrition"),
        ("medication", "💊", "藥物", "Meds"),
    ]

    cols = st.columns(3)
    for i, (route, icon, zh, en) in enumerate(logs):
        with cols[i % 3]:
            label = zh if lang == "zh" else en
            if st.button(
                f"{icon}\n{label}",
                key=f"insights_log_{route}",
                use_container_width=True,
            ):
                from app_state import goto
                goto(route)


def _render_schedule(lang: str) -> None:
    """Calendar / reminders."""
    st.markdown(
        f'<div class="section-hdr">'
        f'{"排程" if lang == "zh" else "SCHEDULE"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(2)
    with cols[0]:
        if st.button(
            "📅\n" + ("行事曆" if lang == "zh" else "Calendar"),
            key="insights_cal",
            use_container_width=True,
        ):
            from app_state import goto
            goto("calendar")
    with cols[1]:
        if st.button(
            "🔔\n" + ("提醒" if lang == "zh" else "Reminders"),
            key="insights_rem",
            use_container_width=True,
        ):
            from app_state import goto
            goto("reminders")
