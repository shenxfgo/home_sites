from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.types import UTCDateTime

# 默认标签颜色的唯一出处。此前请求模型（`api/tags.py`）、服务层形参
# （`tag_service.py`）和这一列各写了一份同样的字面量，三处可以各走各的。
#
# 这一处是三个里唯一真往库里写颜色的：扫描自动建的标签（`scan_service._resolve_tags`
# 那句 `Tag(name=name)`）根本不走 `TagService.create`，颜色只可能来自列默认。
DEFAULT_TAG_COLOR = "#409eff"

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
    color: Mapped[str] = mapped_column(String(20), default=DEFAULT_TAG_COLOR)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    videos = relationship(
        "Video", secondary=video_tags, back_populates="tags", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}')>"
