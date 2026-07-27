"""VideoService for video CRUD operations and playback tracking."""
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.video import Video
from src.models.new_video import NewVideo
from src.models.history import PlayHistory
from src.models.tag import video_tags


class VideoService:
    """Service for managing videos."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_videos(
        self,
        source_id: int | None = None,
        tag_id: int | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Video], int]:
        """Get videos with optional filtering, search, and pagination.

        Returns a tuple of (videos, total_count).
        """
        query = select(Video)
        count_query = select(func.count(Video.id))

        if source_id is not None:
            query = query.where(Video.source_id == source_id)
            count_query = count_query.where(Video.source_id == source_id)

        if tag_id is not None:
            query = query.join(video_tags).where(video_tags.c.tag_id == tag_id)
            count_query = count_query.join(video_tags).where(video_tags.c.tag_id == tag_id)

        if search:
            pattern = f"%{search}%"
            query = query.where(Video.title.ilike(pattern))
            count_query = count_query.where(Video.title.ilike(pattern))

        # Get total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Video.created_at.desc()).offset(offset).limit(page_size)

        result = await self.session.execute(query)
        videos = list(result.scalars().all())

        return videos, total

    async def get_video_by_id(self, video_id: int) -> Video | None:
        """Get a single video by ID."""
        result = await self.session.execute(
            select(Video).where(Video.id == video_id)
        )
        return result.scalar_one_or_none()

    async def update_video(self, video_id: int, **kwargs) -> Video:
        """Update a video's metadata."""
        video = await self.get_video_by_id(video_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        for key, value in kwargs.items():
            if hasattr(video, key):
                setattr(video, key, value)

        await self.session.commit()
        await self.session.refresh(video)
        return video

    async def delete_video(self, video_id: int) -> None:
        """Delete a video."""
        video = await self.get_video_by_id(video_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        await self.session.delete(video)
        await self.session.commit()

    async def get_new_videos(self, source_id: int | None = None) -> list[Video]:
        """Get videos that have been newly discovered and not yet viewed."""
        query = (
            select(Video)
            .join(NewVideo, NewVideo.video_id == Video.id)
            .where(NewVideo.viewed == False)  # noqa: E712
        )
        if source_id is not None:
            query = query.where(NewVideo.source_id == source_id)

        query = query.order_by(NewVideo.discovered_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_video_viewed(self, video_id: int) -> None:
        """Mark a video's new_video entry as viewed."""
        result = await self.session.execute(
            select(NewVideo).where(NewVideo.video_id == video_id)
        )
        new_video = result.scalar_one_or_none()
        if new_video:
            new_video.viewed = True
            await self.session.commit()

    async def record_play(self, video_id: int) -> None:
        """Record that a video was played."""
        video = await self.get_video_by_id(video_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        # Update video stats
        video.view_count += 1
        video.last_played_at = datetime.now(timezone.utc)

        # Create play history entry
        history = PlayHistory(video_id=video_id)
        self.session.add(history)

        await self.session.commit()

    async def update_progress(self, video_id: int, progress: int) -> None:
        """Update the playback progress for the most recent play history entry."""
        result = await self.session.execute(
            select(PlayHistory)
            .where(PlayHistory.video_id == video_id)
            .order_by(PlayHistory.played_at.desc())
            .limit(1)
        )
        history = result.scalar_one_or_none()
        if history:
            history.progress = progress
            # Mark as completed if progress is within 10 seconds of end
            # (only meaningful if video duration is known)
            video = await self.get_video_by_id(video_id)
            if video and video.duration and progress >= video.duration - 10:
                history.completed = True
            await self.session.commit()
