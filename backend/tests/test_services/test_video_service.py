"""Tests for VideoService operations."""
import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from src.models.video import Video
from src.models.new_video import NewVideo
from src.models.history import PlayHistory
from src.models.tag import Tag
from src.services.video_service import VideoService, is_completed


async def _create_video(session, source_id=1, title="Test Video", filepath="/test/video.mp4", duration=120, file_size=1024000):
    """Helper to create a video directly in the database."""
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
async def test_delete_video_removes_dependent_rows(db_session):
    """SQLite ignores the schema's ON DELETE CASCADE, so the service must not."""
    from sqlalchemy import func, select

    from src.models.favorite import Favorite
    from src.models.new_video import NewVideo
    from src.models.tag import Tag, video_tags

    video = await _create_video(db_session, title="Doomed", filepath="/d.mp4")
    tag = Tag(name="恐怖")
    db_session.add(tag)
    await db_session.commit()

    db_session.add_all(
        [
            Favorite(video_id=video.id),
            NewVideo(video_id=video.id, source_id=video.source_id),
            PlayHistory(video_id=video.id, progress=10),
        ]
    )
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


@pytest.mark.asyncio
async def test_get_videos_empty(db_session):
    """Test getting videos from empty database."""
    service = VideoService(db_session)
    videos, total = await service.get_videos()

    assert videos == []
    assert total == 0


@pytest.mark.asyncio
async def test_get_videos_with_data(db_session):
    """Test getting videos returns correct data."""
    await _create_video(db_session, title="Video 1", filepath="/v1.mp4")
    await _create_video(db_session, title="Video 2", filepath="/v2.mp4")
    await _create_video(db_session, title="Video 3", filepath="/v3.mp4")

    service = VideoService(db_session)
    videos, total = await service.get_videos()

    assert total == 3
    assert len(videos) == 3


@pytest.mark.asyncio
async def test_get_videos_filter_by_source(db_session):
    """Test filtering videos by source_id."""
    await _create_video(db_session, source_id=1, filepath="/s1/v1.mp4")
    await _create_video(db_session, source_id=1, filepath="/s1/v2.mp4")
    await _create_video(db_session, source_id=2, filepath="/s2/v1.mp4")

    service = VideoService(db_session)
    videos, total = await service.get_videos(source_id=1)

    assert total == 2
    assert all(v.source_id == 1 for v in videos)


@pytest.mark.asyncio
async def test_get_videos_filter_by_tag(db_session):
    """Test filtering videos by tag_id."""
    tag = Tag(name="action", color="#ff0000")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    video1 = await _create_video(db_session, title="Action Movie", filepath="/a.mp4")
    video2 = await _create_video(db_session, title="Comedy", filepath="/c.mp4")

    video1.tags.append(tag)
    await db_session.commit()

    service = VideoService(db_session)
    videos, total = await service.get_videos(tag_id=tag.id)

    assert total == 1
    assert videos[0].title == "Action Movie"


@pytest.mark.asyncio
async def test_get_videos_search(db_session):
    """Test searching videos by title."""
    await _create_video(db_session, title="The Matrix", filepath="/m.mp4")
    await _create_video(db_session, title="Inception", filepath="/i.mp4")
    await _create_video(db_session, title="Matrix Reloaded", filepath="/mr.mp4")

    service = VideoService(db_session)
    videos, total = await service.get_videos(search="matrix")

    assert total == 2
    assert all("matrix" in v.title.lower() for v in videos)


@pytest.mark.asyncio
async def test_search_for_lost_files_returns_only_missing_rows(db_session):
    """The 丢失 keyword is the whole library's window onto lost records."""
    kept = await _create_video(db_session, title="还在", filepath="/keep.mp4")
    lost = await _create_video(db_session, title="没了", filepath="/gone.mp4")
    lost.is_missing = True
    await db_session.commit()

    service = VideoService(db_session)
    videos, total = await service.get_videos(search="丢失")

    assert total == 1
    assert [video.id for video in videos] == [lost.id]
    assert videos[0].is_missing is True
    assert kept.is_missing is False


@pytest.mark.asyncio
async def test_get_videos_pagination(db_session):
    """Test pagination of videos."""
    for i in range(25):
        await _create_video(db_session, title=f"Video {i}", filepath=f"/v{i}.mp4")

    service = VideoService(db_session)

    # First page
    videos, total = await service.get_videos(page=1, page_size=10)
    assert total == 25
    assert len(videos) == 10

    # Second page
    videos, total = await service.get_videos(page=2, page_size=10)
    assert total == 25
    assert len(videos) == 10

    # Third page (partial)
    videos, total = await service.get_videos(page=3, page_size=10)
    assert total == 25
    assert len(videos) == 5


@pytest.mark.asyncio
async def test_get_video_by_id(db_session):
    """Test getting a specific video by ID."""
    created = await _create_video(db_session)

    service = VideoService(db_session)
    video = await service.get_video_by_id(created.id)

    assert video is not None
    assert video.id == created.id
    assert video.title == "Test Video"


@pytest.mark.asyncio
async def test_get_video_by_id_not_found(db_session):
    """Test getting a video that doesn't exist."""
    service = VideoService(db_session)
    video = await service.get_video_by_id(99999)

    assert video is None


@pytest.mark.asyncio
async def test_update_video(db_session):
    """Test updating video metadata."""
    created = await _create_video(db_session)

    service = VideoService(db_session)
    updated = await service.update_video(created.id, title="Updated Title", rating=5)

    assert updated.title == "Updated Title"
    assert updated.rating == 5
    assert updated.filepath == created.filepath  # unchanged


@pytest.mark.asyncio
async def test_update_video_not_found(db_session):
    """Test updating a video that doesn't exist."""
    service = VideoService(db_session)

    with pytest.raises(ValueError, match="Video with id 99999 not found"):
        await service.update_video(99999, title="test")


@pytest.mark.asyncio
async def test_delete_video(db_session):
    """Test deleting a video."""
    created = await _create_video(db_session)

    service = VideoService(db_session)
    await service.delete_video(created.id)

    video = await service.get_video_by_id(created.id)
    assert video is None


@pytest.mark.asyncio
async def test_delete_video_not_found(db_session):
    """Test deleting a video that doesn't exist."""
    service = VideoService(db_session)

    with pytest.raises(ValueError, match="Video with id 99999 not found"):
        await service.delete_video(99999)


@pytest.mark.asyncio
async def test_get_new_videos(db_session):
    """Test getting newly discovered videos."""
    video1 = await _create_video(db_session, title="New 1", filepath="/n1.mp4")
    video2 = await _create_video(db_session, title="New 2", filepath="/n2.mp4")
    video3 = await _create_video(db_session, title="Old", filepath="/o.mp4")

    # Mark video1 and video2 as new
    nv1 = NewVideo(video_id=video1.id, source_id=1)
    nv2 = NewVideo(video_id=video2.id, source_id=1)
    db_session.add_all([nv1, nv2])
    await db_session.commit()

    service = VideoService(db_session)
    new_videos = await service.get_new_videos()

    assert len(new_videos) == 2
    titles = {v.title for v in new_videos}
    assert "New 1" in titles
    assert "New 2" in titles


@pytest.mark.asyncio
async def test_get_new_videos_filter_by_source(db_session):
    """Test filtering new videos by source."""
    video1 = await _create_video(db_session, source_id=1, filepath="/s1.mp4")
    video2 = await _create_video(db_session, source_id=2, filepath="/s2.mp4")

    nv1 = NewVideo(video_id=video1.id, source_id=1)
    nv2 = NewVideo(video_id=video2.id, source_id=2)
    db_session.add_all([nv1, nv2])
    await db_session.commit()

    service = VideoService(db_session)
    new_videos = await service.get_new_videos(source_id=1)

    assert len(new_videos) == 1
    assert new_videos[0].source_id == 1


@pytest.mark.asyncio
async def test_mark_video_viewed(db_session):
    """Test marking a new video as viewed."""
    video = await _create_video(db_session)
    nv = NewVideo(video_id=video.id, source_id=1)
    db_session.add(nv)
    await db_session.commit()

    service = VideoService(db_session)
    await service.mark_video_viewed(video.id)

    await db_session.refresh(nv)
    assert nv.viewed is True


@pytest.mark.asyncio
async def test_record_play(db_session):
    """Test recording a play event."""
    video = await _create_video(db_session)
    assert video.view_count == 0

    service = VideoService(db_session)
    await service.record_play(video.id)

    await db_session.refresh(video)
    assert video.view_count == 1
    assert video.last_played_at is not None

    # Record another play
    await service.record_play(video.id)
    await db_session.refresh(video)
    assert video.view_count == 2


@pytest.mark.asyncio
async def test_record_play_not_found(db_session):
    """Test recording play for non-existent video."""
    service = VideoService(db_session)

    with pytest.raises(ValueError, match="Video with id 99999 not found"):
        await service.record_play(99999)


@pytest.mark.asyncio
async def test_update_progress(db_session):
    """Test updating playback progress."""
    video = await _create_video(db_session, duration=120)

    # First record a play
    service = VideoService(db_session)
    await service.record_play(video.id)

    # Update progress
    await service.update_progress(video.id, 60)

    # Check history
    from sqlalchemy import select
    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    history = result.scalar_one()
    assert history.progress == 60
    assert history.completed is False


@pytest.mark.asyncio
async def test_update_progress_completed(db_session):
    """Test that progress near end marks as completed."""
    video = await _create_video(db_session, duration=120)

    service = VideoService(db_session)
    await service.record_play(video.id)

    # Progress within 10 seconds of end
    await service.update_progress(video.id, 115)

    from sqlalchemy import select
    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    history = result.scalar_one()
    assert history.completed is True


@pytest.mark.asyncio
async def test_record_play_keeps_one_history_row_per_video(db_session):
    """Replaying refreshes the existing row rather than stacking a second one."""
    video = await _create_video(db_session)
    service = VideoService(db_session)

    await service.record_play(video.id)
    await service.update_progress(video.id, 45)
    await service.record_play(video.id)

    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    history = result.scalar_one()
    assert history.progress == 0
    assert history.completed is False


@pytest.mark.asyncio
async def test_record_play_clears_the_new_badge(db_session):
    """Watching a video is what retires its 新 label."""
    video = await _create_video(db_session)
    db_session.add(NewVideo(video_id=video.id, source_id=video.source_id))
    await db_session.commit()

    service = VideoService(db_session)
    videos, _ = await service.get_videos()
    assert videos[0].is_new is True

    await service.record_play(video.id)

    videos, _ = await service.get_videos()
    assert videos[0].is_new is False
    result = await db_session.execute(
        select(NewVideo).where(NewVideo.video_id == video.id)
    )
    assert result.scalar_one().viewed is True


@pytest.mark.asyncio
async def test_videos_without_a_scan_record_are_not_new(db_session):
    """Only the scan queue decides the badge, so a fresh file is not automatically 新."""
    await _create_video(db_session)

    service = VideoService(db_session)
    videos, _ = await service.get_videos()
    assert videos[0].is_new is False


@pytest.mark.asyncio
async def test_update_progress_reopens_a_finished_video(db_session):
    """Rewinding out of the tail takes the video back into continue watching."""
    video = await _create_video(db_session, duration=120)
    service = VideoService(db_session)
    await service.record_play(video.id)

    await service.update_progress(video.id, 118)
    await service.update_progress(video.id, 30)

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
async def test_update_progress_refreshes_played_at(db_session):
    """最后观看 means the last actual watch, not the moment the session started."""
    video = await _create_video(db_session)
    service = VideoService(db_session)
    await service.record_play(video.id)

    result = await db_session.execute(
        select(PlayHistory).where(PlayHistory.video_id == video.id)
    )
    started_at = result.scalar_one().played_at

    await service.update_progress(video.id, 10)

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
async def test_duplicates_only_report_identical_bytes(db_session, tmp_path):
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

    groups = await VideoService(db_session).get_duplicates()

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
async def test_duplicates_ignore_a_lone_file(db_session, tmp_path):
    """Nothing is a duplicate until a second copy shares its size."""
    payload = b"one and only" * 64
    await _create_video(
        db_session,
        filepath=_write_copy(tmp_path, "only.mkv", payload),
        file_size=len(payload),
    )

    assert await VideoService(db_session).get_duplicates() == []


@pytest.mark.asyncio
async def test_duplicates_skip_rows_whose_file_cannot_be_read(db_session):
    """A share that will not open must not be called a copy of anything."""
    await _create_video(db_session, title="在 NAS 上", filepath="/nas/a.mkv")
    await _create_video(db_session, title="也在 NAS 上", filepath="/nas/b.mkv")

    assert await VideoService(db_session).get_duplicates() == []


@pytest.mark.asyncio
async def test_duplicates_keep_the_copy_that_has_been_watched(db_session, tmp_path):
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
    await VideoService(db_session).update_progress(watched.id, 60)

    group = (await VideoService(db_session).get_duplicates())[0]

    assert group["keep_id"] == watched.id
    assert [v.id for v in group["items"]] == [watched.id, fresh.id]
    assert group["items"][0].progress == 60
