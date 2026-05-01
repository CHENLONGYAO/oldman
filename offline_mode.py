"""
Offline mode: local caching and sync queue.

Allows users to use the app offline, queuing changes for later sync.
"""
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from db import execute_update, execute_query


def cache_data(user_id: str, cache_type: str, data: Any,
               expires_hours: int = 24) -> bool:
    """Cache data locally for offline use."""
    expires_at = (datetime.now() + timedelta(hours=expires_hours)).isoformat()
    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, cache_type, json.dumps(data), expires_at)
        )
        return True
    except Exception:
        return False


def get_cached_data(user_id: str, cache_type: str) -> Optional[Any]:
    """Retrieve cached data if still valid."""
    rows = execute_query(
        """
        SELECT data_json, expires_at FROM offline_cache
        WHERE user_id = ? AND cache_type = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id, cache_type)
    )

    if not rows:
        return None

    row = rows[0]
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.now() > expires:
        return None

    try:
        return json.loads(row["data_json"])
    except Exception:
        return None


def clear_expired_cache() -> int:
    """Delete expired cache entries. Returns count cleared."""
    now = datetime.now().isoformat()
    return execute_update(
        "DELETE FROM offline_cache WHERE expires_at < ?",
        (now,)
    )


def queue_sync_action(user_id: str, action_type: str, payload: Dict) -> bool:
    """Queue an action for later sync when online."""
    queue_data = {
        "action": action_type,
        "payload": payload,
        "queued_at": time.time(),
    }
    return cache_data(user_id, f"sync_queue_{action_type}", queue_data,
                      expires_hours=72)


def get_pending_sync_actions(user_id: str) -> List[Dict]:
    """Get all pending sync actions."""
    rows = execute_query(
        """
        SELECT cache_type, data_json FROM offline_cache
        WHERE user_id = ? AND cache_type LIKE 'sync_queue_%'
        ORDER BY created_at ASC
        """,
        (user_id,)
    )

    actions = []
    for row in rows:
        try:
            data = json.loads(row["data_json"])
            actions.append(data)
        except Exception:
            continue
    return actions


def clear_synced_actions(user_id: str) -> int:
    """Clear queue after successful sync."""
    return execute_update(
        """
        DELETE FROM offline_cache
        WHERE user_id = ? AND cache_type LIKE 'sync_queue_%'
        """,
        (user_id,)
    )


def is_online() -> bool:
    """Check connectivity (simple heuristic - try DNS lookup)."""
    try:
        import socket
        socket.gethostbyname("8.8.8.8")
        return True
    except Exception:
        return False
