"""VideoService for video CRUD operations and playback tracking."""
from datetime import datetime, timezone

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.video import Video
from src.models.favorite import Favorite
from src.models.new_video import NewVideo
from src.models.history import PlayHistory
from src.models.subtitle import Subtitle
from src.models.tag import video_tags


def is_completed(progress: int, duration: int | None) -> bool:
    """Whether ``progress`` counts as having watched the video to the end.

    Players rarely report the final second, so a tail is tolerated. The tail
    scales with the title: 5% of its length, capped at 10 seconds, so short
    clips are not marked finished after half of the video played.
    """
    if not duration or duration <= 0:
        return False
    return progress >= duration - max(1, min(10, duration * 0.05))


async def delete_videos_cascade(
    session: AsyncSession, video_filter
) -> None:
    """Delete the matching videos together with every row pointing at them.

    The schema declares ``ondelete="CASCADE"``, but SQLite only honours that
    when foreign key enforcement is enabled, which this project does not do.
    Without these explicit deletes, removing a video (or its source) leaves
    orphaned history, favorite and new-video rows behind.
    """
    video_ids = select(Video.id).where(video_filter)
    for model in (PlayHistory, Favorite, NewVideo, Subtitle):
        await session.execute(
            delete(model).where(model.video_id.in_(video_ids))
        )
    await session.execute(
        delete(video_tags).where(video_tags.c.video_id.in_(video_ids))
    )
    await session.execute(delete(Video).where(video_filter))


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
        await self._attach_new_flags(videos)

        return videos, total

    async def _attach_new_flags(self, videos: list[Video]) -> None:
        """Set the transient ``is_new`` flag the badge in the UI reads.

        A video is new while an unwatched scan record for it exists, so the
        badge follows "has the user watched it yet" instead of the file's age.
        """
        for video in videos:
            video.is_new = False
        if not videos:
            return
        result = await self.session.execute(
            select(NewVideo.video_id).where(
                NewVideo.video_id.in_([v.id for v in videos]),
                NewVideo.viewed == False,  # noqa: E712
            )
        )
        new_ids = set(result.scalars().all())
        for video in videos:
            video.is_new = video.id in new_ids

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

        await delete_videos_cascade(self.session, Video.id == video_id)
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
        videos = list(result.scalars().all())
        await self._attach_new_flags(videos)
        return videos

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
        """Start a playback session for a video.

        History keeps one row per video, so replaying refreshes that row instead
        of appending a duplicate; the first play also clears the new-video badge.
        """
        video = await self.get_video_by_id(video_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        now = datetime.now(timezone.utc)
        video.view_count += 1
        video.last_played_at = now

        history = await self._get_or_create_history(video_id)
        history.played_at = now
        # Playback always starts from the beginning here, so the stored position
        # is wrong the moment a new session does; progress arrives right after.
        history.progress = 0
        history.completed = False

        await self.mark_video_viewed(video_id)
        await self.session.commit()

    async def _get_or_create_history(self, video_id: int) -> PlayHistory:
        """Return the single history row of a video, creating it when missing."""
        result = await self.session.execute(
            select(PlayHistory).where(PlayHistory.video_id == video_id)
        )
        history = result.scalar_one_or_none()
        if history is None:
            history = PlayHistory(video_id=video_id)
            self.session.add(history)
        return history

    async def update_progress(self, video_id: int, progress: int) -> None:
        """Remember where playback of a video stands."""
        video = await self.get_video_by_id(video_id)
        if not video:
            return

        history = await self._get_or_create_history(video_id)
        history.progress = progress
        history.completed = is_completed(progress, video.duration)
        history.played_at = datetime.now(timezone.utc)
        await self.session.commit()
