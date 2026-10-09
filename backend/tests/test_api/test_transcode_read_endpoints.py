"""转码那三个端点从 HTTP 进来的往返（#172）。

`src/api/transcode.py` 薄的那 11% 就是四段：`GET /{video_id}/status`、
`POST /{video_id}/cancel`（连它那个 404 分支一起）、`GET /formats`，以及 `POST /{video_id}`
那句把服务层的拒绝转成 400 的 `except`。pytest 里只请求过 `POST /{video_id}` 成功那一路和
`GET /{video_id}/outputs` 两条地址，剩下几处一次也没被敲过——
浏览器那边 `Transcode.vue` 进页面就并发读状态与格式表、之后每 1.5 秒轮一次状态，可那都
是对着替身或真后端跑完的整条长流程，「没人启动过」和「取消一个不存在的任务」这两种回答
没人从接口这一头核对过形状。
"""
import asyncio
import contextlib

import pytest

from src.models.video import Video
from src.services import transcode_service as tc_module
from src.utils.ffmpeg import SUPPORTED_FORMATS
from tests.support import ensure_source


@pytest.fixture(autouse=True)
def _clear_jobs():
    """模块级任务表是全进程共享的，别把挂着的活动任务留给下一个文件。"""
    tc_module._jobs.clear()
    yield
    tc_module._jobs.clear()


@pytest.fixture(autouse=True)
def _products_outside_the_repo(tmp_path, monkeypatch):
    """默认那个输出目录是仓库里的 ``backend/data/transcode``。"""
    monkeypatch.setattr(tc_module.settings, "transcode_output_dir", str(tmp_path / "out"))


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


async def _start_a_job_that_hangs(
    client, video: Video, monkeypatch, progress: float
) -> tc_module.TranscodeJob:
    """真的用 ``POST /{video_id}`` 启一个任务，并让它卡在 ffmpeg 那一趟里不返回。

    手搭一条 ``_jobs`` 也能造出「正在跑」，但那样要钉的就只剩序列化，启动那一条接线
    （POST 返回 → 后台任务开始 → 状态读得到）反而没人签收了。

    这个替身**永不返回**，只有被取消才结束，所以 ``_notify`` / ``_record_output`` 那两条
    会写应用库的路在本文件里到不了 —— 本文件也因此不需要重定向模块级会话。
    """
    started = asyncio.Event()

    async def hanging(*args, **kwargs):
        kwargs["on_progress"](progress)
        started.set()
        await asyncio.Event().wait()
        return True, None  # pragma: no cover - 只有取消才离开这一行

    monkeypatch.setattr(tc_module, "transcode_video", hanging)

    response = await client.post(
        f"/api/transcode/{video.id}", json={"target_format": "mkv"}
    )
    assert response.status_code == 200, response.json()
    await asyncio.wait_for(started.wait(), timeout=5)
    return tc_module._jobs[video.id]


async def _kill(job: tc_module.TranscodeJob) -> None:
    """收掉挂着的任务：留下一个被取消的活动任务，下一个文件就转不动了。"""
    job.task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await job.task


@pytest.mark.asyncio
async def test_a_video_nobody_started_answers_with_a_complete_idle_status(
    client, db_session, tmp_path
):
    """进转码页那一刻读的就是这一条：七个字段一个不能少。

    ``frontend/src/types/transcode.ts`` 的 ``TranscodeStatus`` 是照着这个响应写的，
    而 ``Transcode.vue:217`` 的 ``loadAll`` 在没有任务时也照读。缺字段在接口上不会报错，
    只会在页面上变成 ``undefined``。
    """
    video = await _video(db_session, tmp_path)

    response = await client.get(f"/api/transcode/{video.id}/status")

    assert response.status_code == 200, response.json()
    assert response.json() == {
        "video_id": video.id,
        "is_transcoding": False,
        "status": "idle",
        "progress": 0.0,
        "target_format": None,
        "output_path": None,
        "error": None,
    }


@pytest.mark.asyncio
async def test_the_status_of_a_running_job_carries_its_progress_to_one_decimal(
    client, db_session, tmp_path, monkeypatch
):
    """轮询读的那一路：跑着的时候 ``is_transcoding`` 为真，进度只保留一位小数。

    ``on_progress(33.37)`` 出来必须是 ``33.4``——页面上那格「进度」直接印这个数，而它是
    ``utils/ffmpeg.py`` 拿时间戳除出来的，不四舍五入就是一长串小数。
    """
    video = await _video(db_session, tmp_path)
    job = await _start_a_job_that_hangs(client, video, monkeypatch, 33.37)

    response = await client.get(f"/api/transcode/{video.id}/status")
    await _kill(job)

    assert response.status_code == 200, response.json()
    assert response.json() == {
        "video_id": video.id,
        "is_transcoding": True,
        "status": "running",
        "progress": 33.4,
        "target_format": "mkv",
        "output_path": job.output_path,
        "error": None,
    }


@pytest.mark.asyncio
async def test_a_video_row_that_no_longer_exists_still_answers_idle(
    client, db_session
):
    """状态那一条读的是进程内那本 ``_jobs``，一次库都不查。

    于是拿着一个已经不存在的影片 id 去问，得到的也是 200 + idle 而不是 404。这一条钉的是
    现状：改成 404 的话前端那一头会走进 `fetchStatus` 的 catch（`Transcode.vue:120`），
    页面上凭空多出一类「状态接口没有回应」。删影片、删片源之后那一轮还没结束的轮询就是这么
    落地的——它是既有形状，不是用例造出来的偏好。
    """
    response = await client.get("/api/transcode/4242/status")

    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "idle"
    assert response.json()["is_transcoding"] is False


@pytest.mark.asyncio
async def test_a_refused_start_comes_back_with_the_reason(client, db_session, tmp_path):
    """启动那两句 `except ValueError`（400 + 原因）此前只有服务层用例敲过。

    前端在启动失败时读的是响应里的 `detail`，拿不到原因就只剩一句「启动失败」。两种拒绝
    走的是同一个出口，理由不同：格式不支持、以及那部片子不存在。
    """
    video = await _video(db_session, tmp_path)

    bad_format = await client.post(
        f"/api/transcode/{video.id}", json={"target_format": "exe"}
    )
    assert bad_format.status_code == 400, bad_format.json()
    assert "exe" in bad_format.json()["detail"], bad_format.json()

    no_video = await client.post("/api/transcode/4242", json={"target_format": "mkv"})
    assert no_video.status_code == 400, no_video.json()
    assert "4242" in no_video.json()["detail"], no_video.json()


@pytest.mark.asyncio
async def test_cancelling_a_video_that_is_not_transcoding_says_why(
    client, db_session, tmp_path
):
    """取消一个没在跑的片子：404，而且原因得跟着过来。

    ``detail`` 是服务层那句英文（``No active transcoding for video …``），#153 还等着把它
    换成中文，所以这里不钉措辞，只钉「非空 + 带着那个影片 id」——用户看得懂是哪一部。
    """
    video = await _video(db_session, tmp_path)

    response = await client.post(f"/api/transcode/{video.id}/cancel")

    assert response.status_code == 404, response.json()
    detail = response.json()["detail"]
    assert detail, "404 却没人说出原因"
    assert str(video.id) in detail, detail


@pytest.mark.asyncio
async def test_cancelling_a_live_job_answers_204_and_the_status_follows(
    client, db_session, tmp_path, monkeypatch
):
    """取消那一下走完整条 HTTP 链：204 空体，随后状态说「已取消」。

    ``Transcode.vue:186`` 在收到 204 之后就 ``ElMessage.success('转码已取消')`` 并停掉轮询，
    它相信这一次取消真的落进了那本任务表。服务层用例钉的是 ``cancel()`` 本身，这里钉的是
    「204 且没有响应体」这个接口形状。
    """
    video = await _video(db_session, tmp_path)
    await _start_a_job_that_hangs(client, video, monkeypatch, 12.5)

    cancelled = await client.post(f"/api/transcode/{video.id}/cancel")
    assert cancelled.status_code == 204, cancelled.json()
    assert cancelled.content == b"", cancelled.content

    status = await client.get(f"/api/transcode/{video.id}/status")
    assert status.status_code == 200, status.json()
    assert status.json()["status"] == "cancelled", status.json()
    assert status.json()["is_transcoding"] is False, status.json()


@pytest.mark.asyncio
async def test_a_running_job_left_without_a_task_still_ends_cancelled(
    client, db_session, tmp_path
):
    """``cancel()`` 最后那两行是兜底，正常流程拿不到，只能手摆。

    ``transcode()`` 是先建好 ``job.task`` 再登记进 ``_jobs``，而 ``_run`` 每一路都会写状态
    （成功/失败/取消都写），所以「账上挂着 running 却已经没有任务了」这一状态今天到不了。
    留着它是给任务对象丢了的那一天兜底，按 #165 里那些拿不到的格子的做法：手工摆出那个
    状态，钉住它确实收敛成 ``cancelled``，并在此声明它是防御分支而不是实测到的路径。
    """
    video = await _video(db_session, tmp_path)
    tc_module._jobs[video.id] = tc_module.TranscodeJob(
        video_id=video.id,
        target_format="mkv",
        output_path=str(tmp_path / "out" / str(video.id) / "movie.mkv"),
        status="running",
        task=None,
    )

    response = await client.post(f"/api/transcode/{video.id}/cancel")
    assert response.status_code == 204, response.json()

    status = await client.get(f"/api/transcode/{video.id}/status")
    assert status.json()["status"] == "cancelled", status.json()
    assert status.json()["is_transcoding"] is False, status.json()


@pytest.mark.asyncio
async def test_the_formats_endpoint_is_the_encoder_table(client):
    """``GET /formats`` 必须是 ``SUPPORTED_FORMATS`` 的投影，不多不少。

    前端拿它渲染「目标格式」的下拉（``TranscodeFormat`` 三个字段：``format`` /
    ``codec`` / ``extension``）。这一条同时钉住服务层那句直通 ——编码器那张表加一种、
    这里就跟着多一种；漏了 ``codec`` 或改了键名，页面会显示成空白而不是报错。
    """
    response = await client.get("/api/transcode/formats")

    assert response.status_code == 200, response.json()
    assert response.json() == [
        {"format": fmt, "codec": info["codec"], "extension": info["ext"]}
        for fmt, info in SUPPORTED_FORMATS.items()
    ]
