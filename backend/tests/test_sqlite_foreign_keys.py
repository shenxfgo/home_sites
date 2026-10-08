"""模型里声明的外键在两种方言下都得真的算数（#161）。

SQLite 每个连接的 ``PRAGMA foreign_keys`` 出厂是关的，PostgreSQL 一直在强制，所以同
一套模型在两边不是一套规则：孤儿子行 SQLite 收、PG 拒；绕过 ORM 的批量删除 PG 顺着
``ON DELETE CASCADE`` 连带清掉子行、SQLite 只删父表留孤儿。这个文件钉的是**行为**，
两条打的是 ``db_session`` 那条真连接（用例跑在哪个库上由 ``TEST_DATABASE_URL`` 决定，
头部会打印），所以两边各跑一次就是两份证据。

后三条打的是 :func:`enforce_sqlite_foreign_keys` 本身：它在 SQLite 上真的把开关打开、
在别的方言上不挂事件（挂上去那句 PRAGMA PG 不认），而不打开时那个孤儿插入是什么下场。
"""

import pytest
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from src.database.base import Base
from src.database.session import enforce_sqlite_foreign_keys, sqlite_foreign_keys_on_connect
from src.models.watchlist import Watchlist, WatchlistItem
from tests.support import ensure_video

#: 一条指向不存在的片单的行。``video_id`` 那头是真行，所以违规只可能出在 ``watchlist_id``。
ORPHAN_ITEM = (
    "INSERT INTO watchlist_items (watchlist_id, video_id, added_at)"
    " VALUES (1, 1, CURRENT_TIMESTAMP)"
)


async def _build_two_lists(session, user_id: int) -> tuple[int, int]:
    """一单两条、另一单一条，返回 ``要删`` 和 ``留着`` 两个 id。"""
    await ensure_video(session, 1)
    await ensure_video(session, 2)
    doomed = Watchlist(owner_id=user_id, name="要删")
    keep = Watchlist(owner_id=user_id, name="留着")
    session.add_all([doomed, keep])
    await session.commit()
    session.add_all(
        [
            WatchlistItem(watchlist_id=doomed.id, video_id=1),
            WatchlistItem(watchlist_id=doomed.id, video_id=2),
            WatchlistItem(watchlist_id=keep.id, video_id=1),
        ]
    )
    await session.commit()
    return doomed.id, keep.id


async def _count_items(session, watchlist_id: int) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(WatchlistItem)
        .where(WatchlistItem.watchlist_id == watchlist_id)
    )


@pytest.mark.asyncio
async def test_a_child_row_naming_a_parent_that_is_not_there_is_rejected(db_session, user_id):
    """收藏/片单这类子行，指向的父行不存在时两边都得拒。

    红在 SQLite 修前：那一行插得进去，库里从此多一条谁都不会读到的孤儿。
    """
    await ensure_video(db_session, 1)

    with pytest.raises(IntegrityError):
        db_session.add(WatchlistItem(watchlist_id=999, video_id=1))
        await db_session.commit()


@pytest.mark.asyncio
async def test_deleting_a_list_with_one_statement_leaves_no_children(db_session, user_id):
    """绕过 ORM 的批量删除，子行也得跟着没——这正是模型声明的 ``ondelete="CASCADE"``。

    红在 SQLite 修前：``DELETE FROM watchlists WHERE id = ?`` 只带走父行，两条子行留在
    ``watchlist_items`` 里指着已经不存在的片单。
    """
    doomed_id, keep_id = await _build_two_lists(db_session, user_id)

    await db_session.execute(delete(Watchlist).where(Watchlist.id == doomed_id))
    await db_session.commit()
    db_session.expire_all()

    assert await _count_items(db_session, doomed_id) == 0
    # 级联只管自己那一单，别人的队列一条不少。
    assert await _count_items(db_session, keep_id) == 1


@pytest.mark.asyncio
async def test_the_switch_makes_the_declaration_execute(tmp_path):
    """挂了事件的 SQLite 引擎：PRAGMA 是开的，孤儿插入当场被拒。"""
    target = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'enforced.db'}")
    enforce_sqlite_foreign_keys(target)
    try:
        async with target.connect() as conn:
            assert await conn.scalar(text("PRAGMA foreign_keys")) == 1

        async with target.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        with pytest.raises(IntegrityError):
            async with target.begin() as conn:
                await conn.execute(text(ORPHAN_ITEM))
    finally:
        await target.dispose()


@pytest.mark.asyncio
async def test_without_the_switch_the_same_orphan_insert_succeeds(tmp_path):
    """不挂事件就是修前的行为，这条把它写进用例里：声明在那儿，谁也没执行。

    上一条例只证明开关有效，这一条证明它必要——没有它，同一个插入是成功而不是报错。
    """
    target = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'unenforced.db'}")
    try:
        async with target.connect() as conn:
            assert await conn.scalar(text("PRAGMA foreign_keys")) == 0

        async with target.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text(ORPHAN_ITEM))
        async with target.connect() as conn:
            assert await conn.scalar(text("SELECT COUNT(*) FROM watchlist_items")) == 1
    finally:
        await target.dispose()


@pytest.mark.asyncio
async def test_the_switch_is_not_attached_to_a_non_sqlite_engine():
    """非 SQLite 的引擎直接不挂事件——那句 PRAGMA 换到 PG 上是语法错误，会在每个连接上炸。

    这里只建引擎不连库（地址指的是一个不存在的端口，且不带任何口令），检查的是事件注册表。
    """
    target = create_async_engine("postgresql+asyncpg://postgres@127.0.0.1:1/postgres")
    try:
        enforce_sqlite_foreign_keys(target)
        assert not event.contains(
            target.sync_engine, "connect", sqlite_foreign_keys_on_connect
        )
    finally:
        await target.dispose()


@pytest.mark.asyncio
async def test_the_engine_the_app_boots_on_is_armed():
    """``src.database.session.engine`` 必须也走过这个开关，回滚到 SQLite 那天才不是修前。

    这台机器上它是 PostgreSQL（``backend/.env``），那条早退分支就是正确答案，所以这一条
    在 PG 上只断言「没挂错东西」；把 ``DATABASE_URL`` 指回 SQLite 跑一次，它就真的在钉
    事件注册了没有——删掉 session.py 里那句调用的变异只在后者下会红。
    """
    from src.database.session import engine

    is_sqlite = engine.dialect.name == "sqlite"
    registered = event.contains(engine.sync_engine, "connect", sqlite_foreign_keys_on_connect)
    assert registered == is_sqlite
