"""用户管理 API：只有 owner 能动。

账号从命令行建起（``python -m src.cli``），这一组接口把同样的能力搬到界面上：
建号、改角色、停用启用、重置密码、踢下线。**没有删除账号**——停用保留了那个人
的历史与收藏，真删数据是另一回事，家用场景不需要。

两条护栏：不能停用自己（一停就再也进不来，只能回命令行救），不能降级或停用最后
一个可用管理员（整个家的管理面会随之消失）。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.middleware.auth import require_owner
from src.models.user import ROLES, ROLE_MEMBER, ROLE_OWNER, User, UserSession
from src.services.auth_service import AuthService, user_payload

router = APIRouter(prefix="/api/users", tags=["users"])


class AdminUserResponse(BaseModel):
    """The shape the 用户管理 table shows; ``/api/auth/me`` stays narrower."""

    id: int
    username: str
    role: str
    display_name: str | None = None
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    signed_in_devices: int = 0


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    role: str = ROLE_MEMBER
    display_name: str | None = Field(default=None, max_length=64)


class RoleRequest(BaseModel):
    role: str


class StatusRequest(BaseModel):
    is_active: bool


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=200)


class RevokedSessionsResponse(BaseModel):
    revoked: int


async def _payload(session: AsyncSession, user: User) -> AdminUserResponse:
    """One row of the table, including how many browsers still hold it open."""
    result = await session.execute(
        select(func.count(UserSession.token_hash)).where(UserSession.user_id == user.id)
    )
    return AdminUserResponse(
        **user_payload(user),
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        signed_in_devices=result.scalar() or 0,
    )


async def _get_or_404(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    return user


@router.get("", response_model=list[AdminUserResponse])
async def list_users(
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_owner),
) -> list[AdminUserResponse]:
    """Every account, with its role and how many browsers hold it signed in."""
    users = await AuthService(session).list_users()
    return [await _payload(session, user) for user in users]


@router.post("", response_model=AdminUserResponse, status_code=201)
async def create_user(
    payload: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_owner),
) -> AdminUserResponse:
    """Create an account, the same way ``python -m src.cli create-user`` does."""
    try:
        user = await AuthService(session).create_user(
            payload.username,
            payload.password,
            role=payload.role,
            display_name=payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _payload(session, user)


@router.put("/{user_id}/role", response_model=AdminUserResponse)
async def update_role(
    user_id: int,
    payload: RoleRequest,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_owner),
) -> AdminUserResponse:
    """Promote or demote one account."""
    service = AuthService(session)
    user = await _get_or_404(session, user_id)
    try:
        await service.set_role(user, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user.role != ROLE_OWNER and user.id != actor.id:
        # 降级之后旧会话不该还带着管理权限到处跑；只留调用者自己这一枚，
        # 让他看得见"我刚把自己降级了"，而不是被突然踢下线。
        await service.revoke_sessions(user.id)
    return await _payload(session, user)


@router.put("/{user_id}/status", response_model=AdminUserResponse)
async def update_status(
    user_id: int,
    payload: StatusRequest,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_owner),
) -> AdminUserResponse:
    """Enable or disable an account; disabling also signs it out everywhere."""
    service = AuthService(session)
    user = await _get_or_404(session, user_id)
    if user.id == actor.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="不能停用自己的账号")
    try:
        await service.set_active(user, payload.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _payload(session, user)


@router.post("/{user_id}/password", status_code=204)
async def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_owner),
) -> None:
    """Hand a forgotten password back. That account is signed out everywhere."""
    service = AuthService(session)
    user = await _get_or_404(session, user_id)
    try:
        await service.reset_password(user, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{user_id}/sessions", response_model=RevokedSessionsResponse)
async def revoke_sessions(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_owner),
) -> RevokedSessionsResponse:
    """Sign one account out of every browser it is open in."""
    await _get_or_404(session, user_id)
    revoked = await AuthService(session).revoke_sessions(user_id)
    return RevokedSessionsResponse(revoked=revoked)
