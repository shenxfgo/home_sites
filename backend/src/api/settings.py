"""Settings API endpoints.

这里只剩**系统配置**：扫描开关与间隔、默认转码格式、缩略图尺寸。界面偏好（主题）
在 M3 搬去了 ``/api/preferences``，因为那是每个人自己的选择，写在一张全局 KV 表里
会变成"一个人切深色，全家跟着变"。

键名走白名单而不是随便往里塞：``PUT /api/settings/{key}`` 原先能写任意键，前端读
的却是固定字段，多余的键没人清理，最后没人知道哪些还有用。白名单只管键名，
值还要单独过一道 ``_check_setting_value``——那三个数字键的判据和**读者**是同一份
（``setting_service.INT_SETTING_RULES``），两条写路径（整份 PUT 与单键 PUT）走的
也是同一道闸门。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.setting import Setting
from src.services.setting_service import (
    AUTO_SCAN_ENABLED_KEY,
    AUTO_SCAN_INTERVAL_KEY,
    DEFAULT_AUTO_SCAN_ENABLED,
    DEFAULT_AUTO_SCAN_INTERVAL,
    DEFAULT_THUMBNAIL_HEIGHT,
    DEFAULT_THUMBNAIL_WIDTH,
    DEFAULT_TRANSCODE_FORMAT,
    DEFAULT_TRANSCODE_FORMAT_KEY,
    INT_SETTING_RULES,
    THUMBNAIL_HEIGHT_KEY,
    THUMBNAIL_WIDTH_KEY,
    SettingService,
    int_setting_acceptable,
    int_setting_span,
    parse_auto_scan_enabled,
    parse_int_setting,
    setting_number,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

SYSTEM_SETTING_KEYS: frozenset[str] = frozenset(
    {
        AUTO_SCAN_ENABLED_KEY,
        AUTO_SCAN_INTERVAL_KEY,
        DEFAULT_TRANSCODE_FORMAT_KEY,
        THUMBNAIL_WIDTH_KEY,
        THUMBNAIL_HEIGHT_KEY,
    }
)

#: 值要走数字判据的那几项。名单从规则表推导，不再抄一遍键名。
INT_SETTING_KEYS: frozenset[str] = frozenset(INT_SETTING_RULES)


class SettingResponse(BaseModel):
    """Response model for a setting."""
    key: str
    value: str


class SettingUpdate(BaseModel):
    """Request model for updating a setting."""
    value: str


def _check_setting_value(key: str, value: str) -> None:
    """Reject a value the read path could not use.

    两句话是分开的：「这不是个数」和「这个数这项用不了」。后者现在是真的有人管事——
    扫描间隔要能当一个源的间隔，封面尺寸要能进 ffmpeg 的 ``scale``。
    """
    if key not in INT_SETTING_KEYS:
        return
    if setting_number(value) is None:
        raise HTTPException(
            status_code=400,
            detail=f"{key} 必须是整数，收到的值是「{value}」",
        )
    if not int_setting_acceptable(key, value):
        raise HTTPException(
            status_code=400,
            detail=f"{key} 的取值范围是 {int_setting_span(key)}，收到的值是「{value}」",
        )


class AllSettingsResponse(BaseModel):
    """Response model for all settings.

    这五个默认值和读路径的回退是同一批常量：整份 PUT 漏一个键时 Pydantic 替人填上
    的，必须和"这一行没人写过"读到的是同一个东西。
    """
    auto_scan_enabled: bool = DEFAULT_AUTO_SCAN_ENABLED
    auto_scan_interval: int = DEFAULT_AUTO_SCAN_INTERVAL
    default_transcode_format: str = DEFAULT_TRANSCODE_FORMAT
    thumbnail_width: int = DEFAULT_THUMBNAIL_WIDTH
    thumbnail_height: int = DEFAULT_THUMBNAIL_HEIGHT


@router.get("", response_model=AllSettingsResponse)
async def get_settings(
    session: AsyncSession = Depends(get_session),
) -> AllSettingsResponse:
    """Get all application settings."""
    # 这几项的解析规则和管线读的是同一份（`setting_service`）：这张表有了第二个
    # 读者以后，两边各写一套规则它就会有两种真值。
    rows = await SettingService(session).values(SYSTEM_SETTING_KEYS)

    return AllSettingsResponse(
        auto_scan_enabled=parse_auto_scan_enabled(rows.get(AUTO_SCAN_ENABLED_KEY)),
        auto_scan_interval=parse_int_setting(
            AUTO_SCAN_INTERVAL_KEY, rows.get(AUTO_SCAN_INTERVAL_KEY)
        ),
        default_transcode_format=rows.get(
            DEFAULT_TRANSCODE_FORMAT_KEY, DEFAULT_TRANSCODE_FORMAT
        ),
        thumbnail_width=parse_int_setting(
            THUMBNAIL_WIDTH_KEY, rows.get(THUMBNAIL_WIDTH_KEY)
        ),
        thumbnail_height=parse_int_setting(
            THUMBNAIL_HEIGHT_KEY, rows.get(THUMBNAIL_HEIGHT_KEY)
        ),
    )


@router.put("", response_model=AllSettingsResponse)
async def update_settings(
    data: AllSettingsResponse,
    session: AsyncSession = Depends(get_session),
) -> AllSettingsResponse:
    """Update application settings."""
    settings_dict = {
        AUTO_SCAN_ENABLED_KEY: str(data.auto_scan_enabled).lower(),
        AUTO_SCAN_INTERVAL_KEY: str(data.auto_scan_interval),
        DEFAULT_TRANSCODE_FORMAT_KEY: data.default_transcode_format,
        THUMBNAIL_WIDTH_KEY: str(data.thumbnail_width),
        THUMBNAIL_HEIGHT_KEY: str(data.thumbnail_height),
    }
    # 整份 PUT 也不能绕过值闸门：Pydantic 只保证那三项是整数，保证不了它们能用。
    # 先全部判完再写——一半落库一半被拒的那种配置，没人能读回来。
    for key, value in settings_dict.items():
        _check_setting_value(key, value)

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
    _check_setting_value(key, data.value)

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
