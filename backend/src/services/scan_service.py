"""ScanService for scanning video sources and discovering new videos."""
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.source import VideoSource
from src.models.video import Video
from src.models.new_video import NewVideo
from src.services.notification_service import NotificationService
from src.utils.file_scanner import scan_directory, extract_video_info, generate_thumbnail
from src.config import settings


class ScanService:
    """Service for scanning video sources to discover new videos."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._scanning: bool = False
        self._progress: dict[str, Any] = {
            "is_scanning": False,
            "current_source": None,
            "sources_total": 0,
            "sources_completed": 0,
            "files_found": 0,
            "new_videos": 0,
        }

    @property
    def is_scanning(self) -> bool:
        """Return whether a scan is currently in progress."""
        return self._scanning

    async def scan_source(self, source_id: int) -> dict:
        """Scan a single video source for new videos.

        Returns a summary dict with keys: source_id, files_found, new_videos.
        """
        source_result = await self.session.execute(
            select(VideoSource).where(VideoSource.id == source_id)
        )
        source = source_result.scalar_one_or_none()
        if not source:
            raise ValueError(f"Source with id {source_id} not found")

        self._scanning = True
        self._progress["is_scanning"] = True
        self._progress["current_source"] = source.name

        files_found = 0
        new_videos = 0

        try:
            # Scan the directory for video files
            video_files = scan_directory(source.path)
            files_found = len(video_files)

            # Get existing filepaths for this source
            existing_result = await self.session.execute(
                select(Video.filepath).where(Video.source_id == source_id)
            )
            existing_paths = {row[0] for row in existing_result.all()}

            for vf in video_files:
                filepath = vf["filepath"]
                if filepath in existing_paths:
                    continue

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
                video = Video(
                    source_id=source_id,
                    filepath=filepath,
                    title=os.path.splitext(os.path.basename(filepath))[0],
                    duration=info.get("duration"),
                    file_size=vf.get("file_size"),
                    format=info.get("format"),
                    resolution=info.get("resolution"),
                    thumbnail_path=thumbnail_path or None,
                )
                self.session.add(video)
                await self.session.flush()  # Get video.id

                # Create new video entry
                new_video = NewVideo(
                    video_id=video.id,
                    source_id=source_id,
                )
                self.session.add(new_video)
                new_videos += 1

            # Update source last_scan_at
            source.last_scan_at = datetime.now(timezone.utc)
            await self.session.commit()

            # Create scan completion notification
            notification_service = NotificationService(self.session)
            await notification_service.create(
                type="scan_complete",
                title="扫描完成",
                message=f"视频源 {source.name} 扫描完成，发现 {new_videos} 个新视频",
                data={"source_id": source_id, "new_count": new_videos},
            )

        finally:
            self._scanning = False
            self._progress["is_scanning"] = False
            self._progress["current_source"] = None

        return {
            "source_id": source_id,
            "files_found": files_found,
            "new_videos": new_videos,
        }

    async def scan_all_active(self) -> dict:
        """Scan all active video sources.

        Returns a summary dict with keys: sources_scanned, total_files, total_new_videos.
        """
        result = await self.session.execute(
            select(VideoSource).where(VideoSource.is_active == True)  # noqa: E712
        )
        sources = list(result.scalars().all())

        self._scanning = True
        self._progress["is_scanning"] = True
        self._progress["sources_total"] = len(sources)
        self._progress["sources_completed"] = 0

        total_files = 0
        total_new = 0

        try:
            for source in sources:
                self._progress["current_source"] = source.name
                scan_result = await self.scan_source(source.id)
                total_files += scan_result["files_found"]
                total_new += scan_result["new_videos"]
                self._progress["sources_completed"] += 1
        finally:
            self._scanning = False
            self._progress["is_scanning"] = False
            self._progress["current_source"] = None

        return {
            "sources_scanned": len(sources),
            "total_files": total_files,
            "total_new_videos": total_new,
        }

    def get_scan_progress(self) -> dict:
        """Get the current scan progress."""
        return dict(self._progress)

    async def stop_scan(self) -> None:
        """Request stopping the current scan.

        Sets the scanning flag to False so the current scan iteration
        will complete but no further sources will be processed.
        """
        self._scanning = False
        self._progress["is_scanning"] = False
