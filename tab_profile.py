"""
Profile / Me tab: settings + everything else (drawer-style "More" menu).

iOS-style list rows grouped into sections:
1. User card with avatar
2. Account: profile, notifications
3. Devices & Data: wearables, cloud sync, sync status
4. Care: therapist, clinician, audit
5. Settings: theme, language, voice, difficulty
6. About: version, logout
"""
from __future__ import annotations
from typing import Callable, Dict, List, Optional, Tuple

import streamlit as st

from auth import get_session_user, logout


def view_profile():
    """Profile tab landing — settings drawer."""
    user = get_session_user()
    if not user:
        from auth_views import show_auth_page
        show_auth_page()
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")

    _render_user_card(user, lang)
    _render_account_section(lang)
    _render_devices_section(lang)
    _render_care_section(user, lang)
    _render_settings_section(lang)
    _render_about_section(lang)


def _render_user_card(user: Dict, lang: str) -> None:
    """Avatar + name + role card."""
    name = user.get("username") or user.get("name") or ""
    role = user.get("role", "patient")
    initial = (name[:1] or "?").upper()

    role_label = {
        "patient": "病人" if lang == "zh" else "Patient",
        "therapist": "治療師" if lang == "zh" else "Therapist",
        "clinician": "醫師" if lang == "zh" else "Clinician",
        "admin": "管理員" if lang == "zh" else "Admin",
    }.get(role, role)

    st.markdown(
        f'''
        <div class="hero-card" style="display:flex;align-items:center;gap:16px;">
            <div style="width:64px;height:64px;border-radius:50%;
                       background:white;color:#007aff;
                       display:flex;align-items:center;justify-content:center;
                       font-weight:700;font-size:28px;">
                {initial}
            </div>
            <div>
                <h2 style="margin:0">{name}</h2>
                <p style="margin:0;opacity:0.85">{role_label}</p>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if st.button(
        "👤 " + ("編輯個人資料" if lang == "zh" else "Edit Profile"),
        key="prof_edit",
        use_container_width=True,
    ):
        from app_state import goto
        goto("profile")


def _list_item(icon: str, title: str, sub: str, route: str,
                key: str, badge: Optional[str] = None) -> None:
    """One iOS-style list row."""
    with st.container(border=True):
        cols = st.columns([1, 5, 1])
        with cols[0]:
            st.markdown(
                f"<div style='font-size:22px'>{icon}</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            badge_html = (
                f"<span style='background:#ff3b30;color:white;border-radius:8px;"
                f"padding:1px 6px;font-size:11px;margin-left:8px;'>{badge}</span>"
                if badge else ""
            )
            st.markdown(
                f"**{title}** {badge_html}",
                unsafe_allow_html=True,
            )
            if sub:
                st.caption(sub)
        with cols[2]:
            if st.button("›", key=key):
                from app_state import goto
                goto(route)


def _render_account_section(lang: str) -> None:
    st.markdown(
        f'<div class="section-hdr">'
        f'{"帳戶" if lang == "zh" else "ACCOUNT"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    user = get_session_user() or {}
    user_id = user.get("user_id")

    unread_badge = None
    try:
        if user_id:
            from notifications import get_unread_count
            n = get_unread_count(user_id)
            if n > 0:
                unread_badge = str(n)
    except Exception:
        pass

    _list_item(
        "🔔",
        "通知中心" if lang == "zh" else "Notifications",
        "新訊息與提醒" if lang == "zh" else "Messages and alerts",
        "notifications", "prof_notif",
        badge=unread_badge,
    )


def _render_devices_section(lang: str) -> None:
    st.markdown(
        f'<div class="section-hdr">'
        f'{"裝置與資料" if lang == "zh" else "DEVICES & DATA"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    _list_item(
        "⌚",
        "穿戴裝置" if lang == "zh" else "Wearables",
        "Apple Health、Fitbit、Google Fit"
        if lang == "zh" else "Apple Health, Fitbit, Google Fit",
        "wearables", "prof_wear",
    )

    _list_item(
        "☁️",
        "雲端備份" if lang == "zh" else "Cloud Backup",
        "加密備份與還原" if lang == "zh" else "Encrypted backup & restore",
        "cloud_sync", "prof_cloud",
    )

    _list_item(
        "🔄",
        "多裝置同步" if lang == "zh" else "Multi-Device Sync",
        "" if lang == "zh" else "",
        "sync", "prof_sync",
    )


def _render_care_section(user: Dict, lang: str) -> None:
    role = user.get("role", "patient")

    if role not in ("therapist", "clinician", "admin"):
        return

    st.markdown(
        f'<div class="section-hdr">'
        f'{"專業工具" if lang == "zh" else "PROFESSIONAL"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    _list_item(
        "👥",
        "治療師儀表板" if lang == "zh" else "Therapist Dashboard",
        "管理多位病人" if lang == "zh" else "Manage patients",
        "therapist_dashboard", "prof_therap",
    )

    _list_item(
        "🩺",
        "臨床總覽" if lang == "zh" else "Clinician View",
        "全機構統計" if lang == "zh" else "Org-wide stats",
        "clinician", "prof_clin",
    )

    _list_item(
        "📋",
        "稽核日誌" if lang == "zh" else "Audit Log",
        "HIPAA 合規記錄" if lang == "zh" else "HIPAA records",
        "audit_log", "prof_audit",
    )


def _render_settings_section(lang: str) -> None:
    st.markdown(
        f'<div class="section-hdr">'
        f'{"設定" if lang == "zh" else "SETTINGS"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    _list_item(
        "⚙️",
        "所有設定" if lang == "zh" else "All Settings",
        "難度、語音、教練角色"
        if lang == "zh" else "Difficulty, voice, coach",
        "settings", "prof_settings",
    )

    try:
        from theme import get_current_theme, THEMES, set_theme
        cur = get_current_theme()
        cur_theme = THEMES.get(cur, THEMES["light"])
        with st.container(border=True):
            cols = st.columns([1, 5, 2])
            with cols[0]:
                st.markdown(
                    f"<div style='font-size:22px'>{cur_theme['icon']}</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(f"**{'主題' if lang == 'zh' else 'Theme'}**")
                st.caption(
                    cur_theme["name_zh"] if lang == "zh"
                    else cur_theme["name_en"]
                )
            with cols[2]:
                next_theme = "dark" if cur == "light" else "light"
                if st.button(
                    "切換" if lang == "zh" else "Toggle",
                    key="prof_theme_toggle",
                    use_container_width=True,
                ):
                    set_theme(next_theme)
                    st.rerun()
    except ImportError:
        pass

    try:
        s = st.session_state.get("settings", {})
        cur_lang = s.get("lang", "zh")
        with st.container(border=True):
            cols = st.columns([1, 5, 2])
            with cols[0]:
                st.markdown(
                    "<div style='font-size:22px'>🌐</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(
                    f"**{'語言' if lang == 'zh' else 'Language'}**"
                )
                st.caption("中文" if cur_lang == "zh" else "English")
            with cols[2]:
                next_lang = "en" if cur_lang == "zh" else "zh"
                next_label = "EN" if cur_lang == "zh" else "中"
                if st.button(
                    next_label,
                    key="prof_lang_toggle",
                    use_container_width=True,
                ):
                    s["lang"] = next_lang
                    st.session_state.tts_engine = None
                    st.rerun()
    except Exception:
        pass


def _render_about_section(lang: str) -> None:
    st.markdown(
        f'<div class="section-hdr">'
        f'{"關於" if lang == "zh" else "ABOUT"}'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.caption("智慧居家復健評估系統 v2.0"
                  if lang == "zh"
                  else "Smart Rehab v2.0")
        st.caption(
            "AI × DTW × 個人化復健"
            if lang == "zh"
            else "AI × DTW × Personalized Rehab"
        )

    if st.button(
        "🚪 " + ("登出" if lang == "zh" else "Sign Out"),
        key="prof_logout",
        use_container_width=True,
        type="secondary",
    ):
        logout()
        st.rerun()
