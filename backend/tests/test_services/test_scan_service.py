"""Tests for ScanService operations."""
import logging
import os
import tempfile
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.models.notification import Notification
from src.models.source import VideoSource
from src.models.subtitle import Subtitle
from src.models.tag import Tag
from src.models.video import Video
from src.scheduler import tasks as task_module
from src.services import scan_service as scan_module
from src.services.scan_service import ScanService
from src.storage import Capabilities, FoundFile
from tests.conftest import _SharedSession


class _FakeStorage:
    """A storage whose listing can be watched and steered from a test.

    Scan code reaches files through the storage seam now, so that is the seam a
    test has to stand in for -- patching ``scan_directory`` would only prove the
    fake was called.
    """

    def __init__(
        self,
        files: list[FoundFile] | None = None,
        reachable: bool = True,
        sidecar_subtitles: bool = False,
        local_path: bool = True,
        on_list=None,
    ) -> None:
        self.files = files or []
        self._reachable = reachable
        self.capabilities = Capabilities(
            streaming=True,
            local_path=local_path,
            sidecar_subtitles=sidecar_subtitles,
        )
        self.listed_paths: list[str] = []
        self._on_list = on_list

    def reachable(self, root: str) -> bool:
        return self._reachable

    def list_videos(self, root: str) -> list[FoundFile]:
        self.listed_paths.append(root)
        if self._on_list is not None:
            self._on_list()
        return self.files

    def exists(self, locator: str) -> bool:
        return True

    def size(self, locator: str) -> int | None:
        return None

    def iter_range(self, locator: str, start: int, end: int):
        return iter(())

    def edge_fingerprint(self, locator: str) -> str | None:
        return None

    def local_path(self, locator: str) -> str:
        return locator


def _found(locator: str, size: int = 1024) -> FoundFile:
    name = locator.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return FoundFile(
        locator=locator,
        filename=name,
        extension="." + name.rsplit(".", 1)[-1].lower(),
        size=size,
    )


def _patch_storage(monkeypatch, storage) -> None:
    monkeypatch.setattr(scan_module, "storage_for_source", lambda source_type: storage)


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

        await _create_source(db_session, name="Active 1", path=tmpdir1, is_active=True)
        await _create_source(db_session, name="Active 2", path=tmpdir2, is_active=True)
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

        def watch_progress() -> None:
            observed.append(ScanService(db_session).get_scan_progress())

        _patch_storage(monkeypatch, _FakeStorage(on_list=watch_progress))

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


@contextmanager
def _no_media_probe() -> Iterator[None]:
    """Skip ffprobe/ffmpeg, which the scan only needs for metadata."""
    with patch("src.services.scan_service.extract_video_info") as mock_info, \
         patch("src.services.scan_service.generate_thumbnail") as mock_thumb:
        mock_info.return_value = {"duration": 20, "format": "mp4"}
        mock_thumb.return_value = ""
        yield


@pytest.mark.asyncio
async def test_scan_marks_vanished_files_as_missing(db_session):
    """A file that is gone is flagged, and its row survives."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gone = _write_video(tmpdir, "已经删掉.mp4")
        _write_video(tmpdir, "还在.mp4")
        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with _no_media_probe():
            await service.scan_source(source.id)
            os.remove(gone)
            result = await service.scan_source(source.id)

        videos = (await db_session.execute(select(Video))).scalars().all()
        assert result["new_videos"] == 0
        assert {video.title: video.is_missing for video in videos} == {
            "已经删掉": True,
            "还在": False,
        }


@pytest.mark.asyncio
async def test_missing_flag_clears_when_the_file_comes_back(db_session):
    """A share that remounts restores its rows without a re-insert."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_video(tmpdir, "外接硬盘.mp4")
        source = await _create_source(db_session, path=tmpdir)
        service = ScanService(db_session)

        with _no_media_probe():
            await service.scan_source(source.id)
            os.remove(path)
            await service.scan_source(source.id)
            video = (await db_session.execute(select(Video))).scalars().one()
            assert video.is_missing is True

            _write_video(tmpdir, "外接硬盘.mp4")
            restored = await service.scan_source(source.id)

        assert restored["new_videos"] == 0
        assert (await db_session.execute(select(Video))).scalars().one().is_missing is False


@pytest.mark.asyncio
async def test_unmounted_source_marks_nothing(db_session):
    """A source directory that is not there at all must not black out the library."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source = await _create_source(db_session, path=tmpdir)
        video = Video(
            source_id=source.id,
            filepath=os.path.join(tmpdir, "在硬盘上.mp4"),
            title="在硬盘上",
        )
        db_session.add(video)
        await db_session.commit()

    # The share is unmounted: scan_directory finds nothing, as an empty folder
    # would, and that is exactly when a rescan must keep the rows alive.
    service = ScanService(db_session)
    with _no_media_probe():
        result = await service.scan_source(source.id)

    await db_session.refresh(video)
    assert result["files_found"] == 0
    assert video.is_missing is False


@pytest.mark.asyncio
async def test_same_basename_in_two_subfolders_keeps_two_covers(
    db_session, monkeypatch, tmp_path
):
    """同名不同目录的片子各自留一张封面。

    封面名只按 basename 推的时候，``a/01.mp4`` 和 ``b/01.mp4`` 会写到同一个
    ``01.jpg``，后扫的那张悄悄把前一张盖掉 —— 两行都"有封面"，看不出坏过。
    """
    from src.config import settings

    source = await _create_source(db_session, path="/library")
    _patch_storage(
        monkeypatch,
        _FakeStorage(
            files=[_found("/library/a/01.mp4"), _found("/library/b/01.mp4")]
        ),
    )
    monkeypatch.setattr(settings, "thumbnail_path", str(tmp_path / "thumbs"))

    written: list[str] = []

    def _fake_generate(video_path: str, output_path: str) -> str:
        # 真 ffmpeg 会落下文件，扫描靠它判断封面是否成功
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb"):
            pass
        written.append(output_path)
        return output_path

    with patch("src.services.scan_service.extract_video_info") as mock_info, patch(
        "src.services.scan_service.generate_thumbnail", side_effect=_fake_generate
    ):
        mock_info.return_value = {"duration": 20, "format": "mp4"}
        result = await ScanService(db_session).scan_source(source.id)

    assert result["new_videos"] == 2
    assert len(set(written)) == 2, "两张封面写到了同一个文件"

    rows = (
        (
            await db_session.execute(
                select(Video)
                .where(Video.source_id == source.id)
                .order_by(Video.filepath)
            )
        )
        .scalars()
        .all()
    )
    names = [os.path.basename(row.thumbnail_path) for row in rows]
    assert len(set(names)) == 2
    assert all(name.startswith("01-") and name.endswith(".jpg") for name in names)
    assert all(
        row.thumbnail_path.startswith(str(tmp_path / "thumbs" / str(source.id)))
        for row in rows
    )


# ---------------------------------------------------------------------------
# 通知投递：一轮扫描只说一遍，没变就别说


async def _notifications(session) -> list[tuple[str, str]]:
    """(类型, 文案) 清单，按写入顺序。"""
    rows = (
        await session.execute(select(Notification).order_by(Notification.id))
    ).scalars().all()
    return [(row.type, row.message) for row in rows]


def _share_session(monkeypatch, session) -> None:
    """让定时任务复用用例的连接，而不是去连真库。"""
    monkeypatch.setattr(task_module, "async_session_maker", _SharedSession(session))


@pytest.mark.asyncio
async def test_scheduled_scan_announces_once(db_session, monkeypatch, tmp_path):
    """调度任务和扫描服务不能对同一次扫描各发一条。

    曾经 tasks 在 scan_source 已经写过 scan_complete 之后，又对同一个结果补一条
    scheduled_scan —— 六个源跑一轮就是 12 条。
    """
    _write_video(str(tmp_path), "新片.mp4")
    source = await _create_source(db_session, name="定时源", path=str(tmp_path))
    _share_session(monkeypatch, db_session)

    with _no_media_probe():
        await task_module.scan_source_task(source.id)

    assert await _notifications(db_session) == [
        ("scan_complete", "视频源 定时源 扫描完成，发现 1 个新视频")
    ]


@pytest.mark.asyncio
async def test_unchanged_scan_announces_nothing(db_session, monkeypatch, tmp_path):
    """零新增的定时扫描不该把通知流刷成心跳。"""
    _write_video(str(tmp_path), "老片.mp4")
    source = await _create_source(db_session, name="安静源", path=str(tmp_path))
    _share_session(monkeypatch, db_session)

    with _no_media_probe():
        await task_module.scan_source_task(source.id)
        before = await _notifications(db_session)
        await task_module.scan_source_task(source.id)
        await task_module.scan_source_task(source.id)

    assert len(before) == 1
    assert await _notifications(db_session) == before


@pytest.mark.asyncio
async def test_vanished_file_still_announces(db_session, tmp_path):
    """片子没了是变化，必须说 —— 否则整个源掉线只留在行标记里。"""
    path = _write_video(str(tmp_path), "会消失.mp4")
    source = await _create_source(db_session, name="消失源", path=str(tmp_path))

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)
        os.remove(path)
        await ScanService(db_session).scan_source(source.id)

    assert await _notifications(db_session) == [
        ("scan_complete", "视频源 消失源 扫描完成，发现 1 个新视频"),
        ("scan_complete", "视频源 消失源 扫描完成，发现 0 个新视频，1 个文件已找不到"),
    ]


@pytest.mark.asyncio
async def test_returned_file_announces_a_return(db_session, tmp_path):
    """文件挂载回来那一轮，通知不能再写「已找不到」。

    计数只数"翻了几行"，不看朝哪个方向翻：丢了 1 行和回来 1 行说的是同一句话，而后者
    恰恰是好消息 —— 界面上会显示「1 个文件已找不到」，同时那部片子已经能播了。
    """
    path = _write_video(str(tmp_path), "会回来.mp4")
    source = await _create_source(db_session, name="回来源", path=str(tmp_path))

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)
        os.remove(path)
        await ScanService(db_session).scan_source(source.id)
        _write_video(str(tmp_path), "会回来.mp4")
        result = await ScanService(db_session).scan_source(source.id)

    assert result["files_found"] == 1
    assert await _notifications(db_session) == [
        ("scan_complete", "视频源 回来源 扫描完成，发现 1 个新视频"),
        ("scan_complete", "视频源 回来源 扫描完成，发现 0 个新视频，1 个文件已找不到"),
        ("scan_complete", "视频源 回来源 扫描完成，发现 0 个新视频，1 个文件已找回"),
    ]


@pytest.mark.asyncio
async def test_new_subtitle_for_existing_video_announces(db_session, tmp_path):
    """老片旁边多出字幕也是变化，光看 new_videos 会把它漏掉。"""
    _write_video(str(tmp_path), "movie.mp4")
    source = await _create_source(db_session, name="字幕源", path=str(tmp_path))

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)
        _write_text(os.path.join(str(tmp_path), "movie.zh.srt"))
        await ScanService(db_session).scan_source(source.id)

    assert await _notifications(db_session) == [
        ("scan_complete", "视频源 字幕源 扫描完成，发现 1 个新视频"),
        ("scan_complete", "视频源 字幕源 扫描完成，发现 0 个新视频、1 条字幕"),
    ]


@pytest.mark.asyncio
async def test_two_sources_over_one_directory_do_not_collide(db_session, tmp_path):
    """同一个目录被两个源指着是配置失误，不是每轮都去撞一次数据库约束的理由。

    `videos.filepath` 上有唯一约束，而"这文件我认识"的判定只看**本源的**行，所以
    别源已经建过的路径会被当成新文件重插一次：真机上 source 5 和 source 6 都指向
    `backend/data/test_videos`，每轮定时扫描对每个撞车的文件都留下一次
    `duplicate key value violates unique constraint "videos_filepath_key"`。每个文件
    外面确实有一层 SAVEPOINT 兜着（所以整轮没炸），但这条路径本该在插之前说清楚。
    """
    _write_video(str(tmp_path), "共享的一部.mp4")
    first = await _create_source(db_session, name="先建的源", path=str(tmp_path))
    second = await _create_source(db_session, name="后来那个源", path=str(tmp_path))

    with _no_media_probe():
        await ScanService(db_session).scan_source(first.id)
        result = await ScanService(db_session).scan_source(second.id)

    assert result["new_videos"] == 0
    assert result["foreign_paths"] == 1
    rows = (await db_session.execute(select(Video).order_by(Video.id))).scalars().all()
    assert [row.source_id for row in rows] == [first.id]


@pytest.mark.asyncio
async def test_a_foreign_path_does_not_take_the_rest_of_the_listing_down(
    db_session, monkeypatch
):
    """撞车只该影响它自己那一个文件：同一份清单里真正的新片仍然要建得出来。"""
    store = _FakeStorage(files=[_found("/lib/a.mp4")])
    _patch_storage(monkeypatch, store)
    first = await _create_source(db_session, name="已有影片库", path="/lib")
    second = await _create_source(db_session, name="重叠的第二个源", path="/lib")

    with _no_media_probe():
        await ScanService(db_session).scan_source(first.id)
        store.files = [_found("/lib/a.mp4"), _found("/lib/只有这轮才出现.mp4")]
        result = await ScanService(db_session).scan_source(second.id)

    assert result["new_videos"] == 1
    assert result["foreign_paths"] == 1
    owned = (
        await db_session.execute(select(Video.filepath).where(Video.source_id == second.id))
    ).scalars().all()
    assert list(owned) == ["/lib/只有这轮才出现.mp4"]


# ---------------------------------------------------------------------------
# 字幕核对：登记过之后，扫描还要问一句「文件还在吗」
#
# 影片那一行早就有 is_missing 核对（见上面那三条），字幕这一半从来没有：
# _register_subtitles 只会 add，谁也没删。于是 sidecar 文件被移走、改名或删掉之后，
# 那条 Subtitle 行永远留在库里，GET /api/videos/{id}/subtitles 照旧把它列出来，
# 播放器的 CC 菜单照旧给一个能点的入口，而点开必定 404。#146 只是让那句失败
# 说得出是谁，并没有让这条轨消失。


@pytest.mark.asyncio
async def test_scan_prunes_subtitle_row_whose_file_is_gone(db_session, tmp_path):
    """字幕文件没了，那一行就该跟着消失，而不是永远挂在菜单上。"""
    root = str(tmp_path)
    _write_video(root, "movie.mp4")
    srt = _write_text(os.path.join(root, "movie.zh.srt"))
    source = await _create_source(db_session, name="字幕核对源", path=root)

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)
        video = (await db_session.execute(select(Video))).scalars().one()
        assert len(await _subtitles_of(db_session, video.id)) == 1

        os.remove(srt)
        result = await ScanService(db_session).scan_source(source.id)

    # 症状本身：文件已经不在了，那一行还在库里被列出来
    assert [s.filepath for s in await _subtitles_of(db_session, video.id)] == []
    assert result["subtitles_gone"] == 1
    # 影片本身还在盘上，不该被这次核对连带标记成丢失
    await db_session.refresh(video)
    assert video.is_missing is False


@pytest.mark.asyncio
async def test_scan_keeps_subtitle_rows_whose_files_are_still_there(db_session, tmp_path):
    """对照用例：盘上什么都没动，第二遍扫描一条也不许删。"""
    root = str(tmp_path)
    _write_video(root, "movie.mp4")
    _write_text(os.path.join(root, "movie.zh.srt"))
    _write_text(os.path.join(root, "movie.en.vtt"))
    source = await _create_source(db_session, name="安静源", path=root)

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)
        result = await ScanService(db_session).scan_source(source.id)

    video = (await db_session.execute(select(Video))).scalars().one()
    stored = await _subtitles_of(db_session, video.id)
    assert result["subtitles_gone"] == 0
    assert [s.language for s in stored] == ["en", "zh"]


@pytest.mark.asyncio
async def test_scan_keeps_hand_registered_subtitle_the_scanner_never_matches(
    db_session, tmp_path
):
    """人手挂上去的字幕扛得过一次真扫描。

    核对问的是「文件还在吗」，不是「扫描那套命名认不认得它」：`另一组字幕.srt`
    不符合 sidecar 的命名，find_subtitle_files 永远匹配不上，按「这轮没扫到就删」
    来写就会每轮悄悄抹掉一条人工登记的轨 —— #134 那条「手工挂的要活得下来」
    是同一个理由。
    """
    from src.services.subtitle_service import SubtitleService

    root = str(tmp_path)
    _write_video(root, "movie.mp4")
    hand = _write_text(os.path.join(root, "另一组字幕.srt"))
    source = await _create_source(db_session, name="手工登记源", path=root)

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)
        video = (await db_session.execute(select(Video))).scalars().one()
        await SubtitleService(db_session).add(video.id, hand)
        result = await ScanService(db_session).scan_source(source.id)

    assert result["subtitles_gone"] == 0
    stored = await _subtitles_of(db_session, video.id)
    assert [s.filepath for s in stored] == [os.path.normpath(hand)]


@pytest.mark.asyncio
async def test_gone_subtitle_announces_once_and_a_quiet_rescan_does_not(
    db_session, tmp_path
):
    """字幕文件没了是变化，要说出口；说完之后没再变的那一轮不能再刷。

    这句同时钉住通知闸门：`subtitles_gone` 不进去的话，#85 那条「零变化的定时
    扫描不发通知」会被一轮又一轮的「1 条字幕文件已不存在」重新撑开。
    """
    root = str(tmp_path)
    _write_video(root, "movie.mp4")
    srt = _write_text(os.path.join(root, "movie.zh.srt"))
    source = await _create_source(db_session, name="字幕消失源", path=root)

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)
        os.remove(srt)
        await ScanService(db_session).scan_source(source.id)
        await ScanService(db_session).scan_source(source.id)

    assert await _notifications(db_session) == [
        ("scan_complete", "视频源 字幕消失源 扫描完成，发现 1 个新视频、1 条字幕"),
        ("scan_complete", "视频源 字幕消失源 扫描完成，发现 0 个新视频，1 条字幕文件已不存在"),
    ]


@pytest.mark.asyncio
async def test_a_source_without_sidecar_capability_is_not_pruned_locally(
    db_session, monkeypatch
):
    """外挂字幕对它关闭的源，那句本地 isfile 不许去处置它的行。

    源类型是可以通过 `PUT /api/sources/{id}` 改的（本地 → 对象存储），库里就可能留着
    指向 `s3://…` 的外挂字幕行；而 `os.path.isfile("s3://…")` 永远是 False。不看能力
    就核对，一次扫描能把这些行整批删掉 —— 而这条路径上根本没有"文件丢了"这回事。
    """
    _patch_storage(
        monkeypatch,
        _FakeStorage(files=[], reachable=True, sidecar_subtitles=False),
    )
    source = VideoSource(name="桶", path="s3://media/shows", type="minio")
    db_session.add(source)
    await db_session.commit()
    video = Video(
        source_id=source.id,
        filepath="s3://media/shows/movie.mp4",
        title="movie",
    )
    db_session.add(video)
    await db_session.commit()
    leftover = Subtitle(
        video_id=video.id,
        filepath="s3://media/shows/movie.zh.srt",
        language="zh",
    )
    db_session.add(leftover)
    await db_session.commit()

    result = await ScanService(db_session).scan_source(source.id)

    assert result["subtitles_gone"] == 0
    assert len(await _subtitles_of(db_session, video.id)) == 1


# ---------------------------------------------------------------------------
# 一轮扫描的两种「半途」：中途按停止，和一个文件写坏了
#
# #176 补的是本文件此前零签字的三格（196 句缺 7 句：`183-184, 238-239, 331-333`）：
# `is_scanning` 这个属性一次也没有被任何用例读过、扫描途中按下停止后剩下的文件到底
# 还扫不扫（`scan_all_active` 那条只钉了"剩下的**源**"，文件那一圈没有）、以及每个
# 文件外面那圈 `except Exception` 到底有没有真的接过一个坏文件 —— 那句「单个文件失败
# 只跳过，不中断整个视频源的扫描」一直只是注释。


@pytest.fixture
def idle_scan_state():
    """进场前把模块级扫描状态收干净，出场也收干净。

    `_scan_state` 是模块级的（每个请求都会新建一个 ScanService，见文件顶部那段注释），
    所以一条用例留下的 `stop_requested` 会让下一条莫名其妙地"一开场就被按了停止"。
    """
    scan_module._reset_scan_state()
    yield scan_module._scan_state
    scan_module._reset_scan_state()


@pytest.mark.asyncio
async def test_is_scanning_property_reports_the_shared_flag_to_other_instances(
    db_session, monkeypatch, idle_scan_state
):
    """扫描进行中，另一个实例读这个属性得说 True。

    进度接口走的是 `get_scan_progress()`，所以这条属性（`183-184`）此前只有 docstring
    说它存在。它和那张字典读的是同一份模块级状态，这一点没人签过。
    """
    source = await _create_source(db_session, name="属性源", path="/lib")
    observed: list[bool] = []

    _patch_storage(
        monkeypatch,
        _FakeStorage(
            on_list=lambda: observed.append(ScanService(db_session).is_scanning)
        ),
    )

    with _no_media_probe():
        await ScanService(db_session).scan_source(source.id)

    assert observed == [True]
    assert ScanService(db_session).is_scanning is False


@pytest.mark.asyncio
async def test_a_scan_that_crashed_leaves_no_spinning_flag(
    db_session, monkeypatch, idle_scan_state
):
    """扫描自己炸了，进度不能永远停在「正在扫描」。

    收尾写在 `_tracked_scan` 的 `finally` 里：不这么写的话，一次列目录失败就把界面永久
    卡在转圈，而 `POST /scan/stop` 又救不回来（按完停止要等下一圈检查才生效）。
    """
    source = await _create_source(db_session, name="崩掉的源", path="/lib")

    class _Unreadable(_FakeStorage):
        def list_videos(self, root: str) -> list[FoundFile]:
            raise RuntimeError("目录读不动")

    _patch_storage(monkeypatch, _Unreadable())

    with pytest.raises(RuntimeError, match="目录读不动"):
        await ScanService(db_session).scan_source(source.id)

    assert ScanService(db_session).is_scanning is False
    assert ScanService(db_session).get_scan_progress()["is_scanning"] is False


@pytest.mark.asyncio
async def test_a_stop_pressed_before_any_scan_started_is_dropped(
    db_session, monkeypatch, idle_scan_state
):
    """按钮按早了不许把下一轮扫描掐死。

    `_tracked_scan` 在最外层进场时把整份状态重置（含 `stop_requested`），所以扫描开始
    之前那一次停止会被丢掉。用例只钉现状并说明它为什么是对的：不丢的话，一次误按会让
    之后的每一轮都刚起步就散场。
    """
    _patch_storage(
        monkeypatch,
        _FakeStorage(files=[_found("/lib/a.mp4"), _found("/lib/b.mp4")]),
    )
    source = await _create_source(db_session, name="提前按停止", path="/lib")
    service = ScanService(db_session)

    await service.stop_scan()
    with _no_media_probe():
        result = await service.scan_source(source.id)

    assert result["new_videos"] == 2


@pytest.mark.asyncio
async def test_a_stop_mid_source_leaves_the_rest_of_the_listing_alone(
    db_session, monkeypatch, caplog, idle_scan_state
):
    """扫描途中按停止：手上这一部收尾，清单里剩下的一个也不碰。

    `238-239` 这两句（那句 log 和那个 `break`）此前零签字：唯一的停止用例把
    `scan_source` 整个换成了替身，所以"文件那一圈也认停止"从来没被演过。
    """
    first = _found("/lib/第一部.mp4")
    second = _found("/lib/第二部.mp4")
    third = _found("/lib/第三部.mp4")
    _patch_storage(monkeypatch, _FakeStorage(files=[first, second, third]))
    source = await _create_source(db_session, name="停止源", path="/lib")
    # 第三部早就在库里，而这一轮根本轮不到它：核对用的是整份清单而不是"处理过的那些"，
    # 所以它不许被记成丢失 —— 按了停止把两部好片子刷成「已找不到」是更坏的结局。
    already = Video(source_id=source.id, filepath=third.locator, title="第三部")
    db_session.add(already)
    await db_session.commit()

    def probe(filepath: str) -> dict:
        if filepath.endswith("第一部.mp4"):
            scan_module._scan_state["stop_requested"] = True
        return {"duration": 20, "format": "mp4"}

    with caplog.at_level(logging.INFO, logger="src.services.scan_service"):
        with patch("src.services.scan_service.extract_video_info", side_effect=probe), patch(
            "src.services.scan_service.generate_thumbnail", return_value=""
        ):
            result = await ScanService(db_session).scan_source(source.id)

    stored = (await db_session.execute(select(Video.title).order_by(Video.id))).scalars().all()
    assert list(stored) == ["第三部", "第一部"]
    assert result["new_videos"] == 1
    # 说的是清单有几部，不是处理了几部 —— 停止的那一轮这两个数就是不一样。
    assert result["files_found"] == 3
    assert "扫描已按请求停止: 停止源" in caplog.text
    await db_session.refresh(already)
    assert already.is_missing is False
    # 第二块选项板②甲（#182）：半途停掉的一轮**不许**写成"刚刚扫过"。这一列是自动扫描
    # 用来决定下一次什么时候来的，记了时间就等于宣布这一轮把清单扫完了；而这一轮明明还有
    # 两个文件没碰。通知照旧发（那说的是"这一轮发现了什么"，不是心跳），措辞不改是他选的
    # 另一头——"保留时间戳、只改通知文案"那一案被他否掉了。
    assert source.last_scan_at is None
    assert await _notifications(db_session) == [
        ("scan_complete", "视频源 停止源 扫描完成，发现 1 个新视频")
    ]


class _StorageByRoot(_FakeStorage):
    """按根目录给不同清单：一条 `scan_all_active` 路上要看两个源。"""

    def __init__(self, by_root: dict[str, list[FoundFile]]) -> None:
        super().__init__()
        self._by_root = by_root

    def list_videos(self, root: str) -> list[FoundFile]:
        self.listed_paths.append(root)
        return self._by_root.get(root, [])


@pytest.mark.asyncio
async def test_a_stop_set_inside_one_source_also_skips_the_next(
    db_session, monkeypatch, idle_scan_state
):
    """内层扫描收尾时不许把停止请求一起抹掉。

    `scan_all_active` 把每个 `scan_source` 包在自己的 `_tracked_scan` 里，靠 `outermost`
    那道闸门决定谁才配重置状态。把收尾改成无条件重置的话，第一个源里按下的停止会被
    内层那一下抹平，第二个源照扫 —— 也就是「按了停止只停了一半」。
    """
    root_a, root_b = "/lib/a", "/lib/b"
    _patch_storage(
        monkeypatch,
        _StorageByRoot(
            {
                root_a: [_found("/lib/a/1.mp4"), _found("/lib/a/2.mp4")],
                root_b: [_found("/lib/b/1.mp4")],
            }
        ),
    )
    await _create_source(db_session, name="源一", path=root_a)
    await _create_source(db_session, name="源二", path=root_b)

    calls: list[str] = []

    def stop_on_first_probe(filepath: str) -> dict:
        calls.append(filepath)
        scan_module._scan_state["stop_requested"] = True
        return {"duration": 20, "format": "mp4"}

    with patch(
        "src.services.scan_service.extract_video_info", side_effect=stop_on_first_probe
    ), patch("src.services.scan_service.generate_thumbnail", return_value=""):
        result = await ScanService(db_session).scan_all_active()

    rows = (await db_session.execute(select(Video))).scalars().all()
    assert result["sources_scanned"] == 1
    assert result["total_new_videos"] == 1
    assert len(rows) == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_file_that_broke_mid_write_is_skipped_and_the_round_survives(
    db_session, monkeypatch, caplog, idle_scan_state
):
    """一个文件写库写到一半炸了：半截行不许留下，后面那个文件不许陪葬。

    每个文件自己那层 SAVEPOINT（`begin_nested`）和外圈那圈 `except Exception` 在这之前
    一次也没被真触发过。真机上它是唯一挡住"一个坏文件让整轮扫描 500"的东西。
    """
    _patch_storage(
        monkeypatch,
        _FakeStorage(
            files=[
                _found("/lib/好片一.mp4"),
                _found("/lib/坏片.mp4"),
                _found("/lib/好片二.mp4"),
            ]
        ),
    )
    source = await _create_source(db_session, name="含坏文件的源", path="/lib")
    real_register = scan_module._register_subtitles

    def register(service, video_id, video_filepath, known, storage):
        if "坏片" in video_filepath:
            raise RuntimeError("这条片子的字幕写不进库")
        return real_register(service, video_id, video_filepath, known, storage)

    monkeypatch.setattr(scan_module, "_register_subtitles", register)

    with caplog.at_level(logging.WARNING, logger="src.services.scan_service"):
        with _no_media_probe():
            result = await ScanService(db_session).scan_source(source.id)

    titles = sorted(
        video.title for video in (await db_session.execute(select(Video))).scalars().all()
    )
    assert titles == ["好片一", "好片二"]
    assert result["new_videos"] == 2
    skipped = [
        record
        for record in caplog.records
        if "跳过无法处理的视频文件" in record.getMessage()
    ]
    assert len(skipped) == 1
    assert "/lib/坏片.mp4" in skipped[0].getMessage()
    # 回溯必须留在日志里：只报"跳过了"而不带原因，运维就只能猜。
    assert skipped[0].exc_info is not None


@pytest.mark.asyncio
async def test_a_file_skipped_by_one_failure_is_indexed_the_next_round(
    db_session, monkeypatch, idle_scan_state
):
    """跳过是一次性的：下一轮它修好了就该正常建档。

    要是失败把半截行留在库里（或者被记成"已认识"），第二轮就会走 `existing` 那条
    continue 永远跳过它 —— 界面上看就是"这片子再也扫不进来了"。
    """
    _patch_storage(monkeypatch, _FakeStorage(files=[_found("/lib/坏一次.mp4")]))
    source = await _create_source(db_session, name="重试源", path="/lib")
    broken = {"fail": True}
    real_register = scan_module._register_subtitles

    def register(service, video_id, video_filepath, known, storage):
        if broken["fail"]:
            raise RuntimeError("第一轮它就是写不进去")
        return real_register(service, video_id, video_filepath, known, storage)

    monkeypatch.setattr(scan_module, "_register_subtitles", register)

    with _no_media_probe():
        first = await ScanService(db_session).scan_source(source.id)
        broken["fail"] = False
        second = await ScanService(db_session).scan_source(source.id)

    assert first["new_videos"] == 0
    assert second["new_videos"] == 1
    rows = (await db_session.execute(select(Video))).scalars().all()
    assert [video.title for video in rows] == ["坏一次"]


@pytest.mark.asyncio
async def test_a_known_videos_subtitle_failure_still_takes_the_round_down(
    db_session, monkeypatch, idle_scan_state
):
    """「单个文件失败只跳过」今天只护着新片那半圈 —— 本单量出，钉的是现状。

    老片走的是 `known is not None` 那一条 continue，它同样调 `_register_subtitles`，但那
    一句在 `try` 外面（`try` 从新片那一段才开始）。所以库里已有一部片子的字幕写不进
    去时，异常穿出 `scan_source`：这一轮的 `last_scan_at` 不写、通知不发，清单里剩下的
    文件一个也没扫 —— 而同一份清单里一部新片出同样的毛病却只是跳过。真字幕注册今天只
    做 add/flush、炸不出来，所以这一条没有现成的坏输入；把它钉住是为了让"两半圈对称"
    这个改法一定要有用例跟着翻，不是认可现状。
    """
    first = _found("/lib/老片一.mp4")
    second = _found("/lib/老片二.mp4")
    _patch_storage(monkeypatch, _FakeStorage(files=[first, second], sidecar_subtitles=True))
    source = await _create_source(db_session, name="老片坏字幕", path="/lib")
    for locator, title in ((first.locator, "老片一"), (second.locator, "老片二")):
        db_session.add(Video(source_id=source.id, filepath=locator, title=title))
    await db_session.commit()

    def register(service, video_id, video_filepath, known, storage):
        if "老片二" in video_filepath:
            raise RuntimeError("这条老片的字幕写不进库")
        return 0

    monkeypatch.setattr(scan_module, "_register_subtitles", register)

    with _no_media_probe():
        with pytest.raises(RuntimeError, match="这条老片的字幕写不进库"):
            await ScanService(db_session).scan_source(source.id)

    # 整轮死在半路：这一轮的写入没提交，界面从此读不到"扫过"，进度也不再转圈。
    assert source.last_scan_at is None
    assert await _notifications(db_session) == []
    assert ScanService(db_session).is_scanning is False
