"""
全域狀態、設定、難度等級、快取資源、語音與徽章 toast。

被 `views.py`、`pipeline.py`、`app.py` 共用，自身不產生 UI（除了 toast）。
"""
from __future__ import annotations

import time

import streamlit as st

import history as hist


# ============================================================
# 難度等級預設
# ============================================================
DIFFICULTY_PRESETS: dict[str, dict] = {
    "easy":   {"threshold": 22.0, "ema_alpha": 0.4,
               "label_zh": "輕鬆", "label_en": "Easy",
               "icon": "🟢"},
    "normal": {"threshold": 15.0, "ema_alpha": 0.6,
               "label_zh": "標準", "label_en": "Normal",
               "icon": "🟡"},
    "hard":   {"threshold": 9.0,  "ema_alpha": 0.75,
               "label_zh": "嚴格", "label_en": "Hard",
               "icon": "🔴"},
}


# ============================================================
# 設定
# ============================================================
def _default_settings() -> dict:
    return {
        "lang": "zh",
        "difficulty": "normal",
        "threshold": 15.0,
        "senior_mode": True,
        "enable_voice": True,
        "live_voice": True,
        "voice_cooldown": 4.5,
        "ema_alpha": 0.6,
        "neural_weight": 0.4,
        "daily_goal": 1,
        "reminder_enabled": True,
        "preferred_training_time": "09:00",
        "coach": "starbuddy",
    }


def apply_difficulty(level: str) -> None:
    p = DIFFICULTY_PRESETS.get(level)
    if not p:
        return
    s = st.session_state.settings
    s["difficulty"] = level
    s["threshold"] = p["threshold"]
    s["ema_alpha"] = p["ema_alpha"]


# ============================================================
# 每日挑戰：以日期 + 使用者名稱 hash 出當日穩定挑戰
# ============================================================
def daily_challenge_key(name: str, templates_all: dict) -> str | None:
    if not templates_all:
        return None
    seed = f"{name}-{time.strftime('%Y-%m-%d')}"
    keys = sorted(templates_all.keys())
    return keys[sum(ord(c) for c in seed) % len(keys)]


# ============================================================
# Session state
# ============================================================
def init_state() -> None:
    defaults = {
        "step": "welcome",
        "user": {},
        "exercise_key": None,
        "video_path": None,
        "analysis": None,
        "settings": _default_settings(),
        "tts_engine": None,
        "pain_before": 0,
        "pain_safety_confirmed": False,
        "prev_badges": set(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if isinstance(st.session_state.get("user"), str):
        st.session_state.user = {
            "name": st.session_state.user.strip(),
            "age": 65,
            "gender": "—",
            "condition": [],
        }
    # 舊 session 可能缺少新設定；補上預設值但保留使用者已改過的選項。
    for k, v in _default_settings().items():
        st.session_state.settings.setdefault(k, v)
    if float(st.session_state.settings.get("voice_cooldown", 4.5)) < 4.0:
        st.session_state.settings["voice_cooldown"] = 4.5


def lang() -> str:
    return st.session_state.settings.get("lang", "zh")


def user_history_key(user: dict | None = None) -> str:
    """Stable per-account key for local history files."""
    if user is None:
        user = st.session_state.get("user") or {}
    if isinstance(user, dict):
        raw = (
            user.get("history_key")
            or user.get("user_id")
            or user.get("username")
            or user.get("name")
            or "anon"
        )
    else:
        raw = str(user or "anon")
    return str(raw).strip() or "anon"


def goto(step: str) -> None:
    st.session_state.step = step
    st.rerun()


# ============================================================
# 快取重型資源（Torch / MediaPipe lifter / 神經評分器）
# ============================================================
@st.cache_resource
def load_lifter():
    try:
        from motionagformer import MotionAGFormer
    except Exception:
        return None
    return MotionAGFormer()


@st.cache_resource
def load_scorers() -> dict:
    try:
        from neural_scorer import NeuralScorer
    except Exception:
        return {}
    out: dict = {}
    for arch in ("lstm", "stgcn"):
        try:
            out[arch] = NeuralScorer(arch=arch)
        except Exception:
            pass
    return out


# ============================================================
# 語音
# ============================================================
def get_voice():
    if not st.session_state.settings.get("enable_voice"):
        return None
    try:
        from tts import VoiceGuide
    except Exception:
        return None
    if st.session_state.tts_engine is None:
        try:
            st.session_state.tts_engine = VoiceGuide(lang=lang())
        except Exception:
            st.session_state.tts_engine = False
    vg = st.session_state.tts_engine
    if vg and getattr(vg, "available", False):
        vg.set_language(lang())
        return vg
    return None


# ============================================================
# 徽章 toast
# ============================================================
def emit_new_badge_toasts(name: str) -> None:
    earned, _ = hist.compute_badges(name)
    new = earned - st.session_state.prev_badges
    for key in new:
        title = hist.BADGES.get(key, (key, ""))[0]
        st.toast(f"🎉 解鎖徽章：{title}", icon="🏅")
    st.session_state.prev_badges = earned
