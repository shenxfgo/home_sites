import pytest


@pytest.mark.asyncio
async def test_create_new_video(db_session):
    """Test creating new video record"""
    from src.models.new_video import NewVideo
    from src.models.video import Video
    from src.models.source import VideoSource

    source = VideoSource(name="Test", path="/test", type="local")
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
    db_session.add(video)
    await db_session.commit()

    new_video = NewVideo(video_id=video.id, source_id=source.id)
    db_session.add(new_video)
    await db_session.commit()
    await db_session.refresh(new_video)

    assert new_video.id is not None
    assert new_video.video_id == video.id
    assert new_video.source_id == source.id
    assert new_video.viewed is False
