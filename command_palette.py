"""
Command palette: keyboard-driven global search for everything in the app.

Like VS Code Cmd+K — type a few letters, get fuzzy-matched commands.

Searchable items:
- All routes (navigate to any page)
- Exercises (start an exercise immediately)
- Recent sessions (jump to a result)
- Settings actions (toggle voice, change theme, etc.)
- Quick actions (logout, export, backup)

Uses a simple ranking algorithm with prefix-match boost.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import streamlit as st


@dataclass
class Command:
    """A single palette entry."""
    id: str
    title_zh: str
    title_en: str
    category: str  # nav / exercise / action / setting / recent
    icon: str = "•"
    keywords: str = ""
    on_select: Optional[Callable] = None
    description_zh: str = ""
    description_en: str = ""


# ============================================================
# Static command registry
# ============================================================
def _build_static_commands() -> List[Command]:
    """Standard navigation + action commands."""
    from app_state import goto

    nav = [
        ("home", "首頁", "Home", "🏠"),
        ("auto_exercise", "AI 自動分析", "Auto Analysis", "🤖"),
        ("live_enhanced", "即時教練", "Live Coach", "✨"),
        ("analytics", "分析儀表板", "Analytics", "📊"),
        ("games", "遊戲", "Games", "🎮"),
        ("quests", "任務", "Quests", "🎯"),
        ("nutrition", "營養", "Nutrition", "🍎"),
        ("sleep", "睡眠", "Sleep", "😴"),
        ("ai_chat", "AI 對話", "AI Chat", "💬"),
        ("notifications", "通知", "Notifications", "🔔"),
        ("vitals", "生命徵象", "Vitals", "🌡️"),
        ("medication", "藥物", "Medication", "💊"),
        ("pain_map", "疼痛地圖", "Pain Map", "🗺️"),
        ("journal", "日誌", "Journal", "📝"),
        ("calendar", "行事曆", "Calendar", "📅"),
        ("programs", "計畫", "Programs", "📋"),
        ("progress", "進度", "Progress", "📈"),
        ("wearables", "連接裝置", "Devices", "⌚"),
        ("cloud_sync", "雲端備份", "Cloud Sync", "☁️"),
        ("settings", "設定", "Settings", "⚙"),
    ]

    cmds = []
    for route, zh, en, icon in nav:
        cmds.append(Command(
            id=f"nav:{route}",
            title_zh=f"前往 {zh}",
            title_en=f"Go to {en}",
            category="nav",
            icon=icon,
            keywords=f"{route} {zh} {en} go navigate",
            on_select=(lambda r=route: goto(r)),
        ))

    cmds.extend(_action_commands())
    cmds.extend(_setting_commands())
    return cmds


def _action_commands() -> List[Command]:
    """Quick actions."""
    actions = []

    def _logout():
        try:
            from auth import logout
            logout()
            st.rerun()
        except Exception:
            pass

    def _toggle_theme():
        try:
            from theme import get_current_theme, set_theme
            cur = get_current_theme()
            set_theme("dark" if cur == "light" else "light")
            st.rerun()
        except Exception:
            pass

    def _start_workflow_daily():
        try:
            from workflow import start_workflow, advance_workflow
            user = st.session_state.get("user", {})
            uid = user.get("user_id") if isinstance(user, dict) else None
            if uid:
                start_workflow(uid, "daily_session")
                step = advance_workflow(uid)
                if step:
                    from app_state import goto
                    goto(step.route)
        except Exception:
            pass

    def _start_workflow_recovery():
        try:
            from workflow import start_workflow, advance_workflow
            user = st.session_state.get("user", {})
            uid = user.get("user_id") if isinstance(user, dict) else None
            if uid:
                start_workflow(uid, "recovery_check")
                step = advance_workflow(uid)
                if step:
                    from app_state import goto
                    goto(step.route)
        except Exception:
            pass

    actions.append(Command(
        id="action:logout",
        title_zh="登出",
        title_en="Logout",
        category="action",
        icon="🚪",
        keywords="logout signout 登出",
        on_select=_logout,
    ))
    actions.append(Command(
        id="action:toggle_theme",
        title_zh="切換主題",
        title_en="Toggle Theme",
        category="action",
        icon="🌓",
        keywords="theme dark light toggle 主題",
        on_select=_toggle_theme,
    ))
    actions.append(Command(
        id="action:start_daily",
        title_zh="開始今日訓練流程",
        title_en="Start Daily Session Flow",
        category="action",
        icon="🚀",
        keywords="daily routine workflow start 今日 訓練",
        on_select=_start_workflow_daily,
    ))
    actions.append(Command(
        id="action:start_recovery",
        title_zh="開始復原檢查",
        title_en="Start Recovery Check",
        category="action",
        icon="🔍",
        keywords="recovery check workflow 復原",
        on_select=_start_workflow_recovery,
    ))
    return actions


def _setting_commands() -> List[Command]:
    """Setting toggles."""

    def _toggle_voice():
        s = st.session_state.setdefault("settings", {})
        s["enable_voice"] = not s.get("enable_voice", True)
        st.rerun()

    def _toggle_difficulty():
        s = st.session_state.setdefault("settings", {})
        cur = s.get("difficulty", "normal")
        order = ["easy", "normal", "hard"]
        idx = order.index(cur) if cur in order else 1
        s["difficulty"] = order[(idx + 1) % len(order)]
        st.rerun()

    return [
        Command(
            id="set:voice",
            title_zh="切換語音回饋",
            title_en="Toggle Voice Feedback",
            category="setting",
            icon="🔊",
            keywords="voice tts speech 語音",
            on_select=_toggle_voice,
        ),
        Command(
            id="set:difficulty",
            title_zh="切換難度",
            title_en="Cycle Difficulty",
            category="setting",
            icon="🎚️",
            keywords="difficulty easy hard 難度",
            on_select=_toggle_difficulty,
        ),
    ]


def _exercise_commands() -> List[Command]:
    """Build commands for each known exercise template."""
    cmds = []
    try:
        import templates as tpl_mod
        if hasattr(tpl_mod, "BUILTIN_TEMPLATES"):
            for key, tpl in tpl_mod.BUILTIN_TEMPLATES.items():
                cmds.append(Command(
                    id=f"ex:{key}",
                    title_zh=f"開始 {tpl.get('name', key)}",
                    title_en=f"Start {tpl.get('name_en', tpl.get('name', key))}",
                    category="exercise",
                    icon="🏃",
                    keywords=f"{key} {tpl.get('name', '')} exercise start",
                    on_select=(lambda k=key: _start_exercise(k)),
                ))
    except Exception:
        pass
    return cmds


def _start_exercise(key: str) -> None:
    """Set exercise and navigate to record view."""
    from app_state import goto
    st.session_state.exercise_key = key
    goto("live_enhanced")


# ============================================================
# Fuzzy ranking
# ============================================================
def rank_commands(commands: List[Command], query: str,
                   lang: str = "zh") -> List[tuple]:
    """Rank commands against query. Returns [(score, command), ...]."""
    if not query:
        return [(0, c) for c in commands]

    q_lower = query.lower().strip()
    scored = []
    for cmd in commands:
        title = cmd.title_zh if lang == "zh" else cmd.title_en
        haystack = f"{title} {cmd.keywords}".lower()

        score = _score_match(q_lower, haystack)
        if score > 0:
            scored.append((score, cmd))

    scored.sort(key=lambda x: -x[0])
    return scored


def _score_match(query: str, text: str) -> float:
    """Simple fuzzy score: exact > prefix > contains > subsequence."""
    if query == text:
        return 1000
    if text.startswith(query):
        return 500
    if query in text:
        return 100 + (50 if f" {query}" in text else 0)

    if _is_subsequence(query, text):
        return 30 - len(text) * 0.1

    return 0


def _is_subsequence(needle: str, haystack: str) -> bool:
    """Check if needle is a subsequence of haystack."""
    i = 0
    for c in haystack:
        if i < len(needle) and c == needle[i]:
            i += 1
    return i == len(needle)


# ============================================================
# UI rendering
# ============================================================
def render_palette(key_prefix: str = "palette") -> None:
    """Render the command palette UI inline (in sidebar or modal)."""
    lang = st.session_state.get("settings", {}).get("lang", "zh")
    query_key = f"{key_prefix}_query"
    input_key = f"{key_prefix}_query_input"

    if query_key not in st.session_state:
        st.session_state[query_key] = ""

    query = st.text_input(
        "🔍 " + ("搜尋指令..." if lang == "zh" else "Search commands..."),
        key=input_key,
        placeholder="home / 訓練 / settings...",
        label_visibility="collapsed",
    )
    st.session_state[query_key] = query

    if not query:
        st.caption(
            "💡 " + ("輸入關鍵字搜尋頁面、動作或設定"
                     if lang == "zh"
                     else "Type to search pages, actions, or settings")
        )
        return

    all_commands = _build_static_commands() + _exercise_commands()
    ranked = rank_commands(all_commands, query, lang=lang)[:8]

    if not ranked:
        st.info("無結果" if lang == "zh" else "No matches")
        return

    for i, (score, cmd) in enumerate(ranked):
        title = cmd.title_zh if lang == "zh" else cmd.title_en

        cat_color = {
            "nav": "#74b9ff",
            "exercise": "#fdcb6e",
            "action": "#a29bfe",
            "setting": "#55efc4",
            "recent": "#fd79a8",
        }.get(cmd.category, "#dfe6e9")

        if st.button(
            f"{cmd.icon} {title}",
            key=f"palette_cmd_{cmd.id}_{i}",
            use_container_width=True,
        ):
            if cmd.on_select:
                cmd.on_select()
                st.session_state[query_key] = ""
                st.rerun()
        st.caption(
            f"<span style='color:{cat_color};font-size:11px'>"
            f"{cmd.category}</span>",
            unsafe_allow_html=True,
        )


def render_palette_button() -> None:
    """Render a button that opens the palette in a modal."""
    lang = st.session_state.get("settings", {}).get("lang", "zh")

    with st.sidebar.expander("🔍 " + ("指令面板" if lang == "zh"
                                       else "Command Palette")):
        render_palette(key_prefix="sidebar_palette")
