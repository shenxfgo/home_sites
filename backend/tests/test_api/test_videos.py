"""Tests for Video API endpoints."""
import pytest

from src.api.videos import get_video_service
from src.services.video_service import VideoService


@pytest.fixture
async def extra_overrides(db_session):
    """The video route builds its service through this dependency."""

    async def override_get_video_service():
        return VideoService(db_session)

    return {get_video_service: override_get_video_service}


async def _create_source(session, name="Test Source", path="/test"):
    """Helper to create a source for tests."""
    from src.models.source import VideoSource
    source = VideoSource(name=name, path=path, type="local")
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def _create_video(
    session,
    source_id=1,
    title="Test Video",
    filepath="/test/video.mp4",
    duration=None,
    series=None,
    season=None,
    episode=None,
    file_size=None,
):
    """Helper to create a video for tests."""
    from src.models.video import Video
    video = Video(
        source_id=source_id,
        filepath=filepath,
        title=title,
        duration=duration,
        series=series,
        season=season,
        episode=episode,
        file_size=file_size,
    )
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return video


@pytest.mark.asyncio
async def test_list_videos_empty(client):
    """Test listing videos when empty."""
    response = await client.get("/api/videos")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_videos(client, db_session):
    """Test listing videos with data."""
    source = await _create_source(db_session)
    await _create_video(db_session, source_id=source.id, title="V1", filepath="/v1.mp4")
    await _create_video(db_session, source_id=source.id, title="V2", filepath="/v2.mp4")

    response = await client.get("/api/videos")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_videos_filter_source(client, db_session):
    """Test listing videos filtered by source."""
    source1 = await _create_source(db_session, name="S1", path="/s1")
    source2 = await _create_source(db_session, name="S2", path="/s2")
    await _create_video(db_session, source_id=source1.id, filepath="/s1/v1.mp4")
    await _create_video(db_session, source_id=source2.id, filepath="/s2/v1.mp4")

    response = await client.get(f"/api/videos?source_id={source1.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["source_id"] == source1.id


@pytest.mark.asyncio
async def test_list_videos_search(client, db_session):
    """Test searching videos."""
    source = await _create_source(db_session)
    await _create_video(db_session, source_id=source.id, title="The Matrix", filepath="/m.mp4")
    await _create_video(db_session, source_id=source.id, title="Inception", filepath="/i.mp4")

    response = await client.get("/api/videos?search=matrix")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "The Matrix"


@pytest.mark.asyncio
async def test_list_videos_pagination(client, db_session):
    """Test video list pagination."""
    source = await _create_source(db_session)
    for i in range(5):
        await _create_video(db_session, source_id=source.id, title=f"V{i}", filepath=f"/v{i}.mp4")

    response = await client.get("/api/videos?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


@pytest.mark.asyncio
async def test_get_video(client, db_session):
    """Test getting a specific video."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    response = await client.get(f"/api/videos/{video.id}")
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == video.id
    assert result["title"] == "Test Video"


@pytest.mark.asyncio
async def test_get_video_not_found(client):
    """Test getting a video that doesn't exist."""
    response = await client.get("/api/videos/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Video not found"


@pytest.mark.asyncio
async def test_update_video(client, db_session):
    """Test updating a video."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    response = await client.put(
        f"/api/videos/{video.id}",
        json={"title": "Updated Title", "rating": 4},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["title"] == "Updated Title"
    assert result["rating"] == 4


@pytest.mark.asyncio
async def test_update_video_not_found(client):
    """Test updating a video that doesn't exist."""
    response = await client.put("/api/videos/99999", json={"title": "test"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_video_empty_body(client, db_session):
    """Test updating a video with empty body."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    response = await client.put(f"/api/videos/{video.id}", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "No fields to update"


@pytest.mark.asyncio
async def test_delete_video(client, db_session):
    """Test deleting a video."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    response = await client.delete(f"/api/videos/{video.id}")
    assert response.status_code == 204

    # Verify deleted
    response = await client.get(f"/api/videos/{video.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_video_not_found(client):
    """Test deleting a video that doesn't exist."""
    response = await client.delete("/api/videos/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_new_videos(client, db_session):
    """Test listing new (unviewed) videos."""
    from src.models.new_video import NewVideo

    source = await _create_source(db_session)
    video1 = await _create_video(db_session, source_id=source.id, title="New 1", filepath="/n1.mp4")
    video2 = await _create_video(db_session, source_id=source.id, title="New 2", filepath="/n2.mp4")

    nv1 = NewVideo(video_id=video1.id, source_id=source.id)
    nv2 = NewVideo(video_id=video2.id, source_id=source.id)
    db_session.add_all([nv1, nv2])
    await db_session.commit()

    response = await client.get("/api/videos/new")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_mark_new_video_viewed(client, db_session):
    """Test marking a new video as viewed."""
    from src.models.new_video import NewVideo

    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)
    nv = NewVideo(video_id=video.id, source_id=source.id)
    db_session.add(nv)
    await db_session.commit()

    response = await client.post(f"/api/videos/new/{video.id}/viewed")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify marked as viewed
    await db_session.refresh(nv)
    assert nv.viewed is True


@pytest.mark.asyncio
async def test_record_play(client, db_session):
    """Test recording a play event."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    response = await client.post(f"/api/videos/{video.id}/play")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify view count increased
    await db_session.refresh(video)
    assert video.view_count == 1


@pytest.mark.asyncio
async def test_record_play_not_found(client):
    """Test recording play for non-existent video."""
    response = await client.post("/api/videos/99999/play")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_report_progress(client, db_session):
    """Test reporting playback progress."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    # First record a play
    await client.post(f"/api/videos/{video.id}/play")

    # Report progress
    response = await client.post(
        f"/api/videos/{video.id}/progress",
        json={"progress": 60},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_videos_reports_the_stored_position(client, db_session):
    """The list carries playback progress so 继续观看 needs no extra request."""
    source = await _create_source(db_session)
    watched = await _create_video(db_session, source_id=source.id, title="Seen", filepath="/s.mp4")
    fresh = await _create_video(db_session, source_id=source.id, title="Fresh", filepath="/f.mp4")

    await client.post(f"/api/videos/{watched.id}/play")
    await client.post(f"/api/videos/{watched.id}/progress", json={"progress": 75})

    response = await client.get("/api/videos")
    assert response.status_code == 200
    positions = {item["id"]: item["progress"] for item in response.json()["items"]}
    assert positions == {watched.id: 75, fresh.id: None}


@pytest.mark.asyncio
async def test_get_video_reports_the_stored_position(client, db_session):
    """The detail page resumes from the same field."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    await client.post(f"/api/videos/{video.id}/play")
    await client.post(f"/api/videos/{video.id}/progress", json={"progress": 42})

    response = await client.get(f"/api/videos/{video.id}")
    assert response.status_code == 200
    assert response.json()["progress"] == 42


@pytest.mark.asyncio
async def test_continue_list_reports_the_stored_position(client, db_session):
    """The rail's rows carry their own position, so the bar can be drawn."""
    source = await _create_source(db_session)
    video = await _create_video(db_session, source_id=source.id)

    await client.post(f"/api/videos/{video.id}/play")
    await client.post(f"/api/videos/{video.id}/progress", json={"progress": 30})

    response = await client.get("/api/history/continue")
    assert response.status_code == 200
    items = response.json()
    assert [item["id"] for item in items] == [video.id]
    assert items[0]["progress"] == 30


@pytest.mark.asyncio
async def test_list_videos_carries_series_coordinates(client, db_session):
    """The parsed series, season and episode ride along with each row."""
    source = await _create_source(db_session)
    await _create_video(
        db_session,
        source_id=source.id,
        title="海边的日子 第2集",
        filepath="/e2.mp4",
        series="海边的日子",
        season=1,
        episode=2,
    )

    response = await client.get("/api/videos")
    item = response.json()["items"][0]
    assert (item["series"], item["season"], item["episode"]) == ("海边的日子", 1, 2)


@pytest.mark.asyncio
async def test_search_reports_only_rows_whose_file_is_gone(client, db_session):
    """The 丢失 keyword is how the UI reaches the lost records."""
    source = await _create_source(db_session)
    kept = await _create_video(db_session, source_id=source.id, title="还在", filepath="/k.mp4")
    lost = await _create_video(db_session, source_id=source.id, title="没了", filepath="/l.mp4")
    lost.is_missing = True
    await db_session.commit()

    listed = (await client.get("/api/videos")).json()["items"]
    assert {item["title"]: item["is_missing"] for item in listed} == {"还在": False, "没了": True}

    found = (await client.get("/api/videos", params={"search": "丢失"})).json()
    assert found["total"] == 1
    assert found["items"][0]["id"] == lost.id


@pytest.mark.asyncio
async def test_series_progress_counts_watched_episodes_and_picks_the_next(
    client, db_session
):
    """A series reports how far it got and which episode to open next."""
    source = await _create_source(db_session)
    first = await _create_video(
        db_session, source_id=source.id, title="EP1", filepath="/1.mp4",
        duration=100, series="深夜食堂", season=1, episode=1,
    )
    second = await _create_video(
        db_session, source_id=source.id, title="EP2", filepath="/2.mp4",
        duration=100, series="深夜食堂", season=1, episode=2,
    )
    await _create_video(
        db_session, source_id=source.id, title="EP3", filepath="/3.mp4",
        duration=100, series="深夜食堂", season=1, episode=3,
    )
    await _create_video(db_session, source_id=source.id, title="电影", filepath="/m.mp4")

    await client.post(f"/api/videos/{first.id}/progress", json={"progress": 100})
    await client.post(f"/api/videos/{second.id}/progress", json={"progress": 40})

    response = await client.get("/api/videos/series")
    assert response.status_code == 200
    entries = response.json()
    assert [entry["series"] for entry in entries] == ["深夜食堂"]
    entry = entries[0]
    assert (entry["total"], entry["finished"], entry["watched"]) == (3, 1, 2)
    assert entry["next"]["id"] == second.id
    assert entry["next"]["progress"] == 40


@pytest.mark.asyncio
async def test_series_progress_is_empty_without_a_series(client):
    """A library of plain movies reports no series at all."""
    response = await client.get("/api/videos/series")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_duplicates_endpoint_reports_identical_copies(client, db_session, tmp_path):
    """GET /videos/duplicates is a list, not a video id that happens to match."""
    source = await _create_source(db_session)
    payload = b"the same file, twice" * 128
    paths = []
    for name in ("a.mkv", "b.mkv"):
        path = tmp_path / name
        path.write_bytes(payload)
        paths.append(str(path))
    kept = await _create_video(
        db_session,
        source_id=source.id,
        title="午夜列车",
        filepath=paths[0],
        duration=90,
        file_size=len(payload),
    )
    extra = await _create_video(
        db_session,
        source_id=source.id,
        title="午夜列车 备份",
        filepath=paths[1],
        duration=90,
        file_size=len(payload),
    )
    await client.post(f"/api/videos/{extra.id}/progress", json={"progress": 90})

    response = await client.get("/api/videos/duplicates")
    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 1
    group = groups[0]
    assert group["keep_id"] == extra.id
    assert (group["count"], group["file_size"], group["wasted_bytes"]) == (
        2,
        len(payload),
        len(payload),
    )
    assert [item["id"] for item in group["items"]] == [extra.id, kept.id]
    assert group["items"][0]["filepath"] == paths[1]


@pytest.mark.asyncio
async def test_duplicates_endpoint_is_empty_without_a_library(client):
    """An empty library has nothing to compare, and says so with an empty list."""
    response = await client.get("/api/videos/duplicates")
    assert response.status_code == 200
    assert response.json() == []
