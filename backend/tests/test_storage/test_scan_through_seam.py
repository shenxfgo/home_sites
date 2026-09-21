"""扫描经由存储层取文件，两条保证值得单独钉住。

一个是"够不着不等于全丢了"：源不可达时扫描返回空列表，若据此把每一行都标成
丢失，一次凭证错误就能让整库变灰。另一个是对照——源真的空了要照实标。
"""
import os

import pytest

from src.config import settings
from src.models.source import VideoSource
from src.models.video import Video
from src.services.scan_service import ScanService


async def _seed_video(db_session, *, path: str, type_: str, locator: str):
    source = VideoSource(name="待核对的源", path=path, type=type_)
    db_session.add(source)
    await db_session.commit()

    video = Video(source_id=source.id, filepath=locator, title="01", format="mkv")
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return source, video


@pytest.mark.asyncio
async def test_unreachable_share_leaves_existing_rows_alone(db_session, tmp_path):
    """挂载盘没就绪时，已有的行不该被读成"文件没了"。"""
    gone = str(tmp_path / "not-mounted")
    source, video = await _seed_video(
        db_session,
        path=gone,
        type_="local",
        locator=os.path.join(gone, "01.mkv"),
    )

    result = await ScanService(db_session).scan_source(source.id)
    await db_session.refresh(video)

    assert result["files_found"] == 0
    assert video.is_missing is False


@pytest.mark.asyncio
async def test_empty_but_reachable_source_marks_rows_missing(db_session, tmp_path):
    """对照用例：源够得着、里面确实没文件，那就照实标记丢失。"""
    root = str(tmp_path)
    source, video = await _seed_video(
        db_session,
        path=root,
        type_="local",
        locator=os.path.join(root, "01.mkv"),
    )

    await ScanService(db_session).scan_source(source.id)
    await db_session.refresh(video)

    assert video.is_missing is True


@pytest.mark.asyncio
async def test_bucket_without_credentials_is_not_read_as_emptied(
    db_session, monkeypatch
):
    """最危险的一种配置错误：凭证填错，扫描什么都找不到。"""
    monkeypatch.setattr(settings, "s3_access_key_id", "")
    monkeypatch.setattr(settings, "s3_secret_access_key", "")
    source, video = await _seed_video(
        db_session,
        path="s3://media/shows",
        type_="minio",
        locator="s3://media/shows/01.mkv",
    )

    result = await ScanService(db_session).scan_source(source.id)
    await db_session.refresh(video)

    assert result["files_found"] == 0
    assert video.is_missing is False


@pytest.mark.asyncio
async def test_bucket_scan_indexes_rows_without_thumbnails(
    db_session, monkeypatch, tmp_path
):
    """对象存储能列能入库，但出不了缩略图：FFmpeg 没有本地文件可读。"""
    reason = '对象存储用例需要额外依赖：pip install -e ".[dev,s3]"'
    pytest.importorskip("boto3", reason=reason)
    pytest.importorskip("moto", reason=reason)
    import boto3
    from moto import mock_aws

    monkeypatch.setattr(settings, "s3_access_key_id", "test-access-key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "test-secret-key")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "thumbnail_path", str(tmp_path / "thumbs"))

    source = VideoSource(
        name="桶", path="s3://media/shows", type="minio"
    )
    db_session.add(source)
    await db_session.commit()

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="media")
        client.put_object(Bucket="media", Key="shows/第03集.mkv", Body=b"x" * 4096)

        result = await ScanService(db_session).scan_source(source.id)

    assert result["files_found"] == 1
    assert result["new_videos"] == 1
    assert result["subtitles_found"] == 0

    rows = (
        await db_session.execute(
            Video.__table__.select().where(Video.source_id == source.id)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].filepath == "s3://media/shows/第03集.mkv"
    assert rows[0].title  # 文件名解析照旧生效
    assert rows[0].file_size == 4096
    assert rows[0].duration is None
    assert rows[0].thumbnail_path is None
