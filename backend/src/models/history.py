from typing import TYPE_CHECKING

from sqlalchemy import Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from src.database.base import Base

if TYPE_CHECKING:
    from src.models.video import Video


class PlayHistory(Base):
    """Where one person left off in a video.

    One row per (person, video): replaying updates the existing row instead of
    appending, so the history list and the continue-watching rail never show a
    title twice. Two people watching the same title keep two rows, which is why
    ``video_id`` alone must not be unique here.
    """

    __tablename__ = "play_history"
    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="ux_play_history_user_video"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)  # seconds
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    video: Mapped["Video"] = relationship("Video", lazy="select")

    def __repr__(self) -> str:
        return (
            f"<PlayHistory(id={self.id}, user_id={self.user_id}, "
            f"video_id={self.video_id}, progress={self.progress}s)>"
        )
