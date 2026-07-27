"""FFmpeg utilities for video transcoding."""
import subprocess
import json
import os
from pathlib import Path

SUPPORTED_FORMATS = {
    "mp4": {"codec": "libx264", "ext": ".mp4"},
    "webm": {"codec": "libvpx-vp9", "ext": ".webm"},
    "mkv": {"codec": "libx264", "ext": ".mkv"},
    "avi": {"codec": "libx264", "ext": ".avi"},
}


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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {}
    except Exception:
        return {}


def transcode_video(input_path: str, output_path: str, target_format: str) -> bool:
    """Transcode video to target format."""
    if target_format not in SUPPORTED_FORMATS:
        return False

    format_info = SUPPORTED_FORMATS[target_format]

    try:
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", format_info["codec"],
            "-c:a", "aac",
            "-y",  # Overwrite output
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=3600)  # 1 hour timeout
        return result.returncode == 0
    except Exception:
        return False


def check_format_support(format: str) -> bool:
    """Check if a format is supported."""
    return format.lower() in SUPPORTED_FORMATS


def get_supported_formats() -> list[dict]:
    """Get list of supported formats."""
    return [
        {"format": fmt, "codec": info["codec"], "extension": info["ext"]}
        for fmt, info in SUPPORTED_FORMATS.items()
    ]
