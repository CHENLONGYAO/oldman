"""
Joint heatmap visualization: shows accuracy per joint over a session.

Renders a body silhouette with color-coded joints based on:
- ROM violations (red = frequent violations)
- Deviation from target (yellow = needs work, green = good)
- Activity intensity (more saturated = more movement)
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go
import streamlit as st


# Joint positions in normalized 2D body silhouette coordinates
# Origin: 0,0 = top-left of figure, 1,1 = bottom-right
BODY_LAYOUT = {
    "head": (0.5, 0.05),
    "left_shoulder": (0.35, 0.18),
    "right_shoulder": (0.65, 0.18),
    "left_elbow": (0.25, 0.32),
    "right_elbow": (0.75, 0.32),
    "left_wrist": (0.20, 0.45),
    "right_wrist": (0.80, 0.45),
    "torso": (0.5, 0.35),
    "left_hip": (0.42, 0.55),
    "right_hip": (0.58, 0.55),
    "left_knee": (0.40, 0.72),
    "right_knee": (0.60, 0.72),
    "left_ankle": (0.38, 0.92),
    "right_ankle": (0.62, 0.92),
}

JOINT_TO_ANGLES = {
    "left_shoulder": ["left_shoulder_flex_ext", "left_shoulder_abd_add"],
    "right_shoulder": ["right_shoulder_flex_ext", "right_shoulder_abd_add"],
    "left_elbow": ["left_elbow_flex"],
    "right_elbow": ["right_elbow_flex"],
    "left_hip": ["left_hip_flex_ext", "left_hip_abd_add"],
    "right_hip": ["right_hip_flex_ext", "right_hip_abd_add"],
    "left_knee": ["left_knee_flex"],
    "right_knee": ["right_knee_flex"],
    "torso": ["trunk_forward_bend", "trunk_lateral_lean"],
}


def compute_joint_scores(history: List, target_ranges: Optional[Dict] = None
                         ) -> Dict[str, Dict]:
    """Compute per-joint score from history of LiveState.

    Returns dict: {joint_name: {"score": 0-100, "violations": int,
                                 "activity": float}}
    """
    scores: Dict[str, Dict] = {}

    for joint, angle_keys in JOINT_TO_ANGLES.items():
        all_vals: List[float] = []
        violations = 0
        for state in history:
            for ak in angle_keys:
                v = state.angles_smoothed.get(ak)
                if v is not None:
                    all_vals.append(v)
            for rom in state.rom_violations:
                if any(rom.angle_name == ak for ak in angle_keys):
                    violations += 1

        if not all_vals:
            scores[joint] = {"score": 0, "violations": 0, "activity": 0}
            continue

        arr = np.array(all_vals)
        activity = float(np.std(arr))

        if target_ranges and joint in target_ranges:
            tmin, tmax = target_ranges[joint]
            in_range = ((arr >= tmin) & (arr <= tmax)).mean()
            score = float(in_range * 100)
        else:
            penalty = min(100, violations * 5)
            score = max(0, 100 - penalty)

        scores[joint] = {
            "score": round(score, 1),
            "violations": violations,
            "activity": round(activity, 1),
        }

    return scores


def render_joint_heatmap(history: List,
                          target_ranges: Optional[Dict] = None,
                          lang: str = "zh") -> None:
    """Render interactive Plotly heatmap on body silhouette."""
    scores = compute_joint_scores(history, target_ranges)

    fig = go.Figure()

    fig.add_shape(
        type="circle",
        x0=BODY_LAYOUT["head"][0] - 0.06,
        y0=BODY_LAYOUT["head"][1] - 0.06,
        x1=BODY_LAYOUT["head"][0] + 0.06,
        y1=BODY_LAYOUT["head"][1] + 0.06,
        fillcolor="#e9ecef",
        line=dict(color="#adb5bd", width=2),
    )

    body_lines = [
        ("head", "torso"),
        ("torso", "left_shoulder"),
        ("torso", "right_shoulder"),
        ("left_shoulder", "left_elbow"),
        ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"),
        ("right_elbow", "right_wrist"),
        ("torso", "left_hip"),
        ("torso", "right_hip"),
        ("left_hip", "left_knee"),
        ("left_knee", "left_ankle"),
        ("right_hip", "right_knee"),
        ("right_knee", "right_ankle"),
    ]

    line_x: List[Optional[float]] = []
    line_y: List[Optional[float]] = []
    for a, b in body_lines:
        line_x.extend([BODY_LAYOUT[a][0], BODY_LAYOUT[b][0], None])
        line_y.extend([BODY_LAYOUT[a][1], BODY_LAYOUT[b][1], None])

    fig.add_trace(go.Scatter(
        x=line_x, y=line_y,
        mode="lines",
        line=dict(color="#adb5bd", width=8),
        hoverinfo="skip",
        showlegend=False,
    ))

    xs, ys, colors, sizes, texts = [], [], [], [], []
    for joint, info in scores.items():
        if joint not in BODY_LAYOUT:
            continue
        x, y = BODY_LAYOUT[joint]
        xs.append(x)
        ys.append(y)
        colors.append(info["score"])
        sizes.append(20 + info["activity"] * 0.5)

        joint_label = _joint_label(joint, lang)
        texts.append(
            f"{joint_label}<br>"
            f"{'分數' if lang == 'zh' else 'Score'}: {info['score']}<br>"
            f"{'違規' if lang == 'zh' else 'Violations'}: {info['violations']}<br>"
            f"{'活動量' if lang == 'zh' else 'Activity'}: {info['activity']:.1f}°"
        )

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers",
        marker=dict(
            size=sizes,
            color=colors,
            colorscale=[
                [0.0, "#ff3b30"],
                [0.5, "#ffcc00"],
                [1.0, "#34c759"],
            ],
            cmin=0, cmax=100,
            showscale=True,
            colorbar=dict(
                title=("分數" if lang == "zh" else "Score"),
                tickvals=[0, 50, 100],
            ),
            line=dict(color="white", width=2),
        ),
        text=texts,
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        xaxis=dict(visible=False, range=[0, 1]),
        yaxis=dict(visible=False, range=[1, 0], scaleanchor="x"),
        height=500,
        margin=dict(l=20, r=20, t=20, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    st.plotly_chart(fig, use_container_width=True)

    weak_joints = [(j, s) for j, s in scores.items()
                   if s["score"] < 60 and s["activity"] > 1]
    if weak_joints:
        st.warning(
            "⚠️ " + ("需加強" if lang == "zh" else "Needs attention") + ":"
        )
        for j, s in weak_joints:
            st.markdown(
                f"- **{_joint_label(j, lang)}**: "
                f"{s['score']:.0f}/100 "
                f"({s['violations']} {'次違規' if lang == 'zh' else 'violations'})"
            )


def _joint_label(joint: str, lang: str) -> str:
    labels_zh = {
        "head": "頭部", "torso": "軀幹",
        "left_shoulder": "左肩", "right_shoulder": "右肩",
        "left_elbow": "左肘", "right_elbow": "右肘",
        "left_wrist": "左腕", "right_wrist": "右腕",
        "left_hip": "左髖", "right_hip": "右髖",
        "left_knee": "左膝", "right_knee": "右膝",
        "left_ankle": "左踝", "right_ankle": "右踝",
    }
    if lang == "zh":
        return labels_zh.get(joint, joint)
    return joint.replace("_", " ").title()
