"""
OAuth helpers for Google and Apple sign-in.

Configuration can come from environment variables or Streamlit secrets:

Google:
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET

Apple:
    APPLE_CLIENT_ID            # Services ID
    APPLE_CLIENT_SECRET        # Pre-generated client secret JWT
    # or, if PyJWT + cryptography are installed:
    APPLE_TEAM_ID
    APPLE_KEY_ID
    APPLE_PRIVATE_KEY

Shared:
    OAUTH_REDIRECT_URI         # Example: http://localhost:8501
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st

try:
    import jwt
except ImportError:  # pragma: no cover - optional Apple convenience
    jwt = None


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"


class OAuthError(RuntimeError):
    """Raised when an OAuth provider returns an error or bad payload."""


@dataclass(frozen=True)
class OAuthConfig:
    provider: str
    client_id: str | None
    client_secret: str | None
    redirect_uri: str
    missing: tuple[str, ...]

    @property
    def configured(self) -> bool:
        return not self.missing


def _secret(name: str, provider: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    try:
        if name in st.secrets:
            return str(st.secrets[name])
        oauth_secrets = st.secrets.get("oauth", {})
        if provider and provider in oauth_secrets:
            key = name.lower()
            prefix = f"{provider.lower()}_"
            if key.startswith(prefix):
                key = key[len(prefix):]
            value = oauth_secrets[provider].get(key)
            if value:
                return str(value)
    except Exception:
        return None
    return None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base_redirect_uri() -> str:
    return (
        _secret("OAUTH_REDIRECT_URI")
        or _secret("SMART_REHAB_BASE_URL")
        or "http://localhost:8501"
    ).rstrip("/")


def _state_secret() -> str:
    return (
        _secret("OAUTH_STATE_SECRET")
        or _secret("SECRET_KEY")
        or "dev-oauth-state-secret-change-in-production"
    )


def _sign_state(provider: str, timestamp: int, nonce: str) -> str:
    msg = f"{provider}.{timestamp}.{nonce}".encode("utf-8")
    digest = hmac.new(
        _state_secret().encode("utf-8"),
        msg,
        hashlib.sha256,
    ).digest()
    return _b64url(digest)


def _make_state(provider: str) -> str:
    timestamp = int(time.time())
    nonce = secrets.token_urlsafe(18)
    sig = _sign_state(provider, timestamp, nonce)
    return f"{provider}.{timestamp}.{nonce}.{sig}"


def _verify_state(state: str, max_age_seconds: int = 600) -> str | None:
    try:
        provider, ts_raw, nonce, sig = state.split(".", 3)
        if provider not in {"google", "apple"}:
            return None
        timestamp = int(ts_raw)
        if abs(time.time() - timestamp) > max_age_seconds:
            return None
        expected = _sign_state(provider, timestamp, nonce)
        if not hmac.compare_digest(sig, expected):
            return None
        return provider
    except Exception:
        return None


def _apple_client_secret() -> tuple[str | None, tuple[str, ...]]:
    explicit = _secret("APPLE_CLIENT_SECRET", "apple")
    if explicit:
        return explicit, ()

    team_id = _secret("APPLE_TEAM_ID", "apple")
    key_id = _secret("APPLE_KEY_ID", "apple")
    private_key = _secret("APPLE_PRIVATE_KEY", "apple")
    missing = [
        key for key, value in {
            "APPLE_CLIENT_SECRET": explicit,
            "APPLE_TEAM_ID": team_id,
            "APPLE_KEY_ID": key_id,
            "APPLE_PRIVATE_KEY": private_key,
        }.items()
        if not value
    ]
    if team_id and key_id and private_key and jwt:
        private_key = private_key.replace("\\n", "\n")
        now = int(time.time())
        payload = {
            "iss": team_id,
            "iat": now,
            "exp": now + 60 * 60 * 24 * 180,
            "aud": "https://appleid.apple.com",
            "sub": _secret("APPLE_CLIENT_ID", "apple"),
        }
        token = jwt.encode(
            payload,
            private_key,
            algorithm="ES256",
            headers={"kid": key_id},
        )
        return token, ()
    return None, tuple(missing)


def provider_config(provider: str) -> OAuthConfig:
    provider = provider.lower()
    redirect_uri = _base_redirect_uri()
    if provider == "google":
        client_id = _secret("GOOGLE_CLIENT_ID", "google")
        client_secret = _secret("GOOGLE_CLIENT_SECRET", "google")
        missing = tuple(
            key for key, value in {
                "GOOGLE_CLIENT_ID": client_id,
                "GOOGLE_CLIENT_SECRET": client_secret,
            }.items()
            if not value
        )
        return OAuthConfig(provider, client_id, client_secret, redirect_uri, missing)

    if provider == "apple":
        client_id = _secret("APPLE_CLIENT_ID", "apple")
        client_secret, secret_missing = _apple_client_secret()
        missing = []
        if not client_id:
            missing.append("APPLE_CLIENT_ID")
        missing.extend(secret_missing)
        return OAuthConfig(
            provider,
            client_id,
            client_secret,
            redirect_uri,
            tuple(dict.fromkeys(missing)),
        )

    raise ValueError(f"Unsupported OAuth provider: {provider}")


def create_authorization_url(provider: str) -> tuple[str | None, OAuthConfig]:
    cfg = provider_config(provider)
    if not cfg.configured:
        return None, cfg

    state = _make_state(provider)
    st.session_state.setdefault("oauth_states", {})[state] = provider

    if provider == "google":
        params = {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
            "access_type": "online",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}", cfg

    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "response_mode": "query",
        "scope": "name email",
        "state": state,
    }
    return f"{APPLE_AUTH_URL}?{urlencode(params)}", cfg


def _query_param(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def has_oauth_callback() -> bool:
    return bool(_query_param("code") or _query_param("error"))


def clear_oauth_query_params() -> None:
    try:
        st.query_params.clear()
    except Exception:
        pass


def complete_oauth_callback() -> dict[str, Any] | None:
    if not has_oauth_callback():
        return None

    error = _query_param("error")
    if error:
        return {
            "success": False,
            "message": _query_param("error_description") or error,
        }

    code = _query_param("code")
    state = _query_param("state")
    if not code or not state:
        return {"success": False, "message": "OAuth callback missing code/state."}

    provider = st.session_state.get("oauth_states", {}).pop(state, None)
    if not provider:
        provider = _verify_state(state)
    if not provider:
        return {
            "success": False,
            "message": "OAuth state expired. Please try signing in again.",
        }

    try:
        if provider == "google":
            identity = _complete_google(code)
        elif provider == "apple":
            identity = _complete_apple(code)
        else:
            raise OAuthError(f"Unsupported OAuth provider: {provider}")
    except OAuthError as exc:
        return {"success": False, "message": str(exc)}

    return {"success": True, "provider": provider, **identity}


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urlencode(data).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = resp.read().decode("utf-8")
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise OAuthError(f"OAuth token exchange failed: {payload}") from exc
    except URLError as exc:
        raise OAuthError(f"OAuth provider is unreachable: {exc.reason}") from exc
    return json.loads(payload)


def _get_json(url: str, access_token: str) -> dict[str, Any]:
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise OAuthError(f"OAuth userinfo failed: {payload}") from exc
    except URLError as exc:
        raise OAuthError(f"OAuth provider is unreachable: {exc.reason}") from exc


def _complete_google(code: str) -> dict[str, str]:
    cfg = provider_config("google")
    if not cfg.configured:
        raise OAuthError(f"Google OAuth is not configured: {', '.join(cfg.missing)}")

    token = _post_form(
        GOOGLE_TOKEN_URL,
        {
            "client_id": cfg.client_id or "",
            "client_secret": cfg.client_secret or "",
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": cfg.redirect_uri,
        },
    )
    access_token = token.get("access_token")
    if not access_token:
        raise OAuthError("Google did not return an access token.")

    info = _get_json(GOOGLE_USERINFO_URL, access_token)
    provider_user_id = info.get("sub")
    if not provider_user_id:
        raise OAuthError("Google did not return a user id.")
    return {
        "provider_user_id": str(provider_user_id),
        "email": str(info.get("email") or ""),
        "name": str(info.get("name") or info.get("email") or "Google user"),
    }


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise OAuthError("Could not decode provider id token.") from exc


def _complete_apple(code: str) -> dict[str, str]:
    cfg = provider_config("apple")
    if not cfg.configured:
        raise OAuthError(f"Apple OAuth is not configured: {', '.join(cfg.missing)}")

    token = _post_form(
        APPLE_TOKEN_URL,
        {
            "client_id": cfg.client_id or "",
            "client_secret": cfg.client_secret or "",
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": cfg.redirect_uri,
        },
    )
    id_token = token.get("id_token")
    if not id_token:
        raise OAuthError("Apple did not return an id token.")

    payload = _decode_jwt_payload(id_token)
    provider_user_id = payload.get("sub")
    if not provider_user_id:
        raise OAuthError("Apple did not return a user id.")

    email = str(payload.get("email") or "")
    name = email or "Apple user"
    raw_user = _query_param("user")
    if raw_user:
        try:
            user_info = json.loads(raw_user)
            name_parts = user_info.get("name") or {}
            full_name = " ".join(
                str(name_parts.get(part) or "").strip()
                for part in ("firstName", "lastName")
            ).strip()
            name = full_name or name
            email = str(user_info.get("email") or email)
        except json.JSONDecodeError:
            pass

    return {
        "provider_user_id": str(provider_user_id),
        "email": email,
        "name": name,
    }


def oauth_status_text(provider: str, lang: str) -> str:
    cfg = provider_config(provider)
    if cfg.configured:
        return ""
    missing = ", ".join(cfg.missing)
    if lang == "zh":
        return f"尚未設定：{missing}"
    return f"Missing: {missing}"
