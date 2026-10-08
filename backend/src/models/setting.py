"""Setting model."""
from datetime import datetime, timezone

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base
from src.database.types import UTCDateTime


class Setting(Base):
    """Application setting stored as key-value pair."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    # 这里以前没写类型，SQLAlchemy 就按 ``Mapped[datetime]`` 推断成不带时区的
    # TIMESTAMP，可默认值给的却是带时区的 ``now(timezone.utc)``。SQLite 不挑，照收；
    # PostgreSQL 的裸 TIMESTAMP 拒绝带偏移的值，写这条设置就成了 500。全项目的
    # 时间列都统一成带时区，这一列不能再是例外。
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
