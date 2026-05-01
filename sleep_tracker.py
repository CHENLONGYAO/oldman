"""
Sleep tracker: log sleep duration, quality, and correlate with recovery.
"""
from __future__ import annotations
import json
from datetime import datetime, date, timedelta, time
from typing import Dict, List, Optional

from db import execute_query, execute_update


def log_sleep(user_id: str, sleep_date: str, bedtime: str,
              wake_time: str, quality: int,
              interruptions: int = 0, notes: str = "") -> bool:
    """Log a sleep entry. Times in HH:MM format. Quality 1-5."""
    duration_h = _calculate_duration(bedtime, wake_time)

    payload = {
        "sleep_date": sleep_date,
        "bedtime": bedtime,
        "wake_time": wake_time,
        "duration_hours": duration_h,
        "quality": quality,
        "interruptions": interruptions,
        "notes": notes,
        "logged_at": datetime.now().isoformat(),
    }

    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, ?, ?, datetime('now', '+1 year'))
            """,
            (user_id, f"sleep_{sleep_date}",
             json.dumps(payload, ensure_ascii=False)),
        )
        return True
    except Exception:
        return False


def get_sleep_history(user_id: str, days: int = 30) -> List[Dict]:
    """Get sleep entries for past N days."""
    history = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        rows = execute_query(
            """
            SELECT data_json FROM offline_cache
            WHERE user_id = ? AND cache_type = ?
            """,
            (user_id, f"sleep_{d}"),
        )
        if rows:
            try:
                history.append(json.loads(rows[0]["data_json"]))
            except Exception:
                continue
    return list(reversed(history))


def get_sleep_stats(user_id: str, days: int = 14) -> Dict:
    """Calculate sleep statistics."""
    history = get_sleep_history(user_id, days)
    if not history:
        return {
            "samples": 0,
            "avg_duration": 0,
            "avg_quality": 0,
            "consistency_score": 0,
        }

    durations = [h["duration_hours"] for h in history if h.get("duration_hours")]
    qualities = [h["quality"] for h in history if h.get("quality")]
    bedtimes = []
    for h in history:
        bt = h.get("bedtime", "")
        if bt and ":" in bt:
            try:
                hr, mn = map(int, bt.split(":"))
                bedtimes.append(hr * 60 + mn)
            except Exception:
                continue

    consistency = 100.0
    if len(bedtimes) >= 3:
        avg = sum(bedtimes) / len(bedtimes)
        variance = sum((b - avg) ** 2 for b in bedtimes) / len(bedtimes)
        std_min = variance ** 0.5
        consistency = max(0, 100 - std_min * 0.5)

    return {
        "samples": len(history),
        "avg_duration": round(sum(durations) / len(durations), 1) if durations else 0,
        "avg_quality": round(sum(qualities) / len(qualities), 1) if qualities else 0,
        "consistency_score": round(consistency, 1),
        "min_duration": min(durations) if durations else 0,
        "max_duration": max(durations) if durations else 0,
    }


def correlate_with_performance(user_id: str, days: int = 30) -> Dict:
    """Correlate sleep duration/quality with next-day exercise scores."""
    sleep_history = get_sleep_history(user_id, days)
    if len(sleep_history) < 3:
        return {"correlation": None, "samples": 0}

    sleep_by_date = {h["sleep_date"]: h for h in sleep_history}

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = execute_query(
        """
        SELECT DATE(created_at) as d, AVG(score) as avg_score
        FROM sessions
        WHERE user_id = ? AND DATE(created_at) >= ?
        GROUP BY DATE(created_at)
        """,
        (user_id, cutoff),
    )

    pairs_dur = []
    pairs_qual = []
    for r in rows:
        sleep_date = (datetime.fromisoformat(r["d"]).date() -
                      timedelta(days=1)).isoformat()
        sleep_data = sleep_by_date.get(sleep_date)
        if not sleep_data:
            continue
        avg_score = r["avg_score"]
        if sleep_data.get("duration_hours"):
            pairs_dur.append((sleep_data["duration_hours"], avg_score))
        if sleep_data.get("quality"):
            pairs_qual.append((sleep_data["quality"], avg_score))

    return {
        "samples": len(pairs_dur),
        "duration_correlation": _pearson(pairs_dur) if len(pairs_dur) >= 3 else None,
        "quality_correlation": _pearson(pairs_qual) if len(pairs_qual) >= 3 else None,
    }


def get_sleep_score(user_id: str) -> Dict:
    """Compute overall sleep health score (0-100)."""
    stats = get_sleep_stats(user_id)
    if stats["samples"] == 0:
        return {"score": None, "factors": []}

    score = 0
    factors = []

    duration = stats["avg_duration"]
    if 7 <= duration <= 9:
        score += 40
        factors.append(("duration", "ideal", 40))
    elif 6 <= duration < 7 or 9 < duration <= 10:
        score += 25
        factors.append(("duration", "ok", 25))
    else:
        score += 10
        factors.append(("duration", "poor", 10))

    quality = stats["avg_quality"]
    score += int(quality * 6)
    factors.append(("quality", f"{quality}/5", int(quality * 6)))

    consistency = stats["consistency_score"]
    score += int(consistency * 0.3)
    factors.append(("consistency", f"{consistency:.0f}%", int(consistency * 0.3)))

    return {
        "score": min(100, score),
        "factors": factors,
        "stats": stats,
    }


def get_sleep_recommendations(user_id: str, lang: str = "zh") -> List[str]:
    """Generate personalized sleep recommendations."""
    stats = get_sleep_stats(user_id)
    recs = []

    if stats["samples"] == 0:
        return [
            "開始記錄你的睡眠以獲取個人化建議" if lang == "zh"
            else "Log your sleep to get personalized recommendations"
        ]

    if stats["avg_duration"] < 7:
        recs.append(
            f"目前平均 {stats['avg_duration']:.1f} 小時，建議睡 7-9 小時"
            if lang == "zh"
            else f"Avg {stats['avg_duration']:.1f}h — aim for 7-9h"
        )
    if stats["avg_quality"] < 3:
        recs.append(
            "睡眠品質偏低，試試睡前避免螢幕、保持房間涼爽"
            if lang == "zh"
            else "Low quality — try no screens before bed, keep room cool"
        )
    if stats["consistency_score"] < 70:
        recs.append(
            "作息不規律，固定就寢時間有助提升睡眠品質"
            if lang == "zh"
            else "Irregular schedule — set consistent bedtime"
        )

    if not recs:
        recs.append(
            "你的睡眠習慣很好！繼續保持 ✨" if lang == "zh"
            else "Great sleep habits! Keep it up ✨"
        )

    return recs


def _calculate_duration(bedtime: str, wake_time: str) -> float:
    """Calculate hours between bedtime and wake time, handling midnight cross."""
    try:
        bh, bm = map(int, bedtime.split(":"))
        wh, wm = map(int, wake_time.split(":"))
        bed_min = bh * 60 + bm
        wake_min = wh * 60 + wm
        if wake_min <= bed_min:
            wake_min += 24 * 60
        return round((wake_min - bed_min) / 60, 1)
    except Exception:
        return 0.0


def _pearson(pairs: List[tuple]) -> float:
    """Pearson correlation coefficient."""
    if len(pairs) < 2:
        return 0.0
    n = len(pairs)
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / n
    my = sum(ys) / n

    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5

    if dx * dy == 0:
        return 0.0
    return round(num / (dx * dy), 3)
