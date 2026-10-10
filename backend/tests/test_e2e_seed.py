"""``src.e2e_seed`` 的闸门。

播种会 TRUNCATE 它连到的库、还会整目录删掉媒体夹具，而"连哪个库""清哪个目录"都只看
环境变量，所以这里守的就是那两条判据：库名必须说明自己是测试库，目录必须落在
``backend/data/e2e`` 之下。真扫描本身不在这里跑——它需要一个真 PG、真媒体目录和真
FFmpeg，由 e2e 夹具在现场验证。

剩下三处也是同一个道理，但形状不同：``prepare_media`` 清封面那一支、``_truncate_all``、
``main()`` 整段。前两处碰的是"删掉不属于我的东西"，第三处是那个命令行出口。它们都能
在不连任何库的前提下钉住——封面用真目录、``_truncate_all`` 用真反射 + 记录用的连接（那句
``TRUNCATE`` 一个字也不执行，执行它的是真 e2e 的 globalSetup），``main()`` 把 ``seed``
换成替身，钉的是两个环境变量的闸门和 stdout 的形状。``seed()`` 体内那 39 句反过来：它的
价值全在"走的是真写入路径"，拿假会话演一遍就等于什么都没证，所以它留给真后端 e2e 那条链。
"""

from __future__ import annotations

import base64
import contextlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

import src.e2e_seed as e2e_seed
from src.database.base import Base
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
    # 常量解码回来还得是一个真 mp4：拷贝走样时这里先红，而不是让 e2e 报"浏览器放不出来"
    # 那种看不出根因的错。
    clip = media / "e2e_sample.mp4"
    blob = clip.read_bytes()
    assert blob == base64.b64decode(e2e_seed.SAMPLE_MP4_B64)
    assert clip.stat().st_size == len(blob) == 5008
    assert blob[4:8] == b"ftyp"
    # 音轨也在这里钉死。转码配方的音频半边只有在源里带音频流时才会被执行——无声的源让
    # ffmpeg 把 `-c:a` 整个跳过，于是把 `libopus` 写成容器拒收的 `aac` 也能成功；那条产物
    # 断言要真 PG 加真 FFmpeg 起得来才看得见，而这两行在 `pytest` 的半秒里就能红。两条
    # `trak` 盒子加一个 `mp4a` 采样说明，就是"一条视频流 + 一条 AAC"。
    assert blob.count(b"trak") == 2
    assert b"mp4a" in blob
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


# ---------------------------------------------------------------- 封面也归沙箱管


def test_the_thumbnail_directory_is_wiped_only_when_it_lives_in_the_sandbox(
    tmp_path: Path, monkeypatch
) -> None:
    """``prepare_media`` 最后那三行：封面目录在沙箱里就跟着一起清，不在就一个字也不动。

    这一支此前一次也没被敲过，因为用例把 ``BACKEND_ROOT`` 挪进 ``tmp_path`` 却没挪
    ``settings.thumbnail_path``——真实配置里那个目录从来不在沙箱之下，于是守卫永远走"跳过"。
    两边都要钉：只钉"会删"的话，把守卫整个去掉也照样绿，而那正是开发中的封面被一次
    e2e 连锅端掉的形状。
    """
    monkeypatch.setattr(e2e_seed, "BACKEND_ROOT", tmp_path)
    root = tmp_path / "data" / "e2e"
    media = root / "media"
    thumbnails = root / "thumbnails"
    thumbnails.mkdir(parents=True)
    stale = thumbnails / "cover_of_a_renamed_video.jpg"
    stale.write_bytes(b"stale")
    monkeypatch.setattr(e2e_seed, "settings", SimpleNamespace(thumbnail_path=str(thumbnails)))

    e2e_seed.prepare_media(str(media))

    assert not thumbnails.exists()
    assert (media / "e2e_sample.mp4").exists()


def test_a_thumbnail_directory_outside_the_sandbox_survives_the_reset(
    tmp_path: Path, monkeypatch
) -> None:
    """负对照：``THUMBNAIL_PATH`` 指着沙箱外面时，一句删除都不发生。"""
    monkeypatch.setattr(e2e_seed, "BACKEND_ROOT", tmp_path)
    media = tmp_path / "data" / "e2e" / "media"
    thumbnails = tmp_path / "thumbnails"  # 开发中那个目录的形状：沙箱的兄弟，不是孩子
    thumbnails.mkdir(parents=True)
    keep_me = thumbnails / "somebody_elses_cover.jpg"
    keep_me.write_bytes(b"not yours to delete")
    monkeypatch.setattr(e2e_seed, "settings", SimpleNamespace(thumbnail_path=str(thumbnails)))

    e2e_seed.prepare_media(str(media))

    assert keep_me.read_bytes() == b"not yours to delete"
    assert (media / "e2e_sample.mp4").exists()


# ---------------------------------------------------------------- 清库那条语句的形状


class _RecordingConnection:
    """把语句记下来，一条也不执行。

    ``TRUNCATE ... RESTART IDENTITY CASCADE`` 是 PostgreSQL 独有的，而反射那一步
    （``business_tables``）两种方言都读得出来。所以这里用真库真反射算表名，只在
    "落下去执行"这一步换成记录——真执行它的是真 e2e 的 globalSetup，对着 ``home_sites_test``。
    """

    def __init__(self, sync_conn) -> None:
        self._sync = sync_conn
        self.statements: list[str] = []

    async def run_sync(self, fn):
        return fn(self._sync)

    async def execute(self, statement):
        self.statements.append(str(statement))
        return None


class _RecordingEngine:
    def __init__(self, sync_conn) -> None:
        self.conn = _RecordingConnection(sync_conn)

    @contextlib.asynccontextmanager
    async def begin(self):
        yield self.conn


def _quoted_names(statement: str) -> list[str]:
    return re.findall(r'"([^"]+)"', statement)


async def test_the_wipe_names_every_business_table_and_skips_the_version_one(
    tmp_path: Path, monkeypatch
) -> None:
    """``_truncate_all`` 的整段：表名从真反射来，版本表被排除，语句按名字排好。

    钉的是这条语句的**形状**而不是它执行的效果——效果由真 e2e 每次跑一遍。三件事各管一段：
    少了 ``RESTART IDENTITY`` 编号就不从 1 开始，用例里那些写死的 id 全跑偏；把
    ``VERSION_TABLE`` 减掉那一步去掉，Alembic 那行版本跟着没了，下一次启动的迁移会从
    错误的地方接着跑；``sorted`` 则让同一次播种的语句在两次运行里长一个样。
    ``sessions`` 也在这张清单里（和搬迁脚本正好相反）：e2e 每轮都要从"没人登录过"开始。
    """
    path = tmp_path / "seed.db"
    sync_engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(sync_engine)
    with sync_engine.connect() as sync_conn:
        sync_conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        recorder = _RecordingEngine(sync_conn)
        monkeypatch.setattr(e2e_seed, "engine", recorder)
        await e2e_seed._truncate_all()
    sync_engine.dispose()

    assert len(recorder.conn.statements) == 1
    statement = recorder.conn.statements[0]
    assert statement.startswith("TRUNCATE ")
    assert statement.endswith(" RESTART IDENTITY CASCADE")
    names = _quoted_names(statement)
    assert names == sorted(names)
    assert "alembic_version" not in names
    assert set(names) == set(Base.metadata.tables)
    assert "sessions" in names


async def test_a_library_with_no_business_table_wipes_nothing(tmp_path: Path, monkeypatch) -> None:
    """空库那早退：没有表就没有语句，也就没有 ``TRUNCATE  RESTART`` 那种半截话。

    这是 ``_truncate_all`` 唯一另一个出口，也是刚建好、迁移还没跑的库第一次播种时走的
    那一条。少了它会拼出一条 ``TRUNCATE  ...``，在 PG 上是一次语法错误——而现场看到的
    是"e2e 起不来"，看不出根因是库是空的。
    """
    sync_engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with sync_engine.connect() as sync_conn:
        recorder = _RecordingEngine(sync_conn)
        monkeypatch.setattr(e2e_seed, "engine", recorder)
        await e2e_seed._truncate_all()
    sync_engine.dispose()

    assert recorder.conn.statements == []


# ---------------------------------------------------------------- 命令行出口


def test_the_command_line_refuses_to_start_without_both_environment_variables(
    monkeypatch, capsys
) -> None:
    """两个环境变量缺任何一个：退码 2、原因在 stderr、``seed`` 一次也没被调到。

    这是"连哪个库、清哪个目录"之外的第三道保险——播种会清库清目录，而它只看这两条
    环境变量；缺一个就说明调用方还没决定要动什么。
    """
    calls: list = []

    async def explode(**kwargs):
        calls.append(kwargs)

    monkeypatch.delenv("E2E_PASSWORD", raising=False)
    monkeypatch.delenv("E2E_MEDIA_DIR", raising=False)
    monkeypatch.setattr(e2e_seed, "seed", explode)

    assert e2e_seed.main() == 2
    monkeypatch.setenv("E2E_PASSWORD", "e2e-only-password")
    assert e2e_seed.main() == 2
    monkeypatch.setenv("E2E_MEDIA_DIR", str(Path("data") / "e2e" / "media"))
    monkeypatch.delenv("E2E_PASSWORD", raising=False)
    assert e2e_seed.main() == 2

    captured = capsys.readouterr()
    assert calls == []
    assert captured.out == ""
    assert captured.err.count("E2E_PASSWORD and E2E_MEDIA_DIR are both required") == 3


def test_the_command_line_prints_the_summary_as_ascii_json_and_hides_the_password(
    monkeypatch, capsys
) -> None:
    """成功那一路：stdout 是一份按键排好序的 JSON，退码 0，口令一个字也不出现。

    模块 docstring 那句「命令行输出保持 ASCII」在这一族是真的（搬迁脚本那边不是），而它
    靠的是 ``json.dumps`` 默认 ``ensure_ascii=True``——所以摘要里放一个中文值来钉这一条：
    将来谁加上 ``ensure_ascii=False``，cp936 控制台上这一次 e2e 起手就花掉。口令不回显
    是同一句 docstring 的另一半，而它只在真跑一次时才看得出，所以这里用哨兵把它钉住。
    """
    summary = {
        "database": "home_sites_test",
        "username": "e2e_owner",
        "watchlist_name": "今晚看这些",
        "videos": 1,
    }
    seen: list[dict] = []

    async def fake_seed(*, password: str, media_dir: str) -> dict:
        seen.append({"password": password, "media_dir": media_dir})
        return summary

    monkeypatch.setenv("E2E_PASSWORD", "sentinel-never-echoed")
    monkeypatch.setenv("E2E_MEDIA_DIR", "data/e2e/media")
    monkeypatch.setattr(e2e_seed, "seed", fake_seed)

    assert e2e_seed.main() == 0

    captured = capsys.readouterr()
    assert seen == [{"password": "sentinel-never-echoed", "media_dir": "data/e2e/media"}]
    assert json.loads(captured.out) == summary
    assert list(json.loads(captured.out)) == sorted(summary)
    assert all(ord(ch) < 128 for ch in captured.out)
    assert "今晚看这些" not in captured.out
    assert "sentinel-never-echoed" not in captured.out + captured.err


def test_the_command_line_reports_a_seed_failure_on_stderr_and_exits_one(
    monkeypatch, capsys
) -> None:
    """``SeedError`` 那一路：原因进 stderr、退码 1、stdout 保持干净。

    真 e2e 起手就是这一条最可能撞上的（ffmpeg 不在 PATH、扫描没写出片子、member 那行没建
    成 member），所以"说清楚"比"失败"更值得钉：退码 1 而 stderr 空的现场只能去猜。
    """

    async def fail(**kwargs):
        raise SeedError("seeded 0 video(s), expected 1 from data/e2e/media")

    monkeypatch.setenv("E2E_PASSWORD", "e2e-only-password")
    monkeypatch.setenv("E2E_MEDIA_DIR", "data/e2e/media")
    monkeypatch.setattr(e2e_seed, "seed", fail)

    assert e2e_seed.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "e2e seed failed: seeded 0 video(s), expected 1 from data/e2e/media\n"
