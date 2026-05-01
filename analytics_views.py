"""
Analytics dashboard views: insights, predictions, cohort comparisons.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from auth import get_session_user
from analytics import (
    calculate_improvement_rate,
    calculate_adherence,
    detect_anomalies,
    predict_recovery_timeline,
    get_pain_trend,
    get_exercise_breakdown,
    compare_to_cohort,
)
from ml_insights import (
    calculate_risk_score,
    recommend_exercises,
    predict_optimal_training_time,
    get_personalized_insights,
)


def view_analytics():
    """Personal analytics dashboard for current user."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    user_id = user["user_id"]

    st.title("📊 " + ("個人分析儀表板" if lang == "zh" else "Personal Analytics"))

    insights = get_personalized_insights(user_id)
    if insights:
        st.subheader("💡 " + ("個人化洞察" if lang == "zh" else "Personalized Insights"))
        cols = st.columns(min(3, len(insights)))
        for i, insight in enumerate(insights):
            with cols[i % len(cols)]:
                with st.container(border=True):
                    title = insight["title_zh"] if lang == "zh" else insight["title_en"]
                    msg = insight["msg_zh"] if lang == "zh" else insight["msg_en"]
                    st.markdown(f"### {insight['icon']} {title}")
                    if insight["type"] == "positive":
                        st.success(msg)
                    elif insight["type"] == "warning":
                        st.warning(msg)
                    else:
                        st.info(msg)

    st.divider()
    st.subheader("📈 " + ("關鍵指標" if lang == "zh" else "Key Metrics"))

    col1, col2, col3, col4 = st.columns(4)

    improvement = calculate_improvement_rate(user_id)
    with col1:
        delta_str = f"{improvement['rate']:+.1f}%"
        st.metric(
            "進步率" if lang == "zh" else "Improvement Rate",
            f"{improvement['current']:.1f}",
            delta=delta_str,
        )

    adherence = calculate_adherence(user_id)
    with col2:
        st.metric(
            "參與度" if lang == "zh" else "Adherence",
            f"{adherence['adherence_pct']:.0f}%",
            delta=f"{adherence['weeks_met']}/{adherence['total_weeks']} 週" if lang == "zh"
                  else f"{adherence['weeks_met']}/{adherence['total_weeks']} weeks",
        )

    cohort = compare_to_cohort(user_id)
    with col3:
        if cohort.get("user_avg") is not None:
            st.metric(
                "與群體比較" if lang == "zh" else "vs Cohort",
                f"{cohort['user_avg']:.1f}",
                delta=f"{cohort['pct_vs_cohort']:+.1f}%",
            )
        else:
            st.metric("與群體比較" if lang == "zh" else "vs Cohort", "—")

    risk = calculate_risk_score(user_id)
    with col4:
        risk_label = "風險評分" if lang == "zh" else "Risk Score"
        st.metric(
            risk_label,
            f"{risk['risk_score']}/100",
            delta=risk["level_zh"] if lang == "zh" else risk["level"],
            delta_color="inverse",
        )

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("🎯 " + ("恢復預測" if lang == "zh" else "Recovery Prediction"))
        target = st.slider(
            "目標分數" if lang == "zh" else "Target Score",
            50, 100, 85, key="target_score"
        )
        prediction = predict_recovery_timeline(user_id, target_score=float(target))

        if prediction["estimated_days"] is not None:
            st.markdown(
                f"**{'預計達成日期' if lang == 'zh' else 'Estimated Date'}：** "
                f"{prediction['estimated_date']}"
            )
            st.markdown(
                f"**{'預計天數' if lang == 'zh' else 'Estimated Days'}：** "
                f"{prediction['estimated_days']} 天"
            )
            st.caption(
                f"{'信心度' if lang == 'zh' else 'Confidence'}: "
                f"{prediction['confidence']} ({prediction.get('samples', 0)} samples)"
            )
        else:
            confidence = prediction.get("confidence", "low")
            if confidence == "stable":
                st.info("分數穩定，繼續維持" if lang == "zh"
                       else "Stable score, keep it up")
            elif confidence == "declining":
                st.warning("分數下降趨勢，建議調整訓練" if lang == "zh"
                          else "Declining trend, consider adjustment")
            else:
                st.info("資料不足，多訓練幾次即可預測" if lang == "zh"
                       else "Need more data for prediction")

    with col_b:
        st.subheader("🩹 " + ("疼痛趨勢" if lang == "zh" else "Pain Trend"))
        pain = get_pain_trend(user_id)

        if pain["samples"] > 0:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=["訓練前" if lang == "zh" else "Before",
                   "訓練後" if lang == "zh" else "After"],
                y=[pain["avg_before"], pain["avg_after"]],
                marker_color=["#ff6b6b", "#51cf66"],
            ))
            fig.update_layout(
                yaxis_title="平均疼痛 (0-10)" if lang == "zh" else "Avg Pain (0-10)",
                height=250,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"{'樣本' if lang == 'zh' else 'Samples'}: {pain['samples']}")
        else:
            st.info("尚無疼痛數據" if lang == "zh" else "No pain data yet")

    st.divider()
    st.subheader("💪 " + ("動作分析" if lang == "zh" else "Exercise Breakdown"))

    breakdown = get_exercise_breakdown(user_id)
    if breakdown:
        df = pd.DataFrame(breakdown)
        fig = px.bar(
            df, x="exercise", y="avg_score",
            color="consistency",
            color_continuous_scale="Viridis",
            labels={
                "exercise": "動作" if lang == "zh" else "Exercise",
                "avg_score": "平均分數" if lang == "zh" else "Avg Score",
                "consistency": "穩定性" if lang == "zh" else "Consistency",
            },
        )
        fig.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("詳細統計" if lang == "zh" else "Detailed Stats"):
            st.dataframe(df, use_container_width=True)
    else:
        st.info("尚無訓練數據" if lang == "zh" else "No training data yet")

    st.divider()
    st.subheader("🎯 " + ("推薦動作" if lang == "zh" else "Recommended Exercises"))

    recommendations = recommend_exercises(user_id, top_k=3)
    if recommendations:
        rec_cols = st.columns(len(recommendations))
        for i, rec in enumerate(recommendations):
            with rec_cols[i]:
                with st.container(border=True):
                    st.markdown(f"**{rec['exercise']}**")
                    st.metric(
                        "平均分" if lang == "zh" else "Avg Score",
                        f"{rec['avg_score']:.1f}",
                    )
                    st.caption(
                        f"{'最後練習' if lang == 'zh' else 'Last done'}: "
                        f"{rec['days_since']} {'天前' if lang == 'zh' else 'days ago'}"
                    )
                    for reason in rec["reasons"][:2]:
                        st.caption(f"• {reason}")
    else:
        st.info("需要更多訓練數據" if lang == "zh" else "Need more training data")

    if risk["risk_score"] >= 50:
        st.divider()
        st.error("⚠️ " + ("高風險警示" if lang == "zh" else "High Risk Alert"))
        st.markdown("**" + ("風險因素" if lang == "zh" else "Risk Factors") + ":**")
        for factor in risk["factors"]:
            st.markdown(f"- {factor}")
        st.info(
            "建議與治療師聯絡以調整計畫。"
            if lang == "zh"
            else "Consider contacting your therapist to adjust the plan."
        )

    st.divider()
    st.subheader("🔍 " + ("異常偵測" if lang == "zh" else "Anomaly Detection"))

    anomalies = detect_anomalies(user_id)
    if anomalies:
        st.warning(
            f"偵測到 {len(anomalies)} 個異常表現"
            if lang == "zh"
            else f"Detected {len(anomalies)} anomalies"
        )
        anomaly_df = pd.DataFrame(anomalies)
        st.dataframe(anomaly_df, use_container_width=True)
    else:
        st.success("未偵測到異常" if lang == "zh" else "No anomalies detected")
