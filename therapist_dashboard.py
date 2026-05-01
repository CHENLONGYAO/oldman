"""
Therapist dashboard: manage patients, assign programs, view progress.

Features:
- Patient roster with filtering
- Patient detail view with session history
- Bulk program assignment
- Patient messaging
- Cohort analytics
"""
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

from db import (
    get_therapist_patients, get_user_sessions, get_health_data,
    execute_query, execute_update, insert_message, get_user_messages
)
from auth import get_session_user
from i18n import t
from roles import is_therapist


def view_therapist_dashboard():
    """Main therapist dashboard view."""
    lang = st.session_state.get("settings", {}).get("lang", "zh")
    if not is_therapist():
        st.error("無權限" if lang == "zh" else "No permission")
        return

    user = get_session_user()

    st.title("🏥 " + ("治療師儀表板" if lang == "zh" else "Therapist Dashboard"))

    # Navigation tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "👥 " + ("患者名單" if lang == "zh" else "Patient Roster"),
        "📋 " + ("計畫分配" if lang == "zh" else "Program Assignment"),
        "💬 " + ("訊息" if lang == "zh" else "Messages"),
        "📊 " + ("群體分析" if lang == "zh" else "Cohort Analytics")
    ])

    with tab1:
        _show_patient_roster(user["user_id"], lang)

    with tab2:
        _show_program_assignment(user["user_id"], lang)

    with tab3:
        _show_messaging(user["user_id"], lang)

    with tab4:
        _show_cohort_analytics(user["user_id"], lang)


def _show_patient_roster(therapist_id: str, lang: str) -> None:
    """Display list of therapist's patients."""
    st.subheader("👥 " + ("我的患者" if lang == "zh" else "My Patients"))

    # Get patients
    patients = get_therapist_patients(therapist_id)

    if not patients:
        st.info("尚無患者" if lang == "zh" else "No patients yet")
        return

    # Convert to DataFrame for display
    df = pd.DataFrame([
        {
            "名稱" if lang == "zh" else "Name": p["name"] or p["username"],
            "年齡" if lang == "zh" else "Age": p["age"] or "—",
            "狀況" if lang == "zh" else "Condition": p["condition"] or "—",
            "user_id": p["user_id"]
        }
        for p in patients
    ])

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        search = st.text_input(
            "搜尋患者名稱" if lang == "zh" else "Search patient name",
            key="patient_search"
        )
    with col2:
        condition_filter = st.multiselect(
            "狀況篩選" if lang == "zh" else "Filter by condition",
            options=df["狀況" if lang == "zh" else "Condition"].unique(),
            key="condition_filter"
        )
    with col3:
        sort_by = st.radio(
            "排序" if lang == "zh" else "Sort by",
            ["名稱" if lang == "zh" else "Name", "年齡" if lang == "zh" else "Age"],
            horizontal=True
        )

    # Apply filters
    if search:
        df = df[df["名稱" if lang == "zh" else "Name"].str.contains(search, case=False)]

    if condition_filter:
        df = df[df["狀況" if lang == "zh" else "Condition"].isin(condition_filter)]

    # Sort
    name_col = "名稱" if lang == "zh" else "Name"
    age_col = "年齡" if lang == "zh" else "Age"
    sort_col = name_col if sort_by == name_col else age_col
    df = df.sort_values(by=sort_col)

    # Display patient list
    st.dataframe(df[["名稱" if lang == "zh" else "Name", "年齡" if lang == "zh" else "Age", "狀況" if lang == "zh" else "Condition"]], use_container_width=True)

    # Click to view detail
    st.write("")
    selected_name = st.selectbox(
        "選擇患者查看詳細資料" if lang == "zh" else "Select patient to view details",
        options=df["名稱" if lang == "zh" else "Name"].tolist(),
        key="patient_select"
    )

    if selected_name:
        patient_id = df[df["名稱" if lang == "zh" else "Name"] == selected_name].iloc[0]["user_id"]
        _show_patient_detail(patient_id, therapist_id, lang)


def _show_patient_detail(patient_id: str, therapist_id: str, lang: str) -> None:
    """Display detailed view of single patient."""
    st.divider()
    st.subheader("👤 " + ("患者詳細資料" if lang == "zh" else "Patient Details"))

    # Get patient profile
    from db import get_user_profile, get_user_by_id
    profile = get_user_profile(patient_id)
    user = get_user_by_id(patient_id)

    if not profile:
        st.error("無法加載患者資料" if lang == "zh" else "Failed to load patient data")
        return

    # Profile info
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("年齡" if lang == "zh" else "Age", profile.get("age", "—"))
    with col2:
        st.metric("性別" if lang == "zh" else "Gender", profile.get("gender", "—"))
    with col3:
        st.metric("狀況" if lang == "zh" else "Condition", profile.get("condition", "—"))
    with col4:
        st.metric("聯繫" if lang == "zh" else "Contact", user.get("email") or "—")

    # Session history
    st.subheader("📊 " + ("訓練歷史" if lang == "zh" else "Session History"))
    sessions = get_user_sessions(patient_id, limit=10)

    if sessions:
        session_df = pd.DataFrame([
            {
                "日期" if lang == "zh" else "Date": s["created_at"][:10],
                "動作" if lang == "zh" else "Exercise": s["exercise"],
                "分數" if lang == "zh" else "Score": f"{s['score']:.1f}",
                "次數" if lang == "zh" else "Reps": s.get("rep_count", "—")
            }
            for s in sessions
        ])
        st.dataframe(session_df, use_container_width=True)
    else:
        st.info("尚無訓練紀錄" if lang == "zh" else "No training sessions yet")

    # Health data
    st.subheader("🌡️ " + ("健康數據" if lang == "zh" else "Health Data"))
    col1, col2, col3 = st.columns(3)

    with col1:
        pain_data = get_health_data(patient_id, "pain_map", limit=1)
        if pain_data:
            st.metric("疼痛評分" if lang == "zh" else "Pain Score", pain_data[0]["data_json"])
        else:
            st.metric("疼痛評分" if lang == "zh" else "Pain Score", "—")

    with col2:
        vitals_data = get_health_data(patient_id, "vitals", limit=1)
        if vitals_data:
            st.metric("最新生命跡象" if lang == "zh" else "Latest Vitals", "已記錄" if lang == "zh" else "Recorded")
        else:
            st.metric("最新生命跡象" if lang == "zh" else "Latest Vitals", "—")

    with col3:
        journal_data = get_health_data(patient_id, "journal", limit=1)
        if journal_data:
            st.metric("日誌記錄" if lang == "zh" else "Journal", "已記錄" if lang == "zh" else "Recorded")
        else:
            st.metric("日誌記錄" if lang == "zh" else "Journal", "—")


def _show_program_assignment(therapist_id: str, lang: str) -> None:
    """Show program assignment interface."""
    st.subheader("📋 " + ("分配計畫" if lang == "zh" else "Assign Programs"))

    patients = get_therapist_patients(therapist_id)

    if not patients:
        st.info("尚無患者" if lang == "zh" else "No patients yet")
        return

    # Multi-select patients
    patient_options = {p["name"] or p["username"]: p["user_id"] for p in patients}
    selected_patients = st.multiselect(
        "選擇患者（可多選）" if lang == "zh" else "Select patients (multi-select)",
        options=patient_options.keys(),
        key="assign_patients"
    )

    if selected_patients:
        # Program selection
        col1, col2 = st.columns(2)
        with col1:
            program_type = st.radio(
                "計畫類型" if lang == "zh" else "Program Type",
                ["預設計畫" if lang == "zh" else "Built-in", "自訂計畫" if lang == "zh" else "Custom"],
                horizontal=True
            )

        with col2:
            if program_type == ("預設計畫" if lang == "zh" else "Built-in"):
                program = st.selectbox(
                    "選擇計畫" if lang == "zh" else "Select Program",
                    ["膝蓋手術恢復 (6週)" if lang == "zh" else "Knee Surgery Recovery (6 weeks)",
                     "肩部恢復 (8週)" if lang == "zh" else "Shoulder Recovery (8 weeks)"]
                )
            else:
                program = st.text_input(
                    "自訂計畫名稱" if lang == "zh" else "Custom Program Name",
                    key="custom_program"
                )

        # Duration settings
        col1, col2, col3 = st.columns(3)
        with col1:
            start_date = st.date_input(
                "開始日期" if lang == "zh" else "Start Date",
                value=datetime.now()
            )

        with col2:
            duration = st.number_input(
                "持續週數" if lang == "zh" else "Duration (weeks)",
                min_value=1, max_value=24, value=6
            )

        with col3:
            frequency = st.number_input(
                "每週次數" if lang == "zh" else "Sessions per week",
                min_value=1, max_value=7, value=3
            )

        # Assign button
        if st.button("✓ " + ("分配計畫" if lang == "zh" else "Assign Program"),
                    type="primary", use_container_width=True):
            for patient_name in selected_patients:
                patient_id = patient_options[patient_name]
                # Insert assignment
                execute_update(
                    """
                    INSERT INTO team_assignments
                    (therapist_id, patient_id, program_id, assigned_date, start_date, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                    """,
                    (therapist_id, patient_id, program, datetime.now().date(), start_date)
                )

            st.success(f"已分配給 {len(selected_patients)} 位患者" if lang == "zh"
                      else f"Assigned to {len(selected_patients)} patients")
            st.rerun()


def _show_messaging(therapist_id: str, lang: str) -> None:
    """Show patient messaging interface."""
    st.subheader("💬 " + ("患者訊息" if lang == "zh" else "Patient Messages"))

    patients = get_therapist_patients(therapist_id)

    if not patients:
        st.info("尚無患者" if lang == "zh" else "No patients yet")
        return

    # Select recipient
    patient_options = {p["name"] or p["username"]: p["user_id"] for p in patients}
    recipient = st.selectbox(
        "選擇收件人" if lang == "zh" else "Select recipient",
        options=patient_options.keys(),
        key="message_recipient"
    )

    if recipient:
        recipient_id = patient_options[recipient]

        # Get conversation history
        messages = get_user_messages(therapist_id, limit=20)
        filtered_msgs = [m for m in messages
                        if (m["from_user_id"] == therapist_id and m["to_user_id"] == recipient_id) or
                           (m["from_user_id"] == recipient_id and m["to_user_id"] == therapist_id)]

        if filtered_msgs:
            st.write("最近訊息" if lang == "zh" else "Recent Messages")
            for msg in reversed(filtered_msgs):
                if msg["from_user_id"] == therapist_id:
                    sender = "您" if lang == "zh" else "You"
                else:
                    sender = recipient
                st.write(f"**{sender}**: {msg['content']}")

        # New message
        st.write("")
        col1, col2 = st.columns([4, 1])
        with col1:
            new_msg = st.text_input(
                "輸入訊息" if lang == "zh" else "Type message",
                key="new_message"
            )
        with col2:
            if st.button("📤 " + ("發送" if lang == "zh" else "Send"), key="send_msg"):
                if new_msg:
                    insert_message(therapist_id, recipient_id, new_msg)
                    st.success("訊息已發送" if lang == "zh" else "Message sent")
                    st.rerun()


def _show_cohort_analytics(therapist_id: str, lang: str) -> None:
    """Show aggregated analytics for therapist's patients."""
    st.subheader("📊 " + ("群體分析" if lang == "zh" else "Cohort Analytics"))

    patients = get_therapist_patients(therapist_id)

    if not patients:
        st.info("尚無患者" if lang == "zh" else "No patients yet")
        return

    # Aggregate statistics
    total_patients = len(patients)
    total_sessions = 0
    avg_score = 0

    for patient in patients:
        sessions = get_user_sessions(patient["user_id"], limit=100)
        total_sessions += len(sessions)
        if sessions:
            scores = [s["score"] for s in sessions if s["score"]]
            avg_score += sum(scores) / len(scores) if scores else 0

    avg_score = avg_score / total_patients if total_patients > 0 else 0

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("患者數" if lang == "zh" else "Total Patients", total_patients)
    with col2:
        st.metric("總訓練次數" if lang == "zh" else "Total Sessions", total_sessions)
    with col3:
        st.metric("平均分數" if lang == "zh" else "Average Score", f"{avg_score:.1f}")
    with col4:
        st.metric("活躍患者" if lang == "zh" else "Active", sum(1 for p in patients if get_user_sessions(p["user_id"], limit=1)))

    # Performance by patient
    st.subheader("患者表現排名" if lang == "zh" else "Patient Performance Ranking")
    patient_stats = []
    for patient in patients:
        sessions = get_user_sessions(patient["user_id"], limit=50)
        if sessions:
            scores = [s["score"] for s in sessions if s["score"]]
            patient_stats.append({
                "患者" if lang == "zh" else "Patient": patient["name"] or patient["username"],
                "訓練次數" if lang == "zh" else "Sessions": len(sessions),
                "平均分數" if lang == "zh" else "Avg Score": f"{sum(scores)/len(scores):.1f}" if scores else "—"
            })

    if patient_stats:
        df = pd.DataFrame(patient_stats)
        df_sorted = df.sort_values(by="平均分數" if lang == "zh" else "Avg Score", ascending=False)
        st.dataframe(df_sorted, use_container_width=True)
