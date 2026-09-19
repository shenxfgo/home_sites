"""Tests for the multi-dimension video search built by VideoService."""
import pytest

from src.models.history import PlayHistory
from src.models.source import VideoSource
from src.models.tag import Tag
from src.models.video import Video
from src.services.video_service import VideoService


async def _source(session, name, path="/media/first"):
    source = VideoSource(name=name, path=path, type="local")
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def _video(session, source, title, description=None, rating=0, duration=None, tags=(), filepath=None):
    video = Video(
        source_id=source.id,
        filepath=filepath or f"{source.path}/{title}.mp4",
        title=title,
        description=description,
        rating=rating,
        duration=duration,
    )
    if tags:
        video.tags = list(tags)
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return video


async def _tag(session, name):
    tag = Tag(name=name)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


async def _history(session, video, progress, completed):
    session.add(
        PlayHistory(video_id=video.id, progress=progress, completed=completed)
    )
    await session.commit()


async def _titles(service, search=None, **kwargs):
    videos, total = await service.get_videos(search=search, **kwargs)
    return [video.title for video in videos], total


@pytest.mark.asyncio
async def test_a_keyword_also_matches_the_description_and_tag_names(db_session):
    source = await _source(db_session, "剧集")
    suspense = await _tag(db_session, "悬疑")
    await _video(db_session, source, "暗涌")
    await _video(db_session, source, "归途", description="一部悬疑作品")
    await _video(db_session, source, "前夜", tags=[suspense])

    service = VideoService(db_session)
    titles, total = await _titles(service, "悬疑")

    assert sorted(titles) == ["前夜", "归途"]
    assert total == 2


@pytest.mark.asyncio
async def test_every_keyword_has_to_hit(db_session):
    source = await _source(db_session, "剧集")
    await _video(db_session, source, "第二集.暗涌", description="雨夜")
    await _video(db_session, source, "第一集.前夜")

    service = VideoService(db_session)

    assert (await _titles(service, "第二集 暗涌"))[0] == ["第二集.暗涌"]
    assert (await _titles(service, "第二集 雨夜"))[0] == ["第二集.暗涌"]
    assert await _titles(service, "第二集 前夜") == ([], 0)


@pytest.mark.asyncio
async def test_a_quoted_phrase_is_one_keyword(db_session):
    source = await _source(db_session, "剧集")
    await _video(db_session, source, "dark hero 收藏版")
    await _video(db_session, source, "hero 独行版")

    service = VideoService(db_session)

    assert (await _titles(service, '"dark hero"'))[0] == ["dark hero 收藏版"]
    assert (await _titles(service, "dark hero"))[0] == ["dark hero 收藏版"]
    assert sorted((await _titles(service, "hero"))[0]) == sorted(
        ["hero 独行版", "dark hero 收藏版"]
    )


@pytest.mark.asyncio
async def test_source_keyword_limits_to_matching_sources(db_session):
    films = await _source(db_session, "电影收藏", path="/media/films")
    series = await _source(db_session, "剧集目录", path="/media/series")
    await _video(db_session, films, "暗涌")
    await _video(db_session, series, "归途")

    service = VideoService(db_session)

    assert (await _titles(service, "源:剧集"))[0] == ["归途"]
    assert (await _titles(service, "源:收藏 暗涌"))[0] == ["暗涌"]
    assert await _titles(service, "源:不存在") == ([], 0)


@pytest.mark.asyncio
async def test_tag_keyword_only_looks_at_tag_names(db_session):
    source = await _source(db_session, "剧集")
    suspense = await _tag(db_session, "悬疑")
    await _video(db_session, source, "悬疑推理课")  # the word is only in the title
    await _video(db_session, source, "暗涌", tags=[suspense])

    service = VideoService(db_session)

    assert (await _titles(service, "标签:悬疑"))[0] == ["暗涌"]


@pytest.mark.asyncio
async def test_rating_and_duration_comparisons(db_session):
    source = await _source(db_session, "剧集")
    await _video(db_session, source, "高分长片", rating=5, duration=5400)
    await _video(db_session, source, "高分短片", rating=5, duration=600)
    await _video(db_session, source, "新片无分", rating=0, duration=90)

    service = VideoService(db_session)

    assert sorted((await _titles(service, "评分>=4"))[0]) == ["高分短片", "高分长片"]
    assert (await _titles(service, "评分=0"))[0] == ["新片无分"]
    assert (await _titles(service, "时长>40分钟"))[0] == ["高分长片"]
    # A unitless number is read as minutes, the unit people quote for films.
    assert (await _titles(service, "时长>=90"))[0] == ["高分长片"]
    assert (await _titles(service, "评分>=4 时长<=15分钟"))[0] == ["高分短片"]


@pytest.mark.asyncio
async def test_watch_state_splits_the_library_three_ways(db_session):
    source = await _source(db_session, "剧集")
    never = await _video(db_session, source, "没碰过")
    unfinished = await _video(db_session, source, "看一半")
    finished = await _video(db_session, source, "看完了")
    await _history(db_session, unfinished, progress=30, completed=False)
    await _history(db_session, finished, progress=120, completed=True)

    service = VideoService(db_session)

    assert (await _titles(service, "没看过"))[0] == ["没碰过"]
    assert (await _titles(service, "未看完"))[0] == ["看一半"]
    assert (await _titles(service, "已看完"))[0] == ["看完了"]


@pytest.mark.asyncio
async def test_title_hits_rank_above_description_hits(db_session):
    source = await _source(db_session, "剧集")
    title_hit = await _video(db_session, source, "暗涌")
    # Created later, so a recency sort would put this one first.
    await _video(db_session, source, "归途", description="重访暗涌之地")

    service = VideoService(db_session)
    titles, _ = await _titles(service, "暗涌")

    assert titles == ["暗涌", "归途"]
    assert title_hit.title == "暗涌"


@pytest.mark.asyncio
async def test_wildcards_typed_by_the_user_are_literal(db_session):
    source = await _source(db_session, "剧集")
    await _video(db_session, source, "100% 胶片")
    await _video(db_session, source, "普通片子")
    await _video(db_session, source, "A_B 修复版")
    await _video(db_session, source, "AXB 修复版")

    service = VideoService(db_session)

    # ``%`` and ``_`` are LIKE wildcards; only a title carrying them matches.
    assert (await _titles(service, "100%"))[0] == ["100% 胶片"]
    assert (await _titles(service, "A_B"))[0] == ["A_B 修复版"]


@pytest.mark.asyncio
async def test_input_that_is_not_an_operator_stays_a_keyword(db_session):
    source = await _source(db_session, "剧集")
    await _video(db_session, source, "16:9 修复版")

    service = VideoService(db_session)

    assert (await _titles(service, "16:9"))[0] == ["16:9 修复版"]


@pytest.mark.asyncio
async def test_a_video_counted_by_two_tags_is_returned_once(db_session):
    source = await _source(db_session, "剧集")
    suspense = await _tag(db_session, "悬疑")
    noir = await _tag(db_session, "黑色电影")
    await _video(db_session, source, "暗涌", tags=[suspense, noir])

    service = VideoService(db_session)
    titles, total = await _titles(service, "悬疑")

    assert titles == ["暗涌"]
    assert total == 1


@pytest.mark.asyncio
async def test_search_combines_with_the_dropdown_filters(db_session):
    series = await _source(db_session, "剧集", path="/media/series")
    other = await _source(db_session, "备用", path="/media/other")
    suspense = await _tag(db_session, "悬疑")
    await _video(db_session, series, "暗涌", tags=[suspense])
    await _video(db_session, series, "归途")
    await _video(db_session, other, "外源暗涌", tags=[suspense])

    service = VideoService(db_session)
    videos, total = await service.get_videos(
        source_id=series.id, tag_id=suspense.id, search="暗涌"
    )

    assert total == 1
    assert [video.title for video in videos] == ["暗涌"]
