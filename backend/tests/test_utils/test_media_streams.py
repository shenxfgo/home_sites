"""Tests for the embedded stream probe and WebVTT extraction."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.utils.media_streams import (
    StreamNotFound,
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
    """Stand in for subprocess.run, returning one canned result per call."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        return self.results.pop(0)


def _probe():
    return SimpleNamespace(returncode=0, stdout=json.dumps(PROBE_RESULT), stderr="")


def _stdout(text):
    return SimpleNamespace(returncode=0, stdout=text, stderr="")


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


def test_extract_refuses_a_stream_that_is_not_a_subtitle(tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"matroska")

    fake = FakeRun(_probe())
    with patch("src.utils.media_streams.subprocess.run", fake):
        with pytest.raises(StreamNotFound):
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
