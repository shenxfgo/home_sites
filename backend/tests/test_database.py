# tests/test_database.py
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# The table as it looked before history stopped appending: a plain video_id
# column that happily accepted several rows per title.
LEGACY_PLAY_HISTORY_TABLE = """
CREATE TABLE play_history (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    played_at DATETIME,
    progress INTEGER NOT NULL,
    completed BOOLEAN NOT NULL
)
"""


@pytest.mark.asyncio
async def test_database_initialization():
    """Test that database can be initialized"""
    from src.database import init_db, async_session_maker
    from sqlalchemy import text

    await init_db()

    async with async_session_maker() as session:
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = result.fetchall()
        # Should have no tables initially, just the database created
        assert isinstance(tables, list)


@pytest.mark.asyncio
async def test_schema_setup_collapses_legacy_history_rows():
    """The one-row-per-video index is only addable once the duplicates are gone."""
    from src.database.session import DEDUPE_PLAY_HISTORY, PLAY_HISTORY_VIDEO_UNIQUE_INDEX

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text(LEGACY_PLAY_HISTORY_TABLE))
        await conn.execute(
            text(
                "INSERT INTO play_history (video_id, played_at, progress, completed) VALUES "
                "(1, '2026-01-01 10:00:00', 45, 0),"
                "(1, '2026-01-02 09:00:00', 20, 0),"
                "(2, '2026-01-01 08:00:00', 5, 0)"
            )
        )

        await conn.execute(text(DEDUPE_PLAY_HISTORY))
        await conn.execute(text(PLAY_HISTORY_VIDEO_UNIQUE_INDEX))

        rows = await conn.execute(
            text("SELECT video_id, played_at, progress FROM play_history ORDER BY video_id")
        )
        assert rows.fetchall() == [
            (1, "2026-01-02 09:00:00", 20),
            (2, "2026-01-01 08:00:00", 5),
        ]

    async with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text("INSERT INTO play_history (video_id, progress, completed) VALUES (1, 0, 0)")
            )

    await engine.dispose()