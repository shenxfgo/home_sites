"""Tests for ScanService operations."""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from src.models.source import VideoSource
from src.models.video import Video
from src.models.new_video import NewVideo
from src.services.scan_service import ScanService


async def _create_source(session, name="Test Source", path="/test/path", is_active=True):
    """Helper to create a video source."""
    source = VideoSource(
        name=name,
        path=path,
        type="local",
        is_active=is_active,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_scan_source_not_found(db_session):
    """Test scanning a source that doesn't exist."""
    service = ScanService(db_session)

    with pytest.raises(ValueError, match="Source with id 99999 not found"):
        await service.scan_source(99999)


@pytest.mark.asyncio
async def test_scan_source_empty_directory(db_session):
    """Test scanning an empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        result = await service.scan_source(source.id)

        assert result["source_id"] == source.id
        assert result["files_found"] == 0
        assert result["new_videos"] == 0


@pytest.mark.asyncio
async def test_scan_source_with_videos(db_session):
    """Test scanning a directory with video files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some video files
        for name in ["video1.mp4", "video2.mkv", "not_video.txt"]:
            filepath = os.path.join(tmpdir, name)
            with open(filepath, "w") as f:
                f.write("dummy content")

        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 100, "resolution": "1920x1080", "format": "mp4"}
            mock_thumb.return_value = ""

            result = await service.scan_source(source.id)

        assert result["files_found"] == 2  # Only .mp4 and .mkv
        assert result["new_videos"] == 2

        # Verify videos were created
        from sqlalchemy import select
        videos_result = await db_session.execute(
            select(Video).where(Video.source_id == source.id)
        )
        videos = list(videos_result.scalars().all())
        assert len(videos) == 2


@pytest.mark.asyncio
async def test_scan_source_skips_existing(db_session):
    """Test that scanning skips already known videos."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a video file
        filepath = os.path.join(tmpdir, "video.mp4")
        with open(filepath, "w") as f:
            f.write("dummy content")

        source = await _create_source(db_session, path=tmpdir)

        # Pre-create the video record
        video = Video(source_id=source.id, filepath=filepath, title="Existing")
        db_session.add(video)
        await db_session.commit()

        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 100, "resolution": "1920x1080", "format": "mp4"}
            mock_thumb.return_value = ""

            result = await service.scan_source(source.id)

        assert result["files_found"] == 1
        assert result["new_videos"] == 0  # Already exists


@pytest.mark.asyncio
async def test_scan_source_updates_last_scan(db_session):
    """Test that scanning updates the source's last_scan_at."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = await _create_source(db_session, path=tmpdir)
        assert source.last_scan_at is None

        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": None, "resolution": None, "format": None}
            mock_thumb.return_value = ""

            await service.scan_source(source.id)

        from sqlalchemy import select
        result = await db_session.execute(
            select(VideoSource).where(VideoSource.id == source.id)
        )
        updated_source = result.scalar_one()
        assert updated_source.last_scan_at is not None


@pytest.mark.asyncio
async def test_scan_all_active(db_session):
    """Test scanning all active sources."""
    with tempfile.TemporaryDirectory() as tmpdir1, \
         tempfile.TemporaryDirectory() as tmpdir2:

        source1 = await _create_source(db_session, name="Active 1", path=tmpdir1, is_active=True)
        source2 = await _create_source(db_session, name="Active 2", path=tmpdir2, is_active=True)
        await _create_source(db_session, name="Inactive", path="/nonexistent", is_active=False)

        # Create video files in first source
        with open(os.path.join(tmpdir1, "v1.mp4"), "w") as f:
            f.write("dummy")

        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 60, "resolution": "1280x720", "format": "mp4"}
            mock_thumb.return_value = ""

            result = await service.scan_all_active()

        assert result["sources_scanned"] == 2
        assert result["total_files"] == 1
        assert result["total_new_videos"] == 1


@pytest.mark.asyncio
async def test_scan_all_active_empty(db_session):
    """Test scanning when no active sources exist."""
    await _create_source(db_session, is_active=False)

    service = ScanService(db_session)
    result = await service.scan_all_active()

    assert result["sources_scanned"] == 0
    assert result["total_files"] == 0
    assert result["total_new_videos"] == 0


@pytest.mark.asyncio
async def test_get_scan_progress(db_session):
    """Test getting scan progress."""
    service = ScanService(db_session)
    progress = service.get_scan_progress()

    assert progress["is_scanning"] is False
    assert progress["current_source"] is None
    assert progress["sources_total"] == 0
    assert progress["sources_completed"] == 0


@pytest.mark.asyncio
async def test_stop_scan(db_session):
    """Test stopping a scan."""
    service = ScanService(db_session)
    service._scanning = True
    service._progress["is_scanning"] = True

    await service.stop_scan()

    assert service.is_scanning is False
    progress = service.get_scan_progress()
    assert progress["is_scanning"] is False


@pytest.mark.asyncio
async def test_scan_source_nonexistent_directory(db_session):
    """Test scanning a source with non-existent directory."""
    source = await _create_source(db_session, path="/nonexistent/path/12345")
    service = ScanService(db_session)

    result = await service.scan_source(source.id)

    assert result["files_found"] == 0
    assert result["new_videos"] == 0
