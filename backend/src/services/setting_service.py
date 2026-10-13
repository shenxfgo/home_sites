"""系统配置里那些**有读者**的项——这张表不再是只有写没有读的装饰。

`settings` 表是全局 KV。它原先只有 `/api/settings` 自己读写，界面上拨出去的每一项
都得有人真的按它办事，否则「改了设置」和「什么都没变」在屏幕上是一个样子。现在
这张表的读者是：定时扫描（总开关）、新建视频源（扫描间隔的默认值）、扫描轮里的
封面生成（宽、高）。

解析规则一份就够：设置页的读路径和这些管线都走这里，否则同一个字符串会有两种
真值。写闸门（`api/settings.py`）用的也是同一张规则表——门口放行、管线里回退的话，
"能写进去"和"能读回来"就对不上了。
"""

from typing import Iterable, NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.setting import Setting

#: 设置页上「自动扫描」那个开关的键名。
AUTO_SCAN_ENABLED_KEY = "auto_scan_enabled"
#: 「扫描间隔」：新片源没填自己的间隔时用它。
AUTO_SCAN_INTERVAL_KEY = "auto_scan_interval"
#: 「默认转码格式」：读者是转码页的下拉初值，接口本身不替人填。
DEFAULT_TRANSCODE_FORMAT_KEY = "default_transcode_format"
#: 「缩略图宽度」与「缩略图高度」：扫描时 ffmpeg 的 `scale=W:H`。
THUMBNAIL_WIDTH_KEY = "thumbnail_width"
THUMBNAIL_HEIGHT_KEY = "thumbnail_height"

DEFAULT_AUTO_SCAN_ENABLED = True
DEFAULT_AUTO_SCAN_INTERVAL = 3600
DEFAULT_THUMBNAIL_WIDTH = 320
DEFAULT_THUMBNAIL_HEIGHT = 180
DEFAULT_TRANSCODE_FORMAT = "mp4"

#: 扫描间隔的合法区间就是「一个源能有的间隔」（`SourceCreate.scan_interval` 也是
#: 这两个数）：这一项现在的用途是给新片源当默认值，一个当不了源间隔的数字写在
#: 这里没有意义。
SCAN_INTERVAL_MIN = 60
SCAN_INTERVAL_MAX = 86400


class _IntRule(NamedTuple):
    """一个数字键的三份意思：没写时用什么、最小的可用值、最大的可用值。"""

    default: int
    lo: int
    hi: int | None


#: 三个数字键的规则。数值只写在这里一次，读路径和写闸门都从这张表取。
INT_SETTING_RULES: dict[str, _IntRule] = {
    AUTO_SCAN_INTERVAL_KEY: _IntRule(
        DEFAULT_AUTO_SCAN_INTERVAL, SCAN_INTERVAL_MIN, SCAN_INTERVAL_MAX
    ),
    # 封面尺寸只要求是正整数：ffmpeg 的 `scale=W:H` 除此之外不设上限，
    # 而界面上的那个 max 是输入框的便利，不是这条管线的规则。
    THUMBNAIL_WIDTH_KEY: _IntRule(DEFAULT_THUMBNAIL_WIDTH, 1, None),
    THUMBNAIL_HEIGHT_KEY: _IntRule(DEFAULT_THUMBNAIL_HEIGHT, 1, None),
}


def parse_auto_scan_enabled(raw: str | None) -> bool:
    """只有 ``"true"``（不分大小写）算开。

    没写过这一行算**开**：新库的这张表是空的，一个字都没写过的人不该被静默停扫。
    写过但是空串算关——那是显式留下的一行，按字面读。
    """
    if raw is None:
        return True
    return raw.lower() == "true"


def setting_number(raw: str | None) -> int | None:
    """这行字符串是不是一个整数。只管字形，不管这个键能不能用它。

    写闸门要靠它把「这不是个数」和「这个数不能用」分成两句话说。
    """
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _in_span(rule: _IntRule, number: int) -> bool:
    return number >= rule.lo and (rule.hi is None or number <= rule.hi)


def int_setting_acceptable(key: str, value: str) -> bool:
    """``value`` 能不能作为这个键的值被读回来（区间内的整数）。"""
    number = setting_number(value)
    return number is not None and _in_span(INT_SETTING_RULES[key], number)


def int_setting_span(key: str) -> str:
    """这个键的可用区间，给人看的一句话的半成品。"""
    rule = INT_SETTING_RULES[key]
    return f"{rule.lo} 到 {rule.hi}" if rule.hi is not None else f"{rule.lo} 以上"


def parse_int_setting(key: str, raw: str | None) -> int:
    """这一行对这个数字键的意思；读不回来就回这一项的代码默认值。

    回退而不是报错，是因为这些键现在有了后台读者（一轮扫描、一次建源）：一行手工
    SQL 留下的脏值不该把定时任务打断，也不该把设置页打成 500。写闸门用的是同一张
    规则表，所以"回退"这条路只会出现在没人从 API 写过的行上。
    """
    rule = INT_SETTING_RULES[key]
    number = setting_number(raw)
    if number is None or not _in_span(rule, number):
        return rule.default
    return number


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

    async def get_auto_scan_interval(self) -> int:
        """新建视频源时那个「扫描间隔」输入框的默认值。"""
        result = await self.session.execute(
            select(Setting.value).where(Setting.key == AUTO_SCAN_INTERVAL_KEY)
        )
        return parse_int_setting(AUTO_SCAN_INTERVAL_KEY, result.scalar_one_or_none())

    async def get_thumbnail_size(self) -> tuple[int, int]:
        """这一轮封面刷成多大（宽、高）——两行一次读回来。"""
        result = await self.session.execute(
            select(Setting.key, Setting.value).where(
                Setting.key.in_([THUMBNAIL_WIDTH_KEY, THUMBNAIL_HEIGHT_KEY])
            )
        )
        rows: dict[str, str] = {key: value for key, value in result.all()}
        return (
            parse_int_setting(THUMBNAIL_WIDTH_KEY, rows.get(THUMBNAIL_WIDTH_KEY)),
            parse_int_setting(THUMBNAIL_HEIGHT_KEY, rows.get(THUMBNAIL_HEIGHT_KEY)),
        )

    async def values(self, keys: Iterable[str]) -> dict[str, str]:
        """整份设置页要用的那些行，一次查询。没写过的键不在结果里。"""
        result = await self.session.execute(
            select(Setting.key, Setting.value).where(Setting.key.in_(list(keys)))
        )
        return {key: value for key, value in result.all()}
