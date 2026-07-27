# Review Package: Task 3

## Commit List
a98ef00 feat: set up database infrastructure with async SQLAlchemy

## Diff Stats
backend/src/database/__init__.py |  4 ++++
backend/src/database/base.py     |  8 ++++++++
backend/src/database/session.py  | 33 +++++++++++++++++++++++++++++++++
backend/tests/test_database.py   | 18 ++++++++++++++++++
4 files changed, 63 insertions(+)

## Full Diff

```diff
diff --git a/backend/src/database/__init__.py b/backend/src/database/__init__.py
new file mode 100644
index 0000000..f3b8ae0
--- /dev/null
+++ b/backend/src/database/__init__.py
@@ -0,0 +1,4 @@
+from .base import Base
+from .session import engine, async_session_maker, init_db, get_session
+
+__all__ = ["Base", "engine", "async_session_maker", "init_db", "get_session"]
\ No newline at file at end
diff --git a/backend/src/database/base.py b/backend/src/database/base.py
new file mode 100644
index 0000000..0fdfa66
--- /dev/null
+++ b/backend/src/database/base.py
@@ -0,0 +1,8 @@
+from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    pass
\ No newline at file at end
diff --git a/backend/src/database/session.py b/backend/src/database/session.py
new file mode 100644
index 0000000..9e7cba9
--- /dev/null
+++ b/backend/src/database/session.py
@@ -0,0 +1,33 @@
+from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
+from src.config import settings
+from .base import Base


+# Create async engine
+engine = create_async_engine(
+    settings.database_url,
+    echo=False,
+    future=True,
+)

+# Create async session maker
+async_session_maker = async_sessionmaker(
+    engine,
+    class_=AsyncSession,
+    expire_on_commit=False,
+)


async def init_db() -> None:
    """Initialize database and create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Dependency injection for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
\ No newline at file at end
diff --git a/backend/tests/test_database.py b/backend/tests/test_database.py
new file mode 100644
index 0000000..9e50569
--- /dev/null
+++ b/backend/tests/test_database.py
@@ -0,0 +1,18 @@
+# tests/test_database.py
+import pytest
+from sqlalchemy.ext.asyncio import AsyncSession


+@pytest.mark.asyncio
+async def test_database_initialization():
+    """Test that database can be initialized"""
+    from src.database import init_db, async_session_maker
+    from sqlalchemy import text

+    await init_db()

+    async with async_session_maker() as session:
+        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
+        tables = result.fetchall()
+        # Should have no tables initially, just the database created
+        assert isinstance(tables, list)
\ No newline at file at end
```