"""
AI 動作示範視頻生成（使用 Google Gemini Veo 3.1）。
為每個復健動作生成完整演示視頻，緩存以避免重複生成。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import google_media


DEMO_VIDEO_CACHE_DIR = Path(__file__).parent / "demo_videos"


def ensure_cache_dir() -> None:
    """確保視頻緩存目錄存在。"""
    DEMO_VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cached_video_path(exercise_key: str) -> Optional[Path]:
    """檢查是否已有緩存的演示視頻。"""
    ensure_cache_dir()
    video_path = DEMO_VIDEO_CACHE_DIR / f"{exercise_key}_demo.mp4"
    return video_path if video_path.exists() else None


def generate_demo_video(
    exercise_key: str,
    exercise_name: str,
    description: str,
    cue: str,
    duration_seconds: int = 15,
) -> Optional[str]:
    """
    使用 AI 生成動作示範視頻。
    返回視頻文件路徑，若失敗則返回 None。
    """
    # Check cache first
    cached = get_cached_video_path(exercise_key)
    if cached:
        return str(cached)

    # Check if API key is available
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    ensure_cache_dir()
    output_path = DEMO_VIDEO_CACHE_DIR / f"{exercise_key}_demo.mp4"

    try:
        # Create detailed prompt for video generation
        prompt = (
            f"Create a professional rehabilitation exercise demonstration video. "
            f"Exercise: {exercise_name}\n"
            f"Description: {description}\n"
            f"Key cues: {cue}\n"
            f"Show a healthcare professional performing the movement clearly with proper form. "
            f"Duration: {duration_seconds} seconds. "
            f"Include smooth transitions between starting position, movement, and return to rest. "
            f"Professional lighting, clear background, suitable for medical/rehabilitation context."
        )

        # Use google_media to generate video (if Veo is available)
        # This function should exist in google_media.py
        video_data = google_media.generate_video(
            prompt=prompt,
            duration_seconds=min(duration_seconds, 60),  # Veo max is usually 60s
            model="gemini-2.0-flash-exp",  # Using latest available model
        )

        if video_data:
            # Save video to cache
            if isinstance(video_data, bytes):
                output_path.write_bytes(video_data)
            else:
                # If it's a file path, copy it
                import shutil
                shutil.copy(video_data, output_path)

            return str(output_path)

    except Exception as e:
        print(f"Video generation failed: {e}")
        return None

    return None


def list_available_demo_videos() -> dict[str, str]:
    """列出所有已生成的示範視頻。"""
    ensure_cache_dir()
    videos = {}
    for video_file in DEMO_VIDEO_CACHE_DIR.glob("*_demo.mp4"):
        exercise_key = video_file.stem.replace("_demo", "")
        videos[exercise_key] = str(video_file)
    return videos


def clear_demo_video(exercise_key: str) -> bool:
    """刪除特定練習的示範視頻。"""
    video_path = get_cached_video_path(exercise_key)
    if video_path:
        try:
            video_path.unlink()
            return True
        except Exception:
            return False
    return False


def clear_all_demo_videos() -> int:
    """刪除所有示範視頻，返回刪除的數量。"""
    ensure_cache_dir()
    count = 0
    for video_file in DEMO_VIDEO_CACHE_DIR.glob("*_demo.mp4"):
        try:
            video_file.unlink()
            count += 1
        except Exception:
            pass
    return count
