"""
離線語音回饋（pyttsx3，跨平台 TTS）。

pyttsx3 在 Windows 使用 SAPI5、macOS 使用 NSSpeechSynthesizer、Linux 使用 eSpeak。
若系統無法初始化（如 CI、無音效），`available` 會是 False，呼叫端會靜默略過。
"""
from __future__ import annotations

import base64
import asyncio
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import List, Optional

try:
    import pyttsx3
    PYTTSX_OK = True
except Exception:  # pragma: no cover
    PYTTSX_OK = False

try:
    import edge_tts
    EDGE_TTS_OK = True
except Exception:  # pragma: no cover
    edge_tts = None
    EDGE_TTS_OK = False

WINDOWS_SAPI_OK = sys.platform.startswith("win")


def _ps_encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _run_powershell(script: str, block: bool = False) -> bool:
    if not WINDOWS_SAPI_OK:
        return False
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-EncodedCommand", _ps_encoded(script),
    ]
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if block:
            subprocess.run(
                cmd, check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=flags,
            )
        else:
            subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=flags,
            )
        return True
    except Exception:
        return False


def _sapi_script(text: str, rate: int = -3, volume: int = 100,
                 wave_path: str | None = None) -> str:
    safe_text = text.replace("`", "``").replace('"', '`"')
    safe_path = (wave_path or "").replace("`", "``").replace('"', '`"')
    output = (
        f'$s.SetOutputToWaveFile("{safe_path}");'
        if wave_path else ""
    )
    return (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.Rate = {max(-10, min(10, int(rate)))};"
        f"$s.Volume = {max(0, min(100, int(volume)))};"
        "$voices = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo };"
        "$zh = $voices | Where-Object { $_.Culture.Name -like 'zh*' } | Select-Object -First 1;"
        "if ($zh -ne $null) { $s.SelectVoice($zh.Name); }"
        f"{output}"
        f'$s.Speak("{safe_text}");'
        "$s.Dispose();"
    )


def sapi_speak(text: str, block: bool = False, rate: int = -3) -> bool:
    """Use Windows native speech. This is more reliable than pyttsx3 threads."""
    if not text.strip():
        return False
    return _run_powershell(_sapi_script(text, rate=rate), block=block)


def _edge_voice(lang: str) -> str:
    return "zh-TW-HsiaoChenNeural" if lang == "zh" else "en-US-JennyNeural"


def _edge_audio_bytes(text: str, lang: str = "zh") -> bytes | None:
    if not EDGE_TTS_OK or not text.strip():
        return None
    path = Path(tempfile.gettempdir()) / f"smart_rehab_voice_{uuid.uuid4().hex}.mp3"
    cmd = [
        sys.executable, "-m", "edge_tts",
        "--voice", _edge_voice(lang),
        "--rate=-24%",
        "--text", text,
        "--write-media", str(path),
    ]
    try:
        subprocess.run(
            cmd, check=False, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        data = path.read_bytes() if path.exists() else None
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return data if data else None
    except Exception:
        return None


async def _edge_audio_async(text: str, lang: str = "zh") -> bytes | None:
    if not EDGE_TTS_OK or edge_tts is None or not text.strip():
        return None
    chunks: list[bytes] = []
    communicate = edge_tts.Communicate(
        text,
        voice=_edge_voice(lang),
        rate="-28%",
        pitch="+0Hz",
    )
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks) if chunks else None


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _play_mp3_bytes(data: bytes, estimated_ms: int = 3600) -> bool:
    if not WINDOWS_SAPI_OK or not data:
        return False
    path = Path(tempfile.gettempdir()) / f"smart_rehab_voice_{uuid.uuid4().hex}.mp3"
    try:
        path.write_bytes(data)
        uri = path.as_uri()
        script = (
            "Add-Type -AssemblyName PresentationCore;"
            "$p = New-Object System.Windows.Media.MediaPlayer;"
            f'$p.Open([Uri]"{uri}");'
            "$p.Volume = 1;"
            "$p.Play();"
            f"Start-Sleep -Milliseconds {max(1600, min(9000, estimated_ms))};"
            "$p.Stop();$p.Close();"
            f'Remove-Item -LiteralPath "{str(path).replace("`", "``").replace(chr(34), "`" + chr(34))}" -ErrorAction SilentlyContinue;'
        )
        return _run_powershell(script, block=False)
    except Exception:
        return False


def neural_speak(text: str, lang: str = "zh", block: bool = False) -> bool:
    """Speak with Edge neural voice when available."""
    if not EDGE_TTS_OK or not text.strip():
        return False

    def _work() -> None:
        data = _edge_audio_bytes(text, lang)
        if data:
            _play_mp3_bytes(data, estimated_ms=1800 + len(text) * 180)

    if block:
        _work()
    else:
        threading.Thread(target=_work, daemon=True).start()
    return True


def synthesize_audio_bytes(text: str, lang: str = "zh") -> tuple[bytes, str] | None:
    """Return browser-playable neural MP3 when possible, otherwise SAPI WAV."""
    data = _edge_audio_bytes(text, lang) if EDGE_TTS_OK else None
    if data:
        return data, "audio/mp3"
    wav = synthesize_wav_bytes(text)
    return (wav, "audio/wav") if wav else None


def synthesize_wav_bytes(text: str) -> bytes | None:
    """Generate browser-playable WAV bytes using Windows SAPI."""
    if not WINDOWS_SAPI_OK or not text.strip():
        return None
    tmp_path = Path(tempfile.gettempdir()) / f"smart_rehab_voice_{uuid.uuid4().hex}.wav"
    script = _sapi_script(text, wave_path=str(tmp_path))
    if not _run_powershell(script, block=True):
        return None
    try:
        data = tmp_path.read_bytes()
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return data if data else None
    except Exception:
        return None


def voice_status() -> dict:
    return {
        "edge_neural": EDGE_TTS_OK,
        "pyttsx3": PYTTSX_OK,
        "windows_sapi": WINDOWS_SAPI_OK,
        "browser_wav": WINDOWS_SAPI_OK,
    }


class VoiceGuide:
    """封裝 pyttsx3，提供非阻塞的語音回饋。"""

    def __init__(self, rate: int = 170, volume: float = 1.0, lang: str = "zh"):
        self._engine = None
        self._available = False
        self._lock = threading.Lock()
        self._lang = lang
        self._rate = rate
        self._volume = volume
        self._prefer_edge = EDGE_TTS_OK
        self._prefer_sapi = WINDOWS_SAPI_OK
        if self._prefer_edge:
            self._available = True
            return
        if self._prefer_sapi:
            self._available = True
            return
        if not PYTTSX_OK:
            return
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.setProperty("volume", volume)
            # 嘗試挑選中文語音
            if lang == "zh":
                try:
                    for v in engine.getProperty("voices"):
                        name = (v.name or "").lower() + (v.id or "").lower()
                        if any(tag in name for tag in ("zh", "chinese", "hanyu", "taiwan", "mandarin")):
                            engine.setProperty("voice", v.id)
                            break
                except Exception:
                    pass
            self._engine = engine
            self._available = True
        except Exception:  # pragma: no cover
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def set_language(self, lang: str):
        self._lang = lang

    def say(self, text: str, block: bool = False):
        if not self._available or not text:
            return
        text = _shorten_for_voice(text, self._lang)
        if self._prefer_edge:
            neural_speak(text, lang=self._lang, block=block)
            return
        if self._prefer_sapi:
            sapi_speak(text, block=block, rate=-3)
            return

        def _speak():
            with self._lock:
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception:
                    pass

        if block:
            _speak()
        else:
            threading.Thread(target=_speak, daemon=True).start()

    def say_intro(
        self,
        exercise_name: str,
        description: str = "",
        cue: str = "",
        lang: Optional[str] = None,
    ) -> None:
        """進入錄影頁時念出動作介紹（名稱 + 說明 + 提醒）。"""
        if not self._available or not exercise_name:
            return
        use_lang = lang or self._lang
        parts: list[str] = []
        if use_lang == "zh":
            parts.append(f"接下來的動作是：{exercise_name}")
            if description:
                parts.append(description)
            if cue:
                parts.append(f"重點提醒：{cue}")
            parts.append("看著教練提示牌，慢慢做，不要急")
            self.say("。".join(parts))
        else:
            parts.append(f"Next exercise: {exercise_name}.")
            if description:
                parts.append(description)
            if cue:
                parts.append(f"Tip: {cue}.")
            parts.append("Watch the coach cue card. Move slowly.")
            self.say(" ".join(parts))

    def say_cues(
        self,
        cues: Optional[List[dict]],
        score: Optional[float] = None,
        lang: Optional[str] = None,
    ) -> None:
        """簡短方向語音：例「右肩，請抬高。左膝，請彎曲。」

        cues 來自 scoring.feedback_cues()。最多念前 3 條。
        """
        if not self._available:
            return
        use_lang = lang or self._lang
        # 開場
        opening: list[str] = []
        if score is not None:
            opening.append(
                f"分數 {score:.0f}" if use_lang == "zh"
                else f"Score {score:.0f}"
            )
        # 沒有 cues：稱讚
        if not cues:
            praise = (
                "動作完美，繼續保持！" if use_lang == "zh"
                else "Perfect form. Keep going!"
            )
            self.say("。".join(opening + [praise])
                     if use_lang == "zh"
                     else " ".join(opening + [praise]))
            return
        # 簡短方向句
        parts: list[str] = list(opening)
        for c in cues[:3]:
            target = c.get("body_part", c["joint"])
            if use_lang == "zh":
                parts.append(f"{target}請{c['verb']}")
            else:
                parts.append(f"{target} please {c['verb_en']}")
        joiner = "。" if use_lang == "zh" else ". "
        self.say(joiner.join(parts))

    def say_feedback(self, messages: Optional[List[str]], score: Optional[float] = None):
        """將分析結果轉為自然語音播報。"""
        if not self._available:
            return
        parts: List[str] = []
        if score is not None:
            if self._lang == "en":
                parts.append(f"Your overall score is {score:.0f} out of 100.")
            else:
                parts.append(f"您本次的整體分數是 {score:.0f} 分。")
        if messages:
            if self._lang == "en":
                parts.append("Here are some suggestions.")
            else:
                parts.append("以下是建議調整的重點。")
            for m in messages[:3]:
                parts.append(m)
        else:
            parts.append(
                "Your movement quality is excellent. Keep it up."
                if self._lang == "en"
                else "您的動作品質良好，請繼續保持。"
            )
        self.say("。".join(parts) if self._lang == "zh" else " ".join(parts))

    def stop(self):
        if not self._available:
            return
        try:
            self._engine.stop()
        except Exception:  # pragma: no cover
            pass


def _shorten_for_voice(text: str, lang: str = "zh") -> str:
    """Keep spoken cues calm and short."""
    text = " ".join(str(text).replace("；", "。").split())
    parts = [p.strip() for p in text.split("。") if p.strip()]
    if not parts:
        return text
    first = parts[0]
    if lang == "zh":
        first = first.replace("請再", "").replace("請", "")
        if len(first) > 12:
            first = first[:12]
        if "慢慢" not in first and any(k in first for k in ("抬", "放", "伸", "彎", "回")):
            first = "慢慢" + first
    return first
