"""
Retrieval-Augmented Generation (RAG) engine for clinical Q&A.

Pipeline:
1. Retrieve top-K relevant knowledge entries via vector_db
2. Optionally augment with patient-specific context (last sessions, vitals)
3. Build a system prompt with cached static content + dynamic retrieved chunks
4. Query Claude (or fallback to rule-based summary)
5. Return answer with cited sources

Design principles:
- Anthropic prompt caching: static system prompt + retrieved context cached
- Bilingual prompts (zh/en)
- Cite sources by ID so user can review original
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RAGAnswer:
    answer: str
    sources: List[Dict] = field(default_factory=list)
    used_llm: bool = False
    confidence: float = 0.0
    retrieval_count: int = 0


SYSTEM_PROMPT_ZH = """你是一位專業的居家復健 AI 助理。
你會收到一個病人的問題、相關的臨床知識片段、以及病人的最近資料。

回答時：
1. 優先使用提供的知識片段（會被標記為 [Source: id]）
2. 在回應中明確引用來源 ID
3. 用親切但專業的語氣
4. 控制在 200 字內
5. 若知識片段不足以回答，誠實說明
6. 提供具體可執行的建議
7. 對於高風險情況（劇痛、紅旗症狀），明確建議聯絡治療師

格式：
- 直接回答（不要冗長前言）
- 引用：[Source: ex_arm_raise_zh]
- 警示：⚠️ 開頭表示需要注意
"""

SYSTEM_PROMPT_EN = """You are a professional home-rehab AI assistant.
You receive a patient's question, relevant clinical knowledge snippets,
and the patient's recent data.

When answering:
1. Prioritize provided knowledge snippets (marked [Source: id])
2. Explicitly cite source IDs in your reply
3. Use warm but professional tone
4. Keep under 200 words
5. If snippets are insufficient, say so honestly
6. Provide concrete actionable advice
7. For red-flag situations (severe pain, danger signs), explicitly
   recommend contacting the therapist

Format:
- Direct answer (no long preamble)
- Citations: [Source: ex_arm_raise_en]
- Warnings: prefix with ⚠️
"""


def answer_question(question: str,
                     user_id: Optional[str] = None,
                     lang: str = "zh",
                     top_k: int = 5,
                     include_user_context: bool = True
                     ) -> RAGAnswer:
    """Run full RAG pipeline."""
    sources = _retrieve(question, lang=lang, top_k=top_k)

    user_context = ""
    if include_user_context and user_id:
        user_context = _build_user_context(user_id, lang)

    if _llm_available():
        answer = _generate_with_llm(question, sources, user_context, lang)
        if answer:
            return RAGAnswer(
                answer=answer,
                sources=sources,
                used_llm=True,
                confidence=0.85,
                retrieval_count=len(sources),
            )

    return _rule_based_answer(question, sources, user_context, lang)


def _retrieve(query: str, lang: str = "zh", top_k: int = 5) -> List[Dict]:
    """Retrieve relevant knowledge entries."""
    try:
        from clinical_knowledge import search, init_knowledge_base
        init_knowledge_base()
        return search(query, top_k=top_k, lang=lang)
    except Exception:
        return []


def _build_user_context(user_id: str, lang: str) -> str:
    """Build a compact user context string."""
    try:
        from analytics import calculate_improvement_rate, get_pain_trend
        from db import execute_query
        from datetime import date

        improvement = calculate_improvement_rate(user_id)
        pain = get_pain_trend(user_id)

        today_str = date.today().isoformat()
        recent = execute_query(
            """
            SELECT exercise, score, created_at FROM sessions
            WHERE user_id = ? ORDER BY created_at DESC LIMIT 3
            """,
            (user_id,),
        )

        context_data = {
            "current_avg_score": improvement.get("current"),
            "improvement_rate_pct": improvement.get("rate"),
            "pain_trend": pain.get("trend"),
            "recent_sessions": [
                {"ex": r["exercise"], "score": r["score"]}
                for r in recent
            ],
            "today": today_str,
        }
        return json.dumps(context_data, ensure_ascii=False)
    except Exception:
        return ""


def _llm_available() -> bool:
    """Check if at least one configured LLM provider is callable."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            pass
    return False


def _generate_with_llm(question: str, sources: List[Dict],
                        user_context: str, lang: str) -> Optional[str]:
    """Call the configured LLM provider with retrieved snippets."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        answer = _generate_with_anthropic(question, sources, user_context, lang)
        if answer:
            return answer
    if os.environ.get("OPENAI_API_KEY"):
        return _generate_with_openai(question, sources, user_context, lang)
    return None


def _generate_with_anthropic(question: str, sources: List[Dict],
                             user_context: str, lang: str) -> Optional[str]:
    """Call Claude with cached system + dynamic snippets."""
    try:
        import anthropic
    except ImportError:
        return None

    snippet_text = _format_sources(sources)
    user_msg = _build_user_message(question, snippet_text, user_context, lang)
    sys_prompt = SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT_EN

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=[
                {
                    "type": "text",
                    "text": sys_prompt,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception:
        return None

    if not response.content:
        return None
    return response.content[0].text


def _generate_with_openai(question: str, sources: List[Dict],
                          user_context: str, lang: str) -> Optional[str]:
    """Call OpenAI Responses API with retrieved snippets."""
    try:
        from openai import OpenAI
    except ImportError:
        return None

    snippet_text = _format_sources(sources)
    user_msg = _build_user_message(question, snippet_text, user_context, lang)
    sys_prompt = SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT_EN
    model = os.environ.get("OPENAI_MODEL", "gpt-5.1")

    try:
        client = OpenAI()
        response = client.responses.create(
            model=model,
            instructions=sys_prompt,
            input=user_msg,
            max_output_tokens=500,
        )
        text = getattr(response, "output_text", "")
        return text.strip() if text else None
    except Exception:
        return None


def _build_user_message(question: str, snippets: str,
                         user_context: str, lang: str) -> str:
    """Build the user-side message."""
    if lang == "zh":
        return (
            f"## 病人問題\n{question}\n\n"
            f"## 相關知識片段\n{snippets}\n\n"
            f"## 病人最近資料\n{user_context or '（無）'}\n\n"
            f"請根據上述資料回答。"
        )
    return (
        f"## Question\n{question}\n\n"
        f"## Retrieved Knowledge\n{snippets}\n\n"
        f"## Patient Recent Data\n{user_context or '(none)'}\n\n"
        f"Please answer based on the above."
    )


def _format_sources(sources: List[Dict]) -> str:
    """Format retrieved sources for the prompt."""
    if not sources:
        return "（無相關知識片段 / No relevant snippets）"

    lines = []
    for i, src in enumerate(sources, 1):
        sid = src.get("id", f"src_{i}")
        title = src.get("title", "")
        body = src.get("body", "")
        sim = src.get("similarity", 0)
        lines.append(
            f"[Source: {sid}] (similarity={sim:.2f})\n"
            f"{title}\n{body}\n"
        )
    return "\n".join(lines)


def _rule_based_answer(question: str, sources: List[Dict],
                        user_context: str, lang: str) -> RAGAnswer:
    """Compose answer from top sources without LLM."""
    if not sources:
        msg = ("找不到相關資料。請聯絡治療師取得個人化建議。"
               if lang == "zh" else
               "No relevant info found. Contact your therapist.")
        return RAGAnswer(
            answer=msg, sources=[], used_llm=False,
            confidence=0.2, retrieval_count=0,
        )

    top = sources[0]
    others = sources[1:3]

    if lang == "zh":
        parts = [f"【{top.get('title', '相關建議')}】"]
        parts.append(top.get("body", "")[:300])
        parts.append(f"\n[來源: {top.get('id', '')}]")
        if others:
            parts.append("\n相關內容：")
            for s in others:
                parts.append(f"• {s.get('title', '')} [{s.get('id', '')}]")
    else:
        parts = [f"## {top.get('title', 'Relevant Info')}"]
        parts.append(top.get("body", "")[:300])
        parts.append(f"\n[Source: {top.get('id', '')}]")
        if others:
            parts.append("\nRelated:")
            for s in others:
                parts.append(f"• {s.get('title', '')} [{s.get('id', '')}]")

    return RAGAnswer(
        answer="\n".join(parts),
        sources=sources,
        used_llm=False,
        confidence=0.55,
        retrieval_count=len(sources),
    )


def search_by_category(category: str, lang: str = "zh",
                        limit: int = 10) -> List[Dict]:
    """List entries in a specific category."""
    try:
        from clinical_knowledge import search, init_knowledge_base
        init_knowledge_base()
        return search("", top_k=limit, category=category, lang=lang)
    except Exception:
        return []
