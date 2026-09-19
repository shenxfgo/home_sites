"""Turn a video filename into a series, a season and an episode number.

Only the filename is looked at, never the file contents, so the parse stays
cheap enough to run inside the scan loop. Anything it cannot recognise comes
back as a cleaned title rather than a guess: a wrong title costs more than a
verbose one.
"""
import re
from dataclasses import dataclass

_JUNK = re.compile(
    r"""(?ix)
    (?<![a-z0-9])(?:
        \d{3,4}p | 4k
      | x26[45] | h[\.\-]?26[45] | hevc | avc | hdr1?[+]?
      | (?:10|8)[\.\-]?bit
      | web[\.\-]?(?:rip|dl) | webrip
      | blu[\.\-]?ray | bdrip | brrip | dvdrip | hdtv | hdcam | cam
      | screener | scr | ts
      | aac\d? | ac3 | eac3 | dts[\.\-]?hd | dd[\.\-]?5[.]1 | ddp?
      | rep | remux | proper | internal | limited | unrated | uncensored
    )(?:[\s._\-]+|$)
    """
)

_BRACKET = re.compile(r"[\[【(（]([^\]】)）]*)[\]】)）]")

# Ordered by how unambiguous the marker is.
_EPISODE_PATTERNS = (
    re.compile(r"(?i)(?<![a-z0-9])s(?P<season>\d{1,2})[\s._\-]*e(?P<episode>\d{1,3})(?![0-9])"),
    re.compile(r"(?i)第\s*(?P<episode>\d{1,4})\s*[集话話期]"),
    re.compile(r"(?i)(?<![a-z])episode[\s._\-]*(?P<episode>\d{1,3})(?![0-9])"),
    re.compile(r"(?i)(?<![a-z])ep[\s._\-]*(?P<episode>\d{1,3})(?![0-9])"),
    re.compile(r"(?i)(?<![a-z])part[\s._\-]*(?P<episode>\d{1,3})(?![0-9])"),
    re.compile(r"(?i)(?<![a-z0-9])(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?![0-9])"),
)

_EXTENSION = re.compile(r"(?i)\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|mpg|mpeg|ts)$")

_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")


@dataclass(frozen=True)
class ParsedName:
    """What a filename yields: a display title plus the series coordinates."""

    title: str
    series: str | None = None
    season: int | None = None
    episode: int | None = None
    group: str | None = None

    @property
    def episode_label(self) -> str | None:
        """The short badge the UI shows, e.g. ``S01E02`` or ``第12集``."""
        if self.episode is None:
            return None
        if self.season is not None:
            return f"S{self.season:02d}E{self.episode:02d}"
        return f"第{self.episode}集"


def parse_video_filename(filename: str) -> ParsedName:
    """Parse a video file name, with or without its extension."""
    stem = _EXTENSION.sub("", filename.strip())
    group = _find_group(stem)
    cleaned = _clean(stem)
    if not cleaned:
        return ParsedName(title=stem.strip(), group=group)

    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        series = _trim(cleaned[: match.start()])
        episode = _number(match, "episode")
        if not series or episode is None:
            continue

        has_season = "season" in match.groupdict()
        season = _number(match, "season") if has_season else None
        label = (
            f"S{season or 1:02d}E{episode:02d}"
            if has_season
            else f"第{episode}集"
        )
        return ParsedName(
            title=f"{series} {label}",
            series=series,
            season=season if season is not None else (1 if has_season else None),
            episode=episode,
            group=group,
        )

    return ParsedName(title=cleaned, group=group)


def auto_tags(parsed: ParsedName) -> tuple[str, ...]:
    """Tags worth creating for a parsed name: the series first, then the group."""
    return tuple(name for name in (parsed.series, parsed.group) if name)


def _find_group(stem: str) -> str | None:
    """The publisher or 字幕组 a release carries in its first real bracket."""
    for content in _BRACKET.findall(stem):
        candidate = _trim(content.strip(" -_"))
        if not candidate or candidate.isdigit():
            continue
        if _JUNK.fullmatch(candidate):
            continue
        if len(candidate) > 30:
            continue
        # A two letter bracket is a region marker — (US), (JP) — not a group.
        if re.fullmatch(r"(?i)[a-z]{2}", candidate):
            continue
        if re.search(r"[A-Za-z\u4e00-\u9fff]", candidate):
            return candidate
    return None


def _clean(stem: str) -> str:
    """Drop brackets, release junk and separator noise."""
    text = _BRACKET.sub(" ", stem)
    text = _JUNK.sub(" ", text)
    # A dot between digits is a decimal point, not a word separator.
    text = _DECIMAL.sub("\x00", text)
    text = re.sub(r"[._\-–—+~&,]+", " ", text)
    return _trim(text.replace("\x00", "."))


def _trim(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" :")


def _number(match: re.Match, name: str) -> int | None:
    try:
        return int(match.group(name))
    except (IndexError, ValueError, TypeError):
        return None
