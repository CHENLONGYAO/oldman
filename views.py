"""
所有畫面（view_*）。每個函式對應 ROUTES 中的一條路由。
依序：歡迎、基本資料、首頁、錄影、分析、結果、進度、自訂範本、臨床、設定。

這個檔案不負責路由與側欄（在 app.py），也不直接處理評分流程
（在 pipeline.py），主要任務是把使用者輸入轉成對狀態的更新與畫面元件。
"""
from __future__ import annotations

import sys
import tempfile
import time
import re
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st

import ai_coach
import coach as coach_mod
import history as hist
import pose_estimator as pe
import report
import scoring
import templates as tpl_mod
import ui
import visualizer as viz
from app_state import (
    DIFFICULTY_PRESETS,
    apply_difficulty,
    daily_challenge_key,
    get_voice,
    goto,
    lang as get_lang,
    load_lifter,
    load_scorers,
    user_history_key,
)
from i18n import LANGS, language_label, t
from pipeline import run_pipeline


def _show_pose_engine_unavailable(lang: str) -> None:
    """Show a friendly, actionable message when MediaPipe Pose is unavailable."""
    st.error(
        "姿態分析引擎尚未就緒，其他功能仍可繼續使用。"
        if lang == "zh"
        else "The pose analysis engine is not ready; the rest of the app is still available."
    )
    st.caption(
        f"Python: {sys.version.split()[0]}  |  "
        f"Executable: {sys.executable}"
    )
    with st.expander(
        "修復建議" if lang == "zh" else "Troubleshooting",
        expanded=False,
    ):
        st.code(pe.pose_error_message(), language="text")


# New modules for comprehensive health management
try:
    import journal
    import programs
    import reminders
    import sync_manager
except ImportError:
    journal = None
    programs = None
    reminders = None
    sync_manager = None

# New modules for therapist management
try:
    from therapist_dashboard import view_therapist_dashboard
except ImportError:
    def view_therapist_dashboard():
        st.error("Therapist dashboard not available")

# New module for advanced analytics
try:
    from analytics_views import view_analytics
except ImportError:
    def view_analytics():
        st.error("Analytics not available")

# New module for games
try:
    from games_views import view_games
except ImportError:
    def view_games():
        st.error("Games not available")

# New module for wearable device integration
try:
    from wearables_views import view_wearables
except ImportError:
    def view_wearables():
        st.error("Wearables not available")

# New module for cloud backup
try:
    from cloud_sync_views import view_cloud_sync
except ImportError:
    def view_cloud_sync():
        st.error("Cloud sync not available")

# Phase 8: AI chat coach
try:
    from ai_chat_views import view_ai_chat
except ImportError:
    def view_ai_chat():
        st.error("AI chat not available")

# Phase 8: Quests
try:
    from quests_views import view_quests
except ImportError:
    def view_quests():
        st.error("Quests not available")

# Phase 8: Nutrition
try:
    from nutrition_views import view_nutrition
except ImportError:
    def view_nutrition():
        st.error("Nutrition not available")

# Phase 8: Sleep
try:
    from sleep_views import view_sleep
except ImportError:
    def view_sleep():
        st.error("Sleep tracker not available")

# Phase 8: Notifications
try:
    from notifications_views import view_notifications
except ImportError:
    def view_notifications():
        st.error("Notifications not available")

# Phase 8: Audit log
try:
    from audit_views import view_audit_log
except ImportError:
    def view_audit_log():
        st.error("Audit log not available")

# Phase 9: Enhanced realtime engine (high-accuracy pose + biofeedback)
try:
    from realtime_enhanced_views import view_realtime_enhanced
except ImportError:
    def view_realtime_enhanced():
        st.error("Enhanced realtime not available")

# Phase 10: Auto exercise — full automated pipeline
try:
    from auto_exercise_views import view_auto_exercise
except ImportError:
    def view_auto_exercise():
        st.error("Auto exercise not available")

# Phase 11: Daily routine (orchestrated home)
try:
    from daily_routine_views import view_daily_routine
except ImportError:
    def view_daily_routine():
        st.error("Daily routine not available")


def _current_user_name() -> str:
    return user_history_key(st.session_state.get("user") or {})


def _current_user_display_name() -> str:
    user = st.session_state.get("user") or {}
    if isinstance(user, str):
        return user.strip()
    if isinstance(user, dict):
        return str(user.get("name") or user.get("username") or "").strip()
    return ""


def _require_user_name(lang: str) -> str | None:
    name = _current_user_name()
    if not name:
        st.warning(t("not_logged_in", lang))
        return None
    return name


def _active_user_id() -> str | None:
    user = st.session_state.get("user") or {}
    return user.get("user_id") if isinstance(user, dict) else None


def _save_profile_to_db(profile: dict) -> None:
    user_id = _active_user_id()
    if not user_id:
        return
    try:
        from db import update_user_profile
        update_user_profile(user_id, **profile)
    except Exception as exc:
        st.warning(f"SQLite profile sync failed: {exc}")


def _sync_session_pain_to_db(pain_after: int, safety_flag: str | None) -> None:
    analysis = st.session_state.get("analysis") or {}
    session_id = analysis.get("session_id")
    if not session_id:
        return
    try:
        from db import update_session_fields
        update_session_fields(
            session_id,
            pain_after=int(pain_after),
            safety_flag=safety_flag,
        )
    except Exception:
        pass


# ============================================================
# 歡迎
# ============================================================
def view_welcome() -> None:
    lang = get_lang()
    # ===== Apple 巨字 hero =====
    ui.apple_hero(
        eyebrow="智慧居家復健" if lang == "zh"
                else "SMART HOME REHAB",
        headline="人人都能在家做的專業復健"
                 if lang == "zh"
                 else "Professional rehab. From home.",
        sub=t("welcome_desc", lang),
    )

    # 主 CTA 居中
    cta_l, cta_m, cta_r = st.columns([1, 2, 1])
    with cta_m:
        if st.button(
            "▶ " + t("start", lang),
            type="primary", use_container_width=True,
            key="welcome_start",
        ):
            goto("profile")
        st.caption(
            ("MediaPipe 3D · MotionAGFormer · DTW · STGCN / LSTM"
             if lang == "zh"
             else "MediaPipe 3D · MotionAGFormer · DTW · STGCN / LSTM")
        )

    # 只顯示目前登入帳號，避免把本機其他使用者列在患者端。
    current_user = st.session_state.get("user") or {}
    if current_user:
        storage_key = _current_user_name()
        display_name = _current_user_display_name() or storage_key
        data = hist.load(storage_key)
        sessions = data.get("sessions", [])
        avg_score = (
            sum(s.get("score", 0.0) for s in sessions) / len(sessions)
            if sessions else 0.0
        )
        ui.section_eyebrow(
            "歡迎回來" if lang == "zh" else "Welcome back"
        )
        with st.container(border=True):
            initial = (display_name[:1] or "?").upper()
            st.markdown(
                f'<div style="display:flex;align-items:center;'
                f'gap:.6rem;">'
                f'<div style="width:42px;height:42px;'
                f'border-radius:50%;background:linear-gradient'
                f'(135deg,#74b9ff,#00b894);color:white;'
                f'display:flex;align-items:center;'
                f'justify-content:center;font-weight:700;">'
                f'{initial}</div>'
                f'<div><div style="font-weight:600">'
                f'{display_name}</div><div style="font-size:.8rem;'
                f'color:#636e72">{len(sessions)} 次｜'
                f'平均 {avg_score:.1f}</div></div></div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "繼續" if lang == "zh" else "Continue",
                key="resume_current_account",
                use_container_width=True,
            ):
                profile = hist.load_profile(storage_key)
                profile.setdefault("age", current_user.get("age") or 65)
                profile.setdefault("gender", "—")
                profile.setdefault("condition", [])
                st.session_state.user = {**current_user, **profile}
                st.session_state.prev_badges = hist.compute_badges(storage_key)[0]
                goto("home")

    # ===== 三步驟說明 =====
    ui.section_eyebrow(
        "如何使用" if lang == "zh" else "How it works"
    )
    cols = st.columns(3)
    with cols[0]:
        ui.stat_card("📋", t("step_profile", lang), "1")
    with cols[1]:
        ui.stat_card("🎥", t("step_record", lang), "2")
    with cols[2]:
        ui.stat_card("📊", t("step_result", lang), "3")

    # ===== 引擎狀態（折疊在最底）=====
    with st.expander(
        "🔧 " + t("engine_status", lang),
        expanded=False,
    ):
        _render_engine_status()


def _render_engine_status() -> None:
    # 標題交給外層 expander；本函式只渲染狀態列
    lifter = load_lifter()
    scorers = load_scorers()
    cols = st.columns(3)
    with cols[0]:
        if lifter and lifter.available:
            st.success(f"✅ {lifter.status}")
        else:
            txt = lifter.status if lifter else "MotionAGFormer 未啟用"
            st.info(f"ℹ {txt}\n\n→ MediaPipe 3D")
    with cols[1]:
        ls = scorers.get("lstm")
        if ls and ls.available:
            st.success(f"✅ {ls.status}")
        else:
            st.info("ℹ LSTM scorer 未啟用 → DTW")
    with cols[2]:
        sg = scorers.get("stgcn")
        if sg and sg.available:
            st.success(f"✅ {sg.status}")
        else:
            st.info("ℹ STGCN scorer 未啟用 → DTW")


# ============================================================
# 基本資料
# ============================================================
def _select_index(options: list[str], value: str | None, default: int = 0) -> int:
    if value in options:
        return options.index(value)
    return default


def _profile_list_options(lang: str) -> dict[str, list[str]]:
    if lang == "zh":
        return {
            "sides": ["無特定側", "左側", "右側", "雙側"],
            "hands": ["右手", "左手", "雙手皆可"],
            "pain": ["肩", "手肘", "手腕", "下背", "髖", "膝", "腳踝", "其他"],
            "aids": ["不需輔具", "手杖", "助行器", "輪椅", "需家人協助"],
            "activity": ["久坐", "偶爾活動", "每週運動 1-2 次", "規律運動"],
        }
    return {
        "sides": ["No specific side", "Left", "Right", "Both"],
        "hands": ["Right", "Left", "Both"],
        "pain": ["Shoulder", "Elbow", "Wrist", "Low back", "Hip", "Knee", "Ankle", "Other"],
        "aids": ["No aid", "Cane", "Walker", "Wheelchair", "Needs caregiver help"],
        "activity": ["Sedentary", "Occasionally active", "Exercise 1-2 times/week", "Regular exercise"],
    }


def view_profile() -> None:
    lang = get_lang()
    ui.hero(
        "👤 " + t("basic_info", lang),
        "請填寫較完整的資料，之後系統會用它做個人化訓練、疼痛追蹤與提醒。"
        if lang == "zh"
        else "Complete your profile for personalized training, pain tracking, and reminders.",
    )

    prev = dict(st.session_state.get("user") or {})
    prev.setdefault("name", prev.get("username", ""))
    storage_key = _current_user_name()
    if storage_key:
        saved_profile = hist.load_profile(storage_key)
        saved_profile.update({k: v for k, v in prev.items() if v not in (None, "", [])})
        prev = saved_profile

    completion = hist.profile_completion(prev)
    st.progress(
        completion / 100,
        text=(
            f"基本資料完成度 {completion}%"
            if lang == "zh" else f"Profile completion {completion}%"
        ),
    )

    gender_opts = [t("female", lang), t("male", lang), t("other", lang)]
    list_opts = _profile_list_options(lang)
    goal_keys = ["goal_upper", "goal_lower", "goal_balance",
                 "goal_postop", "goal_general"]
    goal_opts = [t(k, lang) for k in goal_keys]

    with st.form("profile_form"):
        st.markdown("#### " + ("身分與身體資料" if lang == "zh" else "Identity and body"))
        name = st.text_input(t("name", lang), value=prev.get("name", ""))
        c1, c2 = st.columns(2)
        with c1:
            age = st.number_input(
                t("age", lang), min_value=1, max_value=120,
                value=int(prev.get("age", 65)), step=1,
            )
        with c2:
            gender_default = prev.get("gender", gender_opts[0])
            if gender_default not in gender_opts:
                gender_default = gender_opts[0]
            gender = st.selectbox(
                t("gender", lang), gender_opts,
                index=gender_opts.index(gender_default),
            )

        c3, c4, c5 = st.columns(3)
        with c3:
            height_cm = st.number_input(
                "身高 (cm)" if lang == "zh" else "Height (cm)",
                min_value=80, max_value=230,
                value=int(prev.get("height_cm", 165)), step=1,
            )
        with c4:
            weight_kg = st.number_input(
                "體重 (kg)" if lang == "zh" else "Weight (kg)",
                min_value=20, max_value=220,
                value=int(prev.get("weight_kg", 60)), step=1,
            )
        with c5:
            dominant_hand = st.selectbox(
                "慣用手" if lang == "zh" else "Dominant hand",
                list_opts["hands"],
                index=_select_index(
                    list_opts["hands"], prev.get("dominant_hand"), 0,
                ),
            )

        st.markdown("#### " + ("復健狀況" if lang == "zh" else "Rehab context"))
        default_goals = prev.get("condition") or [goal_opts[-1]]
        default_goals = [g for g in default_goals if g in goal_opts] \
            or [goal_opts[-1]]
        goals = st.multiselect(
            t("goals", lang), goal_opts, default=default_goals,
        )
        c6, c7 = st.columns(2)
        with c6:
            affected_side = st.selectbox(
                "主要訓練/不適側" if lang == "zh" else "Primary side",
                list_opts["sides"],
                index=_select_index(
                    list_opts["sides"], prev.get("affected_side"), 0,
                ),
            )
        with c7:
            pain_area_default = [
                p for p in prev.get("pain_area", []) if p in list_opts["pain"]
            ]
            pain_area = st.multiselect(
                "常見不適部位" if lang == "zh" else "Common pain areas",
                list_opts["pain"],
                default=pain_area_default,
            )
        diagnosis = st.text_input(
            "主要診斷/復健原因" if lang == "zh" else "Diagnosis / reason",
            value=prev.get("diagnosis", ""),
            placeholder=(
                "例：五十肩、膝關節術後、下背痛"
                if lang == "zh" else "e.g. frozen shoulder, post-op knee, low back pain"
            ),
        )
        surgery_history = st.text_area(
            "手術/受傷紀錄（選填）" if lang == "zh" else "Surgery / injury history (optional)",
            value=prev.get("surgery_history", ""),
            height=80,
        )
        contraindications = st.text_area(
            "需要避免的動作或醫囑（選填）" if lang == "zh" else "Movements to avoid / clinical notes (optional)",
            value=prev.get("contraindications", ""),
            height=80,
        )

        st.markdown("#### " + ("訓練偏好與照護資訊" if lang == "zh" else "Training preferences and care"))
        c8, c9, c10 = st.columns(3)
        with c8:
            mobility_aid = st.selectbox(
                "行動能力/輔具" if lang == "zh" else "Mobility aid",
                list_opts["aids"],
                index=_select_index(
                    list_opts["aids"], prev.get("mobility_aid"), 0,
                ),
            )
        with c9:
            activity_level = st.selectbox(
                "平常活動量" if lang == "zh" else "Activity level",
                list_opts["activity"],
                index=_select_index(
                    list_opts["activity"], prev.get("activity_level"), 1,
                ),
            )
        with c10:
            weekly_goal = st.number_input(
                "每週訓練目標（次）" if lang == "zh" else "Weekly goal (sessions)",
                min_value=1, max_value=14,
                value=int(prev.get("weekly_goal", 3)), step=1,
            )
        c11, c12, c13 = st.columns(3)
        with c11:
            daily_goal = st.number_input(
                "每日訓練目標（次）" if lang == "zh" else "Daily goal (sessions)",
                min_value=1, max_value=5,
                value=int(prev.get("daily_goal", st.session_state.settings.get("daily_goal", 1))),
                step=1,
            )
        with c12:
            reminder_enabled = st.checkbox(
                "顯示 app 內提醒" if lang == "zh" else "Show in-app reminders",
                value=bool(prev.get("reminder_enabled", True)),
            )
        with c13:
            preferred_training_time = st.text_input(
                "偏好訓練時間" if lang == "zh" else "Preferred training time",
                value=prev.get("preferred_training_time", "09:00"),
                placeholder="09:00",
            )
        c14, c15 = st.columns(2)
        with c14:
            contact_name = st.text_input(
                "緊急/照護聯絡人（選填）" if lang == "zh" else "Care contact (optional)",
                value=prev.get("contact_name", ""),
            )
        with c15:
            contact_phone = st.text_input(
                "聯絡電話（選填）" if lang == "zh" else "Contact phone (optional)",
                value=prev.get("contact_phone", ""),
            )
        caregiver_note = st.text_area(
            "給照護者或治療師的備註（選填）" if lang == "zh" else "Notes for caregiver/therapist (optional)",
            value=prev.get("caregiver_note", ""),
            height=80,
        )

        submitted = st.form_submit_button(
            ("儲存並進入訓練 ▶" if lang == "zh" else "Save and continue ▶"),
            type="primary",
        )

    if submitted:
        if not name.strip():
            st.warning(
                "請輸入稱呼以便儲存訓練紀錄。" if lang == "zh"
                else "Please enter a name to save records."
            )
        else:
            profile = {
                "name": name.strip(),
                "age": int(age),
                "gender": gender,
                "height_cm": int(height_cm),
                "weight_kg": int(weight_kg),
                "dominant_hand": dominant_hand,
                "condition": goals,
                "affected_side": affected_side,
                "pain_area": pain_area,
                "diagnosis": diagnosis.strip(),
                "surgery_history": surgery_history.strip(),
                "contraindications": contraindications.strip(),
                "mobility_aid": mobility_aid,
                "activity_level": activity_level,
                "weekly_goal": int(weekly_goal),
                "daily_goal": int(daily_goal),
                "reminder_enabled": bool(reminder_enabled),
                "preferred_training_time": preferred_training_time.strip() or "09:00",
                "contact_name": contact_name.strip(),
                "contact_phone": contact_phone.strip(),
                "caregiver_note": caregiver_note.strip(),
            }
            hist.save_profile(profile, storage_key=storage_key)
            _save_profile_to_db(profile)
            st.session_state.user = {
                **prev,
                **profile,
                "history_key": storage_key,
            }
            st.session_state.settings["daily_goal"] = int(daily_goal)
            st.session_state.settings["reminder_enabled"] = bool(reminder_enabled)
            st.session_state.settings["preferred_training_time"] = (
                preferred_training_time.strip() or "09:00"
            )
            st.session_state.prev_badges = (
                hist.compute_badges(storage_key)[0]
            )
            goto("home")


# ============================================================
# 首頁
# ============================================================
def view_home() -> None:
    lang = get_lang()
    u = st.session_state.user or {}
    name = _current_user_name()
    display_name = _current_user_display_name() or name

    streak = hist.compute_badges(name)[1]
    today = hist.today_session_count(name)
    data = hist.load(name)
    sessions = data.get("sessions", [])
    templates_all = tpl_mod.all_templates()
    plan = hist.today_plan(
        name, templates_all, u, st.session_state.settings,
    )

    diff_level = st.session_state.settings.get("difficulty", "normal")
    diff_meta = DIFFICULTY_PRESETS.get(
        diff_level, DIFFICULTY_PRESETS["normal"]
    )
    diff_label = (diff_meta["label_zh"] if lang == "zh"
                  else diff_meta["label_en"])
    chips = [
        f"{t('age', lang)} {u.get('age', '—')}",
        f"{'訓練側' if lang == 'zh' else 'Side'} {u.get('affected_side', '—')}",
        f"🔥 {streak} {t('day_unit', lang)}",
        f"📅 今日 {today} 次",
        f"{diff_meta['icon']} {diff_label}",
    ]
    ui.hero(
        f"🙋 {display_name}",
        ", ".join(u.get("condition") or [t("goal_general", lang)]),
        chips=chips,
        variant="warm",
    )

    profile_pct = hist.profile_completion(u)
    with st.container(border=True):
        p_cols = st.columns([3, 1])
        with p_cols[0]:
            st.markdown(
                "**" + (
                    "個人化資料" if lang == "zh" else "Personalization profile"
                ) + f"：{profile_pct}%**"
            )
            st.caption(
                "、".join(filter(None, [
                    u.get("diagnosis", ""),
                    u.get("affected_side", ""),
                    u.get("mobility_aid", ""),
                ])) or (
                    "補完整資料後，系統能更精準地推薦訓練。"
                    if lang == "zh"
                    else "Complete your profile for better recommendations."
                )
            )
            st.progress(profile_pct / 100)
        with p_cols[1]:
            if st.button(
                "編輯資料" if lang == "zh" else "Edit profile",
                use_container_width=True,
                key="edit_profile_from_home",
            ):
                goto("profile")

    user_id = _active_user_id()
    if user_id:
        try:
            from smart_routing import render_suggestions
            render_suggestions(user_id, lang=lang, limit=3)
        except Exception as exc:
            st.caption(
                ("下一步建議暫時無法載入: "
                 if lang == "zh" else "Next suggestions unavailable: ")
                + str(exc)
            )

    ui.today_plan_panel(plan, lang=lang)
    if plan.get("last_safety_flag"):
        st.warning(
            "上次訓練有疼痛偏高紀錄，今天建議從低強度開始，若不適請停止。"
            if lang == "zh"
            else "The last session had a high-pain flag. Start easy today and stop if discomfort increases."
        )
    next_key = plan.get("next_key")
    if next_key and next_key in templates_all:
        if st.button(
            "開始今日建議動作" if lang == "zh" else "Start today's recommendation",
            type="primary",
            use_container_width=True,
            key="start_today_plan",
        ):
            st.session_state.exercise_key = next_key
            goto("record")

    # ---- 卡通教練問候 ----
    ui.coach_card(
        st.session_state.settings.get("coach", "starbuddy"),
        state=coach_mod.state_for_streak(streak),
        lang=lang,
    )

    # ---- 每日挑戰 ----
    challenge_key = daily_challenge_key(name, templates_all)
    if challenge_key and challenge_key in templates_all:
        challenge_tpl = templates_all[challenge_key]
        c1, c2 = st.columns([3, 1])
        with c1:
            ui.daily_challenge_card(
                challenge_tpl["name"],
                challenge_tpl.get("description", ""),
                lang=lang,
            )
        with c2:
            st.markdown(
                "<div style='height:18px'></div>",
                unsafe_allow_html=True,
            )
            if st.button(
                "▶ " + ("接受挑戰" if lang == "zh"
                        else "Take challenge"),
                type="primary",
                use_container_width=True,
                key="accept_challenge",
            ):
                st.session_state.exercise_key = challenge_key
                goto("record")
        st.markdown("")

    # ---- 統計卡 ----
    cols = st.columns(4)
    with cols[0]:
        ui.streak_card(streak, "連續訓練天數" if lang == "zh"
                       else "Day streak")
    with cols[1]:
        ui.stat_card(
            "📊", "本日訓練" if lang == "zh" else "Today", f"{today}",
        )
    with cols[2]:
        ui.stat_card(
            "🎯", t("session_count", lang), f"{len(sessions)}",
        )
    with cols[3]:
        if sessions:
            avg = sum(s["score"] for s in sessions) / len(sessions)
            last = sessions[-1]["score"]
            delta = last - avg
            ui.stat_card(
                "💎", t("avg_score", lang), f"{avg:.1f}",
                delta=f"上次 {last:.1f}",
                delta_up=delta >= 0,
            )
        else:
            ui.stat_card("💎", t("avg_score", lang), "—")

    # ---- 每日目標 ----
    daily_goal = st.session_state.settings.get("daily_goal", 1)
    st.markdown("")
    ui.goal_progress(
        today, daily_goal,
        f"📌 {'每日訓練目標' if lang == 'zh' else 'Daily goal'}",
    )

    st.divider()
    st.subheader("🧭 " + ("健康管理" if lang == "zh" else "Health tools"))
    health_items = [
        ("programs", "📋", t("step_programs", lang)),
        ("pain_map", "🗺️", t("step_pain_map", lang)),
        ("journal", "📝", t("step_journal", lang)),
        ("vitals", "🌡️", t("step_vitals", lang)),
        ("medication", "💊", t("step_medication", lang)),
        ("calendar", "📅", t("step_calendar", lang)),
    ]
    for row_start in range(0, len(health_items), 3):
        health_nav = st.columns(3)
        for idx, (route, icon, label) in enumerate(health_items[row_start:row_start + 3]):
            if health_nav[idx].button(
                f"{icon} {label}",
                key=f"home_health_{route}",
                use_container_width=True,
            ):
                goto(route)

    st.divider()
    st.subheader("🏃 " + t("choose_exercise", lang))

    # ---- 推薦動作 ----
    rec_key = hist.recommend_exercise(name, list(templates_all.keys()))
    if rec_key and rec_key in templates_all:
        rec_tpl = templates_all[rec_key]
        cols_rec = st.columns([1, 4])
        with cols_rec[0]:
            st.markdown("##### 💡 推薦" if lang == "zh"
                        else "##### 💡 Recommended")
        with cols_rec[1]:
            with st.container(border=True):
                rc = st.columns([4, 1])
                with rc[0]:
                    st.markdown(f"**{rec_tpl['name']}**")
                    st.caption(rec_tpl.get("description", ""))
                if rc[1].button(
                    "▶ " + t("select_this", lang),
                    type="primary", key="rec_pick",
                    use_container_width=True,
                ):
                    st.session_state.exercise_key = rec_key
                    goto("record")
        st.markdown("")

    # ---- 動作卡分類 ----
    cat_labels = {
        "upper": "💪 上肢" if lang == "zh" else "💪 Upper limb",
        "lower": "🦵 下肢" if lang == "zh" else "🦵 Lower limb",
        "balance": "⚖ 平衡" if lang == "zh" else "⚖ Balance",
        "custom": "✨ 自訂" if lang == "zh" else "✨ Custom",
    }
    groups: dict = {}
    for tpl in templates_all.values():
        groups.setdefault(tpl.get("category", "custom"), []).append(tpl)

    for cat in ("upper", "lower", "balance", "custom"):
        items = groups.get(cat, [])
        if not items:
            continue
        st.markdown(f"#### {cat_labels.get(cat, cat)}")
        cols = st.columns(min(3, len(items)))
        for i, tpl in enumerate(items):
            with cols[i % len(cols)]:
                with st.container(border=True):
                    pb = hist.personal_best(name, tpl["name"])
                    pb_text = (
                        f"🏆 個人最佳 {pb:.1f}"
                        if pb is not None else "—"
                    )
                    st.markdown(
                        f"**{tpl['name']}**"
                        f' <span style="font-size:.8rem;'
                        f'color:#636e72">{pb_text}</span>',
                        unsafe_allow_html=True,
                    )
                    st.caption(tpl.get("description", ""))
                    st.caption(
                        f"🔔 {t('cue', lang)}：{tpl.get('cue', '')}"
                    )
                    bcols = st.columns([3, 1])
                    if bcols[0].button(
                        "▶ " + t("select_this", lang),
                        key=f"pick_{tpl['key']}",
                        use_container_width=True,
                    ):
                        st.session_state.exercise_key = tpl["key"]
                        goto("record")
                    if tpl.get("custom"):
                        if bcols[1].button(
                            "🗑", key=f"del_{tpl['key']}",
                            help="刪除此自訂範本",
                        ):
                            tpl_mod.delete_custom(tpl["key"])
                            st.rerun()

    # ---- 導覽列 ----
    st.divider()
    nav = st.columns(4)
    if nav[0].button("📈 " + t("view_progress", lang),
                     use_container_width=True):
        goto("progress")
    if nav[1].button("🎬 " + t("record_template", lang),
                     use_container_width=True):
        goto("custom")
    if nav[2].button("🩺 " + t("clinician", lang),
                     use_container_width=True):
        goto("clinician")
    if nav[3].button("⚙ " + t("settings", lang),
                     use_container_width=True):
        goto("settings")


# ============================================================
# 錄影：上傳分頁 + 即時鏡頭分頁
# ============================================================
def _record_guidance_steps(tpl: dict, lang: str) -> list[dict]:
    try:
        import realtime as rt_mod
        return rt_mod.template_guidance_steps(tpl, lang=lang)
    except Exception:
        return [
            {
                "icon": "1",
                "title": "準備姿勢" if lang == "zh" else "Setup",
                "detail": tpl.get("description", ""),
            },
            {
                "icon": "2",
                "title": "慢慢跟做" if lang == "zh" else "Move slowly",
                "detail": tpl.get("cue", ""),
            },
        ]


def _speak_record_intro(tpl: dict, lang: str) -> bool:
    voice = get_voice()
    if not voice:
        return False
    voice.say(_record_intro_text(tpl, lang))
    return True


def _record_intro_text(tpl: dict, lang: str) -> str:
    name = tpl.get("name", "")
    desc = tpl.get("description", "")
    cue = tpl.get("cue", "")
    if lang == "zh":
        parts = [f"接下來的動作是：{name}"]
        if desc:
            parts.append(desc)
        if cue:
            parts.append(f"重點提醒：{cue}")
        parts.append("請看著畫面提示，慢慢做，不要急")
        return "。".join(parts)
    parts = [f"Next exercise: {name}."]
    if desc:
        parts.append(desc)
    if cue:
        parts.append(f"Tip: {cue}.")
    parts.append("Watch the screen cue. Move slowly.")
    return " ".join(parts)


def _auto_speak_record_intro(tpl: dict, lang: str) -> None:
    if not st.session_state.settings.get("enable_voice", True):
        return
    sig = f"{tpl.get('key', '')}:{lang}"
    if st.session_state.get("record_intro_sig") == sig:
        return
    _speak_record_intro(tpl, lang)
    st.session_state.record_intro_sig = sig


def _ai_demo_image_for(tpl: dict, lang: str) -> None:
    # Keep this as a teaching demo. The old media-generation button lived here.
    ui.demo_figure_3d_video(tpl, lang=lang)


def _render_record_instruction_showcase(tpl: dict, lang: str) -> None:
    steps = _record_guidance_steps(tpl, lang)
    st.subheader("🧭 " + ("動作教學" if lang == "zh" else "Movement guide"))
    left, right = st.columns([1, 1.05])
    with left:
        _ai_demo_image_for(tpl, lang)
    with right:
        ui.voice_instruction_card(
            steps,
            cue=tpl.get("cue", ""),
            voice_enabled=bool(st.session_state.settings.get("enable_voice", True)),
            lang=lang,
        )
        if st.button(
            "🔊 再聽一次語音教學" if lang == "zh" else "🔊 Replay voice guide",
            use_container_width=True,
            key=f"replay_intro_{tpl.get('key', '')}",
        ):
            if not _speak_record_intro(tpl, lang):
                st.info(
                    "語音引擎尚未啟用，請到設定開啟語音回饋，或確認 pyttsx3 可用。"
                    if lang == "zh"
                    else "Voice engine is unavailable. Enable voice feedback in Settings or check pyttsx3."
                )
    ui.prep_guide_cards(steps, lang=lang)


def _render_audio_tools(tpl: dict, lang: str, key_prefix: str) -> None:
    import tts as tts_mod

    status = tts_mod.voice_status()
    voice_enabled = bool(st.session_state.settings.get("enable_voice", True))
    live_enabled = bool(st.session_state.settings.get("live_voice", True))
    ui.audio_doctor(
        voice_enabled and live_enabled,
        server_voice=status.get("edge_neural") or status.get("windows_sapi") or status.get("pyttsx3"),
        browser_voice=status.get("browser_wav"),
        lang=lang,
    )
    sample = _record_intro_text(tpl, lang)
    a1, a2, a3 = st.columns([1, 1, 1])
    if a1.button(
        "🔊 播放測試音訊" if lang == "zh" else "🔊 Test audio",
        use_container_width=True,
        key=f"{key_prefix}_test_wav",
    ):
        audio = tts_mod.synthesize_audio_bytes(sample, lang=lang)
        if audio:
            data, fmt = audio
            st.audio(data, format=fmt, autoplay=True)
        else:
            st.warning(
                "無法產生系統音訊，請改用右側的瀏覽器語音。"
                if lang == "zh"
                else "Could not generate system audio. Try browser speech."
            )
    with a2:
        ui.browser_speech_button(
            sample,
            "瀏覽器語音" if lang == "zh" else "Browser speech",
            lang=lang,
        )
    if a3.button(
        "✅ 開啟語音" if lang == "zh" else "✅ Enable voice",
        use_container_width=True,
        key=f"{key_prefix}_enable_voice",
    ):
        st.session_state.settings["enable_voice"] = True
        st.session_state.settings["live_voice"] = True
        st.session_state.tts_engine = None
        st.toast("語音已開啟" if lang == "zh" else "Voice enabled", icon="🔊")
        st.rerun()


def _render_live_tab(tpl: dict, lang: str) -> None:
    """即時鏡頭分頁：倒數 → WebRTC 串流 → 即時狀態卡 → 結束評分。"""
    if not pe.pose_available():
        _show_pose_engine_unavailable(lang)
        return

    import realtime as rt_mod

    if not rt_mod.WEBRTC_OK:
        st.warning(
            "⚠ 即時鏡頭功能未啟用。\n\n"
            "請執行：`pip install streamlit-webrtc av`"
            if lang == "zh"
            else "⚠ Live camera not available. "
                 "Install: pip install streamlit-webrtc av"
        )
        return

    from streamlit_webrtc import (  # type: ignore
        webrtc_streamer, WebRtcMode, RTCConfiguration,
    )

    settings = st.session_state.settings
    threshold = settings.get("threshold", 15.0)
    live_voice = bool(
        settings.get("enable_voice", True)
        and settings.get("live_voice", True)
    )
    ui.session_control_panel(
        tpl.get("name", ""),
        voice_enabled=live_voice,
        pip_enabled=True,
        scoring_enabled=True,
        lang=lang,
    )
    with st.expander("音訊測試" if lang == "zh" else "Audio test", expanded=False):
        _render_audio_tools(tpl, lang, f"live_audio_{tpl['key']}")

    pain_before = int(st.session_state.get("pain_before", 0))
    pain_confirm_key = f"pain_low_confirm_{tpl['key']}"
    if pain_before < 7:
        st.session_state[pain_confirm_key] = False
    if pain_before >= 7:
        apply_difficulty("easy")
        st.warning(
            "目前疼痛分數偏高，系統已切換低強度。請先確認今天只做輕量訓練，若疼痛加劇就停止。"
            if lang == "zh"
            else "Pain is high, so the session is switched to easy mode. Stop if pain increases."
        )
        if not st.session_state.get(pain_confirm_key, False):
            if st.button(
                "低強度開始" if lang == "zh" else "Start low intensity",
                type="primary",
                use_container_width=True,
                key=f"confirm_low_{tpl['key']}",
            ):
                st.session_state[pain_confirm_key] = True
                st.rerun()
            return

    # ---- 倒數閘門 ----
    cd_key = f"live_cd_{tpl['key']}"
    if cd_key not in st.session_state:
        st.session_state[cd_key] = False

    if not st.session_state[cd_key]:
        if st.button(
            "▶ " + ("開始倒數 (3 秒後開始)"
                    if lang == "zh"
                    else "Start countdown (3s)"),
            type="primary",
            use_container_width=True,
            key=f"start_{tpl['key']}",
        ):
            ui.countdown(3)
            st.session_state[cd_key] = True
            st.rerun()
        return

    # ---- WebRTC：FaceTime 風格主畫面 + 乾淨提示欄 ----
    call_cols = st.columns([2.2, 1], gap="large")
    with call_cols[0]:
        ui.video_call_title(
            "復健視訊指導中" if lang == "zh" else "Rehab video session",
            "主畫面：你的相機" if lang == "zh" else "Main feed: your camera",
        )
        ctx = webrtc_streamer(
            key=f"coach_{tpl['key']}",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=RTCConfiguration({
                "iceServers": [
                    {"urls": ["stun:stun.l.google.com:19302"]}
                ],
            }),
            video_processor_factory=lambda: rt_mod.RealtimeCoach(
                template=tpl,
                threshold=threshold,
                voice_enabled=live_voice,
                lang=lang,
                voice_cooldown=float(settings.get("voice_cooldown", 4.5)),
                character_key=settings.get("coach", "starbuddy"),
            ),
            media_stream_constraints={
                "video": {
                    "width": {"ideal": 1280},
                    "height": {"ideal": 720},
                    "frameRate": {"ideal": 30},
                },
                "audio": False,
            },
            desired_playing_state=True,
            video_html_attrs={
                "style": {
                    "width": "100%",
                    "borderRadius": "8px",
                    "background": "#000",
                    "boxShadow": "0 18px 48px rgba(0,0,0,.18)",
                },
                "autoPlay": True,
                "playsInline": True,
                "muted": True,
            },
            async_processing=True,
        )

    snap: dict = {}
    elapsed = 0.0
    if ctx and ctx.video_processor is not None:
        snap = ctx.video_processor.snapshot()
        elapsed = ctx.video_processor.session_seconds()
    else:
        dom_joint = scoring._dominant_joint(  # noqa: SLF001
            {
                k: np.asarray(v, dtype=np.float32)
                for k, v in tpl["angle_series"].items()
            },
            exercise_hint=tpl.get("key"),
        )
        dom_series = list(tpl["angle_series"][dom_joint])
        snap = {
            "phase": 0,
            "phase_total": len(dom_series),
            "msgs": [],
            "guide": rt_mod.motion_guide(tpl, 0, dom_series, lang),
            "score": 0.0,
            "fps": 0.0,
        }

    with call_cols[1]:
        ui.live_prompt_panel(
            tpl,
            guide=snap.get("guide"),
            phase=snap.get("phase", 0),
            phase_total=snap.get("phase_total", 1),
            msgs=snap.get("msgs"),
            voice_enabled=live_voice,
            character_key=settings.get("coach", "starbuddy"),
            lang=lang,
        )
        ui.live_session_stats(
            elapsed_s=elapsed,
            score=snap.get("score", 0.0),
            phase=snap.get("phase", 0),
            phase_total=snap.get("phase_total", 1),
            fps=snap.get("fps", 0.0),
            lang=lang,
        )

    st.caption(
        "主畫面只保留大字提示與狀態，不顯示骨架、角度或教學人物。"
        if lang == "zh"
        else "The main feed keeps only large cues and status; no skeleton, angles, or coach figure."
    )

    if not live_voice:
        st.caption(
            "💡 到設定開啟語音與即時語音提醒，小助手就會直接念出手臂往上或往下。"
            if lang == "zh"
            else "💡 Enable voice and live voice cues in Settings for spoken arm directions."
        )

    # ---- 控制列 ----
    col_a, col_b = st.columns(2)
    if col_a.button(
        "✓ " + ("結束並評分" if lang == "zh" else "End & evaluate"),
        type="primary", use_container_width=True,
        key=f"end_eval_{tpl['key']}",
    ):
        if ctx and ctx.video_processor is not None:
            seq = ctx.video_processor.flush_buffer()
            last_frame = ctx.video_processor.last_frame
            last_kp = ctx.video_processor.last_image_kp
            if (
                len(seq) >= 5
                and last_frame is not None
                and last_kp is not None
            ):
                frames = [{
                    "image": last_frame.copy(),
                    "image_kp": last_kp.copy(),
                    "frame_idx": 0,
                }]
                fps = float(snap.get("fps", 30.0))
                st.session_state[cd_key] = False
                run_pipeline(seq, frames, fps, tpl)
            else:
                st.warning(
                    "錄製時間太短或無人入鏡，請再多做幾秒鐘。"
                    if lang == "zh"
                    else "Too few frames captured. Try a bit longer."
                )
        else:
            st.warning("尚未啟動鏡頭。"
                       if lang == "zh" else "Camera not started.")

    if col_b.button(
        "⟲ " + ("重新倒數" if lang == "zh" else "Reset countdown"),
        use_container_width=True,
        key=f"reset_{tpl['key']}",
    ):
        st.session_state[cd_key] = False
        st.rerun()


def view_record() -> None:
    lang = get_lang()
    templates_all = tpl_mod.all_templates()
    tpl = templates_all.get(st.session_state.exercise_key)
    if tpl is None:
        goto("home")
        return

    ui.hero(
        f"🎥 {tpl['name']}",
        tpl.get("description", ""),
        chips=[f"🔔 {tpl.get('cue', '')}"],
    )

    # 卡通教練「準備」鼓勵
    ui.coach_card(
        st.session_state.settings.get("coach", "starbuddy"),
        state="ready", lang=lang,
    )
    _auto_speak_record_intro(tpl, lang)

    # 個人最佳
    pb = hist.personal_best(
        _current_user_name(), tpl["name"]
    )
    if pb is not None:
        ui.pb_banner(
            f"挑戰個人最佳：{pb:.1f} 分" if lang == "zh"
            else f"Personal best: {pb:.1f}"
        )

    _render_record_instruction_showcase(tpl, lang)

    # 訓練前疼痛
    with st.container(border=True):
        st.markdown("#### 📝 " + (
            "錄影前準備" if lang == "zh" else "Pre-session"
        ))
        st.caption("• " + t("video_hint", lang))
        st.markdown("")
        st.markdown(
            "**🩹 " + (
                "現在的疼痛程度（0-10）" if lang == "zh"
                else "Current pain level (0-10)"
            ) + "**"
        )
        st.session_state.pain_before = st.slider(
            "pain_before",
            0, 10,
            st.session_state.pain_before,
            label_visibility="collapsed",
            help="0 = 無痛，10 = 極度疼痛",
        )

    tabs = st.tabs([
        "🔴 " + ("即時鏡頭" if lang == "zh" else "Live Camera"),
        "📁 " + ("上傳影片" if lang == "zh" else "Upload Video"),
    ])

    with tabs[0]:
        _render_live_tab(tpl, lang)

    with tabs[1]:
        uploaded = st.file_uploader(
            t("upload_video", lang),
            type=["mp4", "mov", "avi", "mkv"],
        )
        if uploaded is not None:
            suffix = Path(uploaded.name).suffix or ".mp4"
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix,
            )
            tmp.write(uploaded.read())
            tmp.close()
            st.session_state.video_path = tmp.name
            st.video(tmp.name)
            upload_blocked = (
                int(st.session_state.get("pain_before", 0)) >= 7
                and not st.session_state.get(f"pain_low_confirm_{tpl['key']}", False)
            )
            if upload_blocked:
                st.warning(
                    "疼痛分數偏高，請先在即時鏡頭頁確認低強度開始。"
                    if lang == "zh"
                    else "Pain is high. Confirm low-intensity start in the live camera tab first."
                )
            if st.button(
                "▶ " + t("start_analysis", lang),
                type="primary", use_container_width=True,
                disabled=upload_blocked,
            ):
                goto("analyze")

    st.divider()
    if st.button("← " + t("back", lang)):
        goto("home")


# ============================================================
# 分析（從上傳影片進入）
# ============================================================
def view_analyze() -> None:
    lang = get_lang()
    templates_all = tpl_mod.all_templates()
    tpl = templates_all.get(st.session_state.exercise_key)
    path = st.session_state.video_path
    if tpl is None or not path or not Path(path).exists():
        st.error(t("no_person", lang))
        if st.button(t("back", lang)):
            goto("record")
        return

    ui.hero(
        "🧠 " + t("step_analyze", lang) + "…",
        ("使用 MediaPipe 3D + DTW 進行姿態與動作分析"
         if lang == "zh"
         else "Pose estimation + DTW analysis"),
    )
    if not pe.pose_available():
        _show_pose_engine_unavailable(lang)
        if st.button(t("back", lang)):
            goto("record")
        return

    progress = st.progress(0, text="Loading models…")

    estimator = None
    try:
        estimator = pe.PoseEstimator(
            smooth_alpha=st.session_state.settings["ema_alpha"],
        )
        lifter = load_lifter()
        progress.progress(15, text="Extracting 3D keypoints…")
        seq, frames, fps = estimator.extract_video(
            path, max_frames=300, lifter=lifter,
        )
    except Exception as exc:
        progress.empty()
        st.error(
            "姿態分析失敗，請確認影片格式與姿態引擎狀態。"
            if lang == "zh"
            else "Pose analysis failed. Please check the video and pose engine."
        )
        st.exception(exc)
        if st.button(t("back", lang)):
            goto("record")
        return
    finally:
        if estimator is not None:
            estimator.close()

    if len(seq) < 5:
        progress.empty()
        st.error(t("no_person", lang))
        if st.button(t("back", lang)):
            goto("record")
        return

    run_pipeline(seq, frames, fps, tpl, progress=progress)


# ============================================================
# 結果
# ============================================================
def view_result() -> None:
    lang = get_lang()
    a = st.session_state.analysis
    if a is None:
        goto("home")
        return

    score = a["score"]
    cues = a.get("cues", [])

    # ===== Apple 巨字 hero =====
    eyebrow = "評估完成" if lang == "zh" else "ANALYSIS COMPLETE"
    sub = a["template"]["name"]
    if a.get("rep_count"):
        sub += "  ·  " + (
            f"{a['rep_count']} 次" if lang == "zh"
            else f"{a['rep_count']} reps"
        )
    ui.apple_hero(
        eyebrow=eyebrow,
        headline=("您的訓練成果" if lang == "zh"
                  else "Your performance"),
        sub=sub,
    )

    # ===== 個人新高慶祝 =====
    if a.get("is_pb"):
        ui.pb_banner(
            f"創下 {a['template']['name']} 的個人新高！"
            if lang == "zh"
            else f"New best on {a['template']['name']}!"
        )
        ui.confetti()
        st.balloons()

    # ===== 巨型分數 =====
    if score >= 85:
        verdict = t("excellent", lang)
    elif score >= 70:
        verdict = t("ok", lang)
    else:
        verdict = t("needs_work", lang)
    ui.mega_score(score, verdict=verdict)

    # ===== 卡通教練 =====
    coach_state = "pb" if a.get("is_pb") \
        else coach_mod.state_from_score(score)
    ui.coach_card(
        st.session_state.settings.get("coach", "starbuddy"),
        state=coach_state, lang=lang,
    )

    # ===== 方向提示卡（取代文字牆）+ 語音重播 =====
    if cues:
        ui.section_eyebrow(
            "需要調整" if lang == "zh" else "Adjust these"
        )
        ui.cue_grid(cues, lang=lang)
        # 語音重播
        voice = get_voice()
        cv1, cv2, cv3 = st.columns([1, 2, 1])
        with cv2:
            if voice and st.button(
                "🔊 " + (
                    "重新播放語音指引" if lang == "zh"
                    else "Replay voice cues"
                ),
                use_container_width=True,
                key="replay_voice",
            ):
                voice.say_cues(cues, score=score, lang=lang)
            elif not voice:
                st.caption(
                    "💡 設定中啟用語音回饋，可聽到「右肩抬高」式提示"
                    if lang == "zh"
                    else "💡 Enable voice in Settings for spoken cues."
                )
    else:
        ui.section_eyebrow(
            "完美演出" if lang == "zh" else "Perfect form"
        )
        st.markdown(
            f'<p style="text-align:center;font-size:1.15rem;'
            f'color:#34c759;font-weight:600;">'
            f'{t("excellent", lang)}</p>',
            unsafe_allow_html=True,
        )

    # ===== 動作分析（骨架 / 雷達 / 曲線）=====
    ui.section_eyebrow("動作分析" if lang == "zh" else "Analysis")
    tabs = st.tabs([
        "🎯 " + ("骨架疊加" if lang == "zh" else "Skeleton"),
        "🕸 " + ("關節雷達" if lang == "zh" else "Joint radar"),
        "📈 " + ("角度曲線" if lang == "zh" else "Angle curve"),
    ])
    with tabs[0]:
        mid = len(a["frames"]) // 2
        f = a["frames"][mid]
        overlay = viz.overlay_feedback(
            f["image"], f["image_kp"], a["joints"],
            threshold=st.session_state.settings["threshold"],
        )
        st.image(
            overlay, channels="BGR", use_container_width=True,
            caption=t("skeleton_overlay", lang),
        )
    with tabs[1]:
        fig = ui.plot_joint_radar(
            a["joints"],
            threshold=st.session_state.settings["threshold"],
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Plotly 未安裝。")
    with tabs[2]:
        _render_angle_chart(a)

    # ===== 體感紀錄（疼痛 + 心情合一）=====
    ui.section_eyebrow(
        "感覺如何？" if lang == "zh" else "How do you feel?"
    )
    body_l, body_r = st.columns(2, gap="large")
    with body_l:
        with st.container(border=True):
            st.markdown(
                "**🩹 " + (
                    "訓練後疼痛" if lang == "zh"
                    else "Pain after"
                ) + "** (0-10)"
            )
            pain_after = st.slider(
                "pain_after", 0, 10, st.session_state.pain_before,
                label_visibility="collapsed",
                key="pain_after_slider",
            )
            if st.button(
                "💾 " + ("儲存" if lang == "zh" else "Save"),
                key="save_pain_btn",
                use_container_width=True,
            ):
                delta = int(pain_after) - int(st.session_state.pain_before)
                safety_flag = None
                if int(pain_after) >= 7:
                    safety_flag = "high_pain_after"
                elif delta >= 2:
                    safety_flag = "pain_increased"
                ok = hist.update_last_session(
                    _current_user_name(),
                    pain_after=int(pain_after),
                    safety_flag=safety_flag,
                )
                if ok:
                    _sync_session_pain_to_db(int(pain_after), safety_flag)
                    if delta < 0:
                        st.success(
                            f"✓ 疼痛降低 {abs(delta)} 分"
                            if lang == "zh"
                            else f"✓ Pain ↓ {abs(delta)}"
                        )
                    elif delta == 0:
                        st.info(
                            "✓ 疼痛持平" if lang == "zh"
                            else "✓ Unchanged"
                        )
                    else:
                        st.warning(
                            f"⚠ 疼痛上升 {delta} 分"
                            if lang == "zh"
                            else f"⚠ Pain ↑ {delta}"
                        )
                    if safety_flag:
                        apply_difficulty("easy")
                        st.warning(
                            "已記錄疼痛安全提醒；下次會建議從低強度開始。"
                            if lang == "zh"
                            else "Safety note saved; the next session will start with an easy recommendation."
                        )
    with body_r:
        with st.container(border=True):
            st.markdown(
                "**💭 " + (
                    "今天的心情" if lang == "zh"
                    else "Today's mood"
                ) + "**"
            )
            mood = ui.mood_picker("mood_after_session", lang=lang)
            if st.button(
                "💾 " + ("儲存" if lang == "zh" else "Save"),
                key="save_mood_btn",
                use_container_width=True,
            ):
                hist.update_last_session(
                    _current_user_name(),
                    mood_after=int(mood),
                )
                st.toast(
                    "✓ 心情已紀錄" if lang == "zh"
                    else "✓ Mood saved",
                    icon="💭",
                )

    # ===== 關節詳細（隱藏在 expander，避免淹沒主畫面）=====
    with st.expander(
        "🦴 " + t("joint_detail", lang),
        expanded=False,
    ):
        rows = [
            {
                "關節" if lang == "zh" else "Joint": k,
                ("平均偏差 (°)" if lang == "zh" else "Mean dev (°)"):
                    round(v["mean_dev"], 1),
                ("最大偏差 (°)" if lang == "zh" else "Max dev (°)"):
                    round(v["max_dev"], 1),
                ("取樣點數" if lang == "zh" else "Samples"):
                    v.get("samples", 0),
            }
            for k, v in a["joints"].items()
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True)

    # ===== 操作列 =====
    ui.section_eyebrow("接下來" if lang == "zh" else "Next")
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        png_bytes = _overlay_png_bytes(a)
        pdf = report.generate_pdf_report(
            user_name=_current_user_display_name() or _current_user_name(),
            age=int((st.session_state.user or {}).get("age", 65)),
            exercise=a["template"]["name"],
            score=score,
            joint_scores=a["joints"],
            messages=a["messages"],
            rep_count=a.get("rep_count"),
            neural_scores=a.get("neural_scores"),
            overlay_png=png_bytes,
        )
        st.download_button(
            "📄 " + t("export_pdf", lang),
            data=pdf, file_name="rehab_report.pdf",
            mime="application/pdf", use_container_width=True,
        )
    with e2:
        csv = report.generate_history_csv(
            hist.load(
                _current_user_name()
            ).get("sessions", [])
        )
        st.download_button(
            "📊 " + t("export_csv", lang),
            data=csv, file_name="rehab_history.csv",
            mime="text/csv", use_container_width=True,
        )
    with e3:
        if st.button("🔁 " + t("retry", lang),
                     use_container_width=True):
            goto("record")
    with e4:
        if st.button("🏃 " + t("another", lang),
                     type="primary", use_container_width=True):
            goto("home")


def _overlay_png_bytes(a: dict) -> bytes:
    mid = len(a["frames"]) // 2
    f = a["frames"][mid]
    overlay = viz.overlay_feedback(
        f["image"], f["image_kp"], a["joints"],
        threshold=st.session_state.settings["threshold"],
    )
    ok, buf = cv2.imencode(".png", overlay)
    return buf.tobytes() if ok else b""


def _render_angle_chart(a: dict) -> None:
    lang = get_lang()
    dominant = scoring._dominant_joint(  # noqa: SLF001
        a["patient_series"], exercise_hint=a["template"]["key"],
    )
    patient = a["patient_series"][dominant]
    template = a["template_series"].get(dominant)
    if template is None:
        st.caption("無範本對照資料。")
        return
    t_axis = np.linspace(0, 1, len(patient))
    tmpl_rs = np.interp(
        t_axis, np.linspace(0, 1, len(template)), template,
    )
    patient_label = (
        f"{dominant} (患者)" if lang == "zh"
        else f"{dominant} (Patient)"
    )
    tmpl_label = (
        f"{dominant} (範本)" if lang == "zh"
        else f"{dominant} (Template)"
    )
    df = pd.DataFrame({
        patient_label: patient,
        tmpl_label: tmpl_rs,
    })
    st.line_chart(df, height=280)


# ============================================================
# 進度
# ============================================================
def view_progress() -> None:
    lang = get_lang()
    name = _current_user_name()
    display_name = _current_user_display_name() or name
    data = hist.load(name)
    sessions = data.get("sessions", [])
    earned, streak = hist.compute_badges(name)

    avg = (
        sum(s["score"] for s in sessions) / len(sessions)
        if sessions else 0.0
    )
    chips = [
        f"🔥 {streak} {t('day_unit', lang)}",
        f"🎯 {len(sessions)} {('次' if lang == 'zh' else 'sessions')}",
        f"💎 {avg:.1f}",
    ]
    ui.hero(
        f"📈 {t('progress_title', lang)} — {display_name}",
        ("您的訓練數據摘要" if lang == "zh"
         else "Your training summary"),
        chips=chips,
        variant="warm",
    )

    if not sessions:
        st.info(t("no_sessions", lang))
        if st.button("← " + t("back", lang)):
            goto("home")
        return

    ui.level_badge(hist.current_level(hist.compute_xp(name)), lang=lang)

    cols = st.columns(4)
    with cols[0]:
        ui.streak_card(streak)
    with cols[1]:
        ui.stat_card("🎯", t("session_count", lang),
                     str(len(sessions)))
    with cols[2]:
        ui.stat_card("💎", t("avg_score", lang), f"{avg:.1f}")
    with cols[3]:
        best = max(s["score"] for s in sessions)
        ui.stat_card(
            "🏆",
            "歷史最佳" if lang == "zh" else "All-time best",
            f"{best:.1f}",
        )

    st.markdown("")
    st.subheader("📅 " + (
        "活動行事曆" if lang == "zh" else "Activity calendar"
    ))
    cal_fig = ui.plot_activity_calendar(sessions, weeks=14)
    if cal_fig:
        st.plotly_chart(cal_fig, use_container_width=True)
    else:
        st.info("Plotly 未安裝，請執行 pip install plotly。")

    st.subheader("📈 " + t("trend", lang))
    trend_fig = ui.plot_score_trend(sessions, window=5)
    if trend_fig:
        st.plotly_chart(trend_fig, use_container_width=True)
    else:
        df = pd.DataFrame({"score": [s["score"] for s in sessions]})
        st.line_chart(df)

    pain_fig = ui.plot_pain_change(sessions, lookback=10)
    if pain_fig:
        st.subheader("🩹 " + (
            "疼痛變化（最近 10 次）" if lang == "zh"
            else "Pain change (last 10)"
        ))
        st.plotly_chart(pain_fig, use_container_width=True)

    st.subheader("🏅 " + t("badges", lang))
    if earned:
        badges = [
            (
                hist.BADGES[k][0].split(" ")[0],
                hist.BADGES[k][0].split(" ", 1)[-1],
                hist.BADGES[k][1],
            )
            for k in sorted(earned) if k in hist.BADGES
        ]
        ui.badge_grid(badges)
    else:
        st.caption("完成首次訓練即可解鎖徽章。")

    st.subheader("📋 " + t("history", lang))
    for s in reversed(sessions[-30:]):
        ts_str = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(s["ts"])
        )
        with st.expander(
            f"⏰ {ts_str}  ｜  🏃 {s['exercise']}  ｜  "
            f"💎 {s['score']:.1f}",
        ):
            cc = st.columns(3)
            cc[0].metric(t("overall_score", lang), f"{s['score']:.1f}")
            cc[1].metric(
                t("rep_count", lang), s.get("rep_count", "-"),
            )
            if "pain_before" in s:
                pb = s.get("pain_before")
                pa = s.get("pain_after", "-")
                cc[2].metric(
                    "疼痛 前→後" if lang == "zh"
                    else "Pain before→after",
                    f"{pb} → {pa}",
                )
            if s.get("joints"):
                jrows = [
                    {
                        "關節": k,
                        "平均偏差": round(v.get("mean_dev", 0), 1),
                        "最大偏差": round(v.get("max_dev", 0), 1),
                    }
                    for k, v in s["joints"].items()
                ]
                st.dataframe(
                    jrows, hide_index=True, use_container_width=True,
                )

    st.markdown("")
    csv = report.generate_history_csv(sessions)
    st.download_button(
        "📊 " + t("export_csv", lang),
        data=csv, file_name=f"{display_name}_history.csv",
        mime="text/csv",
    )

    st.divider()
    if st.button("← " + t("back", lang)):
        goto("home")


# ============================================================
# 自訂範本
# ============================================================
def view_custom() -> None:
    lang = get_lang()
    ui.hero(
        "🎬 " + t("record_template", lang),
        t("custom_desc", lang),
    )

    with st.container(border=True):
        name = st.text_input(t("template_name", lang))
        desc = st.text_area(t("template_desc", lang), height=80)
        cue = st.text_area(t("template_cue", lang), height=60)
        category = st.selectbox(
            "分類" if lang == "zh" else "Category",
            ["custom", "upper", "lower", "balance"],
            index=0,
        )

    uploaded = st.file_uploader(
        t("upload_video", lang) + "（"
        + ("治療師/專家示範" if lang == "zh" else "Therapist demo")
        + "）",
        type=["mp4", "mov", "avi", "mkv"],
    )
    if uploaded is not None and st.button(
        "▶ " + t("start_analysis", lang), type="primary",
    ):
        if not pe.pose_available():
            _show_pose_engine_unavailable(lang)
            return

        suffix = Path(uploaded.name).suffix or ".mp4"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(uploaded.read())
        tmp.close()

        with st.spinner("抽取示範動作中…"):
            est = None
            try:
                est = pe.PoseEstimator(
                    smooth_alpha=st.session_state.settings["ema_alpha"],
                )
                seq, _, _ = est.extract_video(tmp.name, max_frames=240)
            except Exception as exc:
                st.error(
                    "示範影片分析失敗，請確認影片格式與姿態引擎狀態。"
                    if lang == "zh"
                    else "Demo video analysis failed. Please check the video and pose engine."
                )
                st.exception(exc)
                return
            finally:
                if est is not None:
                    est.close()

        if len(seq) < 5:
            st.error(t("no_person", lang))
            return

        angle_series = scoring.sequence_to_angle_series(seq)
        series_to_save = {
            k: [float(x) for x in v]
            for k, v in angle_series.items()
        }
        if not name.strip():
            st.warning(
                "請輸入範本名稱。" if lang == "zh"
                else "Please enter a template name."
            )
            return
        tpl = tpl_mod.save_custom(
            name=name.strip(),
            description=desc.strip() or name.strip(),
            cue=cue.strip() or "-",
            angle_series=series_to_save,
            category=category,
        )
        st.success(f"{t('template_saved', lang)} ({tpl['key']})")
        st.balloons()

    st.divider()
    customs = tpl_mod.load_custom()
    if customs:
        st.subheader(
            "已儲存的自訂範本" if lang == "zh"
            else "Saved custom templates"
        )
        for k, v in customs.items():
            with st.container(border=True):
                cc = st.columns([4, 1])
                cc[0].markdown(f"**{v['name']}**")
                cc[0].caption(v.get("description", ""))
                if cc[1].button("🗑", key=f"custom_del_{k}"):
                    tpl_mod.delete_custom(k)
                    st.rerun()

    if st.button("← " + t("back", lang)):
        goto("home")


# ============================================================
# 臨床端總覽
# ============================================================
def view_clinician() -> None:
    lang = get_lang()
    ui.hero(
        "🩺 " + t("clinician", lang),
        t("clinician_desc", lang),
    )

    users = hist.list_users()
    if not users:
        st.info(t("no_sessions", lang))
        if st.button("← " + t("back", lang)):
            goto("home")
        return

    total_sessions = sum(u["session_count"] for u in users)
    avg_score = (
        sum(u["avg_score"] * u["session_count"] for u in users)
        / total_sessions if total_sessions else 0
    )
    cols = st.columns(3)
    with cols[0]:
        ui.stat_card("👥", t("user_count", lang), str(len(users)))
    with cols[1]:
        ui.stat_card(
            "📋", t("session_count", lang), str(total_sessions),
        )
    with cols[2]:
        ui.stat_card("💎", t("avg_score", lang), f"{avg_score:.1f}")

    st.markdown("")
    rows = [
        {
            ("使用者" if lang == "zh" else "User"): u["name"],
            ("年齡" if lang == "zh" else "Age"): u.get("age", "-"),
            ("完成度" if lang == "zh" else "Profile"): (
                f"{hist.profile_completion(u.get('profile', {}))}%"
            ),
            ("復健原因" if lang == "zh" else "Reason"): (
                u.get("profile", {}).get("diagnosis", "-") or "-"
            ),
            ("訓練側" if lang == "zh" else "Side"): (
                u.get("profile", {}).get("affected_side", "-") or "-"
            ),
            ("次數" if lang == "zh" else "Sessions"):
                u["session_count"],
            ("平均分數" if lang == "zh" else "Avg score"):
                round(u["avg_score"], 1),
            ("最近訓練" if lang == "zh" else "Last"): (
                time.strftime(
                    "%Y-%m-%d", time.localtime(u["last_ts"]),
                ) if u["last_ts"] else "-"
            ),
        }
        for u in users
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)

    if st.button("← " + t("back", lang)):
        goto("home")


# ============================================================
# AI 教練：動作教學與語音引導
# ============================================================
def _coach_teaching_script(tpl: dict, lang: str) -> list[dict]:
    name = tpl.get("name", "")
    desc = tpl.get("description", "")
    cue = tpl.get("cue", "")
    if lang == "zh":
        return [
            {"phase": "準備", "line": f"我們今天練習「{name}」。先站穩或坐穩，讓鏡頭看得到全身。"},
            {"phase": "示範", "line": desc or "先看一次動作路徑，再跟著節奏慢慢做。"},
            {"phase": "重點", "line": cue or "保持身體穩定，動作慢、穩、完整。"},
            {"phase": "節奏", "line": "抬起或伸展時數三秒，停一下，再用三秒回到起始位置。"},
            {"phase": "安全", "line": "如果疼痛明顯增加、頭暈或不舒服，請立刻停止並休息。"},
        ]
    return [
        {"phase": "Setup", "line": f"Today's exercise is {name}. Stand or sit steady and keep your full body in frame."},
        {"phase": "Demo", "line": desc or "Watch the movement path once, then follow slowly."},
        {"phase": "Cue", "line": cue or "Stay stable and move slowly through the full range."},
        {"phase": "Tempo", "line": "Move for three seconds, pause briefly, then return for three seconds."},
        {"phase": "Safety", "line": "Stop and rest if pain increases, dizziness appears, or anything feels wrong."},
    ]


def _coach_common_mistakes(tpl: dict, lang: str) -> list[dict]:
    category = tpl.get("category", "custom")
    if category == "upper":
        zh = [
            ("聳肩", "肩膀往耳朵靠近時，先放鬆再重新開始。"),
            ("手肘彎太多", "若動作要求伸直，手肘保持柔和伸展，不要鎖死。"),
            ("速度太快", "放慢速度，讓上抬和放下都能被控制。"),
        ]
        en = [
            ("Shrugging", "Relax the shoulders before starting again."),
            ("Over-bending elbows", "Keep a gentle extension when the exercise calls for straight arms."),
            ("Moving too fast", "Slow down so both lift and return are controlled."),
        ]
    elif category == "lower":
        zh = [
            ("膝蓋內夾", "膝蓋朝腳尖方向，不要往內倒。"),
            ("背部彎曲", "胸口打開，背部維持自然挺直。"),
            ("重心不穩", "先扶椅背或牆面，穩定後再降低輔助。"),
        ]
        en = [
            ("Knees collapsing inward", "Keep knees tracking toward the toes."),
            ("Rounding the back", "Open the chest and keep a natural upright spine."),
            ("Unstable balance", "Use a chair or wall first, then reduce support gradually."),
        ]
    else:
        zh = [
            ("身體歪斜", "保持軀幹直立，必要時扶著穩固物。"),
            ("憋氣", "動作時維持自然呼吸。"),
            ("幅度勉強", "做到可控制、無明顯疼痛的範圍即可。"),
        ]
        en = [
            ("Leaning", "Keep the trunk upright and use stable support if needed."),
            ("Holding breath", "Keep breathing naturally while moving."),
            ("Forcing range", "Stay within a controlled, comfortable range."),
        ]
    rows = zh if lang == "zh" else en
    return [{"title": title, "detail": detail} for title, detail in rows]


def _fallback_coach_guidance(tpl: dict, lang: str) -> dict:
    return {
        "encouragement": (
            f"我會陪你把「{tpl.get('name', '')}」做得慢一點、穩一點。"
            if lang == "zh"
            else f"I'll help you move through {tpl.get('name', '')} slowly and steadily."
        ),
        "script": _coach_teaching_script(tpl, lang),
        "mistakes": _coach_common_mistakes(tpl, lang),
    }


def _normalize_coach_guidance(data: dict, tpl: dict, lang: str) -> dict:
    fallback = _fallback_coach_guidance(tpl, lang)

    script: list[dict] = []
    for row in data.get("script", []):
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase") or "").strip()
        line = str(row.get("line") or "").strip()
        if phase and line:
            script.append({"phase": phase, "line": line})

    mistakes: list[dict] = []
    for row in data.get("mistakes", []):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        detail = str(row.get("detail") or "").strip()
        if title and detail:
            mistakes.append({"title": title, "detail": detail})

    encouragement = str(data.get("encouragement") or "").strip()
    return {
        "encouragement": encouragement or fallback["encouragement"],
        "script": script or fallback["script"],
        "mistakes": mistakes[:4] or fallback["mistakes"],
    }


def _coach_cache_key(tpl_key: str, lang: str) -> str:
    return f"{tpl_key}:{lang}"


def _coach_profile() -> dict:
    user = st.session_state.user or {}
    return {
        "age": user.get("age"),
        "diagnosis": user.get("diagnosis") or user.get("condition"),
        "affected_side": user.get("affected_side"),
        "mobility_aid": user.get("mobility_aid"),
        "pain_area": user.get("pain_area"),
    }


def _coach_full_script_text(tpl: dict, lang: str, script: list[dict] | None = None) -> str:
    rows = script or _coach_teaching_script(tpl, lang)
    lines = [str(row.get("line", "")).strip() for row in rows if row.get("line")]
    return "。".join(lines) if lang == "zh" else " ".join(lines)


def _render_coach_script(script: list[dict], lang: str) -> None:
    for idx, row in enumerate(script, start=1):
        with st.container(border=True):
            c1, c2 = st.columns([1, 7])
            c1.markdown(f"### {idx}")
            c2.markdown(f"**{row['phase']}**")
            c2.write(row["line"])


def view_ai_media() -> None:
    lang = get_lang()
    ui.hero(
        "✨ AI 教練" if lang == "zh" else "✨ AI Coach",
        "選擇動作後，由教練用步驟、節奏、常見錯誤與語音帶你完成練習。"
        if lang == "zh"
        else "Choose an exercise and let the coach guide setup, tempo, mistakes, and voice cues.",
    )

    templates_all = tpl_mod.all_templates()
    keys = list(templates_all.keys())
    default_idx = 0
    if st.session_state.exercise_key in keys:
        default_idx = keys.index(st.session_state.exercise_key)
    tpl_key = st.selectbox(
        "選擇動作" if lang == "zh" else "Exercise",
        keys,
        index=default_idx,
        format_func=lambda k: templates_all[k]["name"],
        key="coach_exercise_select",
    )
    tpl = templates_all[tpl_key]
    st.session_state.exercise_key = tpl_key

    cache = st.session_state.setdefault("ai_coach_guidance", {})
    cache_key = _coach_cache_key(tpl_key, lang)
    guidance = cache.get(cache_key)
    configured = ai_coach.is_configured()

    status_col, action_col = st.columns([2.2, 1])
    with status_col:
        if configured:
            st.success(
                "Gemini 教練已連線，會直接生成本動作的教學。"
                if lang == "zh"
                else "Gemini coach is connected and will generate this guide."
            )
        else:
            st.info(
                "尚未設定 Gemini API，先使用內建教學。"
                if lang == "zh"
                else "Gemini API is not configured, so the built-in guide is shown."
            )
    with action_col:
        refresh_guidance = st.button(
            "重新生成教學" if lang == "zh" else "Regenerate guide",
            disabled=not configured,
            use_container_width=True,
            key=f"coach_refresh_{tpl_key}_{lang}",
        )

    if configured and (guidance is None or refresh_guidance):
        with st.spinner(
            "AI 教練正在整理教學..." if lang == "zh"
            else "AI coach is preparing the guide..."
        ):
            try:
                generated = ai_coach.generate_coaching(
                    tpl,
                    profile=_coach_profile(),
                    lang=lang,
                )
                guidance = _normalize_coach_guidance(generated, tpl, lang)
                cache[cache_key] = guidance
            except Exception as exc:
                guidance = _fallback_coach_guidance(tpl, lang)
                st.warning(
                    "AI 教練暫時無法回應，已先切回內建教學。"
                    if lang == "zh"
                    else "AI coach is temporarily unavailable; showing the built-in guide."
                )
                st.caption(str(exc)[:280])

    if guidance is None:
        guidance = _fallback_coach_guidance(tpl, lang)

    coach_message = guidance.get("encouragement") or (
        f"我會先教你「{tpl['name']}」的準備、節奏和安全重點。準備好後就進入錄影練習。"
        if lang == "zh"
        else f"I'll coach setup, tempo, and safety for {tpl['name']}. When ready, start practice."
    )
    ui.coach_card(
        st.session_state.settings.get("coach", "starbuddy"),
        state="ready",
        lang=lang,
        message=coach_message,
    )

    left, right = st.columns([1, 1.1], gap="large")
    with left:
        ui.demo_figure_3d_video(tpl, lang=lang)
        st.markdown("#### " + ("教練語音" if lang == "zh" else "Coach voice"))
        full_text = _coach_full_script_text(tpl, lang, guidance.get("script"))
        v1, v2 = st.columns(2)
        with v1:
            if st.button(
                "🔊 播放完整教學" if lang == "zh" else "🔊 Play full guide",
                use_container_width=True,
                key="coach_play_full",
            ):
                voice = get_voice()
                if voice:
                    voice.say(full_text)
                else:
                    st.info(
                        "系統語音尚不可用，請使用右側瀏覽器語音。"
                        if lang == "zh"
                        else "System voice is unavailable. Use browser speech."
                    )
        with v2:
            ui.browser_speech_button(
                full_text,
                "瀏覽器語音" if lang == "zh" else "Browser voice",
                lang=lang,
            )

    with right:
        st.markdown("#### " + ("跟著做" if lang == "zh" else "Follow along"))
        _render_coach_script(guidance.get("script", []), lang)

    st.divider()
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### " + ("常見錯誤" if lang == "zh" else "Common mistakes"))
        for item in guidance.get("mistakes", []):
            with st.container(border=True):
                st.markdown(f"**{item['title']}**")
                st.caption(item["detail"])
    with c2:
        st.markdown("#### " + ("錄影前重點" if lang == "zh" else "Before recording"))
        ui.voice_instruction_card(
            _record_guidance_steps(tpl, lang),
            cue=tpl.get("cue", ""),
            voice_enabled=bool(st.session_state.settings.get("enable_voice", True)),
            lang=lang,
        )

    st.divider()
    n1, n2, n3 = st.columns(3)
    if n1.button(
        "🎥 開始練習" if lang == "zh" else "🎥 Start practice",
        type="primary",
        use_container_width=True,
        key="coach_start_record",
    ):
        goto("record")
    if n2.button(
        "🏠 回主選單" if lang == "zh" else "🏠 Home",
        use_container_width=True,
        key="coach_back_home",
    ):
        goto("home" if st.session_state.user else "welcome")
    if n3.button(
        "⚙ 語音設定" if lang == "zh" else "⚙ Voice settings",
        use_container_width=True,
        key="coach_voice_settings",
    ):
        goto("settings")


# ============================================================
# 設定
# ============================================================
def view_settings() -> None:
    lang = get_lang()
    ui.hero(
        "⚙ " + t("settings", lang),
        "客製化分析靈敏度、語言、語音回饋。"
        if lang == "zh"
        else "Customize sensitivity, language, voice.",
    )

    s = st.session_state.settings

    try:
        from theme import render_theme_picker
        render_theme_picker()
        st.markdown("")
    except ImportError:
        pass

    # ---- 卡通教練角色選擇 ----
    st.markdown("#### " + (
        "🎭 卡通教練" if lang == "zh" else "🎭 Cartoon coach"
    ))
    cur_coach = s.get("coach", "starbuddy")
    chosen = ui.coach_picker(cur_coach, "coach_pick", lang=lang)
    if chosen and chosen != cur_coach:
        s["coach"] = chosen
        st.toast(
            f"✓ 已切換為 {coach_mod.display_name(chosen, lang)}"
            if lang == "zh"
            else f"✓ Switched to {coach_mod.display_name(chosen, lang)}",
            icon="🎭",
        )
        st.rerun()
    # 預覽當前選擇的教練
    ui.coach_card(s.get("coach", "starbuddy"), state="greet", lang=lang)
    st.markdown("")

    # ---- 音訊診斷 ----
    import tts as tts_mod
    st.markdown("#### " + (
        "🔊 音訊輸出" if lang == "zh" else "🔊 Audio output"
    ))
    status = tts_mod.voice_status()
    ui.audio_doctor(
        bool(s.get("enable_voice", True) and s.get("live_voice", True)),
        server_voice=status.get("edge_neural") or status.get("windows_sapi") or status.get("pyttsx3"),
        browser_voice=status.get("browser_wav"),
        lang=lang,
    )
    test_text = (
        "音訊測試成功。接下來系統會用語音提醒你動作方向。"
        if lang == "zh"
        else "Audio test successful. The system will speak movement cues."
    )
    ac1, ac2 = st.columns(2)
    if ac1.button(
        "播放系統測試音" if lang == "zh" else "Play system audio",
        use_container_width=True,
        key="settings_audio_wav",
    ):
        audio = tts_mod.synthesize_audio_bytes(test_text, lang=lang)
        if audio:
            data, fmt = audio
            st.audio(data, format=fmt, autoplay=True)
        else:
            st.warning(
                "系統音訊不可用，請使用瀏覽器語音測試。"
                if lang == "zh"
                else "System audio unavailable. Try browser speech."
            )
    with ac2:
        ui.browser_speech_button(
            test_text,
            "瀏覽器語音測試" if lang == "zh" else "Browser speech test",
            lang=lang,
        )
    st.markdown("")

    # ---- 難度快速切換（form 之外，立即套用）----
    st.markdown("#### " + (
        "🎚 難度等級" if lang == "zh" else "🎚 Difficulty"
    ))
    cur_level = s.get("difficulty", "normal")
    diff_cols = st.columns(3)
    for col, (key, meta) in zip(
        diff_cols, DIFFICULTY_PRESETS.items(),
    ):
        is_cur = key == cur_level
        label = (meta["label_zh"] if lang == "zh"
                 else meta["label_en"])
        btn_label = f"{meta['icon']} {label}"
        if col.button(
            btn_label + ("  ✓" if is_cur else ""),
            key=f"diff_{key}",
            type="primary" if is_cur else "secondary",
            use_container_width=True,
        ):
            apply_difficulty(key)
            st.toast(
                f"✓ 已套用 {label}" if lang == "zh"
                else f"✓ {label} applied",
                icon="🎚",
            )
            st.rerun()
    st.caption(
        "⚙ 偏差門檻越低代表評分越嚴格；切換後會自動更新下方數值。"
        if lang == "zh"
        else "Lower threshold = stricter scoring."
    )
    st.markdown("")

    # ---- 詳細設定 form ----
    with st.form("settings_form"):
        new_lang = st.selectbox(
            t("language", lang),
            options=list(LANGS),
            format_func=language_label,
            index=list(LANGS).index(s.get("lang", "zh")),
        )
        new_thresh = st.slider(
            t("threshold", lang),
            min_value=5.0, max_value=45.0,
            value=float(s.get("threshold", 15.0)), step=1.0,
        )
        new_ema = st.slider(
            t("ema_alpha", lang),
            min_value=0.1, max_value=1.0,
            value=float(s.get("ema_alpha", 0.6)), step=0.05,
        )
        new_goal = st.number_input(
            "每日訓練目標次數" if lang == "zh"
            else "Daily session goal",
            min_value=1, max_value=10,
            value=int(s.get("daily_goal", 1)), step=1,
        )
        new_senior = st.checkbox(
            t("senior_mode", lang),
            value=bool(s.get("senior_mode", True)),
        )
        new_voice = st.checkbox(
            t("enable_voice", lang),
            value=bool(s.get("enable_voice", True)),
        )
        new_live_voice = st.checkbox(
            "即時鏡頭語音提醒（手臂往上 / 往下）"
            if lang == "zh" else
            "Live voice cues (arms up / down)",
            value=bool(s.get("live_voice", True)),
            disabled=not new_voice,
        )
        new_voice_cooldown = st.slider(
            "語音提醒間隔（秒）" if lang == "zh"
            else "Voice cue interval (seconds)",
            min_value=2.0, max_value=10.0,
            value=float(s.get("voice_cooldown", 4.5)),
            step=0.5,
            disabled=not new_voice or not new_live_voice,
        )
        new_nw = st.slider(
            "神經評分權重" if lang == "zh"
            else "Neural score weight",
            min_value=0.0, max_value=1.0,
            value=float(s.get("neural_weight", 0.4)),
            step=0.05,
        )
        saved = st.form_submit_button(
            "💾 " + t("save", lang), type="primary",
        )

    if saved:
        st.session_state.settings.update({
            "lang": new_lang,
            "threshold": new_thresh,
            "ema_alpha": new_ema,
            "daily_goal": int(new_goal),
            "senior_mode": new_senior,
            "enable_voice": new_voice,
            "live_voice": new_live_voice,
            "voice_cooldown": new_voice_cooldown,
            "neural_weight": new_nw,
        })
        st.session_state.tts_engine = None
        st.toast("✓ " + t("save", lang), icon="✅")
        time.sleep(0.3)
        goto("home")

    st.caption(t("disclaimer", lang))

    if st.button("← " + t("back", lang)):
        goto("home")


# ============================================================
# 新模組 View Functions
# ============================================================
def _render_journal_calendar_sync(
    today_journal: dict | None,
    user_id: str | None,
    lang: str,
) -> None:
    """Render Google Calendar sync controls for journal entries."""
    from service_integrations import (
        GOOGLE_CALENDAR_SCOPES,
        disconnect,
        get_connection,
        google_calendar_template_url,
        google_oauth_url,
        sync_journal_to_google_calendar,
    )

    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(
                "#### 📅 Google 日曆同步"
                if lang == "zh"
                else "#### 📅 Google Calendar sync"
            )
            st.caption(
                "把每日健康日誌寫入 Google Calendar，方便照護者或治療師跟行程一起查看。"
                if lang == "zh"
                else "Write daily journal entries into Google Calendar alongside care schedules."
            )
        with c2:
            if not user_id:
                st.info(t("not_logged_in", lang))
                return
            conn = get_connection(user_id, "google_calendar")
            if conn:
                st.success("已連接" if lang == "zh" else "Connected")
                if st.button(
                    "解除連接" if lang == "zh" else "Disconnect",
                    key="journal_calendar_disconnect",
                    use_container_width=True,
                ):
                    disconnect(user_id, "google_calendar")
                    st.rerun()
            else:
                url, missing = google_oauth_url(
                    "google_calendar",
                    GOOGLE_CALENDAR_SCOPES,
                )
                if url:
                    st.link_button(
                        "連接 Google Calendar"
                        if lang == "zh"
                        else "Connect Google Calendar",
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

        if today_journal:
            sync_cols = st.columns(2)
            with sync_cols[0]:
                if get_connection(user_id, "google_calendar") and st.button(
                    "同步今日日誌" if lang == "zh" else "Sync today's journal",
                    key="journal_calendar_sync_today",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        sync_journal_to_google_calendar(user_id, today_journal)
                        st.success(
                            "已同步到 Google 日曆"
                            if lang == "zh"
                            else "Synced to Google Calendar"
                        )
                    except Exception as exc:
                        st.error(str(exc))
            with sync_cols[1]:
                st.link_button(
                    "用 Google 日曆開啟"
                    if lang == "zh"
                    else "Open in Google Calendar",
                    google_calendar_template_url(today_journal),
                    use_container_width=True,
                )
        else:
            st.caption(
                "填寫今日日誌後即可同步到日曆。"
                if lang == "zh"
                else "Save today's journal to enable calendar sync."
            )


def view_journal() -> None:
    """每日健康日記頁面：心情、精力、睡眠、備注、天氣。"""
    import journal as journal_mod
    from service_integrations import (
        complete_google_oauth_callback,
        get_connection,
        sync_journal_to_google_calendar,
    )
    lang = get_lang()

    st.title("📝 " + t("step_journal", lang))

    name = _require_user_name(lang)
    if not name:
        return
    user_id = _active_user_id()
    calendar_connected = False
    if user_id:
        callback = complete_google_oauth_callback(user_id, "google_calendar")
        if callback:
            if callback.get("ok"):
                st.success(
                    "Google Calendar 已連接"
                    if lang == "zh"
                    else "Google Calendar connected"
                )
            else:
                st.error(callback.get("error", "OAuth failed"))
        calendar_connected = bool(get_connection(user_id, "google_calendar"))

    # Check if journal already filled today
    today_journal = journal_mod.today_journal(name)
    _render_journal_calendar_sync(today_journal, user_id, lang)

    with st.container():
        st.subheader(t("today", lang) if lang == "zh" else "Today")

        col1, col2, col3 = st.columns(3)

        # Mood selector (5 emoji)
        with col1:
            st.write("😔 💭 🙂 😊 🤩")
            mood = st.radio(
                ("心情" if lang == "zh" else "Mood"),
                [1, 2, 3, 4, 5],
                format_func=lambda x: ["😔", "💭", "🙂", "😊", "🤩"][x - 1],
                key="journal_mood",
                horizontal=True,
            )

        with col2:
            energy = st.slider(
                "精力" if lang == "zh" else "Energy",
                1, 5, 3, key="journal_energy"
            )

        with col3:
            sleep_hours = st.slider(
                "睡眠時數" if lang == "zh" else "Sleep Hours",
                4.0, 12.0, 7.0, 0.5, key="journal_sleep"
            )

        # Weather selector
        st.write("**天氣** / Weather")
        weather_options = {"☀️ 晴天": "sunny", "⛅ 多雲": "cloudy", "🌧️ 雨天": "rainy"}
        weather_labels = {v: k for k, v in weather_options.items()}
        weather = st.radio(
            "選擇天氣" if lang == "zh" else "Select weather",
            list(weather_options.values()),
            format_func=lambda x: weather_labels[x],
            horizontal=True,
            label_visibility="collapsed",
            key="journal_weather",
        )

        # Notes
        notes = st.text_area(
            "今日備注" if lang == "zh" else "Today's Notes",
            height=100,
            key="journal_notes",
        )
        sync_after_save = st.checkbox(
            "儲存後同步到 Google 日曆"
            if lang == "zh" else
            "Sync to Google Calendar after saving",
            value=calendar_connected,
            disabled=not calendar_connected,
            key="journal_sync_after_save",
        )

        if st.button("✓ " + ("保存日記" if lang == "zh" else "Save"), key="journal_save"):
            entry = {
                "date": time.strftime("%Y-%m-%d"),
                "mood": mood,
                "energy": energy,
                "sleep_hours": sleep_hours,
                "weather": weather,
                "notes": notes,
            }
            journal_mod.save_journal(name, entry)
            if sync_after_save and user_id:
                try:
                    sync_journal_to_google_calendar(user_id, entry)
                    st.toast(
                        "已同步 Google 日曆" if lang == "zh"
                        else "Synced to Google Calendar",
                        icon="📅",
                    )
                except Exception as exc:
                    st.warning(str(exc))
            st.success("✓ " + ("日記已保存" if lang == "zh" else "Journal saved"))
            time.sleep(0.5)
            st.rerun()

    # Show today's journal if filled
    if today_journal:
        st.info(f"✓ 今日日記已填寫 / Journal filled for today")
        with st.expander("查看今日紀錄 / View today's entry"):
            st.json(today_journal)

    st.divider()

    # Historical stats
    st.subheader("💹 " + ("趨勢統計" if lang == "zh" else "Statistics"))

    stats = journal_mod.journal_stats(name, days=14)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "平均心情" if lang == "zh" else "Avg Mood",
            f"{stats['avg_mood']:.1f}/5",
        )
    with col2:
        st.metric(
            "平均精力" if lang == "zh" else "Avg Energy",
            f"{stats['avg_energy']:.1f}/5",
        )
    with col3:
        st.metric(
            "平均睡眠" if lang == "zh" else "Avg Sleep",
            f"{stats['avg_sleep']:.1f}h",
        )
    with col4:
        st.metric(
            "記錄天數" if lang == "zh" else "Days",
            stats["count"],
        )

    # Historical list
    recent = journal_mod.load_journal(name, days=30)
    if recent:
        st.subheader("📋 " + ("最近記錄" if lang == "zh" else "Recent entries"))
        for entry in reversed(recent[-10:]):
            with st.expander(
                f"📅 {entry.get('date', 'N/A')} - "
                f"{['😔', '💭', '🙂', '😊', '🤩'][int(entry.get('mood', 3)) - 1]}"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**心情:** {entry.get('mood')}/5")
                    st.write(f"**精力:** {entry.get('energy')}/5")
                with col2:
                    st.write(f"**睡眠:** {entry.get('sleep_hours')}h")
                    st.write(f"**天氣:** {entry.get('weather')}")
                if entry.get("notes"):
                    st.write(f"**備注:** {entry.get('notes')}")


def view_programs() -> None:
    """復健計畫選擇與進度追蹤。"""
    import programs as prog_mod
    lang = get_lang()

    st.title("📋 " + t("step_programs", lang))

    name = _require_user_name(lang)
    if not name:
        return

    templates_all = tpl_mod.all_templates()
    current = prog_mod.current_program(name)

    if not current:
        # Show program selection
        st.subheader("選擇復健計畫" if lang == "zh" else "Select a Program")

        programs_list = list(prog_mod.BUILTIN_PROGRAMS.items())

        cols = st.columns(2)
        for idx, (key, prog) in enumerate(programs_list):
            with cols[idx % 2]:
                with st.container(border=True):
                    st.write(f"## {prog['icon']} {prog['name']}")
                    st.write(f"**{prog['description']}**")
                    st.write(f"⏱️ {prog['weeks']} 週")
                    st.write(f"👥 {prog['target_group']}")

                    if st.button(
                        "開始計畫" if lang == "zh" else "Start",
                        key=f"start_prog_{key}",
                    ):
                        prog_mod.start_program(name, key)
                        st.success("✓ 計畫已開始" if lang == "zh" else "Program started")
                        time.sleep(0.5)
                        st.rerun()
    else:
        # Show program progress
        prog_key = current["key"]
        prog_def = prog_mod.program_details(prog_key)
        if not prog_def:
            st.error("Program not found")
            return

        st.subheader(f"{prog_def['icon']} {prog_def['name']}")
        st.write(prog_def["description"])

        completion = prog_mod.program_completion(name)
        st.progress(completion / 100, text=f"進度 / Progress: {completion:.0f}%")

        current_week = current.get("current_week", 1)
        total_weeks = current.get("weeks", 1)
        st.write(f"**第 {current_week} 週 / Week {current_week}** (共 {total_weeks} 週 / of {total_weeks})")

        # Current week schedule
        week_schedule = prog_mod.program_week_schedule(prog_key, current_week)
        if week_schedule:
            st.write("### 本週課程 / This Week's Schedule")
            st.write(f"**強度:** {week_schedule.get('intensity')}")
            st.write(f"**次數:** {week_schedule.get('sessions_per_week')}次/週")
            st.write(f"**焦點:** {week_schedule.get('focus')}")

            exercises = week_schedule.get("exercises", [])
            if exercises:
                st.write("**動作:**")
                for ex_key in exercises:
                    tpl = templates_all.get(ex_key)
                    label = tpl.get("name", ex_key) if tpl else ex_key
                    disabled = tpl is None
                    if st.button(
                        f"▶ {label}",
                        key=f"program_ex_{ex_key}",
                        disabled=disabled,
                        use_container_width=True,
                    ):
                        st.session_state.exercise_key = ex_key
                        intensity = week_schedule.get("intensity")
                        if intensity in DIFFICULTY_PRESETS:
                            apply_difficulty(intensity)
                        goto("record")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📹 開始訓練", key="prog_record"):
                week_schedule = prog_mod.program_week_schedule(prog_key, current_week)
                for ex_key in (week_schedule or {}).get("exercises", []):
                    if ex_key in templates_all:
                        st.session_state.exercise_key = ex_key
                        break
                goto("record")

        with col2:
            if st.button("❌ 結束計畫", key="prog_end"):
                if st.checkbox("確認結束此計畫？"):
                    prog_mod.end_program(name)
                    st.success("計畫已結束" if lang == "zh" else "Program ended")
                    time.sleep(0.5)
                    st.rerun()


_PAIN_JOINTS = [
    {"region": "頭頸", "en": "Head & neck", "x": 50, "y": 101, "label": "頸"},
    {"region": "左肩", "en": "Left shoulder", "x": 35, "y": 86, "label": "左肩"},
    {"region": "右肩", "en": "Right shoulder", "x": 65, "y": 86, "label": "右肩"},
    {"region": "左肘", "en": "Left elbow", "x": 25, "y": 66, "label": "左肘"},
    {"region": "右肘", "en": "Right elbow", "x": 75, "y": 66, "label": "右肘"},
    {"region": "左腕", "en": "Left wrist", "x": 18, "y": 46, "label": "左腕"},
    {"region": "右腕", "en": "Right wrist", "x": 82, "y": 46, "label": "右腕"},
    {"region": "上背", "en": "Upper back", "x": 50, "y": 76, "label": "上背"},
    {"region": "下背", "en": "Lower back", "x": 50, "y": 58, "label": "下背"},
    {"region": "左髖", "en": "Left hip", "x": 40, "y": 50, "label": "左髖"},
    {"region": "右髖", "en": "Right hip", "x": 60, "y": 50, "label": "右髖"},
    {"region": "左膝", "en": "Left knee", "x": 36, "y": 28, "label": "左膝"},
    {"region": "右膝", "en": "Right knee", "x": 64, "y": 28, "label": "右膝"},
    {"region": "左踝", "en": "Left ankle", "x": 34, "y": 8, "label": "左踝"},
    {"region": "右踝", "en": "Right ankle", "x": 66, "y": 8, "label": "右踝"},
]


def _pain_color(intensity: int) -> str:
    if intensity >= 7:
        return "#e03131"
    if intensity >= 4:
        return "#f08c00"
    if intensity >= 1:
        return "#ffd43b"
    return "#ced4da"


def _pain_level_label(intensity: int, lang: str) -> str:
    if intensity >= 7:
        return "高" if lang == "zh" else "High"
    if intensity >= 4:
        return "中" if lang == "zh" else "Moderate"
    if intensity >= 1:
        return "低" if lang == "zh" else "Mild"
    return "無" if lang == "zh" else "None"


def _pain_joint_key(region: str) -> str:
    return "pain_joint_" + region.encode("unicode_escape").decode("ascii")


def _selected_pain_region(event) -> str | None:
    if not event:
        return None
    selection = event.get("selection", {}) if isinstance(event, dict) else getattr(event, "selection", {})
    points = selection.get("points", []) if isinstance(selection, dict) else getattr(selection, "points", [])
    if not points:
        return None

    point = points[0]
    customdata = point.get("customdata") if isinstance(point, dict) else getattr(point, "customdata", None)
    if isinstance(customdata, (list, tuple)) and customdata:
        customdata = customdata[0]
    if isinstance(customdata, str) and customdata:
        return customdata

    point_number = point.get("point_number") if isinstance(point, dict) else getattr(point, "point_number", None)
    if isinstance(point_number, int) and 0 <= point_number < len(_PAIN_JOINTS):
        return _PAIN_JOINTS[point_number]["region"]
    return None


def _pain_body_figure(pain_regions: dict[str, int], selected_region: str | None, lang: str):
    import plotly.graph_objects as go

    points = {joint["region"]: joint for joint in _PAIN_JOINTS}
    segments = [
        ("頭頸", "上背"), ("左肩", "右肩"), ("上背", "下背"),
        ("左肩", "左肘"), ("左肘", "左腕"), ("右肩", "右肘"),
        ("右肘", "右腕"), ("左髖", "右髖"), ("下背", "左髖"),
        ("下背", "右髖"), ("左髖", "左膝"), ("左膝", "左踝"),
        ("右髖", "右膝"), ("右膝", "右踝"),
    ]
    line_x, line_y = [], []
    for start, end in segments:
        line_x += [points[start]["x"], points[end]["x"], None]
        line_y += [points[start]["y"], points[end]["y"], None]

    marker_sizes = []
    marker_colors = []
    marker_lines = []
    for joint in _PAIN_JOINTS:
        intensity = int(pain_regions.get(joint["region"], 0))
        marker_sizes.append(18 + intensity * 1.8)
        marker_colors.append(_pain_color(intensity))
        marker_lines.append(4 if joint["region"] == selected_region else 1.5)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=line_x,
        y=line_y,
        mode="lines",
        line=dict(color="#adb5bd", width=9),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[joint["x"] for joint in _PAIN_JOINTS],
        y=[joint["y"] for joint in _PAIN_JOINTS],
        mode="markers+text",
        text=[
            joint["label"] if lang == "zh" else joint["en"].replace(" ", "<br>")
            for joint in _PAIN_JOINTS
        ],
        textposition="top center",
        customdata=[
            [joint["region"], int(pain_regions.get(joint["region"], 0))]
            for joint in _PAIN_JOINTS
        ],
        marker=dict(
            size=marker_sizes,
            color=marker_colors,
            line=dict(color="#ffffff", width=marker_lines),
            opacity=0.95,
        ),
        hovertemplate=(
            "%{customdata[0]}<br>"
            + ("疼痛" if lang == "zh" else "Pain")
            + ": %{customdata[1]}/10<extra></extra>"
        ),
        showlegend=False,
    ))
    fig.update_layout(
        height=600,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0)",
        xaxis=dict(visible=False, range=[5, 95], fixedrange=True),
        yaxis=dict(visible=False, range=[0, 116], fixedrange=True, scaleanchor="x"),
        clickmode="event+select",
        dragmode=False,
        selectdirection="any",
        shapes=[
            dict(
                type="circle",
                xref="x",
                yref="y",
                x0=42,
                y0=101,
                x1=58,
                y1=115,
                line=dict(color="#adb5bd", width=7),
                fillcolor="rgba(255,255,255,0.7)",
            ),
            dict(
                type="path",
                path="M 36 82 Q 50 70 64 82 L 61 52 Q 50 44 39 52 Z",
                line=dict(color="#adb5bd", width=5),
                fillcolor="rgba(173,181,189,0.08)",
            ),
        ],
    )
    return fig


def view_pain_map() -> None:
    """疼痛身體地圖。"""
    import pain_map as pain_mod
    lang = get_lang()

    st.title("🗺️ " + t("step_pain_map", lang))

    name = _require_user_name(lang)
    if not name:
        return

    pain_regions = st.session_state.setdefault("pain_joint_scores", {})
    st.session_state.setdefault("pain_map_epoch", 0)
    selected_region = st.session_state.get("pain_selected_region")

    st.subheader("點選人型關節標記疼痛指數" if lang == "zh" else "Select joints on the body map")
    st.caption(
        "在圖上點選關節，再於右側調整 0-10 疼痛分數。0 代表清除該關節標記。"
        if lang == "zh" else
        "Click a joint, then set pain from 0-10 on the right. A score of 0 clears that marker."
    )

    map_col, edit_col = st.columns([1.35, 1])
    with map_col:
        event = st.plotly_chart(
            _pain_body_figure(pain_regions, selected_region, lang),
            use_container_width=True,
            key="pain_body_map",
            on_select="rerun",
            selection_mode="points",
            config={"displayModeBar": False, "scrollZoom": False},
        )
        selected_from_chart = _selected_pain_region(event)
        if selected_from_chart:
            st.session_state.pain_selected_region = selected_from_chart
            selected_region = selected_from_chart
        st.caption(
            "點圖上的圓點選關節；若瀏覽器未觸發，可用下方按鈕選取。"
            if lang == "zh" else
            "Click a dot on the map; if your browser does not trigger it, use the buttons below."
        )
        joint_cols = st.columns(3)
        for idx, joint in enumerate(_PAIN_JOINTS):
            region = joint["region"]
            label = joint["label"] if lang == "zh" else joint["en"]
            with joint_cols[idx % 3]:
                if st.button(
                    label,
                    key=f"pain_select_{_pain_joint_key(region)}",
                    type="primary" if selected_region == region else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.pain_selected_region = region
                    selected_region = region

    with edit_col:
        with st.container(border=True):
            st.markdown("#### " + ("關節疼痛設定" if lang == "zh" else "Joint pain"))
            if selected_region:
                joint = next((j for j in _PAIN_JOINTS if j["region"] == selected_region), None)
                label = joint["region"] if lang == "zh" else joint["en"]
                current = int(pain_regions.get(selected_region, 0))
                intensity = st.slider(
                    label,
                    0,
                    10,
                    current,
                    key=f"{_pain_joint_key(selected_region)}_{st.session_state.pain_map_epoch}",
                    help="0 = 無痛，10 = 極度疼痛" if lang == "zh" else "0 = no pain, 10 = extreme pain",
                )
                if intensity > 0:
                    pain_regions[selected_region] = int(intensity)
                else:
                    pain_regions.pop(selected_region, None)

                level = _pain_level_label(int(intensity), lang)
                st.metric(
                    "疼痛指數" if lang == "zh" else "Pain score",
                    f"{intensity}/10",
                    delta=level,
                )
                if int(intensity) >= 7:
                    st.warning(
                        "疼痛偏高，今天建議降低強度；若有尖銳痛、麻木或腫脹，請停止並聯絡專業人員。"
                        if lang == "zh" else
                        "Pain is high. Reduce intensity today; stop and contact a professional for sharp pain, numbness, or swelling."
                    )
            else:
                st.info(
                    "先在人型圖上點一個關節。"
                    if lang == "zh" else
                    "Select a joint on the body map first."
                )

        areas_with_pain = {
            region: int(score)
            for region, score in pain_regions.items()
            if int(score) > 0
        }
        if areas_with_pain:
            st.markdown("#### " + ("本次標記" if lang == "zh" else "Current markers"))
            table = pd.DataFrame([
                {
                    "部位" if lang == "zh" else "Region": region,
                    "疼痛" if lang == "zh" else "Pain": score,
                    "等級" if lang == "zh" else "Level": _pain_level_label(score, lang),
                }
                for region, score in sorted(
                    areas_with_pain.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ])
            st.dataframe(table, hide_index=True, use_container_width=True)
        else:
            st.caption("尚未標記疼痛關節。" if lang == "zh" else "No painful joints marked yet.")

        note = st.text_area(
            "疼痛備註 / Notes",
            key="pain_notes",
            placeholder=(
                "例如：走樓梯時右膝較痛、肩膀抬高手臂時刺痛"
                if lang == "zh" else
                "e.g. right knee hurts on stairs, shoulder sharp pain when lifting arm"
            ),
        )

        save_col, clear_col = st.columns(2)
        with save_col:
            if st.button(
                "✓ 記錄疼痛" if lang == "zh" else "Save pain",
                key="save_pain",
                type="primary",
                use_container_width=True,
                disabled=not areas_with_pain,
            ):
                pain_mod.save_pain_record(name, areas_with_pain, note)
                st.session_state.pain_joint_scores = {}
                st.session_state.pain_map_epoch += 1
                st.session_state.pop("pain_selected_region", None)
                st.success("✓ 疼痛紀錄已保存" if lang == "zh" else "Pain record saved")
                time.sleep(0.3)
                st.rerun()
        with clear_col:
            if st.button(
                "清除本次" if lang == "zh" else "Clear",
                key="clear_pain_marks",
                use_container_width=True,
            ):
                st.session_state.pain_joint_scores = {}
                st.session_state.pain_map_epoch += 1
                st.session_state.pop("pain_selected_region", None)
                st.rerun()

    st.divider()
    st.subheader("📈 " + ("疼痛趨勢" if lang == "zh" else "Pain Trend"))
    trend = pain_mod.pain_trend(name)
    if trend:
        df = pd.DataFrame({
            "date": trend.get("dates", []),
            "pain": trend.get("intensities", []),
        })
        st.line_chart(df.set_index("date"))
        top_regions = pain_mod.most_painful_regions(name, days=7)
        if top_regions:
            st.write("**最近較需留意的部位 / Areas to watch:**")
            for region, avg in top_regions:
                st.write(f"- {region}: {avg:.1f}/10")
    else:
        st.info("尚無疼痛紀錄。" if lang == "zh" else "No pain records yet.")


_VITALS_AI_STEPS = [
    {
        "key": "blood_pressure",
        "label_zh": "血壓",
        "label_en": "Blood pressure",
        "question_zh": "請告訴我你的血壓，例如：一百二十，八十。",
        "question_en": "Tell me your blood pressure, for example: one twenty over eighty.",
    },
    {
        "key": "heart_rate",
        "label_zh": "心率",
        "label_en": "Heart rate",
        "question_zh": "請告訴我你的心率，也就是每分鐘心跳幾下。",
        "question_en": "Tell me your heart rate in beats per minute.",
        "min": 30,
        "max": 220,
    },
    {
        "key": "spo2",
        "label_zh": "血氧",
        "label_en": "Oxygen saturation",
        "question_zh": "請告訴我你的血氧百分比，例如九十八。",
        "question_en": "Tell me your oxygen saturation percentage, for example ninety eight.",
        "min": 50,
        "max": 100,
    },
    {
        "key": "weight_kg",
        "label_zh": "體重",
        "label_en": "Weight",
        "question_zh": "請告訴我你的體重，單位是公斤。",
        "question_en": "Tell me your weight in kilograms.",
        "min": 20,
        "max": 250,
    },
    {
        "key": "temperature",
        "label_zh": "體溫",
        "label_en": "Temperature",
        "question_zh": "請告訴我你的體溫，例如三十六點七。",
        "question_en": "Tell me your temperature, for example thirty six point seven.",
        "min": 30,
        "max": 45,
    },
]


def _vitals_label(vital_type: str, lang: str) -> str:
    labels = {
        "bp_sys": ("收縮壓", "Systolic"),
        "bp_dia": ("舒張壓", "Diastolic"),
        "heart_rate": ("心率", "Heart rate"),
        "spo2": ("血氧", "SpO2"),
        "weight_kg": ("體重", "Weight"),
        "temperature": ("體溫", "Temperature"),
    }
    zh, en = labels.get(vital_type, (vital_type, vital_type))
    return zh if lang == "zh" else en


def _vitals_unit(vital_type: str) -> str:
    return {
        "bp_sys": "mmHg",
        "bp_dia": "mmHg",
        "heart_rate": "bpm",
        "spo2": "%",
        "weight_kg": "kg",
        "temperature": "°C",
    }.get(vital_type, "")


def _zh_under_100(text: str) -> int | None:
    digits = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    if not text:
        return 0
    if "十" not in text:
        if len(text) == 1 and text in digits:
            return digits[text]
        return None
    left, _, right = text.partition("十")
    tens = digits.get(left, 1) if left else 1
    ones = digits.get(right, 0) if right else 0
    return tens * 10 + ones


def _zh_integer(text: str) -> int | None:
    digits = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    text = text.strip()
    if not text:
        return None
    if all(ch in digits for ch in text):
        return int("".join(str(digits[ch]) for ch in text))
    if "百" in text:
        left, _, right = text.partition("百")
        hundreds = digits.get(left, 1) if left else 1
        total = hundreds * 100
        if not right:
            return total
        if "十" in right:
            rest = _zh_under_100(right)
            return total + (rest or 0)
        if len(right) == 1 and right in digits:
            return total + digits[right] * 10
        rest = _zh_integer(right)
        return total + (rest or 0)
    return _zh_under_100(text)


def _zh_number(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    if "點" in token:
        integer_text, decimal_text = token.split("點", 1)
        integer = _zh_integer(integer_text) or 0
        digits = {
            "零": "0", "〇": "0", "一": "1", "二": "2", "兩": "2",
            "三": "3", "四": "4", "五": "5", "六": "6", "七": "7",
            "八": "8", "九": "9",
        }
        decimal = "".join(digits[ch] for ch in decimal_text if ch in digits)
        return float(f"{integer}.{decimal}") if decimal else float(integer)
    integer = _zh_integer(token)
    return float(integer) if integer is not None else None


def _extract_spoken_numbers(text: str) -> list[float]:
    text = (text or "").strip().translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    numbers = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)]
    if numbers:
        return numbers

    zh_tokens = re.findall(r"[零〇一二兩三四五六七八九十百點]+", text)
    parsed = []
    for token in zh_tokens:
        value = _zh_number(token)
        if value is not None:
            parsed.append(value)
    return parsed


def _parse_vitals_ai_answer(step_key: str, answer: str, lang: str) -> tuple[dict[str, float], str | None]:
    numbers = _extract_spoken_numbers(answer)
    if step_key == "blood_pressure":
        bp_match = re.search(r"(\d{2,3})\s*(?:/|／|比|和|,|，|\s)\s*(\d{2,3})", answer or "")
        if bp_match:
            numbers = [float(bp_match.group(1)), float(bp_match.group(2))]
        if len(numbers) < 2:
            return {}, (
                "我需要兩個數字，例如 120/80。"
                if lang == "zh" else
                "I need two numbers, for example 120 over 80."
            )
        sys_val, dia_val = numbers[0], numbers[1]
        if not (70 <= sys_val <= 230 and 40 <= dia_val <= 150):
            return {}, (
                "血壓數值看起來超出可辨識範圍，請再說一次。"
                if lang == "zh" else
                "Those blood pressure values look out of range. Please answer again."
            )
        return {"bp_sys": sys_val, "bp_dia": dia_val}, None

    if not numbers:
        return {}, (
            "我沒有聽到數字，請再說一次。"
            if lang == "zh" else
            "I did not catch a number. Please answer again."
        )
    value = numbers[0]
    step = next((s for s in _VITALS_AI_STEPS if s["key"] == step_key), {})
    min_value = step.get("min")
    max_value = step.get("max")
    if min_value is not None and max_value is not None and not (min_value <= value <= max_value):
        label = step.get("label_zh" if lang == "zh" else "label_en", step_key)
        return {}, (
            f"{label} 數值看起來超出可辨識範圍，請再說一次。"
            if lang == "zh" else
            f"{label} looks out of range. Please answer again."
        )
    return {step_key: value}, None


def _render_vitals_voice_capture(lang: str) -> str | None:
    import urllib.parse

    param = "vitals_voice_answer"
    locale = "zh-TW" if lang == "zh" else "en-US"
    button_label = "🎤 回答這題" if lang == "zh" else "🎤 Answer"
    listening = "聽中..." if lang == "zh" else "Listening..."
    unsupported = "瀏覽器不支援語音辨識，可改用文字輸入。" if lang == "zh" else "Browser speech recognition is unavailable. Use text input instead."
    component_html = f"""
    <button id="vitalsVoiceBtn" style="
      width:100%;height:44px;border:0;border-radius:14px;
      background:#0071e3;color:white;font-weight:800;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      cursor:pointer;box-shadow:0 8px 22px rgba(0,113,227,.22);">
      {button_label}
    </button>
    <div id="vitalsVoiceStatus" style="margin-top:8px;font-size:13px;color:#666"></div>
    <script>
    const btn = document.getElementById("vitalsVoiceBtn");
    const status = document.getElementById("vitalsVoiceStatus");
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {{
      status.innerText = "{unsupported}";
      btn.disabled = true;
    }} else {{
      const recognition = new SR();
      recognition.lang = "{locale}";
      recognition.continuous = false;
      recognition.interimResults = false;
      btn.onclick = () => {{
        try {{
          recognition.start();
          status.innerText = "{listening}";
        }} catch(e) {{
          status.innerText = String(e);
        }}
      }};
      recognition.onresult = (event) => {{
        const text = event.results[0][0].transcript;
        status.innerText = "✓ " + text;
        const url = new URL(window.parent.location.href);
        url.searchParams.set("{param}", encodeURIComponent(text));
        window.parent.location.href = url.toString();
      }};
      recognition.onerror = (event) => {{
        status.innerText = "✗ " + event.error;
      }};
    }}
    </script>
    """
    st.components.v1.html(component_html, height=76)

    try:
        answer = st.query_params.get(param, "")
    except Exception:
        answer = ""
    if isinstance(answer, list):
        answer = answer[0] if answer else ""
    return urllib.parse.unquote(str(answer)) if answer else None


def _clear_vitals_voice_query() -> None:
    try:
        if "vitals_voice_answer" in st.query_params:
            del st.query_params["vitals_voice_answer"]
    except Exception:
        pass


def _render_vitals_ai_assistant(vitals_mod, name: str, lang: str) -> None:
    draft = st.session_state.setdefault("vitals_ai_draft", {})
    st.session_state.setdefault("vitals_ai_step", 0)
    st.session_state.setdefault("vitals_ai_epoch", 0)
    step_idx = min(st.session_state.vitals_ai_step, len(_VITALS_AI_STEPS) - 1)
    step = _VITALS_AI_STEPS[step_idx]
    question = step["question_zh"] if lang == "zh" else step["question_en"]

    with st.expander("🤖 AI 問答記錄" if lang == "zh" else "🤖 AI guided vitals", expanded=False):
        st.markdown("**AI**")
        st.info(question)
        col_voice, col_audio = st.columns(2)
        with col_voice:
            voice_answer = _render_vitals_voice_capture(lang)
        with col_audio:
            if st.button(
                "🔊 AI 唸出問題" if lang == "zh" else "🔊 Speak question",
                key=f"vitals_ai_speak_{step_idx}_{st.session_state.vitals_ai_epoch}",
                use_container_width=True,
            ):
                try:
                    import tts as tts_mod
                    audio = tts_mod.synthesize_audio_bytes(question, lang=lang)
                    if audio:
                        data, fmt = audio
                        st.audio(data, format=fmt, autoplay=True)
                    else:
                        ui.browser_speech_button(
                            question,
                            "用瀏覽器朗讀" if lang == "zh" else "Browser speech",
                            lang=lang,
                        )
                except Exception:
                    ui.browser_speech_button(
                        question,
                        "用瀏覽器朗讀" if lang == "zh" else "Browser speech",
                        lang=lang,
                    )

        answer_key = f"vitals_ai_answer_{step_idx}_{st.session_state.vitals_ai_epoch}"
        if voice_answer and voice_answer != st.session_state.get("_last_vitals_voice_answer"):
            st.session_state["_last_vitals_voice_answer"] = voice_answer
            st.session_state[answer_key] = voice_answer

        answer = st.text_input(
            "你的回答" if lang == "zh" else "Your answer",
            key=answer_key,
            placeholder=(
                "例如：120/80、72、98、65.5、36.7"
                if lang == "zh" else
                "e.g. 120/80, 72, 98, 65.5, 36.7"
            ),
        )

        submit = st.button(
            "送出回答" if lang == "zh" else "Submit answer",
            key=f"vitals_ai_submit_{step_idx}_{st.session_state.vitals_ai_epoch}",
            type="primary",
            use_container_width=True,
        )
        if submit or (voice_answer and answer == voice_answer):
            updates, error = _parse_vitals_ai_answer(step["key"], answer, lang)
            if error:
                st.warning(error)
                _clear_vitals_voice_query()
            else:
                draft.update({k: round(float(v), 1) for k, v in updates.items()})
                _clear_vitals_voice_query()
                st.session_state.vitals_ai_step = min(step_idx + 1, len(_VITALS_AI_STEPS) - 1)
                st.session_state.vitals_ai_epoch += 1
                if step_idx >= len(_VITALS_AI_STEPS) - 1:
                    st.success("已完成問答，請確認後記錄。" if lang == "zh" else "Done. Review and save.")
                st.rerun()

        if draft:
            rows = [
                {
                    "項目" if lang == "zh" else "Metric": _vitals_label(k, lang),
                    "數值" if lang == "zh" else "Value": f"{v:g} {_vitals_unit(k)}",
                }
                for k, v in draft.items()
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        nav_cols = st.columns(3)
        with nav_cols[0]:
            if st.button(
                "上一題" if lang == "zh" else "Back",
                key="vitals_ai_back",
                disabled=step_idx <= 0,
                use_container_width=True,
            ):
                st.session_state.vitals_ai_step = max(0, step_idx - 1)
                st.session_state.vitals_ai_epoch += 1
                _clear_vitals_voice_query()
                st.rerun()
        with nav_cols[1]:
            if st.button(
                "跳過" if lang == "zh" else "Skip",
                key="vitals_ai_skip",
                use_container_width=True,
            ):
                st.session_state.vitals_ai_step = min(step_idx + 1, len(_VITALS_AI_STEPS) - 1)
                st.session_state.vitals_ai_epoch += 1
                _clear_vitals_voice_query()
                st.rerun()
        with nav_cols[2]:
            if st.button(
                "重來" if lang == "zh" else "Reset",
                key="vitals_ai_reset",
                use_container_width=True,
            ):
                st.session_state.vitals_ai_draft = {}
                st.session_state.vitals_ai_step = 0
                st.session_state.vitals_ai_epoch += 1
                _clear_vitals_voice_query()
                st.rerun()

        save_cols = st.columns(2)
        with save_cols[0]:
            if st.button(
                "確認並記錄" if lang == "zh" else "Save draft",
                key="vitals_ai_save",
                type="primary",
                disabled=not draft,
                use_container_width=True,
            ):
                for vital_type, value in draft.items():
                    vitals_mod.save_vital(name, vital_type, float(value))
                st.session_state.vitals_ai_draft = {}
                st.session_state.vitals_ai_step = 0
                st.session_state.vitals_ai_epoch += 1
                _clear_vitals_voice_query()
                st.success("✓ 生命跡象已記錄" if lang == "zh" else "Vitals recorded")
                time.sleep(0.3)
                st.rerun()
        with save_cols[1]:
            if st.button(
                "套用到手動欄位" if lang == "zh" else "Apply to manual form",
                key="vitals_ai_apply_manual",
                disabled=not draft,
                use_container_width=True,
            ):
                key_map = {
                    "bp_sys": "bp_sys",
                    "bp_dia": "bp_dia",
                    "heart_rate": "heart_rate",
                    "spo2": "spo2",
                    "weight_kg": "weight",
                    "temperature": "temperature",
                }
                for vital_type, widget_key in key_map.items():
                    if vital_type in draft:
                        if vital_type in {"bp_sys", "bp_dia", "heart_rate", "spo2"}:
                            st.session_state[widget_key] = int(round(draft[vital_type]))
                        else:
                            st.session_state[widget_key] = float(draft[vital_type])
                st.toast("已套用到手動欄位" if lang == "zh" else "Applied to manual form")


def view_vitals() -> None:
    """生命跡象追蹤 (血壓、心率、血氧、體重、體溫)。"""
    import vitals as vitals_mod
    lang = get_lang()

    st.title("🌡️ " + t("step_vitals", lang))

    name = _require_user_name(lang)
    if not name:
        return

    st.subheader("記錄生命跡象" if lang == "zh" else "Record Vitals")

    _render_vitals_ai_assistant(vitals_mod, name, lang)

    col1, col2 = st.columns(2)

    with col1:
        st.write("**血壓 / Blood Pressure (mmHg)**")
        bp_sys = st.number_input("收縮壓 (Systolic)", 90, 180, 120, key="bp_sys")
        bp_dia = st.number_input("舒張壓 (Diastolic)", 60, 120, 80, key="bp_dia")

        st.write("**心率 / Heart Rate (bpm)**")
        heart_rate = st.number_input("心率", 40, 150, 70, key="heart_rate")

        st.write("**血氧 / O2 Saturation (%)**")
        spo2 = st.number_input("SpO2", 80, 100, 98, key="spo2")

    with col2:
        st.write("**體重 / Weight (kg)**")
        weight = st.number_input("體重", 30.0, 150.0, 70.0, 0.5, key="weight")

        st.write("**體溫 / Temperature (°C)**")
        temp = st.number_input("體溫", 35.0, 42.0, 37.0, 0.1, key="temperature")

    # Show normal ranges
    st.info(
        "**正常範圍 / Normal Ranges:**\n"
        "- 血壓: 120/80 mmHg\n"
        "- 心率: 60-100 bpm\n"
        "- 血氧: ≥95%\n"
        "- 體溫: 36.1-37.2°C"
    )

    if st.button("✓ 記錄", key="save_vitals"):
        values = {
            "bp_sys": bp_sys,
            "bp_dia": bp_dia,
            "heart_rate": heart_rate,
            "spo2": spo2,
            "weight_kg": weight,
            "temperature": temp,
        }
        for vital_type, value in values.items():
            vitals_mod.save_vital(name, vital_type, float(value))
        st.success("✓ 生命跡象已記錄" if lang == "zh" else "Vitals recorded")
        time.sleep(0.3)
        st.rerun()

    st.divider()
    st.subheader("📊 " + ("最近紀錄" if lang == "zh" else "Recent Vitals"))
    latest = vitals_mod.latest_vitals(name)
    if latest:
        labels = {
            "bp_sys": "收縮壓",
            "bp_dia": "舒張壓",
            "heart_rate": "心率",
            "spo2": "血氧",
            "weight_kg": "體重",
            "temperature": "體溫",
        }
        cols = st.columns(3)
        for idx, (key, value) in enumerate(latest.items()):
            abnormal = vitals_mod.is_abnormal(key, float(value))
            cols[idx % 3].metric(
                labels.get(key, key),
                f"{value:g}",
                "需留意" if abnormal and lang == "zh" else ("Check" if abnormal else None),
            )
    else:
        st.info("尚無生命跡象紀錄。" if lang == "zh" else "No vitals yet.")


def view_medication() -> None:
    """藥物追蹤與管理。"""
    import medication as med_mod
    from photo_ai import analyze_medication_photo, ai_available, configured_model_name
    lang = get_lang()

    st.title("💊 " + t("step_medication", lang))

    name = _require_user_name(lang)
    if not name:
        return

    tab1, tab2 = st.tabs(["今日服藥" if lang == "zh" else "Today", "管理藥物" if lang == "zh" else "Manage"])

    with tab1:
        st.subheader("今日服藥打卡" if lang == "zh" else "Today's Medications")
        today_meds = med_mod.upcoming_medications(name)
        if not today_meds:
            st.info("尚未新增藥物。" if lang == "zh" else "No medications yet.")

        for med in today_meds:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(
                    f"**{med.get('name', '—')}** - "
                    f"{med.get('dose', '')} @ {med.get('scheduled_time', '')}"
                )
                if med.get("notes"):
                    st.caption(med.get("notes"))
            with col2:
                if st.button(
                    "✓" if med.get("taken") else "⭕",
                    key=f"take_{med.get('id')}_{med.get('scheduled_time')}",
                    disabled=bool(med.get("taken")),
                ):
                    med_mod.log_taken(
                        name,
                        med.get("id"),
                        med.get("scheduled_time"),
                    )
                    st.success("✓ 已服用" if lang == "zh" else "Taken")
                    time.sleep(0.3)
                    st.rerun()
            with col3:
                if med.get("taken"):
                    st.caption("已完成" if lang == "zh" else "Done")

        adherence = med_mod.medication_adherence(name)
        if adherence:
            st.divider()
            st.subheader("📊 " + ("服藥依順性" if lang == "zh" else "Adherence"))
            for info in adherence.values():
                st.progress(
                    int(info.get("adherence", 0)) / 100,
                    text=(
                        f"{info.get('name', '—')}: "
                        f"{info.get('adherence', 0):.0f}% "
                        f"({info.get('taken', 0)}/{info.get('expected', 0)})"
                    ),
                )

    with tab2:
        meds = med_mod.list_medications(name)
        if meds:
            st.subheader("目前藥物" if lang == "zh" else "Current Medications")
            for med in meds:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"**{med.get('name', '—')}**")
                        st.caption(
                            f"{med.get('dose', '')} · "
                            f"{', '.join(med.get('times', []))} · "
                            f"{med.get('frequency', '')}"
                        )
                    with col2:
                        if st.button("🗑", key=f"remove_med_{med.get('id')}"):
                            med_mod.remove_medication(name, med.get("id"))
                            st.rerun()

        st.subheader("新增藥物" if lang == "zh" else "Add Medication")

        med_freq_options = [
            "每日一次" if lang == "zh" else "Once daily",
            "每日兩次" if lang == "zh" else "Twice daily",
            "按需" if lang == "zh" else "As needed",
        ]

        with st.expander(
            "📷 拍照辨識藥物" if lang == "zh" else "📷 Scan medication",
            expanded=False,
        ):
            if ai_available():
                st.success(
                    "AI 視覺辨識已啟用" if lang == "zh"
                    else "AI vision is enabled"
                )
                st.caption(
                    f"Model: {configured_model_name()}"
                )
            else:
                st.info(
                    "未設定 ANTHROPIC_API_KEY，仍可拍照後手動輸入。"
                    if lang == "zh"
                    else "ANTHROPIC_API_KEY is not set; you can still take a photo and enter details manually."
                )

            med_photo = st.camera_input(
                "拍藥袋、藥盒或藥瓶標籤" if lang == "zh"
                else "Take a medication label photo",
                key="med_photo_camera",
            )
            med_upload = st.file_uploader(
                "或上傳藥物照片" if lang == "zh"
                else "Or upload a medication photo",
                type=["jpg", "jpeg", "png", "webp"],
                key="med_photo_upload",
            )
            med_image = med_photo or med_upload
            if med_image and st.button(
                "AI 辨識並建立草稿" if lang == "zh" else "Analyze with AI",
                key="med_photo_analyze",
                type="primary",
            ):
                result = analyze_medication_photo(
                    med_image.getvalue(),
                    media_type=getattr(med_image, "type", "image/jpeg"),
                    lang=lang,
                )
                st.session_state.med_photo_draft = result.__dict__

            draft = st.session_state.get("med_photo_draft")
            if draft:
                st.write("**AI 建議草稿**" if lang == "zh" else "**AI draft**")
                st.json({
                    k: draft.get(k)
                    for k in ("name", "dose", "frequency", "times", "notes",
                              "confidence", "warnings")
                })
                for warning in draft.get("warnings") or []:
                    st.warning(warning)
                if st.button(
                    "套用到新增表單" if lang == "zh" else "Apply to form",
                    key="apply_med_photo_draft",
                ):
                    st.session_state.med_name_input = draft.get("name", "")
                    st.session_state.med_dose_input = draft.get("dose", "")
                    st.session_state.med_notes_input = draft.get("notes", "")
                    draft_frequency = str(draft.get("frequency") or "").strip()
                    if draft_frequency in med_freq_options:
                        st.session_state.med_freq_input = draft_frequency
                    else:
                        frequency_text = draft_frequency.lower()
                        if any(token in frequency_text for token in ("bid", "twice", "兩", "2")):
                            st.session_state.med_freq_input = med_freq_options[1]
                        elif any(token in frequency_text for token in ("prn", "need", "按需")):
                            st.session_state.med_freq_input = med_freq_options[2]
                        elif draft_frequency:
                            st.session_state.med_freq_input = med_freq_options[0]

                    draft_times = draft.get("times") or []
                    if draft_times:
                        try:
                            st.session_state.med_time_input = datetime.strptime(
                                str(draft_times[0])[:5],
                                "%H:%M",
                            ).time()
                        except ValueError:
                            pass
                    st.toast(
                        "已套用，請確認後新增" if lang == "zh"
                        else "Applied. Please review before adding.",
                        icon="💊",
                    )

        med_name = st.text_input(
            "藥物名稱" if lang == "zh" else "Medication Name",
            key="med_name_input",
        )
        med_dose = st.text_input(
            "劑量" if lang == "zh" else "Dose",
            key="med_dose_input",
        )
        med_time = st.time_input(
            "服用時間" if lang == "zh" else "Time",
            key="med_time_input",
        )
        med_freq = st.selectbox(
            "頻率" if lang == "zh" else "Frequency",
            med_freq_options,
            key="med_freq_input",
        )
        med_notes = st.text_area(
            "備註" if lang == "zh" else "Notes",
            key="med_notes_input",
            height=80,
        )
        st.caption(
            "請務必核對藥名、劑量與服用時間；AI 辨識不能取代醫師或藥師指示。"
            if lang == "zh" else
            "Always verify name, dose, and timing. AI parsing does not replace clinician or pharmacist instructions."
        )

        if st.button("➕ 新增", key="add_med"):
            if not med_name.strip():
                st.warning("請輸入藥物名稱" if lang == "zh" else "Enter a medication name")
                return
            med_mod.add_medication(name, {
                "name": med_name.strip(),
                "dose": med_dose.strip(),
                "frequency": med_freq,
                "times": [med_time.strftime("%H:%M")],
                "notes": med_notes.strip(),
            })
            st.session_state.pop("med_photo_draft", None)
            st.success("✓ 藥物已新增" if lang == "zh" else "Medication added")
            time.sleep(0.3)
            st.rerun()


def view_calendar() -> None:
    """預約行事曆。"""
    import calendar_tracker as cal_mod
    lang = get_lang()

    st.title("📅 " + t("step_calendar", lang))

    name = _require_user_name(lang)
    if not name:
        return

    tab1, tab2 = st.tabs(["預約列表" if lang == "zh" else "Appointments", "新增預約" if lang == "zh" else "New"])

    with tab1:
        st.subheader("upcoming Appointments" if lang != "zh" else "即將到來的預約")
        appts = cal_mod.list_appointments(name, upcoming_only=True)
        if not appts:
            st.info("尚無即將到來的預約。" if lang == "zh" else "No upcoming appointments.")

        reminders = cal_mod.appointment_reminders(name, days_before=1)
        if reminders:
            st.warning(
                "24 小時內有預約，請留意時間。"
                if lang == "zh" else
                "You have appointments within 24 hours."
            )

        for appt in appts:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"📅 {appt.get('date')} @ {appt.get('time')}")
                    st.write(f"**{appt.get('type', '—')}** - {appt.get('doctor', '')}")
                    st.write(f"📍 {appt.get('location', '')}")
                    if appt.get("notes"):
                        st.caption(appt.get("notes"))
                with col2:
                    if st.button("❌", key=f"del_{appt.get('id')}"):
                        cal_mod.remove_appointment(name, appt.get("id"))
                        st.success("已刪除" if lang == "zh" else "Deleted")
                        time.sleep(0.3)
                        st.rerun()

    with tab2:
        st.subheader("新增預約" if lang == "zh" else "New Appointment")

        appt_date = st.date_input("日期" if lang == "zh" else "Date")
        appt_time = st.time_input("時間" if lang == "zh" else "Time")
        appt_type = st.selectbox(
            "類型" if lang == "zh" else "Type",
            ["物理治療", "回診", "X光/檢查", "藥物領取", "其他"],
        )
        appt_doctor = st.text_input("醫師名字" if lang == "zh" else "Doctor")
        appt_location = st.text_input("地點" if lang == "zh" else "Location")
        appt_notes = st.text_area("備注" if lang == "zh" else "Notes", height=80)

        if st.button("✓ 保存", key="save_appt"):
            cal_mod.add_appointment(name, {
                "date": appt_date.isoformat(),
                "time": appt_time.strftime("%H:%M"),
                "type": appt_type,
                "doctor": appt_doctor.strip(),
                "location": appt_location.strip(),
                "notes": appt_notes.strip(),
            })
            st.success("✓ 預約已保存" if lang == "zh" else "Appointment saved")
            time.sleep(0.3)
            st.rerun()


def view_onboarding() -> None:
    """引導頁面（首次使用）。"""
    lang = get_lang()

    if "onboard_step" not in st.session_state:
        st.session_state.onboard_step = 0

    step = st.session_state.onboard_step

    if step == 0:
        # Welcome screen
        st.markdown(
            '<div style="text-align: center; padding: 4rem 1rem;">'
            '<div style="font-size: 5rem; margin-bottom: 1rem;">🏥</div>'
            '<h1 style="font-size: 2.5rem; margin-bottom: 1rem;">智慧居家復健評估</h1>'
            '<p style="font-size: 1.2rem; color: #666;">AI 驅動的個人化運動指導與進度追蹤</p>'
            '</div>',
            unsafe_allow_html=True,
        )

    elif step == 1:
        # Features
        st.markdown('<h2 style="text-align: center;">✨ 主要功能</h2>', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        features = [
            ("🎥", "AI 動作評分", "實時姿態分析與打分"),
            ("🗣️", "語音指導", "專業教練實時語音提示"),
            ("📈", "進度追蹤", "7日進度曲線與個人最佳紀錄"),
        ]

        for i, (icon, title, desc) in enumerate(features):
            with [col1, col2, col3][i]:
                st.markdown(
                    f'<div style="text-align: center; padding: 1rem;">'
                    f'<div style="font-size: 3rem; margin-bottom: 0.5rem;">{icon}</div>'
                    f'<h4>{title}</h4>'
                    f'<p style="color: #666;">{desc}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    elif step == 2:
        # Privacy
        st.markdown(
            '<h2 style="text-align: center;">🔒 隱私與安全</h2>',
            unsafe_allow_html=True,
        )
        st.info(
            "✓ 訓練資料儲存在本機資料夾或您指定的伺服器環境\n"
            "✓ 不需要把影片上傳到第三方雲端即可完成分析\n"
            "✓ 您可以自行備份或刪除 user_data 內的資料\n"
            "✓ 本系統僅供復健輔助參考，不能取代醫療診斷"
        )

    elif step == 3:
        # Setup
        st.markdown(
            '<h2 style="text-align: center;">👤 開始設定</h2>',
            unsafe_allow_html=True,
        )

        name_input = st.text_input("您的姓名 / Your Name")

        if st.button("✓ 開始使用", key="onboard_start"):
            if name_input:
                profile = {
                    "name": name_input.strip(),
                    "age": 65,
                    "gender": "—",
                    "condition": [],
                    "daily_goal": 1,
                    "weekly_goal": 3,
                }
                storage_key = _current_user_name()
                hist.save_profile(profile, storage_key=storage_key)
                _save_profile_to_db(profile)
                current = st.session_state.get("user") or {}
                st.session_state.user = {
                    **current,
                    **profile,
                    "history_key": storage_key,
                }
                st.session_state.onboarding_done = True
                st.success("✓ 設定完成！" if lang == "zh" else "Setup complete!")
                time.sleep(0.5)
                goto("home")
            else:
                st.error("請輸入姓名" if lang == "zh" else "Please enter your name")

    # Navigation
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if step > 0:
            if st.button("◀ 上一步" if lang == "zh" else "Back"):
                st.session_state.onboard_step -= 1
                st.rerun()

    with col2:
        # Progress dots
        dots = "".join(
            f'<span style="font-size: 1.5rem; margin: 0 0.5rem; '
            f'color: {"#007aff" if i == step else "#ddd"};">●</span>'
            for i in range(4)
        )
        st.markdown(f'<div style="text-align: center;">{dots}</div>', unsafe_allow_html=True)

    with col3:
        if step < 3:
            if st.button("下一步 ▶" if lang == "zh" else "Next"):
                st.session_state.onboard_step += 1
                st.rerun()
        else:
            st.write("")  # Placeholder


def view_reminders() -> None:
    """智能提醒系統頁面。"""
    lang = get_lang()

    st.title("🔔 " + ("智能提醒" if lang == "zh" else "Smart Reminders"))

    user = st.session_state.get("user")
    if not user:
        st.warning(t("not_logged_in", lang))
        return

    if not reminders:
        st.error("Reminders module not available")
        return

    name = user_history_key(user)

    # Get all pending reminders
    pending = reminders.get_pending_reminders(name)
    stats = reminders.get_reminder_stats(name)

    # Show summary
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總提醒數" if lang == "zh" else "Total", stats.get("total", 0))
    with col2:
        st.metric("高優先" if lang == "zh" else "High Priority", stats.get("high_priority", 0))
    with col3:
        medication_count = stats["by_type"].get("medication", 0)
        st.metric("💊 藥物" if lang == "zh" else "💊 Medication", medication_count)
    with col4:
        training_count = stats["by_type"].get("training", 0)
        st.metric("🎯 訓練" if lang == "zh" else "🎯 Training", training_count)

    st.divider()

    if not pending:
        st.success("✓ 無待處理提醒！" if lang == "zh" else "✓ All caught up!")
    else:
        st.subheader("📋 待處理事項" if lang == "zh" else "📋 Pending")

        for reminder in pending:
            priority_badge = "🔴" if reminder.get("priority", 0) >= 3 else "🟡" if reminder.get("priority", 0) >= 2 else "🟢"

            with st.container(border=True):
                col1, col2 = st.columns([5, 1])

                with col1:
                    st.write(
                        f"{priority_badge} **{reminder.get('icon', '•')} "
                        f"{reminder.get('title', '—')}**"
                    )
                    st.caption(reminder.get("description", ""))

                with col2:
                    action = reminder.get("action")
                    if action:
                        if st.button(
                            "→",
                            key=f"rem_{reminder.get('type')}_{int(time.time())}",
                            help="Go to this section" if lang != "zh" else "前往此區域",
                        ):
                            goto(action)

                    if st.button(
                        "✓",
                        key=f"dis_{reminder.get('type')}_{int(time.time())}",
                        help="Dismiss" if lang != "zh" else "忽略",
                    ):
                        reminders.dismiss_reminder(name, reminder.get("type"))
                        st.rerun()

    st.divider()
    st.caption("💡 " + ("提醒根據你的訓練進度、藥物、預約和健康數據自動生成" if lang == "zh" else "Reminders are automatically generated based on your progress, medications, appointments, and health data"))


def view_sync() -> None:
    """多設備同步頁面。"""
    lang = get_lang()

    st.title("🔄 " + ("多設備同步" if lang == "zh" else "Multi-Device Sync"))

    user = st.session_state.get("user")
    if not user:
        st.warning(t("not_logged_in", lang))
        return

    if not sync_manager:
        st.error("Sync manager not available")
        return

    name = user_history_key(user)

    # Device info
    st.subheader("📱 " + ("此設備資訊" if lang == "zh" else "This Device"))
    device_id = sync_manager.get_device_id()
    device_name = sync_manager.get_device_name()

    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"**{device_name}**")
        st.caption(f"ID: {device_id}")
    with col2:
        new_name = st.text_input(
            "重新命名" if lang == "zh" else "Rename",
            device_name,
            key="new_device_name",
            label_visibility="collapsed",
        )
        if new_name != device_name:
            if st.button("✓", key="rename_device"):
                sync_manager.set_device_name(new_name)
                st.success("已更新" if lang == "zh" else "Updated")
                st.rerun()

    st.divider()

    # Sync status
    st.subheader("📊 " + ("同步狀態" if lang == "zh" else "Sync Status"))
    status = sync_manager.get_sync_status(name)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "備份數量" if lang == "zh" else "Backups",
            status.get("backup_count", 0),
        )
    with col2:
        last_sync = status.get("last_sync", "未同步" if lang == "zh" else "Never")
        st.metric("最後同步" if lang == "zh" else "Last Sync", last_sync[:10] if last_sync else "—")
    with col3:
        st.metric(
            "同步次數" if lang == "zh" else "Sync Count",
            status.get("sync_count", 0),
        )

    st.divider()

    # Backup actions
    st.subheader("💾 " + ("備份管理" if lang == "zh" else "Backup Management"))

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔄 立即備份" if lang == "zh" else "🔄 Backup Now", use_container_width=True):
            backup_info = sync_manager.create_local_backup(name)
            st.success(
                f"✓ 備份完成\n{backup_info.get('timestamp')}"
                if lang == "zh"
                else f"✓ Backup created\n{backup_info.get('timestamp')}"
            )
            st.rerun()

    with col2:
        if st.button("📂 列出備份" if lang == "zh" else "📂 List Backups", use_container_width=True):
            st.session_state.show_backups = True

    if st.session_state.get("show_backups"):
        st.subheader("📋 備份列表" if lang == "zh" else "📋 Backup List")
        backups = sync_manager.list_backups(name)

        if backups:
            for backup in backups:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"**{backup.get('timestamp', '—')[:10]}** @ {backup.get('device_name', '—')}")
                        st.caption(f"Size: {backup.get('size', 0) / 1024:.1f}KB")
                    with col2:
                        if st.button("復原" if lang == "zh" else "Restore", key=f"restore_{backup.get('timestamp')}"):
                            if sync_manager.restore_from_backup(name, Path(backup.get("file"))):
                                st.success("✓ 復原完成" if lang == "zh" else "✓ Restored")
                                st.rerun()
                            else:
                                st.error("復原失敗" if lang == "zh" else "Restore failed")
        else:
            st.info("無備份" if lang == "zh" else "No backups")

    st.divider()

    # Cloud sync
    st.subheader("☁️ " + ("雲同步設定" if lang == "zh" else "Cloud Sync Setup"))

    st.info(
        "💡 支持 Firebase 和 Supabase 等雲端服務進行多設備同步。"
        if lang == "zh"
        else "💡 Support Firebase and Supabase for multi-device cloud sync."
    )

    cloud_provider = st.selectbox(
        "雲端提供商" if lang == "zh" else "Cloud Provider",
        ["Disabled", "Firebase", "Supabase", "Custom"],
        key="cloud_provider_select",
    )

    if cloud_provider != "Disabled":
        st.write(f"**設定 {cloud_provider}**")
        st.caption("(功能即將推出 / Coming soon)")


def view_ai_demos() -> None:
    """Legacy route kept for old sessions; it now opens the AI coach."""
    view_ai_media()


# ============================================================
# 路由表（給 app.py 使用）
# ============================================================
ROUTES = {
    "welcome":   view_welcome,
    "onboarding": view_onboarding,
    "profile":   view_profile,
    "home":      view_home,
    "record":    view_record,
    "analyze":   view_analyze,
    "result":    view_result,
    "progress":  view_progress,
    "custom":    view_custom,
    "clinician": view_clinician,
    "ai_media":  view_ai_media,
    "settings":  view_settings,
    "programs":  view_programs,
    "journal":   view_journal,
    "pain_map":  view_pain_map,
    "vitals":    view_vitals,
    "medication": view_medication,
    "calendar":  view_calendar,
    "reminders": view_reminders,
    "sync":      view_sync,
    "ai_demos":  view_ai_demos,
    "therapist_dashboard": view_therapist_dashboard,
    "analytics": view_analytics,
    "games": view_games,
    "wearables": view_wearables,
    "cloud_sync": view_cloud_sync,
    "ai_chat": view_ai_chat,
    "quests": view_quests,
    "nutrition": view_nutrition,
    "sleep": view_sleep,
    "notifications": view_notifications,
    "audit_log": view_audit_log,
    "live_enhanced": view_realtime_enhanced,
    "auto_exercise": view_auto_exercise,
    "daily_routine": view_daily_routine,
}
