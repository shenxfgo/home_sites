"""Settings API endpoints.

这里只剩**系统配置**：扫描开关与间隔、默认转码格式、缩略图尺寸。界面偏好（主题）
在 M3 搬去了 ``/api/preferences``，因为那是每个人自己的选择，写在一张全局 KV 表里
会变成"一个人切深色，全家跟着变"。

键名走白名单而不是随便往里塞：``PUT /api/settings/{key}`` 原先能写任意键，前端读
的却是固定字段，多余的键没人清理，最后没人知道哪些还有用。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.setting import Setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

SYSTEM_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "auto_scan_enabled",
        "auto_scan_interval",
        "default_transcode_format",
        "thumbnail_width",
        "thumbnail_height",
    }
)


class SettingResponse(BaseModel):
    """Response model for a setting."""
    key: str
    value: str


class SettingUpdate(BaseModel):
    """Request model for updating a setting."""
    value: str


class AllSettingsResponse(BaseModel):
    """Response model for all settings."""
    auto_scan_enabled: bool = True
    auto_scan_interval: int = 3600
    default_transcode_format: str = "mp4"
    thumbnail_width: int = 320
    thumbnail_height: int = 180


@router.get("", response_model=AllSettingsResponse)
async def get_settings(
    session: AsyncSession = Depends(get_session),
) -> AllSettingsResponse:
    """Get all application settings."""
    result = await session.execute(select(Setting))
    settings = {s.key: s.value for s in result.scalars().all()}

    return AllSettingsResponse(
        auto_scan_enabled=settings.get("auto_scan_enabled", "true").lower() == "true",
        auto_scan_interval=int(settings.get("auto_scan_interval", "3600")),
        default_transcode_format=settings.get("default_transcode_format", "mp4"),
        thumbnail_width=int(settings.get("thumbnail_width", "320")),
        thumbnail_height=int(settings.get("thumbnail_height", "180")),
    )


@router.put("", response_model=AllSettingsResponse)
async def update_settings(
    data: AllSettingsResponse,
    session: AsyncSession = Depends(get_session),
) -> AllSettingsResponse:
    """Update application settings."""
    settings_dict = {
        "auto_scan_enabled": str(data.auto_scan_enabled).lower(),
        "auto_scan_interval": str(data.auto_scan_interval),
        "default_transcode_format": data.default_transcode_format,
        "thumbnail_width": str(data.thumbnail_width),
        "thumbnail_height": str(data.thumbnail_height),
    }

    for key, value in settings_dict.items():
        result = await session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            session.add(setting)

    await session.commit()
    return data


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> SettingResponse:
    """Get a single setting by key."""
    result = await session.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        return SettingResponse(key=key, value="")

    return SettingResponse(key=setting.key, value=setting.value)


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    data: SettingUpdate,
    session: AsyncSession = Depends(get_session),
) -> SettingResponse:
    """Update a single setting."""
    if key not in SYSTEM_SETTING_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"未知的配置项：{key}。可写的只有 {', '.join(sorted(SYSTEM_SETTING_KEYS))}",
        )

    result = await session.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=key, value=data.value)
        session.add(setting)

    await session.commit()
    return SettingResponse(key=key, value=data.value)
