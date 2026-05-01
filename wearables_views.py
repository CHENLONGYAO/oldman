"""
Wearable device import UI: file upload + format detection.
"""
import streamlit as st
import pandas as pd

import ui
from auth import get_session_user
from wearables import (
    SUPPORTED_FORMATS,
    parse_apple_health,
    parse_fitbit_csv,
    parse_garmin_csv,
    parse_google_fit,
    parse_generic_csv,
    import_records,
    detect_format,
    get_imported_summary,
)
from service_integrations import (
    GOOGLE_FIT_SCOPES,
    complete_google_oauth_callback,
    disconnect,
    get_connection,
    google_oauth_url,
    sync_google_fit_summary,
)


def view_wearables():
    """Wearable device import view."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    callback = complete_google_oauth_callback(user_id, "google_fit")
    if callback:
        if callback.get("ok"):
            st.success(
                "Google Fit 已連接" if lang == "zh" else "Google Fit connected"
            )
        else:
            st.error(callback.get("error", "OAuth failed"))

    st.title("⌚ " + ("連接裝置" if lang == "zh" else "Connected Devices"))

    st.markdown(
        "優先使用直接連線；不支援直接連線的平台仍可用匯出檔匯入。"
        if lang == "zh" else
        "Use direct connections first; file import remains available as fallback."
    )

    with ui.app_section(
        "直接連線" if lang == "zh" else "Direct Connections",
        ("優先方式：背景自動同步" if lang == "zh"
         else "Preferred: background auto-sync"),
        icon="🔗",
    ):
        _render_device_connectors(user_id, lang)

    with ui.app_section(
        "支援匯入格式" if lang == "zh" else "Supported Imports",
        icon="📋",
    ):
        cols = st.columns(len(SUPPORTED_FORMATS))
        for i, (key, info) in enumerate(SUPPORTED_FORMATS.items()):
            with cols[i]:
                name = info["name_zh"] if lang == "zh" else info["name_en"]
                st.markdown(f"### {info['icon']}")
                st.caption(f"{name}")
                st.caption(f"`.{info['ext']}`")

    with ui.app_section(
        "匯入檔案" if lang == "zh" else "File Import",
        ("無法直接連線時的備援" if lang == "zh"
         else "Fallback when direct sync isn't available"),
        icon="📤",
    ):
        _render_file_import(user_id, lang)

    with ui.app_section(
        "已匯入摘要" if lang == "zh" else "Import Summary",
        icon="📊",
    ):
        summary = get_imported_summary(user_id)
        if summary["total"] > 0:
            st.metric(
                "總記錄數" if lang == "zh" else "Total Records",
                summary["total"],
            )
            if summary["sources"]:
                df_sources = pd.DataFrame(summary["sources"])
                st.dataframe(df_sources, use_container_width=True, hide_index=True)
        else:
            st.info(
                "尚未匯入任何穿戴裝置數據"
                if lang == "zh"
                else "No wearable data imported yet"
            )

    with st.expander("📖 " + ("使用說明" if lang == "zh" else "How to Export")):
        if lang == "zh":
            st.markdown("""
**Apple Health (iPhone):**
1. 開啟健康 App → 個人頭像 → 匯出所有健康資料
2. 解壓縮 zip → 上傳 `export.xml`

**Fitbit:**
1. 登入 fitbit.com → 設定 → 資料匯出
2. 下載 CSV 檔案

**Google Fit:**
1. 前往 Google Takeout (takeout.google.com)
2. 選擇 Fit → 下載 → 上傳 JSON

**通用 CSV 格式:**
欄位：`timestamp, type, value`
            """)
        else:
            st.markdown("""
**Apple Health (iPhone):**
1. Health App → Profile → Export All Health Data
2. Unzip → Upload `export.xml`

**Fitbit:**
1. fitbit.com → Settings → Data Export
2. Download CSV

**Google Fit:**
1. takeout.google.com → Select Fit → Download
2. Upload JSON file

**Generic CSV format:**
Columns: `timestamp, type, value`
            """)


def _render_file_import(user_id: str, lang: str) -> None:
    """File-based wearable data import body (parses + previews + imports)."""
    fmt_options = ["auto"] + list(SUPPORTED_FORMATS.keys())
    fmt_choice = st.selectbox(
        "格式" if lang == "zh" else "Format",
        options=fmt_options,
        format_func=lambda k: (
            "自動偵測" if k == "auto" and lang == "zh" else
            "Auto-detect" if k == "auto" else
            (SUPPORTED_FORMATS[k]["name_zh"] if lang == "zh"
             else SUPPORTED_FORMATS[k]["name_en"])
        ),
    )

    uploaded = st.file_uploader(
        "選擇檔案" if lang == "zh" else "Choose file",
        type=["xml", "csv", "json"],
        key="wearable_upload",
    )

    if not uploaded:
        return

    try:
        content = uploaded.read().decode("utf-8", errors="ignore")
    except Exception as e:
        st.error(f"讀取錯誤 / Read error: {e}")
        return

    actual_fmt = fmt_choice
    if fmt_choice == "auto":
        actual_fmt = detect_format(uploaded.name, content)
        if actual_fmt:
            fmt_name = SUPPORTED_FORMATS[actual_fmt]
            st.info(
                f"偵測到格式: {fmt_name['name_zh' if lang == 'zh' else 'name_en']}"
                if lang == "zh" else
                f"Detected: {fmt_name['name_en']}"
            )
        else:
            st.error(
                "無法偵測格式" if lang == "zh"
                else "Could not detect format"
            )
            return

    with st.spinner("解析中..." if lang == "zh" else "Parsing..."):
        if actual_fmt == "apple_health":
            records = parse_apple_health(content)
        elif actual_fmt == "fitbit":
            records = parse_fitbit_csv(content)
        elif actual_fmt == "garmin":
            records = parse_garmin_csv(content)
        elif actual_fmt == "google_fit":
            records = parse_google_fit(content)
        elif actual_fmt == "generic_csv":
            records = parse_generic_csv(content)
        else:
            records = []

    if not records:
        st.warning("無數據" if lang == "zh" else "No data found")
        return

    parse_errors = [r["error"] for r in records if "error" in r]
    valid = [r for r in records if "error" not in r]
    if parse_errors:
        st.warning(
            f"有 {len(parse_errors)} 筆解析錯誤"
            if lang == "zh"
            else f"{len(parse_errors)} parse errors"
        )
        with st.expander("解析錯誤" if lang == "zh" else "Parse Errors"):
            for err in parse_errors[:5]:
                st.caption(f"• {err}")

    if not valid:
        st.warning("沒有可匯入的有效資料" if lang == "zh" else "No valid data found")
        return

    st.success(
        f"找到 {len(valid)} 筆記錄" if lang == "zh"
        else f"Found {len(valid)} records"
    )

    df = pd.DataFrame(valid[:100])
    st.dataframe(df, use_container_width=True, height=200)

    if not st.button(
        "💾 " + ("匯入到我的數據" if lang == "zh" else "Import to My Data"),
        type="primary",
        use_container_width=True,
    ):
        return

    with st.spinner("匯入中..." if lang == "zh" else "Importing..."):
        result = import_records(user_id, records)

    message = (
        f"匯入 {result['imported']} 天資料，跳過 {result['skipped']} 筆"
        if lang == "zh" else
        f"Imported {result['imported']} days, skipped {result['skipped']} records"
    )
    if result["imported"]:
        st.success("✓ " + message)
    else:
        st.warning(message)

    if result.get("errors"):
        with st.expander("錯誤" if lang == "zh" else "Errors"):
            for err in result["errors"]:
                st.caption(f"• {err}")


def _render_device_connectors(user_id: str, lang: str) -> None:
    c1, c2 = st.columns(2)

    with c1:
        with st.container(border=True):
            st.markdown("### Google Fit / Health Connect")
            st.caption(
                "Google Fit API 將於 2026 年底停止服務；目前可連接 Fit，後續建議遷移到 Google Health API 或 Android Health Connect。"
                if lang == "zh" else
                "Google Fit APIs end service in late 2026; this connects Fit now, with migration path to Google Health API or Android Health Connect."
            )
            conn = get_connection(user_id, "google_fit")
            if conn:
                st.success("已連接" if lang == "zh" else "Connected")
                days = st.slider(
                    "同步天數" if lang == "zh" else "Days to sync",
                    1, 30, 7,
                    key="google_fit_sync_days",
                )
                sync_cols = st.columns(2)
                if sync_cols[0].button(
                    "同步 Google Fit" if lang == "zh" else "Sync Google Fit",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        result = sync_google_fit_summary(user_id, days=days)
                        st.success(
                            f"已匯入 {result['imported']} 天資料"
                            if lang == "zh"
                            else f"Imported {result['imported']} days"
                        )
                    except Exception as exc:
                        st.error(str(exc))
                if sync_cols[1].button(
                    "解除連接" if lang == "zh" else "Disconnect",
                    use_container_width=True,
                ):
                    disconnect(user_id, "google_fit")
                    st.rerun()
            else:
                url, missing = google_oauth_url("google_fit", GOOGLE_FIT_SCOPES)
                if url:
                    st.link_button(
                        "連接 Google Fit" if lang == "zh" else "Connect Google Fit",
                        url,
                        type="primary",
                        use_container_width=True,
                    )
                else:
                    st.warning(
                        ("缺少 OAuth 設定: " if lang == "zh"
                         else "Missing OAuth settings: ")
                        + ", ".join(missing)
                    )

    with c2:
        with st.container(border=True):
            st.markdown("### Apple Health")
            st.caption(
                "Apple Health 資料只能由 iPhone / Apple Watch 上的 HealthKit App 讀取；Web 版無法直接讀取。"
                if lang == "zh" else
                "Apple Health data is read through HealthKit on iPhone / Apple Watch; a web app cannot read it directly."
            )
            st.info(
                "目前可匯入 Apple Health XML；若要背景同步，需要 iOS App 端授權 HealthKit 後回傳資料。"
                if lang == "zh" else
                "Apple Health XML import is available now. Background sync requires an iOS app with HealthKit permission."
            )
