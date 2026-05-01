"""
虛擬卡通教練：多個可選角色，依使用者的當前狀態挑選對應的鼓勵台詞。

公開 API：
    CHARACTERS                : dict[character_key, character_info]
    STATES                    : 可用的情境字串
    message_for(state, lang)  : 隨機挑一句台詞
    state_from_score(score)   : 由分數對應到 good / average / low
    state_for_streak(streak)  : 由連續日數選 greet / fire / proud
"""
from __future__ import annotations

import random
from typing import Dict, List

# ---------------- 角色 ----------------
CHARACTERS: Dict[str, Dict[str, str]] = {
    "doggo": {
        "key": "doggo",
        "emoji": "🐶",
        "name_zh": "汪汪教練",
        "name_en": "Coach Doggo",
        "color": "#fdcb6e",
        "color_dark": "#e17055",
    },
    "kitty": {
        "key": "kitty",
        "emoji": "🐱",
        "name_zh": "貓貓老師",
        "name_en": "Sensei Kitty",
        "color": "#74b9ff",
        "color_dark": "#0984e3",
    },
    "bear": {
        "key": "bear",
        "emoji": "🐻",
        "name_zh": "熊熊隊長",
        "name_en": "Capt. Bear",
        "color": "#a29bfe",
        "color_dark": "#6c5ce7",
    },
    "bunny": {
        "key": "bunny",
        "emoji": "🐰",
        "name_zh": "兔兔",
        "name_en": "Bunny",
        "color": "#ff7675",
        "color_dark": "#d63031",
    },
    "starbuddy": {
        "key": "starbuddy",
        "emoji": "✦",
        "avatar": "starfish",
        "name_zh": "小粉星助手",
        "name_en": "Star Buddy",
        "color": "#ff7aa2",
        "color_dark": "#ff3b6b",
    },
}

DEFAULT_CHARACTER = "starbuddy"

# ---------------- 台詞庫 ----------------
STATES = (
    "greet", "ready", "live",
    "good", "average", "low", "pb",
    "rest", "streak", "first_time",
)

_MESSAGES: Dict[str, Dict[str, List[str]]] = {
    "greet": {
        "zh": [
            "今天也要一起加油哦！💪",
            "歡迎回來，準備好了嗎？",
            "嗨～開始今天的訓練吧！",
            "你來啦！我等你好久囉～",
            "我會看著你的手臂方向，該往上或往下都會提醒你。",
        ],
        "en": [
            "Let's get moving today! 💪",
            "Welcome back, ready?",
            "Hi there, time to train!",
            "You're here! Let's go!",
            "I'll call out whether your arms should go up or down.",
        ],
    },
    "ready": {
        "zh": [
            "別忘了暖身唷～",
            "深呼吸，慢慢來不要急。",
            "全身放鬆，動作要到位！",
            "保持微笑，動作會更標準！",
            "等等聽我的聲音提示：手臂往上、往下，跟著做就好。",
        ],
        "en": [
            "Warm up first!",
            "Take a deep breath.",
            "Stay relaxed and aim for full range.",
            "Smile — you'll move better!",
            "Listen for my voice cues: arms up, arms down.",
        ],
    },
    "live": {
        "zh": [
            "紅字提示請注意～",
            "保持節奏，吸氣吐氣！",
            "動作很漂亮，繼續！",
            "再撐一下，你做得到！",
            "我會用聲音提醒方向，眼睛看鏡頭就好。",
        ],
        "en": [
            "Mind the red hints!",
            "Keep the rhythm, breathe!",
            "Looking great, keep going!",
            "You got this!",
            "I'll speak the direction cues, keep your eyes on the camera.",
        ],
    },
    "good": {
        "zh": [
            "哇！動作超漂亮！🌟",
            "完美演出！為你鼓掌！",
            "厲害厲害，繼續保持！",
            "教練都看呆了～",
        ],
        "en": [
            "Wow, beautiful form! 🌟",
            "Perfect, applause!",
            "Amazing, keep it up!",
            "I'm impressed!",
        ],
    },
    "average": {
        "zh": [
            "不錯哦，再多注意一點細節～",
            "穩定發揮！下次更好！",
            "進步中，加油！",
            "已經很棒了，再精進一下！",
        ],
        "en": [
            "Nice work — refine the details.",
            "Steady! Even better next time.",
            "Improving, keep at it!",
            "Already great, polish further!",
        ],
    },
    "low": {
        "zh": [
            "別氣餒，慢慢來就會更好！",
            "練習比分數重要哦～",
            "下一次一定更棒！",
            "深呼吸，再試一次就好！",
        ],
        "en": [
            "Don't worry, slow & steady wins.",
            "Practice over scores!",
            "Next try will be better!",
            "Breathe and retry, you got it.",
        ],
    },
    "pb": {
        "zh": [
            "新紀錄！太厲害了！🎉",
            "突破自己！恭喜恭喜！",
            "破紀錄！繼續挑戰更高！",
            "個人新高，給你大大的拍手！👏",
        ],
        "en": [
            "New best! Awesome! 🎉",
            "You broke your record!",
            "Personal best — keep climbing!",
            "Huge applause! 👏",
        ],
    },
    "rest": {
        "zh": [
            "記得多喝水，好好休息！",
            "今天辛苦了～",
            "好好放鬆，明天再戰！",
        ],
        "en": [
            "Hydrate and rest!",
            "Great work today!",
            "Relax now, see you tomorrow!",
        ],
    },
    "streak": {
        "zh": [
            "連續訓練好幾天了，真有毅力！🔥",
            "你比昨天的自己更強了！",
            "持之以恆，太厲害了！",
        ],
        "en": [
            "Streak going strong! 🔥",
            "Stronger than yesterday!",
            "Consistency wins!",
        ],
    },
    "first_time": {
        "zh": [
            "第一次見面，請多指教～",
            "我是你的訓練夥伴，一起加油！",
            "我會陪著你完成每次訓練的！",
        ],
        "en": [
            "Nice to meet you!",
            "I'm your training buddy!",
            "I'll be with you every session!",
        ],
    },
}


# ---------------- 公用函式 ----------------
def message_for(state: str, lang: str = "zh") -> str:
    pool = _MESSAGES.get(state, {}).get(lang)
    if not pool:
        pool = _MESSAGES.get(state, {}).get("zh") or [""]
    return random.choice(pool)


def state_from_score(score: float) -> str:
    if score >= 85:
        return "good"
    if score >= 70:
        return "average"
    return "low"


def state_for_streak(streak: int) -> str:
    if streak >= 3:
        return "streak"
    if streak == 0:
        return "first_time"
    return "greet"


def get_character(key: str | None) -> Dict[str, str]:
    if key and key in CHARACTERS:
        return CHARACTERS[key]
    return CHARACTERS[DEFAULT_CHARACTER]


def display_name(key: str | None, lang: str = "zh") -> str:
    c = get_character(key)
    return c["name_zh"] if lang == "zh" else c["name_en"]
