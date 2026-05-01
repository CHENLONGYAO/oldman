"""AI photo parsing helpers for medication and meal logging."""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any

DEFAULT_ANTHROPIC_VISION_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class MedicationPhotoResult:
    name: str = ""
    dose: str = ""
    frequency: str = ""
    times: list[str] = field(default_factory=list)
    notes: str = ""
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MealPhotoResult:
    meal_name: str = ""
    foods: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def ai_available() -> bool:
    """Return whether a supported image model provider is configured."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def configured_model_name() -> str:
    """Return the Anthropic vision model currently configured for photo parsing."""
    return (
        os.environ.get("ANTHROPIC_VISION_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
        or DEFAULT_ANTHROPIC_VISION_MODEL
    )


def analyze_medication_photo(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
    lang: str = "zh",
) -> MedicationPhotoResult:
    """Parse a medication package / pill bottle photo into a reviewable draft."""
    fallback_warning = (
        "AI 圖像辨識未啟用，請手動輸入藥物資訊。"
        if lang == "zh" else
        "AI image parsing is not enabled. Please enter medication details manually."
    )
    if not ai_available():
        return MedicationPhotoResult(warnings=[fallback_warning])

    prompt = (
        "請從藥袋、藥盒或藥瓶照片辨識藥物資訊。只提取照片中看得到的文字或高度可信資訊。"
        "不要猜測療效，不要提供醫療建議。回覆 JSON："
        '{"name":"","dose":"","frequency":"","times":["08:00"],'
        '"notes":"","confidence":0.0,"warnings":[]}'
        if lang == "zh" else
        "Parse medication information from the package/bottle photo. Extract only visible or highly reliable information. "
        "Do not guess indications or give medical advice. Return JSON: "
        '{"name":"","dose":"","frequency":"","times":["08:00"],'
        '"notes":"","confidence":0.0,"warnings":[]}'
    )
    data = _call_anthropic_vision(image_bytes, media_type, prompt)
    return _parse_medication_result(data, lang)


def analyze_meal_photo(
    image_bytes: bytes,
    media_type: str = "image/jpeg",
    lang: str = "zh",
) -> MealPhotoResult:
    """Estimate foods and macros from a meal photo into a reviewable draft."""
    fallback_warning = (
        "AI 圖像辨識未啟用，請手動選擇食物。"
        if lang == "zh" else
        "AI image parsing is not enabled. Please select foods manually."
    )
    if not ai_available():
        return MealPhotoResult(warnings=[fallback_warning])

    prompt = (
        "請辨識餐點照片中的食物並估算份量與營養。估算需保守，若看不清楚請放入 warnings。"
        "單位以每餐總量估算。回覆 JSON："
        '{"meal_name":"","foods":[{"name":"","servings":1,'
        '"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0}],'
        '"totals":{"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0},'
        '"notes":"","confidence":0.0,"warnings":[]}'
        if lang == "zh" else
        "Identify foods in this meal photo and estimate portions and nutrition. Be conservative; add warnings when uncertain. "
        "Estimate total per meal. Return JSON: "
        '{"meal_name":"","foods":[{"name":"","servings":1,'
        '"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0}],'
        '"totals":{"kcal":0,"protein_g":0,"carbs_g":0,"fat_g":0},'
        '"notes":"","confidence":0.0,"warnings":[]}'
    )
    data = _call_anthropic_vision(image_bytes, media_type, prompt)
    return _parse_meal_result(data, lang)


def _call_anthropic_vision(
    image_bytes: bytes,
    media_type: str,
    prompt: str,
) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()
    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
    response = client.messages.create(
        model=configured_model_name(),
        max_tokens=900,
        temperature=0,
        system=(
            "You extract structured health log data from images. "
            "Always return valid JSON only. Never include markdown."
        ),
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type or "image/jpeg",
                        "data": encoded,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    text = response.content[0].text if response.content else "{}"
    return _json_from_text(text)


def _json_from_text(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_medication_result(data: dict[str, Any],
                             lang: str) -> MedicationPhotoResult:
    warnings = _list_of_strings(data.get("warnings"))
    if not data:
        warnings.append(
            "無法解析 AI 回覆，請手動輸入。"
            if lang == "zh" else
            "Could not parse AI response; please enter manually."
        )
    times = [
        str(t).strip()
        for t in _list_of_strings(data.get("times"))
        if str(t).strip()
    ]
    return MedicationPhotoResult(
        name=str(data.get("name") or "").strip(),
        dose=str(data.get("dose") or "").strip(),
        frequency=str(data.get("frequency") or "").strip(),
        times=times[:4],
        notes=str(data.get("notes") or "").strip(),
        confidence=_bounded_float(data.get("confidence")),
        warnings=warnings,
        raw=data,
    )


def _parse_meal_result(data: dict[str, Any], lang: str) -> MealPhotoResult:
    warnings = _list_of_strings(data.get("warnings"))
    if not data:
        warnings.append(
            "無法解析 AI 回覆，請手動輸入。"
            if lang == "zh" else
            "Could not parse AI response; please enter manually."
        )

    foods = []
    for item in data.get("foods") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        foods.append({
            "name": name,
            "servings": max(0.1, _bounded_float(item.get("servings"), 1.0)),
            "kcal": max(0.0, _bounded_float(item.get("kcal"))),
            "protein_g": max(0.0, _bounded_float(item.get("protein_g"))),
            "carbs_g": max(0.0, _bounded_float(item.get("carbs_g"))),
            "fat_g": max(0.0, _bounded_float(item.get("fat_g"))),
            "source": "ai_photo",
        })

    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    if not totals and foods:
        totals = {
            "kcal": sum(f.get("kcal", 0) for f in foods),
            "protein_g": sum(f.get("protein_g", 0) for f in foods),
            "carbs_g": sum(f.get("carbs_g", 0) for f in foods),
            "fat_g": sum(f.get("fat_g", 0) for f in foods),
        }
    return MealPhotoResult(
        meal_name=str(data.get("meal_name") or "").strip(),
        foods=foods,
        totals={k: round(_bounded_float(totals.get(k)), 1)
                for k in ("kcal", "protein_g", "carbs_g", "fat_g")},
        notes=str(data.get("notes") or "").strip(),
        confidence=_bounded_float(data.get("confidence")),
        warnings=warnings,
        raw=data,
    )


def _list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _bounded_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1_000_000.0, float(value)))
    except (TypeError, ValueError):
        return default
