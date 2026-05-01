"""
姿態估計模組。

主引擎：MediaPipe Pose（內建 3D 世界座標）。
選用：MotionAGFormer（需提供預訓練權重）—— 由呼叫端傳入 lifter 介面。

輸出 (T, 33, 3) 世界座標序列，與 scoring 模組 相容。
"""
from __future__ import annotations

from typing import List, Optional

import importlib
import cv2
import numpy as np

try:
    import mediapipe as mp
except Exception as exc:  # pragma: no cover - environment dependent
    mp = None  # type: ignore[assignment]
    _mediapipe_import_error = exc
else:
    _mediapipe_import_error = None

# mediapipe 0.10+ 在不同 Python 版本與平台下，legacy `solutions.pose`
# 的載入路徑略有差異。依序嘗試三種策略，並把每次失敗的真實原因累積起來
# 一起回報，讓診斷更容易。
_mp_pose_errors: list[str] = []
mp_pose = None  # type: ignore[assignment]

if mp is None:
    _mp_pose_errors.append(
        f"import mediapipe -> "
        f"{type(_mediapipe_import_error).__name__}: {_mediapipe_import_error}"
    )
else:
    for _strategy in (
        ("mp.solutions.pose", lambda: mp.solutions.pose),
        ("mediapipe.python.solutions.pose",
         lambda: importlib.import_module("mediapipe.python.solutions.pose")),
        ("mediapipe.solutions.pose",
         lambda: importlib.import_module("mediapipe.solutions.pose")),
    ):
        _name, _loader = _strategy
        try:
            mp_pose = _loader()
            break
        except Exception as _exc:  # noqa: BLE001
            _mp_pose_errors.append(f"{_name} -> {type(_exc).__name__}: {_exc}")


def pose_available() -> bool:
    """Return whether the MediaPipe Pose runtime is ready."""
    return mp_pose is not None


def pose_error_message() -> str:
    _diag = "\n".join(f"  - {e}" for e in _mp_pose_errors)
    return (
        "mediapipe 的 Pose solution 無法載入，嘗試的三種路徑都失敗：\n"
        f"{_diag}\n\n"
        "建議步驟：\n"
        "  1) 確認 Python 版本（建議 3.10 或 3.11）：\n"
        "       python --version\n"
        "  2) 強制重裝 mediapipe 至可用版本：\n"
        "       python -m pip install --upgrade --force-reinstall "
        "--no-cache-dir mediapipe\n"
        "  3) 如果是 Python 3.13，請建立 3.11 venv 後重試：\n"
        "       py -3.11 -m venv .venv\n"
        "       .venv\\Scripts\\activate\n"
        "       python -m pip install -r requirements.txt\n"
    )


def ema_smooth(
    sequence: List[np.ndarray], alpha: float = 0.6,
) -> List[np.ndarray]:
    """一階指數平滑，降低 jitter；alpha 越大越接近原始資料。"""
    if not sequence:
        return sequence
    alpha = float(max(0.0, min(1.0, alpha)))
    smoothed: List[np.ndarray] = [sequence[0].copy()]
    for s in sequence[1:]:
        prev = smoothed[-1]
        smoothed.append(alpha * s + (1 - alpha) * prev)
    return smoothed


class PoseEstimator:
    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_conf: float = 0.5,
        smooth_alpha: float = 0.6,
    ):
        if mp_pose is None:
            raise ImportError(pose_error_message())
        self._pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            enable_segmentation=False,
            min_detection_confidence=min_detection_conf,
            min_tracking_confidence=0.5,
        )
        self.smooth_alpha = smooth_alpha

    def close(self) -> None:
        self._pose.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def extract(self, frame_bgr: np.ndarray):
        """回傳單張影格的關鍵點：
        {
          'world': (33,3) 以公尺為單位、以髖中心為原點的 3D 座標,
          'image': (33,3) 影像空間 (x_norm, y_norm, visibility)
        }
        未偵測到人體時回傳 None。
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = self._pose.process(rgb)
        if not res.pose_world_landmarks or not res.pose_landmarks:
            return None
        world = np.array(
            [[lm.x, lm.y, lm.z]
             for lm in res.pose_world_landmarks.landmark],
            dtype=np.float32,
        )
        image = np.array(
            [[lm.x, lm.y, lm.visibility]
             for lm in res.pose_landmarks.landmark],
            dtype=np.float32,
        )
        return {"world": world, "image": image}

    def extract_video(
        self,
        path: str,
        max_frames: int = 240,
        stride: int = 1,
        smooth: bool = True,
        lifter: Optional[object] = None,
    ):
        """抽取整段影片的關鍵點序列。

        lifter: 可選的 2D→3D 提升器（例如 MotionAGFormer 實例）。若提供且
        `.available` 為真，會以其輸出覆蓋 MediaPipe 的世界座標。

        回傳: (sequence, frames, fps)
          sequence: List[(33,3)] 世界座標序列
          frames:   List[dict]   每幀影像與對應 2D 關鍵點
          fps:      float
        """
        cap = cv2.VideoCapture(path)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        sequence: List[np.ndarray] = []
        frames: List[dict] = []
        image_kps: List[np.ndarray] = []
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                kp = self.extract(frame)
                if kp is not None:
                    sequence.append(kp["world"])
                    image_kps.append(kp["image"])
                    frames.append({
                        "image": frame,
                        "image_kp": kp["image"],
                        "frame_idx": idx,
                    })
                    if len(sequence) >= max_frames:
                        break
            idx += 1
        cap.release()

        # 選用：用 MotionAGFormer 重新提升 3D
        if (
            lifter is not None
            and getattr(lifter, "available", False)
            and image_kps
        ):
            try:
                arr2d = np.stack(
                    [kp[:, :2] for kp in image_kps], axis=0
                )
                lifted = lifter.lift(arr2d)
                if lifted is not None and len(lifted) == len(sequence):
                    sequence = [lifted[i] for i in range(len(lifted))]
            except Exception:
                pass

        if smooth and sequence:
            sequence = ema_smooth(sequence, self.smooth_alpha)
        return sequence, frames, fps
