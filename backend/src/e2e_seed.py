"""给真后端 e2e 准备一次性库：造媒体、清干净、建一个 owner、扫一遍临时目录。

账号用 ``AuthService`` 建、影片行走 ``ScanService`` 扫，**不手写 INSERT**：e2e 断言之
下的数据因此和真实站点是同一条代码路写出来的。手搓的种子行会跟着模型与扫描规则的
漂移一起过时（标题解析、季集角标、字幕 sidecar 都是扫描的产物），扫出来的不会。

媒体夹具也在**这个进程里**落盘，而不是由前端的 Playwright 配置来写：那个配置文件会被
求值好几遍（主进程一次、每个 worker 一次），任何写在配置里的副作用都会在播种之后把
``data/e2e`` 再清一次——表现就是库里的封面路径指向一个已经不存在的文件。放在这里，
准备文件和扫描就是同一条顺序执行的链，谁也不会踩谁。

命令行输出保持 ASCII：控制台是 cp936，中文报表会花掉。口令只从环境变量读，任何输出
都不回显它。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy import func, select, text

import src.models  # noqa: F401  # 只为把全部模型注册进 Base.metadata
from src.config import BACKEND_ROOT, settings
from src.database import async_session_maker, engine, init_db
from src.database.migrations import business_tables
from src.models.source import VideoSource
from src.models.subtitle import Subtitle
from src.models.video import Video
from src.services.auth_service import AuthService
from src.services.scan_service import ScanService

#: 测试账号。它只活在马上要被 TRUNCATE 的库里，所以字面值进版本库不是泄密——
#: 真正的判据是下面 ``assert_disposable`` 保证这个库永远不是真库。
DEFAULT_USERNAME = "e2e_owner"
DEFAULT_SOURCE_NAME = "E2E local"

#: 一次性目录的名字。删除只允许发生在它下面，见 :func:`prepare_media`。
SANDBOX_DIR = "e2e"

#: 夹具的文件名（不含扩展名）。片名由扫描从文件名解析成 ``e2e sample``。
FIXTURE_STEM = "e2e_sample"

#: 与前端替身夹具 ``frontend/e2e/fixtures.ts`` 里 ``SAMPLE_MP4`` 同一段真 H.264：
#: 64x36 黑帧、1 fps、30 秒、1882 字节。要真的能解码，浏览器才会报出真实时长，
#: FFmpeg 才抽得出封面。两份字节刻意各自独立，改一处不必联动另一处。
SAMPLE_MP4_B64 = "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"  # noqa: E501  # 整块 base64，折行只会让核对更难

#: 同名的 sidecar，扫描时应登记成一条 lang=zh 的字幕。
SIDECAR_SRT = (
    "1\r\n00:00:00,500 --> 00:00:02,500\r\nE2E subtitle line\r\n"
    "2\r\n00:00:02,500 --> 00:00:04,000\r\nsecond cue\r\n"
)

#: 媒体目录由本脚本每次重建，内容固定是一部片子加一条 sidecar。计数对不上说明夹具
#: 坏了，与其让三条用例各炸一次，不如在起步时就失败。
EXPECTED_VIDEOS = 1
EXPECTED_SUBTITLES = 1
EXPECTED_THUMBNAILS = 1



class SeedError(RuntimeError):
    """Raised when the configured database is not safe to wipe."""


def assert_disposable(database_url: str) -> None:
    """只允许清空一个名字就说明自己是测试库的 PostgreSQL 库。

    这个脚本会 TRUNCATE 它连到的库，而连哪个库只看一条环境变量——所以"看起来是测试
    库"不够，必须是库名自己带 ``_test`` 后缀。SQLite 直接拒收：e2e 选的是和生产同一
    个方言，退回 SQLite 会让这套用例证明不了 PG 的行为。
    """
    parsed = urlsplit(database_url)
    if not parsed.scheme.startswith("postgresql"):
        raise SeedError(
            "e2e seeding needs a PostgreSQL test database; "
            f"got scheme {parsed.scheme!r}. Point DATABASE_URL at home_sites_test."
        )
    dbname = unquote((parsed.path or "").lstrip("/"))
    if not dbname.endswith("_test"):
        raise SeedError(
            f"refusing to wipe database {dbname!r}: only names ending in '_test' are "
            "treated as disposable"
        )


def sandbox_root() -> Path:
    """``backend/data/e2e``——这套夹具唯一允许被删的地方。"""
    return (BACKEND_ROOT / "data" / SANDBOX_DIR).resolve()


def prepare_media(media_dir: str) -> None:
    """把一次性媒体目录重建成"只有一份样例加一条 sidecar"。

    删之前先看路径：不在 ``backend/data/e2e`` 之下的直接拒绝，因为这个脚本会整目录删掉，
    而目录名来自一条环境变量。开发中的封面目录 ``data/thumbnails`` 因此不可能被它碰到；
    反过来，如果调用方忘了设 ``THUMBNAIL_PATH``，封面会写进开发目录——那不属于这里的
    责任范围，所以只警告式地跳过清理，不替调用方猜一个路径去删。
    """
    root = sandbox_root()
    media = Path(media_dir).resolve()
    if root not in media.parents:
        raise SeedError(
            f"refusing to clean {media}: the e2e media directory must live under {root}"
        )
    shutil.rmtree(media, ignore_errors=True)
    media.mkdir(parents=True)
    (media / f"{FIXTURE_STEM}.mp4").write_bytes(base64.b64decode(SAMPLE_MP4_B64))
    # 按字节写：文本模式在 Windows 上会把 \n 再翻成 \r\n，sidecar 就成了 \r\r\n。
    (media / f"{FIXTURE_STEM}.zh.srt").write_bytes(SIDECAR_SRT.encode("utf-8"))

    thumbnails = Path(settings.thumbnail_path).resolve()
    if root in thumbnails.parents:
        shutil.rmtree(thumbnails, ignore_errors=True)


async def _truncate_all() -> None:
    """清掉业务表并把自增推回 1，让每次 e2e 从同一个编号开始。"""
    async with engine.begin() as conn:
        tables = sorted(await conn.run_sync(business_tables))
        if not tables:
            return
        names = ", ".join(f'"{name}"' for name in tables)
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


async def seed(*, password: str, media_dir: str, username: str = DEFAULT_USERNAME) -> dict:
    """重建库内容，返回一份可以直接打进 stdout 的摘要。"""
    assert_disposable(settings.database_url)
    prepare_media(media_dir)

    # 建表走应用自己的启动路径，于是 e2e 也顺便证明了这条选路是活的。
    await init_db()
    await _truncate_all()

    async with async_session_maker() as session:
        auth = AuthService(session)
        user = await auth.create_user(username, password, role="owner", display_name="E2E")
        source = VideoSource(
            name=DEFAULT_SOURCE_NAME,
            path=media_dir,
            type="local",
            # 一小时以后才可能自己扫一次，而一次 e2e 跑不完这么久；扫描产物由下面
            # 这一次显式扫描提供，不靠调度器碰巧赶上。
            scan_interval=3600,
        )
        session.add(source)
        await session.commit()
        source_id = source.id

        scan = await ScanService(session).scan_source(source_id)

        videos = (
            await session.scalar(select(func.count(Video.id)).where(Video.source_id == source_id))
            or 0
        )
        subtitles = await session.scalar(select(func.count(Subtitle.id))) or 0
        # 封面是扫描顺手调 FFmpeg 抽出来的。抽不到不会让扫描失败，只会让 e2e 里那张图
        # 变成 naturalWidth=0 的谜案，所以在起步时就把它当成计数项核对。
        thumbnails = (
            await session.scalar(
                select(func.count(Video.id)).where(
                    Video.source_id == source_id, Video.thumbnail_path.is_not(None)
                )
            )
            or 0
        )

    if videos != EXPECTED_VIDEOS or subtitles != EXPECTED_SUBTITLES:
        raise SeedError(
            f"seeded {videos} video(s) and {subtitles} subtitle(s), "
            f"expected {EXPECTED_VIDEOS}/{EXPECTED_SUBTITLES} from {media_dir}"
        )
    if thumbnails != EXPECTED_THUMBNAILS:
        raise SeedError(
            f"seeded {thumbnails} thumbnail(s), expected {EXPECTED_THUMBNAILS}: "
            "the scan could not run ffmpeg (check it is on PATH) or could not write "
            f"into {settings.thumbnail_path!r}"
        )

    return {
        "database": settings.database_url.rsplit("/", 1)[-1],
        "username": user.username,
        "role": user.role,
        "source_id": source_id,
        "new_videos": scan.get("new_videos", 0),
        "videos": videos,
        "subtitles": subtitles,
        "thumbnails": thumbnails,
    }


def main() -> int:
    password = os.environ.get("E2E_PASSWORD", "")
    media_dir = os.environ.get("E2E_MEDIA_DIR", "")
    if not password or not media_dir:
        print("E2E_PASSWORD and E2E_MEDIA_DIR are both required", file=sys.stderr)
        return 2
    try:
        summary = asyncio.run(seed(password=password, media_dir=media_dir))
    except SeedError as exc:
        print(f"e2e seed failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
