"""Tests for the watchlist CRUD endpoints and the queue routes."""
import pytest

from src.models.video import Video
from tests.support import ensure_source


async def _create_video(db_session, video_id, title, *, progress=None, user_id=None):
    """Seed one title, optionally with a position one person stopped at."""
    from src.models.history import PlayHistory

    await ensure_source(db_session)
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

    missing_list = await client.post(
        f"/api/watchlists/{list_id}/videos", json={"video_id": 999}
    )
    assert missing_list.status_code == 404
    missing_video = await client.post("/api/watchlists/999/videos", json={"video_id": 1})
    assert missing_video.status_code == 404
    assert (await client.put("/api/watchlists/999", json={"name": "无关"})).status_code == 404
    assert (await client.delete("/api/watchlists/999")).status_code == 404


@pytest.mark.asyncio
async def test_a_name_is_required(client):
    assert (await client.post("/api/watchlists", json={"name": ""})).status_code == 422


@pytest.mark.asyncio
async def test_renaming_onto_a_name_the_account_already_uses_answers_409(client):
    """片单名在同一账号里是唯一索引：撞上了要说 409，不能被下面那条 404 接走。

    电池 M5（#198）：把路由里那两个 `except` 的先后次序换过来（`DuplicateWatchlistNameError`
    是 `ValueError` 的子类，排在父类后面就永远轮不到），红的正是这一条——它读到 404。
    这条红只有把状态码钉在 409 上才看得见，断言「报个错」是绿的。
    """
    mine = await _create_list(client, "今晚看这些")
    theirs = await _create_list(client, "以后再说")

    clash = await client.put(f"/api/watchlists/{mine}", json={"name": "以后再说"})

    assert clash.status_code == 409
    assert clash.json()["detail"] == "片单「以后再说」已存在"

    listing = await client.get("/api/watchlists")
    assert [entry["id"] for entry in listing.json()] == [mine, theirs]
    assert [entry["name"] for entry in listing.json()] == ["今晚看这些", "以后再说"]


@pytest.mark.asyncio
async def test_renaming_a_list_to_the_name_it_already_has_is_not_a_clash(client):
    """同一份 PUT 重发一次应当还是 200：自己撞自己不算冲突。

    电池 M4（#198）：把服务层那句 `if name != watchlist.name:` 改成永远成立，红的就是
    这一条（200 变 409）。上一格测的是「撞了要报 409」，这一格测的是「没撞别报」——
    同一条判断的两张脸，缺一张就少一格红。
    """
    mine = await _create_list(client, "今晚看这些")

    same = await client.put(f"/api/watchlists/{mine}", json={"name": "今晚看这些"})

    assert same.status_code == 200
    assert same.json()["name"] == "今晚看这些"


@pytest.mark.asyncio
async def test_description_and_name_are_written_independently(client):
    """PUT 带说明就写说明；只带名字时说明不许被抹成空。

    电池 M3（#198）：`if description is not None:` 改成永远成立，红的就是这一条——只带
    名字的那次 PUT 会把说明清成 null。另加一格 M7：名字那道闸门（`if name is not None:`）
    同样改成永远成立时，只带说明的那次 PUT 会把名字写成 null，撞 NOT NULL 直接 500。
    """
    mine = await _create_list(client, "今晚看这些")

    both = await client.put(
        f"/api/watchlists/{mine}", json={"name": "明晚再看", "description": "周末看完"}
    )
    assert both.status_code == 200
    assert both.json()["description"] == "周末看完"

    only_name = await client.put(f"/api/watchlists/{mine}", json={"name": "后天看"})
    assert only_name.json()["name"] == "后天看"
    assert only_name.json()["description"] == "周末看完"

    only_description = await client.put(
        f"/api/watchlists/{mine}", json={"description": "下周再看"}
    )
    assert only_description.json()["name"] == "后天看"
    assert only_description.json()["description"] == "下周再看"

