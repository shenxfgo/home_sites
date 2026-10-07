"""系统配置里那项「自动扫描」总开关——这张表第一次有了写入方之外的读者。

`settings` 表是全局 KV，`/api/settings` 一路写得进、读得出，却没有任何代码看过它
一眼：把开关拨到关，定时扫描照旧一轮不落。这里只放**有读者的那一项**的读法，
解析规则留一份——设置页的读路径和扫描任务的闸门都走它，否则同一个字符串会有两种
真值。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.setting import Setting

#: 设置页上「自动扫描」那个开关的键名。
AUTO_SCAN_ENABLED_KEY = "auto_scan_enabled"


def parse_auto_scan_enabled(raw: str | None) -> bool:
    """只有 ``"true"``（不分大小写）算开。

    没写过这一行算**开**：新库的这张表是空的，一个字都没写过的人不该被静默停扫。
    写过但是空串算关——那是显式留下的一行，按字面读。
    """
    if raw is None:
        return True
    return raw.lower() == "true"


class SettingService:
    """Reads the global ``settings`` key-value table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_auto_scan_enabled(self) -> bool:
        """自动扫描的总开关，每轮现读——重启不该是打开它的条件。"""
        result = await self.session.execute(
            select(Setting.value).where(Setting.key == AUTO_SCAN_ENABLED_KEY)
        )
        return parse_auto_scan_enabled(result.scalar_one_or_none())
