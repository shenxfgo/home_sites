"""转码那一条命令的配方、进度解析和失败原因——在 pytest 里第一次真的被执行（#169）。

`src/utils/ffmpeg.py` 全量跑里只有 **23%**：服务层用例把 `transcode_video` 整个换成替身，
真 ffmpeg 又只在**另一个进程**里跑（`e2e/real/`），那份执行永远不进这份覆盖率。于是这一节
的四件事——argv 的配方、`-progress` 的读法、失败时把 ffmpeg 自己的话递出去、取消时把半截
文件收走——在 pytest 这一侧一次也没走过。

这里用**假子进程**把它们钉住，而不是再开一条真 ffmpeg：真产物已经有 4 条真后端 e2e 从结果
那一头签收了（容器、编码器、真字节落在真路径上），这一层签的是**发出请求的那一头**——
命令行长什么样、读回来的行怎么解释。两头对着同一个约定，任何一头改了自己不通知对方都会红。

这一层现在**签满了整个文件**：原先留白的 `get_video_info`（35-56）已由 #189 删掉——全仓 `grep`
只有它自己的定义和一份 2026-07-27 的计划文档提到它，**没有任何调用方**，而给死代码写用例只会
让它看起来是活的。
"""
import asyncio
from unittest.mock import patch

import pytest

from src.utils.ffmpeg import (
    SUPPORTED_FORMATS,
    _parse_ffmpeg_time,
    get_supported_formats,
    transcode_video,
)

INPUT = r"D:\library\movie.mp4"
OUTPUT = r"D:\out\1\movie.mkv"


class _FakeStream:
    """按脚本一行行喂 `stdout`，喂完给 EOF；也可以在第 N 行之后炸掉。"""

    def __init__(self, lines, crash_after=None, block_after=None, ready=None):
        self._lines = list(lines)
        self._crash_after = crash_after
        self._block_after = block_after
        self._ready = ready
        self.read_count = 0

    async def readline(self):
        if self._crash_after is not None and self.read_count >= self._crash_after:
            raise RuntimeError("pipe broke")
        if not self._lines:
            return b""
        self.read_count += 1
        line = self._lines.pop(0)
        if self._block_after is not None and self.read_count >= self._block_after:
            # 真正的 ffmpeg 会一直编码下去；这里让下一行 await 到一个永远不会来的事件上，
            # 好让测试有机会把任务取消掉。
            if self._ready is not None:
                self._ready.set()
            await asyncio.Event().wait()
        return line


class _FakeProcess:
    def __init__(self, lines, returncode=0, **stream_kwargs):
        self.stdout = _FakeStream(lines, **stream_kwargs)
        self.returncode = None
        self._exit_code = returncode
        self.kill_count = 0
        self.wait_count = 0

    def kill(self):
        self.kill_count += 1
        self.returncode = -9

    async def wait(self):
        self.wait_count += 1
        if self.returncode is None:
            self.returncode = self._exit_code
        return self.returncode


class _FakeSpawn:
    """替 `asyncio.create_subprocess_exec`：记下 argv，返回那个假进程。"""

    def __init__(self, process=None, error=None):
        self.process = process
        self.error = error
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.process


def _transcode(lines, returncode=0, **stream_kwargs):
    """跑一次转码，命令由假进程逐行喂回 `lines`。"""
    process = _FakeProcess(lines, returncode=returncode, **stream_kwargs)
    spawn = _FakeSpawn(process)
    with patch("src.utils.ffmpeg.asyncio.create_subprocess_exec", spawn):
        result = asyncio.run(transcode_video(INPUT, OUTPUT, "mkv"))
    return result, process, spawn


def test_the_recipe_is_the_command_ffmpeg_is_handed_verbatim():
    """argv 逐字对表：容器配哪一对编码器、`-y`、`-progress pipe:1` 全在这一条上。"""
    for target_format, info in SUPPORTED_FORMATS.items():
        output = rf"D:\out\1\movie.{target_format}"
        spawn = _FakeSpawn(_FakeProcess([b"progress=end\n"]))
        with patch("src.utils.ffmpeg.asyncio.create_subprocess_exec", spawn):
            success, error = asyncio.run(
                transcode_video(INPUT, output, target_format, 30.0)
            )

        assert (success, error) == (True, None), (target_format, error)
        (args, kwargs) = spawn.calls[0]
        assert list(args) == [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            INPUT,
            "-c:v",
            info["codec"],
            "-c:a",
            info["acodec"],
            "-y",
            "-progress",
            "pipe:1",
            output,
        ], target_format
        # stderr 折进同一条管道：两处各一个缓冲，ffmpeg 会在写满stderr 时卡住。
        assert kwargs["stdout"] is asyncio.subprocess.PIPE
        assert kwargs["stderr"] is asyncio.subprocess.STDOUT


def test_webm_is_the_one_container_that_cannot_take_aac():
    """这一格单独钉：`-c:a aac` 在 webm 里是 ffmpeg 直接拒绝的配方，不是"效果差点"。"""
    assert SUPPORTED_FORMATS["webm"]["acodec"] == "libopus"
    assert {item["format"] for item in get_supported_formats()} == set(SUPPORTED_FORMATS)


def test_progress_lines_become_percentages_and_are_capped_at_one_hundred():
    seen: list[float] = []
    lines = [
        b"out_time_ms=10000000\n",  # 机器可读的那两个键不该被当时间戳解析
        b"out_time=00:00:10.000000\n",
        b"out_time=00:01:30.000000\n",
        b"out_time=00:05:00.000000\n",  # 比源还长：封顶，不许报出 300%
        b"progress=end\n",
    ]
    process = _FakeProcess(lines)
    spawn = _FakeSpawn(process)
    with patch("src.utils.ffmpeg.asyncio.create_subprocess_exec", spawn):
        success, error = asyncio.run(
            transcode_video(INPUT, OUTPUT, "mkv", 100.0, seen.append)
        )

    assert (success, error) == (True, None), error
    assert seen == [10.0, 90.0, 100.0], seen


def test_the_microsecond_keys_never_drive_the_progress_bar():
    """`out_time_ms` / `out_time_us` 数的是微秒，被当成 `HH:MM:SS` 读会差出六个数量级。

    今天这一格只是碰巧安全：`_parse_ffmpeg_time("10000000")` 认不出来，于是那行被丢掉。
    这里把**键名**那一层单独钉住——将来谁把解析器改成认裸数字、却忘了只对 `out_time=` 生效，
    这一格会先红，而不是把 10000% 进度悄悄送上去。
    """
    seen: list[float] = []
    lines = [b"out_time_ms=10000000\n", b"out_time_us=10000000\n", b"progress=end\n"]
    with patch(
        "src.utils.ffmpeg.asyncio.create_subprocess_exec",
        _FakeSpawn(_FakeProcess(lines)),
    ):
        success, error = asyncio.run(
            transcode_video(INPUT, OUTPUT, "mkv", 100.0, seen.append)
        )

    assert (success, error) == (True, None), error
    assert seen == [], seen


@pytest.mark.parametrize(
    "kwargs",
    [
        {"total_duration": None},  # 源时长未知：没有任何分母可算
        {"on_progress": None},  # 没人听：解析照做，但不许炸
        {"total_duration": 100.0, "on_progress": None},
    ],
    ids=["no-duration", "no-callback", "neither"],
)
def test_a_progress_line_without_something_to_compare_against_says_nothing(kwargs):
    lines = [b"out_time=00:00:10.000000\n", b"progress=end\n"]
    process = _FakeProcess(lines)
    with patch("src.utils.ffmpeg.asyncio.create_subprocess_exec", _FakeSpawn(process)):
        success, error = asyncio.run(transcode_video(INPUT, OUTPUT, "mkv", **kwargs))

    assert (success, error) == (True, None), error


def test_a_malformed_timestamp_is_skipped_installed_of_stopping_the_run():
    """认不出的一条 `out_time=` 只丢掉这一格，任务照常跑完。"""

    def record(_):
        raise AssertionError("a stamp we cannot read must not reach the callback")

    for stamp in (b"out_time=not-a-time\n", b"out_time=01:02\n", b"out_time=\n"):
        lines = [stamp, b"progress=end\n"]
        with patch(
            "src.utils.ffmpeg.asyncio.create_subprocess_exec",
            _FakeSpawn(_FakeProcess(lines)),
        ):
            success, error = asyncio.run(
                transcode_video(INPUT, OUTPUT, "mkv", 60.0, record)
            )
        assert (success, error) == (True, None), (stamp, error)

    assert _parse_ffmpeg_time("01:00:00.500000") == 3600.5
    assert _parse_ffmpeg_time("garbage") is None


def test_the_failure_carries_what_ffmpeg_said_and_nothing_else():
    """失败那句给的是 ffmpeg 自己的话，机器可读的那些行不许混进去。"""
    diagnostic = "[vc @ 0x1f3c] Invalid data found when processing input"
    prose = "Error while decoding stream #0:0: Invalid data found"
    lines = [
        b"frame=1\n",
        b"out_time=00:00:02.000000\n",
        b"bitrate=1200kB/s\n",
        f"{diagnostic}\n".encode(),
        b"\n",  # 空行：既不是进度也不是诊断
        f"{prose}\n".encode(),
    ]

    result, process, _ = _transcode(lines, returncode=1)

    assert result[0] is False, result
    assert result[1] == f"{diagnostic} {prose}", result[1]
    for noise in ("frame=", "out_time", "bitrate=", "progress="):
        assert noise not in result[1], result[1]
    assert process.returncode == 1


def test_a_failure_that_said_nothing_says_only_the_exit_code():
    """没有诊断行时不许编造原因，但也不能空着回一句"失败了"。"""
    result, _, _ = _transcode([b"out_time=00:00:02.000000\n"], returncode=134)

    assert result == (False, "ffmpeg 以退出码 134 结束"), result


def test_an_unsupported_format_never_starts_a_process():
    """闸门在服务层就已经拦过一次；这一层自己也得拦，且不能留下半个进程。"""
    spawn = _FakeSpawn(_FakeProcess([b"progress=end\n"]))
    with patch("src.utils.ffmpeg.asyncio.create_subprocess_exec", spawn):
        success, error = asyncio.run(transcode_video(INPUT, OUTPUT, "flv", 30.0))

    assert success is False
    assert error == "不支持的格式：flv", error
    assert spawn.calls == [], spawn.calls


def test_ffmpeg_not_being_installed_is_said_in_words():
    """`PATH` 上没有 ffmpeg 时给的是原因，不是回溯——这一句会原样出现在界面上。"""
    spawn = _FakeSpawn(error=FileNotFoundError(2, "No such file or directory: 'ffmpeg'"))
    with patch("src.utils.ffmpeg.asyncio.create_subprocess_exec", spawn):
        success, error = asyncio.run(transcode_video(INPUT, OUTPUT, "mkv", 30.0))

    assert success is False
    assert error is not None and error.startswith("无法启动 ffmpeg："), error
    assert "ffmpeg" in error, error


def test_a_pipe_that_breaks_mid_run_is_a_failure_that_still_reaps_the_child(tmp_path):
    """读管道炸了：要说得出原因，也不能把子进程丢在原地没人收。"""
    lines = [b"out_time=00:00:02.000000\n", b"out_time=00:00:04.000000\n"]
    process = _FakeProcess(lines, crash_after=1)
    with patch("src.utils.ffmpeg.asyncio.create_subprocess_exec", _FakeSpawn(process)):
        success, error = asyncio.run(transcode_video(INPUT, OUTPUT, "mkv", 30.0))

    assert (success, error) == (False, "pipe broke"), error
    assert process.kill_count == 1, "杀不掉就要 reap，两者都得发生"
    assert process.wait_count >= 1


def test_cancelling_kills_the_child_and_removes_the_half_written_file(tmp_path):
    """取消那一路的真契约：子进程被 kill、半截产物被收走、`CancelledError` 原样抛上去。

    真子进程那一路在真后端 e2e（第 21 条，#136）里签；这里签的是**代码形状**——那句 unlink
    在 `suppress(OSError)` 里面，所以文件不在盘上（ffmpeg 还没来得及建）也不能变成一次失败。
    """
    product = tmp_path / "movie.mkv"
    ready = asyncio.Event()
    lines = [b"out_time=00:00:02.000000\n", b"out_time=00:00:04.000000\n"]
    process = _FakeProcess(lines, block_after=1, ready=ready)

    async def scenario():
        product.write_bytes(b"half an encode")
        with patch(
            "src.utils.ffmpeg.asyncio.create_subprocess_exec", _FakeSpawn(process)
        ):
            task = asyncio.create_task(transcode_video(INPUT, str(product), "mkv", 30.0))
            await asyncio.wait_for(ready.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())

    assert process.kill_count == 1, process.kill_count
    assert process.wait_count >= 1, "杀完必须等回收，否则僵尸进程留在原地"
    assert not product.exists(), "半截产物必须跟着任务一起没了"
