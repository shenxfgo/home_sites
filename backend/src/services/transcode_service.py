"""TranscodeService for video transcoding operations."""
import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database.session import async_session_maker
from src.models.transcode_output import TranscodeOutput
from src.models.video import Video
from src.services.notification_service import NotificationService
from src.storage import UnsupportedStorageError, storage_for_locator
from src.utils.ffmpeg import (
    check_format_support,
    get_supported_formats,
    transcode_video,
)

logger = logging.getLogger(__name__)


def product_path(input_path: str, target_format: str, video_id: int) -> Path:
    """这一份产物的去处：``<输出目录>/<影片 id>/<源文件名去扩展>.<格式>``。

    从前它写的是 ``Path(input_path).with_suffix(...)``，也就是**源的旁边**——而那个
    目录正是扫描范围（扫描只看 ``VideoSource.path``，且 ``os.walk`` 一路下潜、没有
    排除机制），于是下一轮扫描把产物当成一部新片子登记进库，同一部片子还能再转一遍
    （#154）。按影片 id 分子目录是命名布局定下的那一半：两个片源里的同名片子（``data/a/
    movie.mp4`` 与 ``backups/movie.mp4``）在平铺布局下会互相覆盖，ffmpeg 带 ``-y``，
    覆盖是静默发生的。
    """
    return (
        Path(settings.transcode_output_dir)
        / str(video_id)
        / f"{Path(input_path).stem}.{target_format}"
    )


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
        # 归一在这里做，不在闸门里做：闸门 ``check_format_support`` 大小写不敏感，而
        # 编码器查表和输出文件的扩展名用的都是原串。只归一其中一处，"MKV" 会先被闸门
        # 放行（HTTP 200「已启动」），再在后台失败成「不支持的格式：MKV」。
        target_format = target_format.lower()

        # Validate format
        if not check_format_support(target_format):
            raise ValueError(f"不支持的格式：{target_format}")

        # Get video
        result = await self.session.execute(
            select(Video).where(Video.id == video_id)
        )
        video = result.scalar_one_or_none()
        if not video:
            raise ValueError(f"视频 #{video_id} 不存在")

        running = _jobs.get(video_id)
        if running and running.status == "running":
            raise ValueError("这部视频正在转码中")

        # FFmpeg 只认本地路径。把对象存储的 locator 直接丢给它，得到的是一句
        # "文件不存在"——那是假话，所以先向存储层要路径，要不到就说明是这类源
        # 暂不支持转码，而不是文件丢了。
        try:
            input_path = storage_for_locator(video.filepath).local_path(
                video.filepath
            )
        except UnsupportedStorageError as exc:
            raise ValueError(str(exc)) from exc
        if not Path(input_path).is_file():
            raise ValueError(f"视频文件不存在：{input_path}")

        # 输出目录独立之后，同格式不再会**覆盖**源文件，但它仍然会让产物和源同名：
        # 库里的 `movie.mkv` 和产物表里的 `movie.mkv` 在人眼里是同一行，而这一单买的就是
        # "产物看得见"。闸门因此留着，挡的理由换了一个。
        if Path(input_path).suffix.lower().lstrip(".") == target_format:
            raise ValueError(
                f"目标格式与源文件相同（{target_format}），"
                "产物会和源文件同名"
            )

        output = product_path(input_path, target_format, video_id)
        # 目录在这里建，不在 ffmpeg 里建：那一步失败会以"转码失败"的面目出现在界面上，
        # 而真实原因是没地方写。
        output.parent.mkdir(parents=True, exist_ok=True)
        output_path = str(output)

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
                await self._record_output(job)
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

    async def _record_output(self, job: TranscodeJob) -> None:
        """登记这一份产物。独立会话，理由与 :meth:`_notify` 同一条。

        只有成功那一路会走到这里：失败的产物压根不存在，取消的那一路 ffmpeg 已经把半截
        文件 unlink 掉了（``utils/ffmpeg.py``）。写进表里一条"存在过、其实没有"的行，正是
        这一单要修掉的那种谎。
        """
        try:
            async with async_session_maker() as session:
                row = await session.scalar(
                    select(TranscodeOutput).where(
                        TranscodeOutput.video_id == job.video_id,
                        TranscodeOutput.target_format == job.target_format,
                    )
                )
                if row is None:
                    row = TranscodeOutput(video_id=job.video_id, target_format=job.target_format)
                    session.add(row)
                # 同一片子同一种容器写的是同一个路径（`product_path`），所以重做是这一行
                # 被更新，不是多出一行。
                row.output_path = job.output_path
                row.created_at = datetime.now(timezone.utc)
                row.deleted_at = None
                await session.commit()
        except Exception:
            logger.exception("Failed to record transcode product for video %s", job.video_id)

    async def list_outputs(self, video_id: int) -> list[dict]:
        """这一部的产物，新做的在前；顺带把"文件还在不在"当场核对一次。

        这次核对是 ``deleted_at`` **唯一的写的人**：产物目录在所有片源之外，扫描走不到它
        （见 :func:`product_path`），除了这里没人能说得出"那份文件没了"。人手工删掉一份
        产物腾磁盘是真会发生的事，而那正是这一列要说的话。反方向也一并翻回来 —— 文件被
        放回去（误删后恢复、换盘）时标记必须清掉，否则这一列会从漏报变成误报，一样是谎。
        """
        result = await self.session.execute(
            select(TranscodeOutput)
            .where(TranscodeOutput.video_id == video_id)
            .order_by(TranscodeOutput.created_at.desc(), TranscodeOutput.id.desc())
        )
        rows = list(result.scalars().all())

        now = datetime.now(timezone.utc)
        products: list[dict] = []
        changed = False
        for row in rows:
            path = Path(row.output_path)
            size = path.stat().st_size if path.is_file() else None
            missing = size is None
            if missing != (row.deleted_at is not None):
                row.deleted_at = now if missing else None
                changed = True
            products.append(
                {
                    "id": row.id,
                    "target_format": row.target_format,
                    "output_path": row.output_path,
                    "size_bytes": size,
                    "created_at": row.created_at,
                    "deleted_at": row.deleted_at,
                }
            )
        if changed:
            await self.session.commit()
        return products

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
            raise ValueError(f"视频 #{video_id} 没有正在进行的转码任务")

        if job.task:
            job.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await job.task
        if job.status == "running":
            job.status = "cancelled"

    def get_supported_formats(self) -> list[dict]:
        """Get list of supported formats."""
        return get_supported_formats()
