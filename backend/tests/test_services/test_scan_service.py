"""Tests for ScanService operations."""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from sqlalchemy import select

from src.models.source import VideoSource
from src.models.subtitle import Subtitle
from src.models.tag import Tag
from src.models.video import Video
from src.models.new_video import NewVideo
from src.services import scan_service as scan_module
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
        assert result["total_subtitles"] == 0


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
async def test_stop_scan_skips_remaining_sources(db_session, monkeypatch):
    """A stop request must make scan_all_active abandon untouched sources."""
    first = await _create_source(db_session, name="first")
    await _create_source(db_session, name="second")

    service = ScanService(db_session)
    visited: list[int] = []

    async def fake_scan_source(source_id: int) -> dict:
        visited.append(source_id)
        scan_module._scan_state["stop_requested"] = True
        return {"source_id": source_id, "files_found": 0, "new_videos": 0, "subtitles_found": 0}

    monkeypatch.setattr(service, "scan_source", fake_scan_source)

    result = await service.scan_all_active()

    assert visited == [first.id]
    assert result["sources_scanned"] == 1
    assert scan_module._scan_state["is_scanning"] is False


@pytest.mark.asyncio
async def test_scan_progress_visible_to_other_service_instances(db_session, monkeypatch):
    """Progress lives at module level so a separate request can observe it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = await _create_source(db_session, name="正在扫描", path=tmpdir)
        observed: list[dict] = []

        def fake_scan_directory(path: str) -> list:
            observed.append(ScanService(db_session).get_scan_progress())
            return []

        monkeypatch.setattr(scan_module, "scan_directory", fake_scan_directory)

        await ScanService(db_session).scan_source(source.id)

        assert observed[0]["is_scanning"] is True
        assert observed[0]["current_source"] == "正在扫描"
        # The scan is over, so the shared state must be back at idle.
        assert ScanService(db_session).get_scan_progress() == {
            "is_scanning": False,
            "current_source": None,
            "sources_total": 0,
            "sources_completed": 0,
            "files_found": 0,
            "new_videos": 0,
        }


@pytest.mark.asyncio
async def test_scan_source_nonexistent_directory(db_session):
    """Test scanning a source with non-existent directory."""
    source = await _create_source(db_session, path="/nonexistent/path/12345")
    service = ScanService(db_session)

    result = await service.scan_source(source.id)

    assert result["files_found"] == 0
    assert result["new_videos"] == 0


async def _subtitles_of(db_session, video_id: int) -> list[Subtitle]:
    result = await db_session.execute(
        select(Subtitle).where(Subtitle.video_id == video_id).order_by(Subtitle.id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_scan_source_registers_sidecar_subtitles(db_session):
    """A new video's sidecar subtitle files become tracks of that video."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_video(tmpdir, "movie.mp4")
        _write_text(os.path.join(tmpdir, "movie.zh.srt"))
        _write_text(os.path.join(tmpdir, "movie.en.vtt"))

        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 10, "resolution": None, "format": "mp4"}
            mock_thumb.return_value = ""
            result = await service.scan_source(source.id)

        video = (await db_session.execute(
            select(Video).where(Video.source_id == source.id)
        )).scalars().one()
        stored = await _subtitles_of(db_session, video.id)

        assert result["subtitles_found"] == 2
        assert [s.language for s in stored] == ["en", "zh"]


@pytest.mark.asyncio
async def test_scan_source_subtitles_are_idempotent(db_session):
    """Re-scanning the same directory must not duplicate subtitle rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_video(tmpdir, "movie.mp4")
        _write_text(os.path.join(tmpdir, "movie.zh.srt"))

        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 10, "resolution": None, "format": "mp4"}
            mock_thumb.return_value = ""
            first = await service.scan_source(source.id)
            second = await service.scan_source(source.id)

        video = (await db_session.execute(
            select(Video).where(Video.source_id == source.id)
        )).scalars().one()

        assert first["subtitles_found"] == 1
        assert second["subtitles_found"] == 0
        assert len(await _subtitles_of(db_session, video.id)) == 1


@pytest.mark.asyncio
async def test_scan_source_adds_subtitles_to_existing_video(db_session):
    """A subtitle dropped next to an already indexed video is found on the next scan."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_video(tmpdir, "movie.mp4")

        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 10, "resolution": None, "format": "mp4"}
            mock_thumb.return_value = ""
            await service.scan_source(source.id)

        _write_text(os.path.join(tmpdir, "movie.ja.ass"))
        result = await service.scan_source(source.id)

        video = (await db_session.execute(
            select(Video).where(Video.source_id == source.id)
        )).scalars().one()
        stored = await _subtitles_of(db_session, video.id)

        assert result["new_videos"] == 0
        assert result["subtitles_found"] == 1
        assert [s.language for s in stored] == ["ja"]


def _write_video(directory: str, name: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write("dummy content")
    return path


def _write_text(path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write("1\n00:00:01,000 --> 00:00:02,000\nhi\n")
    return path


@pytest.mark.asyncio
async def test_scan_records_series_coordinates_and_one_shared_tag(db_session):
    """Episodes of a series keep their coordinates and reuse one tag row."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_video(tmpdir, "[NC-Raws] 海边的日子 第01集.mp4")
        _write_video(tmpdir, "[NC-Raws] 海边的日子 第02集.mp4")
        _write_video(tmpdir, "夜空列车.mp4")

        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 20, "resolution": "640x360", "format": "mp4"}
            mock_thumb.return_value = ""
            await service.scan_source(source.id)

        result = await db_session.execute(select(Video))
        by_title = {video.title: video for video in result.scalars().all()}

        assert set(by_title) == {"海边的日子 第1集", "海边的日子 第2集", "夜空列车"}
        first = by_title["海边的日子 第1集"]
        assert (first.series, first.season, first.episode) == ("海边的日子", None, 1)
        assert [tag.name for tag in first.tags] == ["海边的日子", "NC-Raws"]
        assert by_title["夜空列车"].tags == []

        tags = await db_session.execute(select(Tag).where(Tag.name == "海边的日子"))
        assert len(tags.scalars().all()) == 1


@pytest.mark.asyncio
async def test_rescan_backfills_coordinates_into_old_rows(db_session):
    """A row written before the parser gets its series on the next scan."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_video(tmpdir, "[NC-Raws] 海边的日子 第03集.mp4")
        source = await _create_source(db_session, path=tmpdir)
        curated = Tag(name="我手动加的")
        old = Video(
            source_id=source.id,
            filepath=path,
            title="我改过的名字",
            duration=20,
            format="mp4",
            tags=[curated],
        )
        db_session.add(old)
        await db_session.commit()

        service = ScanService(db_session)
        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 20, "format": "mp4"}
            mock_thumb.return_value = ""
            result = await service.scan_source(source.id)

        assert result["new_videos"] == 0
        assert (old.series, old.season, old.episode) == ("海边的日子", None, 3)
        assert old.title == "我改过的名字"
        assert [tag.name for tag in old.tags] == ["我手动加的", "海边的日子", "NC-Raws"]


@pytest.mark.asyncio
async def test_rescan_does_not_duplicate_auto_tags(db_session):
    """A second scan of the same directory leaves the tag table untouched."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_video(tmpdir, "Severance.S01E01.mkv")
        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with patch("src.services.scan_service.extract_video_info") as mock_info, \
             patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
            mock_info.return_value = {"duration": 20, "format": "mkv"}
            mock_thumb.return_value = ""
            await service.scan_source(source.id)
            await service.scan_source(source.id)

        tags = await db_session.execute(select(Tag))
        assert [tag.name for tag in tags.scalars().all()] == ["Severance"]
