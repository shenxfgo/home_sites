# Task 3: Set Up Database Infrastructure

**Files:**
- Create: `backend/src/database/base.py`
- Create: `backend/src/database/session.py`
- Create: `backend/src/database/__init__.py`

**Interfaces:**
- Consumes: `Settings` from `src/config`
- Produces: `async_session_maker`, `Base` declarative base, `init_db()` function

## Steps

### Step 1: Write the failing test for database initialization

```python
# tests/test_database.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


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
```

### Step 2: Run test to verify it fails

```bash
cd backend
uv run pytest tests/test_database.py -v
```
Expected: FAIL with "module 'src.database' not found"

### Step 3: Write minimal implementation

```python
# backend/src/database/base.py
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    pass
```

```python
# backend/src/database/session.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from .base import Base


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
```

```python
# backend/src/database/__init__.py
from .base import Base
from .session import engine, async_session_maker, init_db, get_session

__all__ = ["Base", "engine", "async_session_maker", "init_db", "get_session"]
```

### Step 4: Run test to verify it passes

```bash
cd backend
uv run pytest tests/test_database.py -v
```
Expected: PASS

### Step 5: Commit

```bash
cd backend
git add src/database/ tests/test_database.py
git commit -m "feat: set up database infrastructure with async SQLAlchemy"
```