"""HistoryService for playback history operations."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.history import PlayHistory
from src.models.tag import Tag, video_tags
from src.models.video import Video
from src.models.watch_event import WatchEvent


def _longest_streak(days: list[date]) -> int:
    """Longest run of consecutive calendar days that has a bar in it."""
    best = current = 0
    for previous, day in zip([None, *days], days):
        current = current + 1 if previous and (day - previous).days == 1 else 1
        best = max(best, current)
    return best


class HistoryService:
    """Service for managing playback history."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_history(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[PlayHistory], int]:
        """Get paginated playback history, most recent watch first."""
        total_result = await self.session.execute(
            select(func.count(PlayHistory.id))
        )
        total = total_result.scalar_one()

        query = (
            select(PlayHistory)
            .order_by(desc(PlayHistory.played_at))
            .options(selectinload(PlayHistory.video))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        history = list(result.scalars().all())

        return history, total

    async def get_continue_list(self) -> list[Video]:
        """Get videos left unfinished, the one most recently watched first.

        The history row already carries the position, so it is copied onto the
        video the resume rail renders instead of looking it up a second time.
        """
        query = (
            select(PlayHistory)
            .where(PlayHistory.completed == False)  # noqa: E712
            .order_by(desc(PlayHistory.played_at))
            .options(selectinload(PlayHistory.video))
            .limit(20)
        )
        result = await self.session.execute(query)
        history_items = list(result.scalars().all())
        videos = []
        for record in history_items:
            if record.video:
                record.video.progress = record.progress
                videos.append(record.video)
        return videos

    async def get_stats(self, days: int = 30) -> dict:
        """Add up the watch-event log: hours in a window, streaks, and tags.

        One row per title in ``play_history`` cannot say how much was watched
        this month, so this reads ``watch_events``, which is the timeline. Days
        are UTC calendar days and the window is zero-filled, so the chart has a
        bar for every day it covers whether or not anything was watched.
        """
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        since = today - timedelta(days=days - 1)
        day = func.date(WatchEvent.occurred_at)

        rows = await self.session.execute(
            select(
                day.label("day"),
                func.sum(WatchEvent.seconds),
                func.count(func.distinct(WatchEvent.video_id)),
            )
            .where(WatchEvent.occurred_at >= since)
            .group_by(day)
        )
        by_day = {str(row[0]): (row[1] or 0, row[2] or 0) for row in rows.all()}

        daily = []
        for offset in range(days):
            key = (since + timedelta(days=offset)).date().isoformat()
            seconds, videos = by_day.get(key, (0, 0))
            daily.append({"date": key, "seconds": int(seconds), "videos": videos})

        totals = await self.session.execute(
            select(
                func.coalesce(func.sum(WatchEvent.seconds), 0),
                func.count(func.distinct(WatchEvent.video_id)),
            ).where(WatchEvent.occurred_at >= since)
        )
        window_seconds, videos_watched = totals.one()

        month_start = today.replace(day=1)
        month_seconds = (
            await self.session.execute(
                select(func.coalesce(func.sum(WatchEvent.seconds), 0)).where(
                    WatchEvent.occurred_at >= month_start
                )
            )
        ).scalar_one()

        tags = await self.session.execute(
            select(Tag.name, Tag.color, func.sum(WatchEvent.seconds))
            .join(video_tags, video_tags.c.tag_id == Tag.id)
            .join(WatchEvent, WatchEvent.video_id == video_tags.c.video_id)
            .where(WatchEvent.occurred_at >= since)
            .group_by(Tag.id)
            .order_by(desc(func.sum(WatchEvent.seconds)))
            .limit(8)
        )

        watched_days = sorted(date.fromisoformat(entry["date"]) for entry in daily if entry["seconds"])
        return {
            "days": days,
            "window_seconds": int(window_seconds),
            "month_seconds": int(month_seconds),
            "videos_watched": int(videos_watched),
            "active_days": len(watched_days),
            "longest_streak_days": _longest_streak(watched_days),
            "daily": daily,
            "tags": [
                {"name": name, "color": color, "seconds": int(seconds or 0)}
                for name, color, seconds in tags.all()
            ],
        }

    async def delete_history(self, history_id: int) -> None:
        """Delete a history record."""
        result = await self.session.execute(
            select(PlayHistory).where(PlayHistory.id == history_id)
        )
        history = result.scalar_one_or_none()
        if not history:
            raise ValueError(f"History with id {history_id} not found")

        await self.session.delete(history)
        await self.session.commit()
