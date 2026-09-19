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
    history fixes are applied here: the rows a pre-upgrade database may already
    hold are collapsed to one per video before its unique index is added.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(DEDUPE_PLAY_HISTORY))
        await conn.execute(text(PLAY_HISTORY_VIDEO_UNIQUE_INDEX))


async def get_session() -> AsyncSession:
    """Dependency injection for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()