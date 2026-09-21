"""对象存储上的影片能播，吃本地路径的功能必须给出人话。

挡住之前这些请求会得到一句"视频文件不存在"——那是假话，会把配置问题伪装成
媒体库缺文件。
"""
import pytest

from src.models.source import VideoSource
from src.models.video import Video

LOCATOR = "s3://media/shows/01.mkv"


async def _object_video(db_session) -> Video:
    source = VideoSource(name="桶", path="s3://media/shows", type="minio")
    db_session.add(source)
    await db_session.commit()

    video = Video(
        source_id=source.id, filepath=LOCATOR, title="01", format="mkv", file_size=4096
    )
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video


@pytest.mark.asyncio
async def test_transcoding_an_object_explains_itself(client, db_session):
    video = await _object_video(db_session)

    response = await client.post(
        f"/api/transcode/{video.id}", json={"target_format": "mp4"}
    )

    assert response.status_code == 400
    assert "对象存储" in response.json()["detail"]


@pytest.mark.asyncio
async def test_listing_embedded_tracks_explains_itself(client, db_session):
    video = await _object_video(db_session)

    response = await client.get(f"/api/videos/{video.id}/subtitles/streams")

    assert response.status_code == 400
    assert "内嵌字幕" in response.json()["detail"]


@pytest.mark.asyncio
async def test_extracting_an_embedded_track_explains_itself(client, db_session):
    video = await _object_video(db_session)

    response = await client.get(
        f"/api/videos/{video.id}/subtitles/embedded/0/stream"
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_attaching_a_sidecar_explains_itself(client, db_session):
    video = await _object_video(db_session)

    response = await client.post(
        f"/api/videos/{video.id}/subtitles",
        json={"filepath": "s3://media/shows/01.zh.srt"},
    )

    assert response.status_code == 400
    assert "外挂字幕" in response.json()["detail"]


@pytest.mark.asyncio
async def test_streaming_an_unreadable_object_falls_back_without_500(
    client, db_session
):
    """没配凭证时读不到大小，回落到占位响应而不是把播放器打成 500。"""
    video = await _object_video(db_session)

    response = await client.get(f"/api/videos/{video.id}/stream")

    assert response.status_code == 200
    assert "note" in response.json()


@pytest.mark.asyncio
async def test_duplicate_check_survives_an_object_locator(client, db_session):
    """重复检测会一次读一堆跨源文件，对象存储读不到只能算"不是重复"。

    两部同尺寸才会进候选组，指纹这一步才会真的被走到；读不到必须安静跳过，
    而不是让整页 500。
    """
    source = VideoSource(name="桶", path="s3://media/shows", type="minio")
    db_session.add(source)
    await db_session.commit()
    db_session.add_all(
        [
            Video(
                source_id=source.id,
                filepath=f"s3://media/shows/{name}.mkv",
                title=name,
                format="mkv",
                file_size=4096,
            )
            for name in ("01", "02")
        ]
    )
    await db_session.commit()

    response = await client.get("/api/videos/duplicates")

    assert response.status_code == 200
    assert response.json() == []
