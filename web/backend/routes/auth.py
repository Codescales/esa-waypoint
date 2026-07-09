from fastapi import APIRouter, Response, HTTPException, Request
from pydantic import BaseModel

from .. import config
from ..auth import verify_password, create_session, cookie_name
from ..limiter import limiter

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    ok: bool


@router.post("/api/login")
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, response: Response):
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    session = create_session()
    response.set_cookie(
        key=cookie_name(),
        value=session,
        max_age=config.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=config.SECURE_COOKIES,
    )
    return LoginResponse(ok=True)


@router.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(key=cookie_name())
    return LoginResponse(ok=True)
