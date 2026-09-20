# tests/test_database.py
"""The boot-time schema fixes, replayed against a database written before them.

There is no Alembic here: ``init_db`` is the migration, so these tests build the
old shape by hand and check that one boot turns it into the current one, that a
second boot changes nothing, and that the first owner account inherits the rows.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import apply_schema_fixes

# A single-user database: nothing owns a row, the history holds several rows per
# title, watchlist names repeat, and the read flags sit on the row itself.
LEGACY_TABLES = (
    """
    CREATE TABLE play_history (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        played_at DATETIME,
        progress INTEGER NOT NULL,
        completed BOOLEAN NOT NULL
    )
    """,
    """
    CREATE TABLE favorites (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        created_at DATETIME
    )
    """,
    """
    CREATE TABLE watch_events (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        seconds INTEGER NOT NULL,
        occurred_at DATETIME
    )
    """,
    """
    CREATE TABLE watchlists (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(100) NOT NULL,
        description VARCHAR(512),
        created_at DATETIME
    )
    """,
    """
    CREATE TABLE new_videos (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        source_id INTEGER NOT NULL,
        discovered_at DATETIME,
        viewed BOOLEAN
    )
    """,
    """
    CREATE TABLE notifications (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        type VARCHAR(50) NOT NULL,
        title VARCHAR(255) NOT NULL,
        message VARCHAR,
        read BOOLEAN,
        created_at DATETIME,
        data JSON
    )
    """,
)

LEGACY_ROWS = (
    # Two watches of video 1: the later one is the row that survives.
    "INSERT INTO play_history (video_id, played_at, progress, completed) VALUES "
    "(1, '2026-01-01 10:00:00', 45, 0),"
    "(1, '2026-01-02 09:00:00', 20, 0),"
    "(2, '2026-01-01 08:00:00', 5, 0)",
    "INSERT INTO favorites (video_id, created_at) VALUES "
    "(1, '2026-01-01 10:00:00'),(1, '2026-01-05 10:00:00'),(2, '2026-01-02 10:00:00')",
    "INSERT INTO watch_events (video_id, seconds, occurred_at) VALUES "
    "(1, 30, '2026-01-01 10:00:00')",
    "INSERT INTO watchlists (name, created_at) VALUES "
    "('tonight', '2026-01-01 10:00:00'),"
    "('tonight', '2026-01-02 10:00:00'),"
    "('weekend', '2026-01-03 10:00:00')",
    "INSERT INTO new_videos (video_id, source_id, discovered_at, viewed) VALUES "
    "(1, 1, '2026-01-01 10:00:00', 1),(2, 1, '2026-01-02 10:00:00', 0)",
    "INSERT INTO notifications (type, title, read) VALUES "
    "('scan', 'finished', 1),('scan', 'failed', 0)",
)

PASSWORD = "long-enough-password"


async def _legacy_engine():
    """An in-memory database holding only the pre-ownership tables and rows."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for statement in LEGACY_TABLES:
            await conn.execute(text(statement))
        for statement in LEGACY_ROWS:
            await conn.execute(text(statement))
    return engine


async def _column_names(conn, table: str) -> set[str]:
    rows = await conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in rows}


async def _index_names(conn, table: str) -> set[str]:
    rows = await conn.execute(text(f"PRAGMA index_list({table})"))
    return {row[1] for row in rows}


async def _scalar(conn, statement: str):
    return (await conn.execute(text(statement))).fetchall()


@pytest.mark.asyncio
async def test_legacy_database_gains_ownership_and_one_row_per_person():
    engine = await _legacy_engine()
    async with engine.begin() as conn:
        await apply_schema_fixes(conn)

        # The duplicates are gone: one history and one favourite row per video.
        assert await _scalar(
            conn,
            "SELECT video_id, played_at, progress FROM play_history ORDER BY video_id",
        ) == [(1, "2026-01-02 09:00:00", 20), (2, "2026-01-01 08:00:00", 5)]
        assert await _scalar(conn, "SELECT COUNT(*) FROM favorites") == [(2,)]
        # Numbering the later copy keeps the new (owner, name) index addable.
        assert await _scalar(conn, "SELECT name FROM watchlists ORDER BY id") == [
            ("tonight",),
            ("tonight (2)",),
            ("weekend",),
        ]

        for table, column in (
            ("favorites", "user_id"),
            ("play_history", "user_id"),
            ("watch_events", "user_id"),
            ("watchlists", "owner_id"),
        ):
            assert column in await _column_names(conn, table)

        # The per-video unique index is exactly what two people watching one
        # title must not hit, so it is replaced by the per-person one.
        indexes = await _index_names(conn, "play_history")
        assert "ux_play_history_user_video" in indexes
        assert "ix_play_history_video_id" not in indexes
        assert await _scalar(conn, "SELECT COUNT(*) FROM new_video_reads") == [(0,)]
        assert await _scalar(conn, "SELECT COUNT(*) FROM notification_reads") == [(0,)]

    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_unique_history_index_is_dropped():
    """A database whose index was already built has nothing left to dedupe."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text(LEGACY_TABLES[0]))
        await conn.execute(text("CREATE UNIQUE INDEX ix_play_history_video_id ON play_history (video_id)"))
        await conn.execute(
            text("INSERT INTO play_history (video_id, played_at, progress, completed) "
                 "VALUES (1, '2026-01-01 10:00:00', 45, 0)")
        )

        await apply_schema_fixes(conn)

        assert await _index_names(conn, "play_history") == {
            "ix_play_history_user_id",
            "ux_play_history_user_video",
        }
        # Nothing was invented or lost: the single row is still the only one.
        assert await _scalar(conn, "SELECT video_id, progress FROM play_history") == [
            (1, 45)
        ]
    await engine.dispose()


@pytest.mark.asyncio
async def test_schema_fixes_are_idempotent():
    engine = await _legacy_engine()
    async with engine.begin() as conn:
        await apply_schema_fixes(conn)
        first = (
            await _scalar(conn, "SELECT COUNT(*) FROM play_history"),
            await _scalar(conn, "SELECT COUNT(*) FROM favorites"),
            await _scalar(conn, "SELECT name FROM watchlists ORDER BY name"),
            await _index_names(conn, "play_history"),
        )

        # Every later boot runs the same statements over the migrated schema.
        await apply_schema_fixes(conn)
        second = (
            await _scalar(conn, "SELECT COUNT(*) FROM play_history"),
            await _scalar(conn, "SELECT COUNT(*) FROM favorites"),
            await _scalar(conn, "SELECT name FROM watchlists ORDER BY name"),
            await _index_names(conn, "play_history"),
        )

    assert first == second
    await engine.dispose()


@pytest.mark.asyncio
async def test_first_owner_inherits_the_legacy_rows():
    from src.services.auth_service import AuthService

    engine = await _legacy_engine()
    async with engine.begin() as conn:
        await apply_schema_fixes(conn)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        auth = AuthService(session)
        owner = await auth.create_user("owner", PASSWORD, role="owner")
        member = await auth.create_user("member", PASSWORD)

        unowned = await session.execute(
            text(
                "SELECT (SELECT COUNT(*) FROM favorites WHERE user_id IS NULL),"
                "(SELECT COUNT(*) FROM play_history WHERE user_id IS NULL),"
                "(SELECT COUNT(*) FROM watch_events WHERE user_id IS NULL),"
                "(SELECT COUNT(*) FROM watchlists WHERE owner_id IS NULL)"
            )
        )
        assert unowned.fetchone() == (0, 0, 0, 0)

        # Creating the member must not hand the same rows over a second time.
        claimed = await session.execute(
            text(
                "SELECT DISTINCT user_id FROM favorites UNION "
                "SELECT DISTINCT owner_id FROM watchlists"
            )
        )
        assert [row[0] for row in claimed] == [owner.id]

        # The global read flags became per-person rows for that owner only.
        inherited = await session.execute(
            text(
                "SELECT COUNT(*) FROM new_video_reads WHERE user_id = :uid "
                "AND new_video_id = 1"
            ),
            {"uid": owner.id},
        )
        assert inherited.fetchone() == (1,)
        assert await session.scalar(
            text("SELECT COUNT(*) FROM notification_reads WHERE user_id = :uid"),
            {"uid": owner.id},
        ) == 1
        assert await session.scalar(
            text("SELECT COUNT(*) FROM new_video_reads WHERE user_id = :uid"),
            {"uid": member.id},
        ) == 0

    await engine.dispose()
