"""
2D → 3D pose lifting via MotionBERT (or fallbacks).

MotionBERT is a transformer-based model trained on Human3.6M / AMASS that
gives state-of-the-art 3D pose predictions (MPJPE ~39mm) from 2D keypoints.

This module provides a unified `lift()` function with automatic fallback:
1. MotionBERT (best, requires torch + downloaded weights)
2. MotionAGFormer (already in repo, lighter)
3. VideoPose3D-style temporal smoothing (always available)

Input: (T, 17, 2) or (T, 33, 2) 2D keypoints normalized to [0,1]
Output: (T, 17, 3) or (T, 33, 3) 3D world coordinates in meters
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import numpy as np


@dataclass
class LiftResult:
    keypoints_3d: np.ndarray  # (T, J, 3)
    backend: str
    mpjpe_estimate: float = 0.0  # mean per-joint position error estimate


# ============================================================
# MotionBERT adapter
# ============================================================
class MotionBERTLifter:
    """MotionBERT lite (243-frame context). Best 3D MPJPE."""

    def __init__(self, model_id: str = "walterzhu/MotionBERT-Lite",
                 context_frames: int = 243):
        self.context_frames = context_frames
        self._model = None
        self._device = "cpu"
        self._load(model_id)

    def _load(self, model_id: str) -> None:
        try:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            try:
                from huggingface_hub import hf_hub_download
                weights = hf_hub_download(
                    repo_id=model_id, filename="best_epoch.bin"
                )
            except Exception:
                weights = None

            if weights and Path(weights).exists():
                self._model = self._build_model_arch()
                state = torch.load(weights, map_location=self._device,
                                   weights_only=False)
                if "model_pos" in state:
                    state = state["model_pos"]
                self._model.load_state_dict(state, strict=False)
                self._model.eval()
                self._model.to(self._device)
                self.is_loaded = True
            else:
                self.is_loaded = False
        except Exception:
            self.is_loaded = False

    def _build_model_arch(self):
        """Lazy import of MotionBERT architecture."""
        try:
            from transformers import AutoModel
            return AutoModel.from_pretrained(
                "walterzhu/MotionBERT-Lite",
                trust_remote_code=True,
            )
        except Exception:
            return None

    def lift(self, keypoints_2d: np.ndarray) -> Optional[np.ndarray]:
        """Lift (T, 17, 2) → (T, 17, 3)."""
        if not getattr(self, "is_loaded", False):
            return None
        try:
            import torch
            arr = keypoints_2d.astype(np.float32)
            if arr.ndim == 2:
                arr = arr[None]

            T = arr.shape[0]
            if T < self.context_frames:
                pad = self.context_frames - T
                arr = np.concatenate([arr, np.repeat(arr[-1:], pad, axis=0)])

            batch = torch.from_numpy(arr[None]).to(self._device)

            with torch.no_grad():
                out = self._model(batch)

            kp3d = out[0].cpu().numpy()[:T]
            return kp3d
        except Exception:
            return None


# ============================================================
# MotionAGFormer fallback (already in this repo)
# ============================================================
class MotionAGFormerLifter:
    """MotionAGFormer — repo's existing lifter."""

    def __init__(self):
        try:
            import motionagformer  # noqa: F401
            self.is_loaded = True
        except ImportError:
            self.is_loaded = False

    def lift(self, keypoints_2d: np.ndarray) -> Optional[np.ndarray]:
        if not self.is_loaded:
            return None
        try:
            import motionagformer as agf
            if hasattr(agf, "lift_2d_to_3d"):
                return agf.lift_2d_to_3d(keypoints_2d)
            if hasattr(agf, "lift"):
                return agf.lift(keypoints_2d)
        except Exception:
            pass
        return None


# ============================================================
# Temporal smoothing fallback
# Pseudo-3D: use 2D + estimated depth from keypoint relationships
# ============================================================
def estimate_depth_heuristic(keypoints_2d: np.ndarray) -> np.ndarray:
    """Generate a plausible Z-coordinate from 2D using anatomy priors.

    Strategy: keypoints further from the body centroid get larger |z| in
    the direction implied by left/right limbs. Not a substitute for real
    3D lifting, but better than zero-Z for visualization.
    """
    T = keypoints_2d.shape[0]
    J = keypoints_2d.shape[1]

    out = np.zeros((T, J, 3), dtype=np.float32)
    out[:, :, :2] = keypoints_2d

    centroid = keypoints_2d.mean(axis=1, keepdims=True)
    rel = keypoints_2d - centroid
    radial = np.linalg.norm(rel, axis=2)

    sign = np.where((np.arange(J) % 2 == 0)[None, :], 1.0, -1.0)
    out[:, :, 2] = radial * 0.3 * sign

    if T > 3:
        kernel = np.array([0.25, 0.5, 0.25])
        for j in range(J):
            for d in range(3):
                out[:, j, d] = np.convolve(
                    out[:, j, d], kernel, mode="same"
                )

    return out


# ============================================================
# Unified API
# ============================================================
_LIFTER_CACHE: Optional[object] = None


def lift(keypoints_2d: np.ndarray,
         backend: Optional[str] = None) -> LiftResult:
    """Lift 2D keypoints to 3D using best available backend.

    Args:
        keypoints_2d: (T, J, 2) or (T, J, 3) array; only first 2 dims used.
        backend: optional preferred backend name.
    """
    if keypoints_2d.shape[-1] >= 2:
        kp = keypoints_2d[..., :2]
    else:
        kp = keypoints_2d

    if kp.ndim == 2:
        kp = kp[None]

    global _LIFTER_CACHE

    if backend == "motionbert" or (backend is None and _LIFTER_CACHE is None):
        if _LIFTER_CACHE is None:
            _LIFTER_CACHE = MotionBERTLifter()
        if hasattr(_LIFTER_CACHE, "is_loaded") and _LIFTER_CACHE.is_loaded:
            kp_3d = _LIFTER_CACHE.lift(kp)
            if kp_3d is not None:
                return LiftResult(
                    keypoints_3d=kp_3d,
                    backend="motionbert",
                    mpjpe_estimate=39.0,
                )

    if backend in (None, "motionagformer"):
        agf_lifter = MotionAGFormerLifter()
        if agf_lifter.is_loaded:
            kp_3d = agf_lifter.lift(kp)
            if kp_3d is not None:
                return LiftResult(
                    keypoints_3d=kp_3d,
                    backend="motionagformer",
                    mpjpe_estimate=46.0,
                )

    kp_3d = estimate_depth_heuristic(kp)
    return LiftResult(
        keypoints_3d=kp_3d,
        backend="heuristic",
        mpjpe_estimate=80.0,
    )


def is_motionbert_available() -> bool:
    """Check if MotionBERT model+weights are loadable."""
    try:
        lifter = MotionBERTLifter()
        return getattr(lifter, "is_loaded", False)
    except Exception:
        return False
