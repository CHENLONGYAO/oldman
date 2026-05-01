"""
Voice command control: hands-free navigation and exercise control.

Recognizes:
- Navigation: "go home", "next", "back", "settings"
- Exercise: "start", "stop", "pause", "resume", "reset"
- Info: "score", "time", "reps"
- Coach: "coach quiet", "coach louder"

Backends:
- Browser-side: Web Speech API via JavaScript (no backend required)
- Server-side: speech_recognition + microphone (optional)

Mostly browser-side for privacy and zero-install.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import re


COMMAND_PATTERNS_ZH = {
    r"回(到)?(首頁|主頁|家)": ("nav", "home"),
    r"下一?(個|頁|步)": ("nav", "next"),
    r"返回|回去|上一頁": ("nav", "back"),
    r"設定|偏好": ("nav", "settings"),
    r"開始|啟動": ("action", "start"),
    r"停止|結束": ("action", "stop"),
    r"暫停": ("action", "pause"),
    r"繼續|重新開始": ("action", "resume"),
    r"重置|清除": ("action", "reset"),
    r"幾(分|分數)|目前分數": ("info", "score"),
    r"時間|多久": ("info", "time"),
    r"次數|做(了)?幾次": ("info", "reps"),
    r"安靜|閉嘴|不要說話": ("coach", "quiet"),
    r"大聲(一)?點|聽不到": ("coach", "louder"),
    r"AI|教練|問問題": ("nav", "ai_chat"),
}

COMMAND_PATTERNS_EN = {
    r"\b(go )?home\b": ("nav", "home"),
    r"\bnext\b": ("nav", "next"),
    r"\bback\b": ("nav", "back"),
    r"\bsettings?\b": ("nav", "settings"),
    r"\bstart\b": ("action", "start"),
    r"\bstop\b": ("action", "stop"),
    r"\bpause\b": ("action", "pause"),
    r"\bresume\b": ("action", "resume"),
    r"\breset\b": ("action", "reset"),
    r"\b(my )?score\b": ("info", "score"),
    r"\btime\b": ("info", "time"),
    r"\breps?\b|\brepetitions?\b": ("info", "reps"),
    r"\bquiet\b|\bshut up\b": ("coach", "quiet"),
    r"\blouder\b|\bcan't hear\b": ("coach", "louder"),
    r"\bai chat\b|\bask\b|\bcoach\b": ("nav", "ai_chat"),
}


@dataclass
class CommandResult:
    raw: str
    category: str  # nav / action / info / coach
    command: str
    confidence: float = 1.0
    matched: bool = True


def parse_command(text: str, lang: str = "zh") -> Optional[CommandResult]:
    """Parse voice transcript into a command, or None if no match."""
    if not text:
        return None
    text_low = text.strip().lower()

    patterns = COMMAND_PATTERNS_ZH if lang == "zh" else COMMAND_PATTERNS_EN
    for pattern, (category, cmd) in patterns.items():
        if re.search(pattern, text_low):
            return CommandResult(
                raw=text, category=category, command=cmd, matched=True
            )

    return CommandResult(raw=text, category="unknown",
                         command="unknown", matched=False)


# ============================================================
# Browser-side Web Speech API integration via Streamlit
# ============================================================
def render_voice_button(lang: str = "zh") -> Optional[str]:
    """Inject Web Speech API button. Returns recognized text via session_state.

    Caller must check `st.session_state.get("voice_command_text")`.
    """
    import streamlit as st

    locale = "zh-TW" if lang == "zh" else "en-US"
    btn_label = "🎤 語音指令" if lang == "zh" else "🎤 Voice Command"

    component_html = f"""
    <button id="voice-btn" style="
        padding: 12px 24px;
        border-radius: 24px;
        background: linear-gradient(135deg, #74b9ff, #007aff);
        color: white;
        border: none;
        cursor: pointer;
        font-size: 16px;
        box-shadow: 0 2px 8px rgba(0,122,255,0.3);
    ">{btn_label}</button>
    <div id="voice-status" style="margin-top:8px;font-size:13px;color:#666"></div>

    <script>
    const btn = document.getElementById("voice-btn");
    const status = document.getElementById("voice-status");

    if (!('webkitSpeechRecognition' in window) &&
        !('SpeechRecognition' in window)) {{
        status.innerText = "{('瀏覽器不支援' if lang == 'zh' else 'Browser unsupported')}";
        btn.disabled = true;
    }} else {{
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SR();
        recognition.lang = "{locale}";
        recognition.continuous = false;
        recognition.interimResults = false;

        btn.addEventListener("click", () => {{
            try {{
                recognition.start();
                status.innerText = "{('聽中…' if lang == 'zh' else 'Listening…')}";
                btn.style.background = "linear-gradient(135deg, #ff6b6b, #ff3b30)";
            }} catch(e) {{
                status.innerText = "Error: " + e;
            }}
        }});

        recognition.onresult = (event) => {{
            const text = event.results[0][0].transcript;
            status.innerText = "✓ " + text;
            btn.style.background = "linear-gradient(135deg, #74b9ff, #007aff)";
            window.parent.postMessage({{
                type: "streamlit:voiceCommand",
                text: text
            }}, "*");
            const url = new URL(window.parent.location.href);
            url.searchParams.set("voice_cmd", encodeURIComponent(text));
            window.parent.location.href = url.toString();
        }};

        recognition.onerror = (e) => {{
            status.innerText = "✗ " + e.error;
            btn.style.background = "linear-gradient(135deg, #74b9ff, #007aff)";
        }};

        recognition.onend = () => {{
            btn.style.background = "linear-gradient(135deg, #74b9ff, #007aff)";
        }};
    }}
    </script>
    """

    st.components.v1.html(component_html, height=80)

    try:
        params = st.query_params
        cmd_text = params.get("voice_cmd", "")
        if cmd_text:
            return cmd_text
    except Exception:
        pass

    return None


def execute_command(result: CommandResult) -> Dict:
    """Execute a parsed command. Returns dict with action taken."""
    import streamlit as st
    from app_state import goto

    if not result.matched:
        return {"executed": False, "reason": "unknown_command"}

    if result.category == "nav":
        nav_map = {
            "home": "home", "settings": "settings",
            "ai_chat": "ai_chat",
        }
        target = nav_map.get(result.command)
        if target:
            goto(target)
            return {"executed": True, "action": f"navigate_to_{target}"}

    if result.category == "action":
        if "active_game" in st.session_state:
            if result.command == "stop":
                st.session_state.active_game = None
                return {"executed": True, "action": "game_stopped"}

    if result.category == "info":
        if result.command == "score":
            user_id = (
                st.session_state.get("user", {}).get("user_id")
                if isinstance(st.session_state.get("user"), dict)
                else None
            )
            if user_id:
                from analytics import calculate_improvement_rate
                rate = calculate_improvement_rate(user_id)
                msg = f"目前平均 {rate.get('current', 0):.1f} 分"
                st.toast(msg)
                return {"executed": True, "action": "show_score",
                        "info": rate}

    if result.category == "coach":
        if result.command == "quiet":
            st.session_state.setdefault("settings", {})["enable_voice"] = False
            return {"executed": True, "action": "muted_coach"}
        if result.command == "louder":
            st.session_state.setdefault("settings", {})["enable_voice"] = True
            return {"executed": True, "action": "unmuted_coach"}

    return {"executed": False, "reason": "no_handler",
            "category": result.category, "command": result.command}
