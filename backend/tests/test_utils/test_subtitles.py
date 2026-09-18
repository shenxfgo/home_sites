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
