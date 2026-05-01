"""
多設備同步管理：本地備份 + 雲同步（可選）。
支持設備標識、增量同步、衝突解決。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import history as hist


# 同步配置
SYNC_BACKUP_DIR = Path(os.environ.get(
    "SMART_REHAB_SYNC_DIR",
    Path.home() / ".smart_rehab_sync"
))

DEVICE_ID_FILE = SYNC_BACKUP_DIR / "device_id.json"


def get_device_id() -> str:
    """取得或生成設備 ID。"""
    SYNC_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if DEVICE_ID_FILE.exists():
        data = json.loads(DEVICE_ID_FILE.read_text(encoding="utf-8"))
        return data.get("device_id")

    # Generate new device ID
    device_id = f"dev_{uuid4().hex[:16]}"
    device_name = f"Device-{datetime.now().strftime('%Y%m%d')}"

    DEVICE_ID_FILE.write_text(json.dumps({
        "device_id": device_id,
        "device_name": device_name,
        "created": datetime.now().isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return device_id


def get_device_name() -> str:
    """取得設備名稱。"""
    if DEVICE_ID_FILE.exists():
        data = json.loads(DEVICE_ID_FILE.read_text(encoding="utf-8"))
        return data.get("device_name", "Unknown")
    return "Unknown"


def set_device_name(name: str) -> None:
    """設定設備名稱。"""
    SYNC_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    device_id = get_device_id()

    DEVICE_ID_FILE.write_text(json.dumps({
        "device_id": device_id,
        "device_name": name,
        "created": datetime.now().isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_user_backup_dir(user_name: str) -> Path:
    """取得用戶的備份目錄。"""
    backup_dir = SYNC_BACKUP_DIR / f"users" / user_name
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _get_sync_manifest_path(user_name: str) -> Path:
    """取得同步清單文件路徑。"""
    return _get_user_backup_dir(user_name) / "sync_manifest.json"


def _compute_data_hash(data: Any) -> str:
    """計算數據的 MD5 哈希值。"""
    json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_str.encode()).hexdigest()


def create_local_backup(user_name: str) -> Dict[str, Any]:
    """
    創建本地備份。
    返回備份元數據：{user, timestamp, device_id, checksum}
    """
    user_data = hist.load(user_name)

    backup_dir = _get_user_backup_dir(user_name)
    timestamp = datetime.now().isoformat()
    device_id = get_device_id()

    # Create backup file with timestamp
    backup_file = backup_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    backup_data = {
        "user": user_name,
        "timestamp": timestamp,
        "device_id": device_id,
        "device_name": get_device_name(),
        "data": user_data,
    }

    checksum = _compute_data_hash(user_data)
    backup_data["checksum"] = checksum

    backup_file.write_text(
        json.dumps(backup_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Update manifest
    _update_sync_manifest(user_name, checksum, timestamp)

    return {
        "user": user_name,
        "timestamp": timestamp,
        "device_id": device_id,
        "checksum": checksum,
        "backup_file": str(backup_file),
    }


def restore_from_backup(user_name: str, backup_file: Optional[Path] = None) -> bool:
    """
    從備份恢復。若不指定備份文件，使用最新的。
    """
    backup_dir = _get_user_backup_dir(user_name)

    if backup_file is None:
        # Find latest backup
        backups = sorted(backup_dir.glob("backup_*.json"))
        if not backups:
            return False
        backup_file = backups[-1]

    try:
        backup_data = json.loads(backup_file.read_text(encoding="utf-8"))
        user_data = backup_data.get("data", {})

        # Restore to history
        for key, value in user_data.items():
            if key != "name":  # Don't overwrite name
                hist.save_user_section(user_name, key, value)

        return True
    except Exception:
        return False


def list_backups(user_name: str) -> List[Dict[str, Any]]:
    """列出所有備份。"""
    backup_dir = _get_user_backup_dir(user_name)
    backups = []

    for backup_file in sorted(backup_dir.glob("backup_*.json"), reverse=True):
        try:
            data = json.loads(backup_file.read_text(encoding="utf-8"))
            backups.append({
                "file": str(backup_file),
                "timestamp": data.get("timestamp"),
                "device_id": data.get("device_id"),
                "device_name": data.get("device_name"),
                "checksum": data.get("checksum"),
                "size": backup_file.stat().st_size,
            })
        except Exception:
            pass

    return backups


def _update_sync_manifest(user_name: str, checksum: str, timestamp: str) -> None:
    """更新同步清單。"""
    manifest_file = _get_sync_manifest_path(user_name)

    manifest = {
        "user": user_name,
        "last_sync": timestamp,
        "last_checksum": checksum,
        "device_id": get_device_id(),
        "sync_count": 0,
    }

    if manifest_file.exists():
        existing = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest["sync_count"] = existing.get("sync_count", 0) + 1

    manifest_file.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_sync_status(user_name: str) -> Dict[str, Any]:
    """取得同步狀態。"""
    manifest_file = _get_sync_manifest_path(user_name)

    if not manifest_file.exists():
        return {
            "synced": False,
            "last_sync": None,
            "backup_count": 0,
            "device_id": get_device_id(),
        }

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    backups = list_backups(user_name)

    return {
        "synced": True,
        "last_sync": manifest.get("last_sync"),
        "last_checksum": manifest.get("last_checksum"),
        "sync_count": manifest.get("sync_count", 0),
        "backup_count": len(backups),
        "device_id": get_device_id(),
        "device_name": get_device_name(),
        "latest_backup": backups[0] if backups else None,
    }


def export_for_cloud(user_name: str) -> Optional[Dict[str, Any]]:
    """
    匯出為雲同步格式。
    可用於 Firebase/Supabase 的 POST 操作。
    """
    user_data = hist.load(user_name)
    checksum = _compute_data_hash(user_data)

    return {
        "user": user_name,
        "timestamp": datetime.now().isoformat(),
        "device_id": get_device_id(),
        "device_name": get_device_name(),
        "checksum": checksum,
        "data": user_data,
    }


def import_from_cloud(user_name: str, cloud_data: Dict[str, Any]) -> bool:
    """
    從雲數據導入（衝突解決：雲端優先）。
    """
    try:
        user_data = cloud_data.get("data", {})

        for key, value in user_data.items():
            if key != "name":
                hist.save_user_section(user_name, key, value)

        # Update manifest
        checksum = cloud_data.get("checksum")
        timestamp = cloud_data.get("timestamp")
        _update_sync_manifest(user_name, checksum, timestamp)

        return True
    except Exception:
        return False


def setup_cloud_sync(
    user_name: str,
    cloud_provider: str = "firebase",  # "firebase", "supabase", "custom"
    config: Optional[Dict[str, str]] = None,
) -> bool:
    """
    設置雲同步配置。
    config: {firebase_project, firebase_key} 或 {supabase_url, supabase_key} 等
    """
    SYNC_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    config_file = SYNC_BACKUP_DIR / "cloud_sync_config.json"

    sync_config = {
        "enabled": True,
        "provider": cloud_provider,
        "user": user_name,
        "configured_at": datetime.now().isoformat(),
    }

    if config:
        sync_config.update(config)

    config_file.write_text(
        json.dumps(sync_config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return True


def get_cloud_sync_config() -> Optional[Dict[str, Any]]:
    """取得雲同步配置。"""
    config_file = SYNC_BACKUP_DIR / "cloud_sync_config.json"

    if config_file.exists():
        return json.loads(config_file.read_text(encoding="utf-8"))

    return None
