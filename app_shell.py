"""
Mobile-first app shell: 4-tab bottom navigation + header + FAB.

Design follows iOS / Android patterns:
- 4 primary tabs: Home / Train / Insights / Profile
- Top header: greeting + bell icon + theme toggle
- Floating Action Button (FAB) at bottom-right for quick exercise launch
- All ~30 legacy routes are reachable from inside one of the 4 tabs

Each tab is a curated landing view, NOT a flat menu of every feature.
The 4 tabs aggregate related features so users discover them by context.

State machine:
- st.session_state.active_tab: "home" | "train" | "insights" | "profile"
- st.session_state.step: legacy route, used only when a sub-page is opened
- When a sub-page is rendered, the tab bar still shows; tapping a tab
  resets st.session_state.step to None and renders the tab landing.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import streamlit as st


@dataclass
class Tab:
    key: str
    icon: str
    label_zh: str
    label_en: str
    routes: Tuple[str, ...]  # legacy routes that belong to this tab
    landing: str             # default route when tab is tapped


PRIMARY_TABS: List[Tab] = [
    Tab(
        key="home",
        icon="🏠",
        label_zh="首頁",
        label_en="Home",
        routes=("daily_routine", "welcome", "onboarding", "home"),
        landing="daily_routine",
    ),
    Tab(
        key="train",
        icon="🏃",
        label_zh="訓練",
        label_en="Train",
        routes=(
            "auto_exercise", "live_enhanced", "record", "analyze",
            "result", "programs", "ai_demos", "custom", "ai_media",
            "games", "quests",
        ),
        landing="train_hub",
    ),
    Tab(
        key="insights",
        icon="📊",
        label_zh="洞察",
        label_en="Insights",
        routes=(
            "analytics", "progress", "ai_chat", "journal",
            "pain_map", "vitals", "sleep", "nutrition",
            "medication", "calendar", "reminders",
        ),
        landing="insights_hub",
    ),
    Tab(
        key="profile",
        icon="👤",
        label_zh="我",
        label_en="Me",
        routes=(
            "profile", "settings", "notifications",
            "wearables", "cloud_sync", "sync",
            "therapist_dashboard", "clinician",
            "audit_log",
        ),
        landing="profile_hub",
    ),
]


# ============================================================
# Tab routing
# ============================================================
def get_active_tab() -> Tab:
    """Determine current active tab from session step."""
    step = st.session_state.get("step", "")
    explicit = st.session_state.get("active_tab")

    if explicit:
        for tab in PRIMARY_TABS:
            if tab.key == explicit:
                return tab

    for tab in PRIMARY_TABS:
        if step in tab.routes:
            return tab

    return PRIMARY_TABS[0]


def goto_tab(tab_key: str) -> None:
    """Switch to a tab and load its landing route."""
    from app_state import goto

    for tab in PRIMARY_TABS:
        if tab.key == tab_key:
            st.session_state.active_tab = tab_key
            goto(tab.landing)
            return


# ============================================================
# Mobile-first CSS
# ============================================================
MOBILE_SHELL_CSS = """
<style>
/* Hide Streamlit default chrome on mobile */
@media (max-width: 900px) {
    [data-testid="stHeader"],
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    .block-container {
        padding-top: 4.5rem !important;
        padding-bottom: 5.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
}

/* Sticky top header */
.app-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 56px;
    background: rgba(255, 255, 255, 0.92);
    backdrop-filter: saturate(180%) blur(20px);
    -webkit-backdrop-filter: saturate(180%) blur(20px);
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
}
.app-header .title {
    font-weight: 600;
    font-size: 17px;
    color: #1c1c1e;
}
.app-header .actions {
    display: flex;
    gap: 12px;
    font-size: 22px;
}

/* Bottom tab bar */
.bottom-tabs {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 64px;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: saturate(180%) blur(24px);
    -webkit-backdrop-filter: saturate(180%) blur(24px);
    border-top: 1px solid rgba(0, 0, 0, 0.08);
    z-index: 1000;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    padding-bottom: env(safe-area-inset-bottom);
}
.bottom-tabs .tab {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    color: #8e8e93;
    text-decoration: none;
    font-size: 11px;
    transition: color 0.15s ease;
    cursor: pointer;
}
.bottom-tabs .tab .icon { font-size: 22px; }
.bottom-tabs .tab.active { color: #007aff; font-weight: 600; }

/* FAB */
.fab {
    position: fixed;
    right: 16px;
    bottom: 80px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: linear-gradient(135deg, #007aff, #5e8efc);
    color: white;
    box-shadow: 0 8px 24px rgba(0, 122, 255, 0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    z-index: 999;
    cursor: pointer;
    transition: transform 0.15s ease;
}
.fab:hover { transform: scale(1.05); }
.fab:active { transform: scale(0.95); }

/* Card design */
.app-card {
    background: white;
    border-radius: 14px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    border: 1px solid rgba(0,0,0,0.04);
    margin-bottom: 12px;
}
.app-card-title {
    font-weight: 600;
    font-size: 16px;
    color: #1c1c1e;
    margin-bottom: 4px;
}
.app-card-sub {
    color: #8e8e93;
    font-size: 13px;
}

/* List rows (settings-style) */
.list-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    background: white;
    border-bottom: 1px solid rgba(0,0,0,0.04);
}
.list-row:first-child { border-top-left-radius: 12px; border-top-right-radius: 12px; }
.list-row:last-child {
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
    border-bottom: none;
}
.list-row .icon {
    width: 32px; height: 32px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
}
.list-row .text { flex: 1; }
.list-row .text .title { font-size: 15px; color: #1c1c1e; }
.list-row .text .sub { font-size: 12px; color: #8e8e93; }
.list-row .chevron { color: #c7c7cc; font-size: 16px; }

/* Section header */
.section-hdr {
    text-transform: uppercase;
    color: #8e8e93;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin: 24px 4px 8px;
}

/* Gradient hero card */
.hero-card {
    background: linear-gradient(135deg, #007aff 0%, #5e8efc 100%);
    color: white;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
}
.hero-card h2 { color: white; margin: 0 0 6px; font-size: 22px; }
.hero-card p { color: rgba(255,255,255,0.9); margin: 0; }

/* Stat chips horizontal */
.stat-chips {
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding: 4px 0 12px;
    scrollbar-width: none;
}
.stat-chips::-webkit-scrollbar { display: none; }
.stat-chip {
    flex: 0 0 auto;
    background: white;
    border-radius: 12px;
    padding: 12px 14px;
    min-width: 110px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.stat-chip .num { font-size: 22px; font-weight: 700; color: #1c1c1e; }
.stat-chip .lbl { font-size: 12px; color: #8e8e93; margin-top: 2px; }

/* Streamlit button override on mobile */
@media (max-width: 900px) {
    .stButton > button {
        border-radius: 12px !important;
        font-weight: 500 !important;
        padding: 12px 16px !important;
        min-height: 48px !important;
    }
    div[data-testid="column"] { padding: 0 4px !important; }
}

/* Dark theme adjustments */
[data-theme="dark"] .app-header {
    background: rgba(28, 28, 30, 0.92);
    border-bottom-color: rgba(255,255,255,0.08);
}
[data-theme="dark"] .app-header .title { color: #e8e8e8; }
[data-theme="dark"] .bottom-tabs {
    background: rgba(28, 28, 30, 0.95);
    border-top-color: rgba(255,255,255,0.08);
}
[data-theme="dark"] .app-card,
[data-theme="dark"] .list-row,
[data-theme="dark"] .stat-chip {
    background: #2c2c2e;
    border-color: rgba(255,255,255,0.04);
}
[data-theme="dark"] .app-card-title,
[data-theme="dark"] .list-row .text .title,
[data-theme="dark"] .stat-chip .num { color: #e8e8e8; }
</style>
"""


def inject_shell_css() -> None:
    """Inject mobile shell CSS."""
    st.markdown(MOBILE_SHELL_CSS, unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================
def render_header(lang: str = "zh") -> None:
    """Top header with greeting and quick actions."""
    user = st.session_state.get("user", {})
    name = user.get("name") if isinstance(user, dict) else ""

    title = name or ("智慧復健" if lang == "zh" else "Smart Rehab")

    unread = 0
    try:
        if user and user.get("user_id"):
            from notifications import get_unread_count
            unread = get_unread_count(user["user_id"])
    except Exception:
        pass

    bell_badge = f'<span style="position:absolute;top:-4px;right:-4px;background:#ff3b30;color:white;border-radius:8px;font-size:10px;padding:1px 5px;font-weight:600;">{unread}</span>' if unread > 0 else ""

    st.markdown(
        f'''
        <div class="app-header">
            <div class="title">👋 {title}</div>
            <div class="actions">
                <span style="position:relative;">🔔{bell_badge}</span>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


# ============================================================
# Bottom tab bar
# ============================================================
def render_bottom_tabs(lang: str = "zh") -> None:
    """Render bottom 4-tab nav. Uses Streamlit columns for tap targets."""
    active = get_active_tab()

    st.markdown(
        '<div class="bottom-tabs">' +
        "".join(
            f'''
            <div class="tab {'active' if t.key == active.key else ''}">
                <div class="icon">{t.icon}</div>
                <div>{t.label_zh if lang == "zh" else t.label_en}</div>
            </div>
            '''
            for t in PRIMARY_TABS
        ) +
        '</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    for i, tab in enumerate(PRIMARY_TABS):
        with cols[i]:
            label = (tab.label_zh if lang == "zh" else tab.label_en)
            is_active = tab.key == active.key
            if st.button(
                f"{tab.icon}\n{label}",
                key=f"bottom_tab_{tab.key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                goto_tab(tab.key)


# ============================================================
# Floating Action Button
# ============================================================
def render_fab(lang: str = "zh") -> None:
    """Floating action button — defaults to "start a quick session"."""
    if st.button(
        "🎬 " + ("快速開始" if lang == "zh" else "Quick Start"),
        key="fab_quick_start",
        use_container_width=False,
        type="primary",
    ):
        from app_state import goto
        st.session_state.active_tab = "train"
        goto("auto_exercise")


# ============================================================
# Sub-page back button
# ============================================================
def render_back_button(to_landing: str, lang: str = "zh") -> None:
    """Render a back arrow when viewing a sub-page within a tab."""
    if st.button(
        "← " + ("返回" if lang == "zh" else "Back"),
        key="back_btn",
    ):
        from app_state import goto
        goto(to_landing)


# ============================================================
# Page wrapper
# ============================================================
def is_landing(route: str) -> bool:
    """True if this route is a tab landing (not a sub-page)."""
    return route in {t.landing for t in PRIMARY_TABS}


def parent_landing(route: str) -> Optional[str]:
    """Return tab landing for the route, or None."""
    for tab in PRIMARY_TABS:
        if route in tab.routes and route != tab.landing:
            return tab.landing
    return None
