"""启动选路与会话收尾：`src/database/session.py` 那 11 行第一次真的被执行。

coverage 里缺的是 `205-210`（`init_db` 选哪条路）和 `278-282`（`get_session` 的 yield 与
`finally` 收尾）。两处的共同点是**只有生产在用、测试从不进来**：启动那一份用例
（`test_app_boot_lifespan.py`）把 `init_db` 换成一个只登记名字的替身，`test_cli.py` 同样换掉它，
而所有走 HTTP 的用例都经 `app.dependency_overrides[get_session]`（`conftest.py:190`）借测试自己的
会话——于是"库来了以后走哪条路"和"一个请求的会话到底还不还回去"这两格零钉子，而后者恰好是
少一行 `close()` 也不报错、只在连接池被抽干的那天炸的那种东西。

这里不换替身：`init_db` 真跑，`get_session` 直接从生成器那一头消费。两者读的都是**模块级**的
`engine` / `async_session_maker`，而那两个默认指向 `settings.database_url`，所以每台引擎都换成
`tmp_path` 上一个独立的 SQLite 文件库——留着默认值就会去动开发库。迁移语句本身在两种方言上都由
`conftest._prepare_schema` 每轮跑过（PG 分支跑的是真 PG），这一层钉的是**选路**。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import src.models  # noqa: F401  # 导入即注册，模型声明的全部表都要在 metadata 里
from src.database import migrations
from src.database import session as session_module
from src.database.base import Base
from src.database.session import get_session, init_db

_TAG_INSERT = (
    "INSERT INTO tags (name, color, created_at) "
    "VALUES ('{name}', '#ffffff', '2026-01-01')"
)


def _head() -> str:
    return ScriptDirectory(str(migrations.ALEMBIC_DIR)).get_current_head()


def _first_revision() -> str:
    """修订链最底下那一环：没有 `down_revision` 的那个。"""
    return next(
        script.revision
        for script in ScriptDirectory(str(migrations.ALEMBIC_DIR)).walk_revisions()
        if script.down_revision is None
    )


def _shape(sync_conn: object) -> list[object]:
    """库与模型声明的差异清单；空列表意味着两边一字不差。"""
    return list(compare_metadata(MigrationContext.configure(sync_conn), Base.metadata))  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def boot_engine(tmp_path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    """模块级那台 `engine` 和那个 maker 换成 `tmp_path` 上的独立文件库。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'boot.db'}")
    session_module.enforce_sqlite_foreign_keys(engine)
    monkeypatch.setattr(session_module, "engine", engine)
    monkeypatch.setattr(
        session_module,
        "async_session_maker",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    yield engine
    await engine.dispose()


async def test_an_empty_database_is_built_by_the_baseline_and_ends_at_head(
    boot_engine: AsyncEngine,
) -> None:
    async with boot_engine.connect() as conn:
        assert await conn.run_sync(migrations.business_tables) == set()

    await init_db()

    async with boot_engine.connect() as conn:
        tables = await conn.run_sync(migrations.business_tables)
        revision = await conn.run_sync(migrations.current_revision)
        drift = await conn.run_sync(_shape)
    assert revision == _head()
    assert tables == set(Base.metadata.tables)
    assert drift == []


async def test_a_legacy_database_is_repaired_then_claimed_and_keeps_its_rows(
    boot_engine: AsyncEngine,
) -> None:
    """有表、没有版本行的老库走的是补齐 + stamp 那条路，不是 upgrade。

    这一条不需要额外的替身就能钉住分支：走错的话 `upgrade_head` 会对已经存在的表再
    `CREATE TABLE` 一次，直接 `OperationalError: table tags already exists`（实测）。
    """
    async with boot_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Base.metadata.tables["tags"]])
        await conn.execute(text(_TAG_INSERT.format(name="before-alembic")))

    async with boot_engine.connect() as conn:
        assert await conn.run_sync(session_module._is_unversioned_legacy) is True

    await init_db()

    async with boot_engine.connect() as conn:
        tables = await conn.run_sync(migrations.business_tables)
        revision = await conn.run_sync(migrations.current_revision)
        drift = await conn.run_sync(_shape)
        survivor = (
            await conn.execute(text("SELECT name FROM tags WHERE name = 'before-alembic'"))
        ).scalar()
    assert revision == _head()
    assert tables == set(Base.metadata.tables)
    assert drift == []
    assert survivor == "before-alembic", "补齐那一路把老库的行弄丢了"


async def test_a_second_boot_on_a_versioned_database_changes_nothing(
    boot_engine: AsyncEngine,
) -> None:
    await init_db()
    async with boot_engine.begin() as conn:
        await conn.execute(text(_TAG_INSERT.format(name="kept")))

    await init_db()

    async with boot_engine.connect() as conn:
        revision = await conn.run_sync(migrations.current_revision)
        drift = await conn.run_sync(_shape)
        kept = (await conn.execute(text("SELECT COUNT(*) FROM tags WHERE name = 'kept'"))).scalar()
    assert revision == _head()
    assert drift == []
    assert kept == 1


async def test_a_pending_revision_is_applied_on_the_next_boot(boot_engine: AsyncEngine) -> None:
    """只跑到第一个修订的库，下一次启动应当把剩下的修订补上。"""
    first = _first_revision()
    async with boot_engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: migrations._run("upgrade", sync_conn, first))

    async with boot_engine.connect() as conn:
        assert await conn.run_sync(migrations.current_revision) == first
        assert "transcode_outputs" not in await conn.run_sync(migrations.business_tables)

    await init_db()

    async with boot_engine.connect() as conn:
        tables = await conn.run_sync(migrations.business_tables)
        revision = await conn.run_sync(migrations.current_revision)
        drift = await conn.run_sync(_shape)
    assert revision == _head()
    assert "transcode_outputs" in tables
    assert drift == []


async def test_get_session_hands_out_a_working_session_on_that_engine(
    boot_engine: AsyncEngine,
) -> None:
    """`get_session` 用的是**调用时**那个模块级 maker，不是导入时抓到的一份。

    交出来的会话得真能打库（提交的那一行从另一条连接读得回来），并且绑的就是 maker 手里
    那台引擎——这两句一起挡住"替身演得太像"：换成一个凭空造的会话，第一句红。
    """
    await init_db()
    generator = get_session()
    session = await generator.__anext__()
    try:
        assert session.get_bind() is boot_engine.sync_engine
        await session.execute(text(_TAG_INSERT.format(name="committed")))
        await session.commit()
    finally:
        await generator.aclose()

    probe = text("SELECT name FROM tags WHERE name = 'committed'")
    async with boot_engine.connect() as conn:
        landed = (await conn.execute(probe)).scalar()
    assert landed == "committed"


async def test_get_session_gives_the_connection_back_when_the_request_ends(
    boot_engine: AsyncEngine,
) -> None:
    await init_db()
    generator = get_session()
    session = await generator.__anext__()
    await session.execute(text("SELECT 1"))
    assert boot_engine.pool.checkedout() == 1, "会话没从池里拿连接，下面那句断言就是空的"

    with pytest.raises(StopAsyncIteration):
        await generator.__anext__()
    assert boot_engine.pool.checkedout() == 0


async def test_get_session_gives_the_connection_back_when_the_consumer_raises(
    boot_engine: AsyncEngine,
) -> None:
    """请求处理中途抛异常（校验失败、500、客户端断开）时，连接一样得还回去。

    这一句钉的是 `finally`：只写 `yield` 不写收尾的话，正常那一路也会被 `async with` 兜住，
    偏偏异常这一路才漏。
    """
    await init_db()
    generator = get_session()
    session = await generator.__anext__()
    await session.execute(text("SELECT 1"))
    assert boot_engine.pool.checkedout() == 1

    with pytest.raises(RuntimeError, match="consumer blew up"):
        await generator.athrow(RuntimeError("consumer blew up"))
    assert boot_engine.pool.checkedout() == 0


async def test_get_session_does_not_carry_an_uncommitted_write_out(
    boot_engine: AsyncEngine,
) -> None:
    await init_db()
    generator = get_session()
    session = await generator.__anext__()
    await session.execute(text(_TAG_INSERT.format(name="half-written")))
    await generator.aclose()

    async with boot_engine.connect() as conn:
        leaked = (
            await conn.execute(text("SELECT COUNT(*) FROM tags WHERE name = 'half-written'"))
        ).scalar()
    assert leaked == 0, "没提交的写跟着会话出去了"
