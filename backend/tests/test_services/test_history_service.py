"""Tests for HistoryService reads behind the history page and continue rail."""
import pytest

from sqlalchemy import select

from src.models.video import Video
from src.models.history import PlayHistory
from src.models.watch_event import WatchEvent
from src.services.history_service import HistoryService


async def _watch(session, user_id, video_id, progress, completed, played_at):
    """Record one viewer's history row for a video, at a position and time."""
    from datetime import datetime, timezone

    session.add(
        PlayHistory(
            user_id=user_id,
            video_id=video_id,
            progress=progress,
            completed=completed,
            played_at=datetime(*played_at, tzinfo=timezone.utc),
        )
    )
    await session.commit()


async def _create_video(session, video_id, title):
    video = Video(
        id=video_id,
        source_id=1,
        filepath=f"/test/{title}.mp4",
        title=title,
        duration=120,
    )
    session.add(video)
    await session.commit()
    return video


@pytest.mark.asyncio
async def test_get_history_paginates_without_losing_the_total(db_session, user_id):
    for video_id in (1, 2, 3):
        await _create_video(db_session, video_id, f"视频 {video_id}")
        await _watch(db_session, user_id, video_id, 10, False, (2026, 1, video_id))

    service = HistoryService(db_session)

    first_page, total = await service.get_history(user_id, page=1, page_size=2)
    assert total == 3
    assert [h.video_id for h in first_page] == [3, 2]

    second_page, total = await service.get_history(user_id, page=2, page_size=2)
    assert total == 3
    assert [h.video_id for h in second_page] == [1]


@pytest.mark.asyncio
async def test_continue_list_offers_each_unfinished_video_once(db_session, user_id):
    """The rail is the same video the table already lists, never repeated."""
    for video_id in (1, 2, 3):
        await _create_video(db_session, video_id, f"视频 {video_id}")
    await _watch(db_session, user_id, 1, 60, False, (2026, 1, 5))
    await _watch(db_session, user_id, 2, 118, True, (2026, 1, 4))
    await _watch(db_session, user_id, 3, 20, False, (2026, 1, 6))

    service = HistoryService(db_session)
    videos = await service.get_continue_list(user_id)

    assert [video.id for video in videos] == [3, 1]

    rows = await db_session.execute(select(PlayHistory))
    assert len(rows.scalars().all()) == 3


@pytest.mark.asyncio
async def test_continue_list_carries_the_position_of_its_own_row(db_session, user_id):
    """Each rail video reports where its single history row stopped."""
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    await _watch(db_session, user_id, 1, 45, False, (2026, 1, 5))
    await _watch(db_session, user_id, 2, 90, False, (2026, 1, 6))

    service = HistoryService(db_session)
    videos = await service.get_continue_list(user_id)

    assert [(video.id, video.progress, video.duration) for video in videos] == [
        (2, 90, 120),
        (1, 45, 120),
    ]


async def _event(session, user_id, video_id, seconds, *, days_ago=0, hour=12):
    """Append one watch event a given number of days back from today."""
    from datetime import datetime, timedelta, timezone

    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    when = when.replace(hour=hour, minute=0, second=0, microsecond=0)
    session.add(
        WatchEvent(user_id=user_id, video_id=video_id, seconds=seconds, occurred_at=when)
    )
    await session.commit()
    return when


@pytest.mark.asyncio
async def test_stats_total_the_window_and_fill_every_day(db_session, user_id):
    """The chart needs a bar per day, and only days inside the window count."""
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    await _event(db_session, user_id, 1, 600, days_ago=2)
    await _event(db_session, user_id, 1, 300, days_ago=1)
    await _event(db_session, user_id, 2, 100, days_ago=3)
    await _event(db_session, user_id, 2, 9999, days_ago=40)

    stats = await HistoryService(db_session).get_stats(user_id, days=7)

    assert len(stats["daily"]) == 7
    assert stats["window_seconds"] == 1000
    assert stats["videos_watched"] == 2
    assert stats["active_days"] == 3
    assert stats["daily"][-1]["seconds"] == 0
    assert [entry["seconds"] for entry in stats["daily"]][-4:] == [100, 600, 300, 0]


@pytest.mark.asyncio
async def test_stats_find_the_longest_run_of_watch_days(db_session, user_id):
    """Three days in a row, then a gap, is a streak of three."""
    await _create_video(db_session, 1, "暗涌")
    for days_ago in (0, 1, 2, 4):
        await _event(db_session, user_id, 1, 60, days_ago=days_ago)

    stats = await HistoryService(db_session).get_stats(user_id, days=30)

    assert (stats["longest_streak_days"], stats["active_days"]) == (3, 4)


@pytest.mark.asyncio
async def test_stats_split_watched_time_by_tag(db_session, user_id):
    """A tag is credited with every second spent on the videos carrying it."""
    from src.models.tag import Tag, video_tags

    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    mystery = Tag(name="悬疑", color="#7c6cff")
    series = Tag(name="剧集", color="#7c6cff")
    db_session.add_all([mystery, series])
    await db_session.commit()
    await db_session.execute(
        video_tags.insert(),
        [
            {"video_id": 1, "tag_id": mystery.id},
            {"video_id": 1, "tag_id": series.id},
            {"video_id": 2, "tag_id": mystery.id},
        ],
    )
    await db_session.commit()

    await _event(db_session, user_id, 1, 600, days_ago=1)
    await _event(db_session, user_id, 2, 240, days_ago=2)

    stats = await HistoryService(db_session).get_stats(user_id, days=7)

    assert [(tag["name"], tag["seconds"]) for tag in stats["tags"]] == [
        ("悬疑", 840),
        ("剧集", 600),
    ]


@pytest.mark.asyncio
async def test_stats_report_the_calendar_month_on_its_own(db_session, user_id):
    """本月 is the month on the wall, not the last thirty days."""
    from datetime import datetime, timedelta, timezone

    await _create_video(db_session, 1, "暗涌")
    today = datetime.now(timezone.utc)
    last_month_end = (today.replace(day=1) - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    db_session.add(
        WatchEvent(
            user_id=user_id, video_id=1, seconds=5000, occurred_at=last_month_end
        )
    )
    await db_session.commit()
    await _event(db_session, user_id, 1, 600, days_ago=0)

    stats = await HistoryService(db_session).get_stats(user_id, days=30)

    assert stats["month_seconds"] == 600
    assert stats["window_seconds"] == 5600
