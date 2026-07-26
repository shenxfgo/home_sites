import pytest
from datetime import datetime


@pytest.mark.asyncio
async def test_create_video_source(db_session):
    """Test creating a video source"""
    from src.models.source import VideoSource

    source = VideoSource(
        name="Test Collection",
        path="/test/path",
        type="local",
        scan_interval=3600,
        is_active=True,
    )

    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)

    assert source.id is not None
    assert source.name == "Test Collection"
    assert source.path == "/test/path"
    assert source.type == "local"
    assert source.scan_interval == 3600
    assert source.is_active is True
    assert source.created_at is not None


@pytest.mark.asyncio
async def test_video_source_type_validation(db_session):
    """Test that video source type must be valid"""
    from src.models.source import VideoSource
    from sqlalchemy.exc import IntegrityError

    source = VideoSource(
        name="Invalid Source",
        path="/test/path",
        type="invalid_type",  # Should be 'local', 'nas', or 'minio'
    )

    db_session.add(source)
    with pytest.raises(IntegrityError):
        await db_session.commit()
