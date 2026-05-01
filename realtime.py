"""
即時鏡頭指導模組（streamlit-webrtc）。

- `RealtimeCoach` 為 VideoProcessor，每張影格做：
    1. MediaPipe 抽取 3D 姿態
    2. 計算當前關節角度
    3. 依範本動作的主導關節進度判斷階段
    4. 比對其他關節是否落在預期範圍，產生短方向提示
    5. 只把提示詞與所選教練提示牌疊到影格上

訊息範例：「左手抬高一點」、「右膝慢慢彎曲」

若 streamlit-webrtc 未安裝，模組仍可 import；UI 會降級為「未啟用」訊息。
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List

import cv2
import numpy as np

import coach as coach_mod
import pose_estimator as pe
import scoring
import visualizer as viz

try:
    from streamlit_webrtc import VideoProcessorBase  # type: ignore
    import av  # type: ignore
    WEBRTC_OK = True
except Exception:  # pragma: no cover
    WEBRTC_OK = False

    class VideoProcessorBase:  # type: ignore[no-redef]
        """Placeholder when streamlit-webrtc isn't installed."""


# 每個關節的方向提示。第 1 個訊息表示「角度太小、需要增加」，
# 第 2 個訊息表示「角度太大、需要降低」。
_HINTS: Dict[str, tuple[str, str]] = {
    "左肩": ("左手抬高一點", "左手慢慢放下"),
    "右肩": ("右手抬高一點", "右手慢慢放下"),
    "左肘": ("左手伸直一點", "左手肘放鬆彎曲"),
    "右肘": ("右手伸直一點", "右手肘放鬆彎曲"),
    "左髖": ("身體挺直一點", "身體微微前傾"),
    "右髖": ("身體挺直一點", "身體微微前傾"),
    "左膝": ("左膝伸直一點", "左膝慢慢彎曲"),
    "右膝": ("右膝伸直一點", "右膝慢慢彎曲"),
}


_TEMPLATE_GUIDES: Dict[str, dict] = {
    "arm_raise": {
        "title": "雙手上舉",
        "start": "雙手自然放在身體兩側，背部挺直。",
        "positive": ("⬆", "雙手往上抬", "慢慢抬到頭頂附近，手肘保持伸直。"),
        "negative": ("⬇", "雙手往下放", "用一樣慢的速度放回身體兩側。"),
        "hold": ("⏸", "上方停一下", "肩膀放鬆，不要聳肩。"),
    },
    "shoulder_abduction": {
        "title": "肩關節側平舉",
        "start": "雙手放在身體兩側，掌心朝下。",
        "positive": ("⬆", "手臂往外抬", "往兩側打開到肩膀高度。"),
        "negative": ("⬇", "手臂慢慢放下", "放回身體兩側，速度保持穩定。"),
        "hold": ("⏸", "肩高停一下", "手臂打開，身體不要側傾。"),
    },
    "elbow_flexion": {
        "title": "坐姿手肘彎曲",
        "start": "上臂貼近身體，肩膀放鬆。",
        "positive": ("➡", "手肘伸直", "前臂慢慢往下回到伸直。"),
        "negative": ("↩", "手肘彎曲", "前臂慢慢彎起，手肘不要離開身體。"),
        "hold": ("⏸", "穩住上臂", "上臂貼近身體，避免晃動。"),
    },
    "wall_pushup": {
        "title": "牆壁伏地挺身",
        "start": "面向牆壁，雙手扶牆，身體保持一直線。",
        "positive": ("➡", "推回伸直", "手肘伸直，把身體推離牆面。"),
        "negative": ("↩", "靠近牆面", "手肘慢慢彎曲，身體靠近牆。"),
        "hold": ("⏸", "身體一直線", "腹部微收，不要塌腰。"),
    },
    "sit_to_stand": {
        "title": "坐到站",
        "start": "坐在椅子前緣，雙腳與肩同寬。",
        "positive": ("⬆", "慢慢站直", "膝蓋和髖部一起伸直。"),
        "negative": ("⬇", "慢慢坐回", "屁股往後找椅子，速度放慢。"),
        "hold": ("⏸", "站穩或坐穩", "重心保持在雙腳中間。"),
    },
    "mini_squat": {
        "title": "迷你深蹲",
        "start": "站姿雙腳與肩同寬，背部挺直。",
        "positive": ("⬆", "站直", "慢慢把膝蓋伸直回到站姿。"),
        "negative": ("⬇", "慢慢蹲低", "膝蓋朝腳尖方向，幅度不用太深。"),
        "hold": ("⏸", "重心穩住", "背部挺直，膝蓋不要內夾。"),
    },
    "knee_extension": {
        "title": "坐姿膝伸展",
        "start": "坐穩椅面，大腿貼住椅子。",
        "positive": ("➡", "膝蓋伸直", "小腿慢慢往前抬到接近水平。"),
        "negative": ("↩", "膝蓋彎曲放下", "小腿慢慢回到起始位置。"),
        "hold": ("⏸", "伸直停一下", "腳背勾起，大腿不要離開椅面。"),
    },
    "hip_abduction": {
        "title": "站姿側抬腿",
        "start": "扶牆或椅背站穩，軀幹保持直立。",
        "positive": ("⬇", "腿慢慢放回", "抬起的腿慢慢回到身體旁邊。"),
        "negative": ("⬆", "側抬腿", "腿往外側抬，身體不要歪。"),
        "hold": ("⏸", "軀幹保持直", "支撐腳踩穩，不要晃。"),
    },
    "march_in_place": {
        "title": "原地踏步",
        "start": "站穩後左右腳輪流抬膝。",
        "positive": ("⬇", "腳放回地面", "腳掌穩穩踩回地面。"),
        "negative": ("⬆", "抬膝", "膝蓋往上抬，腳尖朝前。"),
        "hold": ("⏸", "換腳準備", "身體保持直立，節奏穩定。"),
    },
    "seated_march": {
        "title": "坐姿抬膝踏步",
        "start": "坐直，雙腳踩地。",
        "positive": ("⬆", "抬膝", "膝蓋往上抬，身體不要後仰。"),
        "negative": ("⬇", "腳放下", "腳慢慢踩回地面。"),
        "hold": ("⏸", "換腳準備", "坐直，左右節奏穩定。"),
    },
}


def determine_phase(current_dominant: float,
                    template_dominant: List[float]) -> int:
    """以最近距離匹配，判斷使用者目前處於範本的哪一個階段（幀索引）。"""
    arr = np.asarray(template_dominant, dtype=np.float32)
    return int(np.argmin(np.abs(arr - current_dominant)))


def template_guidance_steps(template: dict, lang: str = "zh") -> list[dict]:
    guide = _TEMPLATE_GUIDES.get(template.get("key", ""), {})
    if not guide:
        return [
            {
                "icon": "1",
                "title": "準備姿勢" if lang == "zh" else "Setup",
                "detail": template.get("cue", ""),
            },
            {
                "icon": "2",
                "title": "跟著提示慢慢做" if lang == "zh" else "Follow cues",
                "detail": template.get("description", ""),
            },
        ]
    if lang == "en":
        return [
            {"icon": "1", "title": "Setup", "detail": guide["start"]},
            {"icon": guide["positive"][0], "title": guide["positive"][1], "detail": guide["positive"][2]},
            {"icon": guide["negative"][0], "title": guide["negative"][1], "detail": guide["negative"][2]},
        ]
    return [
        {"icon": "1", "title": "準備姿勢", "detail": guide["start"]},
        {"icon": guide["positive"][0], "title": guide["positive"][1], "detail": guide["positive"][2]},
        {"icon": guide["negative"][0], "title": guide["negative"][1], "detail": guide["negative"][2]},
    ]


def motion_guide(template: dict, phase: int, dominant_series: List[float],
                 lang: str = "zh") -> dict:
    """依範本進度產生當下的動作節奏指導。"""
    total = max(1, len(dominant_series))
    i = max(0, min(phase, total - 1))
    left = max(0, i - 2)
    right = min(total - 1, i + 2)
    slope = float(dominant_series[right] - dominant_series[left])
    guide = _TEMPLATE_GUIDES.get(template.get("key", ""), {})
    if abs(slope) < 2.0:
        icon, action, detail = guide.get(
            "hold",
            ("", "穩住", "停一下，不要急。"),
        )
    elif slope > 0:
        icon, action, detail = guide.get(
            "positive",
            ("", "慢慢做到位", "跟著節奏，不要急。"),
        )
    else:
        icon, action, detail = guide.get(
            "negative",
            ("", "慢慢回來", "速度放慢一點。"),
        )
    pct = int(round((i + 1) / total * 100))
    if lang == "en":
        # Existing project mostly stores template text in Chinese. Keep action
        # labels readable rather than pretending full translation coverage.
        voice = _compact_voice_text(action, detail, lang)
    else:
        voice = _compact_voice_text(action, detail, lang)
    return {
        "icon": icon,
        "action": action,
        "detail": detail,
        "percent": pct,
        "voice": voice,
    }


def live_feedback(
    current_angles: Dict[str, float],
    template: dict,
    phase: int,
    threshold: float = 12.0,
    max_msgs: int = 3,
) -> List[str]:
    """產生即時方向提示（中文）。最多 max_msgs 條，依偏差大小排序。"""
    cands: list[tuple[float, str]] = []
    for joint, target_series in template["angle_series"].items():
        if joint not in current_angles:
            continue
        target = float(target_series[phase])
        actual = current_angles[joint]
        diff = actual - target
        if abs(diff) < threshold:
            continue
        hints = _HINTS.get(joint, ("調整", "調整"))
        msg = hints[0] if diff < 0 else hints[1]
        cands.append((abs(diff), msg))
    cands.sort(reverse=True)
    return [m for _, m in cands[:max_msgs]]


# ============================================================
# RealtimeCoach
# ============================================================
class RealtimeCoach(VideoProcessorBase):
    """每張影格：抽 pose → 比對範本 → 在影格上疊加指導。"""

    def __init__(self, template: dict, threshold: float = 12.0,
                 buffer_max: int = 600, voice_enabled: bool = False,
                 lang: str = "zh", voice_cooldown: float = 4.0,
                 character_key: str | None = None):
        self.template = template
        self.threshold = threshold
        self.estimator = pe.PoseEstimator(min_detection_conf=0.5)
        self.lang = lang
        self.voice_enabled = voice_enabled
        self.voice_cooldown = voice_cooldown
        self.character_key = character_key or coach_mod.DEFAULT_CHARACTER
        self._voice = None
        if voice_enabled:
            try:
                from tts import VoiceGuide
                vg = VoiceGuide(lang=lang, rate=142)
                if vg.available:
                    self._voice = vg
            except Exception:
                self._voice = None
        self._last_voice_ts: float = 0.0
        self._last_voice_sig: str = ""

        self._lock = threading.Lock()
        self.last_phase: int = 0
        self.last_score: float = 0.0
        self.last_msgs: List[str] = []
        self.last_guide: dict = {}
        self.fps: float = 0.0
        self._frame_times: list[float] = []

        # 暫存最近 buffer_max 幀的 3D 關鍵點，供結束時跑完整 DTW 評分
        self._buffer_max = buffer_max
        self._kp_buffer: list[np.ndarray] = []
        # 最近一張影格與其 2D 關鍵點，供結果頁顯示骨架
        self.last_frame: np.ndarray | None = None
        self.last_image_kp: np.ndarray | None = None
        self.session_start: float | None = None
        self.frame_count: int = 0

        self._dom_joint = scoring._dominant_joint(  # noqa: SLF001
            {k: np.asarray(v, dtype=np.float32)
             for k, v in template["angle_series"].items()},
            exercise_hint=template.get("key"),
        )
        self._dom_series = list(template["angle_series"][self._dom_joint])

    # 對外狀態快照（供 Streamlit 主畫面讀取）
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "phase": self.last_phase,
                "phase_total": len(self._dom_series),
                "score": self.last_score,
                "msgs": list(self.last_msgs),
                "guide": dict(self.last_guide),
                "fps": self.fps,
            }

    def process_frame(self, img_bgr: np.ndarray) -> np.ndarray:
        """獨立可呼叫的處理函式（亦可不透過 webrtc 使用）。"""
        if self.session_start is None:
            self.session_start = time.time()
        self.frame_count += 1
        kp = self.estimator.extract(img_bgr)
        if kp is None:
            return _draw_status_banner(
                img_bgr, "未偵測到人體，請站到鏡頭前",
                bg=(0, 80, 200),
            )
        # 暫存供結束時評分使用（環形緩衝）
        self._kp_buffer.append(kp["world"])
        if len(self._kp_buffer) > self._buffer_max:
            self._kp_buffer.pop(0)

        angles = scoring.pose_to_angles(kp["world"])
        phase = determine_phase(
            angles.get(self._dom_joint, 0.0),
            self._dom_series,
        )
        msgs = live_feedback(angles, self.template, phase, self.threshold)
        guide = motion_guide(self.template, phase, self._dom_series, self.lang)
        self._maybe_speak(msgs, guide)

        joint_scores: Dict[str, Dict[str, float]] = {}
        for j, target_series in self.template["angle_series"].items():
            if j not in angles:
                continue
            target = float(target_series[phase])
            dev = abs(angles[j] - target)
            joint_scores[j] = {
                "max_dev": dev, "mean_dev": dev, "samples": 1,
            }

        prompt = _primary_prompt(msgs, guide, self.lang)
        overlay = _draw_clean_prompt_overlay(
            img_bgr.copy(),
            prompt=prompt,
            guide=guide,
            character_key=self.character_key,
            lang=self.lang,
        )

        # 更新共享狀態
        if joint_scores:
            mean_dev = float(np.mean(
                [v["max_dev"] for v in joint_scores.values()]
            ))
        else:
            mean_dev = 0.0
        with self._lock:
            self.last_phase = phase
            self.last_msgs = msgs
            self.last_guide = guide
            self.last_score = max(0.0, 100.0 - mean_dev)
            self.last_frame = img_bgr.copy()
            self.last_image_kp = kp["image"].copy()
        return overlay

    def session_seconds(self) -> float:
        if self.session_start is None:
            return 0.0
        return time.time() - self.session_start

    def flush_buffer(self) -> list:
        """回傳並清空關鍵點暫存區，供結束後做完整 DTW 評分。"""
        with self._lock:
            buf = list(self._kp_buffer)
            self._kp_buffer.clear()
            self.session_start = None
            self.frame_count = 0
        return buf

    if WEBRTC_OK:
        def recv(self, frame):  # type: ignore[override]
            t0 = time.time()
            img = frame.to_ndarray(format="bgr24")
            overlay = self.process_frame(img)
            self._frame_times.append(time.time() - t0)
            if len(self._frame_times) > 30:
                self._frame_times.pop(0)
            mean_dt = float(np.mean(self._frame_times))
            if mean_dt > 1e-6:
                self.fps = 1.0 / mean_dt
            else:
                self.fps = 0.0
            return av.VideoFrame.from_ndarray(overlay, format="bgr24")

    def _maybe_speak(self, msgs: List[str], guide: dict) -> None:
        if not self._voice:
            return
        now = time.time()
        if now - self._last_voice_ts < self.voice_cooldown:
            return
        if msgs:
            text = _voice_text(msgs[0])
        else:
            text = guide.get("voice") or (
                "很好，慢慢來"
                if self.lang == "zh" else "Good. Take it slow."
            )
        self._last_voice_ts = now
        self._last_voice_sig = text
        self._voice.say(text)


# ============================================================
# 影格繪製工具
# ============================================================
def _ios_pil_font(size: int):
    """重用 visualizer 內已實作的中文字型尋找邏輯。"""
    try:
        return viz._find_font(size)  # type: ignore[attr-defined]  # noqa: SLF001
    except Exception:  # pragma: no cover
        from PIL import ImageFont
        return ImageFont.load_default()


def _voice_text(msg: str) -> str:
    """把畫面提示轉成 TTS 友善文字，例如移除箭頭與角度。"""
    for token in ("⬆", "⬇", "➡", "↩", "✓", "⏸"):
        msg = msg.replace(token, "")
    msg = msg.split("(", 1)[0]
    return msg.strip()


def _compact_voice_text(action: str, detail: str, lang: str) -> str:
    """把長教學句壓成不急促的一句語音。"""
    action = _voice_text(action)
    detail = _voice_text(detail)
    if lang == "zh":
        if action in {"穩住", "保持穩定"}:
            return "穩住，慢慢呼吸"
        if "上" in action or "抬" in action:
            return "慢慢抬高"
        if "下" in action or "放" in action:
            return "慢慢放下"
        if "伸直" in action:
            return "慢慢伸直"
        if "彎" in action:
            return "慢慢彎曲"
        return action or detail or "慢慢來"
    return action or detail or "Take it slow"


def _primary_prompt(msgs: List[str], guide: dict, lang: str) -> str:
    if msgs:
        return _voice_text(msgs[0])
    action = _voice_text(str(guide.get("action", "")))
    if action:
        return action
    return "很好，慢慢來" if lang == "zh" else "Good. Take it slow."


def _hex_to_rgb(hex_color: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    try:
        h = hex_color.strip().lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return fallback


def _draw_clean_prompt_overlay(
    img: np.ndarray,
    prompt: str,
    guide: dict,
    character_key: str | None,
    lang: str = "zh",
) -> np.ndarray:
    """Draw a FaceTime-style cue card; no skeleton, angles, or coach figure."""
    from PIL import Image, ImageDraw

    h, w = img.shape[:2]
    base = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    char = coach_mod.get_character(character_key)
    c1 = _hex_to_rgb(char.get("color", "#007aff"), (0, 122, 255))

    font_label = _ios_pil_font(max(14, int(w * 0.018)))
    font_prompt = _ios_pil_font(max(32, int(w * 0.058)))
    font_detail = _ios_pil_font(max(16, int(w * 0.022)))

    margin = max(20, int(w * 0.03))
    card_w = min(w - margin * 2, max(420, int(w * 0.72)))
    card_h = max(124, int(h * 0.2))
    x1 = (w - card_w) // 2
    y2 = h - margin
    y1 = y2 - card_h

    # Main cue card: dark translucent, FaceTime-like, intentionally minimal.
    draw.rounded_rectangle(
        [x1, y1, x1 + card_w, y2],
        radius=18,
        fill=(18, 18, 20, 212),
        outline=(255, 255, 255, 42),
        width=1,
    )
    name = char["name_zh"] if lang == "zh" else char["name_en"]
    label = f"{name} · {'即時提示' if lang == 'zh' else 'Live cue'}"
    dot_x = x1 + 24
    dot_y = y1 + 28
    draw.ellipse([dot_x, dot_y, dot_x + 10, dot_y + 10], fill=(*c1, 255))
    draw.text((dot_x + 18, y1 + 19), label, fill=(235, 235, 245, 205), font=font_label)

    prompt = prompt.strip()[:18]
    pbox = draw.textbbox((0, 0), prompt, font=font_prompt)
    draw.text(
        (
            x1 + (card_w - (pbox[2] - pbox[0])) / 2,
            y1 + card_h * 0.36,
        ),
        prompt,
        fill=(255, 255, 255, 248),
        font=font_prompt,
    )

    detail = str(guide.get("detail") or guide.get("voice") or "").strip()[:26]
    if detail:
        dbox = draw.textbbox((0, 0), detail, font=font_detail)
        draw.text(
            (
                x1 + (card_w - (dbox[2] - dbox[0])) / 2,
                y1 + card_h * 0.68,
            ),
            detail,
            fill=(235, 235, 245, 175),
            font=font_detail,
        )

    pct = int(guide.get("percent", 0))
    if pct:
        pct = max(0, min(100, pct))
        bar_x1 = x1 + 24
        bar_x2 = x1 + card_w - 24
        bar_y = y2 - 20
        draw.rounded_rectangle([bar_x1, bar_y, bar_x2, bar_y + 6], radius=3, fill=(255, 255, 255, 46))
        draw.rounded_rectangle(
            [bar_x1, bar_y, bar_x1 + int((bar_x2 - bar_x1) * pct / 100), bar_y + 6],
            radius=3,
            fill=(*c1, 255),
        )

    composed = Image.alpha_composite(base, layer).convert("RGB")
    return cv2.cvtColor(np.array(composed), cv2.COLOR_RGB2BGR)


def _draw_prompts(
    img: np.ndarray,
    msgs: List[str],
    phase: int,
    phase_total: int,
    guide: dict | None = None,
) -> np.ndarray:
    """在影格頂部畫毛玻璃風格指導橫幅（含進度條）。"""
    h, w = img.shape[:2]

    # 計算橫幅高度（依訊息行數）
    if not msgs:
        if guide:
            return _draw_status_banner(
                img,
                f"{guide.get('icon', '✓')} {guide.get('action', '動作良好')}："
                f"{guide.get('detail', '保持節奏')}",
                bg=(36, 158, 92),
            )
        return _draw_status_banner(
            img, "✓ 動作良好，繼續保持！", bg=(36, 158, 92),
        )

    rows = min(3, len(msgs))
    banner_h = 64 + rows * 40 + (34 if guide else 0)

    # 半透明白底（使用 cv2 alpha blend）
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (255, 255, 255), -1)
    blended = cv2.addWeighted(overlay, 0.86, img, 0.14, 0)

    # PIL 繪文字（支援中文/箭頭）
    from PIL import Image, ImageDraw

    pil = Image.fromarray(cv2.cvtColor(blended, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font_msg = _ios_pil_font(26)
    font_meta = _ios_pil_font(16)

    # 進度條
    prog = phase / max(1, phase_total - 1)
    draw.text(
        (24, 18),
        f"進度  {phase + 1} / {phase_total}",
        fill=(50, 50, 60), font=font_meta,
    )
    bar_x, bar_y = 200, 24
    bar_w = w - bar_x - 24
    draw.rounded_rectangle(
        [bar_x, bar_y, bar_x + bar_w, bar_y + 10],
        radius=5, fill=(228, 228, 232),
    )
    draw.rounded_rectangle(
        [bar_x, bar_y,
         bar_x + max(8, int(bar_w * prog)), bar_y + 10],
        radius=5, fill=(0, 122, 255),
    )

    # 訊息（紅色文字）
    y = 56
    for msg in msgs[:3]:
        draw.text((24, y), msg, fill=(255, 59, 48), font=font_msg)
        y += 40
    if guide:
        draw.text(
            (24, y + 2),
            f"指導：{guide.get('icon', '')} {guide.get('action', '')}",
            fill=(0, 122, 255), font=font_meta,
        )

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _draw_status_banner(
    img: np.ndarray,
    text: str,
    bg: tuple[int, int, int] = (52, 199, 89),
) -> np.ndarray:
    h, w = img.shape[:2]
    from PIL import Image, ImageDraw

    base = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _ios_pil_font(max(22, int(w * 0.036)))
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x = max(22, int(w * 0.025))
    pad_y = 16
    box_w = min(w - 40, tw + pad_x * 2)
    box_h = th + pad_y * 2
    x1 = (w - box_w) // 2
    y1 = max(18, int(h * 0.06))
    draw.rounded_rectangle(
        [x1, y1, x1 + box_w, y1 + box_h],
        radius=18,
        fill=(18, 18, 20, 218),
        outline=(255, 255, 255, 45),
        width=1,
    )
    accent = (bg[2], bg[1], bg[0])
    draw.rounded_rectangle(
        [x1 + 12, y1 + 12, x1 + 18, y1 + box_h - 12],
        radius=3,
        fill=(*accent, 255),
    )
    draw.text(
        (x1 + max(28, pad_x), y1 + pad_y - 2),
        text,
        fill=(255, 255, 255, 245),
        font=font,
    )
    composed = Image.alpha_composite(base, layer).convert("RGB")
    return cv2.cvtColor(np.array(composed), cv2.COLOR_RGB2BGR)
