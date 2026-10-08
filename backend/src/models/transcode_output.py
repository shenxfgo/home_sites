from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base
from src.database.types import UTCDateTime


class TranscodeOutput(Base):
    """One finished transcode product: which video, which container, where the file went.

    产物从前只活在进程里那本 `_jobs` 账上，服务一重启就谁也不记得自己转过什么
    （#154）。这一张表就是那本账的持久版。

    `deleted_at` 由**读取时那一次 stat** 写：产物目录不在任何片源范围内，扫描
    永远不会走到它，所以除了这一处没有别人能说得出"文件没了"。反方向也一并翻回来
    ——文件被放回去（误删后恢复、换盘）时标记必须清掉，否则这一列会从"漏报"变成
    "误报"，一样是谎。
    """

    __tablename__ = "transcode_outputs"
    __table_args__ = (
        # 同一个片子转成同一种容器写的是同一个路径（`<output_dir>/<video_id>/<stem>.<fmt>`），
        # ffmpeg 带 `-y` 就是覆盖重做，所以这里是一行被更新，不是多出一行。
        UniqueConstraint(
            "video_id", "target_format", name="ux_transcode_output_video_format"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_format: Mapped[str] = mapped_column(String(20), nullable=False)
    output_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TranscodeOutput(id={self.id}, video_id={self.video_id}, "
            f"format='{self.target_format}')>"
        )
