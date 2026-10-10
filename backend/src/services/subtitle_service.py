"""SubtitleService for managing subtitle tracks attached to videos."""
import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.subtitle import Subtitle
from src.models.video import Video
from src.storage import storage_for_locator
from src.utils.subtitles import convert_to_webvtt, sidecar_identity


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
            raise ValueError(f"视频 #{video_id} 不存在")

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

        # 手工这条路把那个文件真读一遍再落行（⑧乙）。挡的是"点了挂字幕、挂上了一条永远不会
        # 有词的轨"：那一行一旦写进库，菜单上就多一个条目，而它唯一会说的话是浏览器那句
        # "没能加载"。扫描那一路照旧只看文件名（`register`），所以这份不对称是**故意的**——
        # 一趟扫描不该因为磁盘上有一个空壳文件就少登记一条轨道，而一个人按下的那一下可以。
        await asyncio.to_thread(convert_to_webvtt, normalized)

        derived_language, derived_label = sidecar_identity(video.filepath, normalized)
        subtitle = Subtitle(
            video_id=video_id,
            filepath=normalized,
            language=language or derived_language,
            label=label or derived_label,
        )
        self.session.add(subtitle)
        await self.session.commit()
        await self.session.refresh(subtitle)
        return subtitle

    async def delete(self, video_id: int, subtitle_id: int) -> None:
        """Remove a subtitle track record."""
        subtitle = await self.get_subtitle(video_id, subtitle_id)
        if not subtitle:
            raise ValueError(f"字幕 #{subtitle_id} 不存在")

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

    async def prune_missing(self, source_id: int) -> int:
        """Delete the tracks whose file is no longer on disk; return how many.

        Without this half, registration is one-way: a sidecar that gets moved,
        renamed or deleted stays listed forever, and the player keeps offering a
        track that can only 404. The question asked is「文件还在吗」rather than
        「这轮扫描认得它吗」, so a track someone registered by hand under a name
        the sidecar pattern never matches survives its own scan.

        The caller commits, same as with ``register``.
        """
        result = await self.session.execute(
            select(Subtitle)
            .join(Video, Video.id == Subtitle.video_id)
            .where(Video.source_id == source_id)
        )
        rows = list(result.scalars().all())
        gone = [row for row in rows if not os.path.isfile(row.filepath)]
        for row in gone:
            await self.session.delete(row)
        return len(gone)

    def register(
        self,
        video_id: int,
        subtitle_file: dict,
        known: set[str],
    ) -> bool:
        """Add a discovered sidecar file unless it is already registered.

        ``known`` is updated in place so a repeated scan stays idempotent.

        This is the scan's half of the two registration paths and it deliberately
        never opens the file: ``add`` (the manual one) does. A scan that read every
        sidecar would fail on one bad file the same way it used to fail on one bad
        video -- and it would drop tracks a person can still remove by hand.
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
