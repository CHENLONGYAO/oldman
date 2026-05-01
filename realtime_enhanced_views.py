"""
即時 AI 私人教練視訊頁。

特色：
- 大畫面攝影機 + 骨架疊加（adaptive 30 FPS, MediaPipe complexity=2）
- One-Euro + Kalman 複合過濾，解剖學關節角度
- 即時 ROM 安全檢查
- LiveCoach：rep 計數、節奏與深度提示、不對稱警示
- 每 5 秒 Claude Haiku 4.5 視覺 LLM 補強教練建議
- TTS 像私人教練一樣口頭計數與提醒
- 卡通教練 avatar + 浮動提示氣泡
- 一層一層的 APP 風格 UI
"""
from __future__ import annotations
import time
from typing import List, Optional

import numpy as np
import streamlit as st

import ui
from auth import get_session_user

try:
    from streamlit_webrtc import (
        webrtc_streamer, WebRtcMode, VideoTransformerBase,
    )
    _WEBRTC_AVAILABLE = True
except ImportError:
    _WEBRTC_AVAILABLE = False
    webrtc_streamer = None
    WebRtcMode = None
    VideoTransformerBase = object

from realtime_engine import RealtimePoseEngine, EngineConfig
from biomechanics import compute_smoothness, compute_symmetry
from heatmap import render_joint_heatmap
from live_coach import (
    LiveCoach, LiveCoachConfig, CueKind, build_coach, EXERCISE_PRESETS,
)


# ============================================================
# 入口
# ============================================================
def view_realtime_enhanced():
    user = get_session_user()
    if not user:
        st.error("請先登入")
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")

    st.title(
        "👨‍🏫 " + ("即時 AI 私人教練" if lang == "zh" else "AI Personal Trainer")
    )
    st.caption(
        "即時動作偵測 × Claude Haiku 4.5 視覺 LLM × 解剖學關節分析 × 口語教學"
        if lang == "zh" else
        "Live pose tracking · Claude Haiku 4.5 vision · anatomical angles · spoken cues"
    )

    if not _WEBRTC_AVAILABLE:
        st.warning(
            "需要 streamlit-webrtc：pip install streamlit-webrtc"
            if lang == "zh" else
            "Requires streamlit-webrtc: pip install streamlit-webrtc"
        )
        return

    _ensure_state()

    # --- 上方控制條：選擇動作 / 目標次數 / VLM 開關 ---
    with ui.app_section(
        "教練設定" if lang == "zh" else "Coach Setup",
        icon="🎯",
    ):
        _render_setup(lang)

    # --- 主畫面：左 = 攝影機；右 = 教練 + 計數 ---
    main_left, main_right = st.columns([3, 2], gap="large")

    with main_left:
        with ui.app_section(
            "訓練畫面" if lang == "zh" else "Live Camera",
            icon="🎥",
        ):
            ctx = _render_camera(lang)

    with main_right:
        with ui.app_section(
            "教練回饋" if lang == "zh" else "Coach",
            icon="🧑‍🏫",
        ):
            _render_coach_panel(lang)

    # 啟動／停止 LiveCoach 與引擎根據 webrtc 狀態
    _sync_engine_lifecycle(ctx, lang)

    # 主要面板（rep / 節奏 / 形體分數）
    with ui.app_section(
        "即時指標" if lang == "zh" else "Live Metrics",
        icon="📊",
    ):
        _render_metrics(lang)

    # 進階指標
    with st.expander(
        "🔬 " + ("進階分析" if lang == "zh" else "Advanced Analysis"),
        expanded=False,
    ):
        _render_advanced(lang)


# ============================================================
# 狀態初始化
# ============================================================
def _ensure_state() -> None:
    ss = st.session_state
    ss.setdefault("rt_engine", None)
    ss.setdefault("rt_coach", None)
    ss.setdefault("rt_latest_frame", None)
    ss.setdefault("rt_cue_log", [])
    ss.setdefault("rt_exercise_key", "mini_squat")
    ss.setdefault("rt_target_reps", 12)
    ss.setdefault("rt_vlm_enabled", True)
    ss.setdefault("rt_speak", True)
    ss.setdefault("rt_session_started_at", None)


# ============================================================
# 設定區
# ============================================================
def _render_setup(lang: str) -> None:
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])

    exercise_options = list(EXERCISE_PRESETS.keys())
    labels_zh = {
        "arm_raise": "雙手上舉", "shoulder_abduction": "肩側平舉",
        "elbow_flexion": "肘屈伸", "mini_squat": "迷你深蹲",
        "sit_to_stand": "坐到站", "knee_extension": "膝伸展",
        "hip_abduction": "髖外展", "march_in_place": "原地踏步",
    }

    with c1:
        new_ex = st.selectbox(
            "選擇動作" if lang == "zh" else "Exercise",
            options=exercise_options,
            index=exercise_options.index(st.session_state.rt_exercise_key)
                if st.session_state.rt_exercise_key in exercise_options else 0,
            format_func=lambda k: (
                labels_zh.get(k, k) if lang == "zh"
                else k.replace("_", " ").title()
            ),
            key="rt_ex_select",
        )
        if new_ex != st.session_state.rt_exercise_key:
            st.session_state.rt_exercise_key = new_ex
            _maybe_reset_coach()

    with c2:
        new_reps = st.number_input(
            "目標次數" if lang == "zh" else "Target Reps",
            min_value=1, max_value=50,
            value=int(st.session_state.rt_target_reps),
            key="rt_target_reps_input",
        )
        if new_reps != st.session_state.rt_target_reps:
            st.session_state.rt_target_reps = int(new_reps)
            _maybe_reset_coach()

    with c3:
        st.session_state.rt_vlm_enabled = st.toggle(
            "AI 視覺" if lang == "zh" else "AI Vision",
            value=st.session_state.rt_vlm_enabled,
            help=("每 5 秒由 Claude Haiku 4.5 給形體建議"
                  if lang == "zh" else
                  "Claude Haiku 4.5 form check every 5s"),
        )
    with c4:
        st.session_state.rt_speak = st.toggle(
            "語音計數" if lang == "zh" else "Voice Cues",
            value=st.session_state.rt_speak,
        )


def _maybe_reset_coach() -> None:
    """設定改變 → 下一次啟動時重建 coach。"""
    coach: Optional[LiveCoach] = st.session_state.get("rt_coach")
    if coach:
        coach.stop()
    st.session_state.rt_coach = None


# ============================================================
# 攝影機
# ============================================================
def _render_camera(lang: str):
    class FrameProvider(VideoTransformerBase):
        def transform(self, frame):
            img = frame.to_ndarray(format="bgr24")
            st.session_state.rt_latest_frame = img
            return img

    ctx = webrtc_streamer(
        key="rt-coach",
        mode=WebRtcMode.SENDRECV,
        video_transformer_factory=FrameProvider,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )

    if not (ctx and ctx.state.playing):
        st.info(
            "👆 " + ("點擊 START 開始訓練" if lang == "zh"
                     else "Click START to begin")
        )
    return ctx


# ============================================================
# 教練面板（右側）
# ============================================================
def _render_coach_panel(lang: str) -> None:
    coach: Optional[LiveCoach] = st.session_state.get("rt_coach")

    avatar = "🧑‍🏫"
    try:
        from coach import CHARACTERS
        persona = st.session_state.get("settings", {}).get("coach", "starbuddy")
        info = CHARACTERS.get(persona, {})
        avatar = info.get("emoji", avatar)
    except ImportError:
        pass

    if coach is None:
        st.markdown(
            f'<div class="coach-bubble-wrap">'
            f'<div class="coach-emoji">{avatar}</div>'
            f'<div class="coach-bubble">'
            + ("等你開始攝影機，我就上線教學。" if lang == "zh"
               else "Start the camera and I'll be right with you.")
            + '</div></div>',
            unsafe_allow_html=True,
        )
        return

    # 取得最新提示（不消費，只 peek）
    history = coach.history(8)
    latest = history[-1] if history else None
    bubble_text = (
        latest.text(lang) if latest
        else ("做動作我就會開始計數和提示。" if lang == "zh"
              else "Move and I'll start counting & cueing.")
    )
    bubble_severity = latest.severity if latest else "info"

    color_map = {
        "info": "#007aff",
        "success": "#34c759",
        "warn": "#ff9500",
        "danger": "#ff3b30",
    }
    accent = color_map.get(bubble_severity, "#007aff")

    st.markdown(
        f'''
        <div class="coach-bubble-wrap">
            <div class="coach-emoji">{avatar}</div>
            <div class="coach-bubble" style="border-color: {accent};">
                <div class="coach-bubble-tag" style="color:{accent};">
                    {_kind_label(latest.kind if latest else CueKind.READY, lang)}
                </div>
                <div class="coach-bubble-text">{bubble_text}</div>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # 最近 N 條提示
    st.markdown(
        f'<div class="section-hdr">{"最近提示" if lang == "zh" else "Recent Cues"}</div>',
        unsafe_allow_html=True,
    )
    if not history[:-1]:
        st.caption("—")
    else:
        for cue in reversed(history[:-1][-6:]):
            sev_color = color_map.get(cue.severity, "#8e8e93")
            tag = _kind_label(cue.kind, lang)
            text = cue.text(lang)
            badge = "🤖" if cue.source == "vlm" else ""
            st.markdown(
                f'<div class="cue-row" style="border-left-color:{sev_color}">'
                f'<span class="cue-tag" style="color:{sev_color}">{tag}</span>'
                f'<span class="cue-text">{badge} {text}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # CSS（局部注入）
    st.markdown(_COACH_PANEL_CSS, unsafe_allow_html=True)


_COACH_PANEL_CSS = """
<style>
.coach-bubble-wrap {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    margin-bottom: 0.7rem;
}
.coach-emoji {
    font-size: 2.6rem;
    flex-shrink: 0;
    line-height: 1;
    filter: drop-shadow(0 4px 8px rgba(0,0,0,0.08));
}
.coach-bubble {
    flex: 1;
    background: #ffffff;
    border: 2px solid #007aff;
    border-radius: 16px;
    padding: 0.85rem 1rem;
    position: relative;
    box-shadow: 0 6px 18px rgba(0,0,0,0.06);
    transition: border-color 0.25s ease;
}
.coach-bubble::before {
    content: '';
    position: absolute;
    left: -10px;
    top: 14px;
    width: 0; height: 0;
    border-top: 8px solid transparent;
    border-bottom: 8px solid transparent;
    border-right: 10px solid #ffffff;
    z-index: 1;
}
.coach-bubble-tag {
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
}
.coach-bubble-text {
    font-size: 1rem;
    font-weight: 600;
    color: #1c1c1e;
    line-height: 1.4;
}
.cue-row {
    display: flex;
    gap: 0.55rem;
    align-items: baseline;
    padding: 0.5rem 0.7rem;
    border-left: 3px solid #8e8e93;
    background: #f7f8fa;
    border-radius: 10px;
    margin-bottom: 0.4rem;
}
.cue-tag {
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    flex-shrink: 0;
    min-width: 56px;
}
.cue-text {
    font-size: 0.88rem;
    color: #3a3a3c;
    line-height: 1.35;
}
</style>
"""


def _kind_label(kind: CueKind, lang: str) -> str:
    table_zh = {
        CueKind.REP_COUNT: "計數",
        CueKind.DEPTH: "深度",
        CueKind.TEMPO: "節奏",
        CueKind.SAFETY: "安全",
        CueKind.SYMMETRY: "對稱",
        CueKind.ENCOURAGE: "鼓勵",
        CueKind.READY: "預備",
        CueKind.REST: "休息",
        CueKind.VLM: "AI 視覺",
    }
    table_en = {
        CueKind.REP_COUNT: "COUNT",
        CueKind.DEPTH: "DEPTH",
        CueKind.TEMPO: "TEMPO",
        CueKind.SAFETY: "SAFETY",
        CueKind.SYMMETRY: "SYMMETRY",
        CueKind.ENCOURAGE: "NICE",
        CueKind.READY: "READY",
        CueKind.REST: "REST",
        CueKind.VLM: "AI VISION",
    }
    return (table_zh if lang == "zh" else table_en).get(kind, kind.value)


# ============================================================
# 引擎與教練生命週期
# ============================================================
def _sync_engine_lifecycle(ctx, lang: str) -> None:
    if not ctx:
        return

    if ctx.state.playing:
        if st.session_state.rt_engine is None:
            engine = RealtimePoseEngine(
                frame_provider=lambda: st.session_state.rt_latest_frame,
                config=EngineConfig(
                    target_fps=30,
                    use_holistic=False,
                    initial_complexity=2,
                    adaptive_quality=True,
                ),
            )
            engine.start()
            st.session_state.rt_engine = engine

        if st.session_state.rt_coach is None:
            coach = build_coach(
                exercise_key=st.session_state.rt_exercise_key,
                target_reps=st.session_state.rt_target_reps,
                lang=lang,
                frame_provider=lambda: st.session_state.rt_latest_frame,
                voice=_resolve_voice() if st.session_state.rt_speak else None,
                vlm_enabled=st.session_state.rt_vlm_enabled,
            )
            coach.start()
            st.session_state.rt_coach = coach
            st.session_state.rt_session_started_at = time.time()

        # 把當前狀態餵給 coach
        engine: RealtimePoseEngine = st.session_state.rt_engine
        coach: LiveCoach = st.session_state.rt_coach
        state = engine.get_latest_state()
        if state and state.timestamp:
            new_cues = coach.observe(state)
            if new_cues:
                st.session_state.rt_cue_log = (
                    st.session_state.rt_cue_log + new_cues
                )[-50:]
    else:
        # 攝影機停止 → 釋放資源
        if st.session_state.rt_coach is not None:
            st.session_state.rt_coach.stop()
            st.session_state.rt_coach = None
        if st.session_state.rt_engine is not None:
            st.session_state.rt_engine.stop()
            st.session_state.rt_engine = None


def _resolve_voice():
    """取出全域 voice guide（若不可用則回 None）。"""
    voice = st.session_state.get("voice_guide")
    if voice is not None:
        return voice
    try:
        from tts import VoiceGuide
        guide = VoiceGuide(lang=st.session_state.get(
            "settings", {}).get("lang", "zh"))
        st.session_state.voice_guide = guide
        return guide
    except Exception:
        return None


# ============================================================
# 即時指標：rep / 節奏 / 形體分數
# ============================================================
def _render_metrics(lang: str) -> None:
    coach: Optional[LiveCoach] = st.session_state.get("rt_coach")
    engine: Optional[RealtimePoseEngine] = st.session_state.get("rt_engine")

    if coach is None or engine is None:
        st.caption("—")
        return

    state = engine.get_latest_state()
    rep = coach.rep_counter
    target = coach.cfg.cues.target_reps
    pct = min(100, int(100 * rep.count / max(1, target)))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "Rep",
            f"{rep.count} / {target}",
            delta=f"{pct}%",
        )
    with c2:
        st.metric(
            "上一下幅度" if lang == "zh" else "Last amplitude",
            f"{rep.last_amplitude:.0f}°",
        )
    with c3:
        st.metric(
            "平均節奏" if lang == "zh" else "Avg tempo",
            f"{rep.avg_duration:.1f} s" if rep.avg_duration else "—",
        )
    with c4:
        st.metric(
            "FPS",
            f"{state.fps:.1f}" if state else "—",
            delta=(f"-{state.frames_skipped} 跳過" if lang == "zh"
                   else f"-{state.frames_skipped} skipped") if state else None,
        )

    st.progress(pct / 100,
                text=("組進度" if lang == "zh" else "Set progress"))

    # 動作中即時 ROM 警示
    if state and state.rom_violations:
        sev_emoji = {
            "severe": "🚨", "moderate": "⚠️", "mild": "ℹ️"
        }
        for v in state.rom_violations[:3]:
            emoji = sev_emoji.get(v.severity, "⚠️")
            st.warning(
                f"{emoji} {v.angle_name}: {v.value:.1f}° "
                f"(範圍 {v.rom_min:.0f}–{v.rom_max:.0f}°)"
                if lang == "zh" else
                f"{emoji} {v.angle_name}: {v.value:.1f}° "
                f"(range {v.rom_min:.0f}–{v.rom_max:.0f}°)"
            )

    # 主關節即時角度（4 顆）
    if state and state.angles_smoothed:
        major = [
            ("left_shoulder_flex_ext", "左肩" if lang == "zh" else "L Shoulder"),
            ("right_shoulder_flex_ext", "右肩" if lang == "zh" else "R Shoulder"),
            ("left_knee_flex", "左膝" if lang == "zh" else "L Knee"),
            ("right_knee_flex", "右膝" if lang == "zh" else "R Knee"),
        ]
        cols = st.columns(4)
        for i, (key, label) in enumerate(major):
            v = state.angles_smoothed.get(key)
            if v is None:
                continue
            with cols[i]:
                st.metric(label, f"{v:+.0f}°")

    # 控制
    cb1, cb2, cb3 = st.columns(3)
    with cb1:
        if st.button(
            "🔄 " + ("重設計數" if lang == "zh" else "Reset reps"),
            use_container_width=True,
            key="rt_reset_reps",
        ):
            coach.reset()
            st.toast("✓ Reset")
    with cb2:
        if st.button(
            "🔇 " + ("靜音切換" if lang == "zh" else "Toggle voice"),
            use_container_width=True,
            key="rt_voice_toggle",
        ):
            st.session_state.rt_speak = not st.session_state.rt_speak
            st.rerun()
    with cb3:
        if st.button(
            "⏹ " + ("結束此組" if lang == "zh" else "End set"),
            use_container_width=True,
            key="rt_end_set",
        ):
            coach.reset()
            st.toast(
                "✓ " + ("已結束，準備下一組" if lang == "zh"
                        else "Ready for next set")
            )


# ============================================================
# 進階分析（折疊）
# ============================================================
def _render_advanced(lang: str) -> None:
    engine: Optional[RealtimePoseEngine] = st.session_state.get("rt_engine")
    if engine is None:
        st.caption("—")
        return

    history = engine.get_history(n=240)
    if len(history) < 8:
        st.caption(
            "資料蒐集中…" if lang == "zh" else "Collecting samples…"
        )
        return

    from realtime_engine import angles_time_series

    cols = st.columns(3)

    _, l_knee = angles_time_series(history, "left_knee_flex")
    _, r_knee = angles_time_series(history, "right_knee_flex")

    if len(l_knee) >= 8:
        sparc = compute_smoothness(l_knee)
        with cols[0]:
            st.metric(
                "平滑度 (SPARC)" if lang == "zh" else "Smoothness",
                f"{sparc:.2f}",
                help=("接近 0 = 越平滑" if lang == "zh"
                      else "Closer to 0 = smoother"),
            )

    if len(l_knee) >= 5 and len(r_knee) >= 5:
        si = compute_symmetry(l_knee, r_knee)
        with cols[1]:
            st.metric(
                "對稱性指數" if lang == "zh" else "Symmetry Index",
                f"{si:.1f}",
                help=("低 = 雙側對稱" if lang == "zh"
                      else "Low = symmetric"),
            )

    avg_inf = float(np.mean(
        [s.inference_ms for s in history if s.inference_ms]
    ) or 0.0)
    with cols[2]:
        st.metric(
            "平均推論時間" if lang == "zh" else "Avg Inference",
            f"{avg_inf:.0f} ms",
        )

    with st.expander(
        "🔥 " + ("關節熱圖" if lang == "zh" else "Joint Heatmap"),
    ):
        if len(history) >= 5:
            render_joint_heatmap(history, lang=lang)
