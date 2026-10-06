"""Tests for subtitle discovery and WebVTT conversion helpers."""
import os
import subprocess
from unittest.mock import patch

import pytest

from src.utils.subtitles import (
    SubtitleConversionError,
    convert_to_webvtt,
    find_subtitle_files,
    read_subtitle_text,
    srt_to_webvtt,
)


def _touch(directory: str, name: str, content: str = "x") -> str:
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def test_find_subtitle_files_matches_sidecars(tmp_path):
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.srt")
    _touch(str(tmp_path), "movie.zh.srt")
    _touch(str(tmp_path), "movie.en.vtt")

    found = find_subtitle_files(video)

    assert [os.path.basename(s["filepath"]) for s in found] == [
        "movie.en.vtt",
        "movie.srt",
        "movie.zh.srt",
    ]


def test_find_subtitle_files_ignores_unrelated_and_sibling_files(tmp_path):
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "moviex.srt")
    _touch(str(tmp_path), "movie.mkv.zh.srt")
    _touch(str(tmp_path), "notes.txt")

    found = find_subtitle_files(video)

    assert found == []


def test_find_subtitle_files_parses_language_codes(tmp_path):
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.zh-CN.srt")
    _touch(str(tmp_path), "movie.chi.srt")
    _touch(str(tmp_path), "movie.中文.srt")

    by_name = {
        os.path.basename(s["filepath"]): s for s in find_subtitle_files(video)
    }

    assert by_name["movie.zh-CN.srt"]["language"] == "zh-cn"
    assert by_name["movie.zh-CN.srt"]["label"] == "zh-CN"
    assert by_name["movie.chi.srt"]["language"] == "zh"
    # Non-ASCII suffixes are kept as the label but are not valid language tags
    assert by_name["movie.中文.srt"]["language"] is None
    assert by_name["movie.中文.srt"]["label"] == "中文"


def test_find_subtitle_files_supports_fullname_sidecars(tmp_path):
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.mp4.zh.srt")

    found = find_subtitle_files(video)

    assert found[0]["language"] == "zh"
    assert found[0]["label"] == "zh"


def test_find_subtitle_files_on_missing_directory_returns_empty():
    assert find_subtitle_files(os.path.join("Z:", "nope", "movie.mp4")) == []


def test_srt_to_webvtt_rewrites_timestamps_and_drops_indices():
    srt = (
        "1\r\n"
        "00:00:01,000 --> 00:00:04,500\r\n"
        "你好\r\n"
        "\r\n"
        "2\r\n"
        "00:01:05,250 --> 00:01:08,000\r\n"
        "hello\r\n"
    )

    vtt = srt_to_webvtt(srt)

    assert vtt.startswith("WEBVTT\n\n")
    assert "00:00:01.000 --> 00:00:04.500" in vtt
    assert "00:01:05.250 --> 00:01:08.000" in vtt
    assert "\n1\n" not in vtt
    assert "你好" in vtt


def test_read_subtitle_text_falls_back_to_gb18030(tmp_path):
    path = tmp_path / "gbk.srt"
    path.write_bytes("00:00:01,000 --> 00:00:02,000\n中文测试\n".encode("gb18030"))

    assert "中文测试" in read_subtitle_text(str(path))


def test_convert_to_webvtt_passes_vtt_through(tmp_path):
    path = _touch(str(tmp_path), "movie.en.vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n")

    assert convert_to_webvtt(path).startswith("WEBVTT")


def test_convert_to_webvtt_missing_file():
    with pytest.raises(FileNotFoundError):
        convert_to_webvtt(os.path.join("Z:", "gone.srt"))


def test_convert_to_webvtt_rejects_unknown_extension(tmp_path):
    path = _touch(str(tmp_path), "movie.sub")

    with pytest.raises(SubtitleConversionError):
        convert_to_webvtt(path)


def test_convert_ass_uses_ffmpeg(tmp_path):
    path = _touch(str(tmp_path), "movie.ass", "[Events]\n")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="WEBVTT\n\n", stderr="")

    with patch("src.utils.subtitles.subprocess.run", return_value=completed) as run:
        assert convert_to_webvtt(path) == "WEBVTT\n\n"

    assert run.call_args[0][0][0] == "ffmpeg"
    assert "-f" in run.call_args[0][0]


def test_convert_ass_without_ffmpeg_raises(tmp_path):
    path = _touch(str(tmp_path), "movie.ass", "[Events]\n")

    with patch(
        "src.utils.subtitles.subprocess.run", side_effect=FileNotFoundError("ffmpeg")
    ):
        with pytest.raises(SubtitleConversionError):
            convert_to_webvtt(path)


# 本机实测的真 ffmpeg 8.x：后缀写着 `.ass`、内容却不是任何字幕时，它连文件都开不了，
# 而那句原因是它自己给的（`-loglevel error` 下 stderr 只剩这两行，退出码 183）。
FFMPEG_UNOPENABLE_STDERR = (
    "Error opening input file movie.ass.\n"
    "Error opening input files: Invalid data found when processing input\n"
)


def test_convert_ass_failure_shows_ffmpegs_own_reason(tmp_path):
    """「字幕转换失败」后面得跟着 ffmpeg 那句话——内嵌那一路一直都跟着。

    丢原因的这一头是浏览器：菜单里点了那条轨，屏幕上只有"转换失败"四个字，而这个
    人手上只有一部手机。同一件事在 `media_streams.extract_subtitle_webvtt` 里是把
    stderr 的最后一行放进消息里的，两条路因此一边能诊断、一边不能。
    """
    path = _touch(str(tmp_path), "movie.ass", "not a subtitle file at all\n")
    completed = subprocess.CompletedProcess(
        args=[], returncode=183, stdout="", stderr=FFMPEG_UNOPENABLE_STDERR
    )

    with patch("src.utils.subtitles.subprocess.run", return_value=completed):
        with pytest.raises(SubtitleConversionError) as excinfo:
            convert_to_webvtt(path)

    message = str(excinfo.value)
    assert message.startswith("字幕转换失败")
    assert "Invalid data found when processing input" in message


def test_convert_ass_failure_without_a_reason_still_says_something(tmp_path):
    """ffmpeg 不开口的时候（退出码 0 而一个字节也没转出来），那句人话得自己站住。

    这一支挡的是"把 fallback 写成空串"：消息只剩前缀，看起来仍然是失败，而读的人会
    以为是谁把日志截断了。
    """
    path = _touch(str(tmp_path), "movie.ass", "[Script Info]\n")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch("src.utils.subtitles.subprocess.run", return_value=completed):
        with pytest.raises(SubtitleConversionError) as excinfo:
            convert_to_webvtt(path)

    assert str(excinfo.value) == "字幕转换失败：这个文件没有转出任何字幕"


# 本机实测的真 ffmpeg 输出（8.x，`-f webvtt` 写 stdout）。ASS 的 `\N` 被 muxer 写成一次真的
# 换行，于是"以 `\N` 开头的台词"变成「时间戳行 + 空行 + 文本」——而空行在 WebVTT 里就是这条
# cue 的结束。界面上因此解析出一条空文本的 cue，那句词落在所有 cue 之外，一句也不显示。
FFMPEG_LEADING_BREAK = (
    "WEBVTT\n\n"
    "00:05.000 --> 00:08.000\n第一句 ONE\n\n"
    "00:10.000 --> 00:12.000\n\n第二句 TWO\n"
)


def test_convert_ass_puts_a_break_led_dialogue_back_inside_its_cue(tmp_path):
    """转换的产物必须是浏览器认得的 cue：紧跟时间戳的那个空行是 muxer 多写的。"""
    path = _touch(str(tmp_path), "movie.ass", "[Events]\n")
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=FFMPEG_LEADING_BREAK, stderr=""
    )

    with patch("src.utils.subtitles.subprocess.run", return_value=completed):
        text = convert_to_webvtt(path)

    assert "00:10.000 --> 00:12.000\n第二句 TWO" in text
    # 文件头 `WEBVTT` 后面那个空行是语法要求的，不属于任何 cue，不许被一起收掉。
    assert text.startswith("WEBVTT\n\n")


def test_convert_ass_keeps_the_separator_of_a_really_empty_cue(tmp_path):
    """台词只有 `\\N` 时那条 cue 是真空的：后面紧跟下一条时间戳，那个空行必须留着。

    少了这一句，修复可以做成"把所有空行都删掉"，而那会把两条 cue 的时间戳吞进上一条的文本里。
    """
    stdout = (
        "WEBVTT\n\n"
        "00:01.000 --> 00:02.000\n\n"
        "00:03.000 --> 00:04.000\n第二句 TWO\n"
    )
    path = _touch(str(tmp_path), "movie.ass", "[Events]\n")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    with patch("src.utils.subtitles.subprocess.run", return_value=completed):
        text = convert_to_webvtt(path)

    assert "00:01.000 --> 00:02.000\n\n00:03.000 --> 00:04.000" in text


def test_convert_srt_keeps_a_break_led_text_inside_its_cue(tmp_path):
    """同一道修复也在纯 Python 那一路：SRT 文本以空行开头时（中文 Windows 上另存过的手感）
    浏览器照样会把这条 cue 截成空的。

    夹具按 LF 写：`_touch` 走文本模式，本机落到磁盘就是 CRLF，而 `srt_to_webvtt` 第一步就把它
    折平——这里要的是"时间戳行后面紧跟一个空行"那一个形状，不是两种换行法叠出来的形状。
    """
    path = _touch(
        str(tmp_path),
        "movie.srt",
        "1\n00:00:01,000 --> 00:00:02,000\n\n第二句 TWO\n",
    )

    text = convert_to_webvtt(path)

    assert "00:00:01.000 --> 00:00:02.000\n第二句 TWO" in text
    assert text.startswith("WEBVTT\n\n")


def test_convert_leaves_the_header_separator_alone_when_nothing_parses(tmp_path):
    """`WEBVTT` 后面那个空行是语法要求的：一行 cue 都没认出来时也不许被折叠吃掉。

    这一条是真跑出来的。#140 第一版的规则只看"下一句非空文本是不是时间戳"，于是第 23 条那个没有
    BOM 的 UTF-16 文件（整份被当成 UTF-8 读、连时间戳都拼不出来）在头部就被折掉一行，红在真后端
    e2e 那句 `startsWith('WEBVTT…')` 上。所以规则多了一道闸门：走到第一条时间戳之前一律不动。
    """
    path = _touch(str(tmp_path), "movie.srt", "hello\n\nworld\n")

    assert convert_to_webvtt(path) == "WEBVTT\n\nhello\n\nworld\n"


def test_convert_vtt_stays_byte_faithful_even_with_the_same_shape(tmp_path):
    """`.vtt` 那一支不转换，所以也不修：交出去的还是盘上那份。

    这一句划的是修复的边界——本单改的是**应用自己写出来的** WebVTT，不是别人写好的文件。
    """
    body = "WEBVTT\n\n00:01.000 --> 00:02.000\n\n第二句 TWO\n"
    path = os.path.join(str(tmp_path), "movie.zh.vtt")
    # 按 LF 落盘（`newline=""`）：这个测试比的是"一个字节都不许动"，换行法不能由写入模式决定。
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(body)

    assert convert_to_webvtt(path) == body
