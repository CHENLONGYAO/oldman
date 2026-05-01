"""
Proactive smart assistant: detects situations + offers in-context AI help.

Triggers a contextual help banner (or modal) when:
- User just completed a session → offer instant feedback
- User logged high pain (>7) → suggest gentle alternatives
- User abandoned mid-flow → offer to resume
- User keeps failing same exercise → suggest easier variant
- User looks at progress → summarize trend

Each "moment" is a small AgentTrigger that's checked on each render.
Assistant uses cached system prompts + tool calls when LLM available.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import streamlit as st


@dataclass
class AssistantMoment:
    """One contextual help moment."""
    id: str
    icon: str
    title_zh: str
    title_en: str
    body_zh: str
    body_en: str
    cta_zh: str = ""
    cta_en: str = ""
    cta_route: str = ""
    priority: int = 50


# ============================================================
# Moment detectors
# ============================================================
def _detect_just_finished_session(user_id: str) -> Optional[AssistantMoment]:
    """User just completed a session in the last 5 minutes."""
    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT exercise, score, created_at FROM sessions
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id,),
        )
        if not rows:
            return None

        row = rows[0]
        try:
            ts = datetime.fromisoformat(
                str(row["created_at"]).replace("Z", "")
            )
        except Exception:
            return None

        if datetime.now() - ts > timedelta(minutes=5):
            return None

        score = row["score"] or 0
        ex = row["exercise"]

        if score >= 90:
            return AssistantMoment(
                id="just_great",
                icon="🎉",
                title_zh="表現超棒！",
                title_en="Great work!",
                body_zh=f"剛剛 {ex} 拿了 {score:.0f} 分，要不要看看詳細分析？",
                body_en=f"You scored {score:.0f} on {ex}. See breakdown?",
                cta_zh="查看分析", cta_en="See analysis",
                cta_route="result", priority=70,
            )
        elif score < 60:
            return AssistantMoment(
                id="just_struggled",
                icon="💡",
                title_zh="可以更好",
                title_en="Room to grow",
                body_zh=f"{ex} 有點挑戰？我可以幫你分析問題在哪。",
                body_en=f"{ex} was tough? I can help you find what to fix.",
                cta_zh="問 AI", cta_en="Ask AI",
                cta_route="ai_chat", priority=80,
            )
        return AssistantMoment(
            id="just_done",
            icon="✓",
            title_zh="訓練完成",
            title_en="Session complete",
            body_zh=f"{score:.0f} 分。要不要記錄今天的疼痛？",
            body_en=f"Scored {score:.0f}. Log your pain level?",
            cta_zh="記錄", cta_en="Log",
            cta_route="pain_map", priority=60,
        )
    except Exception:
        return None


def _detect_high_pain(user_id: str) -> Optional[AssistantMoment]:
    """Recent pain ≥7 in last 24h."""
    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT data_json, created_at FROM health_data
            WHERE user_id = ?
              AND data_type IN ('pain_records', 'pain_map')
              AND created_at >= datetime('now', '-1 day')
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id,),
        )
        if not rows:
            return None
        import json
        try:
            data = json.loads(rows[0]["data_json"])
        except Exception:
            return None

        max_intensity = 0
        if isinstance(data, dict):
            intensities = data.get("intensities") or data.get("regions", {})
            if isinstance(intensities, dict):
                max_intensity = max(
                    (v for v in intensities.values()
                     if isinstance(v, (int, float))),
                    default=0,
                )

        if max_intensity >= 7:
            return AssistantMoment(
                id="high_pain",
                icon="🩹",
                title_zh="疼痛偏高",
                title_en="High pain",
                body_zh=f"記錄到 {max_intensity}/10。建議：低強度訓練、聯絡治療師。",
                body_en=f"Logged {max_intensity}/10. Try gentle moves; "
                        "contact therapist.",
                cta_zh="緩和訓練", cta_en="Gentle routine",
                cta_route="programs", priority=90,
            )
    except Exception:
        return None
    return None


def _detect_repeat_failure(user_id: str) -> Optional[AssistantMoment]:
    """Same exercise scored <70 last 3 sessions."""
    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT exercise, score FROM sessions
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 3
            """,
            (user_id,),
        )
        if len(rows) < 3:
            return None
        same_ex = all(r["exercise"] == rows[0]["exercise"] for r in rows)
        all_low = all((r["score"] or 0) < 70 for r in rows)
        if same_ex and all_low:
            ex = rows[0]["exercise"]
            return AssistantMoment(
                id="repeat_low",
                icon="🤔",
                title_zh="這個動作有點難",
                title_en="This move is tough",
                body_zh=f"{ex} 連續 3 次低於 70 分，要不要試試簡單版本？",
                body_en=f"{ex} below 70 for 3 sessions. Try easier variant?",
                cta_zh="降低難度", cta_en="Easier mode",
                cta_route="settings", priority=75,
            )
    except Exception:
        pass
    return None


def _detect_abandoned_workflow(user_id: str) -> Optional[AssistantMoment]:
    """Active workflow but stalled."""
    try:
        from workflow import get_progress
        progress = get_progress(user_id)
        if not progress:
            return None
        return AssistantMoment(
            id="abandoned_wf",
            icon="📋",
            title_zh="繼續流程",
            title_en="Resume workflow",
            body_zh=f"你還在進行「{progress.get('name_zh', '')}」"
                    f"({progress.get('current_step', 0)+1}/{progress.get('total_steps', 0)})",
            body_en=f"In progress: {progress.get('name_en', '')} "
                    f"({progress.get('current_step', 0)+1}/{progress.get('total_steps', 0)})",
            cta_zh="繼續", cta_en="Continue",
            cta_route="daily_routine", priority=85,
        )
    except Exception:
        return None


def _detect_streak_risk(user_id: str) -> Optional[AssistantMoment]:
    """Streak ≥3 days but no session today AND it's evening."""
    if datetime.now().hour < 18:
        return None
    try:
        from smart_routing import _compute_streak
        streak = _compute_streak(user_id)
        if streak < 3:
            return None
        from db import execute_query
        rows = execute_query(
            """
            SELECT COUNT(*) as c FROM sessions
            WHERE user_id = ? AND DATE(created_at) = DATE('now')
            """,
            (user_id,),
        )
        if rows and rows[0]["c"] > 0:
            return None
        return AssistantMoment(
            id="streak_risk",
            icon="🔥",
            title_zh=f"{streak} 天連續紀錄危險中",
            title_en=f"{streak}-day streak at risk",
            body_zh="今晚還沒訓練，5 分鐘也好！",
            body_en="No training tonight yet — even 5 minutes counts!",
            cta_zh="快速開始", cta_en="Quick start",
            cta_route="auto_exercise", priority=88,
        )
    except Exception:
        return None


# ============================================================
# Public API
# ============================================================
def get_active_moments(user_id: str,
                        max_moments: int = 1) -> List[AssistantMoment]:
    """Detect all active moments, sort by priority, return top-N."""
    detectors = [
        _detect_just_finished_session,
        _detect_high_pain,
        _detect_abandoned_workflow,
        _detect_streak_risk,
        _detect_repeat_failure,
    ]
    moments = []
    for fn in detectors:
        try:
            m = fn(user_id)
            if m:
                moments.append(m)
        except Exception:
            continue

    moments.sort(key=lambda m: -m.priority)
    return moments[:max_moments]


def render_assistant_banner(user_id: str, lang: str = "zh") -> None:
    """Render the highest-priority moment as a banner."""
    moments = get_active_moments(user_id, max_moments=1)
    if not moments:
        return

    m = moments[0]
    dismiss_key = f"_dismissed_moment_{m.id}"
    if st.session_state.get(dismiss_key):
        return

    title = m.title_zh if lang == "zh" else m.title_en
    body = m.body_zh if lang == "zh" else m.body_en
    cta = m.cta_zh if lang == "zh" else m.cta_en

    with st.container(border=True):
        cols = st.columns([1, 5, 2, 1])
        with cols[0]:
            st.markdown(
                f"<div style='font-size:32px'>{m.icon}</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown(f"**{title}**")
            st.caption(body)
        with cols[2]:
            if cta and m.cta_route:
                if st.button(
                    cta, key=f"moment_{m.id}_cta",
                    type="primary", use_container_width=True,
                ):
                    from app_state import goto
                    goto(m.cta_route)
        with cols[3]:
            if st.button("✕", key=f"moment_{m.id}_dismiss"):
                st.session_state[dismiss_key] = True
                st.rerun()


def ask_quick_question(user_id: str, question: str,
                        lang: str = "zh") -> str:
    """Quick AI ask without going to chat page (for inline help bubbles)."""
    try:
        from agentic_ai import run_agent
        result = run_agent(
            question, user_id=user_id, lang=lang, max_iterations=3,
        )
        return result.answer
    except Exception:
        try:
            from rag_engine import answer_question
            rag = answer_question(question, user_id=user_id, lang=lang)
            return rag.answer
        except Exception:
            return ("AI 暫時不可用" if lang == "zh"
                    else "AI temporarily unavailable")
