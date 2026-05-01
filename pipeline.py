"""
完整評分流程：把世界座標序列 → 角度 → DTW → 神經評分 → 整體分數 → 儲存 → 跳轉結果頁。

被 `views.view_analyze`（上傳影片路徑）與 `views._render_live_tab`（即時鏡頭結束）
共同呼叫。執行結束後會 `goto("result")`，呼叫端不需處理後續。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Optional

import numpy as np
import streamlit as st

import history as hist
import scoring
from app_state import (
    emit_new_badge_toasts,
    get_voice,
    goto,
    load_scorers,
    user_history_key,
)


def run_pipeline(
    seq: list,
    frames: list,
    fps: float,
    tpl: dict,
    progress: Optional[object] = None,
) -> None:
    """共用評分流程。

    seq    : list[(33,3)] 世界座標序列
    frames : list[dict]   結果頁顯示用影格
    fps    : float        原始 FPS
    tpl    : dict         動作範本
    """

    def _p(v: int, txt: str = "") -> None:
        if progress is not None:
            progress.progress(v, text=txt)

    # 1. 角度時間序列
    _p(40, "Computing angle series…")
    patient_series = scoring.sequence_to_angle_series(seq)

    # 2. DTW 對齊與每關節偏差
    _p(60, "DTW alignment…")
    template_series = {
        k: np.asarray(v, dtype=np.float32)
        for k, v in tpl["angle_series"].items()
    }
    joint_scores = scoring.score_joint_series(
        patient_series, template_series,
    )

    # 3. 重複次數
    rep_count = len(scoring.detect_reps(
        patient_series, exercise_hint=tpl["key"],
    ))

    # 4. 神經評分（可選）
    _p(75, "Neural quality scoring…")
    neural_scores: dict = {}
    angle_feats = scoring.angle_feature_matrix(patient_series)
    for arch, sc in load_scorers().items():
        if sc and sc.available:
            try:
                val = sc.predict(
                    seq_world=np.stack(seq, axis=0),
                    angle_feats=angle_feats,
                )
                if val is not None:
                    neural_scores[arch.upper()] = val
            except Exception:
                pass

    # 5. 綜合分數 + 文字回饋
    _p(90, "Composing feedback…")
    settings = st.session_state.settings
    user = st.session_state.get("user") or {}
    senior = settings.get("senior_mode", True)
    age = int(user.get("age") or 65)
    age_for_bonus = age if senior else None
    dtw_score = scoring.overall_score(joint_scores, age=age_for_bonus)
    blended = scoring.blend_scores(
        dtw_score,
        np.mean(list(neural_scores.values()))
        if neural_scores else None,
        neural_weight=settings.get("neural_weight", 0.4),
    )
    threshold = settings.get("threshold", 15.0)
    msgs = scoring.feedback_messages(joint_scores, threshold=threshold)
    # 結構化方向提示（含上/下 + 嚴重度），供 cue_grid 顯示與語音播報
    cues = scoring.feedback_cues(
        patient_series, template_series, threshold=threshold,
    )

    # 6. 儲存紀錄
    name = user_history_key(user)
    display_name = user.get("name") or user.get("username") or name
    is_pb = hist.is_new_personal_best(name, tpl["name"], blended)
    pain_before = int(st.session_state.get("pain_before", 0))
    safety_flag = "high_pain_before" if pain_before >= 7 else None
    session_id = str(uuid.uuid4())
    hist.save_session(
        name, tpl["name"], blended, joint_scores,
        age,
        rep_count=rep_count,
        neural_scores=neural_scores or None,
        pain_before=pain_before,
        safety_flag=safety_flag,
        display_name=display_name,
    )
    if user.get("user_id"):
        try:
            from db import insert_session
            insert_session(
                session_id=session_id,
                user_id=user["user_id"],
                exercise=tpl["name"],
                score=float(blended),
                rep_count=rep_count,
                joints_json=json.dumps(joint_scores, ensure_ascii=False),
                neural_scores_json=json.dumps(neural_scores or {}, ensure_ascii=False),
                pain_before=pain_before,
                safety_flag=safety_flag,
            )
        except Exception:
            pass
    _, streak = hist.compute_badges(name)
    xp_gain = hist.xp_for_session(blended, is_pb, streak)
    xp_total = hist.add_xp(name, xp_gain)

    _p(100, "Done.")
    time.sleep(0.2)

    # 7. 寫入結果頁狀態
    st.session_state.analysis = {
        "score": blended,
        "dtw_score": dtw_score,
        "neural_scores": neural_scores,
        "joints": joint_scores,
        "messages": msgs,
        "cues": cues,
        "frames": frames,
        "template": tpl,
        "patient_series": patient_series,
        "template_series": template_series,
        "rep_count": rep_count,
        "fps": fps,
        "session_id": session_id,
        "is_pb": is_pb,
        "xp_gain": xp_gain,
        "xp_total": xp_total,
    }
    # 結果頁進入時自動播語音用旗標
    st.session_state.pending_voice = True

    voice = get_voice()
    if voice:
        # 改用方向式短句：「右肩請抬高。左膝請彎曲。」
        voice.say_cues(
            cues, score=blended,
            lang=settings.get("lang", "zh"),
        )

    emit_new_badge_toasts(name)
    st.toast(f"+{xp_gain} XP", icon="⭐")
    goto("result")
