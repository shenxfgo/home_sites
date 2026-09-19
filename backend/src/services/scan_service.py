"""ScanService for scanning video sources and discovering new videos."""
import asyncio
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.source import VideoSource
from src.models.tag import Tag
from src.models.video import Video
from src.models.new_video import NewVideo
from src.services.notification_service import NotificationService
from src.services.subtitle_service import SubtitleService
from src.utils.file_scanner import scan_directory, extract_video_info, generate_thumbnail
from src.utils.name_parser import auto_tags, parse_video_filename
from src.utils.subtitles import find_subtitle_files
from src.config import settings

logger = logging.getLogger(__name__)


# FastAPI builds a new ScanService per request, so scan state has to live at
# module level: a per-request instance can neither report a running scan to
# GET /scan/progress nor receive a stop from POST /scan/stop.
_scan_state: dict[str, Any] = {}

_PUBLIC_PROGRESS_KEYS = (
    "is_scanning",
    "current_source",
    "sources_total",
    "sources_completed",
    "files_found",
    "new_videos",
)


def _reset_scan_state() -> None:
    """Return the shared scan state to the idle baseline."""
    _scan_state.update(
        {
            "is_scanning": False,
            "current_source": None,
            "sources_total": 0,
            "sources_completed": 0,
            "files_found": 0,
            "new_videos": 0,
            "active_scans": 0,
            "stop_requested": False,
        }
    )


_reset_scan_state()


@contextmanager
def _tracked_scan() -> Iterator[None]:
    """Publish the progress of a running scan and reset it when it ends.

    Nested use is expected: ``scan_all_active`` wraps the ``scan_source`` calls
    it makes, so only the outermost scan resets the counters and clears the
    scanning flag.
    """
    outermost = _scan_state["active_scans"] == 0
    if outermost:
        _reset_scan_state()
        _scan_state["is_scanning"] = True
    _scan_state["active_scans"] += 1
    try:
        yield
    finally:
        _scan_state["active_scans"] -= 1
        if outermost:
            _reset_scan_state()


def _register_subtitles(
    service: SubtitleService,
    video_id: int,
    video_filepath: str,
    known: set[str],
) -> int:
    """Register a video's sidecar subtitle files, skipping the known ones."""
    return sum(
        service.register(video_id, subtitle_file, known)
        for subtitle_file in find_subtitle_files(video_filepath)
    )


async def _tag_index(session: AsyncSession) -> dict[str, Tag]:
    """Existing tags by name, so a scan creates each new one exactly once."""
    result = await session.execute(select(Tag))
    return {tag.name: tag for tag in result.scalars().all()}


async def _resolve_tags(
    session: AsyncSession,
    index: dict[str, Tag],
    names: tuple[str, ...],
) -> list[Tag]:
    """Map tag names onto rows, creating the ones the library has not seen."""
    tags = []
    for name in names:
        tag = index.get(name)
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            await session.flush()
            index[name] = tag
        tags.append(tag)
    return tags


async def _backfill_coordinates(
    session: AsyncSession,
    video: Video,
    index: dict[str, Tag],
    filename: str,
) -> None:
    """Fill series coordinates into a row written before the parser existed.

    Only an empty ``series`` is written and auto tags are appended, so a title
    or tag set someone curated by hand is left alone.
    """
    if video.series is not None:
        return
    parsed = parse_video_filename(filename)
    if parsed.series is None:
        return
    video.series = parsed.series
    video.season = parsed.season
    video.episode = parsed.episode
    auto = await _resolve_tags(session, index, auto_tags(parsed))
    video.tags = [*video.tags, *[tag for tag in auto if tag not in video.tags]]


class ScanService:
    """Service for scanning video sources to discover new videos."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def is_scanning(self) -> bool:
        """Return whether a scan is currently in progress."""
        return _scan_state["is_scanning"]

    async def scan_source(self, source_id: int) -> dict:
        """Scan a single video source for new videos and subtitles.

        Returns a summary dict with keys: source_id, files_found, new_videos,
        subtitles_found.
        """
        source_result = await self.session.execute(
            select(VideoSource).where(VideoSource.id == source_id)
        )
        source = source_result.scalar_one_or_none()
        if not source:
            raise ValueError(f"Source with id {source_id} not found")

        files_found = 0
        new_videos = 0
        subtitles_found = 0

        with _tracked_scan():
            _scan_state["current_source"] = source.name
            # Scan the directory for video files
            video_files = scan_directory(source.path)
            files_found = len(video_files)
            _scan_state["files_found"] += files_found

            # Get existing videos of this source, keyed by path
            existing_result = await self.session.execute(
                select(Video).where(Video.source_id == source_id)
            )
            existing = {video.filepath: video for video in existing_result.scalars().all()}

            subtitle_service = SubtitleService(self.session)
            known_subtitles = await subtitle_service.known_paths(source_id)
            tags_by_name = await _tag_index(self.session)

            for vf in video_files:
                if _scan_state["stop_requested"]:
                    logger.info("扫描已按请求停止: %s", source.name)
                    break

                filepath = vf["filepath"]
                known = existing.get(filepath)
                if known is not None:
                    await _backfill_coordinates(
                        self.session, known, tags_by_name, vf["filename"]
                    )
                    subtitles_found += _register_subtitles(
                        subtitle_service, known.id, filepath, known_subtitles
                    )
                    continue

                # 单个文件失败只跳过，不中断整个视频源的扫描
                try:
                    async with self.session.begin_nested():
                        # Extract video info
                        info = extract_video_info(filepath)

                        # Generate thumbnail
                        thumbnail_path = ""
                        if settings.thumbnail_path:
                            thumb_filename = (
                                os.path.splitext(os.path.basename(filepath))[0] + ".jpg"
                            )
                            thumbnail_path = os.path.join(
                                settings.thumbnail_path, str(source_id), thumb_filename
                            )
                            # Run thumbnail generation in a thread to avoid blocking
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                None, generate_thumbnail, filepath, thumbnail_path
                            )
                            if not thumbnail_path or not os.path.exists(thumbnail_path):
                                thumbnail_path = ""

                        # Create video record
                        parsed = parse_video_filename(vf["filename"])
                        video = Video(
                            source_id=source_id,
                            filepath=filepath,
                            title=parsed.title,
                            duration=info.get("duration"),
                            file_size=vf.get("file_size"),
                            format=info.get("format"),
                            resolution=info.get("resolution"),
                            thumbnail_path=thumbnail_path or None,
                            series=parsed.series,
                            season=parsed.season,
                            episode=parsed.episode,
                        )
                        video.tags = await _resolve_tags(
                            self.session, tags_by_name, auto_tags(parsed)
                        )
                        self.session.add(video)
                        await self.session.flush()  # Get video.id

                        # Create new video entry
                        new_video = NewVideo(
                            video_id=video.id,
                            source_id=source_id,
                        )
                        self.session.add(new_video)
                        await self.session.flush()

                        subtitles_found += _register_subtitles(
                            subtitle_service, video.id, filepath, known_subtitles
                        )
                    new_videos += 1
                    _scan_state["new_videos"] += 1
                except Exception:
                    logger.warning("跳过无法处理的视频文件: %s", filepath, exc_info=True)
                    continue

            # Update source last_scan_at
            source.last_scan_at = datetime.now(timezone.utc)
            # A row whose file the scan could not find is marked lost rather
            # than deleted, but only when the source itself was reachable: an
            # unmounted share returns an empty listing and must not black out
            # the whole library.
            if os.path.isdir(source.path):
                found = {vf["filepath"] for vf in video_files}
                for video in existing.values():
                    video.is_missing = video.filepath not in found
            await self.session.commit()

            # Create scan completion notification
            notification_service = NotificationService(self.session)
            await notification_service.create(
                type="scan_complete",
                title="扫描完成",
                message=f"视频源 {source.name} 扫描完成，发现 {new_videos} 个新视频",
                data={"source_id": source_id, "new_count": new_videos},
            )

        return {
            "source_id": source_id,
            "files_found": files_found,
            "new_videos": new_videos,
            "subtitles_found": subtitles_found,
        }

    async def scan_all_active(self) -> dict:
        """Scan all active video sources.

        Returns a summary dict with keys: sources_scanned, total_files,
        total_new_videos, total_subtitles.
        """
        result = await self.session.execute(
            select(VideoSource).where(VideoSource.is_active == True)  # noqa: E712
        )
        sources = list(result.scalars().all())

        total_files = 0
        total_new = 0
        total_subtitles = 0
        scanned = 0

        with _tracked_scan():
            _scan_state["sources_total"] = len(sources)
            for source in sources:
                if _scan_state["stop_requested"]:
                    logger.info("剩余视频源已按请求跳过扫描")
                    break
                _scan_state["current_source"] = source.name
                scan_result = await self.scan_source(source.id)
                total_files += scan_result["files_found"]
                total_new += scan_result["new_videos"]
                total_subtitles += scan_result["subtitles_found"]
                scanned += 1
                _scan_state["sources_completed"] += 1

        return {
            "sources_scanned": scanned,
            "total_files": total_files,
            "total_new_videos": total_new,
            "total_subtitles": total_subtitles,
        }

    def get_scan_progress(self) -> dict:
        """Get the current scan progress."""
        return {key: _scan_state[key] for key in _PUBLIC_PROGRESS_KEYS}

    async def stop_scan(self) -> None:
        """Request stopping the current scan.

        A running scan reads this shared flag between files and between
        sources, so it finishes the item in hand and then stops.
        """
        _scan_state["stop_requested"] = True
