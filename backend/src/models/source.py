from sqlalchemy import String, Integer, Boolean, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.database.base import Base


class VideoSource(Base):
    """Video source configuration for scanning videos from different locations."""

    __tablename__ = "video_sources"
    __table_args__ = (
        CheckConstraint(
            "type IN ('local', 'nas', 'minio')",
            name="ck_video_source_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'local' | 'nas' | 'minio'
    scan_interval: Mapped[int] = mapped_column(Integer, default=3600)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<VideoSource(id={self.id}, name='{self.name}', type='{self.type}')>"
