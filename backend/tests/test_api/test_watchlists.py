"""Tests for the watchlist CRUD endpoints and the queue routes."""
import pytest

from src.models.video import Video

async def _create_video(db_session, video_id, title, *, progress=None, user_id=None):
    """Seed one title, optionally with a position one person stopped at."""
    from src.models.history import PlayHistory

    video = Video(
        id=video_id,
        source_id=1,
        filepath=f"/test/{title}.mp4",
        title=title,
        duration=600,
    )
    db_session.add(video)
    if progress is not None:
        db_session.add(
            PlayHistory(user_id=user_id, video_id=video_id, progress=progress)
        )
    await db_session.commit()
    return video


async def _create_list(client, name="今晚看这些"):
    response = await client.post("/api/watchlists", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_a_watchlist_can_be_created_renamed_and_deleted(client):
    list_id = await _create_list(client)

    renamed = await client.put(f"/api/watchlists/{list_id}", json={"name": "明晚再看"})

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "明晚再看"
    assert (await client.delete(f"/api/watchlists/{list_id}")).status_code == 204
    assert (await client.get(f"/api/watchlists/{list_id}")).status_code == 404


@pytest.mark.asyncio
async def test_titles_join_the_queue_in_the_order_they_are_added(client, db_session):
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    list_id = await _create_list(client)

    await client.post(f"/api/watchlists/{list_id}/videos", json={"video_id": 2})
    added = await client.post(f"/api/watchlists/{list_id}/videos", json={"video_id": 1})

    assert [item["title"] for item in added.json()["items"]] == ["长夜", "暗涌"]
    assert [item["id"] for item in added.json()["items"]] == [2, 1]


@pytest.mark.asyncio
async def test_the_queue_carries_the_watch_position_of_each_title(
    client, db_session, signed_in_user
):
    """今晚看这些 is a queue to resume, so each row has to say what is left."""
    await _create_video(
        db_session, 1, "暗涌", progress=180, user_id=signed_in_user.id
    )
    list_id = await _create_list(client)
    await client.post(f"/api/watchlists/{list_id}/videos", json={"video_id": 1})

    listed = await client.get("/api/watchlists")

    assert listed.json()[0]["items"][0]["progress"] == 180


@pytest.mark.asyncio
async def test_removing_a_title_keeps_the_list_and_the_video(client, db_session):
    await _create_video(db_session, 1, "暗涌")
    list_id = await _create_list(client)
    await client.post(f"/api/watchlists/{list_id}/videos", json={"video_id": 1})

    removed = await client.delete(f"/api/watchlists/{list_id}/videos/1")

    assert removed.status_code == 200
    assert removed.json()["items"] == []
    assert (await client.get("/api/videos/1")).status_code == 200


@pytest.mark.asyncio
async def test_a_list_can_be_found_by_the_title_it_holds(client, db_session):
    await _create_video(db_session, 1, "暗涌")
    await _create_video(db_session, 2, "长夜")
    mine = await _create_list(client, "今晚看这些")
    await _create_list(client, "以后再说")
    await client.post(f"/api/watchlists/{mine}/videos", json={"video_id": 1})

    holding = await client.get("/api/watchlists", params={"video_id": 1})
    empty = await client.get("/api/watchlists", params={"video_id": 2})

    assert [entry["name"] for entry in holding.json()] == ["今晚看这些"]
    assert empty.json() == []


@pytest.mark.asyncio
async def test_unknown_ids_answer_404_instead_of_a_half_done_queue(client, db_session):
    await _create_video(db_session, 1, "暗涌")
    list_id = await _create_list(client)

    assert (await client.post(f"/api/watchlists/{list_id}/videos", json={"video_id": 999})).status_code == 404
    assert (await client.post("/api/watchlists/999/videos", json={"video_id": 1})).status_code == 404
    assert (await client.put("/api/watchlists/999", json={"name": "无关"})).status_code == 404
    assert (await client.delete("/api/watchlists/999")).status_code == 404


@pytest.mark.asyncio
async def test_a_name_is_required(client):
    assert (await client.post("/api/watchlists", json={"name": ""})).status_code == 422
