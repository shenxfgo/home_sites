"""Tests for the watch stats endpoint."""
import pytest
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.database.base import Base
import src.models  # noqa: F401
from src.models.video import Video
from src.models.source import VideoSource
from src.models.watch_event import WatchEvent


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


async def _seed(session):
    """Two videos and a small log: yesterday 600s, today 60s on one of them."""
    from src.models.tag import Tag, video_tags

    source = VideoSource(name="媒体库", path="/media", type="local")
    session.add(source)
    await session.commit()

    first = Video(source_id=source.id, filepath="/a.mp4", title="暗涌", duration=120)
    second = Video(source_id=source.id, filepath="/b.mp4", title="长夜", duration=120)
    tag = Tag(name="悬疑", color="#7c6cff")
    session.add_all([first, second, tag])
    await session.commit()
    await session.execute(video_tags.insert(), [{"video_id": first.id, "tag_id": tag.id}])

    now = datetime.now(timezone.utc)
    session.add_all([
        WatchEvent(
            video_id=first.id,
            seconds=600,
            occurred_at=(now - timedelta(days=1)).replace(hour=12, minute=0, second=0),
        ),
        WatchEvent(
            video_id=first.id,
            seconds=60,
            occurred_at=now.replace(hour=12, minute=0, second=0),
        ),
    ])
    await session.commit()


@pytest.mark.asyncio
async def test_watch_stats_endpoint_aggregates_the_log(client, db_session):
    """The stats page reads one endpoint for numbers, chart and tag split."""
    await _seed(db_session)

    response = await client.get("/api/history/stats", params={"days": 7})
    assert response.status_code == 200
    stats = response.json()

    assert stats["days"] == 7
    assert (stats["window_seconds"], stats["videos_watched"], stats["active_days"]) == (
        660,
        1,
        2,
    )
    assert stats["longest_streak_days"] == 2
    assert len(stats["daily"]) == 7
    assert stats["daily"][-1]["seconds"] == 60
    assert stats["tags"] == [{"name": "悬疑", "color": "#7c6cff", "seconds": 660}]


@pytest.mark.asyncio
async def test_watch_stats_endpoint_is_not_a_history_id(client, db_session):
    """``/stats`` sits with the other fixed routes, ahead of /{history_id}."""
    response = await client.get("/api/history/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["days"] == 30
    assert stats["window_seconds"] == 0
    assert all(entry["seconds"] == 0 for entry in stats["daily"])


@pytest.mark.asyncio
async def test_watch_stats_rejects_an_impossible_window(client):
    """A window this short would not make a chart, and one this long a scan."""
    for days in (3, 500):
        response = await client.get("/api/history/stats", params={"days": days})
        assert response.status_code == 422
