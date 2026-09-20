from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from src.database.base import Base

if TYPE_CHECKING:
    from src.models.video import Video


class Favorite(Base):
    """A title one person kept. Each account has its own set."""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="ux_favorite_user_video"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    video: Mapped["Video"] = relationship("Video", lazy="select")

    def __repr__(self) -> str:
        return f"<Favorite(id={self.id}, user_id={self.user_id}, video_id={self.video_id})>"
