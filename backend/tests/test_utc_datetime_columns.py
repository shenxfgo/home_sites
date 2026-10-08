"""SQLite 读回来的时间不带时区，于是"按过期时间删会话"那句批量 DELETE 在 Python 里炸（#162）。

红在修前，两条本机实测过：
`TEST_DATABASE_URL= .venv/Scripts/pytest.exe tests/test_api/test_auth.py` → **6 failed, 17 passed**
（三个文件一起是 10 failed），回溯落在 `sqlalchemy/orm/evaluator.py:263`：
`auth_service.py:179-183` 那句
`delete(UserSession).where(..., UserSession.expires_at <= _utc_now())`
是 ORM 启用的批量删除，SQLAlchemy 执行完要在 **Python 里**按同一条 WHERE 重新评估 identity map
里的对象，好把被删掉的行从内存里摘掉。SQLite 的 `DATETIME` 不存偏移，读回来的 `expires_at` 是
naive，`naive <= aware` 当场 `TypeError: can't compare offset-naive and offset-aware datetimes`。
PostgreSQL 的 `TIMESTAMP WITH TIME ZONE` 永远带偏移，所以这一条在主线上一次也没红过。

修法（用户选的是乙）：一个共享的列类型，语义就是 `src/utils/time.as_utc()`，挂到全部 21 处
`DateTime(timezone=True)` 上。**两种方言编译出来的 DDL 逐字节不变**（纯读侧），所以不需要迁移。

这三条用例**自己建一个内存 SQLite 引擎**，不吃 `db_session`：真正的病灶只在这种方言上，
跟着 `TEST_DATABASE_URL` 走的话，本机主线是 PostgreSQL，它们会绿得什么都没钉住。
"""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import DateTime, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.base import Base
from src.database.types import UTCDateTime, is_datetime_column
from src.models.user import ROLE_OWNER, User, UserSession
from src.services.auth_service import AuthService

#: 64 个十六进制字符是 `sessions.token_hash` 唯一的合法形状（见 auth_service.TOKEN_HASH_HEX）。
LIVE_TOKEN = "a" * 64
EXPIRED_TOKEN = "b" * 64


@pytest_asyncio.fixture
async def sqlite_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """一个真的内存 SQLite 库——这一单的病灶只在这种方言上。

    给的是会话工厂不是单个会话：第二条用例要两个会话才摆得出病灶（见那里的注释）。
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _account(session: AsyncSession) -> int:
    user = User(username="home-lab", password_hash="not-used-in-tests", role=ROLE_OWNER)
    session.add(user)
    await session.commit()
    return user.id


async def test_sqlite_hands_the_stored_instant_back_as_an_aware_datetime(sqlite_db):
    """写进去一个 UTC 瞬间，换会话读回来还得是**同一时刻**且带 tzinfo；NULL 不许变成 midnight。"""
    stored = datetime(2026, 10, 8, 3, 0, 0, tzinfo=timezone.utc)
    async with sqlite_db() as session:
        user_id = await _account(session)
        session.add(
            UserSession(
                token_hash=LIVE_TOKEN,
                user_id=user_id,
                expires_at=stored + timedelta(days=1),
            )
        )
        await session.commit()

    async with sqlite_db() as second:
        row = await second.scalar(select(UserSession))
        assert row.expires_at.tzinfo is not None, "SQLite 读回来是 naive，和 PG 给的形状不一样"
        assert row.expires_at == stored + timedelta(days=1)
        # 可空那一格走的是同一类型的另一条分支：没有值时必须是 None，不能补成 0001-01-01。
        assert (await second.scalar(select(User))).last_login_at is None


async def test_pruning_expired_sessions_runs_on_sqlite(sqlite_db):
    """真调用点：那句按 `expires_at <= now` 的批量删除要在 SQLite 上走得通，并且删对行。

    修前不是"结果不对"，是**当场抛 TypeError**——`AuthService.list_sessions` 第一件事就是
    `purge_expired_sessions`，于是「我的设备」那一页整页 500。
    """
    now = datetime.now(timezone.utc)
    async with sqlite_db() as session:
        user_id = await _account(session)
        session.add_all(
            [
                UserSession(
                    token_hash=EXPIRED_TOKEN,
                    user_id=user_id,
                    expires_at=now - timedelta(minutes=1),
                ),
                UserSession(
                    token_hash=LIVE_TOKEN,
                    user_id=user_id,
                    expires_at=now + timedelta(days=1),
                ),
            ]
        )
        await session.commit()

    async with sqlite_db() as second:
        # 必须先像真机那一页那样把这些行**从库里读回来并取完**：评估器重跑 WHERE 用的就是
        # identity map 里这一批 naive 对象。三种摆法只有这一种能红（全部实测过）——
        # 只 `await second.scalars(...)` 不 `.all()`，行没进 map，修前是绿的；
        # 在同一个会话里刚 `add` 完就删，对象带的是 Python 侧那个 aware 值，也比不出红；
        # 用 `expire_all()` 摆出"读回来"的形状，红点会跑到 MissingGreenlet（本机那是同步
        # 惰性加载），钉的不是这一单的病灶。
        list((await second.scalars(select(UserSession))).all())

        live = await AuthService(second).list_sessions(user_id)

        assert [row.token_hash for row in live] == [LIVE_TOKEN]
        remaining = set((await second.scalars(select(UserSession.token_hash))).all())
        assert remaining == {LIVE_TOKEN}, "过期那一行必须真的从库里没了"


def test_every_timestamp_column_uses_the_shared_type_and_compiles_unchanged():
    """把「不需要迁移」那句承诺钉住，顺带钉住"没有一列被落在外面"。

    落在外面有两种静默失败：新加的时间列忘了换类型（读回来又是 naive，#162 原地复发），
    以及换类型时把 DDL 换掉了（库里已有的表和新建的表形状不一致）。后一种在本机看不出来，
    因为主线一直是 PG——所以这里两种方言各逐字对一遍。
    """
    reference = DateTime(timezone=True)
    columns = [
        (table.name, col.name, col.type)
        for table in Base.metadata.sorted_tables
        for col in table.columns
        if is_datetime_column(col.type)
    ]
    # 遍历器一个也没找到的话，下面两个断言都是空的，这一条就什么都没钉住。
    # 23 = #162 那 21 处 + #154 给 transcode_outputs 新加的 created_at / deleted_at。
    assert len(columns) == 23, f"时间列数目变了：{[f'{t}.{c}' for t, c, _ in columns]}"

    naked = [f"{t}.{c}" for t, c, coltype in columns if not isinstance(coltype, UTCDateTime)]
    assert naked == [], "这些列还是裸的 DateTime(timezone=True)，读回来不带时区"

    for table_name, col_name, coltype in columns:
        assert coltype.compile(dialect=postgresql.dialect()) == reference.compile(
            dialect=postgresql.dialect()
        ), f"{table_name}.{col_name} 在 PG 上换了 DDL"
        assert coltype.compile(dialect=sqlite.dialect()) == reference.compile(
            dialect=sqlite.dialect()
        ), f"{table_name}.{col_name} 在 SQLite 上换了 DDL"
