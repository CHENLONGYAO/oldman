"""
Auto Exercise view: upload a video, get full automated analysis.

Pipeline:
1. Extract pose with EnhancedPoseEstimator
2. Auto-classify exercise type (action_recognition)
3. Auto-segment reps (exercise_segmentation)
4. Critique form (form_critic) against best matching template
5. (Optional) Get VLM feedback on keyframes (Claude vision)
6. Show all results in a unified dashboard
"""
from __future__ import annotations
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

from auth import get_session_user

from enhanced_pose import (
    process_video,
    EnhancedPoseEstimator,
    PoseEstimatorConfig,
)
from action_recognition import classify, EXERCISE_RULES
from exercise_segmentation import segment_session
from form_critic import critique_session
from biomechanics import compute_smoothness, compute_symmetry
from heatmap import render_joint_heatmap


def view_auto_exercise():
    """Auto-analysis view: upload video → full report."""
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")

    st.title("🤖 " + ("自動分析" if lang == "zh" else "Auto Analysis"))
    st.caption(
        "上傳訓練影片，AI 自動偵測動作類型、計次、分析姿勢、給予建議。"
        if lang == "zh" else
        "Upload a video — AI auto-detects exercise type, counts reps, "
        "critiques form, and gives advice."
    )

    with st.expander("⚙ " + ("分析設定" if lang == "zh" else "Settings")):
        col1, col2 = st.columns(2)
        with col1:
            complexity = st.select_slider(
                "模型複雜度" if lang == "zh" else "Model Complexity",
                options=[0, 1, 2],
                value=2,
                help="0=快, 2=最準" if lang == "zh"
                else "0=fast, 2=most accurate",
            )
            use_holistic = st.checkbox(
                "Holistic 模式（含臉部+雙手）" if lang == "zh"
                else "Holistic (face+hands)",
                value=False,
            )
        with col2:
            every_n = st.slider(
                "幀採樣間隔" if lang == "zh" else "Frame interval",
                1, 5, 1,
            )
            use_vlm = st.checkbox(
                "啟用 AI 視覺回饋（Claude）" if lang == "zh"
                else "Enable AI Vision Feedback (Claude)",
                value=False,
                help="需要 ANTHROPIC_API_KEY 環境變數",
            )

    uploaded = st.file_uploader(
        "上傳訓練影片" if lang == "zh" else "Upload training video",
        type=["mp4", "mov", "avi", "mkv"],
    )

    if not uploaded:
        st.info(
            "👆 " + ("上傳影片開始分析" if lang == "zh"
                     else "Upload a video to begin")
        )
        return

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=Path(uploaded.name).suffix
    ) as tmp:
        tmp.write(uploaded.read())
        video_path = tmp.name

    progress = st.progress(0, text="🎬 解析影片...")
    config = PoseEstimatorConfig(
        use_holistic=use_holistic,
        complexity=complexity,
    )

    try:
        seq, fps, frames = process_video(
            video_path, config=config, every_n_frames=every_n
        )
    except Exception as e:
        st.error(f"處理失敗 / Failed: {e}")
        return

    if len(seq) < 5:
        st.error("影片太短或無法偵測人體 / Video too short or no person detected")
        return

    progress.progress(25, text="🧠 分類動作...")
    prediction = classify(seq, fps)

    progress.progress(50, text="📏 切分動作週期...")
    seg = segment_session(seq, fps)

    progress.progress(75, text="🔍 評估姿勢...")
    template_seq = _load_template(prediction.exercise)
    if template_seq is not None:
        report = critique_session(seq, template_seq, fps=fps)
    else:
        report = None

    vlm_feedback = None
    if use_vlm:
        progress.progress(85, text="🎨 AI 視覺分析...")
        vlm_feedback = _try_vlm_feedback(
            video_path, seq, prediction, lang, report
        )

    progress.progress(100, text="✓ 完成")

    _render_results(seq, fps, prediction, seg, report,
                    vlm_feedback, lang)


def _load_template(exercise_key: str):
    """Load reference template world sequence for an exercise if available."""
    try:
        import templates as templates_mod
    except ImportError:
        return None

    tpl = templates_mod.get_template(exercise_key) if hasattr(
        templates_mod, "get_template"
    ) else None
    if tpl is None:
        return None

    try:
        ang = tpl.get("angle_series") if isinstance(tpl, dict) else None
        if ang:
            return None
    except Exception:
        pass
    return None


def _try_vlm_feedback(video_path: str, seq, prediction,
                       lang: str, form_report):
    """Try to get Claude vision feedback."""
    try:
        from vlm_feedback import get_feedback, select_keyframes, is_available
        if not is_available():
            st.warning(
                "未設定 ANTHROPIC_API_KEY，跳過 AI 視覺回饋"
                if lang == "zh"
                else "ANTHROPIC_API_KEY not set, skipping AI vision"
            )
            return None

        import cv2
        cap = cv2.VideoCapture(video_path)
        all_frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            all_frames.append(frame)
        cap.release()

        keyframes = select_keyframes(seq, all_frames, n_frames=4)

        analysis_dict = None
        if form_report:
            analysis_dict = {
                "score": form_report.overall_score,
                "concerns": form_report.top_concerns,
                "errors": [
                    {
                        "joint": e.primary_joint,
                        "severity": e.severity,
                        "deviation": round(e.deviation_deg, 1),
                    }
                    for e in form_report.errors[:5]
                ],
            }

        return get_feedback(
            keyframes,
            form_analysis=analysis_dict,
            exercise_name=prediction.exercise,
            lang=lang,
        )
    except Exception as e:
        st.warning(f"VLM unavailable: {e}")
        return None


def _render_results(seq, fps, prediction, seg, report,
                     vlm_feedback, lang: str) -> None:
    st.success("✅ " + ("分析完成" if lang == "zh" else "Analysis complete"))

    st.subheader("🎯 " + ("偵測動作" if lang == "zh" else "Detected Exercise"))
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "動作" if lang == "zh" else "Exercise",
            prediction.exercise,
        )
    with col2:
        st.metric(
            "信心度" if lang == "zh" else "Confidence",
            f"{prediction.confidence * 100:.0f}%",
        )
    with col3:
        st.metric(
            "時長" if lang == "zh" else "Duration",
            f"{prediction.duration_s:.1f}s",
        )

    if prediction.top_k:
        with st.expander("📊 " + ("候選動作" if lang == "zh"
                                  else "Top Candidates")):
            for ex, score in prediction.top_k:
                st.markdown(f"- **{ex}**: {score * 100:.1f}%")

    st.divider()
    st.subheader("📐 " + ("動作切分" if lang == "zh" else "Rep Segmentation"))
    cols = st.columns(4)
    with cols[0]:
        st.metric(
            "重複次數" if lang == "zh" else "Reps",
            seg.total_reps,
        )
    with cols[1]:
        st.metric(
            "平均時長" if lang == "zh" else "Avg Duration",
            f"{seg.avg_duration:.1f}s",
        )
    with cols[2]:
        st.metric(
            "平均幅度" if lang == "zh" else "Avg Amplitude",
            f"{seg.avg_amplitude:.0f}°",
        )
    with cols[3]:
        st.metric(
            "一致性" if lang == "zh" else "Consistency",
            f"{seg.consistency_score:.0f}%",
        )

    if seg.total_reps > 0:
        st.markdown(f"**{('主要關節' if lang == 'zh' else 'Dominant joint')}: "
                   f"{seg.dominant_joint}**")

        if len(seg.angle_series) > 0:
            import plotly.graph_objects as go
            fig = go.Figure()
            t_axis = np.arange(len(seg.angle_series)) / fps
            fig.add_trace(go.Scatter(
                x=t_axis, y=seg.angle_series,
                mode="lines",
                line=dict(color="#74b9ff", width=2),
                name=seg.dominant_joint,
            ))
            for i, rep in enumerate(seg.reps):
                fig.add_vrect(
                    x0=rep.start_frame / fps,
                    x1=rep.end_frame / fps,
                    fillcolor="green" if rep.quality > 0.7 else "yellow",
                    opacity=0.15,
                    line_width=0,
                    annotation_text=f"#{i+1}",
                    annotation_position="top left",
                )
            fig.update_layout(
                xaxis_title=("時間 (s)" if lang == "zh" else "Time (s)"),
                yaxis_title=("角度 (°)" if lang == "zh" else "Angle (°)"),
                height=300,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

    if report:
        st.divider()
        st.subheader("🔍 " + ("姿勢評估" if lang == "zh"
                              else "Form Critique"))

        cols = st.columns(2)
        with cols[0]:
            st.metric(
                "總分" if lang == "zh" else "Score",
                f"{report.overall_score:.1f}/100",
            )
        with cols[1]:
            st.metric(
                "問題數" if lang == "zh" else "Issues",
                len(report.errors),
            )

        st.info(report.summary_zh if lang == "zh" else report.summary_en)

        if report.errors:
            with st.expander(
                "❗ " + ("詳細問題" if lang == "zh" else "Detailed Issues")
            ):
                for err in report.errors[:5]:
                    sev_color = {
                        "major": "🔴", "moderate": "🟡", "minor": "🟢"
                    }.get(err.severity, "⚪")
                    text = err.feedback_zh if lang == "zh" else err.feedback_en
                    st.markdown(f"{sev_color} {text}")

    if vlm_feedback:
        st.divider()
        st.subheader("🎨 " + ("AI 視覺回饋" if lang == "zh"
                              else "AI Vision Feedback"))

        st.markdown(f"**{vlm_feedback.summary}**")

        if vlm_feedback.issues:
            for issue in vlm_feedback.issues:
                sev = issue.get("severity", "minor")
                emoji = {"major": "🔴", "moderate": "🟡",
                        "minor": "🟢"}.get(sev, "⚪")
                st.markdown(
                    f"{emoji} **{issue.get('joint', '')}** — "
                    f"{issue.get('description', '')}"
                )
                if issue.get("fix"):
                    st.caption(f"💡 {issue['fix']}")

        if vlm_feedback.encouragement:
            st.success(vlm_feedback.encouragement)

        if vlm_feedback.next_steps:
            st.markdown("**" + ("下一步" if lang == "zh"
                                else "Next Steps") + ":**")
            for step in vlm_feedback.next_steps:
                st.markdown(f"- {step}")
