"""
Frame-level form critic: identify the worst frames and explain why.

Uses cross-attention-style scoring between patient and template:
1. DTW align patient angle series to template
2. Per aligned frame, compute weighted angle deviation
3. Identify frames with deviation > threshold
4. Group consecutive bad frames into "form errors"
5. For each error, identify the dominant offending joint(s)
6. Translate to natural language feedback in the user's language

Outputs are designed for clinical-quality feedback ("at frame 47, your
left knee is 18° more flexed than the reference; this could indicate
quad weakness").
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from biomechanics import compute_anatomical_angles


@dataclass
class FormError:
    """A detected form deviation spanning one or more frames."""
    start_frame: int
    end_frame: int
    primary_joint: str
    deviation_deg: float
    severity: str  # "minor", "moderate", "major"
    direction: str  # "more_flexed", "less_flexed", "asymmetric"
    timestamp_s: float
    cause_hint: Optional[str] = None
    feedback_zh: str = ""
    feedback_en: str = ""


@dataclass
class FormReport:
    overall_score: float
    errors: List[FormError] = field(default_factory=list)
    summary_zh: str = ""
    summary_en: str = ""
    top_concerns: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)


def critique_session(patient_seq: np.ndarray,
                      template_seq: np.ndarray,
                      fps: float = 30.0,
                      severity_thresholds: Optional[Dict[str, float]] = None
                      ) -> FormReport:
    """Generate frame-level critique comparing patient to template.

    patient_seq, template_seq: (T, 33, 3) world landmark sequences
    """
    if severity_thresholds is None:
        severity_thresholds = {"minor": 8.0, "moderate": 15.0, "major": 25.0}

    p_angles = _angle_series(patient_seq)
    t_angles = _angle_series(template_seq)

    if not p_angles or not t_angles:
        return FormReport(overall_score=0.0,
                         summary_zh="無法分析",
                         summary_en="Could not analyze")

    aligned_pairs = _dtw_align(p_angles, t_angles)

    deviations: Dict[str, np.ndarray] = {}
    common_joints = set(p_angles) & set(t_angles)

    for joint in common_joints:
        p_ser = p_angles[joint]
        t_ser = t_angles[joint]
        diffs = []
        for p_idx, t_idx in aligned_pairs:
            if p_idx < len(p_ser) and t_idx < len(t_ser):
                diffs.append(p_ser[p_idx] - t_ser[t_idx])
        if diffs:
            deviations[joint] = np.array(diffs)

    if not deviations:
        return FormReport(overall_score=50.0)

    errors = _find_error_segments(deviations, fps, severity_thresholds)
    overall = _compute_overall_score(deviations, severity_thresholds)
    top_concerns, strengths = _identify_concerns(deviations,
                                                  severity_thresholds)

    summary_zh, summary_en = _generate_summary(overall, top_concerns,
                                                strengths, errors)

    for err in errors:
        err.feedback_zh = _feedback_text(err, "zh")
        err.feedback_en = _feedback_text(err, "en")

    return FormReport(
        overall_score=overall,
        errors=errors,
        summary_zh=summary_zh,
        summary_en=summary_en,
        top_concerns=top_concerns,
        strengths=strengths,
    )


def _angle_series(seq: np.ndarray) -> Dict[str, np.ndarray]:
    """Compute angle time series from landmark sequence."""
    per_frame = []
    for frame in seq:
        try:
            per_frame.append(compute_anatomical_angles(frame))
        except Exception:
            per_frame.append({})

    if not per_frame:
        return {}

    keys = sorted({k for d in per_frame if d for k in d})
    out = {}
    for k in keys:
        arr = np.array([d.get(k, np.nan) for d in per_frame])
        if np.isnan(arr).all():
            continue
        if np.isnan(arr).any():
            mask = ~np.isnan(arr)
            arr = np.interp(np.arange(len(arr)),
                           np.where(mask)[0], arr[mask])
        out[k] = arr
    return out


def _dtw_align(p_angles: Dict[str, np.ndarray],
                t_angles: Dict[str, np.ndarray]) -> List[Tuple[int, int]]:
    """DTW alignment using stacked angle features."""
    common = sorted(set(p_angles) & set(t_angles))
    if not common:
        return []

    p_min = min(len(p_angles[k]) for k in common)
    t_min = min(len(t_angles[k]) for k in common)

    p_stack = np.stack([p_angles[k][:p_min] for k in common], axis=1)
    t_stack = np.stack([t_angles[k][:t_min] for k in common], axis=1)

    return _dtw_path(p_stack, t_stack)


def _dtw_path(P: np.ndarray, T: np.ndarray) -> List[Tuple[int, int]]:
    """Compute DTW warp path with constant-band radius."""
    n, m = len(P), len(T)
    if n == 0 or m == 0:
        return []

    radius = max(20, int(0.2 * max(n, m)))

    INF = float("inf")
    cost = np.full((n + 1, m + 1), INF, dtype=np.float64)
    cost[0, 0] = 0

    for i in range(1, n + 1):
        j_lo = max(1, i - radius)
        j_hi = min(m, i + radius)
        for j in range(j_lo, j_hi + 1):
            d = float(np.linalg.norm(P[i - 1] - T[j - 1]))
            cost[i, j] = d + min(cost[i - 1, j], cost[i, j - 1],
                                 cost[i - 1, j - 1])

    path: List[Tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        opts = [
            (cost[i - 1, j - 1], i - 1, j - 1),
            (cost[i - 1, j], i - 1, j),
            (cost[i, j - 1], i, j - 1),
        ]
        opts.sort()
        i, j = opts[0][1], opts[0][2]

    return list(reversed(path))


def _find_error_segments(deviations: Dict[str, np.ndarray],
                          fps: float,
                          thresholds: Dict[str, float]) -> List[FormError]:
    """Identify contiguous frames where deviation exceeds threshold."""
    errors: List[FormError] = []

    for joint, dev in deviations.items():
        abs_dev = np.abs(dev)
        bad_mask = abs_dev > thresholds["minor"]
        if not bad_mask.any():
            continue

        in_segment = False
        start = 0
        for i, is_bad in enumerate(bad_mask):
            if is_bad and not in_segment:
                start = i
                in_segment = True
            elif not is_bad and in_segment:
                end = i - 1
                segment_dev = dev[start:end + 1]
                err = _build_error(joint, start, end, segment_dev,
                                   thresholds, fps)
                if err:
                    errors.append(err)
                in_segment = False

        if in_segment:
            end = len(bad_mask) - 1
            segment_dev = dev[start:end + 1]
            err = _build_error(joint, start, end, segment_dev,
                               thresholds, fps)
            if err:
                errors.append(err)

    errors.sort(key=lambda e: -e.deviation_deg)
    return errors[:10]


def _build_error(joint: str, start: int, end: int,
                  segment_dev: np.ndarray,
                  thresholds: Dict[str, float],
                  fps: float) -> Optional[FormError]:
    if len(segment_dev) < 2:
        return None

    peak_idx = int(np.argmax(np.abs(segment_dev)))
    peak_dev = float(segment_dev[peak_idx])
    abs_peak = abs(peak_dev)

    if abs_peak < thresholds["minor"]:
        return None

    if abs_peak >= thresholds["major"]:
        sev = "major"
    elif abs_peak >= thresholds["moderate"]:
        sev = "moderate"
    else:
        sev = "minor"

    direction = "more_flexed" if peak_dev > 0 else "less_flexed"

    return FormError(
        start_frame=start,
        end_frame=end,
        primary_joint=joint,
        deviation_deg=peak_dev,
        severity=sev,
        direction=direction,
        timestamp_s=(start + peak_idx) / fps,
        cause_hint=_cause_hint(joint, direction, sev),
    )


def _cause_hint(joint: str, direction: str, severity: str) -> str:
    """Heuristic explanation for common deviation patterns."""
    if "knee" in joint and direction == "more_flexed":
        return "quad_weakness_or_pain"
    if "knee" in joint and direction == "less_flexed":
        return "limited_rom_or_caution"
    if "shoulder" in joint and direction == "less_flexed":
        return "shoulder_impingement_or_weakness"
    if "hip" in joint and direction == "less_flexed":
        return "hip_flexor_tightness"
    if "trunk" in joint:
        return "compensation_pattern"
    return "form_drift"


def _compute_overall_score(deviations: Dict[str, np.ndarray],
                            thresholds: Dict[str, float]) -> float:
    if not deviations:
        return 0.0

    all_devs = np.concatenate([np.abs(d) for d in deviations.values()])
    mean_dev = float(np.mean(all_devs))
    score = 100.0 - mean_dev * 1.5
    return float(np.clip(score, 0, 100))


def _identify_concerns(deviations: Dict[str, np.ndarray],
                        thresholds: Dict[str, float]
                        ) -> Tuple[List[str], List[str]]:
    """Top problematic joints and joints performing well."""
    joint_scores = []
    for joint, dev in deviations.items():
        mean_abs = float(np.mean(np.abs(dev)))
        joint_scores.append((joint, mean_abs))

    joint_scores.sort(key=lambda x: -x[1])

    concerns = [j for j, s in joint_scores
                if s > thresholds["moderate"]][:3]
    strengths = [j for j, s in joint_scores
                if s < thresholds["minor"] / 2][:3]

    return concerns, strengths


def _generate_summary(score: float, concerns: List[str],
                       strengths: List[str],
                       errors: List[FormError]) -> Tuple[str, str]:
    """Bilingual summary."""
    n_major = sum(1 for e in errors if e.severity == "major")
    n_mod = sum(1 for e in errors if e.severity == "moderate")

    if score >= 90:
        zh_grade = "優秀"
        en_grade = "Excellent"
    elif score >= 75:
        zh_grade = "良好"
        en_grade = "Good"
    elif score >= 60:
        zh_grade = "尚可"
        en_grade = "Fair"
    else:
        zh_grade = "需加強"
        en_grade = "Needs Work"

    zh_parts = [f"整體評估：{zh_grade}（{score:.1f} 分）"]
    en_parts = [f"Overall: {en_grade} ({score:.1f})"]

    if n_major > 0:
        zh_parts.append(f"發現 {n_major} 處明顯偏差")
        en_parts.append(f"{n_major} major form issues")
    if n_mod > 0:
        zh_parts.append(f"{n_mod} 處中度偏差")
        en_parts.append(f"{n_mod} moderate deviations")
    if concerns:
        zh_parts.append(f"主要關注：{', '.join(concerns[:2])}")
        en_parts.append(f"Focus areas: {', '.join(concerns[:2])}")
    if strengths:
        zh_parts.append(f"穩定關節：{', '.join(strengths[:2])}")
        en_parts.append(f"Stable: {', '.join(strengths[:2])}")

    return "；".join(zh_parts), ". ".join(en_parts)


def _feedback_text(err: FormError, lang: str) -> str:
    """Natural-language feedback for a single error."""
    joint_zh = {
        "left_knee_flex": "左膝", "right_knee_flex": "右膝",
        "left_elbow_flex": "左肘", "right_elbow_flex": "右肘",
        "left_shoulder_flex_ext": "左肩前舉",
        "right_shoulder_flex_ext": "右肩前舉",
        "left_shoulder_abd_add": "左肩外展",
        "right_shoulder_abd_add": "右肩外展",
        "left_hip_flex_ext": "左髖前屈",
        "right_hip_flex_ext": "右髖前屈",
        "trunk_forward_bend": "軀幹前傾",
    }
    joint_en = {k: k.replace("_", " ").title() for k in joint_zh}

    sev_zh = {"minor": "輕微", "moderate": "中度", "major": "明顯"}
    sev_en = {"minor": "minor", "moderate": "moderate", "major": "major"}
    dir_zh = {"more_flexed": "屈曲過度",
              "less_flexed": "伸展不足",
              "asymmetric": "不對稱"}
    dir_en = {"more_flexed": "over-flexed",
              "less_flexed": "under-extended",
              "asymmetric": "asymmetric"}

    if lang == "zh":
        joint_label = joint_zh.get(err.primary_joint, err.primary_joint)
        return (f"在第 {err.timestamp_s:.1f} 秒，{joint_label}"
                f"{sev_zh[err.severity]}{dir_zh[err.direction]}"
                f"（偏差 {abs(err.deviation_deg):.1f}°）")
    else:
        joint_label = joint_en.get(err.primary_joint, err.primary_joint)
        return (f"At {err.timestamp_s:.1f}s, {joint_label} is "
                f"{sev_en[err.severity]} {dir_en[err.direction]} "
                f"(by {abs(err.deviation_deg):.1f}°)")
