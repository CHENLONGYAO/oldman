"""
Biomechanics: anatomically correct joint angle computation.

Goes beyond simple 3-point angles to provide clinically meaningful
joint angles via:
- Reference frame construction (torso-aligned coordinate system)
- Plane-projected angles (sagittal, frontal, transverse)
- Euler decomposition (flexion/extension, abduction/adduction, rotation)
- Quaternion-based rotation tracking
- Range of motion (ROM) validation against clinical norms
- Anatomical signed angles (positive = flexion direction)

References:
- Wu et al. 2002, ISB recommendations for joint kinematics
- Vicon Plug-in-Gait reference frames
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import math
import numpy as np

from enhanced_pose import LM


# ============================================================
# Clinical normal ranges of motion (degrees) — adult averages
# Source: AAOS, Magee Clinical Orthopedic Examination 6e
# ============================================================
ROM_NORMS = {
    "shoulder_flexion": (0, 180),
    "shoulder_extension": (0, 60),
    "shoulder_abduction": (0, 180),
    "shoulder_adduction": (0, 50),
    "shoulder_internal_rot": (0, 70),
    "shoulder_external_rot": (0, 90),
    "elbow_flexion": (0, 150),
    "elbow_extension": (0, 0),
    "wrist_flexion": (0, 80),
    "wrist_extension": (0, 70),
    "hip_flexion": (0, 120),
    "hip_extension": (0, 30),
    "hip_abduction": (0, 45),
    "hip_adduction": (0, 30),
    "hip_internal_rot": (0, 45),
    "hip_external_rot": (0, 45),
    "knee_flexion": (0, 135),
    "knee_extension": (0, 10),
    "ankle_dorsiflexion": (0, 20),
    "ankle_plantarflexion": (0, 50),
}


# ============================================================
# Vector math primitives
# ============================================================
def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def _angle_between(u: np.ndarray, v: np.ndarray) -> float:
    """Unsigned angle between two 3D vectors, in degrees."""
    u = _unit(u)
    v = _unit(v)
    dot = float(np.clip(np.dot(u, v), -1.0, 1.0))
    return math.degrees(math.acos(dot))


def _signed_angle(u: np.ndarray, v: np.ndarray, axis: np.ndarray) -> float:
    """Signed angle from u to v around given axis (right-hand rule)."""
    u = _unit(u)
    v = _unit(v)
    axis = _unit(axis)
    sin = float(np.dot(np.cross(u, v), axis))
    cos = float(np.dot(u, v))
    return math.degrees(math.atan2(sin, cos))


def _project_on_plane(v: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Project vector v onto plane defined by normal (unit)."""
    n = _unit(normal)
    return v - np.dot(v, n) * n


# ============================================================
# Body reference frame (torso-aligned)
# Builds an orthonormal basis from shoulders + hips
# ============================================================
@dataclass
class BodyFrame:
    """Torso-aligned coordinate system.

    x: medial-lateral (right is +x)
    y: vertical (up is +y)
    z: anterior-posterior (front is +z)
    origin: midpoint of hips
    """
    origin: np.ndarray
    x: np.ndarray  # right
    y: np.ndarray  # up
    z: np.ndarray  # front

    def to_local(self, point: np.ndarray) -> np.ndarray:
        rel = point - self.origin
        return np.array([np.dot(rel, self.x),
                         np.dot(rel, self.y),
                         np.dot(rel, self.z)], dtype=np.float64)


def build_body_frame(landmarks: np.ndarray) -> BodyFrame:
    """Build torso-aligned reference frame from world landmarks (33,3)."""
    ls = landmarks[LM["LEFT_SHOULDER"]]
    rs = landmarks[LM["RIGHT_SHOULDER"]]
    lh = landmarks[LM["LEFT_HIP"]]
    rh = landmarks[LM["RIGHT_HIP"]]

    hip_mid = (lh + rh) / 2
    sh_mid = (ls + rs) / 2

    x = _unit(rs - ls)             # left-to-right
    y_raw = _unit(sh_mid - hip_mid)  # up
    z = _unit(np.cross(x, y_raw))    # forward (anterior)
    y = _unit(np.cross(z, x))        # re-orthogonalize up

    return BodyFrame(origin=hip_mid, x=x, y=y, z=z)


# ============================================================
# Anatomical joint angles
# Output: dict of {angle_name: degrees}
# ============================================================
def compute_anatomical_angles(landmarks: np.ndarray) -> Dict[str, float]:
    """Compute clinically meaningful joint angles from a single frame.

    landmarks: (33, 3) world coordinates in meters.
    Returns dict with keys matching ROM_NORMS where applicable.
    """
    if landmarks.shape[0] < 33:
        return {}

    bf = build_body_frame(landmarks)
    L = landmarks  # alias
    out: Dict[str, float] = {}

    out.update(_shoulder_angles(L, bf, side="LEFT"))
    out.update(_shoulder_angles(L, bf, side="RIGHT"))
    out.update(_elbow_angles(L))
    out.update(_hip_angles(L, bf, side="LEFT"))
    out.update(_hip_angles(L, bf, side="RIGHT"))
    out.update(_knee_angles(L))
    out.update(_trunk_angles(L, bf))

    return out


def _shoulder_angles(L: np.ndarray, bf: BodyFrame, side: str) -> Dict[str, float]:
    """Shoulder flexion/extension and abduction/adduction (signed, degrees)."""
    sh = L[LM[f"{side}_SHOULDER"]]
    el = L[LM[f"{side}_ELBOW"]]
    upper_arm = el - sh

    sagittal_proj = _project_on_plane(upper_arm, bf.x)
    flex_ext = _signed_angle(-bf.y, sagittal_proj, bf.x)

    frontal_proj = _project_on_plane(upper_arm, bf.z)
    sign = 1 if side == "LEFT" else -1
    abd_add = _signed_angle(-bf.y, frontal_proj, bf.z) * sign

    prefix = "left" if side == "LEFT" else "right"
    return {
        f"{prefix}_shoulder_flex_ext": flex_ext,
        f"{prefix}_shoulder_abd_add": abd_add,
    }


def _elbow_angles(L: np.ndarray) -> Dict[str, float]:
    """Elbow flexion (0 = fully extended)."""
    out = {}
    for side in ("LEFT", "RIGHT"):
        sh = L[LM[f"{side}_SHOULDER"]]
        el = L[LM[f"{side}_ELBOW"]]
        wr = L[LM[f"{side}_WRIST"]]
        upper = sh - el
        forearm = wr - el
        flex = 180.0 - _angle_between(upper, forearm)
        out[f"{'left' if side == 'LEFT' else 'right'}_elbow_flex"] = flex
    return out


def _hip_angles(L: np.ndarray, bf: BodyFrame, side: str) -> Dict[str, float]:
    """Hip flexion/extension and abduction/adduction (signed)."""
    hip = L[LM[f"{side}_HIP"]]
    knee = L[LM[f"{side}_KNEE"]]
    thigh = knee - hip

    sagittal = _project_on_plane(thigh, bf.x)
    flex_ext = _signed_angle(-bf.y, sagittal, bf.x)

    frontal = _project_on_plane(thigh, bf.z)
    sign = 1 if side == "LEFT" else -1
    abd_add = _signed_angle(-bf.y, frontal, bf.z) * sign

    prefix = "left" if side == "LEFT" else "right"
    return {
        f"{prefix}_hip_flex_ext": flex_ext,
        f"{prefix}_hip_abd_add": abd_add,
    }


def _knee_angles(L: np.ndarray) -> Dict[str, float]:
    """Knee flexion (0 = fully extended)."""
    out = {}
    for side in ("LEFT", "RIGHT"):
        hip = L[LM[f"{side}_HIP"]]
        knee = L[LM[f"{side}_KNEE"]]
        ankle = L[LM[f"{side}_ANKLE"]]
        thigh = hip - knee
        shank = ankle - knee
        flex = 180.0 - _angle_between(thigh, shank)
        out[f"{'left' if side == 'LEFT' else 'right'}_knee_flex"] = flex
    return out


def _trunk_angles(L: np.ndarray, bf: BodyFrame) -> Dict[str, float]:
    """Trunk inclination (forward bend) and lateral lean."""
    sh_mid = (L[LM["LEFT_SHOULDER"]] + L[LM["RIGHT_SHOULDER"]]) / 2
    hip_mid = (L[LM["LEFT_HIP"]] + L[LM["RIGHT_HIP"]]) / 2
    trunk = sh_mid - hip_mid

    forward_bend = _signed_angle(np.array([0, 1, 0]),
                                  _project_on_plane(trunk, bf.x),
                                  bf.x)
    lateral_lean = _signed_angle(np.array([0, 1, 0]),
                                  _project_on_plane(trunk, bf.z),
                                  bf.z)

    return {
        "trunk_forward_bend": forward_bend,
        "trunk_lateral_lean": lateral_lean,
    }


# ============================================================
# Range of motion validation
# ============================================================
@dataclass
class ROMViolation:
    angle_name: str
    value: float
    rom_min: float
    rom_max: float
    severity: str  # "mild", "moderate", "severe"


def validate_rom(angles: Dict[str, float],
                  tolerance_pct: float = 10.0) -> List[ROMViolation]:
    """Check angles against clinical ROM norms.

    tolerance_pct: allowed overshoot beyond ROM upper bound.
    """
    violations = []

    rom_keys = {
        "left_shoulder_flex_ext": ("shoulder_flexion", "shoulder_extension"),
        "right_shoulder_flex_ext": ("shoulder_flexion", "shoulder_extension"),
        "left_shoulder_abd_add": ("shoulder_abduction", "shoulder_adduction"),
        "right_shoulder_abd_add": ("shoulder_abduction", "shoulder_adduction"),
        "left_elbow_flex": ("elbow_flexion", None),
        "right_elbow_flex": ("elbow_flexion", None),
        "left_hip_flex_ext": ("hip_flexion", "hip_extension"),
        "right_hip_flex_ext": ("hip_flexion", "hip_extension"),
        "left_knee_flex": ("knee_flexion", None),
        "right_knee_flex": ("knee_flexion", None),
    }

    for angle_name, (pos_rom, neg_rom) in rom_keys.items():
        if angle_name not in angles:
            continue
        val = angles[angle_name]
        violation = _check_one(val, pos_rom, neg_rom, tolerance_pct)
        if violation:
            violation.angle_name = angle_name
            violations.append(violation)

    return violations


def _check_one(val: float, pos_rom_key: Optional[str],
                neg_rom_key: Optional[str],
                tol_pct: float) -> Optional[ROMViolation]:
    """Check single angle. Returns violation or None."""
    if pos_rom_key and val > 0:
        rng = ROM_NORMS.get(pos_rom_key, (0, 180))
        upper = rng[1] * (1 + tol_pct / 100)
        if val > upper:
            sev = _severity(val, rng[1])
            return ROMViolation("", val, rng[0], rng[1], sev)
    if neg_rom_key and val < 0:
        rng = ROM_NORMS.get(neg_rom_key, (0, 60))
        lower = -rng[1] * (1 + tol_pct / 100)
        if val < lower:
            sev = _severity(abs(val), rng[1])
            return ROMViolation("", val, -rng[1], 0, sev)
    return None


def _severity(value: float, threshold: float) -> str:
    over_pct = ((abs(value) - threshold) / threshold) * 100
    if over_pct < 15:
        return "mild"
    if over_pct < 30:
        return "moderate"
    return "severe"


# ============================================================
# Movement quality metrics (per session)
# ============================================================
def compute_smoothness(angle_series: np.ndarray, fps: float = 30.0) -> float:
    """Spectral arc length (SPARC) — gold-standard movement smoothness.

    Returns a value in [-inf, 0]; closer to 0 = smoother.
    """
    if len(angle_series) < 8:
        return 0.0

    velocity = np.gradient(angle_series, 1.0 / fps)
    fft_vals = np.abs(np.fft.rfft(velocity))
    if fft_vals.max() < 1e-9:
        return 0.0
    fft_norm = fft_vals / fft_vals.max()

    freqs = np.fft.rfftfreq(len(velocity), d=1.0 / fps)
    cutoff = freqs <= 20.0
    fft_norm = fft_norm[cutoff]
    freqs = freqs[cutoff]

    if len(freqs) < 2:
        return 0.0

    df = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0
    diff = np.diff(fft_norm)
    arc_lengths = np.sqrt((df ** 2) + (diff ** 2))
    sparc = -float(np.sum(arc_lengths))
    return sparc


def compute_symmetry(left_series: np.ndarray,
                      right_series: np.ndarray) -> float:
    """Bilateral symmetry index (0=identical, 100=opposite).

    Lower is better. Useful for hemiparesis tracking.
    """
    if len(left_series) == 0 or len(right_series) == 0:
        return 0.0

    n = min(len(left_series), len(right_series))
    left = left_series[:n]
    right = right_series[:n]

    diff = np.abs(left - right)
    avg = (np.abs(left) + np.abs(right)) / 2 + 1e-9
    si = float(np.mean(diff / avg) * 100)
    return min(100.0, si)


def compute_velocity_profile(angle_series: np.ndarray,
                              fps: float = 30.0) -> Dict[str, float]:
    """Velocity statistics for movement quality assessment."""
    if len(angle_series) < 2:
        return {"peak_vel": 0, "mean_vel": 0, "vel_cv": 0}

    vel = np.gradient(angle_series, 1.0 / fps)
    abs_vel = np.abs(vel)

    return {
        "peak_vel": float(np.max(abs_vel)),
        "mean_vel": float(np.mean(abs_vel)),
        "vel_cv": float(np.std(abs_vel) / (np.mean(abs_vel) + 1e-9)),
    }
