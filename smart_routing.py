"""
Smart routing: context-aware "next best action" suggestions.

Looks at user state (last activity, time of day, risk score, missing data,
streak status, pending notifications) and ranks possible actions.

Returns top 3 suggestions with rationale and direct CTA buttons.
Used in home view and as floating action panel.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional

from db import execute_query


@dataclass
class Suggestion:
    route: str
    icon: str
    title_zh: str
    title_en: str
    reason_zh: str
    reason_en: str
    score: float  # priority 0-100
    cta_zh: str = "前往"
    cta_en: str = "Go"


def get_suggestions(user_id: str, lang: str = "zh",
                     limit: int = 3) -> List[Suggestion]:
    """Compute context-aware top-N suggestions for the user."""
    suggestions: List[Suggestion] = []
    ctx = _build_context(user_id)

    suggestions.extend(_check_missing_today(ctx))
    suggestions.extend(_check_streak_at_risk(ctx))
    suggestions.extend(_check_high_risk(ctx))
    suggestions.extend(_check_pending_quests(ctx))
    suggestions.extend(_check_unread_notifications(ctx))
    suggestions.extend(_check_data_completeness(ctx))
    suggestions.extend(_check_optimal_time(ctx))
    suggestions.extend(_check_recent_pain(ctx))

    seen_routes = set()
    deduped: List[Suggestion] = []
    for s in sorted(suggestions, key=lambda x: -x.score):
        if s.route in seen_routes:
            continue
        seen_routes.add(s.route)
        deduped.append(s)
        if len(deduped) >= limit:
            break
    return deduped


def _build_context(user_id: str) -> Dict:
    """Gather all signals about the user."""
    today = datetime.now().date().isoformat()

    today_sessions = execute_query(
        """
        SELECT COUNT(*) as c FROM sessions
        WHERE user_id = ? AND DATE(created_at) = ?
        """,
        (user_id, today),
    )

    last_session = execute_query(
        """
        SELECT created_at, score FROM sessions
        WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )
    last_ts = None
    last_score = None
    if last_session:
        try:
            last_ts = datetime.fromisoformat(
                str(last_session[0]["created_at"]).replace("Z", "")
            )
            last_score = last_session[0]["score"]
        except Exception:
            pass

    today_journal = _count_health_entries_today(user_id, ("journal",))
    today_pain = _count_health_entries_today(
        user_id,
        ("pain_map", "pain_records"),
    )

    streak = _compute_streak(user_id)

    risk_score = 0
    try:
        from ml_insights import calculate_risk_score
        risk = calculate_risk_score(user_id)
        risk_score = risk.get("risk_score", 0)
    except Exception:
        pass

    optimal_hour = None
    try:
        from ml_insights import predict_optimal_training_time
        opt = predict_optimal_training_time(user_id)
        if opt.get("hour") is not None and opt.get("confidence") != "low":
            optimal_hour = opt["hour"]
    except Exception:
        pass

    pending_quests = 0
    try:
        from quests import get_active_quests
        quests = get_active_quests(user_id)
        pending_quests = sum(1 for q in quests if q["ready_to_claim"])
    except Exception:
        pass

    unread = 0
    try:
        from notifications import get_unread_count
        unread = get_unread_count(user_id)
    except Exception:
        pass

    pain_trend = None
    try:
        from analytics import get_pain_trend
        pain_trend = get_pain_trend(user_id)
    except Exception:
        pass

    profile_completion = _profile_completion()

    return {
        "user_id": user_id,
        "today_sessions": today_sessions[0]["c"] if today_sessions else 0,
        "last_session_ts": last_ts,
        "last_score": last_score,
        "today_journal": today_journal,
        "today_pain": today_pain,
        "streak": streak,
        "risk_score": risk_score,
        "optimal_hour": optimal_hour,
        "pending_quests": pending_quests,
        "unread_notifications": unread,
        "pain_trend": pain_trend,
        "profile_completion": profile_completion,
        "current_hour": datetime.now().hour,
        "is_morning": 6 <= datetime.now().hour < 11,
        "is_evening": 18 <= datetime.now().hour < 22,
    }


def _count_health_entries_today(user_id: str, data_types: tuple[str, ...]) -> int:
    """Count today's entries stored in the shared health_data table."""
    if not data_types:
        return 0

    placeholders = ", ".join("?" for _ in data_types)
    try:
        rows = execute_query(
            f"""
            SELECT data_json, created_at FROM health_data
            WHERE user_id = ? AND data_type IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT 500
            """,
            (user_id, *data_types),
        )
    except Exception:
        return 0

    today = datetime.now().date().isoformat()
    return sum(1 for row in rows if _health_row_date(dict(row)) == today)


def _health_row_date(row: Dict) -> Optional[str]:
    """Extract a local ISO date from a health_data row."""
    payload: Dict = {}
    raw = row.get("data_json")
    if isinstance(raw, str) and raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            payload = {}

    for key in ("date", "entry_date", "recorded_at", "created_at"):
        parsed = _coerce_iso_date(payload.get(key))
        if parsed:
            return parsed

    parsed_ts = _coerce_timestamp_date(payload.get("ts"))
    if parsed_ts:
        return parsed_ts

    return _coerce_iso_date(row.get("created_at"))


def _coerce_iso_date(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "")).date().isoformat()
    except ValueError:
        return None


def _coerce_timestamp_date(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value)).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _compute_streak(user_id: str) -> int:
    rows = execute_query(
        """
        SELECT DATE(created_at) as d FROM sessions
        WHERE user_id = ?
        GROUP BY DATE(created_at)
        ORDER BY d DESC LIMIT 30
        """,
        (user_id,),
    )
    if not rows:
        return 0

    streak = 0
    today = datetime.now().date()
    for i, row in enumerate(rows):
        try:
            d = datetime.fromisoformat(str(row["d"])).date()
        except Exception:
            continue
        if d == today - timedelta(days=i):
            streak += 1
        else:
            break
    return streak


def _profile_completion() -> float:
    import streamlit as st
    user = st.session_state.get("user", {})
    if not isinstance(user, dict):
        return 0.0
    fields = ["name", "age", "gender", "height_cm", "weight_kg",
              "condition", "goals", "preferred_training_time"]
    filled = sum(1 for f in fields if user.get(f))
    return (filled / len(fields)) * 100


# ============================================================
# Suggestion generators
# ============================================================
def _check_missing_today(ctx: Dict) -> List[Suggestion]:
    """High priority if user hasn't trained today."""
    if ctx["today_sessions"] > 0:
        return []

    score = 70
    if ctx["streak"] >= 3:
        score = 90
    if ctx["is_evening"]:
        score += 10

    return [Suggestion(
        route="auto_exercise",
        icon="🎬",
        title_zh="今日訓練", title_en="Train Today",
        reason_zh=(f"連續 {ctx['streak']} 天" if ctx["streak"] >= 2
                   else "今天還沒訓練"),
        reason_en=(f"{ctx['streak']}-day streak — keep it!"
                   if ctx["streak"] >= 2 else "No training yet today"),
        score=score,
        cta_zh="立即開始", cta_en="Start now",
    )]


def _check_streak_at_risk(ctx: Dict) -> List[Suggestion]:
    """Streak ≥3 days but no session today."""
    if ctx["today_sessions"] > 0 or ctx["streak"] < 3:
        return []
    return [Suggestion(
        route="live_enhanced",
        icon="🔥",
        title_zh=f"保持 {ctx['streak']} 天連續紀錄",
        title_en=f"Save your {ctx['streak']}-day streak",
        reason_zh="今晚不練就斷了！",
        reason_en="Don't break it — train tonight!",
        score=85,
    )]


def _check_high_risk(ctx: Dict) -> List[Suggestion]:
    """Risk score ≥ 70 → suggest contacting therapist."""
    if ctx["risk_score"] < 50:
        return []
    return [Suggestion(
        route="analytics",
        icon="⚠️",
        title_zh="風險警示", title_en="Risk Alert",
        reason_zh=f"風險評分 {ctx['risk_score']}/100，建議查看",
        reason_en=f"Risk score {ctx['risk_score']}/100, review needed",
        score=80 + min(15, ctx["risk_score"] - 50),
    )]


def _check_pending_quests(ctx: Dict) -> List[Suggestion]:
    """Quests waiting to be claimed."""
    if ctx["pending_quests"] == 0:
        return []
    return [Suggestion(
        route="quests",
        icon="🎁",
        title_zh=f"領取 {ctx['pending_quests']} 個任務獎勵",
        title_en=f"Claim {ctx['pending_quests']} quest rewards",
        reason_zh="完成的任務還沒領",
        reason_en="Don't forget your XP!",
        score=65 + ctx["pending_quests"] * 3,
    )]


def _check_unread_notifications(ctx: Dict) -> List[Suggestion]:
    """Unread notifications waiting."""
    if ctx["unread_notifications"] == 0:
        return []
    return [Suggestion(
        route="notifications",
        icon="🔔",
        title_zh=f"{ctx['unread_notifications']} 則新通知",
        title_en=f"{ctx['unread_notifications']} new notifications",
        reason_zh="可能包含重要訊息",
        reason_en="May contain important info",
        score=40 + min(20, ctx["unread_notifications"] * 5),
    )]


def _check_data_completeness(ctx: Dict) -> List[Suggestion]:
    """Profile not yet complete."""
    if ctx["profile_completion"] >= 80:
        return []
    return [Suggestion(
        route="profile",
        icon="✨",
        title_zh="完善個人資料",
        title_en="Complete your profile",
        reason_zh=f"目前 {ctx['profile_completion']:.0f}% 完整",
        reason_en=f"Currently {ctx['profile_completion']:.0f}% complete",
        score=30 + (100 - ctx["profile_completion"]) * 0.3,
    )]


def _check_optimal_time(ctx: Dict) -> List[Suggestion]:
    """Suggest training during user's best-performing hour."""
    if ctx["optimal_hour"] is None or ctx["today_sessions"] > 0:
        return []
    if abs(ctx["current_hour"] - ctx["optimal_hour"]) > 1:
        return []
    return [Suggestion(
        route="auto_exercise",
        icon="⏰",
        title_zh="最佳訓練時段",
        title_en="Optimal training time",
        reason_zh=f"你在 {ctx['optimal_hour']:02d}:00 表現最好",
        reason_en=f"You perform best at {ctx['optimal_hour']:02d}:00",
        score=72,
    )]


def _check_recent_pain(ctx: Dict) -> List[Suggestion]:
    """Pain logged today but no exercise — suggest gentle session."""
    if ctx["today_pain"] == 0 or ctx["today_sessions"] > 0:
        return []
    return [Suggestion(
        route="programs",
        icon="🩹",
        title_zh="緩和訓練",
        title_en="Gentle Routine",
        reason_zh="今天記錄了疼痛，建議低強度",
        reason_en="Pain logged today — try low intensity",
        score=55,
    )]


# ============================================================
# UI helper
# ============================================================
def render_suggestions(user_id: str, lang: str = "zh",
                        limit: int = 3) -> None:
    """Render suggestion cards in current view."""
    import streamlit as st
    from app_state import goto

    suggestions = get_suggestions(user_id, lang=lang, limit=limit)
    if not suggestions:
        return

    st.subheader("💡 " + ("下一步建議" if lang == "zh" else "Next Best Actions"))

    cols = st.columns(len(suggestions))
    for i, s in enumerate(suggestions):
        with cols[i]:
            with st.container(border=True):
                title = s.title_zh if lang == "zh" else s.title_en
                reason = s.reason_zh if lang == "zh" else s.reason_en
                cta = s.cta_zh if lang == "zh" else s.cta_en

                st.markdown(f"### {s.icon} {title}")
                st.caption(reason)
                if st.button(
                    cta,
                    key=f"sugg_{s.route}_{i}",
                    use_container_width=True,
                    type="primary",
                ):
                    goto(s.route)
