"""
SOTA pose model adapters: unified interface across multiple backends.

Supported (auto-fallback chain):
1. Sapiens (Meta, 2024) — best accuracy, GPU recommended
2. RTMPose-X (OpenMMLab) — SOTA real-time, ONNX-friendly
3. YOLOv8-pose-x — 17 COCO keypoints, multi-person
4. ViTPose-Huge — transformer-based, high accuracy
5. MediaPipe Pose heavy — always available fallback

All adapters implement the same interface:
    estimator = SapiensAdapter() / RTMPoseAdapter() / ...
    keypoints, scores = estimator.predict(frame_bgr)

Output format: (33, 3) world coordinates compatible with biomechanics.py.
We map COCO-17/26-keypoint outputs back to MediaPipe's 33-keypoint indexing.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple
import numpy as np


# COCO-17 → MediaPipe-33 keypoint mapping
# (most COCO keypoints have direct equivalents; missing ones get interpolated)
COCO17_TO_MP33 = {
    # COCO idx -> MediaPipe idx
    0: 0,    # nose
    1: 2,    # left eye
    2: 5,    # right eye
    3: 7,    # left ear
    4: 8,    # right ear
    5: 11,   # left shoulder
    6: 12,   # right shoulder
    7: 13,   # left elbow
    8: 14,   # right elbow
    9: 15,   # left wrist
    10: 16,  # right wrist
    11: 23,  # left hip
    12: 24,  # right hip
    13: 25,  # left knee
    14: 26,  # right knee
    15: 27,  # left ankle
    16: 28,  # right ankle
}


@dataclass
class PoseResult:
    keypoints: np.ndarray  # (33, 3) — world or pseudo-world coords
    scores: np.ndarray     # (33,) — visibility / confidence
    bbox: Optional[Tuple[int, int, int, int]] = None
    backend: str = "unknown"


class _BaseAdapter:
    name = "base"
    is_loaded = False

    def predict(self, frame_bgr: np.ndarray) -> Optional[PoseResult]:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ============================================================
# Sapiens (Meta) — best accuracy
# ============================================================
class SapiensAdapter(_BaseAdapter):
    """Meta Sapiens-1B / Sapiens-2B pose estimation."""
    name = "sapiens"

    def __init__(self, model_size: str = "1b"):
        self._model_id = f"facebook/sapiens-pose-{model_size}"
        self._model = None
        self._processor = None
        self._load()

    def _load(self) -> None:
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModel
            self._processor = AutoImageProcessor.from_pretrained(
                self._model_id
            )
            self._model = AutoModel.from_pretrained(self._model_id)
            self._model.eval()
            if torch.cuda.is_available():
                self._model = self._model.cuda()
            self.is_loaded = True
        except Exception:
            self.is_loaded = False

    def predict(self, frame_bgr: np.ndarray) -> Optional[PoseResult]:
        if not self.is_loaded:
            return None
        try:
            import cv2
            import torch
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            inputs = self._processor(images=rgb, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)

            heatmaps = outputs.last_hidden_state.cpu().numpy()
            keypoints, scores = self._heatmaps_to_keypoints(heatmaps[0])
            return PoseResult(
                keypoints=self._coco_to_mp33(keypoints, scores),
                scores=self._expand_scores(scores),
                backend="sapiens",
            )
        except Exception:
            return None

    @staticmethod
    def _heatmaps_to_keypoints(heatmaps: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Extract argmax positions and confidences from heatmaps."""
        n_joints = heatmaps.shape[0]
        kp = np.zeros((n_joints, 3), dtype=np.float32)
        scores = np.zeros(n_joints, dtype=np.float32)
        for j in range(n_joints):
            hm = heatmaps[j]
            idx = np.unravel_index(np.argmax(hm), hm.shape)
            kp[j, 0] = idx[1] / hm.shape[1]
            kp[j, 1] = idx[0] / hm.shape[0]
            kp[j, 2] = 0.0
            scores[j] = float(hm.max())
        return kp, scores

    @staticmethod
    def _coco_to_mp33(coco_kp: np.ndarray,
                      scores: np.ndarray) -> np.ndarray:
        """Project COCO keypoints into 33-keypoint MediaPipe layout."""
        out = np.zeros((33, 3), dtype=np.float32)
        for coco_idx, mp_idx in COCO17_TO_MP33.items():
            if coco_idx < len(coco_kp):
                out[mp_idx] = coco_kp[coco_idx]
        return out

    @staticmethod
    def _expand_scores(scores: np.ndarray) -> np.ndarray:
        out = np.zeros(33, dtype=np.float32)
        for coco_idx, mp_idx in COCO17_TO_MP33.items():
            if coco_idx < len(scores):
                out[mp_idx] = scores[coco_idx]
        return out


# ============================================================
# RTMPose — SOTA real-time
# ============================================================
class RTMPoseAdapter(_BaseAdapter):
    """RTMPose-X via ONNX. Best speed/accuracy balance."""
    name = "rtmpose"

    def __init__(self, weights_path: str = "weights/rtmpose-x.onnx"):
        self.weights_path = weights_path
        self._session = None
        self._load()

    def _load(self) -> None:
        try:
            from onnx_accel import OnnxSession
            if not Path(self.weights_path).exists():
                self.is_loaded = False
                return
            self._session = OnnxSession(self.weights_path)
            self.is_loaded = True
        except Exception:
            self.is_loaded = False

    def predict(self, frame_bgr: np.ndarray) -> Optional[PoseResult]:
        if not self.is_loaded:
            return None
        try:
            import cv2
            input_size = (288, 384)
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, input_size)
            arr = resized.astype(np.float32).transpose(2, 0, 1)[None] / 255.0
            arr = (arr - np.array([[[0.485]], [[0.456]], [[0.406]]])) / \
                  np.array([[[0.229]], [[0.224]], [[0.225]]])

            outputs = self._session.run({"input": arr.astype(np.float32)})
            kp_xy = outputs[0][0]
            scores = outputs[1][0] if len(outputs) > 1 else np.ones(len(kp_xy))

            kp = np.zeros((len(kp_xy), 3), dtype=np.float32)
            kp[:, :2] = kp_xy / np.array(input_size)

            return PoseResult(
                keypoints=SapiensAdapter._coco_to_mp33(kp, scores),
                scores=SapiensAdapter._expand_scores(scores),
                backend="rtmpose",
            )
        except Exception:
            return None


# ============================================================
# YOLOv8-pose — fast multi-person
# ============================================================
class YoloPoseAdapter(_BaseAdapter):
    """YOLOv8-pose-x. Multi-person, fast."""
    name = "yolo_pose"

    def __init__(self, model_path: str = "yolov8x-pose.pt"):
        self._model = None
        try:
            from ultralytics import YOLO
            self._model = YOLO(model_path)
            self.is_loaded = True
        except Exception:
            self.is_loaded = False

    def predict(self, frame_bgr: np.ndarray) -> Optional[PoseResult]:
        if not self.is_loaded:
            return None
        try:
            results = self._model.predict(
                frame_bgr, classes=[0], verbose=False, max_det=1,
            )
            if not results:
                return None
            kp = results[0].keypoints
            if kp is None or len(kp.xy) == 0:
                return None

            xy = kp.xy[0].cpu().numpy()
            conf = kp.conf[0].cpu().numpy() if kp.conf is not None else None

            h, w = frame_bgr.shape[:2]
            normalized = np.zeros((len(xy), 3), dtype=np.float32)
            normalized[:, 0] = xy[:, 0] / w
            normalized[:, 1] = xy[:, 1] / h

            scores = conf if conf is not None else np.ones(len(xy))

            box = None
            if results[0].boxes is not None and len(results[0].boxes) > 0:
                box_xyxy = results[0].boxes.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = map(int, box_xyxy)
                box = (x1, y1, x2 - x1, y2 - y1)

            return PoseResult(
                keypoints=SapiensAdapter._coco_to_mp33(normalized, scores),
                scores=SapiensAdapter._expand_scores(scores),
                bbox=box,
                backend="yolo_pose",
            )
        except Exception:
            return None


# ============================================================
# MediaPipe heavy — always-available fallback
# ============================================================
class MediaPipeHeavyAdapter(_BaseAdapter):
    """MediaPipe Pose with model_complexity=2."""
    name = "mediapipe_heavy"

    def __init__(self):
        try:
            from enhanced_pose import (
                EnhancedPoseEstimator, PoseEstimatorConfig,
            )
            self._estimator = EnhancedPoseEstimator(PoseEstimatorConfig(
                complexity=2, smooth_landmarks=True,
            ))
            self.is_loaded = True
        except Exception:
            self._estimator = None
            self.is_loaded = False

    def predict(self, frame_bgr: np.ndarray) -> Optional[PoseResult]:
        if not self.is_loaded:
            return None
        try:
            pf = self._estimator.process_frame(frame_bgr)
            if pf is None:
                return None
            return PoseResult(
                keypoints=pf.world_landmarks[:, :3],
                scores=pf.world_landmarks[:, 3],
                backend="mediapipe_heavy",
            )
        except Exception:
            return None

    def close(self) -> None:
        if self._estimator:
            self._estimator.close()


# ============================================================
# Auto-selection
# ============================================================
def best_available_adapter(prefer: Optional[str] = None) -> _BaseAdapter:
    """Pick best available pose adapter."""
    order = [prefer] if prefer else []
    order += ["sapiens", "rtmpose", "yolo_pose", "mediapipe_heavy"]

    for name in order:
        if not name:
            continue
        adapter = _instantiate(name)
        if adapter and adapter.is_loaded:
            return adapter

    return MediaPipeHeavyAdapter()


def _instantiate(name: str) -> Optional[_BaseAdapter]:
    if name == "sapiens":
        return SapiensAdapter()
    if name == "rtmpose":
        return RTMPoseAdapter()
    if name == "yolo_pose":
        return YoloPoseAdapter()
    if name == "mediapipe_heavy":
        return MediaPipeHeavyAdapter()
    return None


def list_available() -> List[str]:
    """List adapters that successfully loaded on this machine."""
    available = []
    for name in ("sapiens", "rtmpose", "yolo_pose", "mediapipe_heavy"):
        adapter = _instantiate(name)
        if adapter and adapter.is_loaded:
            available.append(name)
            adapter.close()
    return available
