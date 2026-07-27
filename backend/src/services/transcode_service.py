"""TranscodeService for video transcoding operations."""
import asyncio
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.video import Video
from src.utils.ffmpeg import transcode_video, check_format_support, get_supported_formats
from src.services.notification_service import NotificationService


class TranscodeService:
    """Service for video transcoding."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._active_tasks: dict[int, asyncio.Task] = {}

    async def transcode(self, video_id: int, target_format: str) -> dict:
        """Start transcoding a video."""
        # Validate format
        if not check_format_support(target_format):
            raise ValueError(f"Unsupported format: {target_format}")

        # Get video
        result = await self.session.execute(
            select(Video).where(Video.id == video_id)
        )
        video = result.scalar_one_or_none()
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        # Check if already transcoding
        if video_id in self._active_tasks:
            raise ValueError("Video is already being transcoded")

        # Build output path
        input_path = video.filepath
        output_path = str(Path(input_path).with_suffix(f".{target_format}"))

        # Start transcoding task
        task = asyncio.create_task(
            self._do_transcode(video_id, input_path, output_path, target_format)
        )
        self._active_tasks[video_id] = task

        return {
            "video_id": video_id,
            "status": "started",
            "target_format": target_format,
            "output_path": output_path,
        }

    async def _do_transcode(
        self, video_id: int, input_path: str, output_path: str, target_format: str
    ) -> None:
        """Perform the actual transcoding."""
        try:
            # Run transcoding in thread pool
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None, transcode_video, input_path, output_path, target_format
            )

            # Create notification
            notification_service = NotificationService(self.session)
            if success:
                await notification_service.create(
                    type="transcode_complete",
                    title="转码完成",
                    message=f"视频已成功转码为 {target_format} 格式",
                    data={"video_id": video_id, "format": target_format},
                )
            else:
                await notification_service.create(
                    type="transcode_error",
                    title="转码失败",
                    message=f"视频转码为 {target_format} 格式失败",
                    data={"video_id": video_id, "format": target_format},
                )
        finally:
            # Remove from active tasks
            self._active_tasks.pop(video_id, None)

    async def get_status(self, video_id: int) -> dict:
        """Get transcoding status."""
        is_active = video_id in self._active_tasks
        return {
            "video_id": video_id,
            "is_transcoding": is_active,
            "status": "transcoding" if is_active else "idle",
        }

    async def cancel(self, video_id: int) -> None:
        """Cancel an active transcoding task."""
        task = self._active_tasks.get(video_id)
        if not task:
            raise ValueError(f"No active transcoding for video {video_id}")

        task.cancel()
        self._active_tasks.pop(video_id, None)

    def get_supported_formats(self) -> list[dict]:
        """Get list of supported formats."""
        return get_supported_formats()
