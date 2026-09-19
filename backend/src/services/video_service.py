"""VideoService for video CRUD operations and playback tracking."""
import operator
from datetime import datetime, timezone

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.video import Video
from src.models.favorite import Favorite
from src.models.new_video import NewVideo
from src.models.history import PlayHistory
from src.models.source import VideoSource
from src.models.subtitle import Subtitle
from src.models.tag import Tag, video_tags
from src.utils.video_search import VideoSearchQuery, parse_video_search


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


async def attach_watch_progress(
    session: AsyncSession, videos: list[Video]
) -> None:
    """Set the transient ``progress`` (seconds watched) the resume UI reads.

    One row per video means a single indexed lookup serves the whole page, and
    the list endpoint stays the only place the rail's data comes from.
    """
    for video in videos:
        video.progress = None
    if not videos:
        return
    result = await session.execute(
        select(PlayHistory.video_id, PlayHistory.progress).where(
            PlayHistory.video_id.in_([v.id for v in videos])
        )
    )
    positions = dict(result.all())
    for video in videos:
        video.progress = positions.get(video.id)


_COMPARATORS = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "=": operator.eq,
}

# Correlated EXISTS fragments: a filter on a child table must not multiply the
# video rows, which is why these stay subqueries instead of joins.
_PLAYED = select(PlayHistory.id).where(PlayHistory.video_id == Video.id).exists()
_FINISHED = (
    select(PlayHistory.id)
    .where(PlayHistory.video_id == Video.id, PlayHistory.completed == True)  # noqa: E712
    .exists()
)


def _like(column, term: str):
    """A ``LIKE`` for a user typed term, with the wildcards inside it escaped."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _tagged_with(predicate):
    """EXISTS for a video carrying a tag that satisfies ``predicate``."""
    return (
        select(video_tags.c.video_id)
        .where(video_tags.c.video_id == Video.id)
        .join(Tag, Tag.id == video_tags.c.tag_id)
        .where(predicate)
        .exists()
    )


def _term_filter(term: str):
    """Where a single keyword may be found: title, description or tag name."""
    return or_(_like(Video.title, term), _like(Video.description, term), _tagged_with(_like(Tag.name, term)))


def _term_relevance(term: str):
    """How strongly one keyword matches: a title hit outranks the rest."""
    return case(
        (_like(Video.title, term), 2),
        (_like(Video.description, term), 1),
        (_tagged_with(_like(Tag.name, term)), 1),
        else_=0,
    )


def _search_filters(query: VideoSearchQuery) -> list:
    """Turn a parsed search box into WHERE clauses, terms combined with AND."""
    filters = [_term_filter(term) for term in query.terms]

    if query.source_name:
        filters.append(
            Video.source_id.in_(
                select(VideoSource.id).where(_like(VideoSource.name, query.source_name))
            )
        )
    if query.tag_name:
        filters.append(_tagged_with(_like(Tag.name, query.tag_name)))
    if query.rating:
        compare, value = query.rating
        filters.append(_COMPARATORS[compare](Video.rating, value))
    if query.duration:
        compare, seconds = query.duration
        filters.append(_COMPARATORS[compare](Video.duration, seconds))
    if query.watch_state == "never":
        filters.append(~_PLAYED)
    elif query.watch_state == "unfinished":
        filters.append(_PLAYED & ~_FINISHED)
    elif query.watch_state == "finished":
        filters.append(_FINISHED)

    return filters


def _search_order(query: VideoSearchQuery) -> list:
    """Order results, by relevance while keywords are in play."""
    if query.terms:
        score = _term_relevance(query.terms[0])
        for term in query.terms[1:]:
            score = score + _term_relevance(term)
        return [score.desc(), Video.created_at.desc(), Video.id.desc()]
    return [Video.created_at.desc(), Video.id.desc()]


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

        ``search`` is free text from the home page and is parsed here; see
        :mod:`src.utils.video_search` for the operators it accepts.

        Returns a tuple of (videos, total_count).
        """
        filters = []
        if source_id is not None:
            filters.append(Video.source_id == source_id)
        if tag_id is not None:
            filters.append(
                Video.id.in_(
                    select(video_tags.c.video_id).where(video_tags.c.tag_id == tag_id)
                )
            )
        parsed_search = parse_video_search(search)
        filters.extend(_search_filters(parsed_search))

        query = select(Video)
        count_query = select(func.count(Video.id))
        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        # Get total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(*_search_order(parsed_search)).offset(offset).limit(page_size)

        result = await self.session.execute(query)
        videos = list(result.scalars().all())
        await self._attach_new_flags(videos)
        await attach_watch_progress(self.session, videos)

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
        """Get a single video by ID, with its stored playback position attached."""
        result = await self.session.execute(
            select(Video).where(Video.id == video_id)
        )
        video = result.scalar_one_or_none()
        if video:
            await attach_watch_progress(self.session, [video])
        return video

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
