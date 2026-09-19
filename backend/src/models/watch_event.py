from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class WatchEvent(Base):
    """A stretch of playback the user actually advanced through.

    ``play_history`` keeps one row per title and says where the user left off,
    which cannot answer "how much was watched this month". Each progress report
    that moves the position forward appends the seconds it moved by, so the
    stats page has a timeline to aggregate.
    """

    __tablename__ = "watch_events"
    __table_args__ = (Index("ix_watch_events_occurred_at", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    #: Seconds advanced by this report, never negative.
    seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<WatchEvent(video_id={self.video_id}, seconds={self.seconds})>"
