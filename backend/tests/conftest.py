import sys
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add parent directory to Python path so 'src' becomes importable
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from src.database.base import Base  # noqa: E402

# Import all models so they register with Base.metadata before create_all
import src.models  # noqa: F401, E402


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh in-memory database session for each test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)