"""HistoryService for playback history operations."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.history import PlayHistory
from src.models.tag import Tag, video_tags
from src.models.video import Video
from src.models.watch_event import WatchEvent
from src.utils.time import as_utc


def _longest_streak(days: list[date]) -> int:
    """Longest run of consecutive calendar days that has a bar in it."""
    best = current = 0
    for previous, day in zip([None, *days], days):
        current = current + 1 if previous and (day - previous).days == 1 else 1
        best = max(best, current)
    return best


class HistoryService:
    """Service for managing one person's playback history.

    Where and how far a title was watched is a per-account fact, so every query
    here is scoped by ``user_id``; the library is shared, the positions are not.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_history(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[PlayHistory], int]:
        """Get paginated playback history, most recent watch first."""
        total_result = await self.session.execute(
            select(func.count(PlayHistory.id)).where(PlayHistory.user_id == user_id)
        )
        total = total_result.scalar_one()

        query = (
            select(PlayHistory)
            .where(PlayHistory.user_id == user_id)
            .order_by(desc(PlayHistory.played_at))
            .options(selectinload(PlayHistory.video))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        history = list(result.scalars().all())

        return history, total

    async def get_continue_list(self, user_id: int) -> list[Video]:
        """Get the caller's videos left unfinished, most recently watched first.

        The history row already carries the position, so it is copied onto the
        video the resume rail renders instead of looking it up a second time.
        """
        query = (
            select(PlayHistory)
            .where(
                PlayHistory.user_id == user_id,
                PlayHistory.completed == False,  # noqa: E712
            )
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

    async def get_stats(self, user_id: int, days: int = 30) -> dict:
        """Add up one person's watch-event log: hours, streaks, and tags.

        One row per title in ``play_history`` cannot say how much was watched
        this month, so this reads ``watch_events``, which is the timeline. Days
        are UTC calendar days and the window is zero-filled, so the chart has a
        bar for every day it covers whether or not anything was watched.
        """
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        since = today - timedelta(days=days - 1)
        owned = WatchEvent.user_id == user_id

        # 归桶放在 Python 里：SQL 没有一个跨方言的"取日历日"写法（PG 没有 date() 函数，
        # 而 SQLite 的 CAST(x AS DATE) 会把文本折成数字），原来 func.date() 只在一家成立。
        # 窗口上限 365 天、一个人一天几十条，读全原始行也不大，顺手把总时长和总影片数
        # 一起算掉，原来那第二条汇总查询就没有存在的必要了。
        rows = await self.session.execute(
            select(
                WatchEvent.occurred_at, WatchEvent.video_id, WatchEvent.seconds
            ).where(WatchEvent.occurred_at >= since, owned)
        )
        seconds_by_day: dict[str, int] = {}
        videos_by_day: dict[str, set[int]] = {}
        for occurred_at, video_id, seconds in rows.all():
            key = as_utc(occurred_at).date().isoformat()
            seconds_by_day[key] = seconds_by_day.get(key, 0) + seconds
            videos_by_day.setdefault(key, set()).add(video_id)

        daily = []
        for offset in range(days):
            key = (since + timedelta(days=offset)).date().isoformat()
            daily.append(
                {
                    "date": key,
                    "seconds": seconds_by_day.get(key, 0),
                    "videos": len(videos_by_day.get(key, ())),
                }
            )

        window_seconds = sum(seconds_by_day.values())
        videos_watched = len({video for group in videos_by_day.values() for video in group})

        month_start = today.replace(day=1)
        month_seconds = (
            await self.session.execute(
                select(func.coalesce(func.sum(WatchEvent.seconds), 0)).where(
                    WatchEvent.occurred_at >= month_start, owned
                )
            )
        ).scalar_one()

        tags = await self.session.execute(
            select(Tag.name, Tag.color, func.sum(WatchEvent.seconds))
            .join(video_tags, video_tags.c.tag_id == Tag.id)
            .join(WatchEvent, WatchEvent.video_id == video_tags.c.video_id)
            .where(WatchEvent.occurred_at >= since, owned)
            .group_by(Tag.id)
            .order_by(desc(func.sum(WatchEvent.seconds)))
            .limit(8)
        )

        watched_days = sorted(
            date.fromisoformat(entry["date"]) for entry in daily if entry["seconds"]
        )
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

    async def delete_history(self, user_id: int, history_id: int) -> None:
        """Delete one of the caller's history records.

        The owner is part of the lookup, so another account's row reads as
        missing rather than being deleted.
        """
        result = await self.session.execute(
            select(PlayHistory).where(
                PlayHistory.id == history_id, PlayHistory.user_id == user_id
            )
        )
        history = result.scalar_one_or_none()
        if not history:
            raise ValueError(f"History with id {history_id} not found")

        await self.session.delete(history)
        await self.session.commit()
