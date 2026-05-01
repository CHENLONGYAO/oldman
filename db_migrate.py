"""
Migration script: Convert JSON user data to SQLite database.

Run once on first startup to migrate existing user_data/*.json files
to smart_rehab.db SQLite database.
"""
import json
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Tuple

from db import (
    init_db, insert_user, insert_session, insert_health_data,
    execute_update, get_user_by_username, update_user_profile
)


def migrate_json_to_sqlite() -> Tuple[bool, str]:
    """
    Migrate all JSON user files to SQLite database.

    Returns: (success, message)
    """
    json_dir = Path("./user_data")
    marker = Path("./data/.json_migration_complete")

    if marker.exists():
        return True, "JSON migration already completed"

    if not json_dir.exists():
        return True, "No legacy JSON data found"

    json_files = list(json_dir.glob("*.json"))
    if not json_files:
        return True, "No JSON files to migrate"

    # Initialize database
    init_db()

    migrated_count = 0
    session_count = 0
    errors = []

    # Backup original data
    backup_dir = Path("./user_data_backup")
    backup_dir.mkdir(parents=True, exist_ok=True)

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Generate or reuse user ID. Existing migrated users can claim the
            # account later by registering with the same username.
            username = str(data.get("name", json_file.stem)).strip().lower()
            existing = get_user_by_username(username)
            user_id = existing["user_id"] if existing else str(uuid.uuid4())

            # Create user record (no password for migrated users)
            if not existing and not insert_user(user_id, username, None, "patient"):
                errors.append(f"Failed to create user for {username}")
                continue

            # Update user profile
            profile_data = data.get("profile", {})
            profile_data["name"] = data.get("name", "")
            profile_data["age"] = data.get("age", None)
            update_user_profile(user_id, **profile_data)

            execute_update(
                """
                UPDATE user_profiles SET
                name = ?, age = ?, gender = ?, height_cm = ?,
                weight_kg = ?, affected_side = ?, condition = ?,
                diagnosis = ?, pain_area = ?, mobility_aid = ?,
                activity_level = ?, weekly_goal = ?, daily_goal = ?,
                preferred_training_time = ? WHERE user_id = ?
                """,
                (
                    profile_data.get("name"),
                    profile_data.get("age"),
                    profile_data.get("gender"),
                    profile_data.get("height_cm"),
                    profile_data.get("weight_kg"),
                    profile_data.get("affected_side"),
                    json.dumps(profile_data.get("condition", []), ensure_ascii=False),
                    profile_data.get("diagnosis"),
                    json.dumps(profile_data.get("pain_area", []), ensure_ascii=False),
                    profile_data.get("mobility_aid"),
                    profile_data.get("activity_level"),
                    profile_data.get("weekly_goal"),
                    profile_data.get("daily_goal"),
                    profile_data.get("preferred_training_time"),
                    user_id
                )
            )

            # Migrate sessions
            for session in data.get("sessions", []):
                session_id = str(uuid.uuid4())
                created_at = None
                if session.get("ts"):
                    created_at = datetime.fromtimestamp(session["ts"]).isoformat(sep=" ")
                insert_session(
                    session_id=session_id,
                    user_id=user_id,
                    exercise=session.get("exercise", ""),
                    score=session.get("score", 0),
                    rep_count=session.get("rep_count"),
                    joints_json=json.dumps(session.get("joints", {}), ensure_ascii=False),
                    neural_scores_json=json.dumps(session.get("neural_scores", {}), ensure_ascii=False),
                    pain_before=session.get("pain_before"),
                    pain_after=session.get("pain_after"),
                    safety_flag=session.get("safety_flag"),
                    created_at=created_at,
                )
                session_count += 1

            # Migrate health data (journal, vitals, medication, pain)
            for journal_entry in data.get("journal", []):
                insert_health_data(user_id, "journal", json.dumps(journal_entry, ensure_ascii=False))

            for vitals_entry in data.get("vitals", []):
                insert_health_data(user_id, "vitals", json.dumps(vitals_entry, ensure_ascii=False))

            for med_entry in data.get("medications", []):
                insert_health_data(user_id, "medications", json.dumps(med_entry, ensure_ascii=False))

            for pain_entry in data.get("pain_map", []) + data.get("pain_records", []):
                insert_health_data(user_id, "pain_map", json.dumps(pain_entry, ensure_ascii=False))

            # Migrate badges/achievements
            for badge in data.get("badges", []):
                execute_update(
                    """
                    INSERT OR IGNORE INTO achievements (user_id, badge_key)
                    VALUES (?, ?)
                    """,
                    (user_id, badge)
                )

            # Backup JSON file
            shutil.copy(json_file, backup_dir / json_file.name)

            migrated_count += 1

        except Exception as e:
            errors.append(f"Migration error for {json_file.name}: {str(e)}")

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.now().isoformat(), encoding="utf-8")

    message = f"Migrated {migrated_count} users with {session_count} sessions"
    if errors:
        message += f"\nErrors: {'; '.join(errors)}"

    return True, message


def rollback_migration() -> bool:
    """Rollback migration by restoring from backup."""
    backup_dir = Path("./user_data_backup")
    json_dir = Path("./user_data")

    if backup_dir.exists() and backup_dir.iterdir():
        if json_dir.exists():
            shutil.rmtree(json_dir)
        shutil.copytree(backup_dir, json_dir)
        return True

    return False
