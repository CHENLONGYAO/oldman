"""
ML insights: predictive models, risk scoring, treatment recommendations.

Uses simple ML techniques (linear regression, statistical analysis) to
provide:
- Recovery time estimates with confidence intervals
- Risk scoring (at-risk patients)
- Recommended exercise suggestions based on history
- Optimal training time prediction
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

from db import get_user_sessions, get_health_data
from analytics import (
    calculate_improvement_rate,
    calculate_adherence,
    detect_anomalies,
    get_pain_trend,
)


def calculate_risk_score(user_id: str) -> Dict:
    """
    Calculate at-risk score (0-100) based on multiple factors.

    Higher score = more at-risk (declining performance, low adherence,
    high pain, recent anomalies).
    """
    risk = 0
    factors = []

    improvement = calculate_improvement_rate(user_id, window_days=30)
    if improvement["rate"] < -10:
        risk += 30
        factors.append("分數明顯下降 / Significant score decline")
    elif improvement["rate"] < 0:
        risk += 15
        factors.append("分數略下降 / Slight score decline")

    adherence = calculate_adherence(user_id)
    if adherence["adherence_pct"] < 30:
        risk += 25
        factors.append("低參與度 / Low adherence")
    elif adherence["adherence_pct"] < 60:
        risk += 10
        factors.append("中等參與度 / Moderate adherence")

    pain = get_pain_trend(user_id)
    if pain["trend"] == "worsening":
        risk += 25
        factors.append("疼痛加劇 / Worsening pain")
    elif pain["avg_before"] > 7:
        risk += 15
        factors.append("高疼痛水平 / High pain level")

    anomalies = detect_anomalies(user_id)
    if len(anomalies) >= 3:
        risk += 20
        factors.append("多次異常表現 / Multiple anomalies")
    elif len(anomalies) >= 1:
        risk += 10
        factors.append("近期異常 / Recent anomaly")

    risk = min(100, risk)
    if risk >= 70:
        level = "high"
        level_zh = "高"
    elif risk >= 40:
        level = "medium"
        level_zh = "中"
    else:
        level = "low"
        level_zh = "低"

    return {
        "risk_score": risk,
        "level": level,
        "level_zh": level_zh,
        "factors": factors,
        "needs_attention": risk >= 50,
    }


def recommend_exercises(user_id: str, top_k: int = 3) -> List[Dict]:
    """Recommend next exercises based on user's history and weaknesses."""
    sessions = get_user_sessions(user_id, limit=200)
    if not sessions:
        return []

    by_exercise: Dict[str, List[float]] = {}
    last_done: Dict[str, datetime] = {}

    for s in sessions:
        ex = s.get("exercise")
        if not ex or s.get("score") is None:
            continue
        by_exercise.setdefault(ex, []).append(s["score"])
        ts = _parse_ts(s.get("created_at"))
        if ts and (ex not in last_done or ts > last_done[ex]):
            last_done[ex] = ts

    recommendations = []
    now = datetime.now()
    for ex, scores in by_exercise.items():
        avg_score = float(np.mean(scores))
        days_since = (now - last_done[ex]).days if ex in last_done else 999

        priority = 0.0
        reason = []

        if avg_score < 70:
            priority += 50
            reason.append("需加強 / Needs work")
        elif avg_score < 85:
            priority += 25
            reason.append("有進步空間 / Room to grow")

        if days_since > 7:
            priority += 30
            reason.append(f"{days_since} 天未練習 / Not done in {days_since}d")
        elif days_since > 3:
            priority += 10

        if len(scores) < 5:
            priority += 15
            reason.append("樣本不足 / Limited data")

        recommendations.append({
            "exercise": ex,
            "priority": priority,
            "avg_score": round(avg_score, 1),
            "days_since": days_since,
            "reasons": reason,
        })

    recommendations.sort(key=lambda r: -r["priority"])
    return recommendations[:top_k]


def predict_optimal_training_time(user_id: str) -> Dict:
    """Predict best time of day to train based on historical performance."""
    sessions = get_user_sessions(user_id, limit=200)
    if len(sessions) < 5:
        return {"hour": None, "confidence": "low"}

    by_hour: Dict[int, List[float]] = {}
    for s in sessions:
        ts = _parse_ts(s.get("created_at"))
        if not ts or s.get("score") is None:
            continue
        by_hour.setdefault(ts.hour, []).append(s["score"])

    if not by_hour:
        return {"hour": None, "confidence": "low"}

    best_hour = None
    best_avg = 0.0
    for hour, scores in by_hour.items():
        if len(scores) < 2:
            continue
        avg = float(np.mean(scores))
        if avg > best_avg:
            best_avg = avg
            best_hour = hour

    if best_hour is None:
        return {"hour": None, "confidence": "low"}

    confidence = "high" if len(by_hour[best_hour]) >= 5 else "medium"

    return {
        "hour": best_hour,
        "hour_str": f"{best_hour:02d}:00",
        "avg_score_at_hour": round(best_avg, 1),
        "samples": len(by_hour[best_hour]),
        "confidence": confidence,
    }


def get_personalized_insights(user_id: str) -> List[Dict]:
    """Generate human-readable personalized insights."""
    insights = []

    improvement = calculate_improvement_rate(user_id)
    if improvement["samples"] > 0:
        if improvement["rate"] > 10:
            insights.append({
                "type": "positive",
                "icon": "🎉",
                "title_zh": "進步顯著",
                "title_en": "Great Progress",
                "msg_zh": f"過去 30 天進步 {improvement['rate']}%！繼續保持！",
                "msg_en": f"Improved {improvement['rate']}% in last 30 days!",
            })
        elif improvement["rate"] < -10:
            insights.append({
                "type": "warning",
                "icon": "⚠️",
                "title_zh": "需要注意",
                "title_en": "Attention Needed",
                "msg_zh": f"分數下降 {abs(improvement['rate'])}%，建議調整訓練。",
                "msg_en": f"Score down {abs(improvement['rate'])}%, consider adjusting.",
            })

    adherence = calculate_adherence(user_id)
    if adherence["adherence_pct"] >= 80:
        insights.append({
            "type": "positive",
            "icon": "🔥",
            "title_zh": "堅持訓練",
            "title_en": "Consistent",
            "msg_zh": f"達到目標 {adherence['weeks_met']}/{adherence['total_weeks']} 週！",
            "msg_en": f"Met goals {adherence['weeks_met']}/{adherence['total_weeks']} weeks!",
        })
    elif adherence["adherence_pct"] < 40 and adherence["total_weeks"] >= 2:
        insights.append({
            "type": "warning",
            "icon": "📉",
            "title_zh": "頻率偏低",
            "title_en": "Low Frequency",
            "msg_zh": "建議每週至少訓練 3 次以加速恢復。",
            "msg_en": "Aim for 3+ sessions per week for faster recovery.",
        })

    optimal = predict_optimal_training_time(user_id)
    if optimal.get("hour") is not None and optimal["confidence"] != "low":
        insights.append({
            "type": "info",
            "icon": "🕐",
            "title_zh": "最佳訓練時間",
            "title_en": "Best Training Time",
            "msg_zh": f"您在 {optimal['hour_str']} 表現最佳（平均 {optimal['avg_score_at_hour']} 分）",
            "msg_en": f"You perform best at {optimal['hour_str']} (avg {optimal['avg_score_at_hour']})",
        })

    pain = get_pain_trend(user_id)
    if pain["samples"] >= 3:
        if pain["trend"] == "improving":
            insights.append({
                "type": "positive",
                "icon": "💚",
                "title_zh": "疼痛改善",
                "title_en": "Pain Improving",
                "msg_zh": f"平均疼痛降低 {pain['avg_reduction']} 分。",
                "msg_en": f"Average pain reduced by {pain['avg_reduction']}.",
            })
        elif pain["trend"] == "worsening":
            insights.append({
                "type": "warning",
                "icon": "🩹",
                "title_zh": "疼痛加劇",
                "title_en": "Pain Worsening",
                "msg_zh": "建議與治療師聯絡。",
                "msg_en": "Consider contacting your therapist.",
            })

    return insights


def _parse_ts(ts) -> Optional[datetime]:
    """Parse timestamp."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00").split(".")[0])
    except (ValueError, AttributeError):
        return None
