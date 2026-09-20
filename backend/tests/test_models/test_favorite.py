import pytest


@pytest.mark.asyncio
async def test_create_favorite(db_session):
    """Test creating favorite"""
    from src.models.favorite import Favorite
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

    favorite = Favorite(user_id=user.id, video_id=video.id)
    db_session.add(favorite)
    await db_session.commit()
    await db_session.refresh(favorite)

    assert favorite.id is not None
    assert favorite.video_id == video.id
    assert favorite.user_id == user.id
