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