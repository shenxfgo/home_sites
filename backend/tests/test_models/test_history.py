import pytest


@pytest.mark.asyncio
async def test_create_play_history(db_session):
    """Test creating play history record"""
    from src.models.history import PlayHistory
    from src.models.user import User
    from src.models.video import Video
    from src.models.source import VideoSource

    user = User(username="keeper", password_hash="not-used-in-tests", role="owner")
    db_session.add(user)
    await db_session.commit()

    source = VideoSource(name="Test", path="/test", type="local")
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
    db_session.add(video)
    await db_session.commit()

    history = PlayHistory(user_id=user.id, video_id=video.id, progress=120, completed=False)
    db_session.add(history)
    await db_session.commit()
    await db_session.refresh(history)

    assert history.id is not None
    assert history.video_id == video.id
    assert history.user_id == user.id
    assert history.progress == 120
    assert history.completed is False
