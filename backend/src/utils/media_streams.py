"""Embedded stream discovery for subtitle and audio tracks inside a container.

Matroska files often carry their subtitles inside the video itself. Browsers
cannot render those tracks, so they are listed here and turned into WebVTT on
request by :func:`extract_subtitle_webvtt` — nothing is written to disk.
"""
import json
import os
import subprocess

from src.utils.subtitles import SubtitleConversionError

# Codecs whose cues ffmpeg can hand straight to the WebVTT muxer. Anything else
# (PGS, DVD and DVB bitmaps) is a picture, and a picture cannot be re-timed.
WEBVTT_CODECS: set[str] = {"subrip", "ass", "ssa", "mov_text", "webvtt", "text"}

# ISO 639-2/T codes ffprobe reports for the tracks people actually ship.
_LANGUAGE_NAMES = {
    "chi": "中文",
    "zho": "中文",
    "zh": "中文",
    "eng": "英文",
    "en": "英文",
    "jpn": "日文",
    "ja": "日文",
    "kor": "韩文",
    "ko": "韩文",
    "fra": "法文",
    "fre": "法文",
    "fr": "法文",
    "deu": "德文",
    "ger": "德文",
    "de": "德文",
    "spa": "西班牙文",
    "es": "西班牙文",
    "rus": "俄文",
    "ru": "俄文",
    "yue": "粤语",
    "pt": "葡萄牙文",
    "it": "意大利文",
}


class StreamNotFound(Exception):
    """Raised when a requested stream index is not in the file."""


def _run_ffprobe(filepath: str) -> dict:
    """Return ffprobe's JSON for a media file, or ``{}`` when it cannot be read."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                filepath,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}

    if result.returncode != 0 or not result.stdout:
        return {}
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {}


def _language_of(stream: dict) -> str | None:
    """Read the track's language tag, if the packager set one."""
    tags = stream.get("tags") or {}
    code = tags.get("language") or tags.get("LANGUAGE")
    if not code:
        return None
    code = code.strip().lower()
    return None if code in {"und", "xxx", ""} else code


def _label_of(stream: dict, position: int) -> str:
    """Name a track the way the player's menu should show it."""
    tags = stream.get("tags") or {}
    title = tags.get("title") or tags.get("TITLE")
    if title:
        return title.strip()
    language = _language_of(stream)
    if language:
        return _LANGUAGE_NAMES.get(language, language)
    return f"轨道 {position + 1}"


def probe_streams(filepath: str) -> dict:
    """List the subtitle and audio tracks carried inside a media file.

    ``probed`` is False when ffprobe could not read the file — a share that is
    unmounted looks the same to the player as a file with no tracks, but the UI
    can say something different about it.
    """
    info = _run_ffprobe(filepath)
    streams = info.get("streams") or []

    subtitles: list[dict] = []
    audio: list[dict] = []
    for position, stream in enumerate(
        [item for item in streams if item.get("codec_type") == "subtitle"]
    ):
        codec = (stream.get("codec_name") or "").lower()
        subtitles.append(
            {
                "stream_index": stream.get("index", position),
                "position": position,
                "codec": codec,
                "language": _language_of(stream),
                "label": _label_of(stream, position),
                "supported": codec in WEBVTT_CODECS,
            }
        )
    for position, stream in enumerate(
        [item for item in streams if item.get("codec_type") == "audio"]
    ):
        disposition = stream.get("disposition") or {}
        audio.append(
            {
                "stream_index": stream.get("index", position),
                "position": position,
                "codec": (stream.get("codec_name") or "").lower(),
                "language": _language_of(stream),
                "label": _label_of(stream, position),
                "default": bool(disposition.get("default")),
            }
        )

    return {
        "probed": bool(streams),
        "container": (info.get("format") or {}).get("format_name"),
        "subtitles": subtitles,
        "audio": audio,
    }


def extract_subtitle_webvtt(filepath: str, stream_index: int) -> str:
    """Pull one embedded subtitle track out of the file as WebVTT text.

    The muxer writes to stdout, so the video file is only ever read.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)

    info = _run_ffprobe(filepath)
    wanted = {
        stream.get("index")
        for stream in (info.get("streams") or [])
        if stream.get("codec_type") == "subtitle"
    }
    if stream_index not in wanted:
        raise StreamNotFound(f"文件里没有编号为 {stream_index} 的字幕轨")

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                filepath,
                "-map",
                f"0:{stream_index}",
                "-c:s",
                "webvtt",
                "-f",
                "webvtt",
                "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise SubtitleConversionError(f"内嵌字幕提取失败: {exc}") from exc

    if result.returncode != 0 or not (result.stdout or "").strip():
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "该轨无法转成 WebVTT"
        raise SubtitleConversionError(f"内嵌字幕提取失败：{reason}")
    return result.stdout
