"""`PUT /api/videos/{id}` 上带着 `tag_ids` 的那一路，此前从 pytest 进来一次也没被走过（#173）。

`src/api/videos.py` 在修正后的读数里是 94%，缺的八行（`236-238`、`242-248`）不是边角，是
**影片↔标签关系的第二条写路径**：接口层从前只被 `POST /api/tags/video/{id}` 那一头敲过，而 PUT
这一头一旦拿到 `tag_ids` 走的是 `video.tags = tags`——**整串换掉**，前一句是**往上加**。两条
路径写同一张 `video_tags`，语义相反，中间那一条零钉子。

为什么界面上看不到它：`VideoDetail.vue:234` 组装的 `VideoUpdate` 只有 title/description/rating 三个
键；前端类型上那个 `tag_ids?` 是一个从来没被发出去的字段（和 #151 那四个装饰配置项同一族），
2026-10-10 第二块选项板⑫定成**删掉它**（#191，`frontend/src/types/video.ts`）。所以这一路今天的
调用方只剩"任何别的客户端"——真后端 e2e 那两条裸 `JSON.stringify` 请求就是故意在扮演这个别处，
而别的客户端一旦带上它，能把一个人挂好的标签整串清空。
下面几条钉的都是**实测出来的现有行为**，除了标签 id 不存在那一路：它原本是"未知 id 把整串带走、
接口还回 200"的洞（本单发现、记在待用户定夺），2026-10-09 第二块选项板⑥甲定成**拒绝 404**，
现在由 `test_an_unknown_tag_id_is_refused_and_leaves_the_existing_set_alone` 那三条钉新形状。
"""

import pytest
from sqlalchemy import select

from src.models.tag import Tag, video_tags
from tests.support import ensure_video


async def _tag(client, name: str) -> dict:
    response = await client.post("/api/tags", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


async def _link_ids(db_session, video_id: int) -> list[int]:
    rows = await db_session.execute(
        select(video_tags.c.tag_id).where(video_tags.c.video_id == video_id)
    )
    return sorted(rows.scalars().all())


async def _get(client, video_id: int) -> dict:
    response = await client.get(f"/api/videos/{video_id}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_a_tag_only_put_replaces_what_the_append_endpoint_had_built(client, db_session):
    """同一张关系表上的两条写路径，语义是相反的——这一条就是那条分界线。

    先用 `POST /api/tags/video/{id}`（append）挂上 A，再用 PUT 只交 B。今天的结果是**只剩 B**，
    链接表里 A 那一行随之消失。如果哪天有人把 `video.tags = tags` 改成往上追加，红的是这一条。
    """
    video = await ensure_video(db_session)
    first = await _tag(client, "动作")
    second = await _tag(client, "科幻")

    appended = await client.post(
        f"/api/tags/video/{video.id}", json={"tag_ids": [first["id"]]}
    )
    assert appended.status_code == 204, appended.text

    response = await client.put(f"/api/videos/{video.id}", json={"tag_ids": [second["id"]]})

    assert response.status_code == 200, response.text
    assert [t["name"] for t in response.json()["tags"]] == ["科幻"], response.json()["tags"]
    assert [t["id"] for t in (await _get(client, video.id))["tags"]] == [second["id"]]
    assert await _link_ids(db_session, video.id) == [second["id"]]


@pytest.mark.asyncio
async def test_an_empty_tag_list_clears_the_links_and_leaves_the_tag_rows_alone(
    client, db_session
):
    """`tag_ids: []` 是一次真正的写，不是"什么都不做"。

    空串和 `null` 在这一路上是两种东西（下面那一条钉另一半），而且拆标签只拆链接：标签本身还得在
    `tags` 表里，别的影片上的同名关系不能跟着掉。摘掉 `video.tags = tags` 前面那句查重、或把
    `if tag_ids is not None` 写成 `if tag_ids`，红的是这一条。
    """
    video = await ensure_video(db_session)
    keep = await _tag(client, "纪录片")
    await client.put(f"/api/videos/{video.id}", json={"tag_ids": [keep["id"]]})

    response = await client.put(f"/api/videos/{video.id}", json={"tag_ids": []})

    assert response.status_code == 200, response.text
    assert response.json()["tags"] == []
    assert await _link_ids(db_session, video.id) == []
    # 标签行还在，只是不再挂在这部片子上。
    rows = await db_session.execute(select(Tag.id).where(Tag.id == keep["id"]))
    assert rows.scalar_one() == keep["id"]


@pytest.mark.asyncio
async def test_an_unknown_tag_id_is_refused_and_leaves_the_existing_set_alone(
    client, db_session
):
    """请求里有一个不存在的标签 id：整串请求被拒（404），原有的标签一根汗毛不动。

    2026-10-09 第二块选项板⑥甲。从前这一路是 `select(Tag).where(Tag.id.in_(tag_ids))` 只回查得到的、
    回不到的不当错，而后面的赋值是**整串替换**——一个已被删掉的 id 就能把这部片子原有的标签一起带走，
    接口照样回 200，也没有一句说得出哪个 id 不存在。现在它既不动已有的关系，也说得出是哪一号。
    """
    video = await ensure_video(db_session)
    existing = await _tag(client, "冷门")
    await client.put(f"/api/videos/{video.id}", json={"tag_ids": [existing["id"]]})

    response = await client.put(f"/api/videos/{video.id}", json={"tag_ids": [999999]})

    assert response.status_code == 404, response.text
    assert "999999" in response.json()["detail"], response.json()
    assert await _link_ids(db_session, video.id) == [existing["id"]]
    assert [t["id"] for t in (await _get(client, video.id))["tags"]] == [existing["id"]]


@pytest.mark.asyncio
async def test_a_partly_known_tag_list_is_refused_before_anything_is_written(
    client, db_session
):
    """一半认识一半不认识也不行：不能先把认识的那半挂上去再说这次失败。

    这一条钉的是"拒绝"的两半——状态码是 404，而且库里既不是原来的样子被换成了 [认识的那个]，
    也不是被清空。`[]` 仍然是一次真写（上面第二条用例钉着），别把这两种混成一种。
    """
    video = await ensure_video(db_session)
    before = await _tag(client, "先挂着")
    known = await _tag(client, "认得")
    await client.put(f"/api/videos/{video.id}", json={"tag_ids": [before["id"]]})

    response = await client.put(
        f"/api/videos/{video.id}", json={"tag_ids": [known["id"], 999999]}
    )

    assert response.status_code == 404, response.text
    assert await _link_ids(db_session, video.id) == [before["id"]]


@pytest.mark.asyncio
async def test_a_bad_tag_id_refuses_the_whole_request_including_the_field_half(
    client, db_session
):
    """`{title, tag_ids}` 一起发、而 tag_ids 里有坏号：标题也不许写进去。

    标签的核对被搬到了字段更新**之前**，为的就是别留下"接口回 404、库里标题已经改了"这种两边各自
    自洽的形状（#176 那半截行、#177 那条假进度同一族）。两个半都合法时照旧都写，由
    `test_a_request_that_carries_both_halves_writes_both` 钉着。
    """
    video = await ensure_video(db_session)
    original_title = (await _get(client, video.id))["title"]

    response = await client.put(
        f"/api/videos/{video.id}", json={"title": "不该留下", "tag_ids": [999999]}
    )

    assert response.status_code == 404, response.text
    assert (await _get(client, video.id))["title"] == original_title


@pytest.mark.asyncio
async def test_a_video_that_is_not_there_gives_404_from_both_halves_with_two_wordings(
    client, db_session
):
    """`236-238` 那三行只服务一种请求：只带标签、片子又不存在。

    带普通字段的同一请求走的是 `service.update_video` 抛 `ValueError` → 另一句 404。今天两句措辞不
    一样（一句点名是哪一部，一句不点），而 #153 正等着把这类英文 detail 换成中文，所以这里**不钉
    措辞本身**，只钉"两边都是 404、且这两句不一样"——把它改成同一句之前，得先知道有人看着这个区别。
    """
    tag = await _tag(client, "无人认领")

    tag_only = await client.put("/api/videos/4242", json={"tag_ids": [tag["id"]]})
    with_field = await client.put(
        "/api/videos/4242", json={"title": "改名", "tag_ids": [tag["id"]]}
    )

    assert tag_only.status_code == 404, tag_only.text
    assert with_field.status_code == 404, with_field.text
    tag_detail = tag_only.json()["detail"]
    field_detail = with_field.json()["detail"]
    assert tag_detail and field_detail
    assert tag_detail != field_detail, "两句 404 现在是可以分开的，别悄悄合并"
    assert "4242" in field_detail, field_detail


@pytest.mark.asyncio
async def test_the_replacement_is_committed_before_the_response_finishes(client, db_session):
    """`await session.commit()` 那一句不是收尾装饰：不提交的话响应体照样好看。

    路由用的是请求那份会话，`video.tags = tags` 之后如果没人提交，接口这一头仍然能序列化出新的标签
    列表（对象还在 identity map 里），下一次读才发现没写进去。所以这一条先把会话里的对象全部丢弃
    （`expunge_all`）再重新请求一次。
    """
    video = await ensure_video(db_session)
    tag = await _tag(client, "已提交")

    written = await client.put(f"/api/videos/{video.id}", json={"tag_ids": [tag["id"]]})
    assert written.status_code == 200, written.text

    db_session.expunge_all()
    reread = await _get(client, video.id)

    assert [t["id"] for t in reread["tags"]] == [tag["id"]], reread["tags"]
    assert await _link_ids(db_session, video.id) == [tag["id"]]


@pytest.mark.asyncio
async def test_a_request_that_carries_both_halves_writes_both(client, db_session):
    """`{title, tag_ids}` 同请求：两段写都要留下，而且都在同一份响应里可见。

    这一段今天真的会被人用（`VideoDetail.vue` 只发前一半，另一路客户端两个一起发），
    它是 `230-248` 整条链唯一一次同时走完两半的用例：`service.update_video` 先提交字段，
    路由随后替换关系再提交一次。
    """
    video = await ensure_video(db_session)
    one = await _tag(client, "剧情")
    two = await _tag(client, "喜剧")

    response = await client.put(
        f"/api/videos/{video.id}",
        json={"title": "换了名", "tag_ids": [one["id"], two["id"]]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "换了名", body
    assert sorted(t["name"] for t in body["tags"]) == ["剧情", "喜剧"], body["tags"]
    fresh = await _get(client, video.id)
    assert fresh["title"] == "换了名" and len(fresh["tags"]) == 2, fresh


@pytest.mark.asyncio
async def test_a_tag_only_put_leaves_updated_at_where_it_was_while_a_title_edit_moves_it(
    client, db_session
):
    """只改标签不会动 `videos.updated_at`，改标题会——两种写走的是两种语句。

    关系的替换只写 `video_tags`，`videos` 那一行没有被 UPDATE，所以 ORM 那句 `onupdate` 不触发。
    后果不大但真实：详情页 `VideoDetail.vue:454` 显示的"更新于"在贴完标签后还是旧时间。钉它是因为
    "顺手把关系写也去 bump 一下时间戳"会改变库里那一行的形状，属于要用户点头的那类改动。
    """
    video = await ensure_video(db_session)
    tag = await _tag(client, "时间戳")
    before = await _get(client, video.id)

    tag_only = await client.put(f"/api/videos/{video.id}", json={"tag_ids": [tag["id"]]})
    assert tag_only.json()["updated_at"] == before["updated_at"], (
        tag_only.json()["updated_at"],
        before["updated_at"],
    )

    titled = await client.put(f"/api/videos/{video.id}", json={"title": "动了标题"})
    assert titled.json()["updated_at"] != before["updated_at"], titled.json()["updated_at"]


@pytest.mark.asyncio
async def test_an_explicit_null_tag_list_is_refused_rather_than_read_as_no_change(
    client, db_session
):
    """`{"tag_ids": null}` 是 400，不是"什么也不改"——它和 `[]` 是两回事。

    闸门那句是 `if not update_data and tag_ids is None`：`model_dump(exclude_unset=True)`
    让"没带这个键"和"带了 null"都落到 `tag_ids is None`，于是两者都 400；
    而 `[]` 是带了、且不是 None，走成真写。
    一个客户端如果把 `undefined` 序列化成 `null`，它想表达的"只改别的字段"会被拒在门外，这一条钉住
    今天确实如此。
    """
    video = await ensure_video(db_session)

    response = await client.put(f"/api/videos/{video.id}", json={"tag_ids": None})

    assert response.status_code == 400, response.text
    assert response.json()["detail"], "400 却没人说出原因"


@pytest.mark.asyncio
async def test_the_same_tag_id_listed_twice_leaves_exactly_one_link(client, db_session):
    """重复 id 不会写出两条链接行——`video_tags` 上那个复合主键本来就容不下。

    这一条的价值在"接口不回 500"：如果哪天有人把这句换成逐条 insert，撞主键就是 IntegrityError 顶到
    ASGI 层（#98 那次同类的现场）。今天走关系赋值，重复被 ORM 自己吃掉。
    """
    video = await ensure_video(db_session)
    tag = await _tag(client, "重复")

    response = await client.put(
        f"/api/videos/{video.id}", json={"tag_ids": [tag["id"], tag["id"]]}
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["tags"]) == 1, response.json()["tags"]
    assert await _link_ids(db_session, video.id) == [tag["id"]]
