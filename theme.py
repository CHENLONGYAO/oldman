"""
Theme system: light, dark, high-contrast, sepia.

Persists choice to user settings, injects CSS variables for theming.
"""
import streamlit as st


THEMES = {
    "light": {
        "name_zh": "明亮", "name_en": "Light", "icon": "☀️",
        "bg": "#ffffff",
        "surface": "#f8f9fa",
        "text": "#212529",
        "text_muted": "#6c757d",
        "primary": "#007aff",
        "border": "#dee2e6",
        "shadow": "0 2px 8px rgba(0,0,0,0.06)",
    },
    "dark": {
        "name_zh": "深色", "name_en": "Dark", "icon": "🌙",
        "bg": "#1c1f26",
        "surface": "#262a33",
        "text": "#e8e8e8",
        "text_muted": "#a0a0a0",
        "primary": "#5e8efc",
        "border": "#3a3f4a",
        "shadow": "0 2px 8px rgba(0,0,0,0.4)",
    },
    "high_contrast": {
        "name_zh": "高對比", "name_en": "High Contrast", "icon": "⚡",
        "bg": "#1a1d24",
        "surface": "#252932",
        "text": "#ffffff",
        "text_muted": "#cccccc",
        "primary": "#ffd60a",
        "border": "#ffffff",
        "shadow": "none",
    },
    "sepia": {
        "name_zh": "護眼", "name_en": "Sepia", "icon": "📜",
        "bg": "#f4ecd8",
        "surface": "#ebe0c4",
        "text": "#5b4636",
        "text_muted": "#8a7560",
        "primary": "#a67c52",
        "border": "#d4c5a5",
        "shadow": "0 2px 8px rgba(91,70,54,0.1)",
    },
}


def get_current_theme() -> str:
    """Get the current theme key from session state."""
    return st.session_state.get("settings", {}).get("theme", "light")


def set_theme(theme_key: str) -> None:
    """Set theme in user settings."""
    if "settings" not in st.session_state:
        st.session_state.settings = {}
    if theme_key in THEMES:
        st.session_state.settings["theme"] = theme_key


def inject_theme_css() -> None:
    """Inject CSS based on current theme."""
    key = get_current_theme()
    theme = THEMES.get(key, THEMES["light"])

    css = f"""
    <style>
    :root {{
        --theme-bg: {theme['bg']};
        --theme-surface: {theme['surface']};
        --theme-text: {theme['text']};
        --theme-text-muted: {theme['text_muted']};
        --theme-primary: {theme['primary']};
        --theme-border: {theme['border']};
        --theme-shadow: {theme['shadow']};
    }}

    .stApp {{
        background-color: var(--theme-bg) !important;
        color: var(--theme-text) !important;
    }}

    [data-testid="stSidebar"] {{
        background-color: var(--theme-surface) !important;
    }}

    [data-testid="stSidebar"] * {{
        color: var(--theme-text) !important;
    }}

    .stMarkdown, .stText, p, span, div, label {{
        color: var(--theme-text) !important;
    }}

    h1, h2, h3, h4, h5, h6 {{
        color: var(--theme-text) !important;
    }}

    .stCaption, [data-testid="stCaptionContainer"] {{
        color: var(--theme-text-muted) !important;
    }}

    [data-testid="stMetric"] {{
        background-color: var(--theme-surface) !important;
        border: 1px solid var(--theme-border) !important;
        border-radius: 8px;
        padding: 12px;
    }}

    .stButton > button {{
        background-color: var(--theme-surface) !important;
        color: var(--theme-text) !important;
        border: 1px solid var(--theme-border) !important;
    }}

    .stButton > button[kind="primary"] {{
        background-color: var(--theme-primary) !important;
        color: white !important;
        border-color: var(--theme-primary) !important;
    }}

    [data-testid="stSelectbox"] > div > div,
    [data-testid="stMultiSelect"] > div > div,
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input {{
        background-color: var(--theme-surface) !important;
        color: var(--theme-text) !important;
        border-color: var(--theme-border) !important;
    }}

    [data-testid="stContainer"][data-testid="block-container"] > div {{
        background-color: transparent !important;
    }}

    [data-testid="stAlert"] {{
        background-color: var(--theme-surface) !important;
        color: var(--theme-text) !important;
    }}

    [data-testid="stExpander"] {{
        background-color: var(--theme-surface) !important;
        border-color: var(--theme-border) !important;
    }}

    [data-testid="stTable"], [data-testid="stDataFrame"] {{
        background-color: var(--theme-surface) !important;
        color: var(--theme-text) !important;
    }}

    .stProgress > div > div {{
        background-color: var(--theme-primary) !important;
    }}

    div[role="tablist"] button {{
        color: var(--theme-text) !important;
    }}

    div[role="tab"][aria-selected="true"] {{
        border-bottom-color: var(--theme-primary) !important;
        color: var(--theme-primary) !important;
    }}
    </style>
    """

    st.markdown(css, unsafe_allow_html=True)


def render_theme_picker() -> None:
    """Render theme picker UI."""
    lang = st.session_state.get("settings", {}).get("lang", "zh")
    current = get_current_theme()

    st.markdown(f"### 🎨 {'主題' if lang == 'zh' else 'Theme'}")

    cols = st.columns(len(THEMES))
    for i, (key, theme) in enumerate(THEMES.items()):
        with cols[i]:
            name = theme["name_zh"] if lang == "zh" else theme["name_en"]
            is_current = (key == current)

            st.markdown(
                f"<div style='background:{theme['bg']};"
                f"color:{theme['text']};padding:16px;border-radius:8px;"
                f"border:{'3px solid ' + theme['primary'] if is_current else '1px solid ' + theme['border']};"
                f"text-align:center'>"
                f"<div style='font-size:32px'>{theme['icon']}</div>"
                f"<div style='font-weight:600;margin-top:4px'>{name}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if not is_current:
                if st.button(
                    ("選擇" if lang == "zh" else "Select"),
                    key=f"theme_{key}",
                    use_container_width=True,
                ):
                    set_theme(key)
                    st.rerun()
            else:
                st.success("✓ " + ("使用中" if lang == "zh" else "Active"))


def render_quick_theme_toggle() -> None:
    """Render quick light/dark toggle for sidebar."""
    current = get_current_theme()
    is_dark = current in ("dark", "high_contrast")

    label = "☀️ Light" if is_dark else "🌙 Dark"
    if st.sidebar.button(label, key="quick_theme_toggle",
                         use_container_width=True):
        set_theme("light" if is_dark else "dark")
        st.rerun()
