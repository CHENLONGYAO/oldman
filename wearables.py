"""
Wearable device integration: import data from fitness trackers.

Supported import formats:
- Apple Health (XML export)
- Fitbit (CSV export)
- Google Fit (JSON via Health Connect)
- Generic CSV (timestamp, type, value)

Auto-populates vitals (heart rate, weight, BP) and activity data.
"""
from __future__ import annotations
import csv
import json
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

from db import execute_update, execute_query


SUPPORTED_FORMATS = {
    "apple_health": {
        "name_zh": "Apple Health", "name_en": "Apple Health",
        "ext": "xml", "icon": "🍎",
    },
    "fitbit": {
        "name_zh": "Fitbit", "name_en": "Fitbit",
        "ext": "csv", "icon": "⌚",
    },
    "google_fit": {
        "name_zh": "Google Fit", "name_en": "Google Fit",
        "ext": "json", "icon": "🤖",
    },
    "garmin": {
        "name_zh": "Garmin Connect", "name_en": "Garmin Connect",
        "ext": "csv", "icon": "🏃",
    },
    "generic_csv": {
        "name_zh": "通用 CSV", "name_en": "Generic CSV",
        "ext": "csv", "icon": "📄",
    },
}


def parse_apple_health(xml_content: str) -> List[Dict]:
    """Parse Apple Health XML export. Returns normalized records."""
    records = []
    type_map = {
        "HKQuantityTypeIdentifierHeartRate": "heart_rate",
        "HKQuantityTypeIdentifierBodyMass": "weight_kg",
        "HKQuantityTypeIdentifierBloodPressureSystolic": "bp_sys",
        "HKQuantityTypeIdentifierBloodPressureDiastolic": "bp_dia",
        "HKQuantityTypeIdentifierOxygenSaturation": "spo2",
        "HKQuantityTypeIdentifierBodyTemperature": "temperature",
        "HKQuantityTypeIdentifierStepCount": "steps",
        "HKQuantityTypeIdentifierActiveEnergyBurned": "calories",
    }

    try:
        root = ET.fromstring(xml_content)
        for record in root.findall(".//Record"):
            type_attr = record.get("type", "")
            if type_attr not in type_map:
                continue

            value = record.get("value")
            unit = record.get("unit", "")
            start_date = record.get("startDate", "")

            if not value or not start_date:
                continue

            try:
                value_float = float(value)
            except ValueError:
                continue

            if type_map[type_attr] == "spo2" and value_float < 1:
                value_float *= 100

            records.append({
                "type": type_map[type_attr],
                "value": value_float,
                "unit": unit,
                "timestamp": _normalize_date(start_date),
                "source": "apple_health",
            })
    except ET.ParseError as e:
        return [{"error": f"XML parse error: {e}"}]

    return records


def parse_fitbit_csv(csv_content: str) -> List[Dict]:
    """Parse Fitbit CSV export."""
    records = []
    reader = csv.DictReader(io.StringIO(csv_content))

    for row in reader:
        ts = _row_value(row, ["Date", "date", "timestamp", "Timestamp", "Start Time"])
        if not ts:
            continue

        for aliases, type_name in [
            (
                ["Heart Rate", "Resting Heart Rate", "heart_rate", "Heart rate"],
                "heart_rate",
            ),
            (["Weight", "Weight (kg)", "weight", "Body Weight"], "weight_kg"),
            (["Steps", "Step Count", "steps"], "steps"),
            (["Calories", "Calories Burned", "calories"], "calories"),
        ]:
            val = _parse_float(_row_value(row, aliases))
            if val is not None:
                records.append({
                    "type": type_name,
                    "value": val,
                    "timestamp": ts,
                    "source": "fitbit",
                })

    return records


def parse_garmin_csv(csv_content: str) -> List[Dict]:
    """Parse common Garmin Connect CSV exports."""
    records = []
    reader = csv.DictReader(io.StringIO(csv_content))

    for row in reader:
        ts = _row_value(
            row,
            ["Start Time", "Activity Date", "Date", "date", "timestamp"],
        )
        if not ts:
            continue

        for aliases, type_name in [
            (
                ["Avg HR", "Average Heart Rate", "Avg Heart Rate", "Heart Rate"],
                "heart_rate",
            ),
            (["Weight", "Weight (kg)", "Body Weight"], "weight_kg"),
            (["Steps", "Step Count"], "steps"),
            (["Calories", "Calories Burned"], "calories"),
        ]:
            val = _parse_float(_row_value(row, aliases))
            if val is not None:
                records.append({
                    "type": type_name,
                    "value": val,
                    "timestamp": ts,
                    "source": "garmin",
                })

    return records


def parse_google_fit(json_content: str) -> List[Dict]:
    """Parse Google Fit JSON export."""
    records = []
    try:
        data = json.loads(json_content)
    except json.JSONDecodeError as e:
        return [{"error": f"JSON parse error: {e}"}]

    points = _google_fit_points(data)
    type_map = {
        "com.google.heart_rate.bpm": "heart_rate",
        "com.google.weight": "weight_kg",
        "com.google.step_count.delta": "steps",
        "com.google.calories.expended": "calories",
        "com.google.blood_pressure": "blood_pressure",
    }

    for point in points:
        data_type = point.get("dataTypeName", "")
        if data_type not in type_map:
            continue

        timestamp = _normalize_date(
            point.get("startTimeNanos")
            or point.get("startTimeMillis")
            or point.get("startTime")
            or point.get("timestamp")
            or ""
        )
        metric_type = type_map[data_type]

        if metric_type == "blood_pressure":
            bp_values = _google_blood_pressure_values(point)
            for type_name, value in bp_values.items():
                records.append({
                    "type": type_name,
                    "value": value,
                    "timestamp": timestamp,
                    "source": "google_fit",
                })
            continue

        for value_obj in point.get("value", []):
            val = _google_value(value_obj)
            if val is not None:
                records.append({
                    "type": metric_type,
                    "value": val,
                    "timestamp": timestamp,
                    "source": "google_fit",
                })

    return records


def parse_generic_csv(csv_content: str, source: str = "generic_csv") -> List[Dict]:
    """Parse generic CSV with columns: timestamp/date, type/metric, value."""
    records = []
    reader = csv.DictReader(io.StringIO(csv_content))

    for row in reader:
        ts = _row_value(row, ["timestamp", "Timestamp", "date", "Date", "Start Time"])
        type_val = _row_value(row, ["type", "Type", "metric", "Metric", "name", "Name"])
        val = _parse_float(_row_value(row, ["value", "Value", "amount", "Amount"]))

        if not (ts and type_val and val is not None):
            continue

        type_name = _normalize_metric_type(type_val)
        if not type_name:
            continue

        records.append({
            "type": type_name,
            "value": val,
            "timestamp": ts,
            "source": source,
        })

    return records


def import_records(user_id: str, records: List[Dict]) -> Dict:
    """Import records into the shared health_data table."""
    imported = 0
    skipped = 0
    errors = []

    aggregated: Dict[tuple[str, str], List[Dict]] = {}
    for r in records:
        if "error" in r:
            errors.append(r["error"])
            skipped += 1
            continue

        metric_type = _normalize_metric_type(r.get("type"))
        value = _parse_float(r.get("value"))
        timestamp = _normalize_date(r.get("timestamp", ""))
        date_key = timestamp[:10] if timestamp else ""
        if not (metric_type and value is not None and date_key):
            skipped += 1
            continue

        source = str(r.get("source") or "wearable")
        aggregated.setdefault((source, date_key), []).append({
            **r,
            "type": metric_type,
            "value": value,
            "timestamp": timestamp,
            "source": source,
        })

    for (source, date_key), day_records in aggregated.items():
        by_type: Dict[str, List[float]] = {}
        for r in day_records:
            by_type.setdefault(r["type"], []).append(r["value"])

        avg_values = {
            k: _aggregate_metric(k, v)
            for k, v in by_type.items()
            if v
        }
        if not avg_values:
            skipped += len(day_records)
            continue

        payload = {
            "date": date_key,
            "source": source,
            "metrics": avg_values,
            **avg_values,
        }

        try:
            _replace_daily_payload(user_id, "vitals", source, date_key, payload)
            imported += 1
        except Exception as e:
            errors.append(str(e))
            skipped += len(day_records)

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:5],
        "total_records": len(records),
        "valid_records": sum(len(items) for items in aggregated.values()),
    }


def get_imported_summary(user_id: str, days: int = 30) -> Dict:
    """Summary of imported wearable data."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    rows = execute_query(
        """
        SELECT data_json, created_at
        FROM health_data
        WHERE user_id = ? AND data_type = 'vitals' AND created_at >= ?
        ORDER BY created_at DESC
        """,
        (user_id, cutoff),
    )

    by_source: Dict[str, Dict] = {}
    for row in rows:
        try:
            payload = json.loads(row["data_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        source = payload.get("source")
        if not source or source == "manual":
            continue
        item = by_source.setdefault(source, {
            "source": source,
            "count": 0,
            "first_date": row["created_at"],
            "last_date": row["created_at"],
        })
        item["count"] += 1
        item["first_date"] = min(item["first_date"], row["created_at"])
        item["last_date"] = max(item["last_date"], row["created_at"])

    sources = sorted(
        by_source.values(),
        key=lambda item: item["last_date"],
        reverse=True,
    )
    return {
        "sources": sources,
        "total": sum(item["count"] for item in sources),
    }


def detect_format(filename: str, content: str) -> Optional[str]:
    """Auto-detect file format."""
    name_lower = filename.lower()
    head = content[:4000].lower()

    if name_lower.endswith(".xml") and "<healthdata" in head:
        return "apple_health"
    if name_lower.endswith(".json") and (
        "datatypename" in head or "datasourceid" in head or "data points" in head
    ):
        return "google_fit"
    if name_lower.endswith(".csv"):
        if "fitbit" in name_lower or "fitbit" in head:
            return "fitbit"
        if "garmin" in name_lower or "activity" in head:
            return "garmin"
        return "generic_csv"
    return None


def _row_value(row: Dict, names: List[str]) -> Optional[str]:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = lower_map.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return None


def _parse_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_metric_type(metric_type: object) -> Optional[str]:
    if metric_type is None:
        return None
    key = str(metric_type).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "systolic": "bp_sys",
        "bp_systolic": "bp_sys",
        "blood_pressure_systolic": "bp_sys",
        "diastolic": "bp_dia",
        "bp_diastolic": "bp_dia",
        "blood_pressure_diastolic": "bp_dia",
        "weight": "weight_kg",
        "body_weight": "weight_kg",
        "heart_rate_bpm": "heart_rate",
        "resting_heart_rate": "heart_rate",
        "step_count": "steps",
        "active_energy": "calories",
        "energy": "calories",
        "o2_saturation": "spo2",
        "oxygen_saturation": "spo2",
    }
    return aliases.get(key, key)


def _aggregate_metric(metric_type: str, values: List[float]) -> float:
    if metric_type in {"steps", "calories"}:
        return round(sum(values), 2)
    return round(sum(values) / len(values), 2)


def _replace_daily_payload(
    user_id: str,
    data_type: str,
    source: str,
    date_key: str,
    payload: Dict,
) -> None:
    execute_update(
        """
        DELETE FROM health_data
        WHERE user_id = ? AND data_type = ?
          AND data_json LIKE ? AND data_json LIKE ?
        """,
        (user_id, data_type, f'%"{date_key}"%', f'%"{source}"%'),
    )
    execute_update(
        """
        INSERT INTO health_data (user_id, data_type, data_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            data_type,
            json.dumps(payload, ensure_ascii=False, default=str),
            date_key,
        ),
    )


def _google_fit_points(data: object) -> List[Dict]:
    if isinstance(data, dict):
        if isinstance(data.get("Data Points"), list):
            return data["Data Points"]
        if isinstance(data.get("dataPoint"), list):
            return data["dataPoint"]
        if isinstance(data.get("point"), list):
            return data["point"]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _google_value(value_obj: Dict) -> Optional[float]:
    if "fpVal" in value_obj:
        return _parse_float(value_obj.get("fpVal"))
    if "intVal" in value_obj:
        return _parse_float(value_obj.get("intVal"))
    return None


def _google_blood_pressure_values(point: Dict) -> Dict[str, float]:
    values = [
        _google_value(value_obj)
        for value_obj in point.get("value", [])
    ]
    values = [value for value in values if value is not None]
    result: Dict[str, float] = {}
    if values:
        result["bp_sys"] = values[0]
    if len(values) > 1:
        result["bp_dia"] = values[1]
    return result


def _normalize_date(date_str: str) -> str:
    """Normalize date string to ISO format."""
    if not date_str:
        return ""
    text = str(date_str).strip()
    if text.isdigit():
        try:
            value = int(text)
            if len(text) >= 18:
                seconds = value / 1_000_000_000
            elif len(text) >= 15:
                seconds = value / 1_000_000
            elif len(text) >= 12:
                seconds = value / 1_000
            else:
                seconds = value
            return datetime.fromtimestamp(seconds).isoformat()
        except (OverflowError, OSError, ValueError):
            return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    try:
        for fmt in [
            "%Y-%m-%d %H:%M:%S %z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%Y/%m/%d",
        ]:
            try:
                dt = datetime.strptime(text, fmt)
                return dt.isoformat()
            except ValueError:
                continue
    except Exception:
        pass
    return text
