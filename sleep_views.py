"""
Sleep tracker UI: log sleep, view trends, performance correlation.
"""
from datetime import date, timedelta
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from auth import get_session_user
from sleep_tracker import (
    log_sleep, get_sleep_history, get_sleep_stats,
    correlate_with_performance, get_sleep_score, get_sleep_recommendations,
)


def view_sleep():
    """Sleep tracking dashboard."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    st.title("😴 " + ("睡眠追蹤" if lang == "zh" else "Sleep Tracker"))

    score = get_sleep_score(user_id)
    if score["score"] is not None:
        col1, col2, col3 = st.columns(3)
        stats = score["stats"]
        with col1:
            st.metric(
                "睡眠評分" if lang == "zh" else "Sleep Score",
                f"{score['score']}/100",
            )
        with col2:
            st.metric(
                "平均時長" if lang == "zh" else "Avg Duration",
                f"{stats['avg_duration']}h",
            )
        with col3:
            st.metric(
                "規律性" if lang == "zh" else "Consistency",
                f"{stats['consistency_score']:.0f}%",
            )

    st.divider()
    st.subheader("📝 " + ("記錄昨晚" if lang == "zh" else "Log Last Night"))

    with st.form("sleep_log"):
        sleep_date = st.date_input(
            "日期" if lang == "zh" else "Date",
            value=date.today() - timedelta(days=1),
        )

        c1, c2 = st.columns(2)
        with c1:
            bedtime = st.time_input(
                "就寢時間" if lang == "zh" else "Bedtime",
                value=None,
                key="bedtime",
            )
        with c2:
            wake_time = st.time_input(
                "起床時間" if lang == "zh" else "Wake Time",
                value=None,
                key="wake_time",
            )

        quality = st.slider(
            "睡眠品質" if lang == "zh" else "Quality",
            1, 5, 3,
            help="1=很差, 5=很好" if lang == "zh" else "1=poor, 5=excellent",
        )

        interruptions = st.number_input(
            "夜間醒來次數" if lang == "zh" else "Interruptions",
            min_value=0, max_value=10, value=0,
        )

        notes = st.text_area(
            "備註" if lang == "zh" else "Notes",
            placeholder="作夢、睡前活動..." if lang == "zh"
                        else "Dreams, pre-sleep activity...",
        )

        submitted = st.form_submit_button(
            "💤 " + ("記錄" if lang == "zh" else "Log Sleep"),
            type="primary",
            use_container_width=True,
        )

        if submitted:
            if not bedtime or not wake_time:
                st.error("請輸入就寢和起床時間" if lang == "zh"
                        else "Please enter bedtime and wake time")
            else:
                bt_str = bedtime.strftime("%H:%M")
                wt_str = wake_time.strftime("%H:%M")
                if log_sleep(user_id, sleep_date.isoformat(),
                             bt_str, wt_str, quality, interruptions, notes):
                    st.success("✓ " + ("已記錄" if lang == "zh" else "Logged"))
                    st.rerun()

    history = get_sleep_history(user_id, days=14)
    if history:
        st.divider()
        st.subheader("📈 " + ("最近 14 天" if lang == "zh" else "Last 14 Days"))

        df = pd.DataFrame(history)
        df["sleep_date"] = pd.to_datetime(df["sleep_date"])

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["sleep_date"],
            y=df["duration_hours"],
            name="時長 (h)" if lang == "zh" else "Duration (h)",
            marker_color="#74b9ff",
        ))
        fig.add_hline(y=7, line_dash="dash", line_color="green",
                     annotation_text="7h")
        fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("詳細記錄" if lang == "zh" else "Detail Records"):
            display_df = df[["sleep_date", "bedtime", "wake_time",
                            "duration_hours", "quality", "interruptions"]]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    corr = correlate_with_performance(user_id)
    if corr["samples"] >= 3:
        st.divider()
        st.subheader("🔗 " + ("睡眠 vs 訓練表現" if lang == "zh"
                              else "Sleep vs Performance"))

        c1, c2 = st.columns(2)
        with c1:
            dc = corr.get("duration_correlation", 0) or 0
            st.metric(
                "睡眠時長相關性" if lang == "zh" else "Duration Correlation",
                f"{dc:+.2f}",
                delta=("正相關" if dc > 0.2 else "負相關" if dc < -0.2 else "弱"),
            )
        with c2:
            qc = corr.get("quality_correlation", 0) or 0
            st.metric(
                "品質相關性" if lang == "zh" else "Quality Correlation",
                f"{qc:+.2f}",
                delta=("正相關" if qc > 0.2 else "負相關" if qc < -0.2 else "弱"),
            )

        if dc > 0.3 or qc > 0.3:
            st.success(
                "✓ 睡眠對你的訓練表現有顯著正向影響"
                if lang == "zh" else
                "✓ Sleep significantly improves your performance"
            )

    st.divider()
    st.subheader("💡 " + ("個人化建議" if lang == "zh"
                          else "Personalized Tips"))
    for rec in get_sleep_recommendations(user_id, lang):
        st.info(rec)
