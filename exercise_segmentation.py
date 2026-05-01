"""
Exercise segmentation: auto-detect rep boundaries from joint angle stream.

Algorithm:
1. Identify dominant joint (largest range of motion)
2. Compute its angle time series via biomechanics
3. Smooth with Savitzky-Golay
4. Find peaks (extension) and troughs (flexion)
5. Build (start, peak, end) tuples representing each rep
6. Validate via biomechanical plausibility (min duration, min amplitude)

Returns rep boundaries as frame indices for downstream scoring.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

from biomechanics import compute_anatomical_angles
from angle_filters import savitzky_golay


@dataclass
class Rep:
    start_frame: int
    peak_frame: int
    end_frame: int
    amplitude_deg: float
    duration_s: float
    quality: float


@dataclass
class SegmentationResult:
    dominant_joint: str
    reps: List[Rep]
    total_reps: int
    avg_duration: float
    avg_amplitude: float
    consistency_score: float
    angle_series: np.ndarray


def segment_session(world_seq: np.ndarray, fps: float,
                     min_amplitude_deg: float = 15.0,
                     min_rep_duration_s: float = 0.5) -> SegmentationResult:
    """Detect reps from a continuous pose sequence."""
    if len(world_seq) < 10:
        return _empty_result()

    angle_traces = _build_angle_traces(world_seq)
    if not angle_traces:
        return _empty_result()

    dominant, dom_series = _pick_dominant_joint(angle_traces)
    if dom_series is None:
        return _empty_result()

    smoothed = savitzky_golay(dom_series, window=min(15, len(dom_series) | 1))

    reps = _detect_reps(smoothed, fps, min_amplitude_deg, min_rep_duration_s)
    consistency = _consistency_score(reps)

    return SegmentationResult(
        dominant_joint=dominant,
        reps=reps,
        total_reps=len(reps),
        avg_duration=(
            float(np.mean([r.duration_s for r in reps]))
            if reps else 0.0
        ),
        avg_amplitude=(
            float(np.mean([r.amplitude_deg for r in reps]))
            if reps else 0.0
        ),
        consistency_score=consistency,
        angle_series=smoothed,
    )


def _build_angle_traces(world_seq: np.ndarray) -> dict:
    """Compute anatomical angles for each frame, return per-joint arrays."""
    per_frame = []
    for frame in world_seq:
        try:
            per_frame.append(compute_anatomical_angles(frame))
        except Exception:
            per_frame.append({})

    if not per_frame:
        return {}

    keys = sorted({k for d in per_frame if d for k in d})
    traces = {}
    for k in keys:
        vals = [d.get(k, np.nan) for d in per_frame]
        arr = np.array(vals, dtype=np.float64)
        if np.isnan(arr).all():
            continue
        if np.isnan(arr).any():
            mask = ~np.isnan(arr)
            arr = np.interp(np.arange(len(arr)),
                           np.where(mask)[0], arr[mask])
        traces[k] = arr
    return traces


def _pick_dominant_joint(traces: dict) -> Tuple[str, Optional[np.ndarray]]:
    """Pick joint with largest range of motion."""
    if not traces:
        return "", None

    best_key = ""
    best_range = 0.0
    best_arr = None
    for k, arr in traces.items():
        rng = float(arr.max() - arr.min())
        if rng > best_range:
            best_range = rng
            best_key = k
            best_arr = arr
    return best_key, best_arr


def _detect_reps(series: np.ndarray, fps: float,
                  min_amplitude: float,
                  min_duration_s: float) -> List[Rep]:
    """Find reps using peak/trough detection on smoothed series."""
    if len(series) < 8:
        return []

    rng = float(series.max() - series.min())
    if rng < min_amplitude:
        return []

    peaks = _find_extrema(series, find_max=True, prominence=rng * 0.3)
    troughs = _find_extrema(series, find_max=False, prominence=rng * 0.3)

    if len(peaks) < 1 or len(troughs) < 1:
        return []

    extrema = sorted(
        [(p, "peak") for p in peaks] + [(t, "trough") for t in troughs]
    )

    reps: List[Rep] = []
    min_frames = int(min_duration_s * fps)

    for i in range(len(extrema) - 2):
        e0, t0 = extrema[i]
        e1, t1 = extrema[i + 1]
        e2, t2 = extrema[i + 2]
        if t0 == t2 and t0 != t1:
            duration_frames = e2 - e0
            if duration_frames < min_frames:
                continue
            amplitude = abs(series[e1] - series[e0])
            if amplitude < min_amplitude:
                continue

            rep_segment = series[e0:e2 + 1]
            quality = _rep_quality(rep_segment)

            reps.append(Rep(
                start_frame=int(e0),
                peak_frame=int(e1),
                end_frame=int(e2),
                amplitude_deg=float(amplitude),
                duration_s=float(duration_frames / fps),
                quality=float(quality),
            ))

    return reps


def _find_extrema(series: np.ndarray, find_max: bool = True,
                   prominence: float = 5.0,
                   min_distance: int = 5) -> List[int]:
    """Find local maxima (or minima) with prominence threshold."""
    try:
        from scipy.signal import find_peaks
        if find_max:
            peaks, _ = find_peaks(series, prominence=prominence,
                                   distance=min_distance)
        else:
            peaks, _ = find_peaks(-series, prominence=prominence,
                                   distance=min_distance)
        return peaks.tolist()
    except ImportError:
        return _find_extrema_fallback(series, find_max, prominence,
                                       min_distance)


def _find_extrema_fallback(series: np.ndarray, find_max: bool,
                            prominence: float,
                            min_distance: int) -> List[int]:
    """Pure-numpy fallback."""
    extrema = []
    for i in range(1, len(series) - 1):
        if find_max:
            is_extremum = series[i] > series[i - 1] and series[i] > series[i + 1]
        else:
            is_extremum = series[i] < series[i - 1] and series[i] < series[i + 1]
        if is_extremum:
            if extrema and (i - extrema[-1] < min_distance):
                continue
            window = series[max(0, i - 5):min(len(series), i + 6)]
            local_range = window.max() - window.min()
            if local_range >= prominence:
                extrema.append(i)
    return extrema


def _rep_quality(segment: np.ndarray) -> float:
    """Quality score 0-1 based on rep smoothness."""
    if len(segment) < 4:
        return 0.5
    diff = np.diff(segment)
    sign_changes = np.sum(np.diff(np.sign(diff)) != 0)
    expected_changes = 1
    penalty = max(0, sign_changes - expected_changes) * 0.1
    return float(max(0.0, 1.0 - penalty))


def _consistency_score(reps: List[Rep]) -> float:
    """0-100 score: how consistent are rep durations and amplitudes?"""
    if len(reps) < 2:
        return 100.0 if reps else 0.0

    durations = np.array([r.duration_s for r in reps])
    amplitudes = np.array([r.amplitude_deg for r in reps])

    dur_cv = durations.std() / (durations.mean() + 1e-6)
    amp_cv = amplitudes.std() / (amplitudes.mean() + 1e-6)
    cv = (dur_cv + amp_cv) / 2

    return float(np.clip(100 - cv * 100, 0, 100))


def _empty_result() -> SegmentationResult:
    return SegmentationResult(
        dominant_joint="",
        reps=[],
        total_reps=0,
        avg_duration=0.0,
        avg_amplitude=0.0,
        consistency_score=0.0,
        angle_series=np.array([]),
    )
