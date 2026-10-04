"""标签接口：八个端点都在界面上被用着，这里把它们逐个走一遍。

`frontend/src/views/Tags.vue` 建/改/删标签，`VideoDetail.vue` 给影片贴和摘，
`Home.vue` 读列表算片库分布——之前这些路径只有模型用例和角色扫面，接口本身没测过。
探针是在这条上撞出来的：重名建标签直接把 `IntegrityError` 顶到 ASGI 层（真服务器上
就是 500），而 `tags.name` 上的唯一约束是明写的，界面上也确实点得到。
"""

import pytest
from sqlalchemy import select

from src.models.tag import video_tags
from tests.support import ensure_video

DEFAULT_COLOR = "#409eff"


async def _create(client, name: str, **body) -> dict:
    response = await client.post("/api/tags", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


async def _list(client) -> list[dict]:
    response = await client.get("/api/tags")
    assert response.status_code == 200, response.text
    return response.json()


async def _tag_a_video(client, video_id: int, tag_ids: list[int]):
    return await client.post(f"/api/tags/video/{video_id}", json={"tag_ids": tag_ids})


# ---------- 建 ----------


async def test_creating_a_tag_returns_it_with_a_zero_count(client):
    tag = await _create(client, "科幻", color="#ff6b6b")

    assert tag["name"] == "科幻"
    assert tag["color"] == "#ff6b6b"
    assert tag["video_count"] == 0


async def test_colour_defaults_when_the_body_omits_it(client):
    tag = await _create(client, "纪录片")

    assert tag["color"] == DEFAULT_COLOR


async def test_a_bad_colour_is_rejected_before_it_reaches_the_database(client):
    response = await client.post("/api/tags", json={"name": "彩虹", "color": "red"})

    assert response.status_code == 422


async def test_a_second_tag_with_the_same_name_conflicts_instead_of_500(client):
    """唯一约束在 `tags.name` 上，撞它是使用者的常态（手滑重名），不是异常。"""
    await _create(client, "科幻")

    response = await client.post("/api/tags", json={"name": "科幻"})

    assert response.status_code == 409, response.text
    assert "科幻" in response.json()["detail"]
    # 失败的那一次不能留下半个标签，也不能把名字相同的那条改坏。
    assert [item["name"] for item in await _list(client)] == ["科幻"]


# ---------- 列表与单取 ----------


async def test_the_list_is_ordered_by_name_and_counts_attached_videos(
    client, db_session
):
    """`order_by(Tag.name)` 排的是 UTF-8 字节序，不是拼音。

    两种方言在这上一致（SQLite 的 BINARY、PG 建库时钉死的 C collation 都是字节序），
    所以这条在测试库和真库上给同一个答案：剧(U+5267) 排在 动(U+52A8) 之前。
    """
    await ensure_video(db_session)
    used = await _create(client, "剧情")
    await _create(client, "动画")
    await _tag_a_video(client, 1, [used["id"]])

    listed = await _list(client)

    assert [item["name"] for item in listed] == ["剧情", "动画"]
    assert [item["video_count"] for item in listed] == [1, 0]


async def test_fetching_one_tag(client):
    created = await _create(client, "悬疑")

    response = await client.get(f"/api/tags/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "悬疑"


async def test_fetching_a_tag_that_is_not_there(client):
    response = await client.get("/api/tags/9999")

    assert response.status_code == 404


# ---------- 改 ----------


async def test_renaming_and_recolouring_a_tag(client):
    created = await _create(client, "旧名", color="#111111")

    response = await client.put(
        f"/api/tags/{created['id']}", json={"name": "新名", "color": "#222222"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "新名"
    assert response.json()["color"] == "#222222"


async def test_renaming_onto_an_existing_name_conflicts(client):
    await _create(client, "科幻")
    other = await _create(client, "奇幻")

    response = await client.put(f"/api/tags/{other['id']}", json={"name": "科幻"})

    assert response.status_code == 409, response.text
    assert (await client.get(f"/api/tags/{other['id']}")).json()["name"] == "奇幻"
    assert len(await _list(client)) == 2


async def test_an_empty_patch_changes_nothing_but_is_refused(client):
    created = await _create(client, "科幻")

    response = await client.put(f"/api/tags/{created['id']}", json={})

    assert response.status_code == 400


async def test_updating_a_tag_that_is_not_there(client):
    response = await client.put("/api/tags/9999", json={"name": "随手改"})

    assert response.status_code == 404


# ---------- 删 ----------


async def test_deleting_a_tag_makes_it_gone(client):
    created = await _create(client, "临时")

    response = await client.delete(f"/api/tags/{created['id']}")

    assert response.status_code == 204
    assert (await client.get(f"/api/tags/{created['id']}")).status_code == 404


async def test_deleting_a_used_tag_detaches_it_but_keeps_the_video(client, db_session):
    """删标签带走的是关联，不是影片——片是用户的，标签是元数据。

    读之前先 `expire_all()`：真服务里每个请求一个新会话，而这里的接口和用例共用
    `db_session`，那条影片的 `tags` 集合在贴标签时已经加载过，不失效就会读到
    身份映射里的旧集合（探针实测：库里 `video_tags` 已经空了，响应里还挂着标签）。
    """
    await ensure_video(db_session)
    tag = await _create(client, "科幻")
    await _tag_a_video(client, 1, [tag["id"]])

    assert (await client.delete(f"/api/tags/{tag['id']}")).status_code == 204

    db_session.expire_all()
    assert (await client.get("/api/videos/1")).json()["tags"] == []
    assert (await client.get("/api/videos/1")).json()["title"]
    assert (await db_session.execute(select(video_tags))).all() == []


async def test_deleting_a_tag_that_is_not_there(client):
    assert (await client.delete("/api/tags/9999")).status_code == 404


# ---------- 贴标签与摘 ----------


async def test_tagging_a_video_shows_up_on_both_sides(client, db_session):
    await ensure_video(db_session)
    tag = await _create(client, "科幻")

    assert (await _tag_a_video(client, 1, [tag["id"]])).status_code == 204

    assert [item["id"] for item in await _list(client)] == [tag["id"]]
    videos = await client.get(f"/api/tags/{tag['id']}/videos")
    assert [item["id"] for item in videos.json()] == [1]
    assert (await client.get("/api/videos/1")).json()["tags"][0]["name"] == "科幻"


async def test_videos_of_a_tag_come_back_whether_or_not_the_session_is_cold(
    client, db_session
):
    """同一部影片第二次经 `Tag.videos` 走出来时翻过一次车，这里把那个状态钉住。

    真服务器上它偶发回 500：`MissingGreenlet`——`video.tags` 那一次没被加载，而
    pydantic 的序列化是同步的，碰它就是"在 greenlet 之外做 IO"。用例用
    `expire_all()` 造出"会话里已经有一枚过期实例"的形状（生产的会话工厂是
    `expire_on_commit=False` 且每请求一个新的，所以这不是给生产补的洞），而修法是
    把要加载的关系写明到查询里：状态码不再取决于会话热不热。
    """
    await ensure_video(db_session)
    tag = await _create(client, "科幻")
    assert (await _tag_a_video(client, 1, [tag["id"]])).status_code == 204

    db_session.expire_all()

    response = await client.get(f"/api/tags/{tag['id']}/videos")
    assert response.status_code == 200, response.text
    assert [item["tags"][0]["name"] for item in response.json()] == ["科幻"]


async def test_tagging_twice_is_not_two_rows(client, db_session):
    await ensure_video(db_session)
    tag = await _create(client, "科幻")

    await _tag_a_video(client, 1, [tag["id"]])
    await _tag_a_video(client, 1, [tag["id"]])

    assert (await _list(client))[0]["video_count"] == 1


async def test_several_tags_land_in_one_request(client, db_session):
    await ensure_video(db_session)
    first = await _create(client, "科幻")
    second = await _create(client, "悬疑")

    assert (await _tag_a_video(client, 1, [first["id"], second["id"]])).status_code == 204

    assert {item["name"] for item in (await client.get("/api/videos/1")).json()["tags"]} == {
        "科幻",
        "悬疑",
    }


async def test_tagging_a_video_that_is_not_there(client):
    tag = await _create(client, "科幻")

    assert (await _tag_a_video(client, 9999, [tag["id"]])).status_code == 404


async def test_an_unknown_tag_id_in_the_list_is_skipped(client, db_session):
    """界面递来的 id 都来自标签列表，混进一个失效 id 时不该把整次请求判死。

    这条记录的是当前取舍：存在的照贴，不存在的跳过，整体 204。
    """
    await ensure_video(db_session)
    tag = await _create(client, "科幻")

    assert (await _tag_a_video(client, 1, [tag["id"], 9999])).status_code == 204

    assert [item["id"] for item in (await client.get("/api/videos/1")).json()["tags"]] == [
        tag["id"]
    ]


async def test_removing_a_tag_from_a_video(client, db_session):
    await ensure_video(db_session)
    tag = await _create(client, "科幻")
    await _tag_a_video(client, 1, [tag["id"]])

    response = await client.delete(f"/api/tags/video/1/{tag['id']}")

    assert response.status_code == 204
    assert (await client.get("/api/videos/1")).json()["tags"] == []
    assert (await _list(client))[0]["video_count"] == 0


async def test_removing_a_tag_that_was_never_there_is_a_no_op(client, db_session):
    await ensure_video(db_session)
    tag = await _create(client, "科幻")

    assert (await client.delete(f"/api/tags/video/1/{tag['id']}")).status_code == 204

    assert (await client.get("/api/videos/1")).json()["tags"] == []


async def test_removing_from_a_video_that_is_not_there(client):
    tag = await _create(client, "科幻")

    assert (await client.delete(f"/api/tags/video/9999/{tag['id']}")).status_code == 404


# ---------- 按标签查影片 ----------


async def test_videos_of_a_tag_that_is_not_there(client):
    assert (await client.get("/api/tags/9999/videos")).status_code == 404


async def test_videos_of_a_tag_no_one_has_used(client):
    tag = await _create(client, "冷门")

    response = await client.get(f"/api/tags/{tag['id']}/videos")

    assert response.status_code == 200
    assert response.json() == []


# ---------- 服务层那条排序 ----------


@pytest.mark.parametrize("order", [["悬疑", "动画"], ["动画", "悬疑"]])
async def test_the_list_is_sorted_by_name_however_they_were_created(
    client, order
):
    for name in order:
        await _create(client, name)

    assert [item["name"] for item in await _list(client)] == ["动画", "悬疑"]
