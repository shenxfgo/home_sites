"""SubtitleService for managing subtitle tracks attached to videos."""
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.subtitle import Subtitle
from src.models.video import Video
from src.storage import storage_for_locator


class SubtitleService:
    """Service for managing a video's subtitle tracks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_video(self, video_id: int) -> list[Subtitle]:
        """List the subtitle tracks of a video."""
        result = await self.session.execute(
            select(Subtitle)
            .where(Subtitle.video_id == video_id)
            .order_by(Subtitle.id)
        )
        return list(result.scalars().all())

    async def get_subtitle(self, video_id: int, subtitle_id: int) -> Subtitle | None:
        """Get one subtitle track of a video."""
        result = await self.session.execute(
            select(Subtitle).where(
                Subtitle.id == subtitle_id, Subtitle.video_id == video_id
            )
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        video_id: int,
        filepath: str,
        language: str | None = None,
        label: str | None = None,
    ) -> Subtitle:
        """Register an existing subtitle file as a track of a video."""
        video = await self.session.get(Video, video_id)
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        # 外挂字幕的前提是"视频旁边有个目录可以挂文件"，对象存储没有目录；而且
        # 下面那道目录包含检查用的是本地路径词法，套在 s3:// 地址上会得出错误的
        # 结论，所以先按能力挡掉，别让它退化成一句"字幕必须位于视频所在目录内"。
        if not storage_for_locator(video.filepath).capabilities.sidecar_subtitles:
            raise ValueError("外挂字幕只支持本地或 NAS 视频源，对象存储上的影片挂不了字幕文件")

        normalized = os.path.normpath(filepath)
        if not os.path.isfile(normalized):
            raise ValueError("字幕文件不存在")

        video_dir = os.path.dirname(os.path.abspath(video.filepath))
        if not _within(video_dir, os.path.abspath(normalized)):
            raise ValueError("字幕文件必须位于视频所在目录内")

        subtitle = Subtitle(
            video_id=video_id,
            filepath=normalized,
            language=language or _language_of(normalized, video.filepath),
            label=label or _label_of(normalized, video.filepath),
        )
        self.session.add(subtitle)
        await self.session.commit()
        await self.session.refresh(subtitle)
        return subtitle

    async def delete(self, video_id: int, subtitle_id: int) -> None:
        """Remove a subtitle track record."""
        subtitle = await self.get_subtitle(video_id, subtitle_id)
        if not subtitle:
            raise ValueError(f"Subtitle with id {subtitle_id} not found")

        await self.session.delete(subtitle)
        await self.session.commit()

    async def get_video(self, video_id: int) -> Video | None:
        """Get the video row, so its file can be probed for embedded tracks."""
        return await self.session.get(Video, video_id)

    async def known_paths(self, source_id: int) -> set[str]:
        """Return every subtitle path already registered for a source's videos.

        The scan uses this as a single-query dedupe set instead of hitting the
        database once per video file.
        """
        result = await self.session.execute(
            select(Subtitle.filepath)
            .join(Video, Video.id == Subtitle.video_id)
            .where(Video.source_id == source_id)
        )
        return {_norm(row[0]) for row in result.all()}

    def register(
        self,
        video_id: int,
        subtitle_file: dict,
        known: set[str],
    ) -> bool:
        """Add a discovered sidecar file unless it is already registered.

        ``known`` is updated in place so a repeated scan stays idempotent.
        """
        path = _norm(subtitle_file["filepath"])
        if path in known:
            return False

        known.add(path)
        self.session.add(
            Subtitle(
                video_id=video_id,
                filepath=path,
                language=subtitle_file.get("language"),
                label=subtitle_file.get("label"),
            )
        )
        return True


def _norm(filepath: str) -> str:
    return os.path.normpath(filepath)


def _within(root: str, path: str) -> bool:
    """Return whether ``path`` lives inside the ``root`` directory."""
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        # Different drives on Windows
        return False


def _language_of(subtitle_path: str, video_path: str) -> str | None:
    stem = os.path.splitext(os.path.basename(video_path))[0]
    prefix = os.path.splitext(os.path.basename(subtitle_path))[0]
    suffix = prefix[len(stem):] if prefix.startswith(stem) else ""
    return suffix.lstrip(".") or None


def _label_of(subtitle_path: str, video_path: str) -> str:
    return _language_of(subtitle_path, video_path) or os.path.splitext(
        os.path.basename(subtitle_path)
    )[0]
