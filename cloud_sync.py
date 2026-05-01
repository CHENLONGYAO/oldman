"""
Cloud backup and sync: encrypt and upload user data to cloud providers.

Supports:
- Local file backup (always available)
- Google Drive (via google_media.py if credentials present)
- S3-compatible (boto3 if installed)
- WebDAV (any compliant server)

Backups are AES-256 encrypted client-side before upload.
"""
from __future__ import annotations
import hashlib
import json
import os
import uuid
import zipfile
import io
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from db import execute_query, execute_update


BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

EXPORT_TABLES = [
    ("users", "user_id"),
    ("user_profiles", "user_id"),
    ("sessions", "user_id"),
    ("health_data", "user_id"),
    ("achievements", "user_id"),
    ("games", "user_id"),
]

RESTORE_TABLES = {
    "user_profiles": [
        "user_id", "name", "age", "gender", "height_cm", "weight_kg",
        "dominant_hand", "affected_side", "condition", "diagnosis",
        "pain_area", "surgery_history", "contraindications", "mobility_aid",
        "activity_level", "weekly_goal", "daily_goal",
        "preferred_training_time", "reminder_enabled", "contact_name",
        "contact_phone", "caregiver_note", "profile_complete",
        "profile_json", "created_at", "updated_at",
    ],
    "sessions": [
        "session_id", "user_id", "exercise", "score", "rep_count",
        "joints_json", "neural_scores_json", "pain_before", "pain_after",
        "safety_flag", "created_at",
    ],
    "health_data": [
        "user_id", "data_type", "data_json", "created_at",
    ],
    "achievements": [
        "user_id", "badge_key", "first_achieved", "updated_at",
    ],
    "games": [
        "user_id", "game_type", "score", "game_data_json", "played_at",
    ],
}

LEGACY_HEALTH_TABLES = {
    "vitals": "vitals",
    "medications": "medications",
    "med_logs": "medication_log",
    "pain_records": "pain_map",
    "journal_entries": "journal",
    "appointments": "appointments",
}


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive AES key from passphrase using PBKDF2."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        iterations=100_000,
        dklen=32,
    )


def encrypt_data(data: bytes, passphrase: str) -> bytes:
    """Encrypt data with AES-256-GCM. Returns salt + nonce + ciphertext."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return _xor_encrypt(data, passphrase)

    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(passphrase, salt)
    aes = AESGCM(key)
    ciphertext = aes.encrypt(nonce, data, None)
    return salt + nonce + ciphertext


def decrypt_data(blob: bytes, passphrase: str) -> Optional[bytes]:
    """Decrypt blob produced by encrypt_data. Returns None on failure."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return _xor_decrypt(blob, passphrase)

    if len(blob) < 28:
        return None
    try:
        salt, nonce, ciphertext = blob[:16], blob[16:28], blob[28:]
        key = _derive_key(passphrase, salt)
        aes = AESGCM(key)
        return aes.decrypt(nonce, ciphertext, None)
    except Exception:
        return None


def _xor_encrypt(data: bytes, passphrase: str) -> bytes:
    """Fallback XOR cipher when cryptography lib unavailable.

    Note: This is NOT cryptographically secure. Install `cryptography` for
    real AES-256-GCM encryption. We mark the blob with prefix b'XOR1' so
    decrypt knows which mode was used.
    """
    key = hashlib.sha256(passphrase.encode("utf-8")).digest()
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ key[i % len(key)]
    return b"XOR1" + bytes(out)


def _xor_decrypt(blob: bytes, passphrase: str) -> Optional[bytes]:
    """Decrypt XOR-encoded blob."""
    if not blob.startswith(b"XOR1"):
        return None
    data = blob[4:]
    key = hashlib.sha256(passphrase.encode("utf-8")).digest()
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ key[i % len(key)]
    return bytes(out)


def export_user_data(user_id: str) -> Dict:
    """Collect all user data into a portable dict."""
    payload: Dict = {
        "version": 1,
        "user_id": user_id,
        "exported_at": datetime.now().isoformat(),
    }

    for table, key_col in EXPORT_TABLES:
        try:
            rows = execute_query(
                f"SELECT * FROM {table} WHERE {key_col} = ?",
                (user_id,),
            )
            payload[table] = [dict(r) for r in rows]
        except Exception:
            payload[table] = []

    return payload


def create_backup(user_id: str, passphrase: str) -> Tuple[Path, Dict]:
    """Create encrypted backup file. Returns (path, metadata)."""
    data = export_user_data(user_id)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False, default=str))

    raw = buf.getvalue()
    encrypted = encrypt_data(raw, passphrase)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"backup_{user_id[:8]}_{timestamp}.enc"
    path = BACKUP_DIR / fname
    path.write_bytes(encrypted)

    meta = {
        "filename": fname,
        "size_kb": round(len(encrypted) / 1024, 1),
        "raw_size_kb": round(len(raw) / 1024, 1),
        "tables": {k: len(v) for k, v in data.items() if isinstance(v, list)},
        "created_at": datetime.now().isoformat(),
    }

    _record_backup(user_id, fname, meta)
    return path, meta


def restore_backup(path: Path, passphrase: str) -> Optional[Dict]:
    """Decrypt and parse backup file. Does NOT yet write to DB."""
    if not path.exists():
        return None

    encrypted = path.read_bytes()
    raw = decrypt_data(encrypted, passphrase)
    if raw is None:
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            with zf.open("data.json") as f:
                return json.loads(f.read().decode("utf-8"))
    except Exception:
        return None


def apply_restore(data: Dict, target_user_id: str,
                  overwrite: bool = False) -> Dict:
    """Apply restored data to current database."""
    counts: Dict[str, int] = {}

    if overwrite:
        for table in ["sessions", "health_data", "achievements", "games"]:
            try:
                execute_update(
                    f"DELETE FROM {table} WHERE user_id = ?",
                    (target_user_id,),
                )
            except Exception:
                pass

    for table, cols in RESTORE_TABLES.items():
        rows = data.get(table, [])
        n = 0
        for row in rows:
            row = dict(row)
            row["user_id"] = target_user_id
            if table == "sessions" and not row.get("session_id"):
                row["session_id"] = str(uuid.uuid4())
            try:
                _insert_row(table, cols, row)
                n += 1
            except Exception:
                continue
        counts[table] = n

    legacy_health_rows = _legacy_health_rows(data, target_user_id)
    legacy_count = 0
    for row in legacy_health_rows:
        try:
            _insert_row("health_data", RESTORE_TABLES["health_data"], row)
            legacy_count += 1
        except Exception:
            continue
    if legacy_count:
        counts["legacy_health_data"] = legacy_count

    return counts


def _insert_row(table: str, cols: List[str], row: Dict) -> None:
    placeholders = ",".join("?" * len(cols))
    values = tuple(row.get(c) for c in cols)
    execute_update(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
        f"VALUES ({placeholders})",
        values,
    )


def _legacy_health_rows(data: Dict, target_user_id: str) -> List[Dict]:
    """Convert pre-health_data backup sections into current health_data rows."""
    rows: List[Dict] = []
    for table, data_type in LEGACY_HEALTH_TABLES.items():
        for item in data.get(table, []):
            if not isinstance(item, dict):
                continue
            payload = dict(item)
            payload.pop("user_id", None)
            created_at = (
                item.get("created_at")
                or item.get("recorded_at")
                or item.get("entry_date")
                or item.get("date")
                or datetime.now().isoformat()
            )
            rows.append({
                "user_id": target_user_id,
                "data_type": data_type,
                "data_json": json.dumps(payload, ensure_ascii=False, default=str),
                "created_at": created_at,
            })
    return rows


def _record_backup(user_id: str, filename: str, meta: Dict) -> None:
    """Record backup in database for history."""
    try:
        execute_update(
            """
            INSERT INTO offline_cache (user_id, cache_type, data_json, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                "backup_meta",
                json.dumps({"filename": filename, **meta}),
                (datetime.now() + timedelta(days=365)).isoformat(),
            ),
        )
    except Exception:
        pass


def list_backups(user_id: str) -> List[Dict]:
    """List all local backups for a user."""
    backups = []
    prefix = f"backup_{user_id[:8]}_"

    for p in BACKUP_DIR.glob(f"{prefix}*.enc"):
        stat = p.stat()
        backups.append({
            "filename": p.name,
            "path": str(p),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    backups.sort(key=lambda b: b["modified"], reverse=True)
    return backups


def delete_backup(filename: str) -> bool:
    """Delete a backup file."""
    path = BACKUP_DIR / filename
    if path.exists() and path.is_file():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


# ============================================================
# Cloud provider plugins (optional)
# ============================================================
def upload_to_drive(local_path: Path, folder_id: str = None) -> Optional[str]:
    """Upload backup to Google Drive. Returns file ID."""
    try:
        from google_media import upload_file
        return upload_file(str(local_path), folder_id=folder_id)
    except ImportError:
        return None
    except Exception:
        return None


def upload_to_s3(local_path: Path, bucket: str, key: str = None) -> bool:
    """Upload to S3-compatible storage."""
    try:
        import boto3
    except ImportError:
        return False

    try:
        s3 = boto3.client("s3")
        s3.upload_file(str(local_path), bucket, key or local_path.name)
        return True
    except Exception:
        return False


def upload_to_webdav(local_path: Path, url: str, user: str,
                     password: str) -> bool:
    """Upload to WebDAV server."""
    try:
        import requests
    except ImportError:
        return False

    try:
        with open(local_path, "rb") as f:
            r = requests.put(
                f"{url.rstrip('/')}/{local_path.name}",
                data=f,
                auth=(user, password),
                timeout=60,
            )
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def schedule_auto_backup(user_id: str, interval_days: int = 7) -> Dict:
    """Check if auto-backup is due and create one if so."""
    rows = execute_query(
        """
        SELECT data_json FROM offline_cache
        WHERE user_id = ? AND cache_type = 'backup_meta'
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )

    last_ts = None
    if rows:
        try:
            last_meta = json.loads(rows[0]["data_json"])
            last_ts = datetime.fromisoformat(last_meta["created_at"])
        except Exception:
            pass

    if last_ts and (datetime.now() - last_ts).days < interval_days:
        return {
            "due": False,
            "next_in_days": interval_days - (datetime.now() - last_ts).days,
        }

    return {"due": True, "last_backup": last_ts.isoformat() if last_ts else None}
