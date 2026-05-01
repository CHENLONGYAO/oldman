"""
Enhanced pose estimator: MediaPipe Holistic + complexity=2 (heavy model).

Provides the most detailed pose extraction available in MediaPipe:
- 33 body landmarks in 3D world coordinates (meters)
- Per-joint visibility scores
- Optional face mesh (468 landmarks) and hands (21+21) for upper-body detail
- Higher accuracy via model_complexity=2 (heavy)
- Image-space and world-space coordinates for both 2D overlay and 3D angles

Drop-in replacement for pose_estimator.py with richer outputs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    import mediapipe as mp  # type: ignore
    _MEDIAPIPE_AVAILABLE = True
except ImportError:
    mp = None
    _MEDIAPIPE_AVAILABLE = False


# 33 BlazePose landmark indices
LM = {
    "NOSE": 0,
    "LEFT_EYE_INNER": 1, "LEFT_EYE": 2, "LEFT_EYE_OUTER": 3,
    "RIGHT_EYE_INNER": 4, "RIGHT_EYE": 5, "RIGHT_EYE_OUTER": 6,
    "LEFT_EAR": 7, "RIGHT_EAR": 8,
    "MOUTH_LEFT": 9, "MOUTH_RIGHT": 10,
    "LEFT_SHOULDER": 11, "RIGHT_SHOULDER": 12,
    "LEFT_ELBOW": 13, "RIGHT_ELBOW": 14,
    "LEFT_WRIST": 15, "RIGHT_WRIST": 16,
    "LEFT_PINKY": 17, "RIGHT_PINKY": 18,
    "LEFT_INDEX": 19, "RIGHT_INDEX": 20,
    "LEFT_THUMB": 21, "RIGHT_THUMB": 22,
    "LEFT_HIP": 23, "RIGHT_HIP": 24,
    "LEFT_KNEE": 25, "RIGHT_KNEE": 26,
    "LEFT_ANKLE": 27, "RIGHT_ANKLE": 28,
    "LEFT_HEEL": 29, "RIGHT_HEEL": 30,
    "LEFT_FOOT_INDEX": 31, "RIGHT_FOOT_INDEX": 32,
}


@dataclass
class PoseFrame:
    """Container for a single frame of pose data."""
    timestamp: float
    world_landmarks: np.ndarray  # (33, 4): x, y, z (meters), visibility
    image_landmarks: np.ndarray  # (33, 4): x_norm, y_norm, z_norm, visibility
    face_landmarks: Optional[np.ndarray] = None  # (468, 3) if Holistic
    left_hand: Optional[np.ndarray] = None       # (21, 3) if Holistic
    right_hand: Optional[np.ndarray] = None      # (21, 3) if Holistic
    fps: float = 0.0
    quality: float = 0.0  # mean visibility 0-1
    image_size: Tuple[int, int] = (0, 0)  # (width, height)


@dataclass
class PoseEstimatorConfig:
    """Configuration for the enhanced estimator."""
    use_holistic: bool = False      # True: face+hands+pose, False: pose only
    complexity: int = 2             # 0=lite, 1=full, 2=heavy (most accurate)
    enable_segmentation: bool = False
    smooth_landmarks: bool = True   # MediaPipe internal Kalman-like smoothing
    smooth_segmentation: bool = False
    min_detection_conf: float = 0.6
    min_tracking_conf: float = 0.7
    static_image_mode: bool = False
    refine_face_landmarks: bool = False  # Holistic only


class EnhancedPoseEstimator:
    """High-accuracy pose estimator with optional Holistic mode."""

    def __init__(self, config: Optional[PoseEstimatorConfig] = None):
        if not _MEDIAPIPE_AVAILABLE:
            raise RuntimeError(
                "MediaPipe not available. Install with: pip install mediapipe"
            )

        self.config = config or PoseEstimatorConfig()
        self._pose = None
        self._holistic = None
        self._init_model()

    def _init_model(self) -> None:
        if self.config.use_holistic:
            self._holistic = mp.solutions.holistic.Holistic(
                static_image_mode=self.config.static_image_mode,
                model_complexity=self.config.complexity,
                smooth_landmarks=self.config.smooth_landmarks,
                enable_segmentation=self.config.enable_segmentation,
                smooth_segmentation=self.config.smooth_segmentation,
                refine_face_landmarks=self.config.refine_face_landmarks,
                min_detection_confidence=self.config.min_detection_conf,
                min_tracking_confidence=self.config.min_tracking_conf,
            )
        else:
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=self.config.static_image_mode,
                model_complexity=self.config.complexity,
                smooth_landmarks=self.config.smooth_landmarks,
                enable_segmentation=self.config.enable_segmentation,
                smooth_segmentation=self.config.smooth_segmentation,
                min_detection_confidence=self.config.min_detection_conf,
                min_tracking_confidence=self.config.min_tracking_conf,
            )

    def process_frame(self, frame_bgr: np.ndarray,
                      timestamp: float = 0.0) -> Optional[PoseFrame]:
        """Process a single BGR frame and return PoseFrame or None."""
        import cv2  # local import to avoid cost when unused
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        h, w = frame_bgr.shape[:2]

        if self.config.use_holistic:
            results = self._holistic.process(rgb)
            pose_lm = results.pose_landmarks
            world_lm = results.pose_world_landmarks
        else:
            results = self._pose.process(rgb)
            pose_lm = results.pose_landmarks
            world_lm = results.pose_world_landmarks

        if not (pose_lm and world_lm):
            return None

        world_arr = self._landmarks_to_array(world_lm.landmark, dim=4)
        img_arr = self._landmarks_to_array(pose_lm.landmark, dim=4)

        face_arr = None
        lhand_arr = None
        rhand_arr = None
        if self.config.use_holistic:
            if results.face_landmarks:
                face_arr = self._landmarks_to_array(
                    results.face_landmarks.landmark, dim=3
                )
            if results.left_hand_landmarks:
                lhand_arr = self._landmarks_to_array(
                    results.left_hand_landmarks.landmark, dim=3
                )
            if results.right_hand_landmarks:
                rhand_arr = self._landmarks_to_array(
                    results.right_hand_landmarks.landmark, dim=3
                )

        quality = float(np.mean(world_arr[:, 3])) if world_arr.shape[1] >= 4 else 0.0

        return PoseFrame(
            timestamp=timestamp,
            world_landmarks=world_arr,
            image_landmarks=img_arr,
            face_landmarks=face_arr,
            left_hand=lhand_arr,
            right_hand=rhand_arr,
            quality=quality,
            image_size=(w, h),
        )

    @staticmethod
    def _landmarks_to_array(landmarks, dim: int = 4) -> np.ndarray:
        """Convert MediaPipe landmark list to numpy array."""
        arr = np.zeros((len(landmarks), dim), dtype=np.float32)
        for i, lm in enumerate(landmarks):
            arr[i, 0] = lm.x
            arr[i, 1] = lm.y
            arr[i, 2] = lm.z
            if dim >= 4:
                arr[i, 3] = getattr(lm, "visibility", 1.0)
        return arr

    def close(self) -> None:
        """Release resources."""
        if self._pose:
            self._pose.close()
        if self._holistic:
            self._holistic.close()


def process_video(video_path: str,
                  config: Optional[PoseEstimatorConfig] = None,
                  every_n_frames: int = 1,
                  max_frames: Optional[int] = None) -> Tuple[np.ndarray, float, List[PoseFrame]]:
    """Process video file. Returns (sequence (T,33,3), fps, frames list)."""
    import cv2

    estimator = EnhancedPoseEstimator(config)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    frames: List[PoseFrame] = []
    seq: List[np.ndarray] = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % every_n_frames != 0:
            idx += 1
            continue

        ts = idx / fps if fps > 0 else 0.0
        pf = estimator.process_frame(frame, timestamp=ts)
        if pf is not None:
            frames.append(pf)
            seq.append(pf.world_landmarks[:, :3])

        idx += 1
        if max_frames and len(frames) >= max_frames:
            break

    cap.release()
    estimator.close()

    seq_arr = np.stack(seq) if seq else np.zeros((0, 33, 3), dtype=np.float32)
    return seq_arr, fps, frames
