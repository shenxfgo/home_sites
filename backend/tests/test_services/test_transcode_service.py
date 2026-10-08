"""Tests for TranscodeService operations."""
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.models.source import VideoSource
from src.models.transcode_output import TranscodeOutput
from src.models.video import Video
from src.services import transcode_service as tc_module
from src.services.scan_service import ScanService
from src.services.transcode_service import TranscodeService
from tests.conftest import _SharedSession
from tests.support import ensure_source


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Each test starts from an empty shared job registry."""
    tc_module._jobs.clear()
    yield
    tc_module._jobs.clear()


@pytest.fixture(autouse=True)
def _products_outside_the_repo(tmp_path, monkeypatch):
    """产物目录指到 tmp 下面：默认那个是仓库里的 ``backend/data/transcode``。

    不钉这一条的话，用例每跑一次就往版本库里的工作目录写一份文件。
    """
    monkeypatch.setattr(tc_module.settings, "transcode_output_dir", str(tmp_path / "products"))


@pytest.fixture(autouse=True)
def _products_land_in_the_test_db(monkeypatch, db_session):
    """让后台任务那本独立会话回到**测试库**上。

    ``_record_output`` 和 ``_notify`` 一样走 ``async_session_maker``（请求会话在响应
    返回时就关掉了，后台任务不能再用它），而 conftest 只把中间件那一份换成了测试会话，
    模块里这一份仍然指着应用库。autouse 是因为**每一个**跑完一趟成功的用例都会写一行，
    漏一个就写到真库里去了。借会话的方式与 ``test_app_boot_lifespan`` / ``test_cli`` 同一套。
    """
    monkeypatch.setattr(tc_module, "async_session_maker", _SharedSession(db_session))


async def _create_video(session, tmp_path, filename="movie.mp4", duration=120):
    """Create a video row whose file actually exists on disk."""
    path = tmp_path / filename
    path.write_bytes(b"stub")
    await ensure_source(session)
    video = Video(
        source_id=1,
        filepath=str(path),
        title="Test Video",
        duration=duration,
        format="mp4",
    )
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return video


def _silence_notifications(monkeypatch) -> None:
    """Keep background jobs from writing to the application database."""
    async def noop(self, job):
        return None

    monkeypatch.setattr(TranscodeService, "_notify", noop)


@pytest.mark.asyncio
async def test_get_status_idle(db_session):
    """An unknown video reports idle rather than blowing up."""
    service = TranscodeService(db_session)

    status = await service.get_status(4242)

    assert status == {
        "video_id": 4242,
        "is_transcoding": False,
        "status": "idle",
        "progress": 0.0,
        "target_format": None,
        "output_path": None,
        "error": None,
    }


@pytest.mark.asyncio
async def test_cancel_rejects_job_that_is_not_running(db_session):
    service = TranscodeService(db_session)

    with pytest.raises(ValueError, match="No active transcoding"):
        await service.cancel(4242)


@pytest.mark.asyncio
async def test_transcode_rejects_unsupported_format(db_session, tmp_path):
    video = await _create_video(db_session, tmp_path)
    service = TranscodeService(db_session)

    with pytest.raises(ValueError, match="Unsupported format"):
        await service.transcode(video.id, "exe")


@pytest.mark.asyncio
async def test_transcode_rejects_unknown_video(db_session):
    service = TranscodeService(db_session)

    with pytest.raises(ValueError, match="not found"):
        await service.transcode(4242, "mkv")


@pytest.mark.asyncio
async def test_transcode_rejects_missing_file(db_session, tmp_path):
    service = TranscodeService(db_session)
    video = await _create_video(db_session, tmp_path)
    (tmp_path / "movie.mp4").unlink()

    with pytest.raises(ValueError, match="Video file not found"):
        await service.transcode(video.id, "mkv")


@pytest.mark.asyncio
async def test_transcode_rejects_the_product_having_the_source_name(db_session, tmp_path):
    """同格式在#154之后不再会覆盖源（产物在另一个目录），但它会让产物和源**同名**。

    库里一行 ``movie.mp4``、产物表里一行 ``movie.mp4``，人在界面上看是同一行，而这一单
    买的就是"产物看得见"。闸门留着，挡的理由换了一个。
    """
    video = await _create_video(db_session, tmp_path, filename="movie.mp4")
    service = TranscodeService(db_session)

    with pytest.raises(ValueError, match="same filename as the original"):
        await service.transcode(video.id, "mp4")


@pytest.mark.asyncio
async def test_target_format_is_normalized_before_the_encoder_sees_it(
    db_session, tmp_path, monkeypatch
):
    """闸门大小写不敏感，编码器查表大小写敏感——两边必须拿到同一个值。

    ``check_format_support("MKV")`` 认了，``SUPPORTED_FORMATS.get("MKV")`` 却没有，
    于是接口先回 200「已启动」，任务再在后台失败成「不支持的格式：MKV」。这条用例把
    真正传给编码器的那个字符串钉住（其余用例都把 ``transcode_video`` 整个换掉，参数
    是什么没人看），顺带钉住输出文件的扩展名也跟着归一。
    """
    _silence_notifications(monkeypatch)
    video = await _create_video(db_session, tmp_path)
    calls = []

    async def spy(input_path, output_path, target_format, **kwargs):
        calls.append((output_path, target_format))
        return True, None

    monkeypatch.setattr(tc_module, "transcode_video", spy)

    started = await TranscodeService(db_session).transcode(video.id, "MKV")
    await tc_module._jobs[video.id].task

    assert started["target_format"] == "mkv", started
    expected = str(tmp_path / "products" / str(video.id) / "movie.mkv")
    assert started["output_path"] == expected, started
    assert calls == [(expected, "mkv")], calls
    status = await TranscodeService(db_session).get_status(video.id)
    assert status["status"] == "completed", status


@pytest.mark.asyncio
async def test_status_and_progress_shared_across_service_instances(
    db_session, tmp_path, monkeypatch
):
    """FastAPI builds a new service per request, so the registry is module level."""
    _silence_notifications(monkeypatch)
    video = await _create_video(db_session, tmp_path)

    started = asyncio.Event()

    async def hanging(input_path, output_path, target_format, **kwargs):
        kwargs["on_progress"](42.0)
        started.set()
        await asyncio.Event().wait()
        return True, None

    monkeypatch.setattr(tc_module, "transcode_video", hanging)

    await TranscodeService(db_session).transcode(video.id, "mkv")
    await asyncio.wait_for(started.wait(), timeout=5)

    seen = await TranscodeService(db_session).get_status(video.id)
    assert seen["is_transcoding"] is True, seen
    assert seen["status"] == "running", seen
    assert seen["progress"] == 42.0, seen
    assert seen["target_format"] == "mkv", seen

    duplicate = TranscodeService(db_session)
    with pytest.raises(ValueError, match="already being transcoded"):
        await duplicate.transcode(video.id, "webm")

    await TranscodeService(db_session).cancel(video.id)


@pytest.mark.asyncio
async def test_cancel_stops_the_job_and_records_it(
    db_session, tmp_path, monkeypatch
):
    _silence_notifications(monkeypatch)
    video = await _create_video(db_session, tmp_path)
    started = asyncio.Event()
    killed = asyncio.Event()

    async def hanging(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            killed.set()
            raise

    monkeypatch.setattr(tc_module, "transcode_video", hanging)

    service = TranscodeService(db_session)
    await service.transcode(video.id, "mkv")
    await asyncio.wait_for(started.wait(), timeout=5)
    await TranscodeService(db_session).cancel(video.id)

    await asyncio.wait_for(killed.wait(), timeout=5)

    status = await TranscodeService(db_session).get_status(video.id)
    assert status["status"] == "cancelled", status
    assert status["is_transcoding"] is False, status


@pytest.mark.asyncio
async def test_completed_job_reports_full_progress(
    db_session, tmp_path, monkeypatch
):
    _silence_notifications(monkeypatch)
    video = await _create_video(db_session, tmp_path)

    async def instant(input_path, output_path, target_format, **kwargs):
        kwargs["on_progress"](60.0)
        return True, None

    monkeypatch.setattr(tc_module, "transcode_video", instant)

    await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task

    status = await TranscodeService(db_session).get_status(video.id)
    assert status["status"] == "completed", status
    assert status["progress"] == 100.0, status
    assert status["error"] is None, status


@pytest.mark.asyncio
async def test_failed_job_keeps_the_error_message(
    db_session, tmp_path, monkeypatch
):
    _silence_notifications(monkeypatch)
    video = await _create_video(db_session, tmp_path)

    async def failing(*args, **kwargs):
        return False, "ffmpeg exited with code 1"

    monkeypatch.setattr(tc_module, "transcode_video", failing)

    await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task

    status = await TranscodeService(db_session).get_status(video.id)
    assert status["status"] == "failed", status
    assert status["error"] == "ffmpeg exited with code 1", status
    assert status["is_transcoding"] is False, status


def _product_writer(monkeypatch) -> None:
    """让替身真的把产物写到盘上——这一单的断言全押在"文件在不在"，不能只改内存状态。"""

    async def realish(input_path, output_path, target_format, **kwargs):
        Path(output_path).write_bytes(b"product-bytes")
        return True, None

    monkeypatch.setattr(tc_module, "transcode_video", realish)


async def _rows(session) -> list[TranscodeOutput]:
    result = await session.execute(select(TranscodeOutput).order_by(TranscodeOutput.id))
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_a_product_never_becomes_a_library_row(db_session, tmp_path, monkeypatch):
    """#154 的症状本身：产物从前写在**源的旁边**，而那个目录正是扫描范围。

    ``file_scanner.scan_directory`` 的 ``os.walk`` 一路下潜、没有排除机制，所以下一轮扫描
    会把那份 ``movie.mkv`` 当成一部新片子登记进库 —— 同一部片子从此有两行，还能再转一遍。
    """
    _silence_notifications(monkeypatch)
    _product_writer(monkeypatch)

    media = tmp_path / "media"
    media.mkdir()
    (media / "movie.mp4").write_bytes(b"stub")
    source = VideoSource(name="media", path=str(media), type="local")
    db_session.add(source)
    await db_session.commit()
    video = Video(
        source_id=source.id,
        filepath=str(media / "movie.mp4"),
        title="Test Video",
        duration=120,
        format="mp4",
    )
    db_session.add(video)
    await db_session.commit()

    started = await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task

    product = Path(started["output_path"])
    assert product.is_file(), product
    assert media not in product.parents, "产物又落回扫描范围里了"

    with (
        patch("src.services.scan_service.extract_video_info") as info,
        patch("src.services.scan_service.generate_thumbnail") as thumb,
    ):
        info.return_value = {"duration": 100, "resolution": "1920x1080", "format": "mp4"}
        thumb.return_value = ""
        result = await ScanService(db_session).scan_source(source.id)

    assert result["files_found"] == 1, result
    assert result["new_videos"] == 0, result


@pytest.mark.asyncio
async def test_the_product_is_still_known_after_the_process_forgets_it(
    db_session, tmp_path, monkeypatch
):
    """这一张表存在的全部理由：``_jobs`` 是进程内的，服务一重启就没人记得转过什么。"""
    _silence_notifications(monkeypatch)
    _product_writer(monkeypatch)
    video = await _create_video(db_session, tmp_path)

    started = await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task

    tc_module._jobs.clear()  # 相当于重启了一次

    products = await TranscodeService(db_session).list_outputs(video.id)
    assert len(products) == 1, products
    only = products[0]
    assert only["target_format"] == "mkv", only
    assert only["output_path"] == started["output_path"], only
    assert only["size_bytes"] == Path(started["output_path"]).stat().st_size, only
    assert only["deleted_at"] is None, only
    assert only["created_at"].tzinfo is not None, "读回来的时间必须带时区（#162 那一条形状）"


@pytest.mark.asyncio
async def test_a_failed_job_records_no_product(db_session, tmp_path, monkeypatch):
    """失败的产物压根不存在，写一行"存在过、其实没有"就是这一单要修掉的那种谎。"""
    _silence_notifications(monkeypatch)
    video = await _create_video(db_session, tmp_path)

    async def failing(*args, **kwargs):
        return False, "ffmpeg exited with code 1"

    monkeypatch.setattr(tc_module, "transcode_video", failing)

    await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task

    assert await _rows(db_session) == []


@pytest.mark.asyncio
async def test_a_cancelled_job_records_no_product(db_session, tmp_path, monkeypatch):
    """取消那一路半截文件会被 unlink（``utils/ffmpeg.py``），所以同样不该留行。"""
    _silence_notifications(monkeypatch)
    video = await _create_video(db_session, tmp_path)
    started = asyncio.Event()

    async def hanging(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise

    monkeypatch.setattr(tc_module, "transcode_video", hanging)

    service = TranscodeService(db_session)
    await service.transcode(video.id, "mkv")
    await asyncio.wait_for(started.wait(), timeout=5)
    await TranscodeService(db_session).cancel(video.id)

    assert await _rows(db_session) == []


@pytest.mark.asyncio
async def test_retranscoding_the_same_format_updates_that_one_row(
    db_session, tmp_path, monkeypatch
):
    """同一片子同一容器写的是同一个路径，所以重做是这一行被更新，不是多出一行。"""
    _silence_notifications(monkeypatch)
    _product_writer(monkeypatch)
    video = await _create_video(db_session, tmp_path)

    first = await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task
    second = await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task

    assert second["output_path"] == first["output_path"], second
    rows = await _rows(db_session)
    assert len(rows) == 1, rows
    assert rows[0].video_id == video.id, rows[0]
    assert rows[0].target_format == "mkv", rows[0]


@pytest.mark.asyncio
async def test_a_product_removed_by_hand_is_flagged_and_a_restored_one_clears_it(
    db_session, tmp_path, monkeypatch
):
    """``deleted_at`` 的两个方向都得核对 —— 这一列唯一的写的人就是读的那一次 stat。

    产物目录不在任何片源之内，扫描走不到它；人手工删一份产物腾磁盘是真会发生的事。
    只钉"文件没了要写标记"那一半不够：文件被放回去（误删后恢复、换盘）时标记若不清掉，
    这一列就从漏报变成误报，界面上会说一份明明在盘上的产物"已经不在了"。
    """
    _silence_notifications(monkeypatch)
    _product_writer(monkeypatch)
    video = await _create_video(db_session, tmp_path)

    started = await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task
    product = Path(started["output_path"])

    present = await TranscodeService(db_session).list_outputs(video.id)
    assert present[0]["size_bytes"] is not None, present[0]
    assert present[0]["deleted_at"] is None, present[0]

    product.unlink()
    gone = await TranscodeService(db_session).list_outputs(video.id)
    assert gone[0]["size_bytes"] is None, gone[0]
    assert gone[0]["deleted_at"] is not None, gone[0]
    assert gone[0]["output_path"] == str(product), "行本身要留着：它说的是「产出过」"

    product.write_bytes(b"put back")
    restored = await TranscodeService(db_session).list_outputs(video.id)
    assert restored[0]["deleted_at"] is None, "标记必须跟着盘上的事实翻回去"

    stored = await _rows(db_session)
    assert len(stored) == 1, stored
    assert stored[0].deleted_at is None, "翻回去必须写进库里，不能只在返回值里圆过去"
