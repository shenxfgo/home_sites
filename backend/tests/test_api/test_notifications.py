"""Tests for the notification list, read and delete endpoints."""
import pytest
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database.base import Base
import src.models  # noqa: F401


@pytest.fixture
async def db_session():
    """Create a fresh in-memory database for API tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(db_session):
    """Create async test client with an overridden database session."""
    from src.main import app
    from src.database import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def _create(db_session, title, read=False):
    """Seed one notification and return it."""
    from src.models.notification import Notification

    notification = Notification(
        type="scan_complete",
        title=title,
        message="body",
        read=read,
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.mark.asyncio
async def test_delete_one_notification_leaves_the_others(client, db_session):
    """Deleting a row removes only that row."""
    first = await _create(db_session, "扫描完成 A")
    await _create(db_session, "扫描完成 B")

    response = await client.delete(f"/api/notifications/{first.id}")
    assert response.status_code == 204

    listing = await client.get("/api/notifications")
    titles = [item["title"] for item in listing.json()["items"]]
    assert titles == ["扫描完成 B"]


@pytest.mark.asyncio
async def test_delete_missing_notification_is_not_found(client):
    """A deleted or unknown id answers 404 rather than 500."""
    response = await client.delete("/api/notifications/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_clear_notifications_empties_the_list(client, db_session):
    """The collection route wipes every row at once."""
    await _create(db_session, "A")
    await _create(db_session, "B", read=True)

    response = await client.delete("/api/notifications")
    assert response.status_code == 204

    listing = await client.get("/api/notifications")
    assert listing.json()["total"] == 0
    unread = await client.get("/api/notifications/unread")
    assert unread.json()["count"] == 0


@pytest.mark.asyncio
async def test_clear_on_an_empty_list_is_not_an_error(client):
    """Clearing nothing is a no-op, not a failure."""
    response = await client.delete("/api/notifications")

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_drops_the_unread_count(client, db_session):
    """Unread rows that are deleted stop being counted."""
    unread = await _create(db_session, "未读")
    await _create(db_session, "另一条")

    before = await client.get("/api/notifications/unread")
    assert before.json()["count"] == 2

    await client.delete(f"/api/notifications/{unread.id}")

    after = await client.get("/api/notifications/unread")
    assert after.json()["count"] == 1
