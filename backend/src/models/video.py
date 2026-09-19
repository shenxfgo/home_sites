from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from src.database.base import Base


class Video(Base):
    """Video metadata and information."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("video_sources.id", ondelete="CASCADE")
    )
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seconds
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    series: Mapped[str | None] = mapped_column(String(512), nullable=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The last scan could not find the file. The row stays so the library does
    # not silently lose a title whose share is only momentarily unmounted.
    is_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rating: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    source = relationship("VideoSource", backref="videos")
    tags = relationship(
        "Tag",
        secondary="video_tags",
        back_populates="videos",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Video(id={self.id}, title='{self.title}', filepath='{self.filepath}')>"
