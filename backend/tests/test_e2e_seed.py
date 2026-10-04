"""``src.e2e_seed`` 的闸门。

播种会 TRUNCATE 它连到的库、还会整目录删掉媒体夹具，而"连哪个库""清哪个目录"都只看
环境变量，所以这里守的就是那两条判据：库名必须说明自己是测试库，目录必须落在
``backend/data/e2e`` 之下。真扫描本身不在这里跑——它需要一个真 PG、真媒体目录和真
FFmpeg，由 e2e 夹具在现场验证。
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

import src.e2e_seed as e2e_seed
from src.e2e_seed import SeedError, assert_disposable


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(
            "postgresql+asyncpg://app:pw@127.0.0.1:5432/home_sites",
            id="the-live-library",
        ),
        pytest.param(
            "postgresql+asyncpg://app:pw@127.0.0.1:5432/postgres",
            id="a-database-somebody-else-uses",
        ),
        pytest.param(
            "sqlite+aiosqlite:///./data/e2e.db",
            id="sqlite-is-not-the-production-dialect",
        ),
    ],
)
def test_seeding_is_refused_before_anything_touches_the_database(url: str) -> None:
    with pytest.raises(SeedError):
        assert_disposable(url)


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(
            "postgresql+asyncpg://app:pw@127.0.0.1:5432/home_sites_test",
            id="the-project-test-database",
        ),
        pytest.param(
            "postgresql://app@localhost:5432/anything_test",
            id="plain-postgresql-scheme",
        ),
    ],
)
def test_a_database_naming_itself_a_test_one_is_allowed(url: str) -> None:
    assert_disposable(url)


def test_media_reset_rebuilds_only_the_fixtures(tmp_path: Path, monkeypatch) -> None:
    """沙箱里重建时只留这一部片子和这条 sidecar，上一轮的残留被清掉。"""
    monkeypatch.setattr(e2e_seed, "BACKEND_ROOT", tmp_path)
    media = tmp_path / "data" / "e2e" / "media"
    media.mkdir(parents=True)
    (media / "leftover_from_a_renamed_fixture.mp4").write_bytes(b"stale")

    e2e_seed.prepare_media(str(media))

    assert sorted(p.name for p in media.iterdir()) == ["e2e_sample.mp4", "e2e_sample.zh.srt"]
    # 常量是从前端替身夹具里搬来的同一份字节：拷贝走样时这里先红，而不是让 e2e 报
    # "浏览器放不出来"那种看不出根因的错。
    clip = media / "e2e_sample.mp4"
    assert clip.read_bytes() == base64.b64decode(e2e_seed.SAMPLE_MP4_B64)
    assert clip.stat().st_size == 1882
    assert clip.read_bytes()[4:8] == b"ftyp"
    assert (media / "e2e_sample.zh.srt").read_bytes() == e2e_seed.SIDECAR_SRT.encode("utf-8")


@pytest.mark.parametrize(
    "target",
    [
        pytest.param("media", id="an-ordinary-directory"),
        pytest.param("thumbnails", id="not-under-the-sandbox-either"),
    ],
)
def test_media_reset_refuses_paths_outside_the_sandbox(
    tmp_path: Path, monkeypatch, target: str
) -> None:
    """判据不满足时，拒绝发生在任何删除之前。"""
    monkeypatch.setattr(e2e_seed, "BACKEND_ROOT", tmp_path)
    outside = tmp_path / target
    outside.mkdir()
    keep_me = outside / "somebody_elses.mp4"
    keep_me.write_bytes(b"not yours to delete")

    with pytest.raises(SeedError, match="must live under"):
        e2e_seed.prepare_media(str(outside))

    assert keep_me.read_bytes() == b"not yours to delete"


async def test_personal_rows_come_from_the_same_writers_the_site_uses(
    db_session, user_id
):
    """夹具的 `completed` 必须由 `is_completed()` 说了算，不是由播种脚本猜一个。

    这一条守的是整套真后端 e2e 的地基：继续观看那条轨只读 `completed == False` 的
    行。如果这里改成手写 INSERT 并把 completed 拍成 False，那么 `is_completed` 的
    容差一改（它是按时长比例算的），夹具就变成"库里说看完了、界面上还在轨里"或者
    反过来，而两边看着都自洽——只有把写入交回服务本身，规则改了夹具才跟着改。
    """
    from sqlalchemy import func, select

    from src.models.history import PlayHistory
    from src.models.watch_event import WatchEvent
    from src.models.watchlist import Watchlist, WatchlistItem
    from tests.support import ensure_video

    video = await ensure_video(db_session)  # duration=120，18 秒显然没看完
    stats = await e2e_seed.seed_user_stats(db_session, user_id, video.id)

    assert stats["progress"] == e2e_seed.WATCHED_SECONDS
    assert stats["watchlist_id"] > 0

    row = (await db_session.execute(select(PlayHistory))).scalar_one()
    assert (row.progress, row.completed) == (e2e_seed.WATCHED_SECONDS, False)
    assert await db_session.scalar(select(func.count(WatchEvent.id))) == 1

    listed = (await db_session.execute(select(Watchlist))).scalar_one()
    assert (listed.name, listed.description) == (
        e2e_seed.DEFAULT_WATCHLIST_NAME,
        e2e_seed.DEFAULT_WATCHLIST_DESCRIPTION,
    )

    queued = (await db_session.execute(select(WatchlistItem))).scalars().all()
    assert [item.video_id for item in queued] == [video.id]
