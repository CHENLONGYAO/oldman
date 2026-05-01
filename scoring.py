"""
評分與動作比對模組。

- `sequence_to_angle_series` : 由 3D 關鍵點序列計算各關節角度時間序列
- `dtw_vec`                  : 多維 DTW，回傳距離與對齊路徑
- `score_joint_series`       : 以 DTW 對齊患者/範本序列，計算每關節偏差
- `overall_score`            : 綜合分數（含年齡友善調整）
- `feedback_messages`        : 產出可視化文字回饋
"""
from __future__ import annotations

from typing import Dict, List, Tuple
import numpy as np

# MediaPipe Pose 33 點索引
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28

# 關節名稱 → (A, B, C)，計算 B 處的夾角（向量 BA 與 BC 之間）
JOINT_TRIPLETS: Dict[str, Tuple[int, int, int]] = {
    "左肩": (L_ELBOW, L_SHOULDER, L_HIP),
    "右肩": (R_ELBOW, R_SHOULDER, R_HIP),
    "左肘": (L_SHOULDER, L_ELBOW, L_WRIST),
    "右肘": (R_SHOULDER, R_ELBOW, R_WRIST),
    "左髖": (L_SHOULDER, L_HIP, L_KNEE),
    "右髖": (R_SHOULDER, R_HIP, R_KNEE),
    "左膝": (L_HIP, L_KNEE, L_ANKLE),
    "右膝": (R_HIP, R_KNEE, R_ANKLE),
}


def angle_at(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    v1 = a - b
    v2 = c - b
    denom = np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9
    cos = float(np.dot(v1, v2) / denom)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def pose_to_angles(pose: np.ndarray) -> Dict[str, float]:
    return {name: angle_at(pose[a], pose[b], pose[c])
            for name, (a, b, c) in JOINT_TRIPLETS.items()}


def sequence_to_angle_series(seq: List[np.ndarray]) -> Dict[str, np.ndarray]:
    series = {name: [] for name in JOINT_TRIPLETS}
    for p in seq:
        ang = pose_to_angles(p)
        for k, v in ang.items():
            series[k].append(v)
    return {k: np.asarray(v, dtype=np.float32) for k, v in series.items()}


def dtw_vec(
    A: np.ndarray, B: np.ndarray,
) -> Tuple[float, List[Tuple[int, int]]]:
    """多維 DTW。A, B 形狀 (T, D)。回傳 (平均成本, 對齊路徑)。"""
    n, m = len(A), len(B)
    D = np.full((n + 1, m + 1), np.inf, dtype=np.float64)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = float(np.linalg.norm(A[i - 1] - B[j - 1]))
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])

    path: List[Tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        diag, up, left = D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]
        best = min(diag, up, left)
        if best == diag:
            i, j = i - 1, j - 1
        elif best == up:
            i -= 1
        else:
            j -= 1
    path.reverse()
    return float(D[n, m] / max(n, m)), path


def score_joint_series(
    patient_series: Dict[str, np.ndarray],
    template_series: Dict[str, np.ndarray],
) -> Dict[str, Dict[str, float]]:
    joint_names = [k for k in patient_series if k in template_series]
    if not joint_names:
        return {}

    P = np.stack([patient_series[k] for k in joint_names], axis=1)  # (T_p, J)
    T = np.stack([template_series[k] for k in joint_names], axis=1)  # (T_t, J)
    _, path = dtw_vec(P, T)

    results: Dict[str, Dict[str, float]] = {}
    for j_idx, name in enumerate(joint_names):
        devs = [abs(P[i, j_idx] - T[k, j_idx]) for i, k in path]
        results[name] = {
            "max_dev": float(np.max(devs)) if devs else 0.0,
            "mean_dev": float(np.mean(devs)) if devs else 0.0,
            "samples": int(len(devs)),
        }
    return results


def overall_score(
    joint_scores: Dict[str, Dict[str, float]],
    age: int | None = None,
) -> float:
    if not joint_scores:
        return 0.0
    mean_devs = [v["mean_dev"] for v in joint_scores.values()]
    base = max(0.0, 100.0 - float(np.mean(mean_devs)))
    if age is not None and age >= 65:
        # 長者給予較寬鬆的評分，鼓勵持續訓練
        base = min(100.0, base * 1.05)
    return float(base)


def feedback_messages(
    joint_scores: Dict[str, Dict[str, float]],
    threshold: float = 15.0,
) -> List[str]:
    msgs: List[str] = []
    ordered = sorted(joint_scores.items(), key=lambda kv: -kv[1]["max_dev"])
    for name, v in ordered:
        if v["max_dev"] < threshold:
            continue
        hint = _hint_for(name)
        msgs.append(f"{name} 與範本差異最大達 {v['max_dev']:.1f}°，{hint}")
    return msgs


def _hint_for(joint: str) -> str:
    if "肩" in joint:
        return "建議將手臂再抬高一些，動作放慢、幅度到位。"
    if "肘" in joint:
        return "注意手肘的伸展角度，避免過度彎曲或過伸。"
    if "髖" in joint:
        return "嘗試讓軀幹與髖關節更穩定，避免前傾或側傾。"
    if "膝" in joint:
        return "膝關節彎曲幅度與站起時機請配合範本節奏。"
    return "請對照示範影片調整動作幅度與節奏。"


# ---------------- 重複次數偵測 ----------------
_EXERCISE_DOMINANT_JOINT = {
    "arm_raise": "左肩",
    "elbow_flexion": "左肘",
    "wall_pushup": "左肘",
    "sit_to_stand": "左膝",
    "mini_squat": "左膝",
    "knee_extension": "左膝",
    "shoulder_abduction": "左肩",
    "hip_abduction": "左髖",
    "march_in_place": "左膝",
    "seated_march": "左髖",
}


def _dominant_joint(angle_series: Dict[str, np.ndarray],
                    exercise_hint: str | None = None) -> str:
    if exercise_hint and exercise_hint in _EXERCISE_DOMINANT_JOINT:
        key = _EXERCISE_DOMINANT_JOINT[exercise_hint]
        if key in angle_series:
            return key
    return max(angle_series, key=lambda k: float(np.var(angle_series[k])))


def detect_reps(
    angle_series: Dict[str, np.ndarray],
    exercise_hint: str | None = None,
    min_distance: int = 6,
    prominence_ratio: float = 0.35,
) -> List[Tuple[int, int]]:
    """找出動作重複次數。回傳 [(start, end), ...]，index 為序列幀編號。

    作法：在主導關節的角度序列上做極值偵測，以訊號幅度的 prominence_ratio
    作為動態門檻，min_distance 過濾過近的偽峰。
    """
    if not angle_series:
        return []
    key = _dominant_joint(angle_series, exercise_hint)
    signal = angle_series[key]
    if signal is None or len(signal) < 5:
        return []

    s_min, s_max = float(signal.min()), float(signal.max())
    s_range = s_max - s_min
    if s_range < 1e-3:
        return []
    threshold = s_min + prominence_ratio * s_range

    peaks: List[int] = []
    for i in range(1, len(signal) - 1):
        if signal[i] > signal[i - 1] and signal[i] >= signal[i + 1]:
            far_enough = not peaks or (i - peaks[-1] >= min_distance)
            if signal[i] >= threshold and far_enough:
                peaks.append(i)

    if not peaks:
        return []

    reps: List[Tuple[int, int]] = []
    last = len(signal) - 1
    for i, p in enumerate(peaks):
        start = 0 if i == 0 else (peaks[i - 1] + p) // 2
        if i == len(peaks) - 1:
            end = last
        else:
            end = (p + peaks[i + 1]) // 2
        reps.append((int(start), int(end)))
    return reps


# ---------------- 結構化提示（含方向） ----------------
# 每個關節的「角度增加」對應的物理動作：
#   (direction_when_too_low, direction_when_too_high,
#    verb_zh_low, verb_zh_high,
#    verb_en_low, verb_en_high)
# 「too_low」= 患者角度 < 範本，需要把角度變大；對肩來說是抬高。
_JOINT_DIRECTIONS: Dict[str, tuple] = {
    "左肩": ("up",     "down", "往上抬", "往下放", "move up",  "move down"),
    "右肩": ("up",     "down", "往上抬", "往下放", "move up",  "move down"),
    "左肘": ("extend", "flex", "伸直",   "彎曲", "extend",   "flex"),
    "右肘": ("extend", "flex", "伸直",   "彎曲", "extend",   "flex"),
    "左髖": ("extend", "flex", "挺直",   "前傾", "stand up", "lean"),
    "右髖": ("extend", "flex", "挺直",   "前傾", "stand up", "lean"),
    "左膝": ("extend", "flex", "伸直",   "彎曲", "extend",   "flex"),
    "右膝": ("extend", "flex", "伸直",   "彎曲", "extend",   "flex"),
}

_DIRECTION_ICONS = {
    "up": "⬆", "down": "⬇", "extend": "➡", "flex": "↩",
}


_BODY_PART_LABELS = {
    "左肩": "左手臂", "右肩": "右手臂",
    "左肘": "左手肘", "右肘": "右手肘",
    "左髖": "左髖", "右髖": "右髖",
    "左膝": "左膝", "右膝": "右膝",
}


def feedback_cues(
    patient_series: Dict[str, np.ndarray],
    template_series: Dict[str, np.ndarray],
    threshold: float = 15.0,
) -> List[Dict]:
    """產生結構化的方向提示，依嚴重度排序。

    回傳 list[dict]，每筆含:
      joint: 關節名 (中)
      direction: up / down / extend / flex
      icon: 對應箭頭符號
      delta: 偏差量（絕對值, 度）
      verb: 動作建議動詞 (中)
      verb_en: 英文動詞
      severity: high / mid（low 會被門檻過濾掉）
    """
    cues: List[Dict] = []
    for joint, p_arr in patient_series.items():
        if joint not in template_series or joint not in _JOINT_DIRECTIONS:
            continue
        t_arr = template_series[joint]
        if len(p_arr) == 0 or len(t_arr) == 0:
            continue
        # 把範本重採樣到患者長度，逐點比較
        x_p = np.linspace(0, 1, len(p_arr))
        x_t = np.linspace(0, 1, len(t_arr))
        tmpl_rs = np.interp(x_p, x_t, t_arr)
        diffs = p_arr - tmpl_rs              # > 0 → 患者角度過大
        idx = int(np.argmax(np.abs(diffs)))
        delta = float(diffs[idx])
        if abs(delta) < threshold:
            continue
        d_low, d_high, v_low, v_high, en_low, en_high = \
            _JOINT_DIRECTIONS[joint]
        if delta < 0:
            direction, verb, verb_en = d_low, v_low, en_low
        else:
            direction, verb, verb_en = d_high, v_high, en_high
        sev = "high" if abs(delta) >= 30 else "mid"
        cues.append({
            "joint": joint,
            "body_part": _BODY_PART_LABELS.get(joint, joint),
            "direction": direction,
            "icon": _DIRECTION_ICONS.get(direction, "•"),
            "delta": abs(delta),
            "verb": verb,
            "verb_en": verb_en,
            "severity": sev,
        })
    cues.sort(key=lambda c: -c["delta"])
    return cues


def angle_feature_matrix(angle_series: Dict[str, np.ndarray]) -> np.ndarray:
    """將 dict of (T,) 轉為 (T, J)，欄位順序依 JOINT_TRIPLETS 穩定排序。"""
    cols = [angle_series[k] for k in JOINT_TRIPLETS if k in angle_series]
    if not cols:
        return np.zeros((0, 0), dtype=np.float32)
    T = min(len(c) for c in cols)
    return np.stack([c[:T] for c in cols], axis=1).astype(np.float32)


def blend_scores(dtw_score: float, neural_score: float | None,
                 neural_weight: float = 0.4) -> float:
    """若神經網路評分可用，與 DTW 分數線性融合；否則直接回傳 DTW。"""
    if neural_score is None:
        return dtw_score
    w = max(0.0, min(1.0, neural_weight))
    return (1 - w) * dtw_score + w * neural_score
