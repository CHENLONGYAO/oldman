"""
疼痛身體地圖：追蹤身體各部位的疼痛強度。
存儲於 user_data/{name}.json 的 pain_records 列表。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import history as hist


BODY_REGIONS = {
    "頭頸": "head_neck",
    "左肩": "l_shoulder",
    "右肩": "r_shoulder",
    "上背": "upper_back",
    "下背": "lower_back",
    "左肘": "l_elbow",
    "右肘": "r_elbow",
    "左腕": "l_wrist",
    "右腕": "r_wrist",
    "左髖": "l_hip",
    "右髖": "r_hip",
    "左膝": "l_knee",
    "右膝": "r_knee",
    "左踝": "l_ankle",
    "右踝": "r_ankle",
}


def save_pain_record(name: str, pain_regions: Dict[str, int], note: str = "") -> None:
    """
    保存疼痛記錄。
    pain_regions: {region_name: intensity 0-10}
    """
    record = {
        "ts": int(time.time()),
        "date": datetime.now().date().isoformat(),
        "regions": pain_regions,
        "note": note,
        "max_intensity": max(pain_regions.values()) if pain_regions else 0,
    }
    hist.save_user_section(name, "pain_records", record)


def load_pain_records(name: str, days: int = 30) -> List[Dict[str, Any]]:
    """讀取最近 N 天的疼痛記錄。"""
    all_records = hist.load_user_section(name, "pain_records", [])
    if not all_records:
        return []

    cutoff = (datetime.now() - timedelta(days=days)).date()
    return [
        r for r in all_records
        if datetime.fromisoformat(r.get("date", "1900-01-01")).date() >= cutoff
    ]


def pain_intensity_by_region(name: str, days: int = 30) -> Dict[str, List[float]]:
    """取得各身體部位在 N 天內的疼痛強度序列。"""
    records = load_pain_records(name, days)
    intensity_by_region = {}

    for region_name in BODY_REGIONS.keys():
        intensities = []
        for record in records:
            regions = record.get("regions", {})
            if region_name in regions:
                intensities.append(regions[region_name])
        if intensities:
            intensity_by_region[region_name] = intensities

    return intensity_by_region


def pain_change(name: str) -> Dict[str, Any]:
    """計算疼痛變化（今日 vs 7 天平均）。"""
    records = load_pain_records(name, days=7)
    if not records:
        return {}

    today = datetime.now().date().isoformat()
    today_record = None
    week_avg = {}

    for record in records:
        if record.get("date") == today:
            today_record = record

        for region, intensity in record.get("regions", {}).items():
            if region not in week_avg:
                week_avg[region] = []
            week_avg[region].append(intensity)

    # Calculate averages
    for region in week_avg:
        week_avg[region] = sum(week_avg[region]) / len(week_avg[region])

    result = {}
    if today_record:
        for region, today_intensity in today_record.get("regions", {}).items():
            avg = week_avg.get(region, 0)
            result[region] = {
                "today": today_intensity,
                "avg": avg,
                "change": today_intensity - avg,
            }

    return result


def most_painful_regions(name: str, days: int = 7, top_n: int = 5) -> List[tuple]:
    """找出最疼痛的 N 個部位（按最近 N 天的平均疼痛強度）。"""
    intensity_data = pain_intensity_by_region(name, days)
    region_avg = [
        (region, sum(intensities) / len(intensities))
        for region, intensities in intensity_data.items()
    ]
    region_avg.sort(key=lambda x: x[1], reverse=True)
    return region_avg[:top_n]


def pain_trend(name: str, region: str = None) -> Dict[str, Any]:
    """取得疼痛趨勢（整體或特定部位）。"""
    records = load_pain_records(name, days=30)
    if not records:
        return {}

    dates = []
    intensities = []

    for record in records:
        dates.append(record.get("date"))
        if region:
            intensity = record.get("regions", {}).get(region, 0)
        else:
            intensity = record.get("max_intensity", 0)
        intensities.append(intensity)

    return {
        "dates": dates,
        "intensities": intensities,
        "trend": "improving" if len(intensities) > 1 and intensities[-1] < intensities[0] else "stable",
    }
