# tests/test_db_transfer.py
"""搬家脚本：行、摘要、序列、闸门和演练。

两边都是真实的文件库：老库按当前模型（外加两个只存在于库里的老列）造数据，新库由
``0001`` 基线建表——也就是真换库时的两张库，不是假想形状。

设了 ``TEST_DATABASE_URL`` 还会多跑一条：新库换成真的 PostgreSQL，专门盯时间戳——
SQLite 还回来的是不带 tzinfo 的 UTC 文本，asyncpg 见到不带 tzinfo 的值按会话时区理解，
所以搬运过程中必须把时刻标清楚，否则整库时间一起偏移，而且一句错都不报。
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.database.base import Base
from src.database.migrations import business_tables, upgrade_head
from src.db_audit import audit
from src.db_transfer import TransferError, _read, transfer
from src.models.favorite import Favorite
from src.models.new_video import NewVideo
from src.models.notification import Notification
from src.models.read_state import NewVideoRead
from src.models.source import VideoSource
from src.models.user import ROLE_OWNER, User, UserSession
from src.models.video import Video

NOW = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)

#: 生产在 PG 上时才有的搬家目标；不设就只跑两张 SQLite 文件库。
PG_TARGET_URL = settings.test_database_url


def _url(path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def _columns_of(sync_conn, table: str) -> set[str]:
    """库里这一张表实际的列名（要过 ``run_sync``，所以是同步连接）。"""
    return {column["name"] for column in inspect(sync_conn).get_columns(table)}


def _target_shape(tmp_path):
    """新库：连上去把基线跑一遍，和生产启动走的是同一条路。"""
    path = tmp_path / "target.db"
    sync_engine = create_engine(f"sqlite:///{path}")
    with sync_engine.begin() as conn:
        upgrade_head(conn)
    sync_engine.dispose()
    return _url(path)


async def _seed_legacy(tmp_path) -> str:
    """一家人在老库里应有的样子：两个账号、三部片、收藏/历史/片单/通知各几条。"""
    path = tmp_path / "legacy.db"
    url = _url(path)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 老库特有的两列：模型已经不读它们，值还留在库里
        await conn.execute(text("ALTER TABLE new_videos ADD COLUMN viewed BOOLEAN"))
        await conn.execute(text("ALTER TABLE notifications ADD COLUMN read BOOLEAN"))

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(
            [
                VideoSource(id=1, name="客厅盘", path="D:/media", type="local"),
                VideoSource(id=2, name="NAS", path="\\\\nas\\video", type="nas"),
                Video(id=1, source_id=1, filepath="/m/a.mp4", title="第一部", series="某系列"),
                Video(id=2, source_id=1, filepath="/m/b.mp4", title="第二部", rating=3),
                Video(
                    id=3,
                    source_id=2,
                    filepath="/m/c.mp4",
                    title="第三部",
                    is_missing=True,
                    duration=0,
                ),
                User(id=1, username="xiaofeng", password_hash="x" * 60, role=ROLE_OWNER),
                User(id=2, username="guest", password_hash="y" * 60),
                Favorite(id=1, user_id=1, video_id=1, created_at=NOW),
                Favorite(id=2, user_id=2, video_id=3, created_at=NOW),
                NewVideo(id=1, video_id=1, source_id=1, discovered_at=NOW),
                NewVideo(id=2, video_id=2, source_id=1, discovered_at=NOW),
                NewVideoRead(new_video_id=1, user_id=1),
                Notification(id=1, type="scan", title="扫完了", created_at=NOW, data={"n": 1}),
                # 会话行故意留在老库里：它不该出现在新库，脚本得把它跳过
                UserSession(token_hash="a" * 64, user_id=1, expires_at=NOW, user_agent="手机"),
            ]
        )
        await session.commit()

        # 只留在老库那一列上的值：搬过去会丢，脚本得报出来
        await session.execute(
            text("UPDATE new_videos SET viewed = 1 WHERE id = 2")
        )
        await session.commit()

    await engine.dispose()
    return url


async def _counts(url: str) -> dict[str, int]:
    engine = create_async_engine(url)
    result: dict[str, int] = {}
    async with engine.connect() as conn:
        for name in sorted(t.name for t in Base.metadata.sorted_tables):
            rows = await conn.execute(text(f'SELECT COUNT(*) FROM "{name}"'))
            result[name] = int(rows.scalar_one())
    await engine.dispose()
    return result


async def _rows(url: str, table) -> list[dict]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        found = await conn.execute(select(table))
        rows = [dict(row) for row in found.mappings()]
    await engine.dispose()
    return rows


async def test_every_row_lands_with_its_own_id(tmp_path):
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    await transfer(source, target)

    moved = await _rows(target, Video)
    assert sorted(row["id"] for row in moved) == [1, 2, 3]
    assert {row["title"] for row in moved} == {"第一部", "第二部", "第三部"}
    kept = await _rows(target, Favorite)
    assert [(row["user_id"], row["video_id"]) for row in kept] == [(1, 1), (2, 3)]
    assert await _rows(source, UserSession)  # 老库里确实带着登录会话
    assert await _rows(target, UserSession) == []  # 旧 token 不带到新库


async def test_the_two_libraries_digest_the_same_on_every_table(tmp_path):
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    report = await transfer(source, target)

    assert report.total_rows > 0
    assert [move.name for move in report.moves if not move.matches] == []


async def test_a_leftover_legacy_column_is_reported_and_dropped(tmp_path):
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    report = await transfer(source, target)

    assert any("new_videos.viewed" in w and "1 行" in w for w in report.warnings)
    engine = create_async_engine(target)
    async with engine.connect() as conn:
        columns = await conn.run_sync(_columns_of, "new_videos")
    await engine.dispose()
    assert "viewed" not in columns


async def test_the_new_library_keeps_handing_out_fresh_ids(tmp_path):
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    await transfer(source, target)

    engine = create_async_engine(target)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Video(source_id=1, filepath="/m/d.mp4", title="第四部"))
        await session.commit()
        newest = (
            await session.execute(select(Video).where(Video.title == "第四部"))
        ).scalar_one()
        assert newest.id == 4  # 序列被拨到搬过来的最大值之后
    await engine.dispose()


async def test_dry_run_checks_everything_and_leaves_nothing(tmp_path):
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    report = await transfer(source, target, dry_run=True)

    assert report.rolled_back
    assert [move.matches for move in report.moves]  # 演练也把对账走完了
    counts = await _counts(target)
    assert set(counts.values()) == {0}


async def test_an_orphan_row_stops_the_whole_transfer(tmp_path):
    source = await _seed_legacy(tmp_path)
    engine = create_async_engine(source)
    async with engine.begin() as conn:
        # SQLite 不强制外键，这种行在老库里存得进去：收藏指向一部不存在的片
        await conn.execute(
            text(
                "INSERT INTO favorites (id, user_id, video_id, created_at) "
                "VALUES (99, 1, 12345, '2026-01-05 12:00:00')"
            )
        )
    await engine.dispose()
    target = _target_shape(tmp_path)

    with pytest.raises(TransferError, match="找不到父行"):
        await transfer(source, target)

    assert set((await _counts(target)).values()) == {0}


async def test_a_row_nobody_claimed_stops_the_transfer(tmp_path):
    path = tmp_path / "unclaimed.db"
    url = _url(path)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 真实老库的形状：user_id 是 ALTER 加上去的，既没有非空约束也没有外键
        await conn.execute(text("DROP TABLE favorites"))
        await conn.execute(
            text(
                "CREATE TABLE favorites (id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                "user_id INTEGER, video_id INTEGER NOT NULL, created_at DATETIME)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO videos (id, source_id, filepath, title, is_missing, "
                "rating, view_count, created_at, updated_at) "
                "VALUES (1, 1, '/m/a.mp4', '第一部', 0, 0, 0, "
                "'2026-01-05 12:00:00', '2026-01-05 12:00:00')"
            )
        )
        await conn.execute(
            text("INSERT INTO favorites (id, user_id, video_id) VALUES (1, NULL, 1)")
        )
    await engine.dispose()
    target = _target_shape(tmp_path)

    with pytest.raises(TransferError, match=r"favorites\.user_id.*NULL"):
        await transfer(url, target)


async def test_the_audit_report_and_the_transfer_print_the_same_number(tmp_path):
    """审计报告里的摘要和搬家脚本比的那个摘要，必须是同一个数。

    文档说的流程是"搬完在目标库上再算一遍对得上才算搬全"，靠的就是把这两个数字对着看；
    两边各自拼行文本的话（一处带列名、一处不带），同一个数永远对不上，等于没有这条闸门。
    """
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    report = await transfer(source, target)

    audited = {t.name: t.digest for t in audit(tmp_path / "legacy.db").tables}
    moved = {move.name: move.source_digest for move in report.moves}
    assert set(moved) <= set(audited)  # 审计还多看 sessions 一眼，那是它自己的范围
    assert moved == {name: audited[name] for name in moved}


async def test_the_new_library_has_to_start_out_empty(tmp_path):
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    await transfer(source, target)

    with pytest.raises(TransferError, match="已经有"):
        await transfer(source, target)
    # 第二次一行也没插进去
    assert (await _counts(target))["videos"] == 3


async def test_a_library_that_has_not_been_repaired_is_refused(tmp_path):
    path = tmp_path / "ancient.db"
    url = _url(path)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE videos (id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
                "filepath VARCHAR(1024) NOT NULL, title VARCHAR(512))"
            )
        )
    await engine.dispose()
    target = _target_shape(tmp_path)

    with pytest.raises(TransferError, match="缺表"):
        await transfer(url, target)


async def test_notifications_json_survives_the_trip(tmp_path):
    source = await _seed_legacy(tmp_path)
    engine = create_async_engine(source)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO notifications (id, type, title, created_at, data) "
                "VALUES (7, 'scan', '带数据的', '2026-01-05 12:00:00', "
                "'{\"b\": 2, \"a\": 1}')"
            )
        )
    await engine.dispose()
    target = _target_shape(tmp_path)

    report = await transfer(source, target)

    assert report.by_name("notifications").matches
    moved = await _rows(target, Notification)
    assert [row["data"] for row in moved if row["id"] == 7] == [{"b": 2, "a": 1}]
    assert (await _rows(target, NewVideo))[1]["id"] == 2


async def test_a_naive_sqlite_timestamp_is_read_as_utc(tmp_path):
    """读老库时给时间补上 UTC，是这条链路唯一一次标时刻。

    老库里存的是 ``2026-01-05 12:00:00`` 这样的文本，SQLAlchemy 还回来一个不带 tzinfo 的
    ``datetime``。带着它去插 PG 的 ``timestamptz``，asyncpg 会按数据库会话时区理解这个值，
    本机 +8 就把整个库的时间往前挪 8 小时——不报错，只有摘要对不上。
    """
    source = await _seed_legacy(tmp_path)
    engine = create_async_engine(source)
    async with engine.connect() as conn:
        rows = await _read(conn, Favorite)
    await engine.dispose()

    assert len(rows) == 2
    assert {row["created_at"].tzinfo for row in rows} == {timezone.utc}
    assert {row["created_at"] for row in rows} == {NOW}


@pytest.mark.skipif(not PG_TARGET_URL, reason="需要真 PostgreSQL：设 TEST_DATABASE_URL 才跑")
async def test_the_instant_survives_a_postgresql_target(tmp_path):
    """搬到真 PG 上：时刻必须一个小时都不差，摘要必须整表一致。"""
    source = await _seed_legacy(tmp_path)
    engine = create_async_engine(PG_TARGET_URL)
    async with engine.begin() as conn:
        await conn.run_sync(upgrade_head)  # 空库先走基线，和生产启动同一条路
        tables = sorted(await conn.run_sync(business_tables))
        names = ", ".join(f'"{name}"' for name in tables)
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    await engine.dispose()

    report = await transfer(source, PG_TARGET_URL)

    assert [move.name for move in report.moves if not move.matches] == []
    moved = await _rows(PG_TARGET_URL, Favorite)
    # == 比的是时刻本身，所以 PG 按会话时区还回来的 +08 值照样等于写入的那个瞬间
    assert [row["created_at"] for row in sorted(moved, key=lambda r: r["id"])] == [NOW, NOW]
    assert [row["id"] for row in sorted(moved, key=lambda r: r["id"])] == [1, 2]
