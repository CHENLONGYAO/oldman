"""
Advanced analytics module: trend analysis, predictions, anomaly detection.

Provides metrics beyond basic scoring:
- Recovery rate calculations
- Improvement percentage
- Anomaly detection (sudden score drops)
- Cohort comparisons
- Adherence tracking
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import numpy as np

from db import get_user_sessions, get_health_data, execute_query


def calculate_improvement_rate(user_id: str, window_days: int = 30) -> Dict:
    """Calculate score improvement rate over time window."""
    sessions = get_user_sessions(user_id, limit=200)
    if len(sessions) < 2:
        return {"rate": 0.0, "baseline": 0.0, "current": 0.0, "samples": 0}

    cutoff = datetime.now() - timedelta(days=window_days)
    recent = []
    older = []
    for s in sessions:
        ts = _parse_ts(s.get("created_at"))
        if not ts:
            continue
        if ts >= cutoff:
            recent.append(s["score"])
        else:
            older.append(s["score"])

    if not recent:
        return {"rate": 0.0, "baseline": 0.0, "current": 0.0, "samples": 0}

    current_avg = float(np.mean(recent))
    baseline_avg = float(np.mean(older)) if older else current_avg
    rate = ((current_avg - baseline_avg) / baseline_avg * 100) if baseline_avg else 0.0

    return {
        "rate": round(rate, 1),
        "baseline": round(baseline_avg, 1),
        "current": round(current_avg, 1),
        "samples": len(recent),
    }


def calculate_adherence(user_id: str, target_per_week: int = 3,
                        weeks: int = 4) -> Dict:
    """Calculate session adherence rate."""
    sessions = get_user_sessions(user_id, limit=200)
    cutoff = datetime.now() - timedelta(weeks=weeks)

    weekly_counts: Dict[int, int] = {}
    for s in sessions:
        ts = _parse_ts(s.get("created_at"))
        if not ts or ts < cutoff:
            continue
        week_num = ts.isocalendar()[1]
        weekly_counts[week_num] = weekly_counts.get(week_num, 0) + 1

    if not weekly_counts:
        return {"adherence_pct": 0.0, "weeks_met": 0, "total_weeks": weeks}

    weeks_met = sum(1 for c in weekly_counts.values() if c >= target_per_week)
    adherence_pct = (weeks_met / weeks) * 100

    return {
        "adherence_pct": round(adherence_pct, 1),
        "weeks_met": weeks_met,
        "total_weeks": weeks,
        "avg_per_week": round(np.mean(list(weekly_counts.values())), 1),
    }


def detect_anomalies(user_id: str, threshold_std: float = 2.0) -> List[Dict]:
    """Detect anomalous sessions (sudden score drops)."""
    sessions = get_user_sessions(user_id, limit=100)
    if len(sessions) < 5:
        return []

    scores = [s["score"] for s in sessions if s.get("score") is not None]
    if len(scores) < 5:
        return []

    mean = np.mean(scores)
    std = np.std(scores)
    threshold = mean - (threshold_std * std)

    anomalies = []
    for s in sessions:
        if s.get("score") is not None and s["score"] < threshold:
            anomalies.append({
                "session_id": s.get("session_id"),
                "exercise": s.get("exercise"),
                "score": s.get("score"),
                "expected": round(mean, 1),
                "deviation": round(mean - s["score"], 1),
                "date": s.get("created_at"),
            })

    return anomalies[:10]


def predict_recovery_timeline(user_id: str, target_score: float = 85.0) -> Dict:
    """Predict when user will reach target score using linear regression."""
    sessions = get_user_sessions(user_id, limit=100)
    if len(sessions) < 5:
        return {
            "estimated_days": None,
            "estimated_date": None,
            "confidence": "low",
            "current_score": 0.0,
            "target_score": target_score,
        }

    sessions_sorted = sorted(sessions,
                             key=lambda s: _parse_ts(s["created_at"]) or datetime.min)
    scores = [s["score"] for s in sessions_sorted if s.get("score") is not None]

    if len(scores) < 5:
        return {
            "estimated_days": None,
            "estimated_date": None,
            "confidence": "low",
            "current_score": 0.0,
            "target_score": target_score,
        }

    x = np.arange(len(scores))
    y = np.array(scores)

    slope, intercept = np.polyfit(x, y, 1)
    current = scores[-1]

    if slope <= 0:
        return {
            "estimated_days": None,
            "estimated_date": None,
            "confidence": "stable" if abs(slope) < 0.1 else "declining",
            "current_score": round(current, 1),
            "target_score": target_score,
            "trend_slope": round(slope, 3),
        }

    sessions_needed = max(0, (target_score - current) / slope)
    days_per_session = 2.0
    estimated_days = int(sessions_needed * days_per_session)
    estimated_date = (datetime.now() + timedelta(days=estimated_days)).date()

    confidence = "high" if len(scores) >= 20 else "medium" if len(scores) >= 10 else "low"

    return {
        "estimated_days": estimated_days,
        "estimated_date": estimated_date.isoformat(),
        "confidence": confidence,
        "current_score": round(current, 1),
        "target_score": target_score,
        "trend_slope": round(slope, 3),
        "samples": len(scores),
    }


def get_pain_trend(user_id: str, days: int = 30) -> Dict:
    """Analyze pain reduction trend."""
    sessions = get_user_sessions(user_id, limit=100)
    cutoff = datetime.now() - timedelta(days=days)

    pain_data = []
    for s in sessions:
        ts = _parse_ts(s.get("created_at"))
        if not ts or ts < cutoff:
            continue
        if s.get("pain_before") is not None and s.get("pain_after") is not None:
            pain_data.append({
                "before": s["pain_before"],
                "after": s["pain_after"],
                "reduction": s["pain_before"] - s["pain_after"],
                "date": s.get("created_at"),
            })

    if not pain_data:
        return {"avg_reduction": 0, "samples": 0, "trend": "no_data"}

    avg_reduction = float(np.mean([p["reduction"] for p in pain_data]))
    avg_before = float(np.mean([p["before"] for p in pain_data]))
    avg_after = float(np.mean([p["after"] for p in pain_data]))

    trend = "improving" if avg_reduction > 0.5 else \
            "stable" if avg_reduction > -0.5 else "worsening"

    return {
        "avg_reduction": round(avg_reduction, 1),
        "avg_before": round(avg_before, 1),
        "avg_after": round(avg_after, 1),
        "samples": len(pain_data),
        "trend": trend,
    }


def get_exercise_breakdown(user_id: str) -> List[Dict]:
    """Get per-exercise performance statistics."""
    sessions = get_user_sessions(user_id, limit=500)
    if not sessions:
        return []

    by_exercise: Dict[str, List[float]] = {}
    for s in sessions:
        ex = s.get("exercise", "unknown")
        score = s.get("score")
        if score is not None:
            by_exercise.setdefault(ex, []).append(score)

    breakdown = []
    for ex, scores in by_exercise.items():
        breakdown.append({
            "exercise": ex,
            "count": len(scores),
            "avg_score": round(float(np.mean(scores)), 1),
            "best_score": round(max(scores), 1),
            "worst_score": round(min(scores), 1),
            "consistency": round(100 - float(np.std(scores)), 1),
        })

    return sorted(breakdown, key=lambda x: -x["count"])


def get_cohort_stats(user_role: str = "patient") -> Dict:
    """Get aggregate statistics across all users (for comparison)."""
    rows = execute_query(
        """
        SELECT s.score, s.exercise, u.user_id
        FROM sessions s
        JOIN users u ON s.user_id = u.user_id
        WHERE u.role = ?
        ORDER BY s.created_at DESC
        LIMIT 5000
        """,
        (user_role,)
    )

    if not rows:
        return {"avg_score": 0, "users": 0, "sessions": 0}

    scores = [r["score"] for r in rows if r["score"] is not None]
    unique_users = len(set(r["user_id"] for r in rows))

    return {
        "avg_score": round(float(np.mean(scores)), 1) if scores else 0,
        "median_score": round(float(np.median(scores)), 1) if scores else 0,
        "p90_score": round(float(np.percentile(scores, 90)), 1) if scores else 0,
        "users": unique_users,
        "sessions": len(scores),
    }


def compare_to_cohort(user_id: str) -> Dict:
    """Compare user's performance to cohort average."""
    user_sessions = get_user_sessions(user_id, limit=100)
    if not user_sessions:
        return {"percentile": None, "vs_avg": 0}

    user_scores = [s["score"] for s in user_sessions if s.get("score")]
    if not user_scores:
        return {"percentile": None, "vs_avg": 0}

    user_avg = float(np.mean(user_scores))
    cohort = get_cohort_stats()
    cohort_avg = cohort.get("avg_score", 0)

    diff = user_avg - cohort_avg
    pct_diff = (diff / cohort_avg * 100) if cohort_avg else 0

    return {
        "user_avg": round(user_avg, 1),
        "cohort_avg": cohort_avg,
        "diff": round(diff, 1),
        "pct_vs_cohort": round(pct_diff, 1),
        "above_average": user_avg > cohort_avg,
    }


def _parse_ts(ts) -> Optional[datetime]:
    """Parse timestamp string to datetime."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00").split(".")[0])
    except (ValueError, AttributeError):
        return None
