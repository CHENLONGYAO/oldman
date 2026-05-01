"""
生命跡象追蹤：血壓、心率、血氧、體重、體溫。
存儲於 user_data/{name}.json 的 vitals 列表。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import history as hist


VITALS_NORMAL_RANGES = {
    "bp_sys": (120, 80, 90, 180),      # (ideal_sys, ideal_dia, min, max)
    "bp_dia": (120, 80, 60, 120),
    "heart_rate": (70, 60, 100),        # (ideal, min, max)
    "spo2": (98, 95, 100),              # (ideal, min, max)
    "weight_kg": (70, 30, 150),         # (typical, min, max)
    "temperature": (37.0, 36.1, 37.2),  # (ideal, min, max)
}


def save_vital(name: str, vital_type: str, value: float) -> None:
    """
    保存單筆生命跡象。
    vital_type: "bp_sys", "bp_dia", "heart_rate", "spo2", "weight_kg", "temperature"
    """
    vital_entry = {
        "ts": int(time.time()),
        "date": datetime.now().date().isoformat(),
        "type": vital_type,
        "value": float(value),
    }
    hist.save_user_section(name, "vitals", vital_entry)


def load_vitals(name: str, vital_type: str = None, days: int = 30) -> List[Dict[str, Any]]:
    """讀取最近 N 天的生命跡象（可選擇特定類型）。"""
    all_vitals = hist.load_user_section(name, "vitals", [])
    if not all_vitals:
        return []

    cutoff = (datetime.now() - timedelta(days=days)).date()
    filtered = [
        v for v in all_vitals
        if datetime.fromisoformat(v.get("date", "1900-01-01")).date() >= cutoff
    ]

    if vital_type:
        filtered = [v for v in filtered if v.get("type") == vital_type]

    return filtered


def latest_vitals(name: str) -> Dict[str, float]:
    """取得每個指標最新的一筆數據。"""
    all_vitals = hist.load_user_section(name, "vitals", [])
    if not all_vitals:
        return {}

    latest = {}
    for vital in reversed(all_vitals):
        vital_type = vital.get("type")
        if vital_type not in latest:
            latest[vital_type] = vital.get("value")

    return latest


def is_abnormal(vital_type: str, value: float) -> bool:
    """判斷是否異常（超出正常範圍）。"""
    if vital_type not in VITALS_NORMAL_RANGES:
        return False

    ranges = VITALS_NORMAL_RANGES[vital_type]
    if len(ranges) >= 3:
        min_val = ranges[-2]
        max_val = ranges[-1]
        return value < min_val or value > max_val

    return False


def vitals_summary(name: str, days: int = 7) -> Dict[str, Any]:
    """計算生命跡象統計（平均值、最高值、最低值）。"""
    summary = {}
    vital_types = ["bp_sys", "bp_dia", "heart_rate", "spo2", "weight_kg", "temperature"]

    for vital_type in vital_types:
        vitals = load_vitals(name, vital_type, days)
        if vitals:
            values = [v["value"] for v in vitals]
            summary[vital_type] = {
                "count": len(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "latest": values[-1],
            }

    return summary
