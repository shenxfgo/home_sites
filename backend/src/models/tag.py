from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.types import UTCDateTime

# Association table for many-to-many relationship
video_tags = Table(
    "video_tags",
    Base.metadata,
    Column("video_id", ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """Tag for categorizing videos."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(20), default="#409eff")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    videos = relationship(
        "Video", secondary=video_tags, back_populates="tags", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}')>"
