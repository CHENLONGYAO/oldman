"""
Role-Based Access Control (RBAC) and permission checking.

Roles: patient, therapist, clinician, admin
"""
from typing import List, Optional
from auth import get_session_user


# Role definitions
PATIENT = "patient"
THERAPIST = "therapist"
CLINICIAN = "clinician"
ADMIN = "admin"

# Role hierarchy (higher = more permissions)
ROLE_HIERARCHY = {
    PATIENT: 1,
    THERAPIST: 2,
    CLINICIAN: 3,
    ADMIN: 4
}

# Permission matrix: role -> list of allowed actions
PATIENT_PERMISSIONS = [
    "view_own_profile",
    "record_exercise",
    "view_own_sessions",
    "view_own_health_data",
    "view_games",
    "play_games",
    "view_leaderboard",
]

THERAPIST_PERMISSIONS = [
    *PATIENT_PERMISSIONS,
    "view_patients",
    "view_patient_sessions",
    "view_patient_health_data",
    "create_programs",
    "assign_programs",
    "send_messages",
    "view_cohort_analytics",
]

CLINICIAN_PERMISSIONS = [
    *THERAPIST_PERMISSIONS,
    "view_all_patients",
    "view_all_sessions",
    "export_reports",
    "view_advanced_analytics",
    "manage_therapists",
]

ADMIN_PERMISSIONS = [
    *CLINICIAN_PERMISSIONS,
    "manage_users",
    "manage_settings",
    "view_audit_logs",
]

PERMISSIONS = {
    PATIENT: PATIENT_PERMISSIONS,
    THERAPIST: THERAPIST_PERMISSIONS,
    CLINICIAN: CLINICIAN_PERMISSIONS,
    ADMIN: ADMIN_PERMISSIONS,
}


def get_current_role() -> Optional[str]:
    """Get current user's role."""
    user = get_session_user()
    return user["role"] if user else None


def has_permission(permission: str, user_role: Optional[str] = None) -> bool:
    """Check if user has specific permission."""
    if user_role is None:
        user_role = get_current_role()

    if not user_role:
        return False

    # Admin has all permissions
    if user_role == ADMIN:
        return True

    return permission in PERMISSIONS.get(user_role, [])


def has_role(required_role: str, user_role: Optional[str] = None) -> bool:
    """Check if user has required role or higher."""
    if user_role is None:
        user_role = get_current_role()

    if not user_role:
        return False

    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)


def is_patient(user_role: Optional[str] = None) -> bool:
    """Check if current user has patient-level access."""
    return has_role(PATIENT, user_role)


def is_therapist(user_role: Optional[str] = None) -> bool:
    """Check if current user has therapist-level access."""
    return has_role(THERAPIST, user_role)


def is_clinician(user_role: Optional[str] = None) -> bool:
    """Check if current user has clinician-level access."""
    return has_role(CLINICIAN, user_role)


def is_admin(user_role: Optional[str] = None) -> bool:
    """Check if current user has admin access."""
    return has_role(ADMIN, user_role)


def can_view_patient(current_user_id: str, target_user_id: str,
                     user_role: Optional[str] = None) -> bool:
    """Check if user can view target patient's data."""
    if user_role is None:
        user = get_session_user()
        user_role = user["role"] if user else None

    if not user_role:
        return False

    # User can always view their own data
    if current_user_id == target_user_id:
        return True

    # Admin/clinician can view all
    if user_role in [ADMIN, CLINICIAN]:
        return True

    # Therapist can view assigned patients (checked elsewhere)
    # For now, allow therapist to view (detailed check in views)
    if user_role == THERAPIST:
        return True

    return False


def can_assign_programs(user_role: Optional[str] = None) -> bool:
    """Check if user can assign programs."""
    return has_permission("assign_programs", user_role)


def can_create_programs(user_role: Optional[str] = None) -> bool:
    """Check if user can create programs."""
    return has_permission("create_programs", user_role)


def can_view_analytics(user_role: Optional[str] = None) -> bool:
    """Check if user can view advanced analytics."""
    return has_permission("view_advanced_analytics", user_role)


def can_send_messages(user_role: Optional[str] = None) -> bool:
    """Check if user can send messages."""
    return has_permission("send_messages", user_role)


def get_accessible_features(user_role: Optional[str] = None) -> List[str]:
    """Get list of features accessible to user."""
    if user_role is None:
        user = get_session_user()
        user_role = user["role"] if user else None

    if not user_role:
        return []

    features = []

    if user_role == PATIENT:
        features = [
            "home", "record", "analyze", "result", "progress",
            "games", "leaderboard", "health_tracking",
            "profile", "settings"
        ]
    elif user_role == THERAPIST:
        features = [
            "home", "record", "analyze", "result", "progress",
            "games", "leaderboard", "health_tracking",
            "therapist_dashboard", "patient_roster",
            "program_assignment", "messaging",
            "cohort_analytics", "profile", "settings"
        ]
    elif user_role == CLINICIAN:
        features = [
            "home", "record", "analyze", "result", "progress",
            "games", "leaderboard", "health_tracking",
            "therapist_dashboard", "patient_roster",
            "program_assignment", "messaging",
            "cohort_analytics", "advanced_analytics",
            "clinician_dashboard", "reports",
            "profile", "settings", "audit_logs"
        ]
    elif user_role == ADMIN:
        features = [
            "admin_dashboard", "user_management",
            "system_settings", "audit_logs",
            "all_reports", "all_analytics"
        ]

    return features
