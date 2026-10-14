"""界面偏好按人存一份，而不是全站共用一个 KV 行。

M2 之前主题写在 ``settings.theme``，结果是一个人切到深色，全家跟着变。
``settings`` 从此只放系统配置（扫描间隔、缩略图尺寸、默认转码格式），只有
owner 写得动；这一张表存每个人自己的界面选择，登录即生效。

``prefs`` 是个开放的结构：目前只有 ``theme``，播放器偏好将来加进来不用改表。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base
from src.database.types import UTCDateTime


class UserPreference(Base):
    """One row per account holding its own UI choices."""

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    prefs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 第六块面板 ④ 用户选甲：这一行不动，说明留在代码里。`default=dict` 是**列**默认，
    # 到 INSERT 才生效，所以一个没赋过 `prefs` 的实例上它是 `None`，`sorted(None)` 当场
    # 抛 `TypeError('NoneType' object is not iterable)`——一条为调试而生的 repr 在调试现场炸。
    # 今天够不着：全仓唯一的构造点 `preference_service.py:38` 永远显式传一个 dict（那一份
    # `current` 上面有 `isinstance` 兜底），读回来的行由 `nullable=False` 和 M2 那条裸 SQL
    # （`session.py:121` 只写 `{"theme": …}` 字面量）保证是对象。现状由
    # `tests/test_models/test_model_reprs.py` 里那条 `needs_a_dict_already_present` 钉着。
    def __repr__(self) -> str:
        return f"<UserPreference(user_id={self.user_id}, keys={sorted(self.prefs)})>"
