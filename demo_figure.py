"""
小人示範動畫：依範本的關節角度序列計算 2D 骨架點位，
輸出帶 SMIL `<animate>` 的 SVG，瀏覽器會自動循環播放。

設計目標：
  - 純前端動畫（無 JS、無圖檔，純 SVG SMIL）
  - 支援上肢 / 下肢 / 全身範本
  - 採用簡化前向運動學，視覺直覺即可，不要求生物力學精準

主 API：
    stick_figure_svg(angle_series, duration_s, width, height,
                     color, bg, accent_joints) -> SVG 字串
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Tuple

import numpy as np


# 連接邊：(關節 A, 關節 B)
_EDGES: List[Tuple[str, str]] = [
    ("neck", "pelvis"),
    ("L_shoulder", "R_shoulder"),
    ("L_shoulder", "L_elbow"),
    ("L_elbow", "L_wrist"),
    ("R_shoulder", "R_elbow"),
    ("R_elbow", "R_wrist"),
    ("L_hip", "R_hip"),
    ("L_hip", "L_knee"),
    ("L_knee", "L_ankle"),
    ("R_hip", "R_knee"),
    ("R_knee", "R_ankle"),
]


def _fk(origin: Tuple[float, float],
        dir_math_deg: float,
        length: float) -> Tuple[float, float]:
    """從 origin 沿著 dir_math_deg（math 慣例，逆時針）走 length；SVG 座標 y 朝下。"""
    rad = math.radians(dir_math_deg)
    return (
        origin[0] + length * math.cos(rad),
        origin[1] - length * math.sin(rad),
    )


def _pose(angles: Dict[str, float], w: int, h: int) -> Dict[str, Tuple[float, float]]:
    """以給定一組關節角度，回傳所有關節點 (x, y)。"""
    cx = w / 2
    hip_y = h * 0.62
    shoulder_y = h * 0.32
    head_y = h * 0.18

    shoulder_w = w * 0.18
    hip_w = w * 0.10
    arm_len = h * 0.17
    leg_len = h * 0.20

    pts: Dict[str, Tuple[float, float]] = {
        "head": (cx, head_y),
        "neck": (cx, shoulder_y),
        "pelvis": (cx, hip_y),
        "L_shoulder": (cx - shoulder_w, shoulder_y),
        "R_shoulder": (cx + shoulder_w, shoulder_y),
        "L_hip": (cx - hip_w, hip_y),
        "R_hip": (cx + hip_w, hip_y),
    }

    # ---- 左手臂 ----
    sa_l = float(angles.get("左肩", 25.0))
    upper_l = 270.0 - (sa_l - 25.0) * 1.2  # 25→270°(下), 175→90°(上)
    pts["L_elbow"] = _fk(pts["L_shoulder"], upper_l, arm_len)
    ea_l = float(angles.get("左肘", 175.0))
    bend_l = 180.0 - ea_l
    forearm_l = upper_l + bend_l  # 朝身體內側彎
    pts["L_wrist"] = _fk(pts["L_elbow"], forearm_l, arm_len)

    # ---- 右手臂（鏡像）----
    sa_r = float(angles.get("右肩", 25.0))
    upper_r = 270.0 + (sa_r - 25.0) * 1.2
    pts["R_elbow"] = _fk(pts["R_shoulder"], upper_r, arm_len)
    ea_r = float(angles.get("右肘", 175.0))
    bend_r = 180.0 - ea_r
    forearm_r = upper_r - bend_r
    pts["R_wrist"] = _fk(pts["R_elbow"], forearm_r, arm_len)

    # ---- 左腿 ----
    ha_l = float(angles.get("左髖", 175.0))
    thigh_l = 270.0 + (175.0 - ha_l) * (90.0 / 85.0)
    pts["L_knee"] = _fk(pts["L_hip"], thigh_l, leg_len)
    ka_l = float(angles.get("左膝", 175.0))
    knee_bend_l = 180.0 - ka_l
    shin_l = thigh_l - knee_bend_l
    pts["L_ankle"] = _fk(pts["L_knee"], shin_l, leg_len)

    # ---- 右腿（鏡像）----
    ha_r = float(angles.get("右髖", 175.0))
    thigh_r = 270.0 - (175.0 - ha_r) * (90.0 / 85.0)
    pts["R_knee"] = _fk(pts["R_hip"], thigh_r, leg_len)
    ka_r = float(angles.get("右膝", 175.0))
    knee_bend_r = 180.0 - ka_r
    shin_r = thigh_r + knee_bend_r
    pts["R_ankle"] = _fk(pts["R_knee"], shin_r, leg_len)

    return pts


def _subsample_angles(
    angle_series: Dict[str, list], n: int = 16,
) -> List[Dict[str, float]]:
    keys = list(angle_series.keys())
    if not keys:
        return []
    arrays = [np.asarray(angle_series[k], dtype=np.float32) for k in keys]
    T = max(len(a) for a in arrays)
    if T < 2:
        return []
    indices = np.linspace(0, T - 1, n).astype(int)
    frames: List[Dict[str, float]] = []
    for idx in indices:
        f: Dict[str, float] = {}
        for k, arr in zip(keys, arrays):
            i = min(int(idx), len(arr) - 1)
            f[k] = float(arr[i])
        frames.append(f)
    return frames


def _animate_block(
    attr: str, values: Iterable[float], dur: float,
) -> str:
    vs = ";".join(f"{v:.1f}" for v in values)
    return (
        f'<animate attributeName="{attr}" values="{vs}" '
        f'dur="{dur:.2f}s" repeatCount="indefinite"/>'
    )


def pose_points_for_phase(
    angle_series: Dict[str, list],
    phase: int,
    width: int = 180,
    height: int = 230,
) -> Dict[str, Tuple[float, float]]:
    """回傳某一個範本階段的 2D 小人骨架點位，供即時影格 PiP 繪製。"""
    if not angle_series:
        return {}
    keys = list(angle_series.keys())
    max_len = max((len(angle_series.get(k, [])) for k in keys), default=0)
    if max_len <= 0:
        return {}
    idx = max(0, min(int(phase), max_len - 1))
    angles: Dict[str, float] = {}
    for key in keys:
        vals = angle_series.get(key, [])
        if not vals:
            continue
        angles[key] = float(vals[min(idx, len(vals) - 1)])
    return _pose(angles, width, height)


def skeleton_edges() -> List[Tuple[str, str]]:
    """回傳小人骨架連線，供非 SVG 繪製使用。"""
    return list(_EDGES)


def stick_figure_svg(
    angle_series: Dict[str, list],
    duration_s: float = 4.0,
    width: int = 260,
    height: int = 340,
    color: str = "#ffffff",
    bg: str = "#0a84ff",
    accent_joints: Iterable[str] = (),
    accent_color: str = "#ffd60a",
) -> str:
    """產生帶 SMIL 動畫的 SVG。

    accent_joints: 要高亮（脈動黃色）的關節名（例如 ["左肩","右肩"]），
                   讓使用者一眼看出該動作的主要部位。
    """
    frames = _subsample_angles(angle_series, n=28)
    if not frames:
        return ""

    poses = [_pose(f, width, height) for f in frames]
    lines: List[str] = []
    for a, b in _EDGES:
        if a not in poses[0] or b not in poses[0]:
            continue
        x1s = [p[a][0] for p in poses]
        y1s = [p[a][1] for p in poses]
        x2s = [p[b][0] for p in poses]
        y2s = [p[b][1] for p in poses]
        lines.append(
            f'<line stroke="{color}" stroke-width="6" '
            f'stroke-linecap="round" '
            f'x1="{x1s[0]:.1f}" y1="{y1s[0]:.1f}" '
            f'x2="{x2s[0]:.1f}" y2="{y2s[0]:.1f}">'
            f'{_animate_block("x1", x1s, duration_s)}'
            f'{_animate_block("y1", y1s, duration_s)}'
            f'{_animate_block("x2", x2s, duration_s)}'
            f'{_animate_block("y2", y2s, duration_s)}'
            f'</line>'
        )

    head_xs = [p["head"][0] for p in poses]
    head_ys = [p["head"][1] for p in poses]
    head_circle = (
        f'<circle r="14" fill="{color}" '
        f'cx="{head_xs[0]:.1f}" cy="{head_ys[0]:.1f}">'
        f'{_animate_block("cx", head_xs, duration_s)}'
        f'{_animate_block("cy", head_ys, duration_s)}'
        f'</circle>'
    )

    eye_offset_x, eye_offset_y = 4.5, -3.0
    left_eye = (
        f'<circle r="3.5" fill="{bg}" '
        f'cx="{head_xs[0]-eye_offset_x:.1f}" cy="{head_ys[0]+eye_offset_y:.1f}">'
        f'{_animate_block("cx", [x - eye_offset_x for x in head_xs], duration_s)}'
        f'{_animate_block("cy", [y + eye_offset_y for y in head_ys], duration_s)}'
        f'</circle>'
    )
    right_eye = (
        f'<circle r="3.5" fill="{bg}" '
        f'cx="{head_xs[0]+eye_offset_x:.1f}" cy="{head_ys[0]+eye_offset_y:.1f}">'
        f'{_animate_block("cx", [x + eye_offset_x for x in head_xs], duration_s)}'
        f'{_animate_block("cy", [y + eye_offset_y for y in head_ys], duration_s)}'
        f'</circle>'
    )
    eye_dots = left_eye + right_eye

    # 關節點（小白圓）
    joint_keys = [k for k in poses[0] if k != "head"]
    joint_circles: List[str] = []
    for jk in joint_keys:
        cxs = [p[jk][0] for p in poses]
        cys = [p[jk][1] for p in poses]
        joint_circles.append(
            f'<circle r="4" fill="{color}" opacity="0.85" '
            f'cx="{cxs[0]:.1f}" cy="{cys[0]:.1f}">'
            f'{_animate_block("cx", cxs, duration_s)}'
            f'{_animate_block("cy", cys, duration_s)}'
            f'</circle>'
        )

    # 強調點（黃色脈動圓）
    accent_dots: List[str] = []
    accent_map = {
        "左肩": "L_shoulder", "右肩": "R_shoulder",
        "左肘": "L_elbow", "右肘": "R_elbow",
        "左髖": "L_hip", "右髖": "R_hip",
        "左膝": "L_knee", "右膝": "R_knee",
    }
    for jn in accent_joints:
        key = accent_map.get(jn)
        if key is None:
            continue
        cxs = [p[key][0] for p in poses]
        cys = [p[key][1] for p in poses]
        accent_dots.append(
            f'<circle r="9" fill="{accent_color}" opacity="0.9" '
            f'cx="{cxs[0]:.1f}" cy="{cys[0]:.1f}">'
            f'{_animate_block("cx", cxs, duration_s)}'
            f'{_animate_block("cy", cys, duration_s)}'
            f'<animate attributeName="r" values="7;12;7" '
            f'dur="1.4s" repeatCount="indefinite"/>'
            f'</circle>'
        )

    ground_shadow = (
        f'<ellipse cx="{width/2:.1f}" cy="{height*0.85:.1f}" '
        f'rx="{width*0.22:.1f}" ry="{height*0.025:.1f}" '
        f'fill="rgba(0,0,0,0.18)" opacity="0.7"/>'
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="exercise demo">'
        f'<defs>'
        f'  <radialGradient id="bg-grad" cx="50%" cy="42%" r="62%">'
        f'    <stop offset="0%" stop-color="{bg}" stop-opacity="0.92"/>'
        f'    <stop offset="100%" stop-color="{bg}" stop-opacity="1"/>'
        f'  </radialGradient>'
        f'  <radialGradient id="glow-grad" cx="50%" cy="42%" r="50%">'
        f'    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.10"/>'
        f'    <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>'
        f'  </radialGradient>'
        f'</defs>'
        f'<rect width="100%" height="100%" fill="url(#bg-grad)" rx="22"/>'
        f'<rect width="100%" height="100%" fill="url(#glow-grad)" rx="22"/>'
        f'{ground_shadow}'
        f'{"".join(lines)}'
        f'{"".join(joint_circles)}'
        f'{head_circle}'
        f'{eye_dots}'
        f'{"".join(accent_dots)}'
        f'</svg>'
    )


def primary_joints_for(template: dict) -> List[str]:
    """猜測該範本的主要動作關節（用於 accent_joints 高亮）。"""
    series = template.get("angle_series", {})
    if not series:
        return []
    # 用變異數最大的前兩個關節
    variances = [(k, float(np.var(v))) for k, v in series.items()]
    variances.sort(key=lambda x: -x[1])
    return [k for k, _ in variances[:2]]
