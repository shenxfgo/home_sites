"""Tests for VideoService operations."""

import logging

import pytest
from sqlalchemy import func, select

from src.models.history import PlayHistory
from src.models.new_video import NewVideo
from src.models.tag import Tag
from src.models.video import Video
from src.services.video_service import VideoService, is_completed
from tests.support import ensure_source


async def _create_video(
    session,
    source_id=1,
    title="Test Video",
    filepath="/test/video.mp4",
    duration=120,
    file_size=1024000,
):
    """Helper to create a video directly in the database."""
    # SQLite 出厂不查外键，所以这里过去可以直接写 source_id=1；PostgreSQL 会拒绝
    # 没有父行的影片，父行得真的建出来。
    await ensure_source(session, source_id)
    video = Video(
        source_id=source_id,
        filepath=filepath,
        title=title,
        duration=duration,
        file_size=file_size,
        format="mp4",
        resolution="1920x1080",
    )
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return video


@pytest.mark.asyncio
async def test_delete_video_removes_dependent_rows(db_session, user_id):
    """级联清单不指望数据库替它删：PG 会、SQLite 不会，两边都得由服务说同一句话。"""
    from sqlalchemy import func, select

    from src.models.favorite import Favorite
    from src.models.new_video import NewVideo
    from src.models.read_state import NewVideoRead
    from src.models.tag import Tag, video_tags

    video = await _create_video(db_session, title="Doomed", filepath="/d.mp4")
    tag = Tag(name="恐怖")
    db_session.add(tag)
    await db_session.commit()

    new_video = NewVideo(video_id=video.id, source_id=video.source_id)
    db_session.add_all(
        [
            Favorite(user_id=user_id, video_id=video.id),
            new_video,
            PlayHistory(user_id=user_id, video_id=video.id, progress=10),
        ]
    )
    await db_session.commit()
    db_session.add(NewVideoRead(new_video_id=new_video.id, user_id=user_id))
    await db_session.execute(
        video_tags.insert().values(video_id=video.id, tag_id=tag.id)
    )
    await db_session.commit()

    service = VideoService(db_session)
    await service.delete_video(video.id)

    async def count(model):
        result = await db_session.execute(select(func.count()).select_from(model))
        return result.scalar()

    assert await count(Video) == 0
    assert await count(Favorite) == 0
    assert await count(NewVideo) == 0
    assert await count(PlayHistory) == 0
    assert await count(video_tags) == 0
    # The read rows hang off new_videos, so they are the deepest orphan.
    assert await count(NewVideoRead) == 0


@pytest.mark.asyncio
async def test_get_videos_empty(db_session, user_id):
    """Test getting videos from empty database."""
    service = VideoService(db_session)
    videos, total = await service.get_videos(user_id)

    assert videos == []
    assert total == 0


@pytest.mark.asyncio
async def test_get_videos_with_data(db_session, user_id):
    """Test getting videos returns correct data."""
    await _create_video(db_session, title="Video 1", filepath="/v1.mp4")
    await _create_video(db_session, title="Video 2", filepath="/v2.mp4")
    await _create_video(db_session, title="Video 3", filepath="/v3.mp4")

    service = VideoService(db_session)
    videos, total = await service.get_videos(user_id)

    assert total == 3
    assert len(videos) == 3


@pytest.mark.asyncio
async def test_get_videos_filter_by_source(db_session, user_id):
    """Test filtering videos by source_id."""
    await _create_video(db_session, source_id=1, filepath="/s1/v1.mp4")
    await _create_video(db_session, source_id=1, filepath="/s1/v2.mp4")
    await _create_video(db_session, source_id=2, filepath="/s2/v1.mp4")

    service = VideoService(db_session)
    videos, total = await service.get_videos(user_id, source_id=1)

    assert total == 2
    assert all(v.source_id == 1 for v in videos)


@pytest.mark.asyncio
async def test_get_videos_filter_by_tag(db_session, user_id):
    """Test filtering videos by tag_id."""
    tag = Tag(name="action", color="#ff0000")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    video1 = await _create_video(db_session, title="Action Movie", filepath="/a.mp4")
    await _create_video(db_session, title="Comedy", filepath="/c.mp4")

    video1.tags.append(tag)
    await db_session.commit()

    service = VideoService(db_session)
    videos, total = await service.get_videos(user_id, tag_id=tag.id)

    assert total == 1
    assert videos[0].title == "Action Movie"


@pytest.mark.asyncio
async def test_get_videos_search(db_session, user_id):
    """Test searching videos by title."""
    await _create_video(db_session, title="The Matrix", filepath="/m.mp4")
    await _create_video(db_session, title="Inception", filepath="/i.mp4")
    await _create_video(db_session, title="Matrix Reloaded", filepath="/mr.mp4")

    service = VideoService(db_session)
    videos, total = await service.get_videos(user_id, search="matrix")

    assert total == 2
    assert all("matrix" in v.title.lower() for v in videos)


@pytest.mark.asyncio
async def test_search_for_lost_files_returns_only_missing_rows(db_session, user_id):
    """The 丢失 keyword is the whole library's window onto lost records."""
    kept = await _create_video(db_session, title="还在", filepath="/keep.mp4")
    lost = await _create_video(db_session, title="没了", filepath="/gone.mp4")
    lost.is_missing = True
    await db_session.commit()

    service = VideoService(db_session)
    videos, total = await service.get_videos(user_id, search="丢失")

    assert total == 1
    assert [video.id for video in videos] == [lost.id]
    assert videos[0].is_missing is True
    assert kept.is_missing is False


@pytest.mark.asyncio
async def test_get_videos_pagination(db_session, user_id):
    """Test pagination of videos."""
    for i in range(25):
        await _create_video(db_session, title=f"Video {i}", filepath=f"/v{i}.mp4")

    service = VideoService(db_session)

    # First page
    videos, total = await service.get_videos(user_id, page=1, page_size=10)
    assert total == 25
    assert len(videos) == 10

    # Second page
    videos, total = await service.get_videos(user_id, page=2, page_size=10)
    assert total == 25
    assert len(videos) == 10

    # Third page (partial)
    videos, total = await service.get_videos(user_id, page=3, page_size=10)
    assert total == 25
    assert len(videos) == 5


@pytest.mark.asyncio
async def test_get_video_by_id(db_session, user_id):
    """Test getting a specific video by ID."""
    created = await _create_video(db_session)

    service = VideoService(db_session)
    video = await service.get_video_by_id(created.id, user_id)

    assert video is not None
    assert video.id == created.id
    assert video.title == "Test Video"


@pytest.mark.asyncio
async def test_get_video_by_id_not_found(db_session, user_id):
    """Test getting a video that doesn't exist."""
    service = VideoService(db_session)
    video = await service.get_video_by_id(99999, user_id)

    assert video is None


@pytest.mark.asyncio
async def test_update_video(db_session, user_id):
    """Test updating video metadata."""
    created = await _create_video(db_session)

    service = VideoService(db_session)
    updated = await service.update_video(created.id, user_id, title="Updated Title", rating=5)

    assert updated.title == "Updated Title"
    assert updated.rating == 5
    assert updated.filepath == created.filepath  # unchanged


@pytest.mark.asyncio
async def test_update_video_not_found(db_session, user_id):
    """Test updating a video that doesn't exist."""
    service = VideoService(db_session)

    with pytest.raises(ValueError, match="Video with id 99999 not found"):
        await service.update_video(99999, user_id, title="test")


@pytest.mark.asyncio
async def test_delete_video(db_session, user_id):
    """Test deleting a video."""
    created = await _create_video(db_session)

    service = VideoService(db_session)
    await service.delete_video(created.id)

    video = await service.get_video_by_id(created.id, user_id)
    assert video is None


@pytest.mark.asyncio
async def test_delete_video_not_found(db_session, user_id):
    """Test deleting a video that doesn't exist."""
    service = VideoService(db_session)

    with pytest.raises(ValueError, match="Video with id 99999 not found"):
        await service.delete_video(99999)


@pytest.mark.asyncio
async def test_get_new_videos(db_session, user_id):
    """Test getting newly discovered videos."""
    video1 = await _create_video(db_session, title="New 1", filepath="/n1.mp4")
    video2 = await _create_video(db_session, title="New 2", filepath="/n2.mp4")
    await _create_video(db_session, title="Old", filepath="/o.mp4")

    # Mark video1 and video2 as new
    nv1 = NewVideo(video_id=video1.id, source_id=1)
    nv2 = NewVideo(video_id=video2.id, source_id=1)
    db_session.add_all([nv1, nv2])
    await db_session.commit()

    service = VideoService(db_session)
    new_videos = await service.get_new_videos(user_id)

    assert len(new_videos) == 2
    titles = {v.title for v in new_videos}
    assert "New 1" in titles
    assert "New 2" in titles


@pytest.mark.asyncio
async def test_get_new_videos_filter_by_source(db_session, user_id):
    """Test filtering new videos by source."""
    video1 = await _create_video(db_session, source_id=1, filepath="/s1.mp4")
    video2 = await _create_video(db_session, source_id=2, filepath="/s2.mp4")

    nv1 = NewVideo(video_id=video1.id, source_id=1)
    nv2 = NewVideo(video_id=video2.id, source_id=2)
    db_session.add_all([nv1, nv2])
    await db_session.commit()

    service = VideoService(db_session)
    new_videos = await service.get_new_videos(user_id, source_id=1)

    assert len(new_videos) == 1
    assert new_videos[0].source_id == 1


@pytest.mark.asyncio
async def test_mark_video_viewed(db_session, user_id):
    """Test marking a new video as viewed for one account."""
    from src.models.read_state import NewVideoRead

    video = await _create_video(db_session)
    nv = NewVideo(video_id=video.id, source_id=1)
    db_session.add(nv)
    await db_session.commit()

    service = VideoService(db_session)
    await service.mark_video_viewed(user_id, video.id)

    # The scan record stays for the rest of the household; only the read row is
    # this account's.
    assert await db_session.get(NewVideoRead, (nv.id, user_id)) is not None


@pytest.mark.asyncio
async def test_record_play(db_session, user_id):
    """Test recording a play event."""
    video = await _create_video(db_session)
    assert video.view_count == 0

    service = VideoService(db_session)
    await service.record_play(user_id, video.id)

    await db_session.refresh(video)
    assert video.view_count == 1
    assert video.last_played_at is not None

    # Record another play
    await service.record_play(user_id, video.id)
    await db_session.refresh(video)
    assert video.view_count == 2


@pytest.mark.asyncio
async def test_record_play_not_found(db_session, user_id):
    """Test recording play for non-existent video."""
    service = VideoService(db_session)

    with pytest.raises(ValueError, match="Video with id 99999 not found"):
        await service.record_play(user_id, 99999)


@pytest.mark.asyncio
async def test_update_progress(db_session, user_id):
    """Test updating playback progress."""
    video = await _create_video(db_session, duration=120)

    # First record a play
    service = VideoService(db_session)
    await service.record_play(user_id, video.id)

    # Update progress
    await service.update_progress(user_id, video.id, 60)

    # Check history
    from sqlalchemy import select
    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    history = result.scalar_one()
    assert history.progress == 60
    assert history.completed is False


@pytest.mark.asyncio
async def test_update_progress_completed(db_session, user_id):
    """Test that progress near end marks as completed."""
    video = await _create_video(db_session, duration=120)

    service = VideoService(db_session)
    await service.record_play(user_id, video.id)

    # Progress within 10 seconds of end
    await service.update_progress(user_id, video.id, 115)

    from sqlalchemy import select
    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    history = result.scalar_one()
    assert history.completed is True


@pytest.mark.asyncio
async def test_record_play_keeps_one_history_row_per_video(db_session, user_id):
    """Replaying refreshes the existing row rather than stacking a second one."""
    video = await _create_video(db_session)
    service = VideoService(db_session)

    await service.record_play(user_id, video.id)
    await service.update_progress(user_id, video.id, 45)
    await service.record_play(user_id, video.id)

    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    history = result.scalar_one()
    assert history.progress == 0
    assert history.completed is False


@pytest.mark.asyncio
async def test_record_play_clears_the_new_badge(db_session, user_id, make_user):
    """Watching a video is what retires its 新 label, for the watcher only."""
    from src.models.read_state import NewVideoRead

    other_id = (await make_user("other-viewer")).id
    video = await _create_video(db_session)
    db_session.add(NewVideo(video_id=video.id, source_id=video.source_id))
    await db_session.commit()

    service = VideoService(db_session)
    videos, _ = await service.get_videos(user_id)
    assert videos[0].is_new is True

    await service.record_play(user_id, video.id)

    videos, _ = await service.get_videos(user_id)
    assert videos[0].is_new is False
    # The other account watched nothing, so its badge is still up.
    other_videos, _ = await service.get_videos(other_id)
    assert other_videos[0].is_new is True
    assert await db_session.scalar(
        select(func.count()).select_from(NewVideoRead)
    ) == 1


@pytest.mark.asyncio
async def test_videos_without_a_scan_record_are_not_new(db_session, user_id):
    """Only the scan queue decides the badge, so a fresh file is not automatically 新."""
    await _create_video(db_session)

    service = VideoService(db_session)
    videos, _ = await service.get_videos(user_id)
    assert videos[0].is_new is False


@pytest.mark.asyncio
async def test_update_progress_reopens_a_finished_video(db_session, user_id):
    """Rewinding out of the tail takes the video back into continue watching."""
    video = await _create_video(db_session, duration=120)
    service = VideoService(db_session)
    await service.record_play(user_id, video.id)

    await service.update_progress(user_id, video.id, 118)
    await service.update_progress(user_id, video.id, 30)

    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    history = result.scalar_one()
    assert history.completed is False


def test_is_completed_tolerates_only_a_short_tail():
    """The tolerance is a capped share of the title, not a fixed ten seconds."""
    assert is_completed(114, 120)
    assert not is_completed(110, 120)
    assert is_completed(3591, 3600)
    assert not is_completed(3400, 3600)
    assert not is_completed(30, None)


@pytest.mark.asyncio
async def test_update_progress_refreshes_played_at(db_session, user_id):
    """最后观看 means the last actual watch, not the moment the session started."""
    video = await _create_video(db_session)
    service = VideoService(db_session)
    await service.record_play(user_id, video.id)

    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    started_at = result.scalar_one().played_at

    await service.update_progress(user_id, video.id, 10)

    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    assert result.scalar_one().played_at > started_at


def _write_copy(tmp_path, name: str, payload: bytes) -> str:
    """Write a stand-in media file and return the path the library would store."""
    path = tmp_path / name
    path.write_bytes(payload)
    return str(path)


@pytest.mark.asyncio
async def test_duplicates_only_report_identical_bytes(db_session, user_id, tmp_path):
    """Same size and duration is a hint; the file contents decide."""
    payload = b"the same episode twice" * 64
    first = await _create_video(
        db_session,
        title="暗涌 EP01",
        filepath=_write_copy(tmp_path, "copy1.mkv", payload),
        duration=100,
        file_size=len(payload),
    )
    second = await _create_video(
        db_session,
        title="暗涌 EP01 (字幕组A)",
        filepath=_write_copy(tmp_path, "copy2.mkv", payload),
        duration=100,
        file_size=len(payload),
    )
    other = await _create_video(
        db_session,
        title="暗涌 EP02",
        filepath=_write_copy(tmp_path, "other.mkv", b"z" * len(payload)),
        duration=100,
        file_size=len(payload),
    )

    groups = await VideoService(db_session).get_duplicates(user_id)

    assert len(groups) == 1
    group = groups[0]
    assert [v.id for v in group["items"]] == [first.id, second.id]
    assert (group["count"], group["wasted_bytes"], group["keep_id"]) == (
        2,
        len(payload),
        first.id,
    )
    assert other.id not in [v.id for v in group["items"]]


@pytest.mark.asyncio
async def test_duplicates_ignore_a_lone_file(db_session, user_id, tmp_path):
    """Nothing is a duplicate until a second copy shares its size."""
    payload = b"one and only" * 64
    await _create_video(
        db_session,
        filepath=_write_copy(tmp_path, "only.mkv", payload),
        file_size=len(payload),
    )

    assert await VideoService(db_session).get_duplicates(user_id) == []


@pytest.mark.asyncio
async def test_duplicates_skip_rows_whose_file_cannot_be_read(db_session, user_id):
    """A share that will not open must not be called a copy of anything."""
    await _create_video(db_session, title="在 NAS 上", filepath="/nas/a.mkv")
    await _create_video(db_session, title="也在 NAS 上", filepath="/nas/b.mkv")

    assert await VideoService(db_session).get_duplicates(user_id) == []


@pytest.mark.asyncio
async def test_duplicates_keep_the_copy_that_has_been_watched(db_session, user_id, tmp_path):
    """The record with the watch history is the one worth not deleting."""
    payload = b"watched copy" * 64
    fresh = await _create_video(
        db_session,
        title="暗涌 EP03",
        filepath=_write_copy(tmp_path, "fresh.mkv", payload),
        duration=100,
        file_size=len(payload),
    )
    watched = await _create_video(
        db_session,
        title="暗涌 EP03 备份",
        filepath=_write_copy(tmp_path, "backup.mkv", payload),
        duration=100,
        file_size=len(payload),
    )
    await VideoService(db_session).update_progress(user_id, watched.id, 60)

    group = (await VideoService(db_session).get_duplicates(user_id))[0]

    assert group["keep_id"] == watched.id
    assert [v.id for v in group["items"]] == [watched.id, fresh.id]
    assert group["items"][0].progress == 60


@pytest.mark.asyncio
async def test_progress_forward_moves_append_watch_events(db_session, user_id):
    """How much was watched comes from the seconds a report advanced by."""
    from src.models.watch_event import WatchEvent

    video = await _create_video(db_session, duration=120)
    service = VideoService(db_session)

    await service.update_progress(user_id, video.id, 30)
    await service.update_progress(user_id, video.id, 60)

    result = await db_session.execute(
        select(WatchEvent).where(WatchEvent.video_id == video.id).order_by(WatchEvent.id)
    )
    assert [event.seconds for event in result.scalars().all()] == [30, 30]


@pytest.mark.asyncio
async def test_seeking_backwards_adds_nothing_to_the_log(db_session, user_id):
    """A rewind is not negative watching, and a repeat is not more of it."""
    from sqlalchemy import func

    from src.models.watch_event import WatchEvent

    video = await _create_video(db_session, duration=120)
    service = VideoService(db_session)
    await service.update_progress(user_id, video.id, 90)

    await service.update_progress(user_id, video.id, 20)

    result = await db_session.execute(
        select(func.count(WatchEvent.id)).where(WatchEvent.video_id == video.id)
    )
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_deleting_a_video_takes_its_watch_events_with_it(db_session, user_id):
    """The cascade list must grow with the table, or the log keeps ghost rows."""
    from sqlalchemy import func

    from src.models.watch_event import WatchEvent

    video = await _create_video(db_session, title="删除我", filepath="/del.mp4")
    service = VideoService(db_session)
    await service.update_progress(user_id, video.id, 45)

    await service.delete_video(video.id)

    result = await db_session.execute(select(func.count(WatchEvent.id)))
    assert result.scalar_one() == 0


# --- 删除影片时，应用自己生成的封面也要跟着走 ---


@pytest.mark.asyncio
async def test_delete_video_removes_its_cover_but_never_the_media(db_session, tmp_path):
    """封面是应用生成的产物，删记录就该删掉；影片文件属于用户，绝不能碰。"""
    from src.services.video_service import VideoService

    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"\xff\xd8jpeg")
    media = tmp_path / "深夜测试.mp4"
    media.write_bytes(b"not really a video")

    video = await _create_video(db_session, filepath=str(media))
    video.thumbnail_path = str(cover)
    await db_session.commit()

    await VideoService(db_session).delete_video(video.id)

    assert not cover.exists()
    assert media.exists()


@pytest.mark.asyncio
async def test_cascade_only_reports_covers_so_a_rollback_keeps_them(db_session, tmp_path):
    """删除文件必须排在提交之后：级联函数只报出该删谁，回滚不该把封面弄丢。"""
    from src.services.video_service import delete_videos_cascade

    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"x")
    video = await _create_video(db_session, filepath="/v.mp4")
    video.thumbnail_path = str(cover)
    await db_session.commit()

    paths = await delete_videos_cascade(db_session, Video.id == video.id)

    assert paths == [str(cover)]
    assert cover.exists()


@pytest.mark.asyncio
async def test_delete_video_tolerates_dead_or_legacy_cover_paths(db_session, tmp_path):
    """老行的 thumbnail_path 可能写着已经不存在的文件，甚至带 ./ 前缀和混用分隔符。"""
    from src.services.video_service import VideoService

    vanished = tmp_path / "already-gone.jpg"
    gone = await _create_video(db_session, title="图没了", filepath="/a.mp4")
    gone.thumbnail_path = str(vanished)
    legacy = await _create_video(db_session, title="老写法", filepath="/b.mp4")
    legacy.thumbnail_path = "./data/thumbnails\\5\\sample_1.jpg"
    blank = await _create_video(db_session, title="没封面", filepath="/c.mp4")
    await db_session.commit()

    for video_id in (gone.id, legacy.id, blank.id):
        await VideoService(db_session).delete_video(video_id)

    for video_id in (gone.id, legacy.id, blank.id):
        assert await db_session.get(Video, video_id) is None


def test_the_explicit_cascade_list_is_every_child_of_videos():
    """清单靠人维护，模型里的外键靠机器声明：新增一张挂 videos.id 的表漏进清单要能红。

    两种方言的失败方向是相反的——PG 认 ON DELETE CASCADE，会替你把子行删掉；SQLite
    不查外键，静默留孤儿行。所以这份清单得是全集，不能是"用例恰好写到的那几张"。
    """
    from src.database.base import Base
    from src.services.video_service import VIDEO_CHILD_TABLES

    declared = {
        table.name
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.target_fullname == "videos.id"
    }
    listed = {table.name for table in VIDEO_CHILD_TABLES}

    assert declared == listed


# --- 读取预算、攥在手里删不掉的封面、报给一条已经不存在的影片 ---


def _counted_fingerprints(monkeypatch) -> list[str]:
    """把指纹口子换成一个记账的包装：照样真算，只是顺便记下读了哪些文件。

    预算这件事在返回值里看不出来——读满和读不完都回一样的形状，所以只能量"到底读了几趟"。
    """
    from src.services import video_service as video_service_module

    seen: list[str] = []
    real = video_service_module.fingerprint

    def counting(locator: str) -> str | None:
        seen.append(locator)
        return real(locator)

    monkeypatch.setattr(video_service_module, "fingerprint", counting)
    return seen


async def _seed_copies(
    db_session, directory, *, prefix: str, count: int, size: int, duration: int
) -> list[Video]:
    """一次建出 ``count`` 行同尺寸同时长的影片，每行对应磁盘上一个字节相同的小文件。"""
    await ensure_source(db_session, 1)
    payload = b"duplicate probe payload, the same bytes every time" * 4
    rows: list[Video] = []
    for index in range(count):
        path = directory / f"{prefix}-{index}.mkv"
        path.write_bytes(payload)
        rows.append(
            Video(
                source_id=1,
                filepath=str(path),
                title=f"{prefix}{index}",
                duration=duration,
                file_size=size,
                format="mkv",
            )
        )
    db_session.add_all(rows)
    await db_session.commit()
    return rows


@pytest.mark.asyncio
async def test_the_read_budget_is_spent_on_the_group_worth_the_most_first(
    db_session, user_id, tmp_path, monkeypatch
):
    """一轮只读得起 300 趟：先给最能腾出空间的那一组，第二组装不下就一个字节都不碰。"""
    from src.services.video_service import _DUPLICATE_PROBE_MAX

    seen = _counted_fingerprints(monkeypatch)
    big = await _seed_copies(
        db_session, tmp_path, prefix="大组", count=200, size=1_000_000, duration=10
    )
    # 预算被大组花掉之后只剩 100 趟，第二组比它多一行，就装不下了。
    await _seed_copies(
        db_session,
        tmp_path,
        prefix="小组",
        count=_DUPLICATE_PROBE_MAX - 200 + 50,
        size=900_000,
        duration=10,
    )

    groups = await VideoService(db_session).get_duplicates(user_id)

    assert [group["count"] for group in groups] == [200]
    assert {video.id for video in groups[0]["items"]} == {video.id for video in big}
    assert len(seen) == 200
    assert all("小组" not in path for path in seen)


@pytest.mark.asyncio
async def test_a_group_one_row_over_the_budget_is_left_wholly_unread(
    db_session, user_id, tmp_path, monkeypatch
):
    """装不下一整组就不读半组：宁可这一轮什么都不报，也不给只读了一半的判断。"""
    from src.services.video_service import _DUPLICATE_PROBE_MAX

    seen = _counted_fingerprints(monkeypatch)
    await _seed_copies(
        db_session,
        tmp_path,
        prefix="超预算",
        count=_DUPLICATE_PROBE_MAX + 1,
        size=1_000_000,
        duration=10,
    )

    assert await VideoService(db_session).get_duplicates(user_id) == []
    assert seen == []


@pytest.mark.asyncio
async def test_a_group_exactly_at_the_budget_is_still_read(
    db_session, user_id, tmp_path, monkeypatch
):
    """边界是"超过"不是"达到"：正好把预算花光的那一组要读完，也要报出来。"""
    from src.services.video_service import _DUPLICATE_PROBE_MAX

    seen = _counted_fingerprints(monkeypatch)
    await _seed_copies(
        db_session,
        tmp_path,
        prefix="刚好",
        count=_DUPLICATE_PROBE_MAX,
        size=1_000_000,
        duration=10,
    )

    groups = await VideoService(db_session).get_duplicates(user_id)

    assert [group["count"] for group in groups] == [_DUPLICATE_PROBE_MAX]
    assert groups[0]["wasted_bytes"] == 1_000_000 * (_DUPLICATE_PROBE_MAX - 1)
    assert len(seen) == _DUPLICATE_PROBE_MAX


@pytest.mark.asyncio
async def test_a_row_that_is_alone_at_its_size_is_never_hashed(
    db_session, user_id, tmp_path, monkeypatch
):
    """同尺寸同时长才值得再读一趟磁盘：形单影只的那一行连指纹都不配算。"""
    seen = _counted_fingerprints(monkeypatch)
    pair = await _seed_copies(
        db_session, tmp_path, prefix="成对", count=2, size=1_000_000, duration=10
    )
    lone = await _seed_copies(
        db_session, tmp_path, prefix="独苗", count=1, size=1_000_000, duration=999
    )

    groups = await VideoService(db_session).get_duplicates(user_id)

    assert [group["count"] for group in groups] == [2]
    assert {video.id for video in groups[0]["items"]} == {video.id for video in pair}
    assert len(seen) == 2
    assert lone[0].filepath not in seen


@pytest.mark.asyncio
async def test_a_cover_the_disk_will_not_release_is_logged_and_kept(db_session, tmp_path, caplog):
    """封面被别的句柄攥着时（浏览器还在读它），删影片不该替磁盘兜下这个错。"""
    cover = tmp_path / "攥着的.jpg"
    cover.write_bytes(b"\xff\xd8locked")
    media = tmp_path / "片子.mp4"
    media.write_bytes(b"not really a video")

    video = await _create_video(db_session, title="封面删不掉", filepath=str(media))
    video.thumbnail_path = str(cover)
    await db_session.commit()

    handle = open(cover, "rb")
    try:
        with caplog.at_level(logging.WARNING, logger="src.services.video_service"):
            await VideoService(db_session).delete_video(video.id)
    finally:
        handle.close()

    assert await db_session.get(Video, video.id) is None
    assert cover.exists()
    assert media.exists()
    ours = [r for r in caplog.records if r.name == "src.services.video_service"]
    assert len(ours) == 1
    assert str(cover) in ours[0].getMessage()
    assert ours[0].exc_info is not None


@pytest.mark.asyncio
async def test_a_cover_that_was_never_written_leaves_no_word(db_session, tmp_path, caplog):
    """从来没有过的路径不是一次失败：老行还写着 ./data/... 那种前缀，一句都不该抱怨。"""
    video = await _create_video(db_session, title="没写过封面", filepath="/v.mp4")
    video.thumbnail_path = str(tmp_path / "从来没有过.jpg")
    await db_session.commit()

    with caplog.at_level(logging.WARNING, logger="src.services.video_service"):
        await VideoService(db_session).delete_video(video.id)

    assert [r for r in caplog.records if r.name == "src.services.video_service"] == []


@pytest.mark.asyncio
async def test_a_progress_report_for_a_video_that_is_gone_writes_nothing(db_session, user_id):
    """片子在播放途中被人删了：这趟上报既不该建历史行，也不该记一条观看事件。"""
    from src.models.watch_event import WatchEvent

    await VideoService(db_session).update_progress(user_id, 999_999, 60)

    history_rows = await db_session.execute(select(func.count()).select_from(PlayHistory))
    event_rows = await db_session.execute(select(func.count()).select_from(WatchEvent))
    assert history_rows.scalar_one() == 0
    assert event_rows.scalar_one() == 0
