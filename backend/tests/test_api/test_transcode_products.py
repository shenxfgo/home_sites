"""转码产物那张表从 HTTP 进来的一次往返（#154）。

服务层用例已经把"成功才登记""手工删了要标回来"那几条钉住，这里钉的是**接口那一边**：
前端要读的是一条新地址，字段名一个也不能少（`frontend/src/types/transcode.ts` 对着它写），
而 `size_bytes` 是当场从磁盘读的、`deleted_at` 是当场写回库的——这两件事只有从接口进
才看得到，因为服务层用例里的会话就是接口用的那个会话。
"""
from datetime import datetime, timezone

import pytest

from src.models.transcode_output import TranscodeOutput
from src.models.video import Video
from src.services import transcode_service as tc_module
from tests.conftest import _SharedSession
from tests.support import ensure_source


@pytest.fixture(autouse=True)
def _clear_jobs():
    """模块级任务表是全进程共享的，别把跑完的任务留给下一个文件。"""
    tc_module._jobs.clear()
    yield
    tc_module._jobs.clear()


async def _video(db_session, tmp_path, name="movie.mp4") -> Video:
    path = tmp_path / name
    path.write_bytes(b"source")
    await ensure_source(db_session)
    video = Video(
        source_id=1, filepath=str(path), title="Movie", duration=120, format="mp4"
    )
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video


async def _record(
    db_session, video: Video, target_format: str, output_path: str,
    created_at: datetime | None = None,
) -> TranscodeOutput:
    row = TranscodeOutput(
        video_id=video.id,
        target_format=target_format,
        output_path=output_path,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


@pytest.mark.asyncio
async def test_a_video_without_products_answers_with_an_empty_list(
    client, db_session, tmp_path
):
    """没转过的片子这条地址回 200 加空表，不是 404——前端拿它渲染一行都没有的表格。"""
    video = await _video(db_session, tmp_path)

    response = await client.get(f"/api/transcode/{video.id}/outputs")

    assert response.status_code == 200, response.json()
    assert response.json() == []


@pytest.mark.asyncio
async def test_the_product_list_carries_every_field_the_frontend_reads(
    client, db_session, tmp_path
):
    video = await _video(db_session, tmp_path)
    product = tmp_path / "out" / "movie.mkv"
    product.parent.mkdir()
    product.write_bytes(b"12345")
    await _record(db_session, video, "mkv", str(product))

    response = await client.get(f"/api/transcode/{video.id}/outputs")

    assert response.status_code == 200, response.json()
    item = response.json()[0]
    assert set(item) == {
        "id", "target_format", "output_path", "size_bytes", "created_at", "deleted_at",
    }, item
    assert item["target_format"] == "mkv", item
    assert item["output_path"] == str(product), item
    assert item["size_bytes"] == 5, item
    assert item["created_at"].startswith("20"), item
    assert item["deleted_at"] is None, item


@pytest.mark.asyncio
async def test_only_that_videos_products_are_listed(client, db_session, tmp_path):
    first = await _video(db_session, tmp_path, "a.mp4")
    second = await _video(db_session, tmp_path, "b.mp4")
    await _record(db_session, first, "mkv", str(tmp_path / "a.mkv"))
    await _record(db_session, second, "webm", str(tmp_path / "b.webm"))

    response = await client.get(f"/api/transcode/{first.id}/outputs")

    assert [item["target_format"] for item in response.json()] == ["mkv"], response.json()


@pytest.mark.asyncio
async def test_the_newest_product_is_listed_first(client, db_session, tmp_path):
    video = await _video(db_session, tmp_path)
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await _record(db_session, video, "webm", str(tmp_path / "m.webm"), created_at=older)
    await _record(db_session, video, "mkv", str(tmp_path / "m.mkv"))

    response = await client.get(f"/api/transcode/{video.id}/outputs")

    assert [item["target_format"] for item in response.json()] == ["mkv", "webm"]


@pytest.mark.asyncio
async def test_a_product_deleted_on_disk_reports_the_gap_and_writes_it_back(
    client, db_session, tmp_path
):
    """接口先 stat 再回答，并把"没了"这件事**写回库**，让下一次读不用重新发现。

    这是 `deleted_at` 唯一的写人，只有从接口进才能确认那句写真的落库了：服务层用例里的
    会话就是接口用的那个，对象改动天然看得见，落不落库无所谓。这里读回来之前先让 ORM 从
    库里重新取一次（`refresh` 会发一条 SELECT），看到的只能是库里的那一份。
    """
    video = await _video(db_session, tmp_path)
    product = tmp_path / "movie.mkv"
    product.write_bytes(b"payload")
    row = await _record(db_session, video, "mkv", str(product))
    assert row.deleted_at is None

    product.unlink()
    response = await client.get(f"/api/transcode/{video.id}/outputs")

    assert response.json()[0]["size_bytes"] is None, response.json()
    assert response.json()[0]["deleted_at"], response.json()

    await db_session.refresh(row)
    assert row.deleted_at is not None, "标记只改了内存对象，没写进库"


@pytest.mark.asyncio
async def test_a_completed_job_from_the_api_shows_up_in_the_product_list(
    client, db_session, tmp_path, monkeypatch
):
    """POST 启动 → 任务成功 → GET 立刻能看见那一行，全程走 HTTP。

    这一条把两头的接线钉住：登记用的是模块级会话（`_record_output`），读用的是请求会话，
    两边必须落在同一个库里；否则界面上「转码完成」和「产物列表为空」会同时为真。
    """
    monkeypatch.setattr(tc_module.settings, "transcode_output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(tc_module, "async_session_maker", _SharedSession(db_session))

    async def noop(self, job):
        return None

    monkeypatch.setattr(tc_module.TranscodeService, "_notify", noop)

    video = await _video(db_session, tmp_path)

    async def instant(input_path, output_path, target_format, **kwargs):
        assert output_path == str(tmp_path / "out" / str(video.id) / "movie.mkv")
        with open(output_path, "wb") as fh:
            fh.write(b"product")
        return True, None

    monkeypatch.setattr(tc_module, "transcode_video", instant)

    started = await client.post(f"/api/transcode/{video.id}", json={"target_format": "mkv"})
    assert started.status_code == 200, started.json()
    await tc_module._jobs[video.id].task

    listed = await client.get(f"/api/transcode/{video.id}/outputs")

    assert listed.status_code == 200, listed.json()
    assert [
        (item["target_format"], item["size_bytes"], item["deleted_at"])
        for item in listed.json()
    ] == [("mkv", 7, None)], listed.json()


@pytest.mark.asyncio
async def test_an_unknown_video_has_no_products(client, db_session):
    response = await client.get("/api/transcode/4242/outputs")

    assert response.status_code == 200, response.json()
    assert response.json() == []
