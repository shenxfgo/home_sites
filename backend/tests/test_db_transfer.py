# tests/test_db_transfer.py
"""搬家脚本：行、摘要、序列、闸门和演练。

两边都是真实的文件库：老库按当前模型（外加两个只存在于库里的老列）造数据，新库由
``0001`` 基线建表——也就是真换库时的两张库，不是假想形状。

设了 ``TEST_DATABASE_URL`` 还会多跑一条：新库换成真的 PostgreSQL，专门盯时间戳——
SQLite 还回来的是不带 tzinfo 的 UTC 文本，asyncpg 见到不带 tzinfo 的值按会话时区理解，
所以搬运过程中必须把时刻标清楚，否则整库时间一起偏移，而且一句错都不报。

后面这一批钉的是它的**边界**：主键是文本的表没有序列可拨、父表压根不在这次搬运范围时
外键检查为什么不比、新库那一列的类型把值悄悄改了形状时整笔退回原样、老库少一列时那句
「先启动再来」，以及那个命令行出口——每张表一行、报告走 stdout、失败走 stderr 并退 1，
还有「不带 --to 就搬进应用自己配的那张库」这条必须写在纸面上的默认值。

其中给 SQLite 拨序列那一格已经按 #206 删掉了（第三块面板⑩甲）：本仓两种新库形状的 DDL
都不写 AUTOINCREMENT 关键字，反射又默认把 ``sqlite_`` 打头的内部表滤掉，那道保险两头够
不着。留在这里的是它背后那两条实测事实——反射看不见这张内部表，以及带显式 rowid 插进去
时 SQLite 自己就把 ``sqlite_sequence`` 顶上去。前者如今只有一个活消费者：``_check_source``
那句「老库里多出来的表」用的正是同一份反射清单——所以那格照钉，只是钉的理由换了。
"""

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from src import db_transfer
from src.config import settings
from src.database.base import Base
from src.database.migrations import business_tables, upgrade_head
from src.db_audit import audit
from src.db_transfer import (
    TableMove,
    TransferError,
    TransferReport,
    _model_tables,
    _orphans,
    _read,
    _table_names,
    main,
    transfer,
)
from src.models.favorite import Favorite
from src.models.new_video import NewVideo
from src.models.notification import Notification
from src.models.read_state import NewVideoRead
from src.models.setting import Setting
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


# ---------------------------------------------------------------- 边界：老库少一列


async def _seed_kv_source(tmp_path) -> str:
    """只有系统配置两行、其余表全空的老库：表齐列齐，是「先启动过」的形状。"""
    path = tmp_path / "kv.db"
    url = _url(path)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(
            [Setting(key="auto_scan", value="true"), Setting(key="theme", value="dark")]
        )
        await session.commit()
    await engine.dispose()
    return url


async def test_a_source_library_that_lost_one_declared_column_is_refused(tmp_path):
    """``_check_source`` 那第二个 raise：表在、列不齐。

    上面那条「缺表」的用例已经挡过一种没启动过的老库，这一种更难看见——表名字一个不少，
    只有补齐 SQL 没跑完。报出来的那份列名清单是唯一能让人知道该去跑什么的东西，
    所以它必须点名 updated_at，而不是只说一句「缺列」。
    """
    source = await _seed_kv_source(tmp_path)
    engine = create_async_engine(source)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE settings"))
        await conn.execute(
            text("CREATE TABLE settings (key VARCHAR(100) NOT NULL PRIMARY KEY, value TEXT)")
        )
    await engine.dispose()
    target = _target_shape(tmp_path)

    with pytest.raises(TransferError, match="缺列") as caught:
        await transfer(source, target)

    assert "updated_at" in str(caught.value)
    assert sum((await _counts(target)).values()) == 0  # 一列都没写进去


# ---------------------------------------------------------------- 边界：文本主键


async def test_a_table_whose_primary_key_is_text_moves_without_a_sequence(tmp_path):
    """主键是文本的表（settings.key）走到「不是整数主键，拨什么」那句 return。

    这一族只有这一张表，而它平时是空的——空表在更早一步就返回了，所以「有行 + 文本主键」
    这个组合一直没被敲过。搬进老库里有配置行的库是真换库时的正常形状，搬完必须逐字节相同。
    """
    source = await _seed_kv_source(tmp_path)
    target = _target_shape(tmp_path)

    report = await transfer(source, target)

    move = report.by_name("settings")
    assert move.rows == 2
    assert move.matches
    landed = await _rows(target, Setting.__table__)
    assert {row["key"] for row in landed} == {"auto_scan", "theme"}


# ---------------------------------------------------------------- 边界：父表不在范围内


def test_an_orphan_pointing_at_a_table_that_is_not_being_moved_is_not_reported():
    """``_orphans`` 的 continue：父表压根不在这次 data 里，就没有可比的那一侧。

    今天没有任何模型指向 sessions，所以这一格从接口和真库两条路都够不着，只能直接敲这个
    纯函数（#199 的先例：够不着不是不钉的理由）。同一段里放正反两个对照，是为了让它红得
    清楚——把 continue 改成往下走会当场 KeyError，而把父表取值那一步整个跳过，则会让
    一条真孤儿行安静地搬过去，那才是新库当场拒收的现场。
    """
    table = Favorite.__table__
    orphan = [{"id": 1, "user_id": 1, "video_id": 999}]

    assert _orphans(table, orphan, {}) == []

    moved = {"users": [{"id": 1}], "videos": [{"id": 1}]}
    problems = _orphans(table, orphan, moved)
    assert [p for p in problems if p.startswith("favorites.video_id")] == [
        "favorites.video_id: 1 行在 videos 里找不到父行（id: 1）"
    ]
    assert _orphans(table, [{"id": 2, "user_id": 1, "video_id": 1}], moved) == []


async def test_asking_the_report_about_a_table_that_was_never_moved_raises(tmp_path):
    """``by_name`` 的 raise：被跳过的那张表不在报告里，问它就 KeyError。

    会话表是唯一一个「模型里有、报告里没有」的名字，所以这一句在真实报告上敲得动。
    宁可不回答也不要回答成一个空表——调用方据此判断的下一步是「这张表没搬」。
    """
    source = await _seed_legacy(tmp_path)
    target = _target_shape(tmp_path)

    report = await transfer(source, target)

    assert report.by_name("videos").rows == 3
    with pytest.raises(KeyError, match="sessions"):
        report.by_name("sessions")


# ---------------------------------------------------------------- 边界：新库改了值的形状


async def _seed_tag_source(tmp_path) -> str:
    """老库里只有标签一张表有行，其中一条名字长得像数字。"""
    path = tmp_path / "tags.db"
    url = _url(path)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "INSERT INTO tags (id, name, color, created_at) "
                "VALUES (1, '007', '#409eff', '2026-01-05 12:00:00')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO tags (id, name, color, created_at) "
                "VALUES (2, '纪录片', '#409eff', '2026-01-05 12:00:00')"
            )
        )
    await engine.dispose()
    return url


def _target_that_rewrites_numbers(tmp_path) -> str:
    """新库按模型建齐，只把 tags.name 那一列声明成 INTEGER——SQLite 会照列亲和改写值。"""
    path = tmp_path / "drifted.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE tags"))
        conn.execute(
            text(
                "CREATE TABLE tags (id INTEGER NOT NULL PRIMARY KEY, name INTEGER,"
                " color VARCHAR(20), created_at DATETIME)"
            )
        )
    engine.dispose()
    return _url(path)


async def test_a_new_library_that_rewrites_a_value_rolls_the_whole_thing_back(tmp_path):
    """对账那句存在的全部理由：新库的列亲和把 007 存成 7，一句错都不报。

    这是 #201 那条「列亲和决定值以什么形状存活」的反向应用——老库的 VARCHAR 列把数字变成
    文本，新库的 INTEGER 列把长得像数字的文本变成整数，SQLite 两头都悄悄地做。行数是空的
    闸门看不出来，两边各自读回来算的摘要才看得出来；不一致的那张表被点名，事务整体退回。
    """
    source = await _seed_tag_source(tmp_path)
    target = _target_that_rewrites_numbers(tmp_path)

    with pytest.raises(TransferError, match="不一致") as caught:
        await transfer(source, target)

    assert caught.value.args[0].endswith("tags")
    assert set((await _counts(target)).values()) == {0}
    # 老库里那一行仍是文本：改值的是新库的列声明，不是搬运本身
    engine = create_async_engine(source)
    async with engine.connect() as conn:
        held = (
            await conn.execute(text("SELECT typeof(name), name FROM tags WHERE id = 1"))
        ).first()
    await engine.dispose()
    assert held == ("text", "007")


# ---------------------------------------------------------------- 边界：反射看不见的那张内部表


def test_the_reflection_this_script_uses_cannot_see_the_sequence_table(tmp_path):
    """``sqlite_sequence`` 在 sqlite_master 里，但反射的默认过滤把它藏了。

    ``get_table_names()`` 的 SQL 里写着「name NOT LIKE sqlite 打头」（方言参数
    ``sqlite_include_internal`` 默认 False），而 ``_check_source`` 那句「老库里多出来的表」
    正是拿 ``_table_names`` 算的：没有这道过滤，搬一次 SQLite 老库就会报一张用户从没建过的
    内部表——命令行那格 ``len(warn) == 2`` 就是它的后果。两份清单同时摆出来是早先给
    ``_reset_sequences`` 的 SQLite 保险开的死亡证明（#202），那一格已经按 #206 删了，而这道
    过滤还活着，所以钉子留着。将来谁把反射换成裸 sqlite_master 查询，这一条会当场红。
    """
    path = tmp_path / "internal.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT)"))
        conn.execute(text("INSERT INTO t (id, label) VALUES (7, '搬过来的那一行')"))
    with engine.connect() as conn:
        raw = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
        }
        reflected = _table_names(conn)
    engine.dispose()

    assert "sqlite_sequence" in raw
    assert "sqlite_sequence" not in reflected
    assert "t" in reflected


# ---------------------------------------------------------------- 那个命令行出口


def _seed_cli_source(tmp_path) -> str:
    """命令行那三条用例的老库：用同步引擎造，因为 ``main()`` 自己开事件循环。

    故意留一个只存在于库里的老列（``new_videos.viewed``）并让它存着值——那样 stdout 才会
    同时出现中文警告行和 ASCII 表格行，两者的边界才是被断言过的而不是被假设的。
    """
    path = tmp_path / "cli_legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE new_videos ADD COLUMN viewed BOOLEAN"))
    maker = sessionmaker(engine)
    with maker() as session:
        session.add_all(
            [
                VideoSource(id=1, name="客厅盘", path="D:/media", type="local"),
                Video(id=1, source_id=1, filepath="/m/a.mp4", title="第一部"),
                Video(id=2, source_id=1, filepath="/m/b.mp4", title="第二部"),
                NewVideo(id=1, video_id=1, source_id=1, discovered_at=NOW),
            ]
        )
        session.commit()
        session.execute(text("UPDATE new_videos SET viewed = 1 WHERE id = 1"))
        session.commit()
    engine.dispose()
    return _url(path)


def _sqlite_counts(path) -> dict[str, int]:
    """事件循环外面数一遍每张表的行数（不含 SQLite 内部表）。"""
    conn = sqlite3.connect(path)
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite~_%' ESCAPE '~'"
            )
        ]
        return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    finally:
        conn.close()


def _business_rows(counts: dict[str, int]) -> int:
    return sum(n for name, n in counts.items() if name != "alembic_version")


def test_the_command_line_prints_one_row_per_table_and_reports_committed(tmp_path, capsys):
    code = main(["--from", _seed_cli_source(tmp_path), "--to", _target_shape(tmp_path)])

    captured = capsys.readouterr()
    assert code == 0
    table_lines = [line for line in captured.out.splitlines() if "digest=" in line]
    assert len(table_lines) == len(_model_tables())  # 每张被搬的表一行，一张不落
    assert all(line.endswith("digest=OK") for line in table_lines)
    assert any(line.startswith("videos ") and " rows=2" in line for line in table_lines)
    assert "total rows: 4" in captured.out
    assert captured.out.splitlines()[-1] == "committed"
    assert captured.err == ""

    warn = [line for line in captured.out.splitlines() if line.startswith("WARN")]
    # 警告行永远至少两条：会话表压根不在搬运范围（所以每次搬都「留在原库」），
    # 外加那个只活在老库里的列。两条都在 stdout 上，不是 stderr。
    assert len(warn) == 2
    assert any("new_videos.viewed" in line and "1 行" in line for line in warn)
    assert any("sessions" in line for line in warn)
    # 模块开头写着「命令行输出保持 ASCII」——表格行确实全 ASCII，警告行不是。
    assert all(ord(ch) < 128 for line in table_lines for ch in line)
    assert all(any(ord(ch) > 127 for ch in line) for line in warn)

    counts = _sqlite_counts(tmp_path / "target.db")
    assert counts["videos"] == 2 and counts["new_videos"] == 1
    assert counts["sessions"] == 0  # 会话不搬，从命令行进来也一样


def test_the_command_line_dry_run_reports_the_same_and_writes_nothing(tmp_path, capsys):
    source = _seed_cli_source(tmp_path)
    target = _target_shape(tmp_path)

    code = main(["--from", source, "--to", target, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.splitlines()[-1] == "dry-run: rolled back, nothing written"
    assert "committed" not in captured.out
    assert any("digest=OK" in line for line in captured.out.splitlines())
    assert _business_rows(_sqlite_counts(tmp_path / "target.db")) == 0


def test_the_command_line_abort_path_says_why_on_stderr_and_exits_one(tmp_path, capsys):
    """闸门拒收时：原因在 stderr、退出码 1、stdout 一个字也没有。

    「退回 1」和「把原因说清楚」是同一件事的两半——搬库是在没人盯着的机器上跑的，
    一句 ABORTED 后面不跟着原因，就得去猜是哪张库不对。
    """
    path = tmp_path / "ancient.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE videos (id INTEGER NOT NULL PRIMARY KEY, filepath VARCHAR(1024))")
        )
    engine.dispose()
    target = _target_shape(tmp_path)

    code = main(["--from", _url(path), "--to", target])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith("ABORTED:")
    assert "缺表" in captured.err
    assert captured.out == ""
    assert _business_rows(_sqlite_counts(tmp_path / "target.db")) == 0


def test_the_command_line_defaults_the_new_library_to_the_app_own_database(
    capsys, monkeypatch
):
    """不带 --to 时，默认目标就是应用自己配的那张库——这条接线必须在纸面上钉住。

    真按默认值搬一次就是往开发库里写数据，所以这一条把 ``transfer`` 换成记录用的替身，
    钉的是「argv 里没给地址时那个字符串是从 settings.database_url 取的」这一步，以及
    --from / --to 没有接反（替身收到的是这一对精确的值）。顺手断言连接串一个字也没被打出去：
    那里面带着口令。表格行照跑，因为替身返回的是真表形状的一份报告。
    """
    sentinel = "postgresql+asyncpg://sentinel-only:never-connected@localhost/never"
    seen: list[tuple[str, str, bool]] = []

    async def record(source: str, target: str, *, dry_run: bool) -> TransferReport:
        seen.append((source, target, dry_run))
        return TransferReport(
            moves=[TableMove(name="videos", rows=1, source_digest="d", target_digest="d")]
        )

    monkeypatch.setattr(db_transfer, "settings", SimpleNamespace(database_url=sentinel))
    monkeypatch.setattr(db_transfer, "transfer", record)

    assert main(["--from", "sqlite+aiosqlite:///cli-from.db"]) == 0
    assert main(["--from", "sqlite+aiosqlite:///cli-from.db", "--dry-run"]) == 0

    assert seen == [
        ("sqlite+aiosqlite:///cli-from.db", sentinel, False),
        ("sqlite+aiosqlite:///cli-from.db", sentinel, True),
    ]
    captured = capsys.readouterr()
    assert sentinel not in captured.out and sentinel not in captured.err
    assert "videos" in captured.out
