"""The 越权面 list walked through the HTTP routes with two signed-in clients.

Each case states one thing the household must not be able to do to another
person's data, then asks for it over the wire and expects 404 or an empty list.
"""
import pytest

from src.models.new_video import NewVideo
from src.models.video import Video
from src.services.notification_service import NotificationService


async def _video(db_session, video_id=1, title="暗涌"):
    video = Video(
        id=video_id,
        source_id=1,
        filepath=f"/test/{title}.mp4",
        title=title,
        duration=120,
    )
    db_session.add(video)
    await db_session.commit()
    return video


@pytest.mark.asyncio
async def test_another_account_watchlist_is_not_found_on_any_route(
    client, db_session, make_signed_in_client
):
    await _video(db_session, 1)
    bob = await make_signed_in_client("bob")
    list_id = (
        await client.post("/api/watchlists", json={"name": "今晚看这些"})
    ).json()["id"]

    assert (await bob.get("/api/watchlists")).json() == []
    assert (await bob.get(f"/api/watchlists/{list_id}")).status_code == 404
    assert (
        await bob.put(f"/api/watchlists/{list_id}", json={"name": "归我"})
    ).status_code == 404
    assert (
        await bob.post(f"/api/watchlists/{list_id}/videos", json={"video_id": 1})
    ).status_code == 404
    assert (await bob.delete(f"/api/watchlists/{list_id}/videos/1")).status_code == 404
    assert (await bob.delete(f"/api/watchlists/{list_id}")).status_code == 404

    kept = await client.get(f"/api/watchlists/{list_id}")
    assert kept.status_code == 200
    assert kept.json()["name"] == "今晚看这些"


@pytest.mark.asyncio
async def test_two_accounts_may_name_their_list_the_same(client, make_signed_in_client):
    """Ownership moved the name collision inside one account, where it stays 409."""
    bob = await make_signed_in_client("bob")

    assert (await client.post("/api/watchlists", json={"name": "今晚看这些"})).status_code == 201
    assert (await bob.post("/api/watchlists", json={"name": "今晚看这些"})).status_code == 201
    assert (await client.post("/api/watchlists", json={"name": "今晚看这些"})).status_code == 409


@pytest.mark.asyncio
async def test_deleting_another_account_history_record_answers_404(
    client, db_session, make_signed_in_client
):
    await _video(db_session, 1)
    bob = await make_signed_in_client("bob")
    await client.post("/api/videos/1/progress", json={"progress": 30})
    record_id = (await client.get("/api/history")).json()["items"][0]["id"]

    assert (await bob.get("/api/history")).json()["total"] == 0
    assert (await bob.delete(f"/api/history/{record_id}")).status_code == 404
    assert (await client.get("/api/history")).json()["total"] == 1

    assert (await client.delete(f"/api/history/{record_id}")).status_code == 204


@pytest.mark.asyncio
async def test_each_account_is_told_where_it_stopped(client, db_session, make_signed_in_client):
    """One shared title, two positions, and neither list carries the other's."""
    await _video(db_session, 1)
    bob = await make_signed_in_client("bob")
    await client.post("/api/videos/1/play", json={})
    await client.post("/api/videos/1/progress", json={"progress": 90})
    await bob.post("/api/videos/1/progress", json={"progress": 10})

    assert (await client.get("/api/videos/1")).json()["progress"] == 90
    assert (await bob.get("/api/videos/1")).json()["progress"] == 10
    assert [(v["id"], v["progress"]) for v in (await client.get("/api/history/continue")).json()] == [
        (1, 90)
    ]
    assert [(v["id"], v["progress"]) for v in (await bob.get("/api/history/continue")).json()] == [
        (1, 10)
    ]


@pytest.mark.asyncio
async def test_watch_totals_only_add_up_the_caller_seconds(
    client, db_session, make_signed_in_client
):
    await _video(db_session, 1)
    bob = await make_signed_in_client("bob")
    await client.post("/api/videos/1/progress", json={"progress": 60})
    await bob.post("/api/videos/1/progress", json={"progress": 10})

    assert (await client.get("/api/history/stats")).json()["window_seconds"] == 60
    assert (await bob.get("/api/history/stats")).json()["window_seconds"] == 10


@pytest.mark.asyncio
async def test_favorites_are_two_lists_over_one_shared_title(
    client, db_session, make_signed_in_client
):
    await _video(db_session, 1)
    bob = await make_signed_in_client("bob")

    assert (await client.post("/api/favorites/1")).status_code == 201
    assert (await bob.get("/api/favorites")).json()["total"] == 0
    assert (await bob.get("/api/favorites/1/status")).json() == {"is_favorite": False}

    assert (await bob.post("/api/favorites/1")).status_code == 201
    assert (await bob.delete("/api/favorites/1")).status_code == 204
    assert (await client.get("/api/favorites")).json()["total"] == 1


@pytest.mark.asyncio
async def test_the_finished_filter_answers_for_the_caller(
    client, db_session, make_signed_in_client
):
    """The search operators are the library's own view of who watched what."""
    await _video(db_session, 1)
    bob = await make_signed_in_client("bob")
    await client.post("/api/videos/1/progress", json={"progress": 120})

    assert [v["title"] for v in (await client.get("/api/videos", params={"search": "已看完"})).json()["items"]] == [
        "暗涌"
    ]
    assert (await bob.get("/api/videos", params={"search": "已看完"})).json()["total"] == 0
    assert (await bob.get("/api/videos", params={"search": "没看过"})).json()["total"] == 1


@pytest.mark.asyncio
async def test_reading_a_notification_leaves_it_unread_for_the_others(
    client, db_session, make_signed_in_client
):
    bob = await make_signed_in_client("bob")
    note = await NotificationService(db_session).create(
        "scan_complete", "扫描完成", "新增 3 部"
    )

    assert (await client.post(f"/api/notifications/{note.id}/read")).status_code == 204

    assert (await client.get("/api/notifications/unread")).json() == {"count": 0}
    assert (await bob.get("/api/notifications/unread")).json() == {"count": 1}
    assert (await bob.get("/api/notifications")).json()["items"][0]["read"] is False


@pytest.mark.asyncio
async def test_clearing_the_new_badge_is_a_per_account_reply(
    client, db_session, make_signed_in_client
):
    """The arrival is shared news; having seen it is each person's own."""
    await _video(db_session, 1)
    db_session.add(NewVideo(video_id=1, source_id=1))
    await db_session.commit()
    bob = await make_signed_in_client("bob")

    assert (await client.post("/api/videos/new/1/viewed")).status_code == 200

    assert (await client.get("/api/videos/new")).json() == []
    assert [v["id"] for v in (await bob.get("/api/videos/new")).json()] == [1]
    assert (await bob.get("/api/videos")).json()["items"][0]["is_new"] is True
