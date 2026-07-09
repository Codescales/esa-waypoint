import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from . import config


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        config.SESSION_SECRET,
        salt="esa-session",
        signer_kwargs={"key_derivation": "hmac"},
    )


def verify_password(password: str) -> bool:
    if not config.SHARED_PASSWORD:
        return False
    return hmac.compare_digest(password, config.SHARED_PASSWORD)


def create_session() -> str:
    s = _serializer()
    payload = {
        "authenticated": True,
        "exp": (datetime.now(timezone.utc) + timedelta(seconds=config.SESSION_MAX_AGE)).isoformat(),
    }
    return s.dumps(payload)


def validate_session(session: str | None) -> bool:
    if not session:
        return False
    s = _serializer()
    try:
        payload = s.loads(session, max_age=config.SESSION_MAX_AGE)
        return bool(payload.get("authenticated"))
    except (BadSignature, SignatureExpired):
        return False


_COOKIE_NAME = "esa_session"


def cookie_name() -> str:
    return _COOKIE_NAME


async def current_session(request: Request) -> None:
    session = request.cookies.get(_COOKIE_NAME)
    if not validate_session(session):
        raise HTTPException(status_code=401, detail="Unauthorized")
