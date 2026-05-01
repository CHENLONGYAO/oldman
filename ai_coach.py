"""Gemini-backed rehab coaching text generation.

This module only generates text guidance. It does not generate images or videos,
so the UI remains a coaching experience instead of a media-generation tool.
"""
from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

import google_media


COACH_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")
COACH_MODEL = COACH_MODELS[0]


def api_key() -> str:
    """Read Gemini API key from env vars or Streamlit secrets."""
    key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_AI_API_KEY")
        or ""
    ).strip()
    if key:
        return key
    try:
        return (
            st.secrets.get("GEMINI_API_KEY", "")
            or st.secrets.get("GOOGLE_API_KEY", "")
            or st.secrets.get("GOOGLE_AI_API_KEY", "")
            or ""
        ).strip()
    except Exception:
        return ""


def is_configured() -> bool:
    return bool(api_key())


def _extract_text(data: dict[str, Any]) -> str:
    texts: list[str] = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


def generate_coaching(
    tpl: dict,
    profile: dict | None = None,
    lang: str = "zh",
) -> dict[str, Any]:
    """Generate structured coaching guidance for one exercise."""
    key = api_key()
    if not key:
        raise google_media.GoogleMediaError("Gemini API key is not configured.")

    profile = profile or {}
    system = (
        "You are a careful home rehabilitation coach. "
        "Give concise, safe, non-diagnostic exercise guidance. "
        "Do not claim to replace a clinician. "
        "Return valid JSON only."
    )
    if lang == "zh":
        prompt = f"""
請用繁體中文為居家復健 App 產生一段可直接顯示的 AI 教練教學。
動作名稱：{tpl.get("name", "")}
動作說明：{tpl.get("description", "")}
重點提醒：{tpl.get("cue", "")}
分類：{tpl.get("category", "")}
使用者資料：年齡 {profile.get("age", "未知")}，復健原因 {profile.get("diagnosis", "") or profile.get("condition", "")}

請回傳 JSON，格式如下：
{{
  "encouragement": "一句親切鼓勵",
  "script": [
    {{"phase": "準備", "line": "一句"}},
    {{"phase": "示範", "line": "一句"}},
    {{"phase": "重點", "line": "一句"}},
    {{"phase": "節奏", "line": "一句"}},
    {{"phase": "安全", "line": "一句"}}
  ],
  "mistakes": [
    {{"title": "常見錯誤", "detail": "修正方式"}}
  ]
}}
每個 line 不超過 35 個中文字，mistakes 請給 3 個。
"""
    else:
        prompt = f"""
Generate AI coach guidance for a home rehab app.
Exercise: {tpl.get("name", "")}
Description: {tpl.get("description", "")}
Key cue: {tpl.get("cue", "")}
Category: {tpl.get("category", "")}
User profile: age {profile.get("age", "unknown")}, reason {profile.get("diagnosis", "") or profile.get("condition", "")}

Return JSON only:
{{
  "encouragement": "one warm sentence",
  "script": [
    {{"phase": "Setup", "line": "one sentence"}},
    {{"phase": "Demo", "line": "one sentence"}},
    {{"phase": "Cue", "line": "one sentence"}},
    {{"phase": "Tempo", "line": "one sentence"}},
    {{"phase": "Safety", "line": "one sentence"}}
  ],
  "mistakes": [
    {{"title": "mistake", "detail": "correction"}}
  ]
}}
Keep each line under 18 words and provide exactly 3 mistakes.
"""

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "responseMimeType": "application/json",
        },
    }
    last_error: Exception | None = None
    data: dict[str, Any] | None = None
    for model in COACH_MODELS:
        try:
            data = google_media.request_json(
                f"{google_media.BASE_URL}/models/{model}:generateContent",
                key,
                payload,
            )
            break
        except google_media.GoogleMediaError as exc:
            message = str(exc)
            if (
                "API_KEY_INVALID" in message
                or "PERMISSION_DENIED" in message
                or "403" in message
            ):
                raise
            last_error = exc
    if data is None:
        raise last_error or google_media.GoogleMediaError("Gemini request failed.")

    text = _extract_text(data)
    if not text:
        raise google_media.GoogleMediaError("Gemini did not return coaching text.")
    parsed = _parse_json_text(text)
    if not isinstance(parsed.get("script"), list) or not parsed["script"]:
        raise google_media.GoogleMediaError("Gemini response did not include a coaching script.")
    parsed.setdefault("mistakes", [])
    parsed.setdefault("encouragement", "")
    return parsed
