import pytest


@pytest.mark.asyncio
async def test_create_tag(db_session):
    """Test creating a tag"""
    from src.models.tag import Tag

    tag = Tag(name="Action", color="#ff0000")

    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    assert tag.id is not None
    assert tag.name == "Action"
    assert tag.color == "#ff0000"


@pytest.mark.asyncio
async def test_video_tag_association(db_session):
    """Test many-to-many relationship between videos and tags"""
    from src.models.tag import Tag
    from src.models.video import Video
    from src.models.source import VideoSource

    # Create source and video
    source = VideoSource(name="Test", path="/test", type="local")
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
    db_session.add(video)
    await db_session.commit()

    # Create tags
    tag1 = Tag(name="Action", color="#ff0000")
    tag2 = Tag(name="Sci-Fi", color="#00ff00")
    db_session.add(tag1)
    db_session.add(tag2)
    await db_session.commit()

    # Refresh video to load tags relationship before extending
    await db_session.refresh(video, ["tags"])

    # Associate tags with video
    video.tags.extend([tag1, tag2])
    await db_session.commit()

    # Refresh and check
    await db_session.refresh(video, ["tags"])
    assert len(video.tags) == 2
    assert tag1 in video.tags
    assert tag2 in video.tags

    # Refresh tag1 to check reverse relationship
    await db_session.refresh(tag1, ["videos"])
    assert video in tag1.videos
