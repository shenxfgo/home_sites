"""The favorite route's own refusal, walked through HTTP once.

``FavoriteService.add_favorite`` answers a second copy with 「这部视频已在收藏里」
and the route turns that sentence into a 400. Before #198 nothing had ever posted
the same title twice, so that sentence had no witness at all — the collection was
exercised per account, never per title twice.

电池（#198，六格各自只红一条，每格跑完立刻按 md5 还原那五个源文件）：M1 把这道
重复闸门改成永远不成立（`if existing.scalar_one_or_none():` → `if False:`）红
1 条——本文件那条 400 用例。实测的失败形状值得记一句：第二次 POST 不是变成 201，
而是 **500**——`IntegrityError: UNIQUE constraint failed: favorites.user_id,
favorites.video_id` 不在那句 `except ValueError` 的接得住的范围里。所以这条用例钉的
是「唯一约束之前先说清楚」，抽掉闸门就是把它换成一条崩给调用方的 500。
"""
import pytest
from sqlalchemy import func, select

from src.models.favorite import Favorite
from src.models.video import Video
from tests.support import ensure_source


async def _video(db_session, video_id=1, title="暗涌"):
    await ensure_source(db_session)
    video = Video(
        id=video_id,
        source_id=1,
        filepath=f"/test/{title}.mp4",
        title=title,
        duration=600,
    )
    db_session.add(video)
    await db_session.commit()
    return video


@pytest.mark.asyncio
async def test_favoriting_the_same_title_twice_answers_400(client, db_session):
    """第二次收藏不是「静悄悄地什么也没做」，而是把原因说出来。"""
    await _video(db_session)

    first = await client.post("/api/favorites/1")
    second = await client.post("/api/favorites/1")

    assert first.status_code == 201
    assert second.status_code == 400
    assert second.json()["detail"] == "这部视频已在收藏里"

    # 拒绝归拒绝，库里那条不能变成两行——唯一约束在这里是最后一道，不是第一道。
    rows = await db_session.scalar(
        select(func.count()).select_from(Favorite).where(Favorite.video_id == 1)
    )
    assert rows == 1
    assert (await client.get("/api/favorites")).json()["total"] == 1


@pytest.mark.asyncio
async def test_a_missing_title_is_refused_by_name(client, db_session):
    """外键那一关 SQLite 出厂不查，所以这句「视频 #id 不存在」是两种库同一个答案。"""
    await ensure_source(db_session)

    response = await client.post("/api/favorites/4242")

    assert response.status_code == 400
    assert response.json()["detail"] == "视频 #4242 不存在"
