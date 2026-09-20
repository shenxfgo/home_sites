"""Per-person read state for content that is broadcast to the whole household.

扫描通知和新片日志各只有一份全局行，"看过了"是每个人自己的事，所以这里记
"谁读过哪一条"，而不是给每个人复制一行。两边都是复合主键，天然去重。
"""

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class NewVideoRead(Base):
    """The caller has seen that a title arrived; its 新 badge is off for them."""

    __tablename__ = "new_video_reads"
    __table_args__ = (Index("ix_new_video_reads_user_id", "user_id"),)

    new_video_id: Mapped[int] = mapped_column(
        ForeignKey("new_videos.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    def __repr__(self) -> str:
        return f"<NewVideoRead(new_video_id={self.new_video_id}, user_id={self.user_id})>"


class NotificationRead(Base):
    """The caller has opened one notification; others still see it as unread."""

    __tablename__ = "notification_reads"
    __table_args__ = (Index("ix_notification_reads_user_id", "user_id"),)

    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationRead(notification_id={self.notification_id}, "
            f"user_id={self.user_id})>"
        )
