"""VideoService for video CRUD operations and playback tracking."""
import asyncio
import operator
from datetime import datetime, timezone

from sqlalchemy import case, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.video import Video
from src.models.favorite import Favorite
from src.models.new_video import NewVideo
from src.models.read_state import NewVideoRead
from src.models.history import PlayHistory
from src.models.source import VideoSource
from src.models.subtitle import Subtitle
from src.models.tag import Tag, video_tags
from src.models.watch_event import WatchEvent
from src.models.watchlist import WatchlistItem
from src.storage import fingerprint
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
    # The per-person "seen it" rows hang off ``new_videos``, so they go first.
    await session.execute(
        delete(NewVideoRead).where(
            NewVideoRead.new_video_id.in_(
                select(NewVideo.id).where(NewVideo.video_id.in_(video_ids))
            )
        )
    )
    for model in (PlayHistory, Favorite, NewVideo, Subtitle, WatchEvent, WatchlistItem):
        await session.execute(
            delete(model).where(model.video_id.in_(video_ids))
        )
    await session.execute(
        delete(video_tags).where(video_tags.c.video_id.in_(video_ids))
    )
    await session.execute(delete(Video).where(video_filter))


async def attach_watch_progress(
    session: AsyncSession, videos: list[Video], user_id: int
) -> None:
    """Set the transient ``progress`` (seconds watched) the resume UI reads.

    The position is whosever watched it, so the lookup is scoped to one account;
    one indexed query still serves the whole page, and the list endpoint stays
    the only place the rail's data comes from.
    """
    for video in videos:
        video.progress = None
    if not videos:
        return
    result = await session.execute(
        select(PlayHistory.video_id, PlayHistory.progress).where(
            PlayHistory.user_id == user_id,
            PlayHistory.video_id.in_([v.id for v in videos]),
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
# video rows, which is why these stay subqueries instead of joins. Whether a
# title counts as played is each person's own, so both take the viewer.
def _played(user_id: int):
    return (
        select(PlayHistory.id)
        .where(PlayHistory.video_id == Video.id, PlayHistory.user_id == user_id)
        .exists()
    )


def _finished(user_id: int):
    return (
        select(PlayHistory.id)
        .where(
            PlayHistory.video_id == Video.id,
            PlayHistory.user_id == user_id,
            PlayHistory.completed == True,  # noqa: E712
        )
        .exists()
    )


def _unread_new_video(user_id: int):
    """EXISTS for a scan record of this video the viewer has not read yet."""
    return (
        select(NewVideo.id)
        .where(
            NewVideo.video_id == Video.id,
            ~exists(
                select(NewVideoRead.new_video_id).where(
                    NewVideoRead.new_video_id == NewVideo.id,
                    NewVideoRead.user_id == user_id,
                )
            ),
        )
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


def _search_filters(query: VideoSearchQuery, user_id: int) -> list:
    """Turn a parsed search box into WHERE clauses, terms combined with AND.

    ``user_id`` scopes the watch-state operators: "看完了" means this person has
    finished it, not somebody else.
    """
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
        filters.append(~_played(user_id))
    elif query.watch_state == "unfinished":
        filters.append(_played(user_id) & ~_finished(user_id))
    elif query.watch_state == "finished":
        filters.append(_finished(user_id))
    if query.missing:
        filters.append(Video.is_missing == True)  # noqa: E712

    return filters


def _search_order(query: VideoSearchQuery) -> list:
    """Order results, by relevance while keywords are in play."""
    if query.terms:
        score = _term_relevance(query.terms[0])
        for term in query.terms[1:]:
            score = score + _term_relevance(term)
        return [score.desc(), Video.created_at.desc(), Video.id.desc()]
    return [Video.created_at.desc(), Video.id.desc()]


#: Candidate files one duplicate check may open. Each costs a fixed 2 MB read
#: from the share, and a home NAS answers slowly enough that an unbounded
#: sweep over a big library would hold the request open for minutes.
_DUPLICATE_PROBE_MAX = 300


def _keep_candidate(videos: list[Video]) -> Video:
    """Pick the copy worth keeping when several hold the same bytes.

    The one that has been watched is the one whose history matters, so progress
    decides first and the oldest row breaks the tie.
    """
    return max(
        videos,
        key=lambda v: (v.view_count, v.progress or 0, -v.id),
    )


class VideoService:
    """Service for managing videos."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_series_progress(self, user_id: int) -> list[dict]:
        """How far each parsed series has been watched by one person.

        One grouped query counts the episodes, and only the episodes still
        outstanding are loaded as rows, so a big finished series costs nothing
        beyond its counters.
        """
        finished_clause = _finished(user_id)
        counts = await self.session.execute(
            select(
                Video.series,
                func.count(Video.id),
                func.sum(case((finished_clause, 1), else_=0)),
                func.sum(case((_played(user_id), 1), else_=0)),
            )
            .where(Video.series.is_not(None))
            .group_by(Video.series)
        )
        series = {
            name: {
                "series": name,
                "total": total,
                "finished": finished or 0,
                "watched": watched or 0,
                "next": None,
            }
            for name, total, finished, watched in counts.all()
        }
        if not series:
            return []

        outstanding = await self.session.execute(
            select(Video)
            .where(Video.series.is_not(None), ~_finished(user_id))
            .order_by(
                func.coalesce(Video.season, 1).asc(),
                func.coalesce(Video.episode, 0).asc(),
                Video.id.asc(),
            )
        )
        for video in outstanding.scalars().all():
            entry = series.get(video.series)
            if entry is None or entry["next"] is not None:
                continue
            await attach_watch_progress(self.session, [video], user_id)
            entry["next"] = video

        return sorted(series.values(), key=lambda entry: entry["series"])

    async def get_duplicates(self, user_id: int) -> list[dict]:
        """List copies of the same file that are both in the library.

        Size and duration are compared in SQL, which costs nothing, and only
        the handful of rows that already share both get their first and last
        megabyte hashed. Two entries for a file the share will not open are
        left out rather than guessed at, and the copy whose watch history is
        richest is named as the one to keep.
        """
        buckets = await self.session.execute(
            select(Video.file_size, Video.duration)
            .where(Video.file_size.is_not(None))
            .group_by(Video.file_size, Video.duration)
            .having(func.count(Video.id) > 1)
        )
        sizes = [size for size, _ in buckets.all()]
        if not sizes:
            return []

        result = await self.session.execute(
            select(Video)
            .where(Video.file_size.in_(sizes))
            .order_by(Video.file_size.asc(), Video.duration.asc(), Video.id.asc())
        )
        by_size_and_duration: dict[tuple[int, int | None], list[Video]] = {}
        for video in result.scalars().all():
            by_size_and_duration.setdefault(
                (video.file_size, video.duration), []
            ).append(video)

        # Biggest reclaimable group first, so a request that runs out of read
        # budget spends it on the copies worth deleting.
        candidates = [
            group for group in by_size_and_duration.values() if len(group) > 1
        ]
        candidates.sort(
            key=lambda group: (len(group) - 1) * group[0].file_size, reverse=True
        )
        probed: list[list[Video]] = []
        budget = _DUPLICATE_PROBE_MAX
        for group in candidates:
            if len(group) > budget:
                continue
            budget -= len(group)
            probed.append(group)
        if not probed:
            return []

        flat = [video for group in probed for video in group]
        await attach_watch_progress(self.session, flat, user_id)
        digests = await asyncio.gather(
            *(asyncio.to_thread(fingerprint, video.filepath) for video in flat)
        )
        fingerprints = dict(zip((video.id for video in flat), digests))

        groups = []
        for group in probed:
            by_digest: dict[str, list[Video]] = {}
            for video in group:
                digest = fingerprints.get(video.id)
                if digest is not None:
                    by_digest.setdefault(digest, []).append(video)
            for members in by_digest.values():
                if len(members) < 2:
                    continue
                keep = _keep_candidate(members)
                size = keep.file_size
                groups.append(
                    {
                        "file_size": size,
                        "duration": keep.duration,
                        "count": len(members),
                        "wasted_bytes": size * (len(members) - 1),
                        "keep_id": keep.id,
                        "items": sorted(members, key=lambda v: v.id != keep.id),
                    }
                )

        groups.sort(key=lambda group: (group["wasted_bytes"], group["count"]), reverse=True)
        return groups

    async def get_videos(
        self,
        user_id: int,
        source_id: int | None = None,
        tag_id: int | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Video], int]:
        """Get videos with optional filtering, search, and pagination.

        ``search`` is free text from the home page and is parsed here; see
        :mod:`src.utils.video_search` for the operators it accepts. ``user_id``
        scopes the per-person parts: the new badge, the resume position, and
        any watch-state operator in the search text. The rows themselves are the
        shared library.

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
        filters.extend(_search_filters(parsed_search, user_id))

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
        await self._attach_new_flags(videos, user_id)
        await attach_watch_progress(self.session, videos, user_id)

        return videos, total

    async def _attach_new_flags(self, videos: list[Video], user_id: int) -> None:
        """Set the transient ``is_new`` flag the badge in the UI reads.

        A video is new while an unwatched scan record for it exists that *this*
        account has not read, so the badge follows "have you watched it yet".
        """
        for video in videos:
            video.is_new = False
        if not videos:
            return
        result = await self.session.execute(
            select(Video.id).where(
                Video.id.in_([v.id for v in videos]),
                _unread_new_video(user_id),
            )
        )
        new_ids = set(result.scalars().all())
        for video in videos:
            video.is_new = video.id in new_ids

    async def get_video_by_id(self, video_id: int, user_id: int) -> Video | None:
        """Get a single video by ID, with the caller's playback position."""
        result = await self.session.execute(
            select(Video).where(Video.id == video_id)
        )
        video = result.scalar_one_or_none()
        if video:
            await attach_watch_progress(self.session, [video], user_id)
        return video

    async def update_video(self, video_id: int, user_id: int, **kwargs) -> Video:
        """Update a video's metadata. The library is shared, so anyone signed in
        edits the same row."""
        video = await self.get_video_by_id(video_id, user_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        for key, value in kwargs.items():
            if hasattr(video, key):
                setattr(video, key, value)

        await self.session.commit()
        await self.session.refresh(video)
        return video

    async def delete_video(self, video_id: int) -> None:
        """Delete a video, with every account's rows pointing at it."""
        video = await self.session.get(Video, video_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        await delete_videos_cascade(self.session, Video.id == video_id)
        await self.session.commit()

    async def get_new_videos(self, user_id: int, source_id: int | None = None) -> list[Video]:
        """Get videos the caller discovered and has not looked at yet."""
        query = (
            select(Video)
            .join(NewVideo, NewVideo.video_id == Video.id)
            .where(
                ~exists(
                    select(NewVideoRead.new_video_id).where(
                        NewVideoRead.new_video_id == NewVideo.id,
                        NewVideoRead.user_id == user_id,
                    )
                )
            )
        )
        if source_id is not None:
            query = query.where(NewVideo.source_id == source_id)

        query = query.order_by(NewVideo.discovered_at.desc())
        result = await self.session.execute(query)
        videos = list(result.scalars().all())
        await self._attach_new_flags(videos, user_id)
        return videos

    async def mark_video_viewed(self, user_id: int, video_id: int) -> None:
        """Record that the caller has seen this arrival, clearing their badge."""
        result = await self.session.execute(
            select(NewVideo.id).where(NewVideo.video_id == video_id)
        )
        for new_video_id in result.scalars():
            already = await self.session.get(
                NewVideoRead, (new_video_id, user_id)
            )
            if not already:
                self.session.add(
                    NewVideoRead(new_video_id=new_video_id, user_id=user_id)
                )
        await self.session.commit()

    async def record_play(self, user_id: int, video_id: int) -> None:
        """Start a playback session for a video.

        History keeps one row per person and title, so replaying refreshes that
        row instead of appending a duplicate; the first play also clears the
        new-video badge for whoever pressed play.
        """
        video = await self.get_video_by_id(video_id, user_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        now = datetime.now(timezone.utc)
        video.view_count += 1
        video.last_played_at = now

        history = await self._get_or_create_history(user_id, video_id)
        history.played_at = now
        # Playback always starts from the beginning here, so the stored position
        # is wrong the moment a new session does; progress arrives right after.
        history.progress = 0
        history.completed = False

        await self.mark_video_viewed(user_id, video_id)
        await self.session.commit()

    async def _get_or_create_history(self, user_id: int, video_id: int) -> PlayHistory:
        """Return the caller's history row of a video, creating it when missing."""
        result = await self.session.execute(
            select(PlayHistory).where(
                PlayHistory.video_id == video_id,
                PlayHistory.user_id == user_id,
            )
        )
        history = result.scalar_one_or_none()
        if history is None:
            history = PlayHistory(user_id=user_id, video_id=video_id)
            self.session.add(history)
        return history

    async def update_progress(self, user_id: int, video_id: int, progress: int) -> None:
        """Remember where the caller's playback of a video stands.

        A report that moves the position forward is also the cheapest evidence of
        how much was really watched, so it appends a watch event for the seconds
        gained. Reports that move backwards — a seek, a replay — add nothing
        rather than subtracting, which keeps the totals a sum of watching done.
        """
        video = await self.get_video_by_id(video_id, user_id)
        if not video:
            return

        history = await self._get_or_create_history(user_id, video_id)
        gained = max(0, progress - (history.progress or 0))
        history.progress = progress
        history.completed = is_completed(progress, video.duration)
        history.played_at = datetime.now(timezone.utc)
        if gained:
            self.session.add(
                WatchEvent(user_id=user_id, video_id=video_id, seconds=gained)
            )
        await self.session.commit()
