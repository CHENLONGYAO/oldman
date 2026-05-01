"""
Vision-language model feedback: Claude vision API for clinical-quality feedback.

Pipeline:
1. Sample N keyframes from session video
2. Annotate each with skeleton overlay + worst-frame markers
3. Send to Claude with cached system prompt + biomechanics context
4. Parse JSON response into actionable advice

Uses prompt caching for efficiency:
- System prompt with rehab assistant persona (cached)
- Biomechanics knowledge base (cached)
- Per-request: keyframes + form analysis from form_critic

Falls back gracefully if anthropic SDK / API key absent.
"""
from __future__ import annotations
import base64
import io
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class VLMFeedback:
    summary: str
    issues: List[Dict]          # {joint, description, severity, fix}
    encouragement: str
    next_steps: List[str]
    overall_grade: str          # "excellent" / "good" / "fair" / "needs_work"
    confidence: float


SYSTEM_PROMPT_ZH = """你是一位專業的居家復健視覺診斷助手。你的任務：
1. 分析病人的關鍵姿勢影像
2. 對照臨床規範指出動作問題
3. 給予清楚、有溫度的回饋
4. 在 200 字內完成

回應格式必須是 JSON：
{
  "summary": "簡短整體評估",
  "issues": [
    {"joint": "膝蓋", "description": "具體問題", "severity": "minor|moderate|major", "fix": "如何改善"}
  ],
  "encouragement": "鼓勵性訊息",
  "next_steps": ["下一步建議1", "下一步建議2"],
  "overall_grade": "excellent|good|fair|needs_work"
}
"""

SYSTEM_PROMPT_EN = """You are a clinical home-rehab vision assistant. Your job:
1. Analyze keyframes of the patient's movement
2. Identify form issues against clinical norms
3. Provide warm, clear feedback
4. Keep total response under 200 words

Response MUST be JSON:
{
  "summary": "Brief overall assessment",
  "issues": [
    {"joint": "knee", "description": "specific issue", "severity": "minor|moderate|major", "fix": "how to fix"}
  ],
  "encouragement": "encouraging message",
  "next_steps": ["next step 1", "next step 2"],
  "overall_grade": "excellent|good|fair|needs_work"
}
"""

BIOMECH_CONTEXT = """Clinical reference (cached):
- Knee flexion ROM: 0-135°. Squats target 90-110° flexion.
- Shoulder flexion: 0-180°. Most rehab targets 90-150°.
- Hip flexion: 0-120°. Standing exercises typically 30-90°.
- Bilateral asymmetry > 15° suggests compensation or weakness.
- Trunk forward bend > 30° during squats indicates posterior chain weakness.
- Common compensations: knee valgus, hip drop, shoulder shrug, lumbar flexion.
"""


def api_key() -> str:
    """Read Anthropic API key from env vars or Streamlit secrets."""
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if key:
        return key
    try:
        import streamlit as st
        return (st.secrets.get("ANTHROPIC_API_KEY", "") or "").strip()
    except Exception:
        return ""


def is_available() -> bool:
    """Check if Claude vision API is callable."""
    if not api_key():
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def encode_image_for_api(img_bytes: bytes,
                          media_type: str = "image/jpeg") -> Dict:
    """Encode image bytes for Claude vision API."""
    encoded = base64.standard_b64encode(img_bytes).decode("utf-8")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": encoded,
        },
    }


def encode_image_from_array(arr) -> Optional[Dict]:
    """Encode numpy BGR/RGB array to API format."""
    try:
        import cv2
        ok, buf = cv2.imencode(".jpg", arr,
                                [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return None
        return encode_image_for_api(buf.tobytes())
    except Exception:
        return None


def get_feedback(keyframes: List, form_analysis: Optional[Dict] = None,
                  exercise_name: str = "",
                  lang: str = "zh") -> Optional[VLMFeedback]:
    """Get VLM feedback for a session.

    keyframes: list of numpy arrays (BGR images) — usually 3-5 critical frames.
    form_analysis: optional dict from form_critic.FormReport
    """
    if not is_available():
        return None

    try:
        import anthropic
    except ImportError:
        return None

    encoded_images = []
    for kf in keyframes[:5]:
        enc = encode_image_from_array(kf)
        if enc:
            encoded_images.append(enc)

    if not encoded_images:
        return None

    user_text_parts = []
    if exercise_name:
        user_text_parts.append(
            f"運動項目: {exercise_name}" if lang == "zh"
            else f"Exercise: {exercise_name}"
        )
    if form_analysis:
        user_text_parts.append(
            f"自動分析結果:\n{json.dumps(form_analysis, ensure_ascii=False, indent=2)[:500]}"
            if lang == "zh" else
            f"Auto analysis:\n{json.dumps(form_analysis, indent=2)[:500]}"
        )
    user_text_parts.append(
        "請分析這些關鍵幀，並用 JSON 格式回覆。"
        if lang == "zh" else
        "Analyze these keyframes and respond in JSON."
    )

    content = []
    for img in encoded_images:
        content.append(img)
    content.append({"type": "text", "text": "\n\n".join(user_text_parts)})

    try:
        client = anthropic.Anthropic(api_key=api_key())
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT_EN,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": BIOMECH_CONTEXT,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": content}],
        )
    except Exception:
        return None

    if not response.content:
        return None

    text = response.content[0].text
    return _parse_response(text)


def _parse_response(text: str) -> Optional[VLMFeedback]:
    """Parse JSON response from Claude."""
    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return _fallback_parse(text)

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return _fallback_parse(text)

    return VLMFeedback(
        summary=str(data.get("summary", "")),
        issues=data.get("issues", []) if isinstance(data.get("issues"), list) else [],
        encouragement=str(data.get("encouragement", "")),
        next_steps=(data.get("next_steps", [])
                   if isinstance(data.get("next_steps"), list) else []),
        overall_grade=str(data.get("overall_grade", "fair")),
        confidence=0.9,
    )


def _fallback_parse(text: str) -> VLMFeedback:
    """Build feedback from non-JSON text."""
    return VLMFeedback(
        summary=text[:200],
        issues=[],
        encouragement="",
        next_steps=[],
        overall_grade="fair",
        confidence=0.4,
    )


def select_keyframes(world_seq, video_frames: list,
                      n_frames: int = 4) -> list:
    """Select N keyframes most informative for VLM analysis.

    Strategy:
    - First and last frames (start/end pose)
    - Frame with peak motion (extremum)
    - Frame with worst form deviation if available
    """
    if not video_frames or len(video_frames) < 2:
        return video_frames

    n = len(video_frames)
    if n <= n_frames:
        return list(video_frames)

    indices = [0, n - 1]

    if world_seq is not None and len(world_seq) > 0:
        try:
            import numpy as np
            motion = np.linalg.norm(np.diff(world_seq, axis=0), axis=2).sum(1)
            peak = int(np.argmax(motion))
            indices.append(peak)

            mid = n // 2
            indices.append(mid)
        except Exception:
            pass

    indices = sorted(set(indices))[:n_frames]
    return [video_frames[i] for i in indices if i < len(video_frames)]
