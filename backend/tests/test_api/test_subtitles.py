"""Tests for subtitle API endpoints."""
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.base import Base
from src.models.source import VideoSource
from src.models.video import Video
from src.utils.subtitles import SubtitleConversionError
import src.models  # noqa: F401


@pytest.fixture
async def db_session():
    """Create a fresh in-memory database for API tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

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


async def _video_with_subtitle(db_session, tmp_path, content="1\n00:00:01,000 --> 00:00:02,000\n你好\n"):
    """Create a video plus a sidecar subtitle file on disk."""
    directory = tmp_path / "media"
    directory.mkdir(exist_ok=True)
    (directory / "movie.mp4").write_text("dummy", encoding="utf-8")
    subtitle_path = directory / "movie.zh.srt"
    subtitle_path.write_text(content, encoding="utf-8")

    source = VideoSource(name="Test Source", path=str(directory), type="local")
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, filepath=str(directory / "movie.mp4"), title="Movie")
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video, subtitle_path


async def test_list_subtitles_is_empty_by_default(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.get(f"/api/videos/{video.id}/subtitles")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_list_and_delete_subtitle(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)

    created = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(subtitle_path)},
    )
    assert created.status_code == 201
    subtitle_id = created.json()["id"]
    assert created.json()["language"] == "zh"
    assert created.json()["label"] == "zh"

    listed = await client.get(f"/api/videos/{video.id}/subtitles")
    assert [item["id"] for item in listed.json()] == [subtitle_id]

    deleted = await client.delete(
        f"/api/videos/{video.id}/subtitles/{subtitle_id}"
    )
    assert deleted.status_code == 204

    after = await client.get(f"/api/videos/{video.id}/subtitles")
    assert after.json() == []


async def test_create_rejects_non_subtitle_extension(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(tmp_path / "media" / "movie.mp4")},
    )

    assert response.status_code == 400
    assert "不支持的字幕格式" in response.json()["detail"]


async def test_create_rejects_missing_file(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(tmp_path / "media" / "missing.zh.srt")},
    )

    assert response.status_code == 400
    assert "字幕文件不存在" in response.json()["detail"]


async def test_create_rejects_path_outside_video_directory(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)
    outside = tmp_path / "secret.zh.srt"
    outside.write_text("1\n", encoding="utf-8")

    response = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": str(outside)},
    )

    assert response.status_code == 400
    assert "视频所在目录" in response.json()["detail"]


async def test_stream_converts_srt_to_webvtt(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)
    created = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(subtitle_path)}
    )
    subtitle_id = created.json()["id"]

    response = await client.get(
        f"/api/videos/{video.id}/subtitles/{subtitle_id}/stream"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/vtt")
    assert response.text.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.000" in response.text
    assert "你好" in response.text


async def test_stream_returns_404_for_unknown_subtitle(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.get(f"/api/videos/{video.id}/subtitles/999/stream")

    assert response.status_code == 404


async def test_stream_returns_404_when_file_disappeared(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)
    created = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(subtitle_path)}
    )
    subtitle_path.unlink()

    response = await client.get(
        f"/api/videos/{video.id}/subtitles/{created.json()['id']}/stream"
    )

    assert response.status_code == 404


async def test_stream_reports_unconvertible_subtitle_as_415(client, db_session, tmp_path):
    video, subtitle_path = await _video_with_subtitle(db_session, tmp_path)
    created = await client.post(
        f"/api/videos/{video.id}/subtitles", json={"filepath": str(subtitle_path)}
    )

    with patch(
        "src.api.subtitles.convert_to_webvtt",
        side_effect=SubtitleConversionError("字幕转换失败"),
    ):
        response = await client.get(
            f"/api/videos/{video.id}/subtitles/{created.json()['id']}/stream"
        )

    assert response.status_code == 415


async def test_delete_unknown_subtitle_returns_404(client, db_session, tmp_path):
    video, _ = await _video_with_subtitle(db_session, tmp_path)

    response = await client.delete(f"/api/videos/{video.id}/subtitles/4242")

    assert response.status_code == 404
