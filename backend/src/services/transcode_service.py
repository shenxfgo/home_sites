"""TranscodeService for video transcoding operations."""
import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import async_session_maker
from src.models.video import Video
from src.services.notification_service import NotificationService
from src.storage import UnsupportedStorage, storage_for_locator
from src.utils.ffmpeg import (
    transcode_video,
    check_format_support,
    get_supported_formats,
)

logger = logging.getLogger(__name__)


@dataclass
class TranscodeJob:
    """State of a single background transcode."""

    video_id: int
    target_format: str
    output_path: str
    status: str = "running"  # running | completed | failed | cancelled
    progress: float = 0.0
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


# FastAPI builds a new TranscodeService per request, so the task registry has
# to live at module level for status polling and cancel to see running jobs.
_jobs: dict[int, TranscodeJob] = {}


class TranscodeService:
    """Service for video transcoding."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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

        running = _jobs.get(video_id)
        if running and running.status == "running":
            raise ValueError("Video is already being transcoded")

        # FFmpeg 只认本地路径。把对象存储的 locator 直接丢给它，得到的是一句
        # "文件不存在"——那是假话，所以先向存储层要路径，要不到就说明是这类源
        # 暂不支持转码，而不是文件丢了。
        try:
            input_path = storage_for_locator(video.filepath).local_path(
                video.filepath
            )
        except UnsupportedStorage as exc:
            raise ValueError(str(exc)) from exc
        if not Path(input_path).is_file():
            raise ValueError(f"Video file not found: {input_path}")

        output_path = str(Path(input_path).with_suffix(f".{target_format}"))
        if Path(output_path) == Path(input_path):
            raise ValueError(
                f"Target format matches the source format ({target_format}); "
                "transcoding would overwrite the original file"
            )

        job = TranscodeJob(
            video_id=video_id,
            target_format=target_format,
            output_path=output_path,
        )
        job.task = asyncio.create_task(
            self._run(job, input_path, video.duration)
        )
        _jobs[video_id] = job

        return {
            "video_id": video_id,
            "status": "started",
            "target_format": target_format,
            "output_path": output_path,
        }

    async def _run(
        self, job: TranscodeJob, input_path: str, duration: int | None
    ) -> None:
        """Perform the actual transcoding, updating the shared job state."""
        try:
            success, error = await transcode_video(
                input_path,
                job.output_path,
                job.target_format,
                total_duration=duration,
                on_progress=lambda pct: setattr(job, "progress", pct),
            )
            job.status = "completed" if success else "failed"
            job.error = error
            if success:
                job.progress = 100.0
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except Exception as exc:
            logger.exception("Transcode crashed for video %s", job.video_id)
            job.status = "failed"
            job.error = str(exc)

        await self._notify(job)

    async def _notify(self, job: TranscodeJob) -> None:
        """Record the outcome as a notification using an independent session.

        The request-scoped session is closed once the response is returned, so
        a background task cannot reuse it.
        """
        completed = job.status == "completed"
        try:
            async with async_session_maker() as session:
                await NotificationService(session).create(
                    type="transcode_complete" if completed else "transcode_error",
                    title="转码完成" if completed else "转码失败",
                    message=(
                        f"视频已成功转码为 {job.target_format} 格式"
                        if completed
                        else f"视频转码为 {job.target_format} 格式失败："
                             f"{job.error or '未知原因'}"
                    ),
                    data={"video_id": job.video_id, "format": job.target_format},
                )
        except Exception:
            logger.exception("Failed to write transcode notification for video %s", job.video_id)

    async def get_status(self, video_id: int) -> dict:
        """Get transcoding status."""
        job = _jobs.get(video_id)
        if not job:
            return {
                "video_id": video_id,
                "is_transcoding": False,
                "status": "idle",
                "progress": 0.0,
                "target_format": None,
                "output_path": None,
                "error": None,
            }

        return {
            "video_id": video_id,
            "is_transcoding": job.status == "running",
            "status": job.status,
            "progress": round(job.progress, 1),
            "target_format": job.target_format,
            "output_path": job.output_path,
            "error": job.error,
        }

    async def cancel(self, video_id: int) -> None:
        """Cancel an active transcoding task."""
        job = _jobs.get(video_id)
        if not job or job.status != "running":
            raise ValueError(f"No active transcoding for video {video_id}")

        if job.task:
            job.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await job.task
        if job.status == "running":
            job.status = "cancelled"

    def get_supported_formats(self) -> list[dict]:
        """Get list of supported formats."""
        return get_supported_formats()
