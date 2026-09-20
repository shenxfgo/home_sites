from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from src.database.base import Base

if TYPE_CHECKING:
    from src.models.video import Video


class Watchlist(Base):
    """A hand-picked queue of titles, such as 今晚看这些.

    The queue is a personal asset: each account sees and edits its own lists.
    Items keep the order they were added in, which is the order the owner
    intends to watch them, so no position column is needed.
    """

    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="ux_watchlist_owner_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Watchlist(id={self.id}, name='{self.name}')>"


class WatchlistItem(Base):
    """One video in a watchlist. A title can sit in several lists, once each."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "video_id", name="uq_watchlist_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), index=True
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")
    video: Mapped["Video"] = relationship("Video", lazy="selectin")

    def __repr__(self) -> str:
        return f"<WatchlistItem(id={self.id}, watchlist_id={self.watchlist_id}, video_id={self.video_id})>"
