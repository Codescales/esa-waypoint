"""Admin auth — separate cookie-based session with short expiry.

The admin password is a separate `ADMIN_PASSWORD` env var. Admin
sessions use a server-side cookie (`esa_admin_session`) signed with
`SESSION_SECRET`, with 1-hour expiry (vs 24h for hosts).

This is a separate, higher-trust auth channel than the host auth.
Hosts use client-side sessionStorage and the backend trusts their
identity (Phase 1). Admin operations modify shared state, so the
backend verifies the admin session server-side.
"""

import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from . import config


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        config.SESSION_SECRET,
        salt="esa-admin",
        signer_kwargs={"key_derivation": "hmac"},
    )


def verify_admin_password(password: str) -> bool:
    if not config.ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(password, config.ADMIN_PASSWORD)


def create_admin_session() -> str:
    s = _serializer()
    payload = {
        "admin": True,
        "exp": (datetime.now(timezone.utc) + timedelta(seconds=config.ADMIN_SESSION_MAX_AGE)).isoformat(),
    }
    return s.dumps(payload)


def validate_admin_session(session: str | None) -> bool:
    if not session:
        return False
    s = _serializer()
    try:
        payload = s.loads(session, max_age=config.ADMIN_SESSION_MAX_AGE)
        return bool(payload.get("admin"))
    except (BadSignature, SignatureExpired):
        return False


_COOKIE_NAME = "esa_admin_session"


def admin_cookie_name() -> str:
    return _COOKIE_NAME


async def current_admin(request: Request) -> None:
    """FastAPI dependency. Raises 401 if no valid admin session."""
    session = request.cookies.get(_COOKIE_NAME)
    if not validate_admin_session(session):
        raise HTTPException(status_code=401, detail="Admin auth required")
