"""Google Gemini media generation helpers.

Reads API credentials from environment variables or a user-supplied value.
Never hard-code keys in this module.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any


BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
NANO_BANANA_2_MODEL = "gemini-3.1-flash-image-preview"
NANO_BANANA_PRO_MODEL = "gemini-3-pro-image-preview"
NANO_BANANA_MODEL = "gemini-2.5-flash-image"
VEO_MODEL = "veo-3.1-generate-preview"
VEO_FAST_MODEL = "veo-3.1-fast-generate-preview"
VEO_LITE_MODEL = "veo-3.1-lite-generate-preview"


class GoogleMediaError(RuntimeError):
    pass


def api_key_from_env() -> str:
    return (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_AI_API_KEY")
        or ""
    ).strip()


def request_json(
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    method: str = "POST",
) -> dict[str, Any]:
    headers = {"x-goog-api-key": api_key}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GoogleMediaError(f"Google API {exc.code}: {body}") from exc
    except Exception as exc:
        raise GoogleMediaError(str(exc)) from exc


def download_bytes(url: str, api_key: str) -> bytes:
    req = urllib.request.Request(url, headers={"x-goog-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GoogleMediaError(f"Download failed {exc.code}: {body}") from exc
    except Exception as exc:
        raise GoogleMediaError(str(exc)) from exc


def generate_image(
    prompt: str,
    api_key: str,
    aspect_ratio: str = "16:9",
    image_size: str = "1K",
    model: str = NANO_BANANA_2_MODEL,
) -> tuple[bytes, str, str]:
    image_config = {"aspectRatio": aspect_ratio}
    if model in {NANO_BANANA_2_MODEL, NANO_BANANA_PRO_MODEL}:
        image_config["imageSize"] = image_size
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "imageConfig": image_config,
        },
    }
    data = request_json(
        f"{BASE_URL}/models/{model}:generateContent",
        api_key,
        payload,
    )
    texts: list[str] = []
    for cand in data.get("candidates", []):
        content = cand.get("content", {})
        for part in content.get("parts", []):
            if part.get("text"):
                texts.append(part["text"])
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                mime = inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png"
                return base64.b64decode(inline_data["data"]), mime, "\n".join(texts)
    raise GoogleMediaError("No image returned from Gemini image model.")


def start_video_generation(
    prompt: str,
    api_key: str,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    model: str = VEO_MODEL,
) -> str:
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
        },
    }
    data = request_json(
        f"{BASE_URL}/models/{model}:predictLongRunning",
        api_key,
        payload,
    )
    name = data.get("name")
    if not name:
        raise GoogleMediaError(f"No operation name returned: {data}")
    return name


def get_operation(operation_name: str, api_key: str) -> dict[str, Any]:
    return request_json(f"{BASE_URL}/{operation_name}", api_key, method="GET")


def extract_video_uri(operation: dict[str, Any]) -> str | None:
    samples = (
        operation.get("response", {})
        .get("generateVideoResponse", {})
        .get("generatedSamples", [])
    )
    if not samples:
        return None
    video = samples[0].get("video", {})
    return video.get("uri")
