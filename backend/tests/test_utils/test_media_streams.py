"""Tests for the embedded stream probe and WebVTT extraction.

#175 补的是这一文件此前**三格零签字**的薄位置（61 句缺 5 句：`57-58, 66, 176-177`），它们的共同
点是"探针跑不起来 / 输出不是预期那样"这一族从来没被演过：`57-58` 是 ffprobe 回了一段坏 JSON，
`66` 是一条**完全没有语言标签**的轨（注意和 `und`/`xxx` 不是一格，那两值走的是 `68`；`65` 那个
判断本身早有用例经过，缺的是它的 `return`），`176-177` 是提取时 ffmpeg 根本起不来 / 挂住 / 被拒绝。
原先 10 条把 `subprocess.run` 换成替身演的是"一切顺利"那一路，代价和 #174 同形：发出去的
**超时、编码参数**本身没有一格签字，两处异常元组里 `OSError` 那一支也从来没真的坏过。

顺带量到一处现状（见文件末尾两条）：`extract_subtitle_webvtt` 在 ffprobe 自己跑不起来时，
会说成"文件里没有编号为 N 的字幕轨"——原因被换成了一个关于这部片子的假话。用例钉的是现状，
不是认可；怎么改属于产品决定，待用户定夺。
"""
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.utils.media_streams import (
    StreamNotFoundError,
    extract_subtitle_webvtt,
    probe_streams,
)
from src.utils.subtitles import SubtitleConversionError

PROBE_RESULT = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264"},
        {
            "index": 1,
            "codec_type": "subtitle",
            "codec_name": "subrip",
            "tags": {"language": "chi", "title": "简中"},
        },
        {
            "index": 2,
            "codec_type": "subtitle",
            "codec_name": "ass",
            "tags": {"language": "eng"},
        },
        {
            "index": 3,
            "codec_type": "subtitle",
            "codec_name": "hdmv_pgs_subtitle",
            "tags": {"language": "und"},
        },
        {
            "index": 4,
            "codec_type": "audio",
            "codec_name": "aac",
            "tags": {"language": "chi"},
            "disposition": {"default": 1},
        },
        {
            "index": 5,
            "codec_type": "audio",
            "codec_name": "ac3",
            "tags": {"language": "jpn"},
            "disposition": {"default": 0},
        },
    ],
    "format": {"format_name": "matroska,webm"},
}


class FakeRun:
    """Stand in for subprocess.run, returning one canned result per call.

    `kwargs` 记的是**发出去的那份参数**——超时和编码约定只能在这一头签（#174 同一课）。
    喂进来的若是一个异常实例，就当作子进程那一步真的坏了（`raise`）而不是当结果返回。
    """

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []
        self.kwargs = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        self.kwargs.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _probe():
    return SimpleNamespace(returncode=0, stdout=json.dumps(PROBE_RESULT), stderr="")


def _stdout(text):
    return SimpleNamespace(returncode=0, stdout=text, stderr="")


def _child(stdout, returncode=0, stderr=""):
    """任意一份 ffprobe / ffmpeg 的收尾状态。"""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_probe_streams_lists_tracks_in_container_order():
    with patch("src.utils.media_streams.subprocess.run", FakeRun(_probe())):
        found = probe_streams("D:\\videos\\movie.mkv")

    assert found["probed"] is True
    assert found["container"] == "matroska,webm"
    assert [item["stream_index"] for item in found["subtitles"]] == [1, 2, 3]
    assert [item["position"] for item in found["subtitles"]] == [0, 1, 2]
    assert found["subtitles"][0]["label"] == "简中"
    assert found["subtitles"][0]["supported"] is True
    # No title tag: the language code becomes the menu label.
    assert found["subtitles"][1]["label"] == "英文"
    assert found["subtitles"][1]["language"] == "eng"
    # A bitmap track cannot be turned into WebVTT, so the UI must not offer it.
    assert found["subtitles"][2]["supported"] is False
    assert found["subtitles"][2]["language"] is None


def test_probe_streams_asks_ffprobe_for_streams_and_format():
    fake = FakeRun(_probe())
    with patch("src.utils.media_streams.subprocess.run", fake):
        probe_streams("D:\\videos\\movie.mkv")

    assert fake.calls[0][0] == "ffprobe"
    assert fake.calls[0][-1] == "D:\\videos\\movie.mkv"
    assert "-show_streams" in fake.calls[0]
    assert "-show_format" in fake.calls[0]


def test_probe_streams_labels_audio_and_its_default():
    with patch("src.utils.media_streams.subprocess.run", FakeRun(_probe())):
        found = probe_streams("D:\\videos\\movie.mkv")

    assert [item["label"] for item in found["audio"]] == ["中文", "日文"]
    assert [item["default"] for item in found["audio"]] == [True, False]


def test_probe_streams_reports_an_unreadable_file_without_lying():
    failure = SimpleNamespace(returncode=1, stdout="", stderr="No such file")
    with patch("src.utils.media_streams.subprocess.run", FakeRun(failure)):
        found = probe_streams("D:\\nas\\movie.mkv")

    assert found == {"probed": False, "container": None, "subtitles": [], "audio": []}


def test_probe_streams_survives_ffprobe_being_absent():
    with patch(
        "src.utils.media_streams.subprocess.run", side_effect=FileNotFoundError("ffprobe")
    ):
        found = probe_streams("D:\\videos\\movie.mkv")

    assert found["probed"] is False


def test_extract_writes_the_webvtt_to_stdout(tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    payload = "WEBVTT\n\n00:01.000 --> 00:02.000\n中文内嵌\n"

    fake = FakeRun(_probe(), _stdout(payload))
    with patch("src.utils.media_streams.subprocess.run", fake):
        text = extract_subtitle_webvtt(str(video), 1)

    assert text == payload
    command = fake.calls[1]
    assert command[0] == "ffmpeg"
    assert command[command.index("-map") + 1] == "0:1"
    assert command[-1] == "-"
    assert "-y" not in command


def test_extract_puts_a_break_led_embedded_cue_back_together(tmp_path):
    """内嵌 ASS 轨上同一个洞：本机实测 ffmpeg 把以 `\\N` 开头的台词写成「时间戳 + 空行 + 文本」。

    那条空行在 WebVTT 里就是这条 cue 的结束，于是浏览器解析出一条空文本的 cue，那句词整个不显示。
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    stdout = (
        "WEBVTT\n\n"
        "00:05.000 --> 00:08.000\n\n内嵌 ASS 第一句 ONE\n\n"
        "00:10.000 --> 00:12.000\n内嵌 ASS 第二句 TWO\n"
    )

    fake = FakeRun(_probe(), _stdout(stdout))
    with patch("src.utils.media_streams.subprocess.run", fake):
        text = extract_subtitle_webvtt(str(video), 2)

    assert "00:05.000 --> 00:08.000\n内嵌 ASS 第一句 ONE" in text
    assert text.startswith("WEBVTT\n\n")
    # 第二条本来就正常，它前面那个空行是分条用的，不许跟着一起被收掉。
    assert "TWO\n" in text
    assert "\n\n00:10.000 --> 00:12.000\n" in text


def test_extract_refuses_a_stream_that_is_not_a_subtitle(tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")

    fake = FakeRun(_probe())
    with patch("src.utils.media_streams.subprocess.run", fake):
        with pytest.raises(StreamNotFoundError):
            extract_subtitle_webvtt(str(video), 0)

    # The probe rejects the index before ffmpeg is ever started.
    assert [command[0] for command in fake.calls] == ["ffprobe"]


def test_extract_reports_an_unconvertible_track(tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    failure = SimpleNamespace(
        returncode=1,
        stdout="",
        stderr="Output file #0 does not contain any stream\nUnsupported codec hdmv_pgs_subtitle",
    )

    fake = FakeRun(_probe(), failure)
    with patch("src.utils.media_streams.subprocess.run", fake):
        with pytest.raises(SubtitleConversionError, match="Unsupported codec"):
            extract_subtitle_webvtt(str(video), 3)


def test_extract_needs_the_file_on_disk():
    with pytest.raises(FileNotFoundError):
        extract_subtitle_webvtt("D:\\videos\\ gone.mkv", 1)


# ---------- #175：探针跑不起来 / 输出不是预期那样 ----------


def _streams(*streams):
    """一份只装着给定 `streams` 的 ffprobe 输出。"""
    return json.dumps({"streams": list(streams), "format": {"format_name": "matroska"}})


def test_a_truncated_ffprobe_json_is_read_as_unreadable_rather_than_crashing(tmp_path):
    """`57-58`：ffprobe 被中途杀掉 / 磁盘写满时吐的是半截 JSON，这一格必须落成"读不出来"。

    走的是 `probe_streams`，也就是片源详情那个轨列表——一句 `JSONDecodeError` 会把整页
    变成 500，而"这一部暂时探不到"是同一个界面本来就会处理的形状（`probed: False`）。
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    fake = FakeRun(_child('{"streams": ['))

    with patch("src.utils.media_streams.subprocess.run", fake):
        found = probe_streams(str(video))

    assert found == {"probed": False, "container": None, "subtitles": [], "audio": []}


def test_a_track_with_no_language_tag_at_all_falls_back_to_its_position(tmp_path):
    """`66`：连 `tags` 都没有的一条轨（裸 AAC、裸 srt 轨常见）不该拿到一个语言名。

    这一格和 `und`/`xxx` 不是一回事：后两者走的是 `68`（有标签但那个值是占位符），
    所以两处都得各自的钉——菜单上"轨道 1"和"英文"的分别就靠这两行。
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    fake = FakeRun(
        _child(
            _streams(
                {"index": 0, "codec_type": "audio", "codec_name": "aac"},
                {
                    "index": 1,
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "tags": {},
                },
            )
        )
    )

    with patch("src.utils.media_streams.subprocess.run", fake):
        found = probe_streams(str(video))

    assert [(item["language"], item["label"]) for item in found["audio"]] == [(None, "轨道 1")]
    assert [(item["language"], item["label"]) for item in found["subtitles"]] == [
        (None, "轨道 1")
    ]
    # 没有语言不等于不支持：能不能转 WebVTT 只看编码器。
    assert found["subtitles"][0]["supported"] is True


def test_a_whitespace_or_empty_language_tag_is_still_not_a_language(tmp_path):
    """两种"有标签但没有语言"的坏法走的是两个不同的口子，所以两条都要各自钉。

    `""` 在 `tags.get("language") or tags.get("LANGUAGE")` 那里就是假值，走 `65` 从 `66` 回 None；
    只有 `"  "` 这种**空白**值能活到 `67` 的 `strip().lower()`，再撞上 `68` 集合里那个 `""`。
    换句话说：把 `{"und", "xxx", ""}` 里的 `""` 删掉，只有空白那一条会红——实测过，别抄近路。
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    fake = FakeRun(
        _child(
            _streams(
                {
                    "index": 0,
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "tags": {"language": "  "},
                },
                {
                    "index": 1,
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "tags": {"language": ""},
                },
            )
        )
    )

    with patch("src.utils.media_streams.subprocess.run", fake):
        found = probe_streams(str(video))

    assert [(item["language"], item["label"]) for item in found["subtitles"]] == [
        (None, "轨道 1"),
        (None, "轨道 2"),
    ]


def test_both_child_processes_are_given_a_deadline_and_a_decoding_contract(tmp_path):
    """替身演掉子进程之后，唯一还签得住"这两次调用长什么样"的就是这份参数表。

    `text=True` 刻意**不**在这里断言：#174 的 Z4 实测过，只要 `encoding` 还在，
    `subprocess` 本身就进文本模式，那一格是结构上红不了的等价参数——写了只会让人以为它有签字。
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    fake = FakeRun(
        _child(_streams({"index": 0, "codec_type": "subtitle", "codec_name": "subrip"})),
        _child(_streams({"index": 0, "codec_type": "subtitle", "codec_name": "subrip"})),
        _child("WEBVTT\n\n"),
    )

    with patch("src.utils.media_streams.subprocess.run", fake):
        probe_streams(str(video))
        extract_subtitle_webvtt(str(video), 0)

    assert [call[0] for call in fake.calls] == ["ffprobe", "ffprobe", "ffmpeg"]
    probed, extracted = fake.kwargs[1], fake.kwargs[2]
    # 探测 30 秒、转码 60 秒：一个是菜单上的即时读，一个真在写管道。
    assert probed["timeout"] == 30
    assert extracted["timeout"] == 60
    for kwargs in (probed, extracted):
        assert kwargs["capture_output"] is True
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"


def test_a_probe_hang_or_denied_share_reads_as_unreadable():
    """`48-49` 的另外两支：ffprobe 挂住 / 共享被拒绝，详情页上只该显示"探不到"。

    已有的 `test_probe_streams_survives_ffprobe_being_absent` 只演过 `FileNotFoundError`
    那一支，另外两支从来没被真的抛过——电池里把元组里的 `TimeoutExpired` 或 `OSError`
    摘掉，此前是量不出红的。这一格红在接口上就是片源详情整页 500。
    """
    for effect in (subprocess.TimeoutExpired("ffprobe", 30), PermissionError(13, "denied")):
        with patch("src.utils.media_streams.subprocess.run", side_effect=effect):
            found = probe_streams("D:\\nas\\movie.mkv")

        assert found["probed"] is False


def test_ffprobe_tag_keys_are_read_in_either_casing(tmp_path):
    """打包器写标签有两种拼法：`language` / `LANGUAGE`、`title` / `TITLE`，四种都得认。

    大写字面此前全库零签字——把 `tags.get("LANGUAGE")` 或 `tags.get("TITLE")` 那一半边摘掉
    是量不出红的。顺带钉住 `xxx` 这个占位码：它和 `und` 撞在 `68` 的同一个集合上，
    但此前只有 `und` 被喂过，删掉 `"xxx"` 同样红不了。
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    fake = FakeRun(
        _child(
            _streams(
                {
                    "index": 0,
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "tags": {"LANGUAGE": "jpn"},
                },
                {
                    "index": 1,
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "tags": {"TITLE": "评论轨"},
                },
                {
                    "index": 2,
                    "codec_type": "subtitle",
                    "codec_name": "webvtt",
                    "tags": {"language": "xxx"},
                },
            )
        )
    )

    with patch("src.utils.media_streams.subprocess.run", fake):
        found = probe_streams(str(video))

    assert [(item["language"], item["label"]) for item in found["subtitles"]] == [
        ("jpn", "日文"),
        (None, "评论轨"),
        (None, "轨道 3"),
    ]


def _extract_with_second_call_raising(tmp_path, effect):
    """让 ffprobe 正常回一条字幕轨，第二步的 ffmpeg 换成抛 `effect`。"""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    fake = FakeRun(
        _child(_streams({"index": 0, "codec_type": "subtitle", "codec_name": "subrip"})),
        effect,
    )
    with patch("src.utils.media_streams.subprocess.run", fake):
        return extract_subtitle_webvtt(str(video), 0)


def test_extract_says_the_conversion_failed_when_ffmpeg_cannot_be_started(tmp_path):
    """`176-177`：连进程都没起来时也要给一句"转换失败"，而不是让 `OSError` 穿到接口外面。"""
    with pytest.raises(SubtitleConversionError, match="内嵌字幕提取失败"):
        _extract_with_second_call_raising(tmp_path, OSError(22, "Invalid argument"))


def test_extract_says_which_of_the_three_child_failures_it_was(tmp_path):
    """三种坏法（起不来 / 挂住 / 被拒绝）各走一遍 `176-177`，且原因得带在句子里。

    这一族是 #142 的下半：外挂那一路的失败原因已经由 `ffmpeg_stderr_reason` 签收，
    内嵌这一路"根本没有 stderr 可读"的三种坏法此前一条没有。但元组的承重不均要记下来：
    `FileNotFoundError` 和 `PermissionError` 都是 `OSError` 的子类，单独摘掉任一支都摘不出红
    （电池里实测），真正有签字的是 `OSError` 与 `TimeoutExpired` 那两支。
    """
    with pytest.raises(SubtitleConversionError, match=r"\[Errno 2\] ffmpeg not found"):
        _extract_with_second_call_raising(tmp_path, FileNotFoundError(2, "ffmpeg not found"))
    with pytest.raises(SubtitleConversionError, match="timed out"):
        _extract_with_second_call_raising(tmp_path, subprocess.TimeoutExpired("ffmpeg", 60))
    with pytest.raises(SubtitleConversionError, match="denied"):
        _extract_with_second_call_raising(tmp_path, PermissionError(13, "denied"))


def _extract_after_a_useless_probe(tmp_path, first):
    """第一步（ffprobe）按 `first` 坏掉，看 `extract_subtitle_webvtt` 说的是哪句话。"""
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")
    fake = FakeRun(first)
    with patch("src.utils.media_streams.subprocess.run", fake):
        with pytest.raises(StreamNotFoundError, match="没有编号为 0 的字幕轨") as caught:
            extract_subtitle_webvtt(str(video), 0)
    return fake, caught.value


def test_a_probe_that_could_not_run_is_blamed_on_the_file(tmp_path):
    """本单量出的那个洞（钉的是现状，不是认可）：探不到 ≠ 没有这条轨。

    ffprobe 跑不起来（没装、不在服务账号的 PATH 上、30 秒没回）时 `_run_ffprobe` 回 `{}`，
    于是 `wanted` 是空集，接口说的是「文件里没有编号为 0 的字幕轨」并回 404（`api/subtitles.py`
    把 `StreamNotFoundError` 映射成 404）——那句是**关于这部片子的假话**，而真原因（工具没跑成）
    是用户听得见也修得了的一句话。对照 #142：外挂那一路后来把 ffmpeg 的原因带上了，这一路今天
    仍然把原因换成一个错误的否定。要不要分开、分开成 404 还是 503/415，属于产品决定，待用户定夺。
    """
    absent = FileNotFoundError(2, "ffprobe not found")
    fake, error = _extract_after_a_useless_probe(tmp_path, absent)

    assert str(error) == "文件里没有编号为 0 的字幕轨"
    # 连一次 ffmpeg 都没起——那句"没有这条轨"是在探测失败之后立刻说的。
    assert [call[0] for call in fake.calls] == ["ffprobe"]


def test_a_probe_that_exits_non_zero_is_blamed_on_the_file_too(tmp_path):
    """同一个洞的第二种坏法：ffprobe 起来了但非零退出（文件坏、share 掉线），话还是一句假话。"""
    _extract_after_a_useless_probe(tmp_path, _child("", returncode=1, stderr="Invalid data"))
