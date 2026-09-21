"""界面偏好按人存一份，而不是全站共用一个 KV 行。

M2 之前主题写在 ``settings.theme``，结果是一个人切到深色，全家跟着变。
``settings`` 从此只放系统配置（扫描间隔、缩略图尺寸、默认转码格式），只有
owner 写得动；这一张表存每个人自己的界面选择，登录即生效。

``prefs`` 是个开放的结构：目前只有 ``theme``，播放器偏好将来加进来不用改表。
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class UserPreference(Base):
    """One row per account holding its own UI choices."""

    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    prefs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<UserPreference(user_id={self.user_id}, keys={sorted(self.prefs)})>"
