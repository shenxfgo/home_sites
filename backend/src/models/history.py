from typing import TYPE_CHECKING

from sqlalchemy import Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from src.database.base import Base

if TYPE_CHECKING:
    from src.models.video import Video


class PlayHistory(Base):
    """Record of video playback."""

    __tablename__ = "play_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
        return f"<PlayHistory(id={self.id}, video_id={self.video_id}, progress={self.progress}s)>"
