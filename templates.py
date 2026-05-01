"""
動作範本：內建 + 使用者/治療師自訂。

範本的角度定義與 scoring.JOINT_TRIPLETS 一致：
- 肩角：向量(肘→肩) 與 (髖→肩) 的夾角。手垂下 ~25°，舉至頭頂 ~175°。
- 肘角：伸直 ~175°，彎曲 ~45°。
- 髖角：站立直立 ~175°，坐姿 ~90°。
- 膝角：站立伸直 ~175°，坐姿 ~90°。

自訂範本會儲存於 templates_custom/*.json，載入時自動合併。
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

CUSTOM_DIR = Path(os.environ.get("SMART_REHAB_TEMPLATE_DIR", Path(__file__).parent / "templates_custom"))


# ---------------- 曲線工具 ----------------
def _smooth(t: np.ndarray) -> np.ndarray:
    """Hermite smoothstep (3t^2 - 2t^3)，讓動作加減速更自然。"""
    return t * t * (3.0 - 2.0 * t)


def _sym_curve(T: int, start: float, peak: float) -> List[float]:
    """前半 start→peak，後半鏡像回 start。"""
    half = T // 2
    up = start + (peak - start) * _smooth(np.linspace(0, 1, half))
    down = up[::-1]
    return np.concatenate([up, down]).tolist()


def _flat(T: int, value: float) -> List[float]:
    return np.full(T, value, dtype=np.float32).tolist()


def _asym_curve(
    T: int, start: float, peak: float, hold_ratio: float = 0.2,
) -> List[float]:
    """抬起 → 停留 → 放下，用於有停留動作的範本。"""
    rise = int(T * (1 - hold_ratio) / 2)
    hold = T - 2 * rise
    up = start + (peak - start) * _smooth(np.linspace(0, 1, rise))
    mid = np.full(hold, peak)
    down = up[::-1]
    return np.concatenate([up, mid, down]).tolist()


# ---------------- 內建範本 ----------------
def arm_raise(T: int = 30) -> Dict:
    shoulder = _sym_curve(T, 25.0, 175.0)
    return {
        "key": "arm_raise",
        "name": "雙手上舉",
        "category": "upper",
        "description": "雙手由身體兩側緩慢向上舉至頭頂，再緩慢放下。",
        "cue": "保持背部挺直，雙肘儘量伸直，肩膀放鬆不聳肩。",
        "angle_series": {
            "左肩": shoulder, "右肩": shoulder,
            "左肘": _flat(T, 175.0), "右肘": _flat(T, 175.0),
            "左髖": _flat(T, 175.0), "右髖": _flat(T, 175.0),
            "左膝": _flat(T, 175.0), "右膝": _flat(T, 175.0),
        },
    }


def shoulder_abduction(T: int = 30) -> Dict:
    """側平舉：雙手由體側往外側舉起至肩高。"""
    shoulder = _sym_curve(T, 25.0, 95.0)
    return {
        "key": "shoulder_abduction",
        "name": "肩關節側平舉",
        "category": "upper",
        "description": "雙手由身體兩側緩慢往外側舉起至與肩同高，再緩慢放下。",
        "cue": "掌心朝下，手臂伸直，避免聳肩或身體側傾。",
        "angle_series": {
            "左肩": shoulder, "右肩": shoulder,
            "左肘": _flat(T, 175.0), "右肘": _flat(T, 175.0),
            "左髖": _flat(T, 175.0), "右髖": _flat(T, 175.0),
            "左膝": _flat(T, 175.0), "右膝": _flat(T, 175.0),
        },
    }


def elbow_flexion(T: int = 30) -> Dict:
    """坐姿手肘彎曲：前臂由伸直慢慢彎起再放回。"""
    elbow = _sym_curve(T, 175.0, 55.0)
    return {
        "key": "elbow_flexion",
        "name": "坐姿手肘彎曲",
        "category": "upper",
        "description": "坐姿或站姿，手臂靠近身側，前臂緩慢彎起再伸直放回。",
        "cue": "上臂貼近身體，肩膀放鬆，動作慢而穩。",
        "angle_series": {
            "左肩": _flat(T, 30.0), "右肩": _flat(T, 30.0),
            "左肘": elbow, "右肘": elbow,
            "左髖": _flat(T, 175.0), "右髖": _flat(T, 175.0),
            "左膝": _flat(T, 175.0), "右膝": _flat(T, 175.0),
        },
    }


def wall_pushup(T: int = 34) -> Dict:
    """牆壁伏地挺身：以手肘角度為主，適合上肢控制。"""
    elbow = _sym_curve(T, 175.0, 80.0)
    shoulder = _sym_curve(T, 85.0, 65.0)
    return {
        "key": "wall_pushup",
        "name": "牆壁伏地挺身",
        "category": "upper",
        "description": "面向牆壁，雙手扶牆，彎曲手肘靠近牆面，再推回伸直。",
        "cue": "身體保持一直線，手肘慢慢彎曲，不要聳肩。",
        "angle_series": {
            "左肩": shoulder, "右肩": shoulder,
            "左肘": elbow, "右肘": elbow,
            "左髖": _flat(T, 175.0), "右髖": _flat(T, 175.0),
            "左膝": _flat(T, 175.0), "右膝": _flat(T, 175.0),
        },
    }


def sit_to_stand(T: int = 30) -> Dict:
    knee = _sym_curve(T, 90.0, 175.0)
    hip = _sym_curve(T, 90.0, 175.0)
    return {
        "key": "sit_to_stand",
        "name": "坐到站",
        "category": "lower",
        "description": "由椅子坐姿緩慢站起，站直後再緩慢坐回。",
        "cue": "雙腳與肩同寬，起身時身體略前傾，膝蓋不超過腳尖。",
        "angle_series": {
            "左肩": _flat(T, 25.0), "右肩": _flat(T, 25.0),
            "左肘": _flat(T, 170.0), "右肘": _flat(T, 170.0),
            "左髖": hip, "右髖": hip,
            "左膝": knee, "右膝": knee,
        },
    }


def mini_squat(T: int = 34) -> Dict:
    knee = _sym_curve(T, 175.0, 120.0)
    hip = _sym_curve(T, 175.0, 125.0)
    return {
        "key": "mini_squat",
        "name": "迷你深蹲",
        "category": "lower",
        "description": "站姿雙腳與肩同寬，膝蓋微彎下蹲，再慢慢站直。",
        "cue": "膝蓋朝腳尖方向，背部挺直，幅度不用太深。",
        "angle_series": {
            "左肩": _flat(T, 30.0), "右肩": _flat(T, 30.0),
            "左肘": _flat(T, 170.0), "右肘": _flat(T, 170.0),
            "左髖": hip, "右髖": hip,
            "左膝": knee, "右膝": knee,
        },
    }


def knee_extension(T: int = 30) -> Dict:
    knee = _asym_curve(T, 90.0, 170.0, hold_ratio=0.25)
    return {
        "key": "knee_extension",
        "name": "坐姿膝伸展",
        "category": "lower",
        "description": "坐於椅上，膝蓋緩慢向前伸直抬起至水平，停留 1 秒再放下。",
        "cue": "大腿貼穩椅面，腳背勾起，避免代償。",
        "angle_series": {
            "左肩": _flat(T, 30.0), "右肩": _flat(T, 30.0),
            "左肘": _flat(T, 90.0), "右肘": _flat(T, 90.0),
            "左髖": _flat(T, 90.0), "右髖": _flat(T, 90.0),
            "左膝": knee, "右膝": knee,
        },
    }


def hip_abduction(T: int = 30) -> Dict:
    """站姿單側抬腿（左腿往外抬）。"""
    hip_left = _sym_curve(T, 175.0, 140.0)
    return {
        "key": "hip_abduction",
        "name": "站姿側抬腿",
        "category": "balance",
        "description": "站立扶牆或椅背，單側腿向外側緩慢抬起，再緩慢放下。",
        "cue": "軀幹保持直立不側傾，支撐腿膝蓋微彎。",
        "angle_series": {
            "左肩": _flat(T, 25.0), "右肩": _flat(T, 25.0),
            "左肘": _flat(T, 170.0), "右肘": _flat(T, 170.0),
            "左髖": hip_left, "右髖": _flat(T, 175.0),
            "左膝": _flat(T, 170.0), "右膝": _flat(T, 170.0),
        },
    }


def march_in_place(T: int = 40) -> Dict:
    """原地踏步：兩腿輪流抬膝。"""
    half = T // 2
    left = _sym_curve(half, 175.0, 95.0) + _flat(T - half, 175.0)
    right = _flat(half, 175.0) + _sym_curve(T - half, 175.0, 95.0)
    left_hip = _sym_curve(half, 175.0, 100.0) + _flat(T - half, 175.0)
    right_hip = _flat(half, 175.0) + _sym_curve(T - half, 175.0, 100.0)
    return {
        "key": "march_in_place",
        "name": "原地踏步",
        "category": "balance",
        "description": "站立雙腳與肩同寬，輪流將膝蓋抬高至腰部高度。",
        "cue": "抬膝時腳尖向前，手臂可自然擺動。",
        "angle_series": {
            "左肩": _flat(T, 30.0), "右肩": _flat(T, 30.0),
            "左肘": _flat(T, 160.0), "右肘": _flat(T, 160.0),
            "左髖": left_hip, "右髖": right_hip,
            "左膝": left, "右膝": right,
        },
    }


def seated_march(T: int = 40) -> Dict:
    """坐姿抬膝：兩腿輪流抬起，適合平衡與下肢啟動。"""
    half = T // 2
    left_knee = _sym_curve(half, 95.0, 70.0) + _flat(T - half, 95.0)
    right_knee = _flat(half, 95.0) + _sym_curve(T - half, 95.0, 70.0)
    left_hip = _sym_curve(half, 90.0, 120.0) + _flat(T - half, 90.0)
    right_hip = _flat(half, 90.0) + _sym_curve(T - half, 90.0, 120.0)
    return {
        "key": "seated_march",
        "name": "坐姿抬膝踏步",
        "category": "balance",
        "description": "坐在椅上，左右腳輪流抬膝，像坐著原地踏步。",
        "cue": "身體坐直，抬膝時不要後仰，左右節奏穩定。",
        "angle_series": {
            "左肩": _flat(T, 30.0), "右肩": _flat(T, 30.0),
            "左肘": _flat(T, 90.0), "右肘": _flat(T, 90.0),
            "左髖": left_hip, "右髖": right_hip,
            "左膝": left_knee, "右膝": right_knee,
        },
    }


BUILTIN: Dict[str, Dict] = {
    t["key"]: t for t in (
        arm_raise(), shoulder_abduction(), elbow_flexion(), wall_pushup(),
        sit_to_stand(), mini_squat(), knee_extension(),
        hip_abduction(), march_in_place(), seated_march(),
    )
}


# ---------------- 自訂範本 ----------------
def _slugify(name: str) -> str:
    base = re.sub(r"[^\w一-鿿]+", "_", name).strip("_")
    return (base or "custom") + "_" + str(int(time.time()))


def save_custom(
    name: str,
    description: str,
    cue: str,
    angle_series: Dict[str, List[float]],
    category: str = "custom",
) -> Dict:
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    key = "custom_" + _slugify(name)
    tpl = {
        "key": key,
        "name": name,
        "category": category,
        "description": description,
        "cue": cue,
        "custom": True,
        "created": int(time.time()),
        "angle_series": {k: list(map(float, v)) for k, v in angle_series.items()},
    }
    (CUSTOM_DIR / f"{key}.json").write_text(
        json.dumps(tpl, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tpl


def delete_custom(key: str) -> bool:
    f = CUSTOM_DIR / f"{key}.json"
    if f.exists():
        f.unlink()
        return True
    return False


def load_custom() -> Dict[str, Dict]:
    if not CUSTOM_DIR.exists():
        return {}
    out: Dict[str, Dict] = {}
    for f in sorted(CUSTOM_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "key" in data and "angle_series" in data:
            out[data["key"]] = data
    return out


def all_templates() -> Dict[str, Dict]:
    """內建 + 自訂範本合併。app.py 應呼叫此函式而非讀取 BUILTIN。"""
    merged = dict(BUILTIN)
    merged.update(load_custom())
    return merged


# 向後相容：靜態變數（首次 import 時讀取）
TEMPLATES: Dict[str, Dict] = all_templates()
