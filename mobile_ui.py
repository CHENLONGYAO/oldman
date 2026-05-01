"""
Mobile-friendly UI components and responsive design utilities.

Features:
- Mobile detection from user agent
- Touch-optimized buttons (48px minimum)
- Responsive grid layouts
- Mobile-specific CSS injection
"""
import streamlit as st


MOBILE_CSS = """
<style>
/* Touch-optimized buttons (48px min, Apple/Material guidelines) */
@media (max-width: 768px) {
    .stButton > button {
        min-height: 48px !important;
        font-size: 16px !important;
        padding: 12px 16px !important;
    }
    .stRadio > label, .stSelectbox > label {
        font-size: 16px !important;
    }
    /* Larger inputs on mobile */
    input, textarea, select {
        font-size: 16px !important;  /* Prevents iOS zoom */
        min-height: 44px !important;
    }
    /* Stack columns on mobile */
    .row-widget.stHorizontal > div {
        flex-direction: column !important;
    }
    /* Wider touch targets for navigation */
    [data-testid="stSidebarNav"] a {
        padding: 12px 16px !important;
        min-height: 44px !important;
    }
    /* Mobile metrics: full width */
    [data-testid="stMetric"] {
        width: 100% !important;
        margin-bottom: 8px !important;
    }
    /* Responsive tables */
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }
    /* Mobile-friendly h1/h2 */
    h1 { font-size: 1.6rem !important; }
    h2 { font-size: 1.3rem !important; }
    h3 { font-size: 1.15rem !important; }
}

/* Tablet adjustments */
@media (min-width: 769px) and (max-width: 1024px) {
    .stButton > button {
        min-height: 44px !important;
    }
}

/* Make plotly charts responsive */
.js-plotly-plot, .plotly {
    width: 100% !important;
}

/* Better dropdown menus on mobile */
@media (max-width: 768px) {
    [data-baseweb="select"] {
        min-height: 48px !important;
    }
}
</style>
"""


def inject_mobile_css() -> None:
    """Inject mobile-responsive CSS."""
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)


def is_mobile_view() -> bool:
    """
    Detect if user is on mobile.

    Streamlit doesn't expose user agent directly, so we use a session
    state preference or screen width detection via URL param.
    """
    if "is_mobile" in st.session_state:
        return st.session_state.is_mobile

    try:
        params = st.query_params
        if params.get("mobile") == "1":
            st.session_state.is_mobile = True
            return True
    except Exception:
        pass

    return False


def adaptive_columns(desktop_count: int = 3, mobile_count: int = 1):
    """Return columns appropriate for current viewport."""
    count = mobile_count if is_mobile_view() else desktop_count
    return st.columns(count)


def mobile_friendly_metric(label: str, value: str, delta: str = None) -> None:
    """Render metric with mobile-friendly sizing."""
    if is_mobile_view():
        delta_html = (
            f"<div style='font-size:12px;color:#28a745'>{delta}</div>"
            if delta else ""
        )
        st.markdown(
            f"<div style='padding:12px;background:#f8f9fa;border-radius:8px;"
            f"margin-bottom:8px'>"
            f"<div style='font-size:14px;color:#6c757d'>{label}</div>"
            f"<div style='font-size:24px;font-weight:600'>{value}</div>"
            f"{delta_html}"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.metric(label, value, delta=delta)


def render_mobile_toggle() -> None:
    """Show mobile/desktop toggle in sidebar."""
    is_mobile = is_mobile_view()
    label = "💻 切換到桌面" if is_mobile else "📱 切換到手機"
    if st.sidebar.button(label, key="mobile_toggle"):
        st.session_state.is_mobile = not is_mobile
        st.rerun()


def render_mobile_nav(routes: list, current_step: str, lang: str) -> None:
    """Render compact mobile navigation as a dropdown."""
    if not is_mobile_view():
        return

    options = {key: f"{icon} {label_zh if lang == 'zh' else label_en}"
               for key, label_zh, label_en, icon in routes}

    current_idx = list(options.keys()).index(current_step) if current_step in options else 0

    selected = st.selectbox(
        "📍 " + ("導航" if lang == "zh" else "Navigation"),
        options=list(options.keys()),
        format_func=lambda k: options[k],
        index=current_idx,
        key="mobile_nav",
    )

    if selected != current_step:
        from app_state import goto
        goto(selected)


def render_swipeable_cards(items: list, render_fn) -> None:
    """Render cards in a horizontally scrollable container on mobile."""
    if is_mobile_view():
        st.markdown(
            "<div style='overflow-x:auto;display:flex;gap:12px;padding:8px'>",
            unsafe_allow_html=True,
        )
        for item in items:
            render_fn(item)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        cols = st.columns(min(3, len(items)))
        for i, item in enumerate(items):
            with cols[i % len(cols)]:
                render_fn(item)
