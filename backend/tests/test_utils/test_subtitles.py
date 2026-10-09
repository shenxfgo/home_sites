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
    assert by_name["movie.zh-CN.srt"]["label"] == "中文（CN）"
    assert by_name["movie.chi.srt"]["language"] == "zh"
    assert by_name["movie.chi.srt"]["label"] == "中文"
    # Non-ASCII suffixes are kept as the label but are not valid language tags
    assert by_name["movie.中文.srt"]["language"] is None
    assert by_name["movie.中文.srt"]["label"] == "中文"


def test_find_subtitle_files_labels_a_sidecar_the_way_the_menu_reads_it(tmp_path):
    """同一个字幕菜单里，内嵌那条叫「中文」，外挂这条不能叫 `chi`。

    `media_streams` 那张名字表一直把 ffprobe 的语言标签翻成中文（第 21 条钉的是界面上点
    「中文」这一格），而 sidecar 的 `label` 存的是文件名后缀的原文，于是两条来源的轨在同一个
    下拉里一边中文、一边英文代码。真库现在就躺着一行 `label='en'`，也就是用户自己打开播放页
    看到的那一格。
    """
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.chi.srt")
    _touch(str(tmp_path), "movie.eng.srt")
    _touch(str(tmp_path), "movie.jpn.ass")

    by_name = {
        os.path.basename(s["filepath"]): s for s in find_subtitle_files(video)
    }
    names = ("movie.chi.srt", "movie.eng.srt", "movie.jpn.ass")

    assert [by_name[name]["label"] for name in names] == ["中文", "英文", "日文"]
    # `language` 存的仍是归一化后的代码，不是界面上的名字：那是 `srclang` 的出处。
    assert [by_name[name]["language"] for name in names] == ["zh", "en", "ja"]


def test_sidecar_label_keeps_an_unknown_language_code_as_is(tmp_path):
    """名字表里没有的代码不能编出一个名字，更不能丢掉后缀里的信息。

    这一条挡的是"把未知代码一律显示成 `未知语言`"那种写法——那个人知道自己片子叫什么，
    而我不知道。
    """
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.nor.srt")

    found = find_subtitle_files(video)

    assert found[0]["language"] == "nor"
    assert found[0]["label"] == "nor"


def test_sidecar_label_of_a_region_keeps_the_region(tmp_path):
    """`zh-CN` 和 `zh-TW` 不能都显示成「中文」。

    一部片子的简中和繁中两条字幕在菜单里变成同一个名字，就再也点不开了——名字表只认到
    语族，所以地区得由显示名字自己带下去。
    """
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.zh-CN.srt")
    _touch(str(tmp_path), "movie.zh-TW.srt")

    by_name = {
        os.path.basename(s["filepath"]): s for s in find_subtitle_files(video)
    }

    assert by_name["movie.zh-CN.srt"]["label"] == "中文（CN）"
    assert by_name["movie.zh-TW.srt"]["label"] == "中文（TW）"


def test_sidecar_with_no_language_suffix_is_labelled_by_the_video_stem(tmp_path):
    """`movie.srt` 挂在 `movie.mp4` 旁边：没有后缀可认，名字就用影片自己的主干名。

    这一格改修前后都是同一个结果（#143 动的是"有后缀"那一半），留着是因为它是兜底那一步唯一的
    钉子：`_identity_of_suffix` 一旦连兜底也交给名字表，菜单里那一条就会变成空格。
    """
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.srt")

    found = find_subtitle_files(video)

    assert (found[0]["language"], found[0]["label"]) == (None, "movie")


def test_find_subtitle_files_supports_fullname_sidecars(tmp_path):
    video = _touch(str(tmp_path), "movie.mp4")
    _touch(str(tmp_path), "movie.mp4.zh.srt")

    found = find_subtitle_files(video)

    assert found[0]["language"] == "zh"
    assert found[0]["label"] == "中文"


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
    # 那份假产物里真的写着一条 cue：转换结果一条 cue 也没有的话，现在轮不到这句"成功"了（#187）。
    stdout = "WEBVTT\n\n00:05.000 --> 00:08.000\n第一句 ONE\n"
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    with patch("src.utils.subtitles.subprocess.run", return_value=completed) as run:
        assert convert_to_webvtt(path) == stdout

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


def test_convert_keeps_the_header_separator_of_a_file_that_has_a_cue(tmp_path):
    """`WEBVTT` 后面那个空行是语法要求的：修复只许动 cue 内部的那些空行。

    这一条是真跑出来的。#140 第一版的规则只看"下一句非空文本是不是时间戳"，于是那个连时间戳都拼
    不出来的文件在头部就被折掉一行，红在真后端 e2e 那句 `startsWith('WEBVTT…')` 上。所以规则多了
    一道闸门：走到第一条时间戳之前一律不动。

    原来这一格钉的是一份**没有 cue** 的文件（`hello\\n\\nworld`），因为那时那样的文件照样交得出去。
    #187 之后它归 415 管，于是这句头部规则改对着一份有 cue、文本行前面也有空行的形状钉——闸门
    本身一个字没动。
    """
    path = _touch(
        str(tmp_path),
        "movie.srt",
        "hello\n\n1\n00:00:01,000 --> 00:00:02,000\n第二句 TWO\n",
    )

    text = convert_to_webvtt(path)

    assert text.startswith("WEBVTT\n\nhello\n\n")
    assert "00:00:01.000 --> 00:00:02.000\n第二句 TWO" in text


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


# --- 零条 cue 的转换算失败（#187，第二块选项板⑧子问一乙 + 子问二甲）---


def test_convert_a_sidecar_that_parses_into_no_cue_fails(tmp_path):
    """一句 cue 都没解析出来的那份文件，不能再交出一份"合法但空"的 WebVTT 当作成功。

    这是本单的正门：以前这条路回 200、`WEBVTT` 后面什么都没有，浏览器把那条轨加载完（`readyState`
    2）、cue 清单是空的、菜单照常可点——**它自己完全不觉得有事**，界面上因此没有任何东西可说
    （真后端 e2e 第 22 条第 6 步曾经把这个形状钉成现状）。现在失败在转换这一次调用上就发生，
    接口那句 415 因此和 `<track>` 那个 `error` 事件是同一个来处。
    """
    path = _touch(str(tmp_path), "movie.srt", "hello\n\nworld\n")

    with pytest.raises(SubtitleConversionError) as excinfo:
        convert_to_webvtt(path)

    assert "没有解析出任何一条字幕" in str(excinfo.value)


def test_convert_a_vtt_with_no_cue_fails_too(tmp_path):
    """⑧子问一甲：`.vtt` 那一支也算 cue——直通的是**转换**，不是"这道闸门"。

    这一格划的就是边界在哪儿：字节一个不许动（上一条），和"这份文件里到底有没有一句字幕"是两件
    事。别人写好的 WebVTT 长得再难看也照原样交出去，但一份只有头的 `.vtt` 交出去，浏览器那一头
    拿到的还是零条 cue，跟上一条那个洞一模一样。
    """
    path = _touch(str(tmp_path), "movie.zh.vtt", "WEBVTT\n\n这一句不是时间戳\n")

    with pytest.raises(SubtitleConversionError):
        convert_to_webvtt(path)


def test_convert_an_ass_that_ffmpeg_turned_into_nothing_fails(tmp_path):
    """ffmpeg 那句"转换成功"只剩一个头时，退出码 0 不算数。

    这一份 stdout 就是真 ffmpeg 8.x 对着"只有 `[Events]`、没有 `[Script Info]`"那种 ASS 吐出来的
    东西（真后端 e2e 第 22 条那个截断夹具），本机实测：容器被认成 `lrc`，退出码 0，`WEBVTT`
    后面一个 cue 都没有。`_ffmpeg_to_webvtt` 那一头挡的是**空 stdout**，这一头挡的是非空的空壳。
    """
    path = _touch(str(tmp_path), "movie.ass", "[Events]\n")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="WEBVTT\n\n", stderr="")

    with patch("src.utils.subtitles.subprocess.run", return_value=completed):
        with pytest.raises(SubtitleConversionError) as excinfo:
            convert_to_webvtt(path)

    # 后缀跟着走出来：同一条 415 在三种格式上说的是三件不同的事，读的人得能分辨。
    assert ".ass" in str(excinfo.value)


# --- 没有 BOM 的 UTF-16（#186，第二块选项板⑧子问二乙）---

_UTF16_SRT = (
    "1\r\n00:00:01,000 --> 00:00:03,000\r\n第一句字幕 ONE\r\n\r\n"
    "2\r\n00:00:04,000 --> 00:00:06,000\r\n第二句字幕 TWO\r\n\r\n"
)


def test_a_bomless_utf16le_sidecar_keeps_its_cues(tmp_path):
    """⑧c：这一份里真的写着两句话——认不出编码却"成功"，比报错糟糕得多。

    UTF-16LE 的字节两两一组，ASCII 那半个全是 0x00，而 0x00 是**合法**的 UTF-8，所以
    `decode("utf-8")` 从不抛、gb18030 那道兜底压根不会触发。带 NUL 的时间戳行匹配不上
    `_TIMESTAMP_RANGE`、序号行也过不了 `isdigit()`，两个过滤器白跑一遍，交出去的是一份合法
    VTT 头加一串谁都不认得的东西，状态码仍然是 200。
    """
    path = tmp_path / "movie.chi.srt"
    path.write_bytes(_UTF16_SRT.encode("utf-16-le"))
    assert not path.read_bytes().startswith(b"\xff\xfe"), "这一条要的就是没有 BOM"

    text = convert_to_webvtt(str(path))

    assert "00:00:01.000 --> 00:00:03.000\n第一句字幕 ONE" in text
    assert "00:00:04.000 --> 00:00:06.000\n第二句字幕 TWO" in text
    assert "\x00" not in text


def test_a_bomless_utf16be_sidecar_keeps_its_cues(tmp_path):
    """大尾那一头：0x00 落在偶数下标上，同一份文本、另一个方向。"""
    path = tmp_path / "movie.chi.srt"
    path.write_bytes(_UTF16_SRT.encode("utf-16-be"))

    text = convert_to_webvtt(str(path))

    assert "00:00:01.000 --> 00:00:03.000\n第一句字幕 ONE" in text
    assert "\x00" not in text


def test_a_utf8_file_with_a_stray_nul_is_not_promoted_to_utf16(tmp_path):
    """NUL 率那道闸门挡的是"一个漏进去的 0x00 就换掉一整份编码"。

    这一格不是洁癖：真按"哪个下标有 NUL"判，一个混进单个 NUL 的 UTF-8 文件会被整份拆成
    UTF-16，中文全变成生僻字——比原来那句错更难看得多。补的那一个 NUL 把长度凑成偶数，于是
    这一格只剩 NUL 率这一道闸门在挡。实测分界很宽：真 UTF-16 的字幕在 0.35~0.50，
    GBK / UTF-8 / 纯 ASCII 一律 0.000，单个漏进的 NUL 摊到 52 字节上是 0.019。
    """
    raw = "00:00:01,000 --> 00:00:02,000\r\n正常的一句话\r\n".encode("utf-8")
    assert len(raw) % 2 == 1, "这一格要的是补上 NUL 之后正好凑成偶数"
    path = tmp_path / "movie.chi.srt"
    path.write_bytes(raw + b"\x00")

    text = read_subtitle_text(str(path))

    assert "正常的一句话" in text, "按 UTF-16 读这份文件会把它整句拆成别的字"
    assert text.count("\x00") == 1


def test_an_empty_sidecar_still_reads_as_nothing(tmp_path):
    """0 字节的那一份是这条阶梯上最短的输入：猜测那一支唯一的长度闸门是它的除法保护。

    猜编码要先算 NUL 率，而 NUL 率是一次除法——空文件摊到这里分母是 0，`ZeroDivisionError`
    从一条 HTTP 请求上出去就是 500。一个 0 字节的 `.srt` 不是假设：下载断在半路、编辑器建了
    个空文件都会留下它，而扫描只看文件名，会照样把它登记成一条轨道。

    #187 之后它的下场是 415 而不是 200，但这两句得**同时**成立：读这一层不许抛（所以那句
    `read_subtitle_text == ""` 留着），而失败要说得出口（所以这一格钉的是 `SubtitleConversionError`
    而不是随便一个异常——`ZeroDivisionError` 逃出来时这一格同样会红）。
    """
    path = tmp_path / "movie.chi.srt"
    path.write_bytes(b"")

    assert read_subtitle_text(str(path)) == ""

    with pytest.raises(SubtitleConversionError):
        convert_to_webvtt(str(path))


def test_a_truncated_utf16_file_raises_nothing_but_the_honest_failure(tmp_path):
    """奇数字节（写到一半断的）不是 UTF-16 的合法长度：可以读错，不许抛。

    `convert_to_webvtt` 挂在一条 HTTP 请求上，`UnicodeDecodeError` 从这儿出去就是 500。#187 之后
    这一份的下场从"200 而零条 cue"换成 415，而弃权那一步和零 cue 那道闸门是两句各自独立的话：
    前面这一句管的是异常出不去，后面这一句管的是它不该成功时不装成功。
    """
    path = tmp_path / "movie.chi.srt"
    path.write_bytes(_UTF16_SRT.encode("utf-16-le") + b"\x00")

    with pytest.raises(SubtitleConversionError):
        convert_to_webvtt(str(path))


def test_a_bomless_utf16_guess_with_a_broken_tail_raises_nothing(tmp_path):
    """猜进来之后读到一半断了：偶数、NUL 率也够，尾部那半个代理码位把 `decode` 打断。

    尾部那 `\\x00\\xd8` 是一个只有一半的高位代理（U+D800 后面没有配对的低位），`decode`
    在这儿直接抛 `UnicodeDecodeError: unexpected end of data`。唯一那道判据——NUL 率过阈值
    ——它**过了**，所以这一格钉的是猜测那一支自己的弃权：猜出来的编码没有 BOM 那句"我就是
    UTF-16"的保证，猜错就必须退回原来的阶梯，而不是把异常递出去变成 500。上一条奇数字节的
    测试走的是同一道弃权，只是断在另一个地方——长度对不上，编到最后一组少一个字节。

    两条现在都收在 415 上（#187）：这一格断言的仍然是**那一个类型**，异常换成 `UnicodeDecodeError`
    就红，所以弃权没有被新的闸门吃掉。
    """
    raw = _UTF16_SRT.encode("utf-16-le") + b"\x00\xd8"
    assert len(raw) % 2 == 0, "这一格要的就是长度闸门拦不住"
    assert raw.count(0) / len(raw) > 0.1, "这一格要的就是 NUL 率闸门也拦不住"

    path = tmp_path / "movie.chi.srt"
    path.write_bytes(raw)

    with pytest.raises(SubtitleConversionError):
        convert_to_webvtt(str(path))
