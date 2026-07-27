"""Tests for Scan API endpoints."""
import os
import tempfile
import pytest
import httpx
from unittest.mock import patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database.base import Base
import src.models  # noqa: F401


@pytest.fixture
async def db_session():
    """Create a fresh in-memory database for API tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(db_session):
    """Create async test client with overridden database session."""
    from src.main import app
    from src.database import get_session
    from src.services.scan_service import ScanService
    from src.api.scan import get_scan_service

    async def override_get_session():
        yield db_session

    async def override_get_scan_service():
        return ScanService(db_session)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_scan_service] = override_get_scan_service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def _create_source(session, name="Test Source", path="/test", is_active=True):
    """Helper to create a source."""
    from src.models.source import VideoSource
    source = VideoSource(name=name, path=path, type="local", is_active=is_active)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_scan_source(client, db_session):
    """Test scanning a single source."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = await _create_source(db_session, path=tmpdir)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 100, "resolution": "1920x1080", "format": "mp4"}
            mock_thumb.return_value = ""

            response = await client.post(f"/api/sources/{source.id}/scan")

        assert response.status_code == 200
        result = response.json()
        assert result["source_id"] == source.id
        assert result["files_found"] == 0
        assert result["new_videos"] == 0


@pytest.mark.asyncio
async def test_scan_source_not_found(client):
    """Test scanning a source that doesn't exist."""
    response = await client.post("/api/sources/99999/scan")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_scan_source_with_files(client, db_session):
    """Test scanning a source with video files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create video files
        for name in ["v1.mp4", "v2.mkv"]:
            with open(os.path.join(tmpdir, name), "w") as f:
                f.write("dummy")

        source = await _create_source(db_session, path=tmpdir)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 60, "resolution": "1280x720", "format": "mp4"}
            mock_thumb.return_value = ""

            response = await client.post(f"/api/sources/{source.id}/scan")

        assert response.status_code == 200
        result = response.json()
        assert result["files_found"] == 2
        assert result["new_videos"] == 2


@pytest.mark.asyncio
async def test_scan_all(client, db_session):
    """Test scanning all active sources."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = await _create_source(db_session, path=tmpdir, is_active=True)
        await _create_source(db_session, path="/nonexistent", is_active=False)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 60, "resolution": "1280x720", "format": "mp4"}
            mock_thumb.return_value = ""

            response = await client.post("/api/scan/all")

        assert response.status_code == 200
        result = response.json()
        assert result["sources_scanned"] == 1
        assert result["total_new_videos"] == 0


@pytest.mark.asyncio
async def test_get_scan_progress(client):
    """Test getting scan progress."""
    response = await client.get("/api/scan/progress")
    assert response.status_code == 200
    result = response.json()
    assert result["is_scanning"] is False
    assert result["sources_total"] == 0
    assert result["sources_completed"] == 0


@pytest.mark.asyncio
async def test_stop_scan(client):
    """Test stopping a scan."""
    response = await client.post("/api/scan/stop")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
