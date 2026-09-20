"""Tests proving two accounts on one library cannot see each other's data.

Every row the household shares is one query away from leaking, so each owned
read is asked here as the wrong person, and each write by id is aimed at somebody
else's row. Together these are the 越权面 list of the auth design.
"""
import pytest
from sqlalchemy import func, select

from src.models.favorite import Favorite
from src.models.history import PlayHistory
from src.models.new_video import NewVideo
from src.models.video import Video
from src.models.watch_event import WatchEvent
from src.services.favorite_service import FavoriteService
from src.services.history_service import HistoryService
from src.services.notification_service import NotificationService
from src.services.video_service import VideoService
from src.services.watchlist_service import WatchlistService


async def _video(session, video_id, title, **columns):
    video = Video(
        id=video_id,
        source_id=1,
        filepath=f"/test/{title}.mp4",
        title=title,
        duration=120,
        **columns,
    )
    session.add(video)
    await session.commit()
    return video


async def _watch(session, user_id, video_id, progress, *, completed=False):
    record = PlayHistory(
        user_id=user_id, video_id=video_id, progress=progress, completed=completed
    )
    session.add(record)
    await session.commit()
    return record


async def _event(session, user_id, video_id, seconds):
    session.add(WatchEvent(user_id=user_id, video_id=video_id, seconds=seconds))
    await session.commit()


@pytest.mark.asyncio
async def test_a_favorite_is_not_in_the_other_account_list(db_session, make_user):
    """Keeping a title is a per-account judgement about the same shared row."""
    alice, bob = await make_user("alice"), await make_user("bob")
    await _video(db_session, 1, "暗涌")
    service = FavoriteService(db_session)

    await service.add_favorite(alice.id, 1)

    assert await service.get_favorites(bob.id) == ([], 0)
    assert await service.is_favorite(bob.id, 1) is False
    assert await service.is_favorite(alice.id, 1) is True
    # Both may keep it: the pair is unique, the title alone is not.
    assert (await service.add_favorite(bob.id, 1)).user_id == bob.id


@pytest.mark.asyncio
async def test_removing_another_account_favorite_leaves_it_in_place(
    db_session, make_user
):
    await _video(db_session, 1, "暗涌")
    alice, bob = await make_user("alice"), await make_user("bob")
    service = FavoriteService(db_session)
    await service.add_favorite(alice.id, 1)

    with pytest.raises(ValueError):
        await service.remove_favorite(bob.id, 1)

    assert await service.is_favorite(alice.id, 1) is True
    assert await db_session.scalar(select(func.count(Favorite.id))) == 1


@pytest.mark.asyncio
async def test_history_and_the_resume_rail_hold_only_the_caller_watching(
    db_session, make_user
):
    await _video(db_session, 1, "暗涌")
    alice, bob = await make_user("alice"), await make_user("bob")
    await _watch(db_session, alice.id, 1, 30)
    service = HistoryService(db_session)

    assert await service.get_history(bob.id) == ([], 0)
    assert await service.get_continue_list(bob.id) == []

    alice_history, total = await service.get_history(alice.id)
    assert (total, [record.video_id for record in alice_history]) == (1, [1])
    assert [video.id for video in await service.get_continue_list(alice.id)] == [1]


@pytest.mark.asyncio
async def test_deleting_another_account_history_row_reads_as_missing(
    db_session, make_user
):
    """The owner is part of the lookup, so a foreign id cannot be deleted."""
    await _video(db_session, 1, "暗涌")
    alice, bob = await make_user("alice"), await make_user("bob")
    record = await _watch(db_session, alice.id, 1, 30)

    with pytest.raises(ValueError):
        await HistoryService(db_session).delete_history(bob.id, record.id)

    assert await db_session.scalar(select(func.count(PlayHistory.id))) == 1


@pytest.mark.asyncio
async def test_watch_stats_add_up_only_the_caller_events(db_session, make_user):
    await _video(db_session, 1, "暗涌")
    alice, bob = await make_user("alice"), await make_user("bob")
    await _event(db_session, alice.id, 1, 600)
    await _event(db_session, bob.id, 1, 60)
    service = HistoryService(db_session)

    alice_stats = await service.get_stats(alice.id, days=7)
    bob_stats = await service.get_stats(bob.id, days=7)

    assert (alice_stats["window_seconds"], bob_stats["window_seconds"]) == (600, 60)
    assert bob_stats["longest_streak_days"] == 1


@pytest.mark.asyncio
async def test_another_account_watchlist_is_not_reachable_by_id(
    db_session, make_user
):
    """Every write path loads through the owner filter, so 越权 becomes 不存在."""
    await _video(db_session, 1, "暗涌")
    await _video(db_session, 2, "长夜")
    alice, bob = await make_user("alice"), await make_user("bob")
    service = WatchlistService(db_session)
    mine = await service.create(alice.id, "今晚看这些")
    await service.add_video(alice.id, mine.id, 1)

    assert await service.list_watchlists(bob.id) == []
    assert await service.get_watchlist(bob.id, mine.id) is None
    with pytest.raises(ValueError):
        await service.add_video(bob.id, mine.id, 2)
    with pytest.raises(ValueError):
        await service.remove_video(bob.id, mine.id, 1)
    with pytest.raises(ValueError):
        await service.update(bob.id, mine.id, name="归我")
    with pytest.raises(ValueError):
        await service.delete(bob.id, mine.id)

    untouched = await service.get_watchlist(alice.id, mine.id)
    assert (untouched.name, [item.video_id for item in untouched.items]) == (
        "今晚看这些",
        [1],
    )


@pytest.mark.asyncio
async def test_two_accounts_may_use_the_same_watchlist_name(db_session, make_user):
    """Names are unique inside one account, which is what ownership makes true."""
    alice, bob = await make_user("alice"), await make_user("bob")
    service = WatchlistService(db_session)

    mine = await service.create(alice.id, "今晚看这些")
    theirs = await service.create(bob.id, "今晚看这些")

    assert mine.id != theirs.id
    assert [entry.name for entry in await service.list_watchlists(alice.id)] == [
        "今晚看这些"
    ]
    assert [entry.id for entry in await service.list_watchlists(bob.id)] == [theirs.id]


@pytest.mark.asyncio
async def test_a_progress_report_moves_only_the_caller_row(db_session, make_user):
    await _video(db_session, 1, "暗涌")
    alice, bob = await make_user("alice"), await make_user("bob")
    service = VideoService(db_session)

    await service.update_progress(alice.id, 1, 90)
    await service.update_progress(bob.id, 1, 10)

    rows = await db_session.execute(select(PlayHistory).order_by(PlayHistory.user_id))
    assert [(r.user_id, r.progress) for r in rows.scalars()] == [
        (alice.id, 90),
        (bob.id, 10),
    ]
    videos, _ = await service.get_videos(alice.id)
    assert videos[0].progress == 90
    assert (await service.get_video_by_id(1, bob.id)).progress == 10


@pytest.mark.asyncio
async def test_the_watch_state_operators_answer_for_the_caller(db_session, make_user):
    """"看完了" means this person finished it, not somebody else in the house."""
    await _video(db_session, 1, "暗涌")
    alice, bob = await make_user("alice"), await make_user("bob")
    service = VideoService(db_session)
    await service.update_progress(alice.id, 1, 120)

    assert [v.title for v in (await service.get_videos(alice.id, search="已看完"))[0]] == [
        "暗涌"
    ]
    assert (await service.get_videos(bob.id, search="已看完"))[1] == 0
    assert [v.title for v in (await service.get_videos(bob.id, search="没看过"))[0]] == [
        "暗涌"
    ]


@pytest.mark.asyncio
async def test_series_progress_counts_the_caller_finished_episodes(db_session, make_user):
    await _video(db_session, 1, "暗涌 EP01", series="暗涌", season=1, episode=1)
    await _video(db_session, 2, "暗涌 EP02", series="暗涌", season=1, episode=2)
    alice, bob = await make_user("alice"), await make_user("bob")
    service = VideoService(db_session)
    await service.update_progress(alice.id, 1, 120)

    alice_entry = (await service.get_series_progress(alice.id))[0]
    bob_entry = (await service.get_series_progress(bob.id))[0]

    assert (alice_entry["total"], alice_entry["finished"]) == (2, 1)
    assert (bob_entry["total"], bob_entry["finished"]) == (2, 0)
    assert (alice_entry["next"].id, bob_entry["next"].id) == (2, 1)


@pytest.mark.asyncio
async def test_clearing_the_new_badge_leaves_it_on_for_everyone_else(
    db_session, make_user
):
    """A scan record is shared; having seen it is not."""
    video = await _video(db_session, 1, "暗涌")
    db_session.add(NewVideo(video_id=video.id, source_id=1))
    await db_session.commit()
    alice, bob = await make_user("alice"), await make_user("bob")
    service = VideoService(db_session)

    await service.mark_video_viewed(alice.id, video.id)

    assert [v.id for v in await service.get_new_videos(alice.id)] == []
    assert [v.id for v in await service.get_new_videos(bob.id)] == [video.id]
    assert (await service.get_videos(bob.id))[0][0].is_new is True
    assert (await service.get_videos(alice.id))[0][0].is_new is False


@pytest.mark.asyncio
async def test_marking_a_notification_read_is_each_person_own(
    db_session, make_user
):
    alice, bob = await make_user("alice"), await make_user("bob")
    note = await NotificationService(db_session).create(
        "scan_complete", "扫描完成", "新增 3 部"
    )
    service = NotificationService(db_session)

    await service.mark_read(alice.id, note.id)

    assert (await service.get_unread_count(alice.id)) == 0
    assert (await service.get_unread_count(bob.id)) == 1
    assert (await service.get_notifications(bob.id))[0][0].read is False


@pytest.mark.asyncio
async def test_deleting_a_notification_takes_it_from_the_whole_household(
    db_session, make_user
):
    """The feed is broadcast and has no owner column, so a delete is shared by design.

    There is no per-person row for a foreign id to reach, which is why the
    notification delete route is role-gated rather than ownership-scoped.
    """
    alice, bob = await make_user("alice"), await make_user("bob")
    note = await NotificationService(db_session).create(
        "scan_complete", "扫描完成", "新增 3 部"
    )
    service = NotificationService(db_session)

    await service.delete_notification(note.id)

    assert await service.get_notifications(alice.id) == ([], 0)
    assert await service.get_notifications(bob.id) == ([], 0)
