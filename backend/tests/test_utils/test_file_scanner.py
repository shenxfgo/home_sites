"""Tests for the on-disk scanner: which files count, and what ffprobe says.

``ffprobe``/``ffmpeg`` are patched out — the unit under test is how this module
reads their output and what it does when they disagree, not whether the machine
has them installed. One assertion pins the argv that gets sent, because the
flags are the behaviour (which frame the cover takes, how wide it lands, and the
UTF-8 decode that keeps a cp936 console from turning ffprobe's output into None).
"""

import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from src.utils import file_scanner
from src.utils.file_scanner import (
    VIDEO_EXTENSIONS,
    extract_video_info,
    generate_thumbnail,
    scan_directory,
)


class _FakeRun:
    """Record the call and answer with a canned subprocess result."""

    def __init__(self, returncode=0, stdout="", exception=None, side_effect=None):
        self.returncode = returncode
        self.stdout = stdout
        self.exception = exception
        self.side_effect = side_effect
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((list(cmd), kwargs))
        if self.exception is not None:
            raise self.exception
        if self.side_effect is not None:
            self.side_effect(list(cmd))
        return SimpleNamespace(returncode=self.returncode, stdout=self.stdout, stderr="")

    @property
    def argv(self) -> list[str]:
        return self.calls[0][0]

    @property
    def kwargs(self) -> dict:
        return self.calls[0][1]


def _write_cover(cmd: list[str]):
    """Write to ffmpeg's output path, and nowhere else.

    父目录故意不建：封面路径的目录是 ``generate_thumbnail`` 自己 mkdir 出来的，
    这里跟着建就把那条分支测没了。
    """
    with open(cmd[-1], "wb") as handle:
        handle.write(b"\xff\xd8")


def _patch_run(monkeypatch, fake: _FakeRun) -> None:
    monkeypatch.setattr(file_scanner.subprocess, "run", fake)


# ---------- scan_directory ----------


def test_a_nested_tree_yields_every_video_with_its_size(tmp_path):
    shelf = tmp_path / "电视剧" / "第一季"
    shelf.mkdir(parents=True)
    (shelf / "ep01.mkv").write_bytes(b"x" * 700)
    (shelf / "ep02.MKV").write_bytes(b"y" * 900)
    (tmp_path / "movie.mp4").write_bytes(b"z" * 10)
    # 字幕、封面和说明文件就堆在同一个目录里，扫描只认视频后缀。
    (shelf / "ep01.srt").write_text("1\n00:00:01 --> 00:00:02\nhi\n", encoding="utf-8")
    (tmp_path / "cover.jpg").write_bytes(b"12345678")
    (tmp_path / "notes.txt").write_bytes(b"")

    found = scan_directory(str(tmp_path))

    by_name = {item["filename"]: item for item in found}
    assert set(by_name) == {"ep01.mkv", "ep02.MKV", "movie.mp4"}
    assert by_name["ep01.mkv"]["file_size"] == 700
    assert by_name["ep02.MKV"]["file_size"] == 900
    # 后缀统一小写入库，大小写不同的同一个视频不会被当成两种格式。
    assert by_name["ep02.MKV"]["extension"] == ".mkv"
    assert by_name["ep01.mkv"]["extension"] in VIDEO_EXTENSIONS
    assert by_name["ep01.mkv"]["filepath"] == os.path.join(str(shelf), "ep01.mkv")


def test_an_empty_directory_is_a_scan_with_no_results(tmp_path):
    assert scan_directory(str(tmp_path)) == []


def test_a_path_that_is_not_a_directory_scans_to_nothing(tmp_path):
    a_file = tmp_path / "movie.mp4"
    a_file.write_bytes(b"x")
    assert scan_directory(str(a_file)) == []
    assert scan_directory(str(tmp_path / "未挂载")) == []


def test_a_file_that_vanishes_mid_scan_is_skipped_not_fatal(tmp_path, monkeypatch):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"x")
    real_stat = os.stat

    def flaky(path, *args, **kwargs):
        # 只让这一次 stat 失败：入口的 root.is_dir() 也走 os.stat，
        # 全量替换会让用例测到的是闸门而不是这个 except。
        if str(path) == str(video):
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", flaky)
    try:
        found = scan_directory(str(tmp_path))
    finally:
        monkeypatch.undo()

    assert found == []


def test_a_junction_is_walked_into(tmp_path):
    """联接点指向的目录会被一起扫进来，这是特性不是漏风。

    家里的片库跨盘就靠这个（源目录里放一个指向第二块盘的 junction）。真正的权限
    边界在"谁能加视频源"上——只有 owner 能加，而他能加的本来就包括整块盘，
    遍历阶段再拦一层并不会更严，反而会把跨盘的库扫成半套。
    """
    if os.name != "nt":
        pytest.skip("POSIX 上 os.walk 默认不跟软链，这条说的是 Windows 的 junction")
    library = tmp_path / "library"
    elsewhere = tmp_path / "第二块盘"
    library.mkdir()
    elsewhere.mkdir()
    (elsewhere / "private.mkv").write_bytes(b"x" * 123)

    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(library / "escape"), str(elsewhere)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if made.returncode != 0:
        pytest.skip(f"建不出 junction：{made.stdout}\n{made.stderr}")

    found = scan_directory(str(library))

    assert [item["filename"] for item in found] == ["private.mkv"]
    # 入库的是遍历到的那条路径，不是解析后的真身：locator 全靠字符串全等去重。
    assert found[0]["filepath"] == os.path.join(str(library), "escape", "private.mkv")


# ---------- extract_video_info ----------


def test_duration_and_resolution_come_from_the_probe(monkeypatch):
    _patch_run(
        monkeypatch,
        _FakeRun(
            stdout=json.dumps(
                {
                    "format": {"duration": "1234.56"},
                    "streams": [
                        {"codec_type": "audio", "channels": 2},
                        {"codec_type": "video", "width": 1920, "height": 1080},
                        {"codec_type": "video", "width": 640, "height": 360},
                    ],
                }
            )
        ),
    )

    info = extract_video_info(os.path.join("media", "show", "ep01.mkv"))

    assert info == {"duration": 1234, "resolution": "1920x1080", "format": "mkv"}


def test_the_first_video_stream_wins(monkeypatch):
    _patch_run(
        monkeypatch,
        _FakeRun(
            stdout=json.dumps(
                {
                    "format": {"duration": "60"},
                    "streams": [
                        {"codec_type": "video", "width": 3840, "height": 2160},
                        {"codec_type": "video", "width": 1280, "height": 720},
                    ],
                }
            )
        ),
    )
    assert extract_video_info("a.mp4")["resolution"] == "3840x2160"


def test_the_probe_is_asked_for_json_and_the_path_is_untouched(monkeypatch, tmp_path):
    fake = _FakeRun(stdout=json.dumps({"format": {}, "streams": []}))
    _patch_run(monkeypatch, fake)
    path = str(tmp_path / "日剧 01.webm")

    extract_video_info(path)

    assert fake.argv[0] == "ffprobe"
    assert fake.argv[-1] == path
    assert "-show_streams" in fake.argv and "-show_format" in fake.argv
    # 区域编码是 cp936 时，按它解码 ffprobe 的 UTF-8 输出会抛异常并把 stdout 变成 None。
    assert fake.kwargs["encoding"] == "utf-8"


@pytest.mark.parametrize("stdout", ["", "not json at all"])
def test_unusable_output_leaves_only_the_extension(monkeypatch, stdout, tmp_path):
    _patch_run(monkeypatch, _FakeRun(returncode=0, stdout=stdout))

    info = extract_video_info(str(tmp_path / "movie.mp4"))

    assert info == {"duration": None, "resolution": None, "format": "mp4"}


def test_a_failing_probe_is_reported_as_no_metadata(monkeypatch):
    _patch_run(monkeypatch, _FakeRun(returncode=1, stdout=""))

    assert extract_video_info("a.mkv") == {
        "duration": None,
        "resolution": None,
        "format": "mkv",
    }


def test_a_garbage_duration_is_left_empty(monkeypatch):
    _patch_run(
        monkeypatch,
        _FakeRun(stdout=json.dumps({"format": {"duration": "N/A"}, "streams": []})),
    )
    assert extract_video_info("a.mkv")["duration"] is None


def test_a_stream_list_without_video_has_no_resolution(monkeypatch):
    _patch_run(
        monkeypatch,
        _FakeRun(
            stdout=json.dumps(
                {"format": {"duration": "10"}, "streams": [{"codec_type": "audio"}]}
            )
        ),
    )
    info = extract_video_info("a.mp4")
    assert info["resolution"] is None
    assert info["duration"] == 10


def test_a_video_stream_without_dimensions_has_no_resolution(monkeypatch):
    _patch_run(
        monkeypatch,
        _FakeRun(stdout=json.dumps({"format": {}, "streams": [{"codec_type": "video"}]})),
    )
    assert extract_video_info("a.mp4")["resolution"] is None


@pytest.mark.parametrize(
    "exception",
    [
        FileNotFoundError("ffprobe not installed"),
        subprocess.TimeoutExpired(cmd="ffprobe", timeout=10),
    ],
)
def test_a_missing_or_hanging_probe_does_not_break_the_scan(monkeypatch, exception):
    _patch_run(monkeypatch, _FakeRun(exception=exception))

    info = extract_video_info("a.mp4")

    assert info == {"duration": None, "resolution": None, "format": "mp4"}


def test_a_file_without_extension_has_no_format(monkeypatch):
    _patch_run(monkeypatch, _FakeRun(returncode=1, stdout=""))
    assert extract_video_info("LICENSE")["format"] is None


# ---------- generate_thumbnail ----------


def test_a_cover_is_written_where_the_caller_asked(tmp_path, monkeypatch):
    output = tmp_path / "covers" / "deep" / "ep01.jpg"
    _patch_run(monkeypatch, _FakeRun(side_effect=_write_cover))

    assert generate_thumbnail("ep01.mkv", str(output)) == str(output)
    # 目录是这里建的，调用方不用先 mkdir。
    assert output.exists()


def test_the_cover_command_is_pinned(tmp_path, monkeypatch):
    """封面取第 1 秒、缩到 320 宽，参数顺序就是这里的行为。

    ``-ss`` 现在跟在 ``-i`` 后面，也就是解码到该时间点的精确取帧；家里这片源上
    1 秒的解码代价可以忽略，所以这条用例锁的是"取哪一帧、多宽"，不是顺序的快慢。
    """
    output = tmp_path / "covers" / "ep01.jpg"
    fake = _FakeRun(side_effect=_write_cover)
    _patch_run(monkeypatch, fake)
    video = str(tmp_path / "ep01.mkv")

    generate_thumbnail(video, str(output))

    assert fake.argv == [
        "ffmpeg",
        "-y",
        "-i",
        video,
        "-ss",
        "00:00:01",
        "-vframes",
        "1",
        "-vf",
        "scale=320:-1",
        str(output),
    ]
    assert fake.kwargs["timeout"] == 30


def test_a_zero_exit_without_a_file_is_a_failure(tmp_path, monkeypatch):
    _patch_run(monkeypatch, _FakeRun(returncode=0, stdout=""))
    assert generate_thumbnail("a.mkv", str(tmp_path / "missing.jpg")) == ""


def test_a_failing_ffmpeg_is_silent(tmp_path, monkeypatch):
    _patch_run(monkeypatch, _FakeRun(returncode=1, stdout=""))
    assert generate_thumbnail("a.mkv", str(tmp_path / "cover.jpg")) == ""


@pytest.mark.parametrize(
    "exception",
    [
        FileNotFoundError("ffmpeg not installed"),
        subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30),
    ],
)
def test_a_missing_or_hanging_ffmpeg_yields_no_cover(tmp_path, monkeypatch, exception):
    _patch_run(monkeypatch, _FakeRun(exception=exception))
    assert generate_thumbnail("a.mkv", str(tmp_path / "cover.jpg")) == ""
