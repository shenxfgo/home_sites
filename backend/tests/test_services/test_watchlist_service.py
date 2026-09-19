"""Tests for WatchlistService behind the 片单 feature."""
import pytest

from sqlalchemy import func, select

from src.models.video import Video
from src.models.watchlist import Watchlist, WatchlistItem
from src.services.video_service import delete_videos_cascade
from src.services.watchlist_service import WatchlistService


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
async def test_a_new_watchlist_starts_empty(db_session):
    watchlist = await WatchlistService(db_session).create("今晚看这些", "睡前各看一集")
    await db_session.refresh(watchlist)

    assert (watchlist.name, watchlist.description, watchlist.items) == (
        "今晚看这些",
        "睡前各看一集",
        [],
    )


@pytest.mark.asyncio
async def test_titles_stay_in_the_order_they_were_added(db_session):
    """The queue order is the watching order, so it must not shuffle."""
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    service = WatchlistService(db_session)
    watchlist = await service.create("今晚看这些")

    watchlist = await service.add_video(watchlist.id, 2)
    watchlist = await service.add_video(watchlist.id, 1)

    assert [item.video.title for item in watchlist.items] == ["长夜", "暗涌"]


@pytest.mark.asyncio
async def test_adding_a_title_twice_keeps_one_row(db_session):
    """The picker can be clicked twice; the queue should not hold a duplicate."""
    await _create_video(db_session, 1, "暗涌")
    service = WatchlistService(db_session)
    watchlist = await service.create("今晚看这些")

    await service.add_video(watchlist.id, 1)
    again = await service.add_video(watchlist.id, 1)

    assert len(again.items) == 1


@pytest.mark.asyncio
async def test_removing_a_title_leaves_the_library_alone(db_session):
    await _create_video(db_session, 1, "暗涌")
    service = WatchlistService(db_session)
    watchlist = await service.create("今晚看这些")
    await service.add_video(watchlist.id, 1)

    emptied = await service.remove_video(watchlist.id, 1)

    assert emptied.items == []
    assert await db_session.scalar(select(func.count(Video.id))) == 1


@pytest.mark.asyncio
async def test_deleting_a_watchlist_keeps_the_videos(db_session):
    """Throwing away the list must never throw away the titles in it."""
    await _create_video(db_session, 1, "暗涌")
    service = WatchlistService(db_session)
    watchlist = await service.create("今晚看这些")
    await service.add_video(watchlist.id, 1)

    await service.delete(watchlist.id)

    assert await db_session.scalar(select(func.count(Watchlist.id))) == 0
    assert await db_session.scalar(select(func.count(WatchlistItem.id))) == 0
    assert await db_session.scalar(select(func.count(Video.id))) == 1


@pytest.mark.asyncio
async def test_filtering_by_video_returns_only_the_lists_holding_it(db_session):
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    service = WatchlistService(db_session)
    tonight = await service.create("今晚看这些")
    someday = await service.create("以后再说")
    await service.add_video(tonight.id, 1)
    await service.add_video(someday.id, 1)
    await service.add_video(someday.id, 2)

    holding_first = await service.list_watchlists(video_id=1)
    holding_third = await service.list_watchlists(video_id=2)

    assert [watchlist.name for watchlist in holding_first] == ["今晚看这些", "以后再说"]
    assert [watchlist.name for watchlist in holding_third] == ["以后再说"]
    assert len(await service.list_watchlists()) == 2


@pytest.mark.asyncio
async def test_renaming_a_watchlist_keeps_its_queue(db_session):
    await _create_video(db_session, 1, "暗涌")
    service = WatchlistService(db_session)
    watchlist = await service.create("今晚看这些")
    await service.add_video(watchlist.id, 1)

    renamed = await service.update(watchlist.id, name="明晚再看")

    assert renamed.name == "明晚再看"
    assert renamed.description is None
    assert len(renamed.items) == 1


@pytest.mark.asyncio
async def test_an_unknown_title_or_list_is_an_error(db_session):
    """The API turns these into 404s, so they must not pass silently."""
    await _create_video(db_session, 1, "暗涌")
    service = WatchlistService(db_session)
    watchlist = await service.create("今晚看这些")

    with pytest.raises(ValueError):
        await service.add_video(watchlist.id, 999)
    with pytest.raises(ValueError):
        await service.add_video(999, 1)
    with pytest.raises(ValueError):
        await service.update(999, name="无关")
    with pytest.raises(ValueError):
        await service.delete(999)


@pytest.mark.asyncio
async def test_deleting_a_video_clears_it_from_every_list(db_session):
    """A title leaves the queue when it leaves the library, with no orphan rows."""
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    service = WatchlistService(db_session)
    watchlist = await service.create("今晚看这些")
    await service.add_video(watchlist.id, 1)
    await service.add_video(watchlist.id, 2)

    await delete_videos_cascade(db_session, Video.id == 1)
    await db_session.commit()

    remaining = await service.get_watchlist(watchlist.id)
    assert [item.video_id for item in remaining.items] == [2]
