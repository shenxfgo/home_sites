"""转码那两条后台通知真的写进了库（#172）。

`_notify` 那 16 行在既有服务层用例里每个都被换成 noop（`_silence_notifications`），注释
写的是「别让后台任务写应用库」。那条顾虑 #154 之后已经有了别的办法：同一个文件里的 autouse
fixture 把模块级会话指回测试库，后台任务本来就写不到应用库里去。于是这一层在 pytest 里一次
也没真跑过，而它写的正是人能看见的那句话——`NotificationCenter.vue` 的 `isErrorType`
拿 `type.endsWith('_error')` 认失败那一副面孔，真后端 e2e 第 15 条对着 `type` /
`title` / `data` 三个键断言。#142 刚在字幕那条路上修过「失败那句把 ffmpeg 的原因丢了」，
这里是同一个坑的另一个现场。
"""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from src.models.notification import Notification
from src.models.transcode_output import TranscodeOutput
from src.models.video import Video
from src.services import transcode_service as tc_module
from src.services.transcode_service import TranscodeService
from tests.conftest import _SharedSession
from tests.support import ensure_source


@pytest.fixture(autouse=True)
def _clear_jobs():
    tc_module._jobs.clear()
    yield
    tc_module._jobs.clear()


@pytest.fixture(autouse=True)
def _products_outside_the_repo(tmp_path, monkeypatch):
    """默认那个输出目录是仓库里的 ``backend/data/transcode``。"""
    monkeypatch.setattr(tc_module.settings, "transcode_output_dir", str(tmp_path / "out"))


@pytest.fixture(autouse=True)
def _notifications_land_in_the_test_db(monkeypatch, db_session):
    """这一文件存在的理由：`_notify` 走的是模块级会话，得把它按回测试库。

    与 ``test_transcode_service.py`` 里那条同名 fixture 同一套借法；这里不复用它，是因为
    那个文件把 `_notify` 全换成了 noop，那条重定向在那边只是给 `_record_output` 用的。
    """
    monkeypatch.setattr(tc_module, "async_session_maker", _SharedSession(db_session))


async def _video(db_session, tmp_path) -> Video:
    path = tmp_path / "movie.mp4"
    path.write_bytes(b"source")
    await ensure_source(db_session)
    video = Video(
        source_id=1, filepath=str(path), title="Movie", duration=120, format="mp4"
    )
    db_session.add(video)
    await db_session.commit()
    await db_session.refresh(video)
    return video


async def _finish_job(
    db_session, monkeypatch, video: Video, outcome
) -> None:
    """跑完一趟任务并等到后台那一轮结束；``outcome`` 是替身 ``transcode_video`` 的返回。

    给一个异常实例时替身直接抛——那是「编码器进程没了」那一路，和「ffmpeg 回话说失败」
    是两条不同的分支。
    """

    async def fake(input_path, output_path, target_format, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        success, error = outcome
        if success:
            Path(output_path).write_bytes(b"product")
        return success, error

    monkeypatch.setattr(tc_module, "transcode_video", fake)
    await TranscodeService(db_session).transcode(video.id, "mkv")
    await tc_module._jobs[video.id].task


async def _notes(session) -> list[Notification]:
    result = await session.execute(select(Notification).order_by(Notification.id))
    return list(result.scalars().all())


async def _products(session) -> list[TranscodeOutput]:
    result = await session.execute(select(TranscodeOutput).order_by(TranscodeOutput.id))
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_a_finished_job_announces_exactly_one_completion(
    db_session, tmp_path, monkeypatch
):
    """成功那一路：一行 `transcode_complete`，而且只有这一行。

    「只有这一行」不是凑数——#85 那次就是同一条链路每轮写两行通知。`data` 是这一行里唯一
    机器读得住的那半：真后端 e2e 第 15 条对着 `{video_id, format}` 断言（界面上今天还没有
    读者，别把它读成"点了就能跳回那部片子"）。
    """
    video = await _video(db_session, tmp_path)

    await _finish_job(db_session, monkeypatch, video, (True, None))

    rows = await _notes(db_session)
    assert [(r.type, r.title) for r in rows] == [("transcode_complete", "转码完成")]
    assert "已成功转码为 mkv" in rows[0].message, rows[0].message
    assert rows[0].data == {"video_id": video.id, "format": "mkv"}, rows[0].data


@pytest.mark.asyncio
async def test_a_failed_job_passes_ffmpeg_words_into_the_notification(
    db_session, tmp_path, monkeypatch
):
    """ffmpeg 说的那句必须原样出现在通知末尾，不能只剩「失败了」。

    #142 的同一个症状：闸门报了失败，人在通知里看不到为什么，只能自己猜是编码器没装还是
    源文件坏了。
    """
    video = await _video(db_session, tmp_path)

    await _finish_job(
        db_session, monkeypatch, video, (False, "ffmpeg 以退出码 1 结束")
    )

    rows = await _notes(db_session)
    assert [(r.type, r.title) for r in rows] == [("transcode_error", "转码失败")]
    assert "转码为 mkv 格式失败" in rows[0].message, rows[0].message
    assert rows[0].message.endswith("ffmpeg 以退出码 1 结束"), rows[0].message
    assert rows[0].data == {"video_id": video.id, "format": "mkv"}, rows[0].data


@pytest.mark.asyncio
async def test_a_failure_with_no_reason_still_says_something(
    db_session, tmp_path, monkeypatch
):
    """`transcode_video` 只回一句「没成功」却没给原因时，那句得写「未知原因」。

    这一路 `job.error` 是 `None`，不接住的话 message 会拼成「……失败：None」，通知里出现
    一个 Python 的 `None`。
    """
    video = await _video(db_session, tmp_path)

    await _finish_job(db_session, monkeypatch, video, (False, None))

    rows = await _notes(db_session)
    assert [r.type for r in rows] == ["transcode_error"]
    assert rows[0].message.endswith("未知原因"), rows[0].message


@pytest.mark.asyncio
async def test_an_encoder_that_dies_midway_still_announces(
    db_session, tmp_path, monkeypatch
):
    """编码器抛异常（不是回 `False`）那一路：状态写 failed，人那边也得有一行。

    这一条钉的是 `except Exception`（155-158）：它把异常咽下并转成状态，然后**继续**走到
    `_notify`。少了这一步，ffmpeg 子进程整个没了的那种失败就只有日志里看得见——而日志
    不是人查问题的地方。
    """
    video = await _video(db_session, tmp_path)

    await _finish_job(
        db_session, monkeypatch, video, RuntimeError("ffmpeg 进程消失了")
    )

    status = await TranscodeService(db_session).get_status(video.id)
    assert status["status"] == "failed", status
    assert status["error"] == "ffmpeg 进程消失了", status

    rows = await _notes(db_session)
    assert [r.type for r in rows] == ["transcode_error"]
    assert "ffmpeg 进程消失了" in rows[0].message, rows[0].message
    assert await _products(db_session) == [], "崩掉的这一趟没有产物"


@pytest.mark.asyncio
async def test_a_notification_that_cannot_be_written_does_not_sink_the_job(
    db_session, tmp_path, monkeypatch
):
    """通知写不进去（表被锁、库正好在维护）时吞掉，但任务状态与产物登记都不受牵连。

    `_notify` 里那个 `except Exception` 是整个后台任务的最后一道兜底：它要是往外抛，
    转码已经做完了的事实在 `await task` 那一头会变成一次崩溃。产物那一行是独立会话写的，
    不能被一条通知的失败带走。
    """

    async def exploding(self, **kwargs):
        raise RuntimeError("notifications 表被锁住了")

    monkeypatch.setattr(tc_module.NotificationService, "create", exploding)
    video = await _video(db_session, tmp_path)

    await _finish_job(db_session, monkeypatch, video, (True, None))

    assert await _notes(db_session) == []
    status = await TranscodeService(db_session).get_status(video.id)
    assert status["status"] == "completed", status
    assert len(await _products(db_session)) == 1, "产物登记被一次通知失败带累了"


class _ScalarFails:
    """把 `session.scalar` 变成一次数据库故障，其余都原样交给借来的会话。

    `_record_output` 开头那次查重用的就是 `scalar`。只坏这一处，`_notify` 那一路（add /
    commit / refresh）才能照常跑完——两条吞异常的路分得开，整个 maker 一起坏就分不开了。
    """

    def __init__(self, session) -> None:
        self._session = session

    async def scalar(self, *_args, **_kwargs):
        raise RuntimeError("transcode_outputs 读不了")

    def __getattr__(self, name):
        return getattr(self._session, name)


class _WrappingSession(_SharedSession):
    """与 `_SharedSession` 同一个借法，只是把交出去的会话包一层。"""

    async def __aenter__(self):
        return _ScalarFails(await super().__aenter__())


@pytest.mark.asyncio
async def test_a_product_that_cannot_be_recorded_still_announces(
    db_session, tmp_path, monkeypatch
):
    """登记产物那一行失败时吞掉，通知照写，任务照完成。

    这一对是反过来的依赖：文件真的转出来了，表里那一行只是账。记账失败不能让人以为转码
    也失败了。
    """
    video = await _video(db_session, tmp_path)
    monkeypatch.setattr(tc_module, "async_session_maker", _WrappingSession(db_session))

    await _finish_job(db_session, monkeypatch, video, (True, None))

    assert await _products(db_session) == []
    status = await TranscodeService(db_session).get_status(video.id)
    assert status["status"] == "completed", status
    assert [r.type for r in await _notes(db_session)] == ["transcode_complete"]


@pytest.mark.asyncio
async def test_a_cancelled_job_announces_nothing(
    db_session, tmp_path, monkeypatch
):
    """取消是人按下的一下，不是失败：既不该有 `transcode_complete`，也不该有 `transcode_error`。

    `_run` 在 `CancelledError` 那一路重新抛出，所以 `_notify` 那一句根本走不到。这条要是
    哪天被「顺手加个 finally」改写了，每个取消都会多发一条失败通知。
    """
    started = asyncio.Event()

    async def hanging(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
        return True, None  # pragma: no cover - 只有取消才离开这里

    monkeypatch.setattr(tc_module, "transcode_video", hanging)
    video = await _video(db_session, tmp_path)

    service = TranscodeService(db_session)
    await service.transcode(video.id, "mkv")
    await asyncio.wait_for(started.wait(), timeout=5)
    await service.cancel(video.id)

    assert tc_module._jobs[video.id].status == "cancelled"
    assert await _notes(db_session) == []
