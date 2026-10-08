"""用例共用的小工具：把外键要求的父行补齐。

两种方言现在都会当场拒绝指空父行的子行：PostgreSQL 出厂就强制，SQLite 出厂不查
（``PRAGMA foreign_keys`` 关着），从 #161 起 ``tests/conftest.py`` 在测试引擎上把那句
补上了，所以「直接写 ``source_id=1`` 而不建那条视频源」这条路在两边都不通了。父行由
用例自己补，两种数据库才是同一套规则，也不用在共享测试库里藏一条谁都没提过的种子行。
"""

from src.models.source import VideoSource
from src.models.video import Video


async def ensure_source(session, source_id: int = 1) -> VideoSource:
    """保证这条视频源存在；已经有了就原样返回。"""
    source = await session.get(VideoSource, source_id)
    if source is None:
        source = VideoSource(
            id=source_id,
            name=f"source-{source_id}",
            path=f"/library/source{source_id}",
            type="local",
        )
        session.add(source)
        await session.commit()
    return source


async def ensure_video(session, video_id: int = 1, source_id: int = 1) -> Video:
    """保证这条影片存在，顺带补齐它自己的源，外键两头都不缺。"""
    await ensure_source(session, source_id)
    video = await session.get(Video, video_id)
    if video is None:
        video = Video(
            id=video_id,
            source_id=source_id,
            filepath=f"/library/video{video_id}.mp4",
            title=f"video {video_id}",
            duration=120,
            file_size=1024,
            format="mp4",
        )
        session.add(video)
        await session.commit()
    return video
