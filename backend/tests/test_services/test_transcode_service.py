"""Tests for TranscodeService operations."""
import asyncio

import pytest

from src.models.video import Video
from src.services import transcode_service as tc_module
from src.services.transcode_service import TranscodeService


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Each test starts from an empty shared job registry."""
    tc_module._jobs.clear()
    yield
    tc_module._jobs.clear()


async def _create_video(session, tmp_path, filename="movie.mp4", duration=120):
    """Create a video row whose file actually exists on disk."""
    path = tmp_path / filename
    path.write_bytes(b"stub")
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
async def test_transcode_rejects_overwriting_source(db_session, tmp_path):
    """An mp4 -> mp4 job resolves to the input path and would destroy it."""
    video = await _create_video(db_session, tmp_path, filename="movie.mp4")
    service = TranscodeService(db_session)

    with pytest.raises(ValueError, match="overwrite the original"):
        await service.transcode(video.id, "mp4")


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
