"""
Authentication views: login, register, logout.
"""
import streamlit as st
from auth import register_user, login_user, login_oauth
from i18n import t
from oauth_flow import (
    clear_oauth_query_params,
    complete_oauth_callback,
    create_authorization_url,
    oauth_status_text,
    provider_config,
)


def _render_oauth_link(label: str, url: str, key: str) -> None:
    if hasattr(st, "link_button"):
        st.link_button(label, url, use_container_width=True)
    else:
        st.markdown(
            f"""
            <a href="{url}" target="_self"
               style="display:block;text-align:center;padding:.55rem .75rem;
                      border:1px solid rgba(49,51,63,.2);border-radius:.5rem;
                      text-decoration:none;color:inherit;">
                {label}
            </a>
            """,
            unsafe_allow_html=True,
        )


def _render_oauth_buttons(lang: str) -> None:
    col_g, col_a = st.columns(2)

    with col_g:
        google_url, _ = create_authorization_url("google")
        if google_url:
            _render_oauth_link("🔵 Google", google_url, "google_oauth")
        else:
            st.button("🔵 Google", use_container_width=True, disabled=True)
            st.caption(oauth_status_text("google", lang))

    with col_a:
        apple_url, _ = create_authorization_url("apple")
        if apple_url:
            _render_oauth_link("🍎 Apple", apple_url, "apple_oauth")
        else:
            st.button("🍎 Apple", use_container_width=True, disabled=True)
            st.caption(oauth_status_text("apple", lang))

    with st.expander("OAuth 設定" if lang == "zh" else "OAuth setup", expanded=False):
        redirect_uri = provider_config("google").redirect_uri
        st.caption(
            "請在 Google Cloud Console / Apple Developer 後台把以下 Redirect URI 加入允許清單。"
            if lang == "zh"
            else "Add this Redirect URI to Google Cloud Console / Apple Developer."
        )
        st.code(redirect_uri)
        st.caption(
            "可用環境變數或 Streamlit secrets 設定：GOOGLE_CLIENT_ID、GOOGLE_CLIENT_SECRET、"
            "APPLE_CLIENT_ID、APPLE_CLIENT_SECRET、OAUTH_REDIRECT_URI。"
            if lang == "zh"
            else "Configure with environment variables or Streamlit secrets: GOOGLE_CLIENT_ID, "
            "GOOGLE_CLIENT_SECRET, APPLE_CLIENT_ID, APPLE_CLIENT_SECRET, OAUTH_REDIRECT_URI."
        )


def _handle_oauth_callback(lang: str) -> bool:
    result = complete_oauth_callback()
    if result is None:
        return False

    if result.get("success"):
        success, message, token = login_oauth(
            result["provider"],
            result["provider_user_id"],
            result.get("email", ""),
            result.get("name", ""),
        )
        if success and token:
            st.session_state.auth_token = token
            clear_oauth_query_params()
            st.success(message)
            st.rerun()
        st.error(message)
    else:
        st.error(result.get("message") or ("OAuth 登入失敗" if lang == "zh" else "OAuth login failed"))

    if st.button("返回登入" if lang == "zh" else "Back to login", key="oauth_back"):
        clear_oauth_query_params()
        st.rerun()
    return True


def view_login():
    """User login view."""
    lang = st.session_state.get("settings", {}).get("lang", "zh")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🏥 " + t("app_title", lang))
        st.markdown("---")

        username = st.text_input(
            t("username", lang),
            placeholder="輸入用戶名" if lang == "zh" else "Enter username",
            key="login_username"
        )

        password = st.text_input(
            t("password", lang),
            type="password",
            placeholder="輸入密碼" if lang == "zh" else "Enter password",
            key="login_password"
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔓 " + ("登入" if lang == "zh" else "Login"), use_container_width=True, type="primary"):
                if username and password:
                    success, message, token = login_user(username, password)
                    if success:
                        st.session_state.auth_token = token
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
                else:
                    st.warning("請輸入用戶名和密碼" if lang == "zh" else "Please enter username and password")

        with col_b:
            if st.button("📝 " + ("註冊" if lang == "zh" else "Register"), use_container_width=True):
                st.session_state.auth_view = "register"
                st.rerun()

        st.markdown("---")

        _render_oauth_buttons(lang)


def view_register():
    """User registration view."""
    lang = st.session_state.get("settings", {}).get("lang", "zh")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🏥 " + t("app_title", lang))
        st.markdown("---")

        username = st.text_input(
            t("username", lang),
            placeholder="至少 3 個字符" if lang == "zh" else "At least 3 characters",
            key="register_username"
        )

        password = st.text_input(
            t("password", lang),
            type="password",
            placeholder="至少 6 個字符" if lang == "zh" else "At least 6 characters",
            key="register_password"
        )

        password_confirm = st.text_input(
            "確認密碼" if lang == "zh" else "Confirm Password",
            type="password",
            placeholder="再次輸入密碼" if lang == "zh" else "Enter password again",
            key="register_password_confirm"
        )

        role = st.radio(
            "選擇身份" if lang == "zh" else "Select Role",
            ["患者" if lang == "zh" else "Patient", "治療師" if lang == "zh" else "Therapist"],
            horizontal=True,
            key="register_role"
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("✓ " + ("創建帳戶" if lang == "zh" else "Create Account"), use_container_width=True, type="primary"):
                if not username or not password or not password_confirm:
                    st.warning("請填寫所有欄位" if lang == "zh" else "Please fill all fields")
                elif password != password_confirm:
                    st.error("密碼不匹配" if lang == "zh" else "Passwords don't match")
                else:
                    role_map = {
                        "患者" if lang == "zh" else "Patient": "patient",
                        "治療師" if lang == "zh" else "Therapist": "therapist"
                    }
                    success, message = register_user(username, password, role_map.get(role, "patient"))
                    if success:
                        st.success(message)
                        st.info("帳戶已創建！現在可以登入。" if lang == "zh" else "Account created! You can now login.")
                        st.session_state.auth_view = "login"
                        st.rerun()
                    else:
                        st.error(message)

        with col_b:
            if st.button("← " + ("返回登入" if lang == "zh" else "Back to Login"), use_container_width=True):
                st.session_state.auth_view = "login"
                st.rerun()


def show_auth_page():
    """Show login or register page."""
    lang = st.session_state.get("settings", {}).get("lang", "zh")
    if _handle_oauth_callback(lang):
        return

    view_type = st.session_state.get("auth_view", "login")

    if view_type == "register":
        view_register()
    else:
        view_login()
