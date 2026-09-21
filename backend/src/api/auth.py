"""认证 API：登录、登出、当前用户、我的设备、首启状态。

账号创建走 CLI（``python -m src.cli``），这里没有任何注册接口。
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_session
from src.middleware.auth import get_current_user, get_current_user_id, get_session_token
from src.models.user import User
from src.services.auth_service import (
    COOKIE_NAME,
    INVALID_CREDENTIALS,
    TOKEN_HASH_HEX,
    AuthService,
    hash_token,
    login_rate_limiter,
    normalize_username,
    session_payload,
    user_payload,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

TOKEN_HASH_PATTERN = rf"^{TOKEN_HASH_HEX}$"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class AuthStatusResponse(BaseModel):
    authenticated: bool
    needs_setup: bool


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    display_name: str | None = None


class DeviceResponse(BaseModel):
    """一行"我的设备"。``token_hash`` 是摘要，不是 Cookie 值。"""

    token_hash: str
    current: bool
    user_agent: str | None = None
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
) -> AuthService:
    """Dependency to get AuthService instance."""
    return AuthService(session)


def _set_session_cookie(response: Response, token: str, *, remember: bool) -> None:
    lifetime = timedelta(days=settings.remember_me_days) if remember else timedelta(
        hours=settings.session_hours
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )


@router.post("/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Exchange credentials for an HttpOnly session cookie."""
    username = normalize_username(payload.username)
    limiter = login_rate_limiter()
    key = (request.client.host if request.client else "unknown", username)

    locked = limiter.locked_for(key)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"尝试过于频繁，请 {locked} 秒后再试",
            headers={"Retry-After": str(locked)},
        )

    user = await service.authenticate(username, payload.password)
    if user is None:
        limiter.record_failure(key)
        # 账号不存在与密码错误给出同一句话，避免把账号枚举出去。
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)

    limiter.record_success(key)
    token = await service.create_session(
        user,
        remember=payload.remember,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, token, remember=payload.remember)
    return UserResponse(**user_payload(user))


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> AuthStatusResponse:
    """Public probe the login page uses: is anyone signed in, and is setup due."""
    token = request.cookies.get(COOKIE_NAME)
    authenticated = bool(token) and await service.resolve_session(token) is not None
    return AuthStatusResponse(
        authenticated=authenticated, needs_setup=await service.needs_setup()
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    """The signed-in user, for the frontend to restore its state on load."""
    return UserResponse(**user_payload(user))


@router.get("/sessions", response_model=list[DeviceResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    token: str = Depends(get_session_token),
    service: AuthService = Depends(get_auth_service),
) -> list[DeviceResponse]:
    """这个账号当前登录的所有浏览器，并标出"就是这台"。"""
    mine = hash_token(token)
    sessions = await service.list_sessions(user.id)
    return [session_payload(sess, current=sess.token_hash == mine) for sess in sessions]


@router.delete("/sessions/{token_hash}", status_code=204)
async def revoke_device(
    token_hash: str = Path(pattern=TOKEN_HASH_PATTERN),
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Sign one of this account's browsers out.

    撤销的是别台设备，当前 Cookie 不动，所以在这里退出手机后本页还能继续看。
    """
    if not await service.revoke_session(user.id, token_hash):
        raise HTTPException(status_code=404, detail="设备不存在或已退出")


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    token: str = Depends(get_session_token),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Revoke this browser's session and drop the cookie."""
    await service.logout(token)
    response.delete_cookie(key=COOKIE_NAME, path="/")


@router.post("/password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    token: str = Depends(get_session_token),
    service: AuthService = Depends(get_auth_service),
) -> None:
    """Rotate the caller's password and sign every other device out."""
    try:
        await service.change_password(
            user,
            payload.old_password,
            payload.new_password,
            keep_token_hash=hash_token(token),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
