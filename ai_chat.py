"""
AI conversational coach: rule-based + optional LLM fallback.

Provides interactive chat for users to ask questions about:
- Their training data (last score, streak, etc.)
- Exercise advice (form, modifications)
- Pain management tips
- Recovery timeline
- Motivation

Falls back to simple keyword matching if no LLM API key is set.
"""
from __future__ import annotations
import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional

from db import execute_query
from analytics import (
    calculate_improvement_rate,
    calculate_adherence,
    get_pain_trend,
)
from ml_insights import (
    calculate_risk_score,
    recommend_exercises,
    predict_optimal_training_time,
)


INTENT_PATTERNS = {
    "score": [
        r"分數|得分|表現|成績",
        r"\b(score|how am i|performance|grade)\b",
    ],
    "streak": [
        r"連續|連勝|streak",
    ],
    "pain": [
        r"疼痛|痛|不舒服|難受",
        r"\b(pain|hurt|sore|ache)\b",
    ],
    "advice": [
        r"建議|幫助|怎麼辦|該做什麼|推薦",
        r"\b(advice|help|recommend|suggestion|what should)\b",
    ],
    "motivation": [
        r"加油|鼓勵|沒動力|放棄|累",
        r"\b(motivat|tired|give up|exhaust|quit)\b",
    ],
    "form": [
        r"姿勢|動作|怎麼做|技巧",
        r"\b(form|posture|technique|how to|how do)\b",
    ],
    "schedule": [
        r"時間|什麼時候|頻率|安排",
        r"\b(when|time|frequency|schedule)\b",
    ],
    "greet": [
        r"你好|哈囉|嗨",
        r"\b(hi|hello|hey|sup)\b",
    ],
    "thanks": [
        r"謝謝|感謝|thanks?",
    ],
}


def detect_intent(message: str) -> str:
    """Detect user's intent from message."""
    msg = message.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, msg, re.IGNORECASE):
                return intent
    return "unknown"


def respond_to_intent(intent: str, user_id: str, lang: str = "zh") -> str:
    """Generate response based on intent and user data."""
    if intent == "greet":
        return _greet(user_id, lang)
    if intent == "score":
        return _score_response(user_id, lang)
    if intent == "streak":
        return _streak_response(user_id, lang)
    if intent == "pain":
        return _pain_response(user_id, lang)
    if intent == "advice":
        return _advice_response(user_id, lang)
    if intent == "motivation":
        return _motivation_response(user_id, lang)
    if intent == "form":
        return _form_response(lang)
    if intent == "schedule":
        return _schedule_response(user_id, lang)
    if intent == "thanks":
        return ("不客氣！加油！💪" if lang == "zh"
                else "You're welcome! Keep going! 💪")
    return _fallback(lang)


def chat(user_id: str, message: str, lang: str = "zh") -> Dict:
    """Process chat message, return response + metadata."""
    if not message.strip():
        return {"reply": "", "intent": "empty"}

    intent = detect_intent(message)

    try:
        from agentic_ai import run_agent, _llm_available
        if _llm_available():
            result = run_agent(message, user_id=user_id, lang=lang)
            if result.used_llm and result.answer:
                return {
                    "reply": result.answer,
                    "intent": intent,
                    "source": "agentic",
                    "tool_calls": [t["tool"] for t in result.tool_calls],
                }
    except ImportError:
        pass

    try:
        from rag_engine import answer_question
        rag = answer_question(message, user_id=user_id, lang=lang)
        if rag.answer and rag.retrieval_count > 0:
            return {
                "reply": rag.answer,
                "intent": intent,
                "source": "rag",
                "sources": [s.get("id") for s in rag.sources],
            }
    except ImportError:
        pass

    llm_reply = _try_llm(message, user_id, lang)
    if llm_reply:
        return {"reply": llm_reply, "intent": intent, "source": "llm"}

    reply = respond_to_intent(intent, user_id, lang)
    return {"reply": reply, "intent": intent, "source": "rules"}


def _greet(user_id: str, lang: str) -> str:
    rows = execute_query(
        "SELECT username FROM users WHERE user_id = ?",
        (user_id,),
    )
    name = rows[0]["username"] if rows else ""
    if lang == "zh":
        return f"你好 {name}！有什麼可以幫你的？😊"
    return f"Hi {name}! How can I help you today? 😊"


def _score_response(user_id: str, lang: str) -> str:
    improvement = calculate_improvement_rate(user_id)
    if improvement["samples"] == 0:
        return ("還沒有訓練資料喔，先來做一次練習吧！" if lang == "zh"
                else "No training data yet — try a session first!")

    rate = improvement["rate"]
    cur = improvement["current"]
    if lang == "zh":
        if rate > 5:
            return f"你最近進步很多！平均 {cur:.1f} 分，比上期高 {rate:.1f}% 🎉"
        if rate < -5:
            return (f"最近平均 {cur:.1f} 分，比上期低 {abs(rate):.1f}%。"
                    f"放鬆一下，調整節奏會更好。")
        return f"目前平均 {cur:.1f} 分，表現穩定。"
    if rate > 5:
        return f"You're improving! Avg {cur:.1f}, up {rate:.1f}% 🎉"
    if rate < -5:
        return f"Avg {cur:.1f}, down {abs(rate):.1f}%. Take it easy."
    return f"Average {cur:.1f}. Steady performance."


def _streak_response(user_id: str, lang: str) -> str:
    rows = execute_query(
        """
        SELECT DATE(created_at) as d FROM sessions
        WHERE user_id = ?
        GROUP BY DATE(created_at)
        ORDER BY d DESC LIMIT 30
        """,
        (user_id,),
    )

    if not rows:
        return ("還沒有連續紀錄。今天就開始吧！" if lang == "zh"
                else "No streak yet. Start today!")

    from datetime import date, timedelta
    streak = 0
    today = date.today()
    for i, row in enumerate(rows):
        try:
            d = datetime.fromisoformat(row["d"]).date()
        except Exception:
            continue
        if d == today - timedelta(days=i):
            streak += 1
        else:
            break

    if lang == "zh":
        return f"目前連續 {streak} 天訓練！🔥 繼續保持！"
    return f"Current streak: {streak} days! 🔥 Keep it up!"


def _pain_response(user_id: str, lang: str) -> str:
    pain = get_pain_trend(user_id)
    if pain["samples"] == 0:
        return ("先記錄你的疼痛狀況吧！" if lang == "zh"
                else "Start logging your pain levels first!")

    if pain["trend"] == "improving":
        if lang == "zh":
            return (f"好消息！你的疼痛平均降低 {pain['avg_reduction']} 分。"
                    f"訓練有效！💚")
        return (f"Good news! Pain reduced by {pain['avg_reduction']} on avg. "
                f"Training is working! 💚")
    if pain["trend"] == "worsening":
        if lang == "zh":
            return ("疼痛似乎加劇了。建議：1) 降低訓練強度 2) 多休息 "
                    "3) 與治療師聯絡。")
        return ("Pain seems worse. Try: 1) Lower intensity 2) More rest "
                "3) Contact therapist.")
    if lang == "zh":
        return "疼痛維持穩定。記得在訓練前後都記錄。"
    return "Pain is stable. Remember to log before and after training."


def _advice_response(user_id: str, lang: str) -> str:
    recs = recommend_exercises(user_id, top_k=2)
    if not recs:
        return ("先做幾次練習，我才能給更精準的建議！" if lang == "zh"
                else "Do a few sessions and I can give better advice!")

    risk = calculate_risk_score(user_id)
    parts = []
    if lang == "zh":
        parts.append("建議練習：")
        for r in recs:
            parts.append(f"• {r['exercise']}（平均 {r['avg_score']:.0f} 分）")
        if risk["risk_score"] >= 50:
            parts.append("⚠️ 近期表現偏低，建議放慢腳步並與治療師討論。")
    else:
        parts.append("Recommendations:")
        for r in recs:
            parts.append(f"• {r['exercise']} (avg {r['avg_score']:.0f})")
        if risk["risk_score"] >= 50:
            parts.append("⚠️ Recent decline — slow down and consult therapist.")

    return "\n".join(parts)


def _motivation_response(user_id: str, lang: str) -> str:
    quotes_zh = [
        "每一次練習都是進步的一步。",
        "復健就像爬樓梯，慢慢來，但別停下。",
        "今天的努力是明天的力量。",
        "你做得比你想的還要好！💪",
        "小小的進步累積起來就是大改變。",
    ]
    quotes_en = [
        "Every rep is a step forward.",
        "Recovery is a marathon, not a sprint.",
        "Today's effort is tomorrow's strength.",
        "You're doing better than you think! 💪",
        "Small wins add up to big changes.",
    ]
    import random
    return random.choice(quotes_zh if lang == "zh" else quotes_en)


def _form_response(lang: str) -> str:
    if lang == "zh":
        return ("動作要領：\n"
                "• 慢慢做，控制全程\n"
                "• 呼吸均勻，不要憋氣\n"
                "• 感到尖銳痛即停止\n"
                "• 可以查看 AI 示範影片參考")
    return ("Form tips:\n"
            "• Move slow and controlled\n"
            "• Breathe evenly, don't hold breath\n"
            "• Stop on sharp pain\n"
            "• Check AI demo videos for reference")


def _schedule_response(user_id: str, lang: str) -> str:
    optimal = predict_optimal_training_time(user_id)
    adherence = calculate_adherence(user_id)

    parts = []
    if lang == "zh":
        if optimal.get("hour") is not None:
            parts.append(
                f"你在 {optimal['hour_str']} 表現最好"
                f"（平均 {optimal['avg_score_at_hour']:.0f} 分）"
            )
        parts.append(f"目前每週平均 {adherence.get('avg_per_week', 0)} 次。")
        if adherence["adherence_pct"] < 60:
            parts.append("建議每週至少 3 次以加速恢復。")
    else:
        if optimal.get("hour") is not None:
            parts.append(
                f"Best time: {optimal['hour_str']} "
                f"(avg {optimal['avg_score_at_hour']:.0f})"
            )
        parts.append(f"Avg {adherence.get('avg_per_week', 0)} per week.")
        if adherence["adherence_pct"] < 60:
            parts.append("Aim for 3+ sessions per week.")

    return "\n".join(parts) if parts else (
        "先建立一些訓練紀錄吧！" if lang == "zh"
        else "Build up some training records first!"
    )


def _fallback(lang: str) -> str:
    if lang == "zh":
        return ("我可以幫你了解：分數進步、連續天數、疼痛狀況、"
                "訓練建議、最佳時間、動作要領。試著問問看吧！")
    return ("I can help with: score progress, streaks, pain, advice, "
            "best training time, form tips. Try asking!")


def _try_llm(message: str, user_id: str, lang: str) -> Optional[str]:
    """Try to use LLM if API key is available."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        if os.environ.get("ANTHROPIC_API_KEY"):
            reply = _call_anthropic(message, user_id, lang)
            if reply:
                return reply
        if os.environ.get("OPENAI_API_KEY"):
            return _call_openai(message, user_id, lang)
        return None
    except Exception:
        return None


def _call_anthropic(message: str, user_id: str, lang: str) -> Optional[str]:
    """Call Anthropic Claude for richer response."""
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic()
    context = _build_user_context(user_id, lang)

    system_prompt = (
        "你是一位專業的居家復健 AI 助理。語氣親切、簡潔。"
        "用使用者的數據給出具體建議。回答控制在 100 字內。"
        if lang == "zh" else
        "You are a friendly home rehab AI assistant. Be concise (under 100 words). "
        "Use the user's data to give specific advice."
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=[
                {"type": "text", "text": system_prompt},
                {
                    "type": "text",
                    "text": f"User context:\n{context}",
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": message}],
        )
        return response.content[0].text if response.content else None
    except Exception:
        return None


def _call_openai(message: str, user_id: str, lang: str) -> Optional[str]:
    """Call OpenAI for richer response when configured."""
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI()
    context = _build_user_context(user_id, lang)
    model = os.environ.get("OPENAI_MODEL", "gpt-5.1")

    system_prompt = (
        "你是一位專業的居家復健 AI 助理。語氣親切、簡潔。"
        "用使用者的數據給出具體建議。回答控制在 100 字內。"
        "醫療高風險或紅旗症狀時，請建議聯絡治療師或醫師。"
        if lang == "zh" else
        "You are a friendly home rehab AI assistant. Be concise (under 100 words). "
        "Use the user's data to give specific advice. For red flags, advise "
        "contacting a therapist or physician."
    )
    instructions = f"{system_prompt}\n\nUser context:\n{context}"

    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=message,
            max_output_tokens=300,
        )
        text = getattr(response, "output_text", "")
        return text.strip() if text else None
    except Exception:
        pass

    try:
        chat_model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-5.1-chat-latest")
        response = client.chat.completions.create(
            model=chat_model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": message},
            ],
            max_tokens=300,
        )
        return response.choices[0].message.content
    except Exception:
        return None


def _build_user_context(user_id: str, lang: str) -> str:
    """Build cached context block for LLM."""
    improvement = calculate_improvement_rate(user_id)
    adherence = calculate_adherence(user_id)
    pain = get_pain_trend(user_id)

    return json.dumps({
        "lang": lang,
        "improvement_rate_30d": improvement.get("rate"),
        "current_avg_score": improvement.get("current"),
        "samples": improvement.get("samples"),
        "adherence_pct": adherence.get("adherence_pct"),
        "avg_sessions_per_week": adherence.get("avg_per_week"),
        "pain_trend": pain.get("trend"),
        "avg_pain_reduction": pain.get("avg_reduction"),
    })


def save_chat(user_id: str, message: str, reply: str, intent: str) -> None:
    """Save chat history."""
    from db import execute_update
    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, ?, ?, datetime('now', '+30 days'))
            """,
            (
                user_id,
                "chat_history",
                json.dumps({
                    "message": message,
                    "reply": reply,
                    "intent": intent,
                    "ts": datetime.now().isoformat(),
                }),
            ),
        )
    except Exception:
        pass


def get_chat_history(user_id: str, limit: int = 20) -> List[Dict]:
    """Retrieve recent chat history."""
    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = 'chat_history'
        ORDER BY created_at DESC LIMIT ?
        """,
        (user_id, limit),
    )

    history = []
    for row in rows:
        try:
            history.append(json.loads(row["data_json"]))
        except Exception:
            continue
    return list(reversed(history))
