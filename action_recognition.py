"""
Action recognition: classify exercise type from joint angle sequences.

Two-tier classifier:
1. Fast path: angle-feature heuristic with confidence score
2. Accurate path: DTW nearest-neighbor against template library

Falls back gracefully if torch is missing. Returns:
- predicted exercise key
- confidence (0-1)
- top-3 candidates with scores

Used by Auto Exercise mode so users don't need to pick from menu.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from biomechanics import compute_anatomical_angles


@dataclass
class ActionPrediction:
    exercise: str
    confidence: float
    top_k: List[Tuple[str, float]]
    rep_count: int
    duration_s: float


# ============================================================
# Heuristic feature extractor
# ============================================================
def extract_session_features(world_seq: np.ndarray, fps: float) -> Dict[str, float]:
    """Extract scalar features from a session for classification.

    world_seq: (T, 33, 3) MediaPipe world landmarks across frames.
    Returns dict of motion features.
    """
    if len(world_seq) < 5:
        return {}

    angles_per_frame = []
    for frame in world_seq:
        try:
            a = compute_anatomical_angles(frame)
            angles_per_frame.append(a)
        except Exception:
            continue

    if not angles_per_frame:
        return {}

    keys = sorted({k for d in angles_per_frame for k in d})
    angles = {}
    for k in keys:
        vals = [d.get(k, 0.0) for d in angles_per_frame]
        angles[k] = np.array(vals)

    feats = {}
    for k, arr in angles.items():
        feats[f"{k}_range"] = float(arr.max() - arr.min())
        feats[f"{k}_std"] = float(arr.std())
        feats[f"{k}_mean"] = float(arr.mean())
        feats[f"{k}_max"] = float(arr.max())
        feats[f"{k}_min"] = float(arr.min())

    feats["duration_s"] = len(world_seq) / max(fps, 1.0)
    feats["fps"] = fps

    hip_height = world_seq[:, 23, 1].mean()
    knee_height = world_seq[:, 25, 1].mean()
    feats["vertical_motion"] = float(world_seq[:, 0, 1].max() - world_seq[:, 0, 1].min())
    feats["lateral_motion"] = float(world_seq[:, 0, 0].max() - world_seq[:, 0, 0].min())
    feats["hip_knee_offset"] = float(hip_height - knee_height)

    return feats


# ============================================================
# Rule-based classifier
# Each exercise has a "fingerprint" of distinguishing features.
# ============================================================
EXERCISE_RULES = {
    "arm_raise": {
        "primary_angle": "left_shoulder_flex_ext",
        "primary_range_min": 90,
        "secondary_angle": "right_shoulder_flex_ext",
        "secondary_range_min": 90,
        "vertical_motion_max": 0.15,
        "needs_legs": False,
    },
    "shoulder_abduction": {
        "primary_angle": "left_shoulder_abd_add",
        "primary_range_min": 80,
        "secondary_angle": "right_shoulder_abd_add",
        "secondary_range_min": 80,
        "vertical_motion_max": 0.15,
        "needs_legs": False,
    },
    "elbow_flexion": {
        "primary_angle": "left_elbow_flex",
        "primary_range_min": 80,
        "secondary_angle": "right_elbow_flex",
        "secondary_range_min": 80,
        "shoulder_range_max": 30,
        "vertical_motion_max": 0.10,
        "needs_legs": False,
    },
    "knee_extension": {
        "primary_angle": "left_knee_flex",
        "primary_range_min": 60,
        "secondary_angle": "right_knee_flex",
        "secondary_range_min": 0,
        "vertical_motion_max": 0.20,
        "needs_legs": True,
    },
    "mini_squat": {
        "primary_angle": "left_knee_flex",
        "primary_range_min": 30,
        "secondary_angle": "right_knee_flex",
        "secondary_range_min": 30,
        "vertical_motion_min": 0.10,
        "needs_legs": True,
    },
    "sit_to_stand": {
        "primary_angle": "left_knee_flex",
        "primary_range_min": 60,
        "secondary_angle": "left_hip_flex_ext",
        "secondary_range_min": 60,
        "vertical_motion_min": 0.25,
        "needs_legs": True,
    },
    "march_in_place": {
        "primary_angle": "left_hip_flex_ext",
        "primary_range_min": 40,
        "secondary_angle": "right_hip_flex_ext",
        "secondary_range_min": 40,
        "vertical_motion_max": 0.20,
        "needs_legs": True,
    },
    "hip_abduction": {
        "primary_angle": "left_hip_abd_add",
        "primary_range_min": 25,
        "secondary_angle": "right_hip_abd_add",
        "secondary_range_min": 0,
        "vertical_motion_max": 0.10,
        "needs_legs": True,
    },
}


def _score_rule(feats: Dict[str, float], rule: Dict) -> float:
    """Score how well features match a rule (0-1)."""
    if not feats:
        return 0.0

    score = 0.0
    weight_sum = 0.0

    p_key = rule["primary_angle"] + "_range"
    p_val = feats.get(p_key, 0)
    p_min = rule["primary_range_min"]
    if p_min > 0:
        s = min(1.0, p_val / max(p_min, 1.0))
        score += s * 3.0
        weight_sum += 3.0

    s_key = rule["secondary_angle"] + "_range"
    s_val = feats.get(s_key, 0)
    s_min = rule.get("secondary_range_min", 0)
    if s_min > 0:
        s = min(1.0, s_val / max(s_min, 1.0))
        score += s * 1.5
        weight_sum += 1.5

    if "shoulder_range_max" in rule:
        sh = max(
            feats.get("left_shoulder_flex_ext_range", 0),
            feats.get("right_shoulder_flex_ext_range", 0),
        )
        s = 1.0 if sh < rule["shoulder_range_max"] else 0.5
        score += s
        weight_sum += 1.0

    vmotion = feats.get("vertical_motion", 0)
    if "vertical_motion_min" in rule:
        s = 1.0 if vmotion >= rule["vertical_motion_min"] else 0.4
        score += s
        weight_sum += 1.0
    if "vertical_motion_max" in rule:
        s = 1.0 if vmotion <= rule["vertical_motion_max"] else 0.4
        score += s
        weight_sum += 1.0

    return score / weight_sum if weight_sum > 0 else 0.0


# ============================================================
# DTW-based nearest-neighbor classifier (more accurate)
# ============================================================
def classify_by_dtw(world_seq: np.ndarray,
                     templates: Dict[str, np.ndarray]) -> Tuple[str, float, List[Tuple[str, float]]]:
    """Classify using DTW distance to template angle series.

    templates: {exercise_key: (T, K) reference angle series}
    """
    try:
        from scoring import sequence_to_angle_series, dtw_vec
    except ImportError:
        return "unknown", 0.0, []

    try:
        patient_series = sequence_to_angle_series(world_seq)
    except Exception:
        return "unknown", 0.0, []

    if not patient_series:
        return "unknown", 0.0, []

    p_arr = _stack_series(patient_series)
    if p_arr.size == 0:
        return "unknown", 0.0, []

    distances: List[Tuple[str, float]] = []
    for ex_key, template_arr in templates.items():
        try:
            cost, _ = dtw_vec(p_arr, template_arr)
        except Exception:
            continue
        distances.append((ex_key, float(cost)))

    if not distances:
        return "unknown", 0.0, []

    distances.sort(key=lambda x: x[1])

    best_dist = distances[0][1]
    second_dist = distances[1][1] if len(distances) > 1 else best_dist * 2
    margin = (second_dist - best_dist) / max(second_dist, 1e-6)
    confidence = float(np.clip(margin * 2.0, 0.0, 1.0))

    top_k = [(k, _dist_to_score(d, best_dist)) for k, d in distances[:3]]
    return distances[0][0], confidence, top_k


def _stack_series(series: Dict[str, np.ndarray]) -> np.ndarray:
    """Stack joint series into (T, K) array."""
    arrays = list(series.values())
    if not arrays:
        return np.array([])
    min_len = min(len(a) for a in arrays)
    return np.stack([a[:min_len] for a in arrays], axis=1)


def _dist_to_score(dist: float, best: float) -> float:
    """Convert DTW distance to a 0-1 similarity score."""
    if best < 1e-6:
        return 1.0
    return float(np.clip(best / dist, 0.0, 1.0))


# ============================================================
# Public API
# ============================================================
def classify(world_seq: np.ndarray, fps: float,
              templates: Optional[Dict[str, np.ndarray]] = None) -> ActionPrediction:
    """Auto-classify exercise from a session sequence."""
    feats = extract_session_features(world_seq, fps)

    rule_scores: List[Tuple[str, float]] = []
    for ex_key, rule in EXERCISE_RULES.items():
        score = _score_rule(feats, rule)
        rule_scores.append((ex_key, score))
    rule_scores.sort(key=lambda x: -x[1])

    best_rule = rule_scores[0] if rule_scores else ("unknown", 0.0)

    if templates:
        dtw_pred, dtw_conf, dtw_top = classify_by_dtw(world_seq, templates)
        if dtw_conf > 0.4 and dtw_conf > best_rule[1]:
            return ActionPrediction(
                exercise=dtw_pred,
                confidence=dtw_conf,
                top_k=dtw_top,
                rep_count=_count_reps(feats),
                duration_s=feats.get("duration_s", 0),
            )

    return ActionPrediction(
        exercise=best_rule[0],
        confidence=float(best_rule[1]),
        top_k=[(k, s) for k, s in rule_scores[:3]],
        rep_count=_count_reps(feats),
        duration_s=feats.get("duration_s", 0),
    )


def _count_reps(feats: Dict[str, float]) -> int:
    """Rough rep count from primary motion magnitude."""
    if not feats:
        return 0
    duration = feats.get("duration_s", 0)
    if duration <= 0:
        return 0

    cycle_s = 3.0
    return max(0, int(duration / cycle_s))
