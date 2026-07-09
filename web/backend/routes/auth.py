from fastapi import APIRouter, Response
from pydantic import BaseModel

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    ok: bool


@router.post("/api/login")
async def login(body: LoginRequest):
    # Auth is handled by the frontend. Backend is only reachable through
    # the frontend proxy (Docker internal network), so it trusts all requests.
    return LoginResponse(ok=True)


@router.post("/api/logout")
async def logout():
    return LoginResponse(ok=True)
