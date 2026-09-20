from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.database.base import Base
from typing import Any


class Notification(Base):
    """System notifications, broadcast to everyone.

    Read state belongs to the person, not the row, so it lives in
    :class:`~src.models.read_state.NotificationRead`; the old ``read`` flag is
    gone from the model.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type='{self.type}', title='{self.title}')>"
