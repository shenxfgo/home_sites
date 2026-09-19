"""Tests for HistoryService reads behind the history page and continue rail."""
import pytest

from sqlalchemy import select

from src.models.video import Video
from src.models.history import PlayHistory
from src.services.history_service import HistoryService


async def _watch(session, video_id, progress, completed, played_at):
    """Record one video's single history row at a given position and time."""
    from datetime import datetime, timezone

    session.add(
        PlayHistory(
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
async def test_get_history_paginates_without_losing_the_total(db_session):
    for video_id in (1, 2, 3):
        await _create_video(db_session, video_id, f"视频 {video_id}")
        await _watch(db_session, video_id, 10, False, (2026, 1, video_id))

    service = HistoryService(db_session)

    first_page, total = await service.get_history(page=1, page_size=2)
    assert total == 3
    assert [h.video_id for h in first_page] == [3, 2]

    second_page, total = await service.get_history(page=2, page_size=2)
    assert total == 3
    assert [h.video_id for h in second_page] == [1]


@pytest.mark.asyncio
async def test_continue_list_offers_each_unfinished_video_once(db_session):
    """The rail is the same video the table already lists, never repeated."""
    for video_id in (1, 2, 3):
        await _create_video(db_session, video_id, f"视频 {video_id}")
    await _watch(db_session, 1, 60, False, (2026, 1, 5))
    await _watch(db_session, 2, 118, True, (2026, 1, 4))
    await _watch(db_session, 3, 20, False, (2026, 1, 6))

    service = HistoryService(db_session)
    videos = await service.get_continue_list()

    assert [video.id for video in videos] == [3, 1]

    rows = await db_session.execute(select(PlayHistory))
    assert len(rows.scalars().all()) == 3


@pytest.mark.asyncio
async def test_continue_list_carries_the_position_of_its_own_row(db_session):
    """Each rail video reports where its single history row stopped."""
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    await _watch(db_session, 1, 45, False, (2026, 1, 5))
    await _watch(db_session, 2, 90, False, (2026, 1, 6))

    service = HistoryService(db_session)
    videos = await service.get_continue_list()

    assert [(video.id, video.progress, video.duration) for video in videos] == [
        (2, 90, 120),
        (1, 45, 120),
    ]
