"""与数据库方言无关的时间处理。

写入库里的时间一律是 UTC，但读回来的形状跟着方言走，所以凡是拿库里的时间做减法或
取日历日的地方，都先过一道这里。
"""

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """把从库里读回来的时间收成"带 UTC 时区的同一时刻"。"""
    if value.tzinfo is None:
        # SQLite 的 DATETIME 不存偏移，读回来永远不带 tzinfo
        return value.replace(tzinfo=timezone.utc)
    # PG 的 TIMESTAMP WITH TIME ZONE 会按连接会话的时区还给应用
    return value.astimezone(timezone.utc)
