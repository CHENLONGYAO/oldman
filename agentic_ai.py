"""
Agentic AI: Claude with tool use for autonomous data queries.

Tools available to the model:
- get_user_metrics: improvement, adherence, risk, pain trend
- search_knowledge: vector-search clinical KB
- list_recent_sessions: last N sessions
- get_exercise_breakdown: per-exercise stats
- get_recommendations: ML-driven suggestions
- compare_to_cohort: percentile + average

The agent runs a tool loop until it returns a final answer. Designed for
clinical-quality answers with cited evidence.

Uses Claude Sonnet 4.6 by default (best reasoning), can downgrade to
Haiku for speed. Caches the tool definitions and system prompt.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


SYSTEM_PROMPT_ZH = """你是一位資深的居家復健 AI 顧問。
你可以使用工具查詢病人資料、檢索臨床知識、推薦動作。

工作原則：
1. 先理解使用者意圖，再決定要用哪些工具
2. 一次可呼叫多個工具（並行）
3. 整合工具結果後給出明確回答
4. 引用知識來源 ID
5. 高風險或紅旗症狀：明確建議聯絡治療師
6. 回應控制在 250 字以內
7. 用親切但專業的語氣

當你已經有足夠資料時，停止呼叫工具並回應。
"""

SYSTEM_PROMPT_EN = """You are a senior home-rehab AI consultant.
You can use tools to query patient data, retrieve clinical knowledge,
and recommend exercises.

Principles:
1. Understand intent first, then choose tools
2. Call multiple tools in parallel when independent
3. Integrate tool results into a clear answer
4. Cite knowledge source IDs
5. For red-flag situations: explicitly recommend contacting therapist
6. Keep responses under 250 words
7. Warm, professional tone

When you have enough data, stop calling tools and respond.
"""


# ============================================================
# Tool definitions
# ============================================================
def _tool_specs() -> List[Dict]:
    """Return tool spec list for Claude API."""
    return [
        {
            "name": "get_user_metrics",
            "description": "Get the patient's current performance metrics: "
                          "improvement rate, adherence, risk score, pain trend.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "search_knowledge",
            "description": "Semantic search the clinical knowledge base. "
                          "Use this to find evidence-based info about "
                          "exercises, conditions, or safety.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["exercise", "condition", "safety",
                                 "biomech", "nutrition", "sleep"],
                    },
                    "lang": {"type": "string", "enum": ["zh", "en"]},
                    "top_k": {"type": "integer", "default": 3},
                },
                "required": ["query"],
            },
        },
        {
            "name": "list_recent_sessions",
            "description": "Get the patient's most recent training sessions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "get_exercise_breakdown",
            "description": "Per-exercise stats: count, avg score, "
                          "best, worst, consistency.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "get_recommendations",
            "description": "ML-driven exercise recommendations based on "
                          "the patient's history and weaknesses.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "compare_to_cohort",
            "description": "Compare patient to peer cohort (avg, percentile).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "predict_recovery",
            "description": "Predict days/sessions to reach a target score.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "target_score": {"type": "number", "default": 85},
                },
                "required": ["user_id"],
            },
        },
    ]


# ============================================================
# Tool implementations
# ============================================================
def _tool_get_user_metrics(args: Dict) -> Dict:
    user_id = args["user_id"]
    try:
        from analytics import (
            calculate_improvement_rate, calculate_adherence,
            get_pain_trend,
        )
        from ml_insights import calculate_risk_score
        return {
            "improvement": calculate_improvement_rate(user_id),
            "adherence": calculate_adherence(user_id),
            "pain_trend": get_pain_trend(user_id),
            "risk": calculate_risk_score(user_id),
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_search_knowledge(args: Dict) -> Dict:
    try:
        from clinical_knowledge import search, init_knowledge_base
        init_knowledge_base()
        results = search(
            args["query"],
            top_k=args.get("top_k", 3),
            category=args.get("category"),
            lang=args.get("lang", "zh"),
        )
        return {"results": results, "count": len(results)}
    except Exception as e:
        return {"error": str(e)}


def _tool_list_recent_sessions(args: Dict) -> Dict:
    try:
        from db import execute_query
        rows = execute_query(
            """
            SELECT exercise, score, rep_count, pain_before, pain_after, created_at
            FROM sessions WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (args["user_id"], args.get("limit", 5)),
        )
        return {"sessions": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e)}


def _tool_get_exercise_breakdown(args: Dict) -> Dict:
    try:
        from analytics import get_exercise_breakdown
        return {"breakdown": get_exercise_breakdown(args["user_id"])}
    except Exception as e:
        return {"error": str(e)}


def _tool_get_recommendations(args: Dict) -> Dict:
    try:
        from ml_insights import recommend_exercises
        return {
            "recommendations": recommend_exercises(
                args["user_id"], top_k=args.get("top_k", 3),
            ),
        }
    except Exception as e:
        return {"error": str(e)}


def _tool_compare_to_cohort(args: Dict) -> Dict:
    try:
        from analytics import compare_to_cohort
        return compare_to_cohort(args["user_id"])
    except Exception as e:
        return {"error": str(e)}


def _tool_predict_recovery(args: Dict) -> Dict:
    try:
        from analytics import predict_recovery_timeline
        return predict_recovery_timeline(
            args["user_id"],
            target_score=float(args.get("target_score", 85)),
        )
    except Exception as e:
        return {"error": str(e)}


_TOOL_HANDLERS: Dict[str, Callable[[Dict], Dict]] = {
    "get_user_metrics": _tool_get_user_metrics,
    "search_knowledge": _tool_search_knowledge,
    "list_recent_sessions": _tool_list_recent_sessions,
    "get_exercise_breakdown": _tool_get_exercise_breakdown,
    "get_recommendations": _tool_get_recommendations,
    "compare_to_cohort": _tool_compare_to_cohort,
    "predict_recovery": _tool_predict_recovery,
}


# ============================================================
# Agent loop
# ============================================================
@dataclass
class AgentResult:
    answer: str
    tool_calls: List[Dict] = field(default_factory=list)
    iterations: int = 0
    used_llm: bool = False
    error: Optional[str] = None


def run_agent(question: str,
              user_id: Optional[str] = None,
              lang: str = "zh",
              max_iterations: int = 5,
              model: str = "claude-sonnet-4-6") -> AgentResult:
    """Run an agentic loop: model calls tools until it produces a final answer."""
    if not _llm_available():
        return _fallback_answer(question, user_id, lang)

    try:
        import anthropic
    except ImportError:
        return _fallback_answer(question, user_id, lang)

    sys_prompt = SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT_EN
    if user_id:
        sys_prompt += f"\n\n當前病人 ID: {user_id}" if lang == "zh" \
                      else f"\n\nCurrent patient ID: {user_id}"

    client = anthropic.Anthropic()
    messages: List[Dict] = [{"role": "user", "content": question}]
    tool_call_log: List[Dict] = []

    for iteration in range(max_iterations):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": sys_prompt,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                tools=_tool_specs(),
                messages=messages,
            )
        except Exception as e:
            return AgentResult(
                answer=f"AI 服務錯誤 / AI service error: {e}",
                iterations=iteration,
                error=str(e),
                tool_calls=tool_call_log,
            )

        if response.stop_reason == "end_turn":
            text_blocks = [
                b.text for b in response.content
                if hasattr(b, "text") and b.text
            ]
            answer = "\n".join(text_blocks).strip() or (
                "（無回應）" if lang == "zh" else "(no response)"
            )
            return AgentResult(
                answer=answer,
                tool_calls=tool_call_log,
                iterations=iteration + 1,
                used_llm=True,
            )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if not (hasattr(block, "type") and block.type == "tool_use"):
                    continue
                handler = _TOOL_HANDLERS.get(block.name)
                if not handler:
                    result = {"error": f"unknown tool: {block.name}"}
                else:
                    try:
                        result = handler(block.input or {})
                    except Exception as e:
                        result = {"error": str(e)}

                tool_call_log.append({
                    "tool": block.name,
                    "input": block.input,
                    "result_summary": _summarize(result),
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False,
                                          default=str),
                })

            messages.append({"role": "user", "content": tool_results})
            continue

        text = "".join(b.text for b in response.content
                       if hasattr(b, "text"))
        return AgentResult(
            answer=text.strip(),
            tool_calls=tool_call_log,
            iterations=iteration + 1,
            used_llm=True,
        )

    return AgentResult(
        answer=("達到最大迭代次數，無法完成回答。"
                if lang == "zh"
                else "Reached max iterations without final answer."),
        tool_calls=tool_call_log,
        iterations=max_iterations,
        used_llm=True,
    )


def _summarize(result: Dict) -> str:
    """Truncate large tool results for log."""
    s = json.dumps(result, ensure_ascii=False, default=str)
    return s[:200] + "..." if len(s) > 200 else s


def _llm_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _fallback_answer(question: str, user_id: Optional[str],
                      lang: str) -> AgentResult:
    """RAG-only fallback when LLM unavailable."""
    try:
        from rag_engine import answer_question
        rag = answer_question(question, user_id=user_id, lang=lang)
        return AgentResult(
            answer=rag.answer,
            iterations=0,
            used_llm=rag.used_llm,
        )
    except Exception:
        return AgentResult(
            answer=("AI 服務目前不可用" if lang == "zh"
                   else "AI service unavailable"),
            iterations=0,
        )
