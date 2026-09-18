"""File scanning utilities for discovering video files on disk."""
import json
import os
import subprocess
from pathlib import Path

VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
}


def scan_directory(path: str) -> list[dict]:
    """Recursively scan a directory for video files.

    Returns a list of dicts with keys: filepath, filename, extension, file_size.
    """
    results: list[dict] = []
    root = Path(path)
    if not root.is_dir():
        return results

    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                filepath = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(filepath)
                    file_size = stat.st_size
                except OSError:
                    continue
                results.append(
                    {
                        "filepath": filepath,
                        "filename": filename,
                        "extension": ext,
                        "file_size": file_size,
                    }
                )
    return results


def extract_video_info(filepath: str) -> dict:
    """Extract video metadata using ffprobe.

    Returns a dict with keys: duration, resolution, format.
    Falls back to defaults if ffprobe is unavailable.
    """
    info: dict = {
        "duration": None,
        "resolution": None,
        "format": None,
    }

    ext = os.path.splitext(filepath)[1].lower().lstrip(".")
    info["format"] = ext if ext else None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                filepath,
            ],
            capture_output=True,
            text=True,
            # ffprobe 输出含 UTF-8 文件名；按系统区域编码（如 cp936）解码会抛
            # UnicodeDecodeError 并使 stdout 变成 None
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout:
            return info

        probe = json.loads(result.stdout)

        # Extract duration
        if "format" in probe and "duration" in probe["format"]:
            try:
                info["duration"] = int(float(probe["format"]["duration"]))
            except (ValueError, KeyError):
                pass

        # Extract resolution from first video stream
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                if width and height:
                    info["resolution"] = f"{width}x{height}"
                break

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        pass

    return info


def generate_thumbnail(video_path: str, output_path: str) -> str:
    """Generate a thumbnail from a video file using ffmpeg.

    Returns the output_path on success, empty string on failure.
    """
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-ss", "00:00:01",
                "-vframes", "1",
                "-vf", "scale=320:-1",
                output_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""
