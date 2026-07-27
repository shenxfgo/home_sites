"""SourceService for video source CRUD operations."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.source import VideoSource
from src.scheduler import scheduler


class SourceService:
    """Service for managing video sources."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        name: str,
        path: str,
        type: str,  # noqa: A002
        scan_interval: int = 3600,
        is_active: bool = True,
    ) -> VideoSource:
        """Create a new video source."""
        source = VideoSource(
            name=name,
            path=path,
            type=type,
            scan_interval=scan_interval,
            is_active=is_active,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)

        # Auto-schedule active sources
        if source.is_active:
            scheduler.add_source_job(source.id, source.scan_interval)

        return source

    async def get_by_id(self, source_id: int) -> VideoSource | None:
        """Get a source by ID."""
        result = await self.session.execute(
            select(VideoSource).where(VideoSource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = False) -> list[VideoSource]:
        """List all video sources."""
        query = select(VideoSource)
        if active_only:
            query = query.where(VideoSource.is_active == True)  # noqa: E712
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        source_id: int,
        **kwargs,
    ) -> VideoSource:
        """Update a video source."""
        source = await self.get_by_id(source_id)
        if not source:
            raise ValueError(f"Source with id {source_id} not found")

        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)

        await self.session.commit()
        await self.session.refresh(source)

        # Sync scheduler when scan_interval or is_active changes
        if "scan_interval" in kwargs or "is_active" in kwargs:
            if source.is_active:
                scheduler.add_source_job(source.id, source.scan_interval)
            else:
                scheduler.remove_source_job(source.id)

        return source

    async def delete(self, source_id: int) -> None:
        """Delete a video source."""
        source = await self.get_by_id(source_id)
        if not source:
            raise ValueError(f"Source with id {source_id} not found")

        await self.session.delete(source)
        await self.session.commit()

        # Remove scheduled job for deleted source
        scheduler.remove_source_job(source_id)

    async def update_last_scan(self, source_id: int) -> None:
        """Update the last_scan_at timestamp for a source."""
        await self.update(source_id, last_scan_at=datetime.now(timezone.utc))
