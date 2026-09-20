from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.database.base import Base


class NewVideo(Base):
    """A title a scan brought in, shared by the whole household.

    Whether it is still "new" is per person, so that state lives in
    :class:`~src.models.read_state.NewVideoRead` rather than a flag here; the
    column ``viewed`` that used to hold it is gone from the model, and a
    database written before the change keeps a leftover copy SQLite ignores.
    """

    __tablename__ = "new_videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("video_sources.id", ondelete="CASCADE")
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<NewVideo(id={self.id}, video_id={self.video_id})>"
