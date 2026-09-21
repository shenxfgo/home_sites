from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from .base import Base


# Collapses the history table to one row per (person, video): the row holding
# the most recent watch survives, the rest are dropped. Databases written before
# history stopped appending can hold several rows per title, and ``IS`` (not
# ``=``) is what lets the still-unclaimed rows with a NULL owner collapse too.
DEDUPE_PLAY_HISTORY = """
DELETE FROM play_history
 WHERE id NOT IN (
     SELECT (SELECT keep.id
               FROM play_history keep
              WHERE keep.video_id = current.video_id
                AND keep.user_id IS current.user_id
              ORDER BY keep.played_at DESC, keep.id DESC
              LIMIT 1)
       FROM play_history current
 )
"""

# The same video used to be unique on its own, which is exactly what two people
# watching one title must not hit. Old databases carry that index by name.
DROP_PLAY_HISTORY_VIDEO_UNIQUE_INDEX = """
DROP INDEX IF EXISTS ix_play_history_video_id
"""

PLAY_HISTORY_USER_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_play_history_user_video
    ON play_history (user_id, video_id)
"""

# ``favorites`` never had a unique constraint, so a legacy database can already
# hold the same title twice for one person; the index would refuse the table.
DEDUPE_FAVORITES = """
DELETE FROM favorites
 WHERE id NOT IN (
     SELECT (SELECT keep.id
               FROM favorites keep
              WHERE keep.video_id = current.video_id
                AND keep.user_id IS current.user_id
              ORDER BY keep.created_at ASC, keep.id ASC
              LIMIT 1)
       FROM favorites current
 )
"""

FAVORITES_USER_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_favorite_user_video
    ON favorites (user_id, video_id)
"""

# Lists are per person too, and two of them may not share a name. Numbering the
# later copies keeps a legacy database whose owner claims both from failing the
# UPDATE; nothing gets deleted, and a run over already-distinct names does
# nothing.
DEDUPE_WATCHLIST_NAMES = """
UPDATE watchlists
   SET name = name || ' (2)'
 WHERE id > (SELECT MIN(keep.id) FROM watchlists keep WHERE keep.name = watchlists.name)
"""

WATCHLIST_OWNER_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlist_owner_name
    ON watchlists (owner_id, name)
"""


# Columns added after the first release. ``create_all`` never alters a table it
# already created, so a database written before them gets each one in turn.
# The ownership columns stay nullable here on purpose: rows a household already
# wrote have no owner until the first owner account claims them (see
# ``AuthService.claim_legacy_rows``), and SQLite cannot add a column that is
# NOT NULL without a default that would be a lie.
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("videos", "series", "ALTER TABLE videos ADD COLUMN series VARCHAR(512)"),
    ("videos", "season", "ALTER TABLE videos ADD COLUMN season INTEGER"),
    ("videos", "episode", "ALTER TABLE videos ADD COLUMN episode INTEGER"),
    (
        "videos",
        "is_missing",
        "ALTER TABLE videos ADD COLUMN is_missing INTEGER NOT NULL DEFAULT 0",
    ),
    ("favorites", "user_id", "ALTER TABLE favorites ADD COLUMN user_id INTEGER"),
    ("play_history", "user_id", "ALTER TABLE play_history ADD COLUMN user_id INTEGER"),
    ("watch_events", "user_id", "ALTER TABLE watch_events ADD COLUMN user_id INTEGER"),
    ("watchlists", "owner_id", "ALTER TABLE watchlists ADD COLUMN owner_id INTEGER"),
)

VIDEOS_SERIES_INDEX = """
CREATE INDEX IF NOT EXISTS ix_videos_series ON videos (series)
"""

# ``settings.theme`` 是全家共用一个外观：一个人切深色，其他人的界面跟着变。M3 把
# 这个选择搬进了 ``user_preferences``，所以升级时先按老值给每个还没有偏好行的账号
# 铺一份（保持他们此刻看到的界面不变），再删掉那个共享键。CASE 只认那三个取值，
# 老库里写进过别的东西就落回 light，不会拼出一段解析不了的 JSON。
INHERIT_THEME_IN_PREFERENCES = """
INSERT OR IGNORE INTO user_preferences (user_id, prefs, updated_at)
SELECT u.id,
       CASE s.value WHEN 'dark' THEN '{"theme":"dark"}'
                    WHEN 'auto' THEN '{"theme":"auto"}'
                    ELSE '{"theme":"light"}' END,
       CURRENT_TIMESTAMP
  FROM users u
  JOIN settings s ON s.key = 'theme'
 WHERE u.id NOT IN (SELECT user_id FROM user_preferences)
"""

DROP_SHARED_THEME_SETTING = """
DELETE FROM settings WHERE key = 'theme'
"""

# ``ALTER TABLE ADD COLUMN`` does not honour the ``index=True`` the models
# declare, so every per-person lookup column needs its index spelled out.
OWNERSHIP_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_favorites_user_id ON favorites (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_play_history_user_id ON play_history (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_watch_events_user_id ON watch_events (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_watchlists_owner_id ON watchlists (owner_id)",
)


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
    """Bring the configured database up to the current schema."""
    async with engine.begin() as conn:
        await apply_schema_fixes(conn)


async def apply_schema_fixes(conn) -> None:
    """Create missing tables and migrate an existing one in place.

    ``create_all`` only adds missing tables, never alters existing ones, so the
    ownership columns and the index changes added since the first release are
    applied here. Order matters: a column has to exist before a statement that
    mentions it runs, and rows must be collapsed before the unique index that
    enforces the collapse is added. Every statement is idempotent, so this runs
    on each boot and a migration can be replayed against a copy of the data.
    """
    await conn.run_sync(Base.metadata.create_all)
    await _add_missing_columns(conn)
    await conn.execute(text(DEDUPE_PLAY_HISTORY))
    await conn.execute(text(DROP_PLAY_HISTORY_VIDEO_UNIQUE_INDEX))
    await conn.execute(text(PLAY_HISTORY_USER_UNIQUE_INDEX))
    await conn.execute(text(DEDUPE_FAVORITES))
    await conn.execute(text(FAVORITES_USER_UNIQUE_INDEX))
    await conn.execute(text(DEDUPE_WATCHLIST_NAMES))
    await conn.execute(text(WATCHLIST_OWNER_UNIQUE_INDEX))
    await conn.execute(text(VIDEOS_SERIES_INDEX))
    for statement in OWNERSHIP_INDEXES:
        await conn.execute(text(statement))
    await conn.execute(text(INHERIT_THEME_IN_PREFERENCES))
    await conn.execute(text(DROP_SHARED_THEME_SETTING))


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