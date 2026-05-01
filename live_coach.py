"""
即時 AI 私人教練 — 在 RealtimePoseEngine 之上的教練層。

提供四種能力：
1. 即時計數 (RepCounter)        — 串流式峰谷偵測，在動作未完成時也能算 rep
2. 即時提示 (CueGenerator)      — 從關節角度、ROM、tempo 推導出口語提示
3. 提示節流 (LiveCueQueue)      — 同類別 3 秒內只播 1 次，避免疲勞轟炸
4. 視覺增強 (vlm_async_check)    — 每 5 秒非同步呼叫 Claude Haiku 4.5 給更深度的形體建議

LiveCoach 整合上述，訂閱 RealtimePoseEngine 狀態並產生動作中的教練回饋。

設計取捨：
- 即時規則路徑必須 < 30ms（不阻塞 UI）。複雜推理走非同步 VLM。
- LLM 結果回填時是「補充」不是「主導」：規則提示先講、VLM 之後補充細節。
- 教練語氣由 character_key 驅動 (Cf. coach.CHARACTERS)。
"""
from __future__ import annotations
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Dict, List, Optional, Tuple

import numpy as np


# ============================================================
# 教練常用參數
# ============================================================
class CueKind(Enum):
    REP_COUNT = "rep_count"
    DEPTH = "depth"
    TEMPO = "tempo"
    SAFETY = "safety"
    SYMMETRY = "symmetry"
    ENCOURAGE = "encourage"
    READY = "ready"
    REST = "rest"
    VLM = "vlm"


# 同類別提示之間至少間隔幾秒（避免同一個提醒連珠炮）
CUE_COOLDOWNS_S: Dict[CueKind, float] = {
    CueKind.REP_COUNT: 0.4,
    CueKind.DEPTH: 3.0,
    CueKind.TEMPO: 4.0,
    CueKind.SAFETY: 2.0,    # 安全議題冷卻較短
    CueKind.SYMMETRY: 5.0,
    CueKind.ENCOURAGE: 6.0,
    CueKind.READY: 4.0,
    CueKind.REST: 8.0,
    CueKind.VLM: 8.0,
}


@dataclass
class Cue:
    """單一教練提示，可以同時輸出文字 + 語音 + 浮動條。"""
    kind: CueKind
    text_zh: str
    text_en: str
    timestamp: float = field(default_factory=time.time)
    severity: str = "info"   # info | warn | danger | success
    source: str = "rule"     # rule | vlm | system
    rep_index: Optional[int] = None

    def text(self, lang: str = "zh") -> str:
        return self.text_zh if lang == "zh" else self.text_en


# ============================================================
# 串流式 Rep 計數器
# ============================================================
@dataclass
class RepCounterConfig:
    dominant_joint: str = "left_knee_flex"  # 動作主導關節
    flex_threshold: float = 30.0   # 偏離靜止角度多少視為「進入動作」
    extend_threshold: float = 10.0  # 回到接近靜止視為「完成動作」
    min_rep_duration_s: float = 0.6  # 過短判定為抖動，不算 rep
    max_rep_duration_s: float = 8.0  # 過長判定為靜止，重置狀態
    min_amplitude_deg: float = 15.0  # 動作幅度不足不算


class RepCounter:
    """串流偵測 rep 起點/峰值/終點。

    狀態機：IDLE → ASCENDING → AT_PEAK → DESCENDING → IDLE
    回到 IDLE 時若滿足條件則 emit 一個 rep。
    """

    STATE_IDLE = "idle"
    STATE_ASCENDING = "ascending"
    STATE_DESCENDING = "descending"

    def __init__(self, config: Optional[RepCounterConfig] = None):
        self.cfg = config or RepCounterConfig()
        self._state = self.STATE_IDLE
        self._baseline: Optional[float] = None
        self._rep_start_t: Optional[float] = None
        self._rep_start_v: Optional[float] = None
        self._peak_v: Optional[float] = None
        self._peak_t: Optional[float] = None
        self._rep_count = 0
        self._last_rep: Optional[Tuple[float, float, float]] = None  # (start_t, peak_t, end_t)
        self._rep_durations: Deque[float] = deque(maxlen=10)
        self._rep_amplitudes: Deque[float] = deque(maxlen=10)

    @property
    def count(self) -> int:
        return self._rep_count

    @property
    def avg_duration(self) -> float:
        return float(np.mean(self._rep_durations)) if self._rep_durations else 0.0

    @property
    def last_amplitude(self) -> float:
        return self._rep_amplitudes[-1] if self._rep_amplitudes else 0.0

    def reset(self) -> None:
        self.__init__(self.cfg)

    def update(self, t: float, value: float) -> Optional[int]:
        """Feed a new (timestamp, joint angle) sample.

        Returns the new rep index when a rep just completed, else None.
        """
        if self._baseline is None:
            self._baseline = value
            return None

        # 動態調整 baseline 為近期最小值（避免漂移）
        self._baseline = min(self._baseline, value) if self._state == self.STATE_IDLE else self._baseline
        delta = value - self._baseline

        if self._state == self.STATE_IDLE:
            if delta >= self.cfg.flex_threshold:
                self._state = self.STATE_ASCENDING
                self._rep_start_t = t
                self._rep_start_v = self._baseline
                self._peak_v = value
                self._peak_t = t
        elif self._state == self.STATE_ASCENDING:
            if value > (self._peak_v or value):
                self._peak_v = value
                self._peak_t = t
            # 開始下降（連續低於峰值 5°）
            if (self._peak_v - value) > 5.0:
                self._state = self.STATE_DESCENDING
        elif self._state == self.STATE_DESCENDING:
            if value > (self._peak_v or value):
                # 回升 → 重新標記峰值
                self._peak_v = value
                self._peak_t = t
                self._state = self.STATE_ASCENDING
            elif delta <= self.cfg.extend_threshold:
                # 回到接近 baseline → 完成 rep
                duration = t - (self._rep_start_t or t)
                amplitude = (self._peak_v or 0.0) - (self._rep_start_v or 0.0)
                if (duration >= self.cfg.min_rep_duration_s
                        and duration <= self.cfg.max_rep_duration_s
                        and amplitude >= self.cfg.min_amplitude_deg):
                    self._rep_count += 1
                    self._last_rep = (
                        self._rep_start_t or t, self._peak_t or t, t
                    )
                    self._rep_durations.append(duration)
                    self._rep_amplitudes.append(amplitude)
                    self._reset_active()
                    return self._rep_count
                # 否則視為失敗 attempt（抖動或幅度不足），靜默重置
                self._reset_active()

        # 動作太久沒回到 baseline → 重置
        if (self._rep_start_t and (t - self._rep_start_t) > self.cfg.max_rep_duration_s):
            self._reset_active()

        return None

    def _reset_active(self) -> None:
        self._state = self.STATE_IDLE
        self._rep_start_t = None
        self._rep_start_v = None
        self._peak_v = None
        self._peak_t = None


# ============================================================
# 規則式提示產生器
# ============================================================
@dataclass
class CueGeneratorConfig:
    target_reps: int = 12
    target_rep_duration_s: float = 3.0     # 預期一次 rep 約 3 秒
    tempo_tolerance: float = 0.7           # 與目標 ±70% 內視為合格
    asymmetry_threshold_deg: float = 12.0  # 雙側差超過視為不對稱
    depth_warn_ratio: float = 0.6          # 幅度低於目標 60% 提醒
    target_amplitude_deg: float = 60.0     # 預期動作幅度
    encourage_every_n_reps: int = 3        # 每 N reps 給一次鼓勵
    coach_persona: str = "starbuddy"


class CueGenerator:
    """從 LiveState + RepCounter 推導語意化教練提示。"""

    def __init__(self, config: Optional[CueGeneratorConfig] = None):
        self.cfg = config or CueGeneratorConfig()

    def from_rep_complete(self, rep_index: int,
                           rep_amplitude: float,
                           rep_duration: float) -> List[Cue]:
        cues: List[Cue] = []

        # 計數宣告（每次都報）
        cues.append(Cue(
            kind=CueKind.REP_COUNT,
            text_zh=self._count_phrase_zh(rep_index, self.cfg.target_reps),
            text_en=self._count_phrase_en(rep_index, self.cfg.target_reps),
            severity="success",
            rep_index=rep_index,
        ))

        # 深度檢查
        depth_ratio = rep_amplitude / max(self.cfg.target_amplitude_deg, 1e-3)
        if depth_ratio < self.cfg.depth_warn_ratio:
            cues.append(Cue(
                kind=CueKind.DEPTH,
                text_zh=f"幅度不夠喔（{rep_amplitude:.0f}°），下一下再深一點。",
                text_en=f"Go a bit deeper next rep ({rep_amplitude:.0f}°).",
                severity="warn",
                rep_index=rep_index,
            ))
        elif depth_ratio > 1.15:
            cues.append(Cue(
                kind=CueKind.DEPTH,
                text_zh="深度很到位！",
                text_en="Great depth!",
                severity="success",
                rep_index=rep_index,
            ))

        # Tempo 檢查
        target = self.cfg.target_rep_duration_s
        ratio = rep_duration / target
        if ratio < (1 - self.cfg.tempo_tolerance):
            cues.append(Cue(
                kind=CueKind.TEMPO,
                text_zh="慢一點，控制下放速度。",
                text_en="Slow it down, control the descent.",
                severity="warn",
                rep_index=rep_index,
            ))
        elif ratio > (1 + self.cfg.tempo_tolerance):
            cues.append(Cue(
                kind=CueKind.TEMPO,
                text_zh="加一點節奏，保持流暢。",
                text_en="Pick up the pace, stay fluid.",
                severity="info",
                rep_index=rep_index,
            ))

        # 鼓勵節點
        if (rep_index > 0
                and rep_index % self.cfg.encourage_every_n_reps == 0
                and rep_index < self.cfg.target_reps):
            remaining = self.cfg.target_reps - rep_index
            cues.append(Cue(
                kind=CueKind.ENCOURAGE,
                text_zh=f"做得好！還有 {remaining} 下，呼吸別憋住。",
                text_en=f"Nice! {remaining} reps to go — keep breathing.",
                severity="success",
                rep_index=rep_index,
            ))

        if rep_index >= self.cfg.target_reps:
            cues.append(Cue(
                kind=CueKind.REST,
                text_zh="這組完成！休息 30 秒再開下一組。",
                text_en="Set complete! Rest 30 seconds before the next.",
                severity="success",
                rep_index=rep_index,
            ))

        return cues

    def from_rom_violations(self, violations: List) -> List[Cue]:
        """ROM 違規 → 安全/形體提示。"""
        cues = []
        seen_joints = set()
        for v in violations:
            if v.angle_name in seen_joints:
                continue
            seen_joints.add(v.angle_name)
            zh, en = self._rom_phrase(v)
            cues.append(Cue(
                kind=CueKind.SAFETY,
                text_zh=zh,
                text_en=en,
                severity="danger" if v.severity == "severe" else "warn",
            ))
        return cues

    def from_asymmetry(self, angles: Dict[str, float]) -> Optional[Cue]:
        """檢查雙側差。"""
        pairs = [
            ("left_knee_flex", "right_knee_flex", "膝", "knee"),
            ("left_shoulder_flex_ext", "right_shoulder_flex_ext", "肩", "shoulder"),
            ("left_hip_flex_ext", "right_hip_flex_ext", "髖", "hip"),
            ("left_elbow_flex", "right_elbow_flex", "肘", "elbow"),
        ]
        worst = None
        worst_diff = 0.0
        for left, right, zh_name, en_name in pairs:
            l_val = angles.get(left)
            r_val = angles.get(right)
            if l_val is None or r_val is None:
                continue
            diff = abs(l_val - r_val)
            if diff > worst_diff:
                worst_diff = diff
                worst = (zh_name, en_name, l_val, r_val, diff)

        if worst and worst[4] >= self.cfg.asymmetry_threshold_deg:
            zh_name, en_name, l_val, r_val, diff = worst
            stronger = "左" if l_val > r_val else "右"
            stronger_en = "left" if l_val > r_val else "right"
            return Cue(
                kind=CueKind.SYMMETRY,
                text_zh=f"{stronger}側{zh_name}用得比較多，注意雙側對稱。",
                text_en=f"Your {stronger_en} {en_name} is doing more — keep both sides equal.",
                severity="warn",
            )
        return None

    @staticmethod
    def _count_phrase_zh(idx: int, target: int) -> str:
        if idx >= target:
            return f"{idx}！這組完成。"
        if idx == target - 1:
            return f"{idx}！剩 1 下。"
        return str(idx)

    @staticmethod
    def _count_phrase_en(idx: int, target: int) -> str:
        if idx >= target:
            return f"{idx}! Set done."
        if idx == target - 1:
            return f"{idx}! One more."
        return str(idx)

    @staticmethod
    def _rom_phrase(v) -> Tuple[str, str]:
        """ROM 違規 → 中英文提示。"""
        joint_zh = {
            "left_knee_flex": "左膝", "right_knee_flex": "右膝",
            "left_shoulder_flex_ext": "左肩", "right_shoulder_flex_ext": "右肩",
            "left_hip_flex_ext": "左髖", "right_hip_flex_ext": "右髖",
            "trunk_forward_bend": "軀幹",
        }.get(v.angle_name, v.angle_name)
        joint_en = v.angle_name.replace("_", " ").replace("flex", "").strip().title()
        if v.severity == "severe":
            zh = f"⚠ {joint_zh}超出安全範圍，先停下來。"
            en = f"⚠ {joint_en} past safe range — pause."
        else:
            zh = f"{joint_zh}快到極限，慢一點。"
            en = f"{joint_en} near limit, ease up."
        return zh, en


# ============================================================
# 提示節流佇列
# ============================================================
class LiveCueQueue:
    """同類別冷卻；確保提示不會連珠炮，且 SAFETY 永遠優先。"""

    def __init__(self, history_max: int = 50):
        self._last_emit: Dict[CueKind, float] = {}
        self._history: Deque[Cue] = deque(maxlen=history_max)
        self._pending: Deque[Cue] = deque()
        self._lock = threading.Lock()

    def offer(self, cue: Cue) -> bool:
        """嘗試入列。回傳 True = 接受並排播，False = 被冷卻擋住。"""
        cooldown = CUE_COOLDOWNS_S.get(cue.kind, 3.0)
        # 安全議題不會被同類冷卻擋住超過 1 秒
        if cue.kind == CueKind.SAFETY:
            cooldown = min(cooldown, 1.0)

        with self._lock:
            last = self._last_emit.get(cue.kind, 0.0)
            if (cue.timestamp - last) < cooldown:
                return False
            self._last_emit[cue.kind] = cue.timestamp
            self._pending.append(cue)
            self._history.append(cue)
            return True

    def drain_pending(self) -> List[Cue]:
        with self._lock:
            items = list(self._pending)
            self._pending.clear()
            return items

    def history(self, n: int = 20) -> List[Cue]:
        with self._lock:
            return list(self._history)[-n:]


# ============================================================
# 非同步 VLM 補強 (Claude Haiku 4.5)
# ============================================================
@dataclass
class VLMCheckConfig:
    interval_s: float = 5.0
    enabled: bool = True
    exercise_name: str = ""
    lang: str = "zh"


class VLMAsyncChecker:
    """每 interval_s 秒抓一張當前畫面送 Claude Haiku 4.5，回填教練提示。"""

    def __init__(self, frame_provider: Callable[[], Optional[np.ndarray]],
                 cue_queue: LiveCueQueue,
                 config: Optional[VLMCheckConfig] = None):
        self._provider = frame_provider
        self._queue = cue_queue
        self.cfg = config or VLMCheckConfig()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.cfg.enabled:
            return
        try:
            from vlm_feedback import is_available
            if not is_available():
                return
        except ImportError:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop,
                                         daemon=True,
                                         name="vlm-async-check")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.cfg.interval_s)
            if self._stop.is_set():
                break
            frame = self._safe_frame()
            if frame is None:
                continue
            cue = self._call_vlm(frame)
            if cue:
                self._queue.offer(cue)

    def _safe_frame(self) -> Optional[np.ndarray]:
        try:
            return self._provider()
        except Exception:
            return None

    def _call_vlm(self, frame: np.ndarray) -> Optional[Cue]:
        try:
            from vlm_feedback import get_feedback
        except ImportError:
            return None
        try:
            feedback = get_feedback(
                keyframes=[frame],
                form_analysis=None,
                exercise_name=self.cfg.exercise_name,
                lang=self.cfg.lang,
            )
        except Exception:
            return None
        if not feedback:
            return None

        # 取最重要的 issue 或 encouragement 變成提示
        if feedback.issues:
            top = feedback.issues[0]
            sev = str(top.get("severity", "minor"))
            severity_ui = {
                "major": "danger", "moderate": "warn", "minor": "info"
            }.get(sev, "info")
            zh = f"{top.get('joint', '')}：{top.get('description', '')} → {top.get('fix', '')}"
            en = f"{top.get('joint', '')}: {top.get('description', '')} → {top.get('fix', '')}"
            return Cue(
                kind=CueKind.VLM,
                text_zh=zh.strip(" ：→"),
                text_en=en.strip(" :→"),
                severity=severity_ui,
                source="vlm",
            )
        if feedback.encouragement:
            return Cue(
                kind=CueKind.VLM,
                text_zh=feedback.encouragement,
                text_en=feedback.encouragement,
                severity="success",
                source="vlm",
            )
        return None


# ============================================================
# 整合層：LiveCoach
# ============================================================
@dataclass
class LiveCoachConfig:
    rep: RepCounterConfig = field(default_factory=RepCounterConfig)
    cues: CueGeneratorConfig = field(default_factory=CueGeneratorConfig)
    vlm: VLMCheckConfig = field(default_factory=VLMCheckConfig)
    speak: bool = True
    lang: str = "zh"


class LiveCoach:
    """在每幀 LiveState 上跑 rep 偵測 + 規則提示，並啟動 VLM 補強執行緒。

    使用方式：
        coach = LiveCoach(frame_provider=lambda: latest_frame)
        coach.start()
        ...
        for state in engine_states:
            new_cues = coach.observe(state)
            for cue in new_cues:
                render(cue)
        coach.stop()
    """

    def __init__(self,
                 frame_provider: Optional[Callable[[], Optional[np.ndarray]]] = None,
                 config: Optional[LiveCoachConfig] = None,
                 voice: Optional[object] = None):
        self.cfg = config or LiveCoachConfig()
        self.rep_counter = RepCounter(self.cfg.rep)
        self.cue_gen = CueGenerator(self.cfg.cues)
        self.queue = LiveCueQueue()
        self._frame_provider = frame_provider
        self._voice = voice
        self._vlm: Optional[VLMAsyncChecker] = None
        self._started_at: Optional[float] = None
        self._last_state_t: float = 0.0

    @property
    def session_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, self._last_state_t - self._started_at)

    def start(self) -> None:
        self._started_at = time.time()
        # 開場提示
        greet = Cue(
            kind=CueKind.READY,
            text_zh="準備好就開始，我會跟著你計數和提醒。",
            text_en="Start when you're ready — I'll count and cue you.",
            severity="info",
            source="system",
        )
        self.queue.offer(greet)

        if self._frame_provider:
            self._vlm = VLMAsyncChecker(
                frame_provider=self._frame_provider,
                cue_queue=self.queue,
                config=self.cfg.vlm,
            )
            self._vlm.start()

    def stop(self) -> None:
        if self._vlm:
            self._vlm.stop()
            self._vlm = None

    def reset(self) -> None:
        self.rep_counter.reset()
        self._started_at = time.time()

    def update_target_reps(self, n: int) -> None:
        self.cfg.cues.target_reps = max(1, int(n))

    def update_dominant_joint(self, joint: str) -> None:
        self.cfg.rep.dominant_joint = joint
        self.rep_counter.cfg.dominant_joint = joint

    def observe(self, state) -> List[Cue]:
        """每幀呼叫一次，回傳這一幀新接受的提示（已通過冷卻）。"""
        self._last_state_t = state.timestamp or time.time()
        smoothed = state.angles_smoothed or {}

        # 1) ROM 違規 → 立即安全提示
        if state.rom_violations:
            for cue in self.cue_gen.from_rom_violations(state.rom_violations):
                self.queue.offer(cue)

        # 2) 不對稱 → 警示
        sym_cue = self.cue_gen.from_asymmetry(smoothed)
        if sym_cue:
            self.queue.offer(sym_cue)

        # 3) Rep 計數
        joint = self.cfg.rep.dominant_joint
        val = smoothed.get(joint)
        if val is not None:
            new_rep = self.rep_counter.update(state.timestamp or time.time(),
                                                float(val))
            if new_rep is not None:
                amp = self.rep_counter.last_amplitude
                dur = (self.rep_counter._rep_durations[-1]
                       if self.rep_counter._rep_durations else 0.0)
                for cue in self.cue_gen.from_rep_complete(new_rep, amp, dur):
                    self.queue.offer(cue)

        # 取出本輪通過冷卻的新提示
        new_cues = self.queue.drain_pending()
        if self.cfg.speak and self._voice:
            for cue in new_cues:
                self._speak(cue)
        return new_cues

    def history(self, n: int = 20) -> List[Cue]:
        return self.queue.history(n)

    def _speak(self, cue: Cue) -> None:
        """非阻塞 TTS 播放。失敗靜默忽略。"""
        if not self._voice:
            return
        try:
            text = cue.text(self.cfg.lang)
            speak_fn = getattr(self._voice, "speak", None)
            if callable(speak_fn):
                speak_fn(text, block=False)
            else:
                # 退回到 tts.speak 直接呼叫
                import tts
                if hasattr(tts, "speak"):
                    tts.speak(text, lang=self.cfg.lang, block=False)
        except Exception:
            pass


# ============================================================
# 動作選擇 → LiveCoach 預設值對照表
# ============================================================
EXERCISE_PRESETS: Dict[str, Dict] = {
    "arm_raise": {
        "dominant_joint": "left_shoulder_flex_ext",
        "target_amplitude_deg": 120.0,
        "target_rep_duration_s": 3.5,
    },
    "shoulder_abduction": {
        "dominant_joint": "left_shoulder_abd_add",
        "target_amplitude_deg": 70.0,
        "target_rep_duration_s": 3.0,
    },
    "elbow_flexion": {
        "dominant_joint": "left_elbow_flex",
        "target_amplitude_deg": 100.0,
        "target_rep_duration_s": 2.5,
    },
    "mini_squat": {
        "dominant_joint": "left_knee_flex",
        "target_amplitude_deg": 60.0,
        "target_rep_duration_s": 3.0,
    },
    "sit_to_stand": {
        "dominant_joint": "left_knee_flex",
        "target_amplitude_deg": 90.0,
        "target_rep_duration_s": 3.5,
    },
    "knee_extension": {
        "dominant_joint": "left_knee_flex",
        "target_amplitude_deg": 70.0,
        "target_rep_duration_s": 2.5,
    },
    "hip_abduction": {
        "dominant_joint": "left_hip_abd_add",
        "target_amplitude_deg": 30.0,
        "target_rep_duration_s": 2.5,
    },
    "march_in_place": {
        "dominant_joint": "left_hip_flex_ext",
        "target_amplitude_deg": 70.0,
        "target_rep_duration_s": 1.5,
    },
}


def preset_for(exercise_key: str) -> Dict:
    """安全取出預設；未知動作回傳通用設定。"""
    return EXERCISE_PRESETS.get(exercise_key, {
        "dominant_joint": "left_knee_flex",
        "target_amplitude_deg": 60.0,
        "target_rep_duration_s": 3.0,
    })


def build_coach(exercise_key: str,
                target_reps: int = 12,
                lang: str = "zh",
                frame_provider: Optional[Callable] = None,
                voice: Optional[object] = None,
                vlm_enabled: bool = True) -> LiveCoach:
    """從動作 key 建立 LiveCoach（套上預設值）。"""
    p = preset_for(exercise_key)
    cfg = LiveCoachConfig(
        rep=RepCounterConfig(dominant_joint=p["dominant_joint"]),
        cues=CueGeneratorConfig(
            target_reps=target_reps,
            target_amplitude_deg=p["target_amplitude_deg"],
            target_rep_duration_s=p["target_rep_duration_s"],
        ),
        vlm=VLMCheckConfig(
            enabled=vlm_enabled,
            exercise_name=exercise_key,
            lang=lang,
        ),
        lang=lang,
    )
    return LiveCoach(frame_provider=frame_provider,
                      config=cfg, voice=voice)
