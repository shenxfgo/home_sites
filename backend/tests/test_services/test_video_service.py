"""Tests for VideoService operations."""
import pytest
from datetime import datetime, timezone

from src.models.video import Video
from src.models.new_video import NewVideo
from src.models.history import PlayHistory
from src.models.tag import Tag
from src.services.video_service import VideoService


async def _create_video(session, source_id=1, title="Test Video", filepath="/test/video.mp4", duration=120):
    """Helper to create a video directly in the database."""
    video = Video(
        source_id=source_id,
        filepath=filepath,
        title=title,
        duration=duration,
        file_size=1024000,
        format="mp4",
        resolution="1920x1080",
    )
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return video


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
