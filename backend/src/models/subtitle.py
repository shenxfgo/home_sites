from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base
from src.database.types import UTCDateTime


class Subtitle(Base):
    """Subtitle files for videos."""

    __tablename__ = "subtitles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False)
    label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Subtitle(id={self.id}, video_id={self.video_id}, language='{self.language}')>"
