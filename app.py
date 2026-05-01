"""
智慧居家復健評估系統 — 入口檔。

整體架構：
    app.py        : 路由分派 + 側欄 + main()
    app_state.py  : 全域狀態、設定、難度、快取資源、語音、徽章 toast
    pipeline.py   : 完整評分流程（DTW + 神經評分 + 儲存）
    views.py      : 所有畫面（welcome / profile / home / ... / settings）
    ui.py         : 蘋果風 CSS、卡片、Plotly 圖、卡通教練
    realtime.py   : streamlit-webrtc 即時鏡頭指導
    pipeline 之外的領域模組：scoring / pose_estimator / visualizer /
                              templates / history / report / tts / i18n /
                              motionagformer / neural_scorer / coach

執行：
    pip install -r requirements.txt
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

import history as hist
import ui
from app_state import goto, init_state, lang as get_lang, user_history_key
from auth import logout, get_session_user
from auth_views import show_auth_page
from db import init_db
from db_migrate import migrate_json_to_sqlite
from i18n import LANGS, language_label, t
from views import ROUTES, view_welcome


# ============================================================
# 頁面設定（必須在第一個 st.* 之前）
# ============================================================
st.set_page_config(
    page_title="智慧居家復健評估系統",
    page_icon="🏥",
    layout="wide",
)


# ============================================================
# 側欄
# ============================================================
_SIDEBAR_ITEMS: dict[str, tuple[str, str]] = {
    "welcome": ("step_welcome", "🏠"),
    "onboarding": ("step_onboarding", "✨"),
    "profile": ("step_profile", "👤"),
    "home": ("step_home", "🏠"),
    "daily_routine": ("step_daily_routine", "🌅"),
    "programs": ("step_programs", "📋"),
    "record": ("step_record", "🎥"),
    "live_enhanced": ("step_live_enhanced", "✨"),
    "auto_exercise": ("step_auto_exercise", "🤖"),
    "analyze": ("step_analyze", "🧠"),
    "result": ("step_result", "📊"),
    "progress": ("step_progress", "📈"),
    "pain_map": ("step_pain_map", "🗺️"),
    "journal": ("step_journal", "📝"),
    "vitals": ("step_vitals", "🌡️"),
    "medication": ("step_medication", "💊"),
    "calendar": ("step_calendar", "📅"),
    "reminders": ("step_reminders", "🔔"),
    "sync": ("step_sync", "🔄"),
    "custom": ("step_custom", "🎬"),
    "analytics": ("step_analytics", "📊"),
    "games": ("step_games", "🎮"),
    "wearables": ("step_wearables", "⌚"),
    "cloud_sync": ("step_cloud_sync", "☁️"),
    "ai_chat": ("step_ai_chat", "💬"),
    "quests": ("step_quests", "🎯"),
    "nutrition": ("step_nutrition", "🍎"),
    "sleep": ("step_sleep", "😴"),
    "notifications": ("step_notifications", "🔔"),
    "audit_log": ("step_audit_log", "📋"),
    "therapist_dashboard": ("step_therapist", "👥"),
    "clinician": ("step_clinician", "🩺"),
    "ai_media": ("step_ai_media", "🧑‍🏫"),
    "settings": ("step_settings", "⚙"),
}

_QUICK_NAV = ("daily_routine", "auto_exercise", "live_enhanced", "progress")

_SIDEBAR_GROUPS: list[tuple[str, str, tuple[str, ...]]] = [
    ("rehab", "復健訓練", ("programs", "record", "custom", "ai_media", "result")),
    (
        "health",
        "健康紀錄",
        ("journal", "pain_map", "vitals", "medication", "nutrition", "sleep"),
    ),
    (
        "schedule",
        "行程提醒",
        ("calendar", "reminders", "notifications", "quests", "games"),
    ),
    (
        "data",
        "資料與同步",
        ("wearables", "analytics", "sync", "cloud_sync", "ai_chat"),
    ),
    (
        "care",
        "專業與設定",
        ("therapist_dashboard", "clinician", "audit_log", "profile", "settings"),
    ),
]


def _render_user_card(u: dict, lang: str) -> None:
    initial = (u.get("name", "")[:1] or "?").upper()
    st.markdown(
        f'<div style="display:flex;align-items:center;'
        f'gap:.6rem;padding:.6rem;border-radius:12px;'
        f'background:white;margin-bottom:.5rem;">'
        f'<div style="width:38px;height:38px;border-radius:50%;'
        f'background:linear-gradient(135deg,#74b9ff,#00b894);'
        f'color:white;display:flex;align-items:center;'
        f'justify-content:center;font-weight:700;">'
        f'{initial}</div>'
        f'<div><div style="font-weight:600">'
        f'{u.get("name", "—")}</div>'
        f'<div style="font-size:.75rem;color:#636e72">'
        f'{t("age", lang)} {u.get("age", "—")}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _ensure_account_storage(u: dict) -> dict:
    """Make local JSON history account-scoped while SQLite remains primary."""
    if not u:
        return u
    key = user_history_key(u)
    u = dict(u)
    u["history_key"] = key
    hist.ensure_account_storage(
        key,
        profile=u,
        legacy_names=[
            u.get("name", ""),
            u.get("username", ""),
        ],
    )
    return u


def _render_nav_button(key: str, lang: str, *, prefix: str) -> None:
    label_key, icon = _SIDEBAR_ITEMS[key]
    cur = st.session_state.step == key
    enabled = _route_available(key)
    btn_type = "primary" if cur else "secondary"
    if st.button(
        f"{icon} {t(label_key, lang)}",
        key=f"{prefix}_{key}",
        use_container_width=True,
        type=btn_type,
        disabled=not enabled,
    ):
        goto(key)


def _render_flow_indicator(lang: str) -> None:
    st.caption("📍 " + ("常用入口" if lang == "zh" else "Quick actions"))
    quick_cols = st.columns(2)
    for i, key in enumerate(_QUICK_NAV):
        with quick_cols[i % 2]:
            _render_nav_button(key, lang, prefix="side_quick")

    st.caption("🧭 " + ("功能分類" if lang == "zh" else "Sections"))
    for group_key, group_zh, routes in _SIDEBAR_GROUPS:
        expanded = st.session_state.step in routes
        group_en = {
            "rehab": "Rehab",
            "health": "Health",
            "schedule": "Schedule",
            "data": "Data & Sync",
            "care": "Care & Settings",
        }.get(group_key, group_key)
        with st.expander(group_zh if lang == "zh" else group_en, expanded=expanded):
            for key in routes:
                _render_nav_button(key, lang, prefix=f"side_{group_key}")


def _route_available(step: str) -> bool:
    from roles import is_therapist, is_clinician
    u = bool(st.session_state.get("user"))
    if step in {
        "welcome", "onboarding", "profile", "settings",
    }:
        return True
    if step == "clinician":
        return is_clinician()
    if step == "therapist_dashboard":
        return is_therapist()
    if step == "audit_log":
        return is_therapist()
    if step in {"analytics", "ai_media"}:
        return u
    if step in {
        "home", "programs", "progress", "pain_map", "journal",
        "vitals", "medication", "calendar", "custom",
        "reminders", "sync",
        "analytics", "games", "wearables", "cloud_sync",
        "ai_chat", "quests", "nutrition", "sleep", "notifications",
        "live_enhanced", "auto_exercise", "daily_routine",
    }:
        return u
    if step == "record":
        return u and bool(st.session_state.get("exercise_key"))
    if step == "analyze":
        return (
            u
            and bool(st.session_state.get("exercise_key"))
            and bool(st.session_state.get("video_path"))
        )
    if step == "result":
        return bool(st.session_state.get("analysis"))
    if step == "audit_log":
        if not u:
            return False
        try:
            from roles import is_therapist
            return is_therapist(u.get("role", "patient"))
        except ImportError:
            return u.get("role") in ("admin", "therapist")
    return False


def _render_sidebar() -> None:
    lang = get_lang()
    with st.sidebar:
        st.markdown(f"### 🏥 {t('app_title', lang)}")

        u = st.session_state.user
        if u:
            _render_user_card(u, lang)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("👤 " + ("個人資料" if lang == "zh" else "Profile"),
                           use_container_width=True, key="sidebar_profile"):
                    goto("profile")
            with col2:
                if st.button("🚪 " + ("登出" if lang == "zh" else "Logout"),
                           use_container_width=True, key="sidebar_logout"):
                    logout()
                    st.rerun()

        new_lang = st.radio(
            t("language", lang),
            options=list(LANGS),
            format_func=language_label,
            index=list(LANGS).index(lang),
            horizontal=True,
            key="sidebar_lang",
        )
        if new_lang != lang:
            st.session_state.settings["lang"] = new_lang
            st.session_state.tts_engine = None
            st.rerun()

        st.divider()
        _render_flow_indicator(lang)

        try:
            from mobile_ui import render_mobile_toggle
            render_mobile_toggle()
        except ImportError:
            pass

        try:
            from theme import render_quick_theme_toggle
            render_quick_theme_toggle()
        except ImportError:
            pass

        try:
            from command_palette import render_palette_button
            render_palette_button()
        except ImportError:
            pass

        try:
            from voice_commands import (
                execute_command,
                parse_command,
                render_voice_button,
            )
            with st.expander("🎤 " + ("語音控制" if lang == "zh" else "Voice")):
                cmd_text = render_voice_button(lang=lang)
                if cmd_text and cmd_text != st.session_state.get("_last_voice_cmd"):
                    st.session_state["_last_voice_cmd"] = cmd_text
                    result = parse_command(cmd_text, lang=lang)
                    if result and result.matched:
                        execute_command(result)
                        st.toast(f"✓ {result.command}")
        except ImportError:
            pass

        if u:
            try:
                from notifications import get_unread_count
                unread = get_unread_count(u.get("user_id", ""))
                if unread > 0:
                    st.markdown(
                        f"🔔 **{unread}** "
                        f"{'未讀通知' if lang == 'zh' else 'unread'}"
                    )
            except ImportError:
                pass

        st.divider()
        if st.button("🏠 " + t("home", lang),
                     use_container_width=True):
            goto("home" if u else "welcome")


# ============================================================
# 主入口
# ============================================================
def main() -> None:
    # Initialize database on first run
    if "db_initialized" not in st.session_state:
        try:
            init_db()
            migrate_json_to_sqlite()
            st.session_state.db_initialized = True
        except Exception as e:
            st.error(f"資料庫初始化失敗: {e}")
            st.stop()

    init_state()
    ui.inject_css()

    try:
        from mobile_ui import inject_mobile_css
        inject_mobile_css()
    except ImportError:
        pass

    try:
        from theme import inject_theme_css
        inject_theme_css()
    except ImportError:
        pass

    # Check authentication
    user = get_session_user()
    if not user:
        # Show language selector in top right
        col1, col2 = st.columns([4, 1])
        with col2:
            current_lang = get_lang()
            lang = st.radio(
                t("language", current_lang),
                options=list(LANGS),
                format_func=language_label,
                index=list(LANGS).index(current_lang),
                horizontal=True,
                key="auth_lang",
                label_visibility="collapsed",
            )
            if lang != current_lang:
                st.session_state.settings["lang"] = lang
                st.rerun()

        show_auth_page()
        return

    # Authenticated user - show main app
    st.session_state.user = _ensure_account_storage(dict(user)) if user else None
    if st.session_state.get("step") == "welcome":
        st.session_state.step = "daily_routine"

    _render_sidebar()

    try:
        from workflow import render_workflow_indicator
        render_workflow_indicator()
    except ImportError:
        pass

    view_fn = ROUTES.get(st.session_state.step, view_welcome)
    try:
        from telemetry import measure, counter
        counter(f"page.{st.session_state.step}")
        with measure(f"render.{st.session_state.step}"):
            view_fn()
    except ImportError:
        view_fn()


if __name__ == "__main__":
    main()
