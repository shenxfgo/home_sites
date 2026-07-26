import pytest
from datetime import datetime


@pytest.mark.asyncio
async def test_create_video(db_session):
    """Test creating a video record"""
    from src.models.video import Video
    from src.models.source import VideoSource

    # Create a source first
    source = VideoSource(name="Test Source", path="/test", type="local")
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    # Create video
    video = Video(
        source_id=source.id,
        filepath="/test/video.mp4",
        title="Test Video",
        description="A test video",
        duration=600,  # 10 minutes
        file_size=1024000,
        format="mp4",
        resolution="1920x1080",
        rating=5,
        view_count=0,
    )

    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)

    assert video.id is not None
    assert video.source_id == source.id
    assert video.title == "Test Video"
    assert video.duration == 600
    assert video.rating == 5
    assert video.view_count == 0


@pytest.mark.asyncio
async def test_video_source_relationship(db_session):
    """Test that video has relationship to source"""
    from src.models.video import Video
    from src.models.source import VideoSource

    source = VideoSource(name="Test", path="/test", type="local")
    db_session.add(source)
    await db_session.commit()

    video = Video(
        source_id=source.id,
        filepath="/test/video.mp4",
        title="Video",
    )
    db_session.add(video)
    await db_session.commit()

    # Refresh to load relationship
    await db_session.refresh(video)

    assert video.source is not None
    assert video.source.name == "Test"
