"""OAuth-backed integrations for calendar and wearable services."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

import streamlit as st

from db import execute_query, execute_update


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_EVENTS_URL = (
    "https://www.googleapis.com/calendar/v3/calendars/primary/events"
)
GOOGLE_FIT_AGGREGATE_URL = (
    "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
)

GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
]

GOOGLE_FIT_SCOPES = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
]


class IntegrationError(RuntimeError):
    """Raised when an external integration cannot complete."""


def _secret(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        if name in st.secrets:
            return str(st.secrets[name])
        oauth_secrets = st.secrets.get("oauth", {})
        if "google" in oauth_secrets:
            key = name.lower().replace("google_", "")
            value = oauth_secrets["google"].get(key)
            if value:
                return str(value)
    except Exception:
        pass
    return ""


def _redirect_uri() -> str:
    return (
        _secret("OAUTH_REDIRECT_URI")
        or _secret("SMART_REHAB_BASE_URL")
        or "http://localhost:8501"
    ).rstrip("/")


def _state_secret() -> str:
    return (
        _secret("OAUTH_STATE_SECRET")
        or _secret("SECRET_KEY")
        or "dev-oauth-state-secret-change-in-production"
    )


def _sign_state(service: str, timestamp: int, nonce: str) -> str:
    payload = f"google.{service}.{timestamp}.{nonce}".encode("utf-8")
    digest = hmac.new(
        _state_secret().encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return digest


def _make_state(service: str) -> str:
    timestamp = int(time.time())
    nonce = secrets.token_urlsafe(16)
    sig = _sign_state(service, timestamp, nonce)
    return f"google.{service}.{timestamp}.{nonce}.{sig}"


def _verify_state(state: str, expected_service: str) -> bool:
    try:
        provider, service, ts_raw, nonce, sig = state.split(".", 4)
        timestamp = int(ts_raw)
    except Exception:
        return False
    if provider != "google" or service != expected_service:
        return False
    if abs(time.time() - timestamp) > 600:
        return False
    expected = _sign_state(service, timestamp, nonce)
    return hmac.compare_digest(sig, expected)


def google_oauth_url(service: str, scopes: list[str]) -> tuple[str | None, list[str]]:
    """Build an authorization URL for a Google integration."""
    client_id = _secret("GOOGLE_CLIENT_ID")
    client_secret = _secret("GOOGLE_CLIENT_SECRET")
    missing = [
        key for key, value in {
            "GOOGLE_CLIENT_ID": client_id,
            "GOOGLE_CLIENT_SECRET": client_secret,
        }.items()
        if not value
    ]
    if missing:
        return None, missing

    state = _make_state(service)
    st.session_state.setdefault("service_oauth_states", {})[state] = service
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}", []


def complete_google_oauth_callback(user_id: str, service: str) -> dict[str, Any] | None:
    """Complete an OAuth callback for a Google service."""
    code = _query_param("code")
    state = _query_param("state")
    error = _query_param("error")
    if not (code or error):
        return None
    if not state or not _verify_state(state, service):
        return None

    try:
        if error:
            raise IntegrationError(str(error))
        token = _exchange_code(str(code))
        _save_connection(user_id, service, token)
        return {"ok": True, "service": service}
    except Exception as exc:
        return {"ok": False, "service": service, "error": str(exc)}
    finally:
        try:
            st.query_params.clear()
        except Exception:
            pass


def get_connection(user_id: str, service: str) -> dict[str, Any] | None:
    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id, f"integration:{service}"),
    )
    if not rows:
        return None
    try:
        return json.loads(rows[0]["data_json"])
    except json.JSONDecodeError:
        return None


def disconnect(user_id: str, service: str) -> None:
    execute_update(
        """
        DELETE FROM offline_cache
        WHERE user_id = ? AND cache_type = ?
        """,
        (user_id, f"integration:{service}"),
    )


def sync_journal_to_google_calendar(
    user_id: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Create or update a Google Calendar all-day event for a journal entry."""
    event = _journal_event_payload(user_id, entry)
    token = _access_token(user_id, "google_calendar")
    event_id = event["id"]
    url = f"{GOOGLE_CALENDAR_EVENTS_URL}/{event_id}"
    return _google_request("PUT", url, token, event)


def google_calendar_template_url(entry: dict[str, Any]) -> str:
    """Build a no-OAuth Google Calendar event template URL."""
    event = _journal_event_payload("local", entry)
    params = {
        "action": "TEMPLATE",
        "text": event["summary"],
        "details": event["description"],
        "dates": f"{event['start']['date'].replace('-', '')}/"
                 f"{event['end']['date'].replace('-', '')}",
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)


def sync_google_fit_summary(user_id: str, days: int = 7) -> dict[str, Any]:
    """Fetch Google Fit daily aggregates and store them as health_data."""
    token = _access_token(user_id, "google_fit")
    end = datetime.now()
    start = end - timedelta(days=days)
    payload = {
        "startTimeMillis": int(start.timestamp() * 1000),
        "endTimeMillis": int(end.timestamp() * 1000),
        "aggregateBy": [
            {"dataTypeName": "com.google.step_count.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.heart_rate.bpm"},
            {"dataTypeName": "com.google.weight"},
        ],
        "bucketByTime": {"durationMillis": 86_400_000},
    }
    data = _google_request("POST", GOOGLE_FIT_AGGREGATE_URL, token, payload)
    records = _fit_records_from_aggregate(data)

    imported = 0
    for record in records:
        if not record.get("metrics"):
            continue
        _replace_health_payload(user_id, "vitals", record)
        imported += 1
    return {"imported": imported, "days": days}


def _exchange_code(code: str) -> dict[str, Any]:
    body = {
        "code": code,
        "client_id": _secret("GOOGLE_CLIENT_ID"),
        "client_secret": _secret("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": _redirect_uri(),
        "grant_type": "authorization_code",
    }
    data = _post_form(GOOGLE_TOKEN_URL, body)
    if "access_token" not in data:
        raise IntegrationError(f"Google token response missing access_token: {data}")
    data["expires_at"] = time.time() + int(data.get("expires_in", 3600)) - 60
    return data


def _refresh_token(user_id: str, service: str, conn: dict[str, Any]) -> dict[str, Any]:
    refresh_token = conn.get("refresh_token")
    if not refresh_token:
        raise IntegrationError("缺少 refresh token，請重新連接 Google 帳戶")
    body = {
        "client_id": _secret("GOOGLE_CLIENT_ID"),
        "client_secret": _secret("GOOGLE_CLIENT_SECRET"),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    data = _post_form(GOOGLE_TOKEN_URL, body)
    conn.update(data)
    conn["refresh_token"] = refresh_token
    conn["expires_at"] = time.time() + int(conn.get("expires_in", 3600)) - 60
    _save_connection(user_id, service, conn)
    return conn


def _access_token(user_id: str, service: str) -> str:
    conn = get_connection(user_id, service)
    if not conn:
        raise IntegrationError("尚未連接 Google 帳戶")
    if float(conn.get("expires_at", 0)) <= time.time():
        conn = _refresh_token(user_id, service, conn)
    token = conn.get("access_token")
    if not token:
        raise IntegrationError("Google access token 不可用")
    return str(token)


def _save_connection(user_id: str, service: str, data: dict[str, Any]) -> None:
    payload = {
        **data,
        "service": service,
        "connected_at": datetime.now().isoformat(),
    }
    execute_update(
        """
        DELETE FROM offline_cache
        WHERE user_id = ? AND cache_type = ?
        """,
        (user_id, f"integration:{service}"),
    )
    execute_update(
        """
        INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
        VALUES (?, ?, ?, datetime('now', '+365 days'))
        """,
        (
            user_id,
            f"integration:{service}",
            json.dumps(payload, ensure_ascii=False, default=str),
        ),
    )


def _post_form(url: str, body: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _read_json(req)


def _google_request(
    method: str,
    url: str,
    access_token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Authorization": f"Bearer {access_token}"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return _read_json(req)


def _read_json(req: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise IntegrationError(f"Google API {exc.code}: {body}") from exc
    except Exception as exc:
        raise IntegrationError(str(exc)) from exc
    return json.loads(body) if body else {}


def _query_param(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _journal_event_payload(user_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    date_text = str(entry.get("date") or datetime.now().date().isoformat())[:10]
    start = datetime.fromisoformat(date_text).date()
    end = start + timedelta(days=1)
    mood = entry.get("mood", "—")
    energy = entry.get("energy", "—")
    sleep = entry.get("sleep_hours", "—")
    notes = str(entry.get("notes") or "").strip()
    digest = hashlib.sha1(f"{user_id}:{date_text}".encode("utf-8")).hexdigest()
    return {
        "id": f"srj{digest[:24]}",
        "summary": "SmartRehab 健康日誌",
        "description": (
            f"心情: {mood}/5\n"
            f"精力: {energy}/5\n"
            f"睡眠: {sleep} 小時\n"
            f"備註: {notes or '無'}"
        ),
        "start": {"date": start.isoformat()},
        "end": {"date": end.isoformat()},
        "visibility": "private",
        "extendedProperties": {
            "private": {
                "smartrehab_type": "journal",
                "smartrehab_date": date_text,
            }
        },
    }


def _fit_records_from_aggregate(data: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for bucket in data.get("bucket", []):
        start_ms = int(bucket.get("startTimeMillis", 0))
        date = datetime.fromtimestamp(start_ms / 1000).date().isoformat()
        metrics: dict[str, float] = {}
        for dataset in bucket.get("dataset", []):
            source = str(dataset.get("dataSourceId", ""))
            values = [
                _point_value(point)
                for point in dataset.get("point", [])
            ]
            values = [v for v in values if v is not None]
            if not values:
                continue
            if "step_count" in source:
                metrics["steps"] = sum(values)
            elif "calories" in source:
                metrics["calories"] = round(sum(values), 1)
            elif "heart_rate" in source:
                metrics["heart_rate"] = round(sum(values) / len(values), 1)
            elif "weight" in source:
                metrics["weight_kg"] = round(values[-1], 1)
        records.append({
            "date": date,
            "source": "google_fit",
            "metrics": metrics,
            **metrics,
        })
    return records


def _point_value(point: dict[str, Any]) -> float | None:
    values = point.get("value", [])
    if not values:
        return None
    value = values[0]
    if "fpVal" in value:
        return float(value["fpVal"])
    if "intVal" in value:
        return float(value["intVal"])
    return None


def _replace_health_payload(user_id: str, data_type: str, payload: dict[str, Any]) -> None:
    date = payload.get("date")
    source = payload.get("source")
    if date and source:
        execute_update(
            """
            DELETE FROM health_data
            WHERE user_id = ? AND data_type = ?
              AND data_json LIKE ? AND data_json LIKE ?
            """,
            (user_id, data_type, f'%"{date}"%', f'%"{source}"%'),
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
            date or datetime.now().isoformat(),
        ),
    )
