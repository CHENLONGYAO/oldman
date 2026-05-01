"""
Audit log: HIPAA-style compliance logging for sensitive operations.

Logs:
- Authentication events (login/logout/failed)
- Data access (PHI viewing)
- Data modifications (record create/update/delete)
- Permission changes
- Exports (CSV/PDF/backup)

Each entry: timestamp, user_id, ip, action, resource, success, details.
Read-only after write — append-only design.
"""
from __future__ import annotations
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from db import execute_query, execute_update


AUDIT_ACTIONS = {
    # Auth
    "login_success": {"category": "auth", "severity": "info"},
    "login_failed": {"category": "auth", "severity": "warning"},
    "logout": {"category": "auth", "severity": "info"},
    "password_change": {"category": "auth", "severity": "info"},
    "session_expired": {"category": "auth", "severity": "info"},
    # Data access
    "view_session": {"category": "phi_access", "severity": "info"},
    "view_vitals": {"category": "phi_access", "severity": "info"},
    "view_pain_record": {"category": "phi_access", "severity": "info"},
    "view_medication": {"category": "phi_access", "severity": "info"},
    "view_other_user": {"category": "phi_access", "severity": "warning"},
    # Data mutation
    "create_session": {"category": "data_mutation", "severity": "info"},
    "delete_session": {"category": "data_mutation", "severity": "warning"},
    "update_profile": {"category": "data_mutation", "severity": "info"},
    "delete_account": {"category": "data_mutation", "severity": "critical"},
    # Permissions
    "role_change": {"category": "permission", "severity": "warning"},
    "share_data": {"category": "permission", "severity": "info"},
    "revoke_access": {"category": "permission", "severity": "info"},
    # Exports
    "export_pdf": {"category": "export", "severity": "info"},
    "export_csv": {"category": "export", "severity": "info"},
    "create_backup": {"category": "export", "severity": "info"},
    "restore_backup": {"category": "export", "severity": "warning"},
    # System
    "config_change": {"category": "system", "severity": "warning"},
    "data_anonymized": {"category": "system", "severity": "info"},
}


def _ensure_table() -> None:
    """Create audit log table if not exists. Append-only by convention."""
    try:
        execute_update(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT NOT NULL,
                category TEXT,
                severity TEXT,
                resource_type TEXT,
                resource_id TEXT,
                ip_address TEXT,
                user_agent TEXT,
                success INTEGER DEFAULT 1,
                details_json TEXT,
                hash_chain TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """,
            (),
        )
        execute_update(
            "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)",
            (),
        )
        execute_update(
            "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)",
            (),
        )
        execute_update(
            "CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(created_at)",
            (),
        )
    except Exception:
        pass


def log(action: str, user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        success: bool = True,
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None) -> bool:
    """Append a log entry. Hash-chain links to previous entry for tamper detection."""
    _ensure_table()

    action_def = AUDIT_ACTIONS.get(action, {})
    category = action_def.get("category", "other")
    severity = action_def.get("severity", "info")

    prev_hash = _get_last_hash()
    payload_str = json.dumps({
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "success": success,
        "details": details or {},
        "ts": datetime.now().isoformat(),
    }, sort_keys=True, ensure_ascii=False)
    chain_input = (prev_hash + payload_str).encode("utf-8")
    new_hash = hashlib.sha256(chain_input).hexdigest()

    try:
        execute_update(
            """
            INSERT INTO audit_log (
                user_id, action, category, severity,
                resource_type, resource_id, ip_address, user_agent,
                success, details_json, hash_chain
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, action, category, severity,
                resource_type, resource_id, ip_address, user_agent,
                1 if success else 0,
                json.dumps(details or {}, ensure_ascii=False),
                new_hash,
            ),
        )
        return True
    except Exception:
        return False


def _get_last_hash() -> str:
    """Get hash of last audit entry for chain integrity."""
    try:
        rows = execute_query(
            "SELECT hash_chain FROM audit_log ORDER BY id DESC LIMIT 1",
            (),
        )
        if rows and rows[0].get("hash_chain"):
            return rows[0]["hash_chain"]
    except Exception:
        pass
    return "GENESIS"


def query_logs(user_id: Optional[str] = None,
               action: Optional[str] = None,
               category: Optional[str] = None,
               severity: Optional[str] = None,
               start_date: Optional[str] = None,
               end_date: Optional[str] = None,
               limit: int = 100) -> List[Dict]:
    """Query audit logs with filters."""
    _ensure_table()
    conditions = []
    params = []

    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if action:
        conditions.append("action = ?")
        params.append(action)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if start_date:
        conditions.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= ?")
        params.append(end_date)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT * FROM audit_log {where}
        ORDER BY created_at DESC LIMIT ?
    """
    params.append(limit)

    try:
        rows = execute_query(sql, tuple(params))
        return [dict(r) for r in rows]
    except Exception:
        return []


def verify_integrity(start_id: int = 1, end_id: Optional[int] = None) -> Dict:
    """Verify hash-chain integrity. Returns first broken link if any."""
    _ensure_table()

    where = "WHERE id >= ?"
    params: list = [start_id]
    if end_id is not None:
        where += " AND id <= ?"
        params.append(end_id)

    try:
        rows = execute_query(
            f"SELECT * FROM audit_log {where} ORDER BY id ASC",
            tuple(params),
        )
    except Exception:
        return {"verified": False, "error": "query_failed"}

    prev_hash = "GENESIS"
    if start_id > 1:
        prev_rows = execute_query(
            "SELECT hash_chain FROM audit_log WHERE id = ?",
            (start_id - 1,),
        )
        if prev_rows:
            prev_hash = prev_rows[0]["hash_chain"]

    for row in rows:
        payload_str = json.dumps({
            "user_id": row["user_id"],
            "action": row["action"],
            "resource_type": row["resource_type"],
            "resource_id": row["resource_id"],
            "success": bool(row["success"]),
            "details": json.loads(row["details_json"]) if row["details_json"] else {},
            "ts": row["created_at"],
        }, sort_keys=True, ensure_ascii=False)
        expected = hashlib.sha256(
            (prev_hash + payload_str).encode("utf-8")
        ).hexdigest()

        if expected != row["hash_chain"]:
            return {
                "verified": False,
                "broken_at_id": row["id"],
                "expected": expected,
                "actual": row["hash_chain"],
            }
        prev_hash = row["hash_chain"]

    return {"verified": True, "entries_checked": len(rows)}


def get_user_activity_summary(user_id: str, days: int = 30) -> Dict:
    """Aggregate activity for a user."""
    _ensure_table()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    rows = execute_query(
        """
        SELECT category, action, COUNT(*) as count
        FROM audit_log
        WHERE user_id = ? AND created_at >= ?
        GROUP BY category, action
        ORDER BY count DESC
        """,
        (user_id, cutoff),
    )

    summary = {"total": 0, "by_category": {}, "top_actions": []}
    for r in rows:
        summary["total"] += r["count"]
        summary["by_category"].setdefault(r["category"], 0)
        summary["by_category"][r["category"]] += r["count"]
        summary["top_actions"].append({
            "action": r["action"],
            "count": r["count"],
        })

    summary["top_actions"] = summary["top_actions"][:10]
    return summary


def export_logs_csv(filters: Dict) -> str:
    """Export filtered logs as CSV string."""
    logs = query_logs(**filters, limit=10000)
    if not logs:
        return ""

    headers = ["created_at", "user_id", "action", "category", "severity",
               "resource_type", "resource_id", "ip_address", "success"]
    lines = [",".join(headers)]
    for log_entry in logs:
        row = [
            str(log_entry.get(h, "")).replace(",", ";").replace("\n", " ")
            for h in headers
        ]
        lines.append(",".join(row))
    return "\n".join(lines)
