# tests/test_api/test_video_reads_with_a_cold_session.py
"""凡是回 `VideoResponse` 的读接口，都不能因为会话里那枚实例过期了就从 200 变 500。

`Video.tags` 在关系上写了 `lazy="selectin"`，所以直接 `select(Video)` 查出来的影片
自带标签。可当影片是**经另一条关系**load 出来的（`PlayHistory.video`、
`Favorite.video`、`WatchlistItem.video`），或者会话里已经躺着一枚过期实例时，标签
集合不会被带上，而 pydantic 的序列化是同步的——碰它就是一次 greenlet 之外的 IO，
`MissingGreenlet` 一路顶成 500。这几条用例统一用 `expire_all()` 造出那个状态：不是
给生产补洞（生产每请求一个新会话，且 `expire_on_commit=False`），是不让"回什么码"
取决于会话热不热。
"""

from tests.support import ensure_video


async def _tagged_video(client, db_session) -> dict:
    """造一部贴了标签的影片，返回那个标签。"""
    await ensure_video(db_session)
    tag = (await client.post("/api/tags", json={"name": "科幻", "color": "#ff6b6b"})).json()
    response = await client.post("/api/tags/video/1", json={"tag_ids": [tag["id"]]})
    assert response.status_code == 204, response.text
    return tag


def _items(payload) -> list[dict]:
    """两种响应形状（裸列表和 `{"items": [...]}`）都取到影片数组。"""
    return payload if isinstance(payload, list) else payload["items"]


async def _assert_tags_came_back(client, db_session, path: str, tag: dict) -> None:
    db_session.expire_all()

    response = await client.get(path)

    assert response.status_code == 200, response.text
    videos = [item for item in _items(response.json()) if item["id"] == 1]
    assert [[t["name"] for t in item["tags"]] for item in videos] == [[tag["name"]]]


async def test_the_video_list_reads_a_cold_instance_back(client, db_session):
    tag = await _tagged_video(client, db_session)
    await _assert_tags_came_back(client, db_session, "/api/videos", tag)


async def test_a_single_video_reads_a_cold_instance_back(client, db_session):
    tag = await _tagged_video(client, db_session)

    db_session.expire_all()

    response = await client.get("/api/videos/1")
    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()["tags"]] == [tag["name"]]


async def test_the_resume_rail_reads_a_cold_instance_back(client, db_session):
    """`/api/history/continue` 是经 `PlayHistory.video` 走到影片的，不是直接查影片。"""
    tag = await _tagged_video(client, db_session)
    assert (await client.post("/api/videos/1/play")).status_code == 200
    assert (
        await client.post("/api/videos/1/progress", json={"progress": 30})
    ).status_code == 200

    await _assert_tags_came_back(client, db_session, "/api/history/continue", tag)


async def test_the_favorites_list_reads_a_cold_instance_back(client, db_session):
    tag = await _tagged_video(client, db_session)
    assert (await client.post("/api/favorites/1")).status_code == 201

    await _assert_tags_came_back(client, db_session, "/api/favorites", tag)


async def test_a_watchlist_reads_a_cold_instance_back(client, db_session):
    tag = await _tagged_video(client, db_session)
    created = await client.post("/api/watchlists", json={"name": "周末看"})
    assert created.status_code == 201, created.text
    watchlist_id = created.json()["id"]
    added = await client.post(
        f"/api/watchlists/{watchlist_id}/videos", json={"video_id": 1}
    )
    assert added.status_code == 200, added.text

    await _assert_tags_came_back(client, db_session, f"/api/watchlists/{watchlist_id}", tag)
