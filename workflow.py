"""
Workflow orchestrator: declarative multi-step flows.

Replaces ad-hoc step routing with a finite-state machine:
- Define a workflow as ordered steps with guards and side-effects
- Each step has a `should_skip` predicate and an `on_enter` action
- Supports branching (if/else), parallel paths, and resumable state
- Persists progress so users can continue interrupted flows

Built-in workflows:
- onboarding: profile → goals → first exercise → review
- daily_session: warmup → record → analyze → log → reward
- recovery_program: weekly progression with milestones
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional
import json
import time

import streamlit as st

from db import execute_query, execute_update


@dataclass
class WorkflowStep:
    key: str
    title_zh: str
    title_en: str
    route: str  # streamlit step to navigate to
    on_enter: Optional[Callable] = None
    should_skip: Optional[Callable[[Dict], bool]] = None
    is_complete: Optional[Callable[[Dict], bool]] = None
    branch: Optional[Callable[[Dict], str]] = None
    branch_routes: Optional[Dict[str, str]] = None
    icon: str = "•"


@dataclass
class Workflow:
    key: str
    name_zh: str
    name_en: str
    steps: List[WorkflowStep]
    on_complete: Optional[Callable] = None


# ============================================================
# Workflow execution state
# ============================================================
@dataclass
class WorkflowState:
    workflow_key: str
    current_step: int = -1
    started_at: float = field(default_factory=time.time)
    step_data: Dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    branch_path: List[str] = field(default_factory=list)


# ============================================================
# Built-in workflows
# ============================================================
def _onboarding_complete(data: Dict) -> bool:
    user = st.session_state.get("user", {})
    return bool(user.get("name") and user.get("age"))


def _has_first_session(data: Dict) -> bool:
    user = st.session_state.get("user", {})
    user_id = user.get("user_id") if isinstance(user, dict) else None
    if not user_id:
        return False
    rows = execute_query(
        "SELECT COUNT(*) as c FROM sessions WHERE user_id = ?",
        (user_id,),
    )
    return bool(rows and rows[0]["c"] > 0)


def _branch_by_risk(data: Dict) -> str:
    """Route to clinician if high risk, otherwise standard flow."""
    user = st.session_state.get("user", {})
    user_id = user.get("user_id") if isinstance(user, dict) else None
    if not user_id:
        return "standard"
    try:
        from ml_insights import calculate_risk_score
        risk = calculate_risk_score(user_id)
        return "high_risk" if risk["risk_score"] >= 70 else "standard"
    except Exception:
        return "standard"


WORKFLOWS: Dict[str, Workflow] = {
    "onboarding": Workflow(
        key="onboarding",
        name_zh="新手導引",
        name_en="Onboarding",
        steps=[
            WorkflowStep(
                key="welcome",
                title_zh="歡迎",
                title_en="Welcome",
                route="welcome",
                icon="👋",
            ),
            WorkflowStep(
                key="profile",
                title_zh="基本資料",
                title_en="Your Profile",
                route="profile",
                is_complete=_onboarding_complete,
                icon="👤",
            ),
            WorkflowStep(
                key="goals",
                title_zh="設定目標",
                title_en="Set Goals",
                route="settings",
                icon="🎯",
            ),
            WorkflowStep(
                key="first_session",
                title_zh="第一次訓練",
                title_en="First Session",
                route="auto_exercise",
                is_complete=_has_first_session,
                icon="🎬",
            ),
            WorkflowStep(
                key="review",
                title_zh="檢視成果",
                title_en="Review",
                route="result",
                icon="📊",
            ),
        ],
    ),

    "daily_session": Workflow(
        key="daily_session",
        name_zh="每日訓練",
        name_en="Daily Session",
        steps=[
            WorkflowStep(
                key="warmup",
                title_zh="熱身",
                title_en="Warmup",
                route="ai_media",
                icon="🔥",
            ),
            WorkflowStep(
                key="branch",
                title_zh="路徑選擇",
                title_en="Routing",
                route="home",
                branch=_branch_by_risk,
                branch_routes={
                    "high_risk": "clinician",
                    "standard": "live_enhanced",
                },
                icon="🔀",
            ),
            WorkflowStep(
                key="record",
                title_zh="錄影訓練",
                title_en="Record",
                route="live_enhanced",
                icon="🎥",
            ),
            WorkflowStep(
                key="analyze",
                title_zh="自動分析",
                title_en="Analyze",
                route="auto_exercise",
                icon="🧠",
            ),
            WorkflowStep(
                key="log",
                title_zh="記錄狀態",
                title_en="Log Status",
                route="journal",
                icon="📝",
            ),
            WorkflowStep(
                key="reward",
                title_zh="領取任務獎勵",
                title_en="Claim Rewards",
                route="quests",
                icon="🏆",
            ),
        ],
    ),

    "recovery_check": Workflow(
        key="recovery_check",
        name_zh="復原檢查",
        name_en="Recovery Check",
        steps=[
            WorkflowStep(
                key="vitals",
                title_zh="生命徵象",
                title_en="Vitals",
                route="vitals",
                icon="🌡️",
            ),
            WorkflowStep(
                key="pain",
                title_zh="疼痛地圖",
                title_en="Pain Map",
                route="pain_map",
                icon="🗺️",
            ),
            WorkflowStep(
                key="sleep",
                title_zh="睡眠",
                title_en="Sleep",
                route="sleep",
                icon="😴",
            ),
            WorkflowStep(
                key="analytics",
                title_zh="總結分析",
                title_en="Analytics",
                route="analytics",
                icon="📊",
            ),
        ],
    ),
}


# ============================================================
# Public API
# ============================================================
def start_workflow(user_id: str, workflow_key: str) -> bool:
    """Start a workflow. Persists to DB and sets session state."""
    if workflow_key not in WORKFLOWS:
        return False

    state = WorkflowState(workflow_key=workflow_key, current_step=-1)
    _save_state(user_id, state)
    st.session_state.active_workflow = state
    return True


def advance_workflow(user_id: str) -> Optional[WorkflowStep]:
    """Move to next step (skipping any that should be skipped)."""
    state = get_active_state(user_id)
    if not state or state.completed:
        return None

    workflow = WORKFLOWS.get(state.workflow_key)
    if not workflow:
        return None

    state.current_step += 1
    while state.current_step < len(workflow.steps):
        step = workflow.steps[state.current_step]
        if step.should_skip and step.should_skip(state.step_data):
            state.current_step += 1
            continue
        if step.is_complete and step.is_complete(state.step_data):
            state.current_step += 1
            continue
        routed_step = step
        if step.branch:
            branch_key = step.branch(state.step_data)
            state.branch_path.append(branch_key)
            state.step_data[f"{step.key}_branch"] = branch_key
            if step.branch_routes and branch_key in step.branch_routes:
                routed_step = replace(step, route=step.branch_routes[branch_key])
        _save_state(user_id, state)
        if routed_step.on_enter:
            try:
                routed_step.on_enter()
            except Exception:
                pass
        return routed_step

    state.completed = True
    _save_state(user_id, state)
    if workflow.on_complete:
        try:
            workflow.on_complete()
        except Exception:
            pass
    st.session_state.pop("active_workflow", None)
    return None


def get_active_state(user_id: str) -> Optional[WorkflowState]:
    """Get current workflow state for user."""
    if "active_workflow" in st.session_state:
        return st.session_state.active_workflow

    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = 'workflow_state'
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )
    if not rows:
        return None

    try:
        data = json.loads(rows[0]["data_json"])
        if data.get("completed"):
            return None
        state = WorkflowState(
            workflow_key=data["workflow_key"],
            current_step=data.get("current_step", -1),
            started_at=data.get("started_at", time.time()),
            step_data=data.get("step_data", {}),
            completed=data.get("completed", False),
            branch_path=data.get("branch_path", []),
        )
        st.session_state.active_workflow = state
        return state
    except Exception:
        return None


def cancel_workflow(user_id: str) -> None:
    """Cancel active workflow."""
    st.session_state.pop("active_workflow", None)
    try:
        execute_update(
            """
            DELETE FROM offline_cache
            WHERE user_id = ? AND cache_type = 'workflow_state'
            """,
            (user_id,),
        )
    except Exception:
        pass


def get_progress(user_id: str) -> Optional[Dict]:
    """Get progress info for active workflow."""
    state = get_active_state(user_id)
    if not state:
        return None
    workflow = WORKFLOWS.get(state.workflow_key)
    if not workflow:
        return None

    total = len(workflow.steps)
    if total == 0:
        return None

    current_index = min(max(state.current_step, 0), total - 1)
    completed_count = min(max(state.current_step + 1, 0), total)
    return {
        "workflow": state.workflow_key,
        "name_zh": workflow.name_zh,
        "name_en": workflow.name_en,
        "current_step": state.current_step,
        "completed_count": completed_count,
        "total_steps": total,
        "progress_pct": (completed_count / total) * 100,
        "current_title_zh": workflow.steps[current_index].title_zh,
        "current_title_en": workflow.steps[current_index].title_en,
    }


def _save_state(user_id: str, state: WorkflowState) -> None:
    """Persist state to DB."""
    payload = {
        "workflow_key": state.workflow_key,
        "current_step": state.current_step,
        "started_at": state.started_at,
        "step_data": state.step_data,
        "completed": state.completed,
        "branch_path": state.branch_path,
    }
    try:
        execute_update(
            """
            DELETE FROM offline_cache
            WHERE user_id = ? AND cache_type = 'workflow_state'
            """,
            (user_id,),
        )
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, 'workflow_state', ?, datetime('now', '+30 days'))
            """,
            (user_id, json.dumps(payload, ensure_ascii=False, default=str)),
        )
    except Exception:
        pass


def render_workflow_indicator() -> None:
    """Render a top-of-page progress indicator if a workflow is active."""
    user = st.session_state.get("user", {})
    user_id = user.get("user_id") if isinstance(user, dict) else None
    if not user_id:
        return

    progress = get_progress(user_id)
    if not progress:
        return

    lang = st.session_state.get("settings", {}).get("lang", "zh")
    name = progress["name_zh"] if lang == "zh" else progress["name_en"]
    step = progress["current_title_zh"] if lang == "zh" else progress["current_title_en"]

    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.caption(
                f"📋 {name} • {'目前' if lang == 'zh' else 'Current'}: {step}"
            )
            st.progress(progress["progress_pct"] / 100)
            st.caption(
                f"{progress['completed_count']}/{progress['total_steps']}"
            )
        with c2:
            if st.button(
                "▶ " + ("下一步" if lang == "zh" else "Next"),
                key="wf_next",
                use_container_width=True,
                type="primary",
            ):
                step_obj = advance_workflow(user_id)
                if step_obj:
                    from app_state import goto
                    goto(step_obj.route)
        with c3:
            if st.button(
                "✕ " + ("結束" if lang == "zh" else "Exit"),
                key="wf_cancel",
                use_container_width=True,
            ):
                cancel_workflow(user_id)
                st.rerun()
