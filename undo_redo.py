"""
Undo/redo system for data-mutating actions.

Records reversible actions and allows users to undo within a window
(default 30 minutes). Used for:
- Deleted journal entries / vitals / pain records
- Modified profile fields
- Quest claims (rare, but possible)

Each action stores enough info to restore the previous state.
Stored in offline_cache for cross-session persistence.
"""
from __future__ import annotations
import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Deque, List, Optional

from db import execute_query, execute_update


@dataclass
class UndoableAction:
    action_id: str
    user_id: str
    action_type: str  # "delete" / "update" / "create"
    resource: str     # table or domain name
    label_zh: str
    label_en: str
    undo_payload: Dict
    redo_payload: Optional[Dict] = None
    created_at: float = field(default_factory=time.time)


# In-memory stacks per user
_UNDO_STACKS: Dict[str, Deque[UndoableAction]] = {}
_REDO_STACKS: Dict[str, Deque[UndoableAction]] = {}
_MAX_STACK = 25
_DEFAULT_WINDOW_S = 1800  # 30 minutes


def push_action(action: UndoableAction) -> None:
    """Push an undoable action onto user's stack."""
    stack = _UNDO_STACKS.setdefault(action.user_id, deque(maxlen=_MAX_STACK))
    stack.append(action)
    _REDO_STACKS.pop(action.user_id, None)
    _persist_action(action)


def can_undo(user_id: str) -> bool:
    return bool(_UNDO_STACKS.get(user_id))


def can_redo(user_id: str) -> bool:
    return bool(_REDO_STACKS.get(user_id))


def get_recent_actions(user_id: str, limit: int = 5,
                        window_s: int = _DEFAULT_WINDOW_S) -> List[UndoableAction]:
    """List actions still within the undo window."""
    stack = _UNDO_STACKS.get(user_id) or deque()
    cutoff = time.time() - window_s
    return [a for a in reversed(stack) if a.created_at >= cutoff][:limit]


def undo(user_id: str) -> Optional[Dict]:
    """Undo the most recent action."""
    stack = _UNDO_STACKS.get(user_id)
    if not stack:
        return None

    action = stack.pop()
    if time.time() - action.created_at > _DEFAULT_WINDOW_S:
        return {"success": False, "reason": "expired"}

    success = _execute_undo(action)
    if success:
        redo_stack = _REDO_STACKS.setdefault(user_id, deque(maxlen=_MAX_STACK))
        redo_stack.append(action)

    return {
        "success": success,
        "label_zh": action.label_zh,
        "label_en": action.label_en,
        "resource": action.resource,
    }


def redo(user_id: str) -> Optional[Dict]:
    """Redo the last undone action."""
    redo_stack = _REDO_STACKS.get(user_id)
    if not redo_stack:
        return None

    action = redo_stack.pop()
    success = _execute_redo(action)
    if success:
        stack = _UNDO_STACKS.setdefault(user_id, deque(maxlen=_MAX_STACK))
        stack.append(action)

    return {
        "success": success,
        "label_zh": action.label_zh,
        "label_en": action.label_en,
    }


# ============================================================
# Action helpers — wrap mutations to make them undoable
# ============================================================
def make_delete_action(user_id: str, resource: str, row_id: int,
                        full_row: Dict, label_zh: str = "",
                        label_en: str = "") -> UndoableAction:
    """Wrap a deletion as undoable."""
    return UndoableAction(
        action_id=f"del_{resource}_{row_id}_{int(time.time() * 1000)}",
        user_id=user_id,
        action_type="delete",
        resource=resource,
        label_zh=label_zh or f"刪除 {resource} #{row_id}",
        label_en=label_en or f"Delete {resource} #{row_id}",
        undo_payload={"row": full_row, "table": resource},
        redo_payload={"row_id": row_id, "table": resource},
    )


def make_update_action(user_id: str, resource: str, row_id: int,
                        before: Dict, after: Dict,
                        label_zh: str = "", label_en: str = "") -> UndoableAction:
    """Wrap an update as undoable."""
    return UndoableAction(
        action_id=f"upd_{resource}_{row_id}_{int(time.time() * 1000)}",
        user_id=user_id,
        action_type="update",
        resource=resource,
        label_zh=label_zh or f"更新 {resource} #{row_id}",
        label_en=label_en or f"Update {resource} #{row_id}",
        undo_payload={"row_id": row_id, "values": before, "table": resource},
        redo_payload={"row_id": row_id, "values": after, "table": resource},
    )


# ============================================================
# Internal: execute undo/redo
# ============================================================
def _execute_undo(action: UndoableAction) -> bool:
    """Apply the inverse of the original action."""
    payload = action.undo_payload
    table = payload.get("table")
    if not table:
        return False

    try:
        if action.action_type == "delete":
            row = payload.get("row", {})
            cols = [k for k in row.keys() if k != "id"]
            placeholders = ",".join("?" * len(cols))
            values = tuple(row.get(c) for c in cols)
            execute_update(
                f"INSERT INTO {table} ({','.join(cols)}) "
                f"VALUES ({placeholders})",
                values,
            )
            return True

        if action.action_type == "update":
            row_id = payload["row_id"]
            values = payload["values"]
            set_clause = ", ".join(f"{k} = ?" for k in values.keys())
            params = tuple(values.values()) + (row_id,)
            execute_update(
                f"UPDATE {table} SET {set_clause} WHERE id = ?",
                params,
            )
            return True

        if action.action_type == "create":
            row_id = payload.get("row_id")
            if row_id is not None:
                execute_update(
                    f"DELETE FROM {table} WHERE id = ?",
                    (row_id,),
                )
                return True
    except Exception:
        return False
    return False


def _execute_redo(action: UndoableAction) -> bool:
    """Re-apply the original action."""
    payload = action.redo_payload or {}
    table = payload.get("table")
    if not table:
        return False

    try:
        if action.action_type == "delete":
            row_id = payload.get("row_id")
            if row_id is not None:
                execute_update(
                    f"DELETE FROM {table} WHERE id = ?",
                    (row_id,),
                )
                return True

        if action.action_type == "update":
            row_id = payload["row_id"]
            values = payload["values"]
            set_clause = ", ".join(f"{k} = ?" for k in values.keys())
            params = tuple(values.values()) + (row_id,)
            execute_update(
                f"UPDATE {table} SET {set_clause} WHERE id = ?",
                params,
            )
            return True
    except Exception:
        return False
    return False


def _persist_action(action: UndoableAction) -> None:
    """Persist action so it survives session reload."""
    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, 'undo_action', ?, datetime('now', '+1 hour'))
            """,
            (
                action.user_id,
                json.dumps({
                    "action_id": action.action_id,
                    "action_type": action.action_type,
                    "resource": action.resource,
                    "label_zh": action.label_zh,
                    "label_en": action.label_en,
                    "undo_payload": action.undo_payload,
                    "redo_payload": action.redo_payload,
                    "created_at": action.created_at,
                }, ensure_ascii=False, default=str),
            ),
        )
    except Exception:
        pass


# ============================================================
# UI helper
# ============================================================
def render_undo_toast(user_id: str, lang: str = "zh") -> None:
    """Render a small undo button if there's a recent action."""
    import streamlit as st

    actions = get_recent_actions(user_id, limit=1, window_s=60)
    if not actions:
        return

    action = actions[0]
    label = action.label_zh if lang == "zh" else action.label_en

    cols = st.columns([5, 1])
    with cols[0]:
        st.caption(f"⏪ {label}")
    with cols[1]:
        if st.button(
            "↶ " + ("還原" if lang == "zh" else "Undo"),
            key=f"undo_{action.action_id}",
        ):
            result = undo(user_id)
            if result and result.get("success"):
                st.toast(
                    "✓ " + ("已還原" if lang == "zh" else "Undone")
                )
                st.rerun()
