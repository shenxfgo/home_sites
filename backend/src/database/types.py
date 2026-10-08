"""全仓共用的列类型：目前只有一个「带时区的 UTC 时间戳」。

`UTCDateTime` 存在的原因是两种方言把同一个瞬间还回来的形状不一样：PostgreSQL 的
`TIMESTAMP WITH TIME ZONE` 带偏移，SQLite 的 `DATETIME` 只存"年-月-日 时:分:秒.微秒"那串
文本，读回来永远 naive。写进去的一律是 UTC（见 `src/utils/time.py`），所以读回来补上
`tzinfo=UTC` 就是同一时刻，不改变任何值。
"""

from datetime import datetime

from sqlalchemy.engine import Dialect
from sqlalchemy.types import DateTime, TypeDecorator

from src.utils.time import as_utc


class UTCDateTime(TypeDecorator):
    """带时区的时间戳：读回来永远带 `tzinfo=UTC`（#162）。

    只改写**读**的那一侧。建表语句由 `impl` 出，两种方言的编译结果和原来那句
    `DateTime(timezone=True)` 逐字节相同（`tests/test_utc_datetime_columns.py` 钉着这一条），
    所以库里已有的表一行都不用动，也不需要迁移。

    为什么修在类型这一层而不是调用点：病灶是 SQLAlchemy 的 ORM 批量删除——执行完它要在
    **Python 里**按同一条 WHERE 把 identity map 里的对象重跑一遍（`orm/evaluator.py`），
    于是那句 `expires_at <= now` 变成 `naive <= aware`，当场 `TypeError`。调用点怎么写都
    绕不开框架自己那次评估。
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return as_utc(value)


def is_datetime_column(coltype: object) -> bool:
    """这一列是不是时间戳——套了 `UTCDateTime` 的也要认。

    `TypeDecorator` 的实例**不是** `DateTime` 的实例（实测），所以凡是拿
    `isinstance(col.type, DateTime)` 分流的地方都必须先剥一层 `impl`，否则那一支会静默地
    不再命中。`src/db_audit.py` 有三处这样的分流。
    """
    return isinstance(getattr(coltype, "impl", coltype), DateTime)
