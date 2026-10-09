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

# How the player's menu names a language. Both subtitle sources land in one dropdown, so
# this table is shared by the embedded path (`media_streams`) and the sidecar one; keys are
# the codes ffprobe and filename suffixes actually use, which is why the 3- and 2-letter
# forms of the same language both appear.
LANGUAGE_NAMES = {
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
    stem = os.path.splitext(base)[0]

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

        suffix = _sidecar_suffix(video_filepath, entry.path)
        if suffix is None:
            continue
        if any(suffix.lower().startswith(other) for other in VIDEO_EXTENSIONS):
            # Belongs to a sibling file, e.g. movie.mkv.zh.srt next to movie.mp4
            continue

        language, label = _identity_of_suffix(suffix, stem)
        results.append(
            {
                "filepath": entry.path,
                "language": language,
                "label": label,
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


def language_display_name(code: str) -> str:
    """Name a language code the way the player's menu should show it.

    Unknown codes come back unchanged: inventing a name for a language I don't have would
    be worse than showing the suffix the person wrote themselves. A region stays visible
    because the table only knows language families — without it ``zh-CN`` and ``zh-TW``
    would be two menu entries both called 「中文」, which cannot be clicked apart.
    """
    primary, _, region = code.partition("-")
    name = LANGUAGE_NAMES.get(primary)
    if name is None:
        return code
    return f"{name}（{region.upper()}）" if region else name


def sidecar_identity(video_filepath: str, subtitle_filepath: str) -> tuple[str | None, str]:
    """The ``(language, label)`` pair a sidecar file should be registered with.

    Both write paths ask for this: the scan (through ``find_subtitle_files``) and a manual
    registration. The manual one used to slice the filename a second time, with a looser
    rule, so the same file got ``language='chi'`` by hand and ``'zh'`` by scan, and
    ``movie.mp4.zh.srt`` came out as ``mp4.zh`` in *both* columns — while ``language`` is
    ``VARCHAR(10)`` on the live database and a descriptive suffix longer than ten characters
    turned a plain registration into a 500.
    """
    stem = os.path.splitext(os.path.basename(subtitle_filepath))[0]
    suffix = _sidecar_suffix(video_filepath, subtitle_filepath)
    return _identity_of_suffix(suffix if suffix is not None else "", stem)


def _sidecar_suffix(video_filepath: str, subtitle_filepath: str) -> str | None:
    """The part of a sidecar's name between the video's stem and its extension.

    ``movie.srt`` next to ``movie.mp4`` has no suffix; ``movie.zh.srt`` has ``.zh``; and a
    video's own extension may appear a second time (``movie.mp4.zh.srt``), which is part of
    the name and not a language. ``None`` means the file is not named after this video.

    The only place a sidecar's name is sliced — the scan and a manual registration used to
    each cut it their own way, and that is where #143's four wrong labels came from.
    """
    stem, video_ext = os.path.splitext(os.path.basename(video_filepath))
    prefix = os.path.splitext(os.path.basename(subtitle_filepath))[0]
    if prefix == stem:
        return ""
    if not prefix.startswith(stem + "."):
        return None
    suffix = prefix[len(stem):]
    if suffix.lower().startswith(video_ext.lower()):
        return suffix[len(video_ext):]
    return suffix


def _identity_of_suffix(suffix: str, fallback_label: str) -> tuple[str | None, str]:
    raw = suffix.lstrip(".")
    language = _parse_language(suffix)
    if language is None:
        # A suffix that is not a language code is the name the person gave the file.
        return None, raw or fallback_label
    return language, language_display_name(language)


# A mark-less UTF-16 file has no marker to look for, but it leaves a trace: the ASCII half of
# every character -- the digits, colons and newlines that make up a cue's timestamps -- is a
# 0x00 byte, and no 8-bit subtitle encoding produces those. Measured on files shaped like
# this project's own fixtures: real UTF-16 subtitles sit at 0.35-0.50 NUL per byte, while
# GBK, UTF-8 and plain ASCII are all 0.000, and one stray 0x00 spread over a 52-byte file is
# 0.019 -- the line is drawn under the real files and well above that. A miss costs no more
# than today costs (the track reads as empty); a false hit rewrites the text of a good file,
# so the gate errs towards not guessing. The parity holding the NULs says which byte of each
# pair came first, and an odd byte count simply fails to decode -- a guess that can abstain
# needs no length gate for it. The empty file is gated only because the rate is a division.
_UTF16_NUL_RATE = 0.1


def _bomless_utf16(raw: bytes) -> str | None:
    """Decode a UTF-16 subtitle file written without a byte-order mark, or give up."""
    if not raw or raw.count(0) / len(raw) < _UTF16_NUL_RATE:
        return None
    codec = "utf-16-be" if raw[0::2].count(0) > raw[1::2].count(0) else "utf-16-le"
    try:
        return raw.decode(codec)
    except UnicodeDecodeError:
        # 这一支是猜出来的，没有 BOM 那句"我就是 UTF-16"的保证，所以猜中的字节序列照样
        # 可能读到一半断在一个孤立的高位代理上。这里宁可弃权退回原来的阶梯：这条调用挂在
        # 一条 HTTP 请求上，把异常递出去就是 500，而"读错"顶多是那条轨又是空的。
        return None


def read_subtitle_text(filepath: str) -> str:
    """Read a subtitle file, falling back to the encodings it was likely saved in."""
    with open(filepath, "rb") as handle:
        raw = handle.read()

    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    bomless = _bomless_utf16(raw)
    if bomless is not None:
        return bomless

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

    All three branches answer the same question before they return: is there a
    single cue in there? A file whose lines never parse as timestamps, a truncated
    download ffmpeg reads as ``lrc``, a `.vtt` that is only a header -- each used to
    hand back a well-formed empty WebVTT with HTTP 200, which the browser loads
    happily (``readyState`` 2, zero cues) and the player can therefore not report.
    Failing here is what makes the 415, and with it the ``<track>`` ``error`` event
    (#146), reachable at all.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".vtt":
        webvtt = read_subtitle_text(filepath)
    elif ext == ".srt":
        webvtt = fold_blank_lines_inside_cues(srt_to_webvtt(read_subtitle_text(filepath)))
    elif ext in (".ass", ".ssa"):
        webvtt = fold_blank_lines_inside_cues(_ffmpeg_to_webvtt(filepath))
    else:
        raise SubtitleConversionError(f"不支持的字幕格式: {ext}")

    if not any(_CUE_TIMESTAMP_LINE.match(line) for line in webvtt.splitlines()):
        raise SubtitleConversionError(
            f"字幕转换失败：这份文件里没有解析出任何一条字幕（{ext}）"
        )
    return webvtt


# One line of a finished WebVTT cue: "00:01:02.003 --> ..." or the
# "00:02.003 --> ..." dialect ffmpeg writes. Tells a cue separator apart from a
# stray blank line, and tells an empty conversion apart from a real one.
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


def ffmpeg_stderr_reason(stderr: str, fallback: str) -> str:
    """The last line of ffmpeg's own complaint, which is where it puts the reason.

    Shared by the two conversion paths on purpose: one of them used to drop it and
    say only "转换失败", so the same failure was diagnosable in the embedded case and
    meaningless in the sidecar one, from the browser. `fallback` is each caller's own
    sentence for "the child process said nothing".
    """
    lines = (stderr or "").strip().splitlines()
    return lines[-1] if lines else fallback


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
        raise SubtitleConversionError(
            f"字幕转换失败：{ffmpeg_stderr_reason(result.stderr, '这个文件没有转出任何字幕')}"
        )
    return result.stdout
