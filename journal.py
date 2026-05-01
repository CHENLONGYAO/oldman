"""
每日健康日記：心情、精力、睡眠、天氣、備注。
存儲於 user_data/{name}.json 的 journal 列表。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import history as hist


def save_journal(name: str, entry: Dict[str, Any]) -> None:
    """
    保存日記條目。
    entry: {mood, energy, sleep_hours, weather, notes}
    自動添加 ts（時間戳）和日期。
    """
    entry_with_ts = {
        "ts": int(time.time()),
        "date": datetime.now().date().isoformat(),
        "mood": int(entry.get("mood", 3)),
        "energy": int(entry.get("energy", 3)),
        "sleep_hours": float(entry.get("sleep_hours", 7)),
        "weather": str(entry.get("weather", "sunny")),
        "notes": str(entry.get("notes", "")),
    }
    hist.save_user_section(name, "journal", entry_with_ts)


def load_journal(name: str, days: int = 30) -> List[Dict[str, Any]]:
    """讀取最近 N 天的日記。"""
    all_entries = hist.load_user_section(name, "journal", [])
    if not all_entries:
        return []
    cutoff = (datetime.now() - timedelta(days=days)).date()
    return [
        e for e in all_entries
        if datetime.fromisoformat(e.get("date", "1900-01-01")).date()
        >= cutoff
    ]


def today_journal(name: str) -> Dict[str, Any] | None:
    """查詢今天是否已填日記。"""
    all_entries = hist.load_user_section(name, "journal", [])
    if not all_entries:
        return None
    today = datetime.now().date().isoformat()
    for e in reversed(all_entries):
        if e.get("date") == today:
            return e
    return None


def journal_stats(name: str, days: int = 14) -> Dict[str, Any]:
    """計算日記統計（平均心情、精力、睡眠）。"""
    entries = load_journal(name, days)
    if not entries:
        return {
            "avg_mood": 0,
            "avg_energy": 0,
            "avg_sleep": 0,
            "count": 0,
        }
    moods = [e.get("mood", 3) for e in entries]
    energies = [e.get("energy", 3) for e in entries]
    sleeps = [e.get("sleep_hours", 7) for e in entries]
    return {
        "avg_mood": sum(moods) / len(moods) if moods else 0,
        "avg_energy": sum(energies) / len(energies) if energies else 0,
        "avg_sleep": sum(sleeps) / len(sleeps) if sleeps else 0,
        "count": len(entries),
    }
