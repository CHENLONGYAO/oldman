"""
Train tab: all training-related entry points consolidated.

Layout:
1. Hero: "Today's recommended exercise"
2. Mode selector (3 large buttons): AI auto / Live coach / Custom
3. Programs (multi-week structured plans)
4. Demo videos
5. Games & quests (gamified training)
"""
from __future__ import annotations
from typing import List, Optional

import streamlit as st

from auth import get_session_user


def view_train():
    """Train tab landing."""
    user = get_session_user()
    if not user:
        from auth_views import show_auth_page
        show_auth_page()
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    _render_recommendation_hero(user_id, lang)
    _render_mode_selector(lang)
    _render_programs(lang)
    _render_demos_and_games(lang)


def _render_recommendation_hero(user_id: str, lang: str) -> None:
    """Show top recommended exercise based on history."""
    rec_exercise = None
    rec_reason = ""
    try:
        from ml_insights import recommend_exercises
        recs = recommend_exercises(user_id, top_k=1)
        if recs:
            rec_exercise = recs[0]["exercise"]
            reasons = recs[0].get("reasons", [])
            rec_reason = reasons[0] if reasons else ""
    except Exception:
        pass

    if not rec_exercise:
        zh = "今天適合練什麼？讓 AI 幫你決定"
        en = "What to train today? Let AI decide"
        st.markdown(
            f'''
            <div class="hero-card">
                <h2>🎯 {"今日推薦" if lang == "zh" else "Today's Pick"}</h2>
                <p>{zh if lang == "zh" else en}</p>
            </div>
            ''',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'''
        <div class="hero-card">
            <h2>🎯 {rec_exercise}</h2>
            <p>{rec_reason}</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if st.button(
        "🚀 " + ("立即開始" if lang == "zh" else "Start Now"),
        key="train_start_rec",
        type="primary",
        use_container_width=True,
    ):
        from app_state import goto
        st.session_state.exercise_key = rec_exercise
        goto("live_enhanced")


def _render_mode_selector(lang: str) -> None:
    """Three primary training modes."""
    st.markdown(
        f'<div class="section-hdr">'
        f'{"訓練模式" if lang == "zh" else "MODE"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    modes = [
        {
            "icon": "🤖",
            "title_zh": "AI 自動分析",
            "title_en": "AI Auto Analysis",
            "desc_zh": "上傳影片，AI 全自動偵測動作、計次、評估",
            "desc_en": "Upload, AI auto-detects, counts, scores",
            "route": "auto_exercise",
            "color": "#007aff",
        },
        {
            "icon": "✨",
            "title_zh": "即時教練",
            "title_en": "Live Coach",
            "desc_zh": "鏡頭即時指導，邊做邊獲得回饋",
            "desc_en": "Real-time camera guidance + feedback",
            "route": "live_enhanced",
            "color": "#5856d6",
        },
        {
            "icon": "🎬",
            "title_zh": "傳統錄影",
            "title_en": "Classic Record",
            "desc_zh": "選擇動作後錄影或上傳",
            "desc_en": "Pick an exercise, then record/upload",
            "route": "record",
            "color": "#34c759",
        },
    ]

    for mode in modes:
        title = mode["title_zh"] if lang == "zh" else mode["title_en"]
        desc = mode["desc_zh"] if lang == "zh" else mode["desc_en"]
        with st.container(border=True):
            cols = st.columns([1, 5])
            with cols[0]:
                st.markdown(
                    f"<div style='font-size:36px;text-align:center'>"
                    f"{mode['icon']}</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(f"### {title}")
                st.caption(desc)
                if st.button(
                    "▶ " + ("開始" if lang == "zh" else "Open"),
                    key=f"mode_{mode['route']}",
                    use_container_width=True,
                    type="primary",
                ):
                    from app_state import goto
                    goto(mode["route"])


def _render_programs(lang: str) -> None:
    """Structured programs."""
    try:
        import programs
    except ImportError:
        return

    st.markdown(
        f'<div class="section-hdr">'
        f'{"復健計畫" if lang == "zh" else "PROGRAMS"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(
            "📋 " + ("結構化多週訓練" if lang == "zh"
                     else "Structured Multi-Week Plans")
        )
        st.caption(
            "膝關節、肩膀、平衡專屬計畫"
            if lang == "zh"
            else "Knee, shoulder, balance specialized programs"
        )
        if st.button(
            "查看所有計畫" if lang == "zh" else "View All Plans",
            key="train_programs",
            use_container_width=True,
        ):
            from app_state import goto
            goto("programs")


def _render_demos_and_games(lang: str) -> None:
    """Demo videos and gamified training."""
    st.markdown(
        f'<div class="section-hdr">'
        f'{"探索更多" if lang == "zh" else "EXPLORE"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    items = [
        {
            "icon": "🎬",
            "title_zh": "動作示範影片",
            "title_en": "Demo Videos",
            "sub_zh": "AI 生成的動作教學",
            "sub_en": "AI-generated tutorials",
            "route": "ai_demos",
        },
        {
            "icon": "🎮",
            "title_zh": "復健遊戲",
            "title_en": "Rehab Games",
            "sub_zh": "邊玩邊練：反應、平衡、節奏",
            "sub_en": "Play to train: reaction, balance, rhythm",
            "route": "games",
        },
        {
            "icon": "🎯",
            "title_zh": "任務挑戰",
            "title_en": "Quest Challenges",
            "sub_zh": "每日/每週任務 + XP 獎勵",
            "sub_en": "Daily/weekly + XP rewards",
            "route": "quests",
        },
        {
            "icon": "🎬",
            "title_zh": "錄製範本",
            "title_en": "Record Template",
            "sub_zh": "讓治療師錄製專屬範本",
            "sub_en": "Therapist records custom templates",
            "route": "custom",
        },
    ]

    cols = st.columns(2)
    for i, item in enumerate(items):
        with cols[i % 2]:
            title = item["title_zh"] if lang == "zh" else item["title_en"]
            sub = item["sub_zh"] if lang == "zh" else item["sub_en"]
            with st.container(border=True):
                st.markdown(f"### {item['icon']} {title}")
                st.caption(sub)
                if st.button(
                    "→",
                    key=f"explore_{item['route']}",
                    use_container_width=True,
                ):
                    from app_state import goto
                    goto(item["route"])
