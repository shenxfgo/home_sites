import pytest


@pytest.mark.asyncio
async def test_create_subtitle(db_session):
    """Test creating subtitle record"""
    from src.models.subtitle import Subtitle
    from src.models.video import Video
    from src.models.source import VideoSource

    source = VideoSource(name="Test", path="/test", type="local")
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
    db_session.add(video)
    await db_session.commit()

    subtitle = Subtitle(
        video_id=video.id, language="zh", filepath="/test/sub.srt", label="中文"
    )
    db_session.add(subtitle)
    await db_session.commit()
    await db_session.refresh(subtitle)

    assert subtitle.id is not None
    assert subtitle.video_id == video.id
    assert subtitle.language == "zh"
    assert subtitle.label == "中文"
