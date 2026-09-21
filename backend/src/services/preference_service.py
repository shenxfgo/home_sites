"""界面偏好读写：每个人一份，登录即生效。

只认白名单里的键，其余一律不落库——这张表的 ``prefs`` 是 JSON，如果不设边界，
它会变成谁都能往里塞字段的抽屉，而前端无从判断哪些键还有人在读。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.preference import UserPreference

# 未登录或从没设置过时的取值，与前端 useTheme 的默认保持一致。
PREF_DEFAULTS: dict[str, Any] = {"theme": "light"}

THEME_VALUES: tuple[str, ...] = ("light", "dark", "auto")


class PreferenceService:
    """Owns the ``user_preferences`` rows; every method takes a ``user_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_prefs(self, user_id: int) -> dict[str, Any]:
        """The caller's choices, with anything they never set filled in."""
        row = await self.session.get(UserPreference, user_id)
        stored = row.prefs if row and isinstance(row.prefs, dict) else {}
        return {**PREF_DEFAULTS, **stored}

    async def save_prefs(self, user_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge the given keys and return the whole resulting preference set."""
        row = await self.session.get(UserPreference, user_id)
        current = dict(row.prefs) if row and isinstance(row.prefs, dict) else {}
        current.update({key: value for key, value in patch.items() if value is not None})

        if row is None:
            self.session.add(UserPreference(user_id=user_id, prefs=current))
        else:
            # 换一个新 dict 而不是原地改：SQLAlchemy 看不见 JSON 列内部的变动。
            row.prefs = current
        await self.session.commit()
        return {**PREF_DEFAULTS, **current}
