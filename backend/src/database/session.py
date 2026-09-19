from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from .base import Base


# Collapses the history table to one row per video: the row holding the most
# recent watch survives for each video, the rest are dropped. Databases written
# before history stopped appending can hold several rows per title.
DEDUPE_PLAY_HISTORY = """
DELETE FROM play_history
 WHERE id NOT IN (
     SELECT (SELECT keep.id
               FROM play_history keep
              WHERE keep.video_id = current.video_id
              ORDER BY keep.played_at DESC, keep.id DESC
              LIMIT 1)
       FROM play_history current
 )
"""

PLAY_HISTORY_VIDEO_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS ix_play_history_video_id
    ON play_history (video_id)
"""


# Columns added after the first release. ``create_all`` never alters a table it
# already created, so a database written before them gets each one in turn.
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("videos", "series", "ALTER TABLE videos ADD COLUMN series VARCHAR(512)"),
    ("videos", "season", "ALTER TABLE videos ADD COLUMN season INTEGER"),
    ("videos", "episode", "ALTER TABLE videos ADD COLUMN episode INTEGER"),
    (
        "videos",
        "is_missing",
        "ALTER TABLE videos ADD COLUMN is_missing INTEGER NOT NULL DEFAULT 0",
    ),
)

VIDEOS_SERIES_INDEX = """
CREATE INDEX IF NOT EXISTS ix_videos_series ON videos (series)
"""


# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

# Create async session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables and bring an existing database up to the current schema.

    ``create_all`` only adds missing tables, never alters existing ones, so the
    history fixes and the columns added since the first release are applied
    here: the rows a pre-upgrade database may already hold are collapsed to one
    per video before its unique index is added.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(DEDUPE_PLAY_HISTORY))
        await conn.execute(text(PLAY_HISTORY_VIDEO_UNIQUE_INDEX))
        await _add_missing_columns(conn)
        await conn.execute(text(VIDEOS_SERIES_INDEX))


async def _add_missing_columns(conn) -> None:
    """Apply every :data:`ADDED_COLUMNS` statement the database lacks."""
    seen: dict[str, set[str]] = {}
    for table, column, statement in ADDED_COLUMNS:
        if table not in seen:
            rows = await conn.execute(text(f"PRAGMA table_info({table})"))
            seen[table] = {row[1] for row in rows}
        if column not in seen[table]:
            await conn.execute(text(statement))
            seen[table].add(column)


async def get_session() -> AsyncSession:
    """Dependency injection for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()