"""Sidecar subtitle discovery and WebVTT conversion utilities."""
import os
import re
import subprocess

from src.utils.file_scanner import VIDEO_EXTENSIONS

SUBTITLE_EXTENSIONS: set[str] = {".srt", ".ass", ".ssa", ".vtt"}

# A sidecar language suffix looks like "movie.zh.srt" or "movie.pt-BR.vtt".
_LANGUAGE_SUFFIX = re.compile(r"^\.-?[a-zA-Z]{2,3}(?:-[a-zA-Z]{2,4}|\-[0-9]{4})?$")
_TIMESTAMP_RANGE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}),(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}),(\d{3})"
)
# ISO 639 codes that subtitle files use inconsistently for the same language.
_LANGUAGE_ALIASES = {
    "chi": "zh",
    "zho": "zh",
    "eng": "en",
    "fre": "fr",
    "fra": "fr",
    "ger": "de",
    "deu": "de",
    "jpn": "ja",
    "kor": "ko",
    "spa": "es",
}


class SubtitleConversionError(Exception):
    """Raised when a subtitle file cannot be turned into WebVTT."""


def find_subtitle_files(video_filepath: str) -> list[dict]:
    """Find sidecar subtitle files belonging to a video file.

    A file is a sidecar of ``movie.mp4`` when it is named ``movie.srt``,
    ``movie.zh.srt`` or ``movie.mp4.zh.srt``.

    Returns a list of dicts with keys: filepath, language, label.
    """
    base = os.path.basename(video_filepath)
    directory = os.path.dirname(video_filepath) or "."
    stem, video_ext = os.path.splitext(base)

    try:
        entries = list(os.scandir(directory))
    except OSError:
        return []

    results: list[dict] = []
    for entry in entries:
        if not entry.is_file():
            continue
        ext = os.path.splitext(entry.name)[1].lower()
        if ext not in SUBTITLE_EXTENSIONS:
            continue
        prefix = entry.name[: -len(ext)]
        if prefix != stem and not prefix.startswith(stem + "."):
            continue

        suffix = prefix[len(stem):]
        if suffix.lower().startswith(video_ext.lower()):
            suffix = suffix[len(video_ext):]
        elif any(suffix.lower().startswith(other) for other in VIDEO_EXTENSIONS):
            # Belongs to a sibling file, e.g. movie.mkv.zh.srt next to movie.mp4
            continue

        language = _parse_language(suffix)
        results.append(
            {
                "filepath": entry.path,
                "language": language,
                "label": suffix.lstrip(".") or stem,
            }
        )

    results.sort(key=lambda item: item["filepath"])
    return results


def _parse_language(suffix: str) -> str | None:
    """Extract a BCP-47-ish language code from a sidecar filename suffix."""
    if not suffix or not _LANGUAGE_SUFFIX.match(suffix):
        return None
    code = suffix.lstrip(".").lower()
    primary, _, region = code.partition("-")
    normalized = _LANGUAGE_ALIASES.get(primary, primary)
    return f"{normalized}-{region}" if region else normalized


def read_subtitle_text(filepath: str) -> str:
    """Read a subtitle file, falling back to the encodings it was likely saved in."""
    with open(filepath, "rb") as handle:
        raw = handle.read()

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # Subtitle files edited on Chinese Windows are usually GBK/GB18030
        return raw.decode("gb18030", errors="replace")


def srt_to_webvtt(content: str) -> str:
    """Convert SRT text to WebVTT text."""
    output = ["WEBVTT", ""]
    for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = _TIMESTAMP_RANGE.match(line)
        if match:
            output.append(
                f"{match.group(1)}.{match.group(2)} --> {match.group(3)}.{match.group(4)}"
            )
            continue
        if line.strip().isdigit():
            continue
        output.append(line)
    return "\n".join(output).strip() + "\n"


def convert_to_webvtt(filepath: str) -> str:
    """Return the subtitle file as WebVTT text.

    ``<track>`` only renders WebVTT, so the other formats are converted here
    rather than served raw. A ``.vtt`` is already the browser's own format and
    stays byte-for-byte as written, defects included: only text this module
    converts gets repaired.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".vtt":
        return read_subtitle_text(filepath)
    if ext == ".srt":
        return fold_blank_lines_inside_cues(srt_to_webvtt(read_subtitle_text(filepath)))
    if ext in (".ass", ".ssa"):
        return fold_blank_lines_inside_cues(_ffmpeg_to_webvtt(filepath))
    raise SubtitleConversionError(f"不支持的字幕格式: {ext}")


# One line of a finished WebVTT cue: "00:01:02.003 --> ..." or the
# "00:02.003 --> ..." dialect ffmpeg writes. Tells a cue separator apart from a
# stray blank line.
_CUE_TIMESTAMP_LINE = re.compile(
    r"^\s*(?:\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->"
)


def fold_blank_lines_inside_cues(webvtt: str) -> str:
    """Fold the blank lines a converter wrote *inside* a cue back into its text.

    ffmpeg's WebVTT muxer turns an ASS ``\\N`` into a literal newline, so a
    dialogue starting with ``\\N`` comes out as a timestamp line, a blank line,
    then the text. A blank line ends a WebVTT cue, so the browser parses an
    empty cue and drops the stranded sentence: the subtitle looks selected but
    shows nothing. The pure-Python SRT path can hand back the same shape.

    Two things keep the fold honest:

    * A blank run is only folded when the next non-blank line is not itself a
      timestamp line -- a genuinely empty cue keeps its separator, otherwise the
      next cue's timestamp would be swallowed as text.
    * Nothing before the first timestamp line is touched. That region is the
      ``WEBVTT`` header (and an optional cue identifier), not cue text, and its
      blank line is required syntax.
    """
    lines = webvtt.split("\n")
    kept: list[str] = []
    past_header = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip():
            past_header = past_header or bool(_CUE_TIMESTAMP_LINE.match(line))
            kept.append(line)
            index += 1
            continue
        next_text = index
        while next_text < len(lines) and not lines[next_text].strip():
            next_text += 1
        following = lines[next_text] if next_text < len(lines) else ""
        if past_header and following and not _CUE_TIMESTAMP_LINE.match(following):
            index = next_text
            continue
        kept.append(line)
        index += 1
    return "\n".join(kept)


def _ffmpeg_to_webvtt(filepath: str) -> str:
    """Convert an SSA/ASS subtitle to WebVTT with ffmpeg."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                filepath,
                "-f",
                "webvtt",
                "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise SubtitleConversionError(f"字幕转换失败: {exc}") from exc

    if result.returncode != 0 or not (result.stdout or "").strip():
        raise SubtitleConversionError("字幕转换失败")
    return result.stdout
