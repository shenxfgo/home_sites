"""偏好接口：登录用户读写自己那一份界面选择。

路径上的成员白名单已经写在鉴权中间件里（MEMBER_WRITE_PATHS），因为这一组接口
动的是自己的数据，member 与 owner 权限相同；服务端只认当前会话的 user_id，
所以没有"改别人偏好"的入口。
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.middleware.auth import get_current_user_id
from src.services.preference_service import PreferenceService

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

ThemeValue = Literal["light", "dark", "auto"]


class PreferencesResponse(BaseModel):
    """The caller's UI choices, defaults included."""

    theme: ThemeValue = "light"


class PreferencesUpdate(BaseModel):
    """A partial patch; omitted keys keep their stored value."""

    theme: ThemeValue | None = None


@router.get("", response_model=PreferencesResponse)
async def get_preferences(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> PreferencesResponse:
    """Read the signed-in account's preferences."""
    prefs = await PreferenceService(session).get_prefs(user_id)
    return PreferencesResponse(**prefs)


@router.put("", response_model=PreferencesResponse)
async def update_preferences(
    data: PreferencesUpdate,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> PreferencesResponse:
    """Merge the given keys into the signed-in account's preferences."""
    prefs = await PreferenceService(session).save_prefs(user_id, data.model_dump())
    return PreferencesResponse(**prefs)
