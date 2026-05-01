"""
Multi-person tracking: detect and track multiple people for group rehab.

MediaPipe Pose only tracks one person, so we use MediaPipe Object Detection +
crop-and-track approach:
1. Detect persons via lightweight bounding-box model each N frames
2. For each box, run pose estimator on the cropped region
3. Maintain identity across frames using IoU + centroid matching
4. Each tracked person has independent angle filters

This enables:
- Group rehab class with up to 4 patients
- Caregiver next to patient (filter out caregiver)
- Therapist demonstration alongside patient comparison
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import time
import numpy as np

from enhanced_pose import EnhancedPoseEstimator, PoseEstimatorConfig, PoseFrame


@dataclass
class TrackedPerson:
    person_id: int
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    centroid: Tuple[float, float]
    pose: Optional[PoseFrame] = None
    last_seen: float = 0.0
    track_age: int = 0
    color: Tuple[int, int, int] = (0, 255, 0)


@dataclass
class MultiPersonState:
    persons: List[TrackedPerson] = field(default_factory=list)
    frame_idx: int = 0
    timestamp: float = 0.0


class MultiPersonTracker:
    """Tracks up to N persons with independent pose extraction.

    For lightweight deployment, uses MediaPipe Object Detection
    (or YOLOv8 Nano if available) for bounding boxes, then runs
    EnhancedPoseEstimator on each cropped region.
    """

    PALETTE = [
        (231, 76, 60), (52, 152, 219), (46, 204, 113),
        (155, 89, 182), (241, 196, 15), (230, 126, 34),
    ]

    def __init__(self, max_persons: int = 4,
                 detection_interval: int = 5,
                 iou_threshold: float = 0.3):
        self.max_persons = max_persons
        self.detection_interval = detection_interval
        self.iou_threshold = iou_threshold

        self._pose_estimators: List[EnhancedPoseEstimator] = []
        self._next_id = 0
        self._frame_idx = 0
        self._tracked: List[TrackedPerson] = []
        self._detector = None
        self._init_detector()

    def _init_detector(self) -> None:
        """Try YOLOv8 → MediaPipe object_detection → motion-based fallback."""
        try:
            from ultralytics import YOLO  # type: ignore
            self._detector = ("yolo", YOLO("yolov8n.pt"))
            return
        except Exception:
            pass

        try:
            import mediapipe as mp  # type: ignore
            object_det = mp.solutions.object_detection.ObjectDetection(
                min_detection_confidence=0.5,
            )
            self._detector = ("mp_object", object_det)
            return
        except Exception:
            pass

        self._detector = ("motion", None)

    def update(self, frame_bgr: np.ndarray,
                timestamp: Optional[float] = None) -> MultiPersonState:
        """Process a frame, return state with all tracked persons."""
        self._frame_idx += 1
        if timestamp is None:
            timestamp = time.time()

        if self._frame_idx % self.detection_interval == 0 or not self._tracked:
            detected_boxes = self._detect_persons(frame_bgr)
            self._tracked = self._match_and_update(detected_boxes, timestamp)

        for person in self._tracked:
            self._extract_pose_for_person(frame_bgr, person, timestamp)

        return MultiPersonState(
            persons=self._tracked,
            frame_idx=self._frame_idx,
            timestamp=timestamp,
        )

    def _detect_persons(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Detect person bounding boxes."""
        if not self._detector:
            return []

        kind, model = self._detector
        h, w = frame.shape[:2]

        if kind == "yolo":
            try:
                results = model.predict(frame, classes=[0], verbose=False,
                                        max_det=self.max_persons)
                boxes = []
                for r in results:
                    if r.boxes is None:
                        continue
                    for box in r.boxes.xyxy.cpu().numpy():
                        x1, y1, x2, y2 = map(int, box)
                        boxes.append((x1, y1, x2 - x1, y2 - y1))
                return boxes[:self.max_persons]
            except Exception:
                return []

        if kind == "mp_object":
            try:
                import cv2
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = model.process(rgb)
                boxes = []
                if results.detections:
                    for det in results.detections[:self.max_persons]:
                        bbox = det.location_data.relative_bounding_box
                        x = int(bbox.xmin * w)
                        y = int(bbox.ymin * h)
                        bw = int(bbox.width * w)
                        bh = int(bbox.height * h)
                        boxes.append((x, y, bw, bh))
                return boxes
            except Exception:
                return []

        return [(0, 0, w, h)]

    def _match_and_update(self, detected: List[Tuple[int, int, int, int]],
                           timestamp: float) -> List[TrackedPerson]:
        """Match detected boxes to existing tracks via IoU."""
        if not detected:
            return [p for p in self._tracked if timestamp - p.last_seen < 1.0]

        new_tracked: List[TrackedPerson] = []
        used_existing: List[int] = []

        for box in detected:
            best_iou = 0.0
            best_idx = -1
            for i, person in enumerate(self._tracked):
                if i in used_existing:
                    continue
                iou = _iou(box, person.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i

            if best_idx >= 0 and best_iou >= self.iou_threshold:
                p = self._tracked[best_idx]
                p.bbox = box
                p.centroid = _centroid(box)
                p.last_seen = timestamp
                p.track_age += 1
                new_tracked.append(p)
                used_existing.append(best_idx)
            else:
                pid = self._next_id
                self._next_id += 1
                color = self.PALETTE[pid % len(self.PALETTE)]
                new_tracked.append(TrackedPerson(
                    person_id=pid,
                    bbox=box,
                    centroid=_centroid(box),
                    last_seen=timestamp,
                    color=color,
                ))

        for i, person in enumerate(self._tracked):
            if i not in used_existing and timestamp - person.last_seen < 0.5:
                new_tracked.append(person)

        return new_tracked[:self.max_persons]

    def _extract_pose_for_person(self, frame: np.ndarray,
                                   person: TrackedPerson,
                                   timestamp: float) -> None:
        """Extract pose from cropped region around person."""
        x, y, w, h = person.bbox
        h_full, w_full = frame.shape[:2]

        margin_x = int(w * 0.1)
        margin_y = int(h * 0.1)
        x1 = max(0, x - margin_x)
        y1 = max(0, y - margin_y)
        x2 = min(w_full, x + w + margin_x)
        y2 = min(h_full, y + h + margin_y)

        if x2 <= x1 or y2 <= y1:
            return

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return

        if person.person_id >= len(self._pose_estimators):
            est = EnhancedPoseEstimator(PoseEstimatorConfig(
                use_holistic=False,
                complexity=1,
                smooth_landmarks=True,
            ))
            self._pose_estimators.append(est)

        estimator = self._pose_estimators[
            person.person_id % len(self._pose_estimators)
        ]
        pf = estimator.process_frame(crop, timestamp=timestamp)
        person.pose = pf

    def close(self) -> None:
        """Release all estimators."""
        for est in self._pose_estimators:
            est.close()
        self._pose_estimators = []


def _iou(a: Tuple[int, int, int, int],
         b: Tuple[int, int, int, int]) -> float:
    """Intersection-over-union of two boxes (x,y,w,h)."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2 = ax1 + aw
    ay2 = ay1 + ah
    bx2 = bx1 + bw
    by2 = by1 + bh

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _centroid(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x, y, w, h = box
    return (x + w / 2, y + h / 2)
