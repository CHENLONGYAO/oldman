"""
Audit log UI: admin view for compliance review.
"""
from datetime import datetime, timedelta, date
import streamlit as st
import pandas as pd

from auth import get_session_user
from roles import is_therapist
from audit_log import (
    AUDIT_ACTIONS, query_logs, verify_integrity,
    get_user_activity_summary, export_logs_csv,
)


def view_audit_log():
    """Audit log review page (admin/therapist only)."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    role = user.get("role", "patient")
    if not is_therapist(role):
        st.error(
            "僅限治療師層級以上存取" if st.session_state.get(
                "settings", {}).get("lang", "zh") == "zh"
            else "Therapist-level access only"
        )
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")

    st.title("📋 " + ("稽核日誌" if lang == "zh" else "Audit Log"))
    st.caption(
        "符合 HIPAA 要求的不可變更操作記錄"
        if lang == "zh" else
        "HIPAA-compliant immutable activity log"
    )

    tab_view, tab_summary, tab_integrity = st.tabs([
        "📜 " + ("查看" if lang == "zh" else "View"),
        "📊 " + ("摘要" if lang == "zh" else "Summary"),
        "🔒 " + ("完整性" if lang == "zh" else "Integrity"),
    ])

    with tab_view:
        _render_view_tab(lang)

    with tab_summary:
        _render_summary_tab(lang)

    with tab_integrity:
        _render_integrity_tab(lang)


def _render_view_tab(lang: str) -> None:
    st.subheader("🔍 " + ("篩選" if lang == "zh" else "Filters"))

    col1, col2, col3 = st.columns(3)
    with col1:
        category_filter = st.selectbox(
            "類別" if lang == "zh" else "Category",
            options=["all", "auth", "phi_access", "data_mutation",
                     "permission", "export", "system"],
            format_func=lambda c: ({"all": "全部", "auth": "驗證",
                                    "phi_access": "PHI 存取",
                                    "data_mutation": "資料變更",
                                    "permission": "權限",
                                    "export": "匯出",
                                    "system": "系統"}.get(c, c)
                                   if lang == "zh" else c),
        )
    with col2:
        severity_filter = st.selectbox(
            "嚴重性" if lang == "zh" else "Severity",
            options=["all", "info", "warning", "critical"],
        )
    with col3:
        days_back = st.number_input(
            "回溯天數" if lang == "zh" else "Days back",
            min_value=1, max_value=365, value=7,
        )

    user_id_filter = st.text_input(
        "使用者 ID (選填)" if lang == "zh" else "User ID (optional)"
    )

    filters = {
        "limit": 200,
        "start_date": (datetime.now() - timedelta(days=int(days_back))).isoformat(),
    }
    if category_filter != "all":
        filters["category"] = category_filter
    if severity_filter != "all":
        filters["severity"] = severity_filter
    if user_id_filter:
        filters["user_id"] = user_id_filter.strip()

    logs = query_logs(**filters)

    st.markdown(
        f"**{len(logs)}** {'筆記錄' if lang == 'zh' else 'entries'}"
    )

    if logs:
        df = pd.DataFrame(logs)
        display_cols = ["created_at", "user_id", "action", "category",
                        "severity", "resource_type", "success"]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True,
                    hide_index=True, height=400)

        if st.button(
            "📥 " + ("匯出 CSV" if lang == "zh" else "Export CSV"),
        ):
            csv_str = export_logs_csv(filters)
            st.download_button(
                "下載 CSV" if lang == "zh" else "Download CSV",
                data=csv_str,
                file_name=f"audit_log_{date.today().isoformat()}.csv",
                mime="text/csv",
            )
    else:
        st.info("無記錄" if lang == "zh" else "No entries")


def _render_summary_tab(lang: str) -> None:
    user_id = st.text_input(
        "使用者 ID" if lang == "zh" else "User ID",
        key="summary_user_id",
    )

    if not user_id:
        st.info("請輸入使用者 ID" if lang == "zh" else "Enter user ID")
        return

    days = st.slider(
        "回溯天數" if lang == "zh" else "Days back",
        7, 365, 30,
    )

    summary = get_user_activity_summary(user_id, days=days)

    st.metric(
        "總操作次數" if lang == "zh" else "Total Actions",
        summary["total"],
    )

    if summary["by_category"]:
        st.subheader("📊 " + ("按類別" if lang == "zh" else "By Category"))
        cat_df = pd.DataFrame([
            {"category": k, "count": v}
            for k, v in summary["by_category"].items()
        ])
        st.bar_chart(cat_df.set_index("category"))

    if summary["top_actions"]:
        st.subheader("🔝 " + ("熱門操作" if lang == "zh" else "Top Actions"))
        st.dataframe(
            pd.DataFrame(summary["top_actions"]),
            use_container_width=True,
            hide_index=True,
        )


def _render_integrity_tab(lang: str) -> None:
    st.subheader("🔐 " + ("雜湊鏈完整性檢查" if lang == "zh"
                          else "Hash Chain Integrity"))
    st.caption(
        "驗證日誌記錄是否被竄改。每筆記錄的雜湊都包含前一筆。"
        if lang == "zh" else
        "Verify log entries haven't been tampered with. "
        "Each entry's hash includes the previous."
    )

    if st.button(
        "🔍 " + ("執行檢查" if lang == "zh" else "Run Check"),
        type="primary",
    ):
        with st.spinner("驗證中..." if lang == "zh" else "Verifying..."):
            result = verify_integrity()

        if result["verified"]:
            st.success(
                f"✓ 完整性確認 ({result['entries_checked']} 筆通過驗證)"
                if lang == "zh"
                else f"✓ Integrity verified ({result['entries_checked']} entries)"
            )
        else:
            st.error(
                f"⚠️ 完整性失敗 — 在 ID {result.get('broken_at_id')} 處鏈結斷裂"
                if lang == "zh"
                else f"⚠️ Integrity failure at ID {result.get('broken_at_id')}"
            )
            if "expected" in result:
                with st.expander("詳情" if lang == "zh" else "Details"):
                    st.code(f"Expected: {result['expected']}\n"
                           f"Actual:   {result['actual']}")
