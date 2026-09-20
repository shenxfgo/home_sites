"""Tests for SourceService CRUD operations."""
import pytest
from datetime import datetime


@pytest.mark.asyncio
async def test_create_source(db_session):
    """Test creating a video source."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    source = await service.create(
        name="My Collection",
        path="/media/collection",
        type="local",
        scan_interval=1800,
    )

    assert source.id is not None
    assert source.name == "My Collection"
    assert source.path == "/media/collection"
    assert source.type == "local"
    assert source.scan_interval == 1800
    assert source.is_active is True


@pytest.mark.asyncio
async def test_create_source_defaults(db_session):
    """Test creating a source uses default values."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    source = await service.create(name="Default", path="/path", type="nas")

    assert source.scan_interval == 3600
    assert source.is_active is True


@pytest.mark.asyncio
async def test_list_sources(db_session):
    """Test listing all video sources."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    await service.create(name="Source 1", path="/path1", type="local")
    await service.create(name="Source 2", path="/path2", type="nas")
    await service.create(name="Source 3", path="/path3", type="minio")

    sources = await service.list_all()

    assert len(sources) == 3
    assert any(s.name == "Source 1" for s in sources)
    assert any(s.name == "Source 2" for s in sources)
    assert any(s.name == "Source 3" for s in sources)


@pytest.mark.asyncio
async def test_list_sources_active_only(db_session):
    """Test listing only active sources."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    await service.create(name="Active", path="/a", type="local")
    await service.create(name="Inactive", path="/b", type="local", is_active=False)

    active_sources = await service.list_all(active_only=True)

    assert len(active_sources) == 1
    assert active_sources[0].name == "Active"


@pytest.mark.asyncio
async def test_get_source_by_id(db_session):
    """Test getting a specific source by ID."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="Test", path="/test", type="local")

    retrieved = await service.get_by_id(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == "Test"


@pytest.mark.asyncio
async def test_get_source_not_found(db_session):
    """Test getting a source that doesn't exist."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    result = await service.get_by_id(99999)

    assert result is None


@pytest.mark.asyncio
async def test_update_source(db_session):
    """Test updating a source."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="Original", path="/test", type="local")

    updated = await service.update(created.id, name="Updated", scan_interval=7200)

    assert updated.name == "Updated"
    assert updated.scan_interval == 7200
    assert updated.path == "/test"  # unchanged


@pytest.mark.asyncio
async def test_update_source_not_found(db_session):
    """Test updating a source that doesn't exist."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    with pytest.raises(ValueError, match="Source with id 99999 not found"):
        await service.update(99999, name="test")


@pytest.mark.asyncio
async def test_delete_source(db_session):
    """Test deleting a source."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="To Delete", path="/test", type="local")

    await service.delete(created.id)

    deleted = await service.get_by_id(created.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_delete_source_not_found(db_session):
    """Test deleting a source that doesn't exist."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)

    with pytest.raises(ValueError, match="Source with id 99999 not found"):
        await service.delete(99999)


@pytest.mark.asyncio
async def test_delete_source_removes_videos_and_dependents(db_session, user_id):
    """videos.source_id is NOT NULL, so a source with videos used to fail to delete."""
    from sqlalchemy import func, select

    from src.models.favorite import Favorite
    from src.models.history import PlayHistory
    from src.models.new_video import NewVideo
    from src.models.video import Video
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    doomed = await service.create(name="Doomed", path="/doomed", type="local")
    keeper = await service.create(name="Keeper", path="/keeper", type="local")

    doomed_video = Video(source_id=doomed.id, filepath="/doomed/a.mp4", title="a")
    keeper_video = Video(source_id=keeper.id, filepath="/keeper/b.mp4", title="b")
    db_session.add_all([doomed_video, keeper_video])
    await db_session.commit()

    db_session.add_all(
        [
            NewVideo(video_id=doomed_video.id, source_id=doomed.id),
            Favorite(user_id=user_id, video_id=doomed_video.id),
            PlayHistory(user_id=user_id, video_id=doomed_video.id, progress=42),
            NewVideo(video_id=keeper_video.id, source_id=keeper.id),
        ]
    )
    await db_session.commit()

    await service.delete(doomed.id)

    async def count(model):
        result = await db_session.execute(select(func.count()).select_from(model))
        return result.scalar()

    assert await count(Video) == 1
    assert await count(NewVideo) == 1
    assert await count(Favorite) == 0
    assert await count(PlayHistory) == 0
    assert await service.get_by_id(doomed.id) is None
    assert await service.get_by_id(keeper.id) is not None


@pytest.mark.asyncio
async def test_update_last_scan(db_session):
    """Test updating last_scan_at timestamp."""
    from src.services.source_service import SourceService

    service = SourceService(db_session)
    created = await service.create(name="Test", path="/test", type="local")

    assert created.last_scan_at is None

    await service.update_last_scan(created.id)

    updated = await service.get_by_id(created.id)
    assert updated.last_scan_at is not None
    assert isinstance(updated.last_scan_at, datetime)
