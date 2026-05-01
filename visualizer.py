"""
視覺化模組：於影格上標記關節偏差（紅點 + 角度標籤）。
使用 PIL 以支援中文/度數符號的繪製。
"""
from __future__ import annotations

import os
from typing import Dict
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# MediaPipe Pose landmark 索引對應關節名
JOINT_LANDMARK_IDX = {
    "左肩": 11, "右肩": 12,
    "左肘": 13, "右肘": 14,
    "左髖": 23, "右髖": 24,
    "左膝": 25, "右膝": 26,
}

# 線段連線（畫骨架用）
SKELETON_EDGES = [
    (11, 13), (13, 15),
    (12, 14), (14, 16),
    (11, 12),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27),
    (24, 26), (26, 28),
]


def _find_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\msjh.ttc",      # 微軟正黑體
        r"C:\Windows\Fonts\msjhbd.ttc",
        r"C:\Windows\Fonts\mingliu.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def overlay_feedback(
    frame_bgr: np.ndarray,
    image_kp: np.ndarray,
    joint_scores: Dict[str, Dict[str, float]],
    threshold: float = 15.0,
) -> np.ndarray:
    """於影格上疊加骨架、紅點與角度標籤。

    frame_bgr : (H, W, 3) uint8 BGR
    image_kp  : (33, 3) 每筆為 (x_norm, y_norm, visibility)
    """
    h, w = frame_bgr.shape[:2]

    # 先用 cv2 繪骨架線
    overlay = frame_bgr.copy()
    for a, b in SKELETON_EDGES:
        if image_kp[a, 2] < 0.3 or image_kp[b, 2] < 0.3:
            continue
        pa = (int(image_kp[a, 0] * w), int(image_kp[a, 1] * h))
        pb = (int(image_kp[b, 0] * w), int(image_kp[b, 1] * h))
        cv2.line(overlay, pa, pb, (230, 230, 230), 2, cv2.LINE_AA)

    # 切換到 PIL 繪製節點與中文
    pil = Image.fromarray(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font = _find_font(20)

    for name, idx in JOINT_LANDMARK_IDX.items():
        if name not in joint_scores:
            continue
        x = int(image_kp[idx, 0] * w)
        y = int(image_kp[idx, 1] * h)
        dev = joint_scores[name]["max_dev"]
        over = dev >= threshold

        color = (220, 40, 40) if over else (30, 170, 80)
        radius = 10 if over else 6
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=color, outline=(255, 255, 255), width=2,
        )
        if over:
            label = f"{name} {dev:.0f}°"
            # 白底讓文字清楚
            tb = draw.textbbox((x + 14, y - 14), label, font=font)
            draw.rectangle(
                [tb[0] - 4, tb[1] - 2, tb[2] + 4, tb[3] + 2],
                fill=(255, 255, 255, 200),
            )
            draw.text((x + 14, y - 14), label, fill=color, font=font)

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
