"""
Authentication module: password hashing, JWT tokens, OAuth integration.

Supports:
- Username/password registration and login
- Bcrypt password hashing
- JWT session tokens
- OAuth 2.0 (Google, Apple)
"""
import os
import uuid
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import streamlit as st

try:
    import jwt
except ImportError:  # pragma: no cover - exercised in lightweight installs
    jwt = None

try:
    from werkzeug.security import generate_password_hash, check_password_hash
except ImportError:  # pragma: no cover - exercised in lightweight installs
    generate_password_hash = None
    check_password_hash = None

from db import (
    insert_user, get_user_by_username, get_user_by_id,
    insert_oauth_account, get_user_by_oauth, get_user_profile,
    set_user_password, update_user_profile
)

# Secret key for JWT - should be in environment or Streamlit secrets
SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-key-change-in-production"
TOKEN_EXPIRY_DAYS = 7
PBKDF2_ITERATIONS = 260_000


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _fallback_hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{_b64url(salt)}${_b64url(digest)}"
    )


def _verify_fallback_hash(password: str, password_hash: str) -> bool:
    try:
        if password_hash.startswith("pbkdf2_sha256$"):
            _, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
            salt = _b64url_decode(salt_b64)
            expected = _b64url_decode(digest_b64)
        elif password_hash.startswith("pbkdf2:sha256:"):
            method, salt, digest_hex = password_hash.split("$", 2)
            iterations = method.rsplit(":", 1)[-1]
            salt = salt.encode("utf-8")
            expected = bytes.fromhex(digest_hex)
        else:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _fallback_encode_jwt(payload: Dict[str, Any]) -> str:
    normalized = dict(payload)
    for key in ("iat", "exp"):
        value = normalized.get(key)
        if isinstance(value, datetime):
            normalized[key] = int(value.timestamp())
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join([
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url(json.dumps(normalized, separators=(",", ":")).encode("utf-8")),
    ])
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _fallback_decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            SECRET_KEY.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_sig, _b64url_decode(signature_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = payload.get("exp")
        if exp is not None and datetime.utcnow().timestamp() > float(exp):
            return None
        return payload
    except Exception:
        return None

def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    if generate_password_hash:
        return generate_password_hash(password, method="pbkdf2:sha256")
    return _fallback_hash_password(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    if not password_hash:
        return False
    if _verify_fallback_hash(password, password_hash):
        return True
    if check_password_hash:
        return check_password_hash(password_hash, password)
    return False

def create_jwt_token(user_id: str, username: str, role: str = "patient") -> str:
    """Create JWT token for session."""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS)
    }
    if jwt:
        return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return _fallback_encode_jwt(payload)

def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token and return payload."""
    if not jwt:
        return _fallback_decode_jwt(token)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def register_user(username: str, password: str, role: str = "patient") -> Tuple[bool, str]:
    """
    Register new user.

    Returns: (success, message)
    """
    username = (username or "").strip()
    if not username:
        return False, "請輸入用戶名"
    if not password or len(password) < 6:
        return False, "密碼至少需 6 個字符"

    role = role if role in {"patient", "therapist", "clinician", "admin"} else "patient"

    # Check if username exists. Migrated JSON users have no password yet;
    # registration claims that local profile instead of blocking the flow.
    existing = get_user_by_username(username)
    if existing:
        if existing.get("password_hash"):
            return False, "用戶名已存在"
        password_hash = hash_password(password)
        if set_user_password(existing["user_id"], password_hash, role):
            return True, f"舊資料帳戶 {username} 已啟用"
        return False, "啟用舊資料帳戶時出錯"

    # Validate new usernames after legacy-profile claim has had a chance.
    if len(username) < 3:
        return False, "用戶名至少需 3 個字符"

    # Create user
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)

    if insert_user(user_id, username, password_hash, role):
        return True, f"用戶 {username} 創建成功"
    else:
        return False, "創建用戶時出錯"

def login_user(username: str, password: str) -> Tuple[bool, str, Optional[str]]:
    """
    Login user with username and password.

    Returns: (success, message, token)
    """
    user = get_user_by_username(username)
    if not user:
        return False, "用戶名或密碼錯誤", None

    if not verify_password(password, user["password_hash"]):
        return False, "用戶名或密碼錯誤", None

    token = create_jwt_token(user["user_id"], user["username"], user["role"])
    return True, "登入成功", token

def login_oauth(provider: str, provider_user_id: str, email: str, name: str) -> Tuple[bool, str, Optional[str]]:
    """
    OAuth login/registration.

    Returns: (success, message, token)
    """
    # Check if OAuth account exists
    user = get_user_by_oauth(provider, provider_user_id)

    if not user:
        # Create new user from OAuth
        user_id = str(uuid.uuid4())
        username = f"{provider}_{provider_user_id[:8]}"

        # Register with no password (OAuth only)
        if not insert_user(user_id, username, None, "patient"):
            return False, f"{provider} 登入失敗", None

        # Link OAuth account
        if not insert_oauth_account(user_id, provider, provider_user_id, email):
            return False, f"{provider} 帳戶連結失敗", None

        # Update profile with name
        update_user_profile(user_id, name=name)

        token = create_jwt_token(user_id, username, "patient")
        return True, f"使用 {provider} 創建帳戶成功", token

    # Update last login
    token = create_jwt_token(user["user_id"], user["username"], user["role"])
    return True, f"{provider} 登入成功", token

def get_session_user() -> Optional[Dict[str, Any]]:
    """Get current session user from streamlit state."""
    if "auth_token" not in st.session_state:
        return None

    token = st.session_state.auth_token
    if not token:
        return None
    payload = verify_jwt_token(token)

    if not payload:
        st.session_state.auth_token = None
        return None

    # Also get full user profile
    user = get_user_by_id(payload["user_id"])
    if not user:
        st.session_state.auth_token = None
        return None

    profile = get_user_profile(payload["user_id"]) or {}
    merged = {**user, **profile}
    merged["user_id"] = user["user_id"]
    merged["username"] = user["username"]
    merged["role"] = user.get("role", "patient")
    merged["name"] = merged.get("name") or user["username"]
    merged["history_key"] = user["user_id"]
    merged.setdefault("age", 65)
    merged.setdefault("gender", "—")
    merged.setdefault("condition", [])
    return merged

def is_authenticated() -> bool:
    """Check if user is authenticated."""
    return get_session_user() is not None

def is_therapist() -> bool:
    """Check if current user is therapist."""
    user = get_session_user()
    return user and user.get("role") == "therapist"

def is_clinician() -> bool:
    """Check if current user is clinician."""
    user = get_session_user()
    return user and user.get("role") in ["clinician", "admin"]

def logout():
    """Logout current user."""
    st.session_state.auth_token = None
    st.session_state.user = None
    st.session_state.step = "welcome"
