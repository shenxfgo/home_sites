"""FFmpeg utilities for video transcoding."""
import asyncio
import contextlib
import json
import re
import subprocess
from collections import deque
from pathlib import Path
from typing import Callable

SUPPORTED_FORMATS = {
    "mp4": {"codec": "libx264", "acodec": "aac", "ext": ".mp4"},
    # WebM rejects aac: only VP8/VP9/AV1 video and Vorbis/Opus audio are allowed.
    "webm": {"codec": "libvpx-vp9", "acodec": "libopus", "ext": ".webm"},
    "mkv": {"codec": "libx264", "acodec": "aac", "ext": ".mkv"},
    "avi": {"codec": "libx264", "acodec": "aac", "ext": ".avi"},
}

# Lines printed by `ffmpeg -progress` are `key=value` stats, not diagnostics;
# real ffmpeg errors start with a bracketed tag or prose.
_PROGRESS_KEY = re.compile(r"^\w[\w.]*=")


def _parse_ffmpeg_time(stamp: str) -> float | None:
    """Convert an ``HH:MM:SS.microseconds`` stamp into seconds."""
    try:
        hours, minutes, seconds = stamp.strip().split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (ValueError, AttributeError):
        return None


def get_video_info(filepath: str) -> dict:
    """Get video information using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            filepath,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        return {}
    except Exception:
        return {}


async def transcode_video(
    input_path: str,
    output_path: str,
    target_format: str,
    total_duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[bool, str | None]:
    """Transcode video to target format.

    Returns ``(success, error_message)``. ``on_progress`` receives the
    percentage done when the source duration is known. The process is killed
    when the surrounding task is cancelled.
    """
    format_info = SUPPORTED_FORMATS.get(target_format)
    if not format_info:
        return False, f"Unsupported format: {target_format}"

    # -progress writes machine readable key=value lines to stdout; folding
    # stderr into the same pipe keeps a single stream to drain, so ffmpeg can
    # never block on a full stderr buffer while we await stdout.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", input_path,
        "-c:v", format_info["codec"],
        "-c:a", format_info["acodec"],
        "-y",
        "-progress", "pipe:1",
        output_path,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (FileNotFoundError, OSError) as exc:
        return False, f"Failed to start ffmpeg: {exc}"

    # Keeps the tail of any non-progress output so failures can be reported.
    other_output: deque[str] = deque(maxlen=20)
    try:
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue

            # -progress prints HH:MM:SS.microseconds under out_time; the
            # out_time_ms / out_time_us keys are both microseconds, so the
            # formatted one is the safer thing to parse.
            if line.startswith("out_time="):
                if total_duration and on_progress:
                    done = _parse_ffmpeg_time(line.split("=", 1)[1])
                    if done is not None:
                        on_progress(min(done / total_duration * 100, 100.0))
            elif not _PROGRESS_KEY.match(line):
                other_output.append(line)

        returncode = await proc.wait()
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        with contextlib.suppress(OSError):
            Path(output_path).unlink(missing_ok=True)
        raise
    except Exception as exc:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        return False, str(exc)

    if returncode != 0:
        return False, " ".join(other_output) or f"ffmpeg exited with code {returncode}"
    return True, None


def check_format_support(format: str) -> bool:
    """Check if a format is supported."""
    return format.lower() in SUPPORTED_FORMATS


def get_supported_formats() -> list[dict]:
    """Get list of supported formats."""
    return [
        {"format": fmt, "codec": info["codec"], "extension": info["ext"]}
        for fmt, info in SUPPORTED_FORMATS.items()
    ]
