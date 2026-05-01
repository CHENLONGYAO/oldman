"""
SQLite database setup, schema, and utilities.

This module handles:
- Database initialization and connection management
- Schema creation and migrations
- Connection pooling
"""
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Database path
DB_DIR = Path("./data")
DB_PATH = DB_DIR / "smart_rehab.db"


def get_db_path() -> Path:
    """Return the configured SQLite database path."""
    return DB_PATH


def init_db() -> sqlite3.Connection:
    """Initialize database with schema if it doesn't exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    _create_schema(conn)
    _ensure_schema(conn)

    return conn

def get_db() -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _tables_exist(conn: sqlite3.Connection) -> bool:
    """Check if main tables exist."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    )
    return cursor.fetchone() is not None

def _create_schema(conn: sqlite3.Connection) -> None:
    """Create all database tables."""
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            email TEXT,
            role TEXT DEFAULT 'patient',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # OAuth accounts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oauth_accounts (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(provider, provider_user_id)
        )
    """)

    # User profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            height_cm REAL,
            weight_kg REAL,
            dominant_hand TEXT,
            affected_side TEXT,
            condition TEXT,
            diagnosis TEXT,
            pain_area TEXT,
            surgery_history TEXT,
            contraindications TEXT,
            mobility_aid TEXT,
            activity_level TEXT,
            weekly_goal INTEGER,
            daily_goal INTEGER,
            preferred_training_time TEXT,
            reminder_enabled INTEGER DEFAULT 1,
            contact_name TEXT,
            contact_phone TEXT,
            caregiver_note TEXT,
            profile_complete REAL DEFAULT 0.0,
            profile_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            exercise TEXT NOT NULL,
            score REAL NOT NULL,
            rep_count INTEGER,
            joints_json TEXT,
            neural_scores_json TEXT,
            pain_before INTEGER,
            pain_after INTEGER,
            safety_flag TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Health data table (generic for journal, vitals, medication, pain)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS health_data (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            data_type TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Achievements/Badges table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            badge_key TEXT NOT NULL,
            first_achieved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(user_id, badge_key)
        )
    """)

    # Games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            game_type TEXT NOT NULL,
            score REAL NOT NULL,
            game_data_json TEXT,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Team assignments (therapist → patients)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_assignments (
            id INTEGER PRIMARY KEY,
            therapist_id TEXT NOT NULL,
            patient_id TEXT NOT NULL,
            program_id TEXT,
            assigned_date DATE DEFAULT CURRENT_DATE,
            start_date DATE,
            end_date DATE,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (therapist_id) REFERENCES users(user_id),
            FOREIGN KEY (patient_id) REFERENCES users(user_id)
        )
    """)

    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            from_user_id TEXT NOT NULL,
            to_user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            read_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_user_id) REFERENCES users(user_id),
            FOREIGN KEY (to_user_id) REFERENCES users(user_id)
        )
    """)

    # Team memberships
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_memberships (
            id INTEGER PRIMARY KEY,
            therapist_id TEXT NOT NULL,
            patient_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (therapist_id) REFERENCES users(user_id),
            FOREIGN KEY (patient_id) REFERENCES users(user_id),
            UNIQUE(therapist_id, patient_id)
        )
    """)

    # Cloud sync metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cloud_sync_meta (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            last_sync_timestamp TIMESTAMP,
            version_hash TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(user_id)
        )
    """)

    # Offline cache
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offline_cache (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            cache_type TEXT NOT NULL,
            data_json TEXT NOT NULL,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_data_user ON health_data(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_data_type ON health_data(data_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_to_user ON messages(to_user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_user_id ON games(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_therapist ON team_assignments(therapist_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_patient ON team_assignments(patient_id)")

    conn.commit()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply small additive schema upgrades for existing local databases."""
    profile_columns = {
        "dominant_hand": "TEXT",
        "surgery_history": "TEXT",
        "contraindications": "TEXT",
        "reminder_enabled": "INTEGER DEFAULT 1",
        "contact_name": "TEXT",
        "contact_phone": "TEXT",
        "caregiver_note": "TEXT",
        "profile_json": "TEXT",
    }
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(user_profiles)").fetchall()
    }
    for column, ddl in profile_columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE user_profiles ADD COLUMN {column} {ddl}")
    conn.commit()

def execute_query(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    """Execute SELECT query and return results."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results

def execute_update(query: str, params: tuple = ()) -> int:
    """Execute INSERT/UPDATE/DELETE and return rows affected."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected


PROFILE_COLUMNS = {
    "name",
    "age",
    "gender",
    "height_cm",
    "weight_kg",
    "dominant_hand",
    "affected_side",
    "condition",
    "diagnosis",
    "pain_area",
    "surgery_history",
    "contraindications",
    "mobility_aid",
    "activity_level",
    "weekly_goal",
    "daily_goal",
    "preferred_training_time",
    "reminder_enabled",
    "contact_name",
    "contact_phone",
    "caregiver_note",
    "profile_complete",
    "profile_json",
}


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _decode_profile_value(key: str, value: Any) -> Any:
    if key not in {"condition", "pain_area", "profile_json"}:
        return value
    if not isinstance(value, str) or not value:
        return [] if key in {"condition", "pain_area"} else value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _profile_completion(profile: Dict[str, Any]) -> float:
    fields = [
        "name", "age", "gender", "height_cm", "weight_kg",
        "affected_side", "condition", "diagnosis", "pain_area",
        "mobility_aid", "activity_level", "weekly_goal", "daily_goal",
        "preferred_training_time",
    ]
    done = 0
    for key in fields:
        val = profile.get(key)
        if isinstance(val, list):
            done += int(bool(val))
        else:
            done += int(val not in (None, "", "—"))
    return round(done / len(fields) * 100, 1)


def normalize_profile(profile: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return a Streamlit-friendly profile dict from a DB profile row."""
    if not profile:
        return {}
    normalized = dict(profile)
    for key, value in list(normalized.items()):
        normalized[key] = _decode_profile_value(key, value)
    normalized["reminder_enabled"] = bool(normalized.get("reminder_enabled", 1))
    if isinstance(normalized.get("profile_json"), dict):
        saved = normalized.pop("profile_json")
        saved.update({k: v for k, v in normalized.items() if v not in (None, "", [])})
        normalized = saved
    return normalized


def insert_user(user_id: str, username: str, password_hash: str, role: str = "patient") -> bool:
    """Insert new user."""
    try:
        execute_update(
            """
            INSERT INTO users (user_id, username, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, username, password_hash, role)
        )
        # Create user profile record
        execute_update(
            "INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)",
            (user_id,)
        )
        return True
    except sqlite3.IntegrityError:
        return False


def set_user_password(user_id: str, password_hash: str, role: str | None = None) -> bool:
    """Set or replace a user's password hash."""
    if role:
        return execute_update(
            """
            UPDATE users
            SET password_hash = ?, role = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (password_hash, role, user_id)
        ) > 0
    return execute_update(
        """
        UPDATE users
        SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (password_hash, user_id)
    ) > 0

def insert_oauth_account(user_id: str, provider: str, provider_user_id: str, email: str) -> bool:
    """Link OAuth account to user."""
    try:
        execute_update(
            """
            INSERT INTO oauth_accounts (user_id, provider, provider_user_id, email)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, provider, provider_user_id, email)
        )
        return True
    except sqlite3.IntegrityError:
        return False

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username."""
    result = execute_query(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    )
    return dict(result[0]) if result else None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    result = execute_query(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    )
    return dict(result[0]) if result else None


def get_user_by_oauth(provider: str, provider_user_id: str) -> Optional[Dict[str, Any]]:
    """Get user linked to an OAuth provider account."""
    result = execute_query(
        """
        SELECT u.*
        FROM oauth_accounts oa
        JOIN users u ON oa.user_id = u.user_id
        WHERE oa.provider = ? AND oa.provider_user_id = ?
        """,
        (provider, provider_user_id)
    )
    return dict(result[0]) if result else None


def get_user_by_profile_name(name: str) -> Optional[Dict[str, Any]]:
    """Find a user by profile display name or username."""
    result = execute_query(
        """
        SELECT u.*
        FROM users u
        LEFT JOIN user_profiles p ON u.user_id = p.user_id
        WHERE lower(p.name) = lower(?) OR lower(u.username) = lower(?)
        ORDER BY u.created_at DESC
        LIMIT 1
        """,
        (name, name)
    )
    return dict(result[0]) if result else None

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile."""
    result = execute_query(
        "SELECT * FROM user_profiles WHERE user_id = ?",
        (user_id,)
    )
    return normalize_profile(dict(result[0])) if result else None

def update_user_profile(user_id: str, **kwargs) -> bool:
    """Update user profile with provided fields."""
    if not kwargs:
        return True
    profile_json = dict(kwargs)
    kwargs = {k: v for k, v in kwargs.items() if k in PROFILE_COLUMNS}
    if not kwargs:
        return True

    if "condition" in kwargs:
        kwargs["condition"] = _json_or_none(kwargs["condition"])
    if "pain_area" in kwargs:
        kwargs["pain_area"] = _json_or_none(kwargs["pain_area"])
    if "reminder_enabled" in kwargs:
        kwargs["reminder_enabled"] = int(bool(kwargs["reminder_enabled"]))
    kwargs["profile_complete"] = kwargs.get("profile_complete", _profile_completion(profile_json))
    kwargs["profile_json"] = json.dumps(profile_json, ensure_ascii=False)

    execute_update(
        "INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)",
        (user_id,)
    )
    fields = [f"{k} = ?" for k in kwargs.keys()]
    values = list(kwargs.values()) + [user_id]
    query = f"UPDATE user_profiles SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?"
    return execute_update(query, tuple(values)) > 0

def insert_session(session_id: str, user_id: str, exercise: str, score: float,
                  rep_count: int, joints_json: str = None, neural_scores_json: str = None,
                  pain_before: int = None, pain_after: int = None,
                  safety_flag: str = None, created_at: str = None) -> bool:
    """Insert training session."""
    try:
        if created_at:
            execute_update(
                """
                INSERT INTO sessions
                (session_id, user_id, exercise, score, rep_count, joints_json,
                 neural_scores_json, pain_before, pain_after, safety_flag, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, user_id, exercise, score, rep_count, joints_json,
                    neural_scores_json, pain_before, pain_after, safety_flag, created_at
                )
            )
        else:
            execute_update(
                """
                INSERT INTO sessions
                (session_id, user_id, exercise, score, rep_count, joints_json,
                 neural_scores_json, pain_before, pain_after, safety_flag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, user_id, exercise, score, rep_count, joints_json,
                    neural_scores_json, pain_before, pain_after, safety_flag
                )
            )
        return True
    except sqlite3.IntegrityError:
        return False


def update_session_fields(session_id: str, **kwargs) -> bool:
    """Update selected session fields."""
    allowed = {"pain_after", "safety_flag"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return True
    assignments = [f"{k} = ?" for k in fields]
    values = list(fields.values()) + [session_id]
    return execute_update(
        f"UPDATE sessions SET {', '.join(assignments)} WHERE session_id = ?",
        tuple(values)
    ) > 0

def get_user_sessions(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Get user's training sessions."""
    results = execute_query(
        """
        SELECT * FROM sessions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    )
    return [dict(row) for row in results]

def insert_health_data(user_id: str, data_type: str, data_json: str) -> bool:
    """Insert health data (journal, vitals, medication, pain)."""
    try:
        execute_update(
            """
            INSERT INTO health_data (user_id, data_type, data_json)
            VALUES (?, ?, ?)
            """,
            (user_id, data_type, data_json)
        )
        return True
    except sqlite3.IntegrityError:
        return False


HEALTH_SECTION_TYPES = {
    "journal": "journal",
    "vitals": "vitals",
    "medications": "medications",
    "medication_log": "medication_log",
    "pain_records": "pain_map",
    "pain_map": "pain_map",
    "appointments": "appointments",
    "active_program": "active_program",
}


def mirror_health_data_by_profile_name(name: str, section_key: str, data: Any) -> bool:
    """Mirror JSON-backed health sections into SQLite for dashboards."""
    data_type = HEALTH_SECTION_TYPES.get(section_key)
    if not data_type or data is None:
        return False
    user = get_user_by_profile_name(name)
    if not user:
        return False
    payload = data if isinstance(data, dict) else {"snapshot": data}
    return insert_health_data(
        user["user_id"],
        data_type,
        json.dumps(payload, ensure_ascii=False),
    )

def get_health_data(user_id: str, data_type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Get user's health data."""
    if data_type:
        results = execute_query(
            """
            SELECT * FROM health_data
            WHERE user_id = ? AND data_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, data_type, limit)
        )
    else:
        results = execute_query(
            """
            SELECT * FROM health_data
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
    return [dict(row) for row in results]

def get_therapist_patients(therapist_id: str) -> List[Dict[str, Any]]:
    """Get all patients assigned to therapist."""
    results = execute_query(
        """
        SELECT DISTINCT u.user_id, u.username, p.name, p.age, p.condition
        FROM team_assignments ta
        JOIN users u ON ta.patient_id = u.user_id
        LEFT JOIN user_profiles p ON u.user_id = p.user_id
        WHERE ta.therapist_id = ? AND ta.status = 'active'
        ORDER BY p.name
        """,
        (therapist_id,)
    )
    return [dict(row) for row in results]

def insert_message(from_user_id: str, to_user_id: str, content: str) -> bool:
    """Insert message between users."""
    try:
        execute_update(
            """
            INSERT INTO messages (from_user_id, to_user_id, content)
            VALUES (?, ?, ?)
            """,
            (from_user_id, to_user_id, content)
        )
        return True
    except sqlite3.IntegrityError:
        return False

def get_user_messages(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get messages for user (both sent and received)."""
    results = execute_query(
        """
        SELECT m.*,
               u1.username as from_username,
               u2.username as to_username
        FROM messages m
        JOIN users u1 ON m.from_user_id = u1.user_id
        JOIN users u2 ON m.to_user_id = u2.user_id
        WHERE m.to_user_id = ? OR m.from_user_id = ?
        ORDER BY m.created_at DESC
        LIMIT ?
        """,
        (user_id, user_id, limit)
    )
    return [dict(row) for row in results]
