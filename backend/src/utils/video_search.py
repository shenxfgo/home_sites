"""Parsing of the search box into structured video query conditions.

The home page exposes one text field, so the filters a user can reach are
exactly what this module can express. Anything it does not recognise stays a
plain keyword, which keeps values like ``16:9`` and ``http://x`` searchable as
text instead of silently disappearing into an unknown operator.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: ``key:value`` filters. The colon may be ASCII or full width.
NAME_KEYS = {
    "源": "source",
    "视频源": "source",
    "source": "source",
    "标签": "tag",
    "tag": "tag",
}

#: Standalone words that select a playback state.
WATCH_STATES = {
    "没看过": "never",
    "未看完": "unfinished",
    "已看完": "finished",
}

#: Keys accepted in front of a comparison operator.
COMPARISON_KEYS = {
    "评分": "rating",
    "rating": "rating",
    "时长": "duration",
    "长度": "duration",
    "duration": "duration",
}

#: Unit suffixes for a duration literal.
DURATION_UNITS = {
    "小时": 3600,
    "分钟": 60,
    "秒": 1,
    "h": 3600,
    "min": 60,
    "m": 60,
    "s": 1,
}

OPERATORS = {">=": ">=", "≥": ">=", "<=": "<=", "≤": "<=", ">": ">", "<": "<", "=": "="}

_OPERATOR_SOURCE = "|".join(re.escape(op) for op in (">=", "<=", "≥", "≤", ">", "<", "="))
_NAME_KEY_SOURCE = "|".join(NAME_KEYS)
_COMPARISON_KEY_SOURCE = "|".join(COMPARISON_KEYS)

_TOKEN = re.compile(r'"([^"]+)"|(\S+)')
_NAME_INLINE = re.compile(rf"^(?P<key>{_NAME_KEY_SOURCE})[:：](?P<value>\S.*)$", re.IGNORECASE)
_NAME_BARE = re.compile(rf"^(?P<key>{_NAME_KEY_SOURCE})[:：]$", re.IGNORECASE)
_COMPARISON = re.compile(
    rf"^(?:(?P<key>{_COMPARISON_KEY_SOURCE})\s*)?(?P<op>{_OPERATOR_SOURCE})\s*(?P<value>\S+)$",
    re.IGNORECASE,
)
_STANDALONE_COMPARISON = re.compile(
    rf"^(?:(?P<key>{_COMPARISON_KEY_SOURCE})|(?P<op>{_OPERATOR_SOURCE}))$",
    re.IGNORECASE,
)
_DURATION_VALUE = re.compile(r"^(?P<number>\d+(?:\.\d+)?)(?P<unit>[^\d\s.]+)$")
_INTEGER = re.compile(r"^\d+$")


@dataclass(frozen=True)
class VideoSearchQuery:
    """What the user asked for, split into the parts a query can act on."""

    terms: tuple[str, ...] = ()
    source_name: str | None = None
    tag_name: str | None = None
    rating: tuple[str, int] | None = None
    duration: tuple[str, int] | None = None
    watch_state: str | None = None

    @property
    def has_conditions(self) -> bool:
        """Whether anything was understood, so an empty box is not a filter."""
        return bool(
            self.terms
            or self.source_name
            or self.tag_name
            or self.rating
            or self.duration
            or self.watch_state
        )


def parse_video_search(text: str | None) -> VideoSearchQuery:
    """Turn raw search box text into a :class:`VideoSearchQuery`.

    Terms combine with AND and are matched by the service against the title,
    the description and the tag names. ``"quoted text"`` keeps a phrase in one
    term; spaces around ``:`` and around an operator are ignored, so
    ``标签: 悬疑`` and ``评分 >= 4`` parse as intended.
    """
    tokens = [
        {"text": quoted or bare, "quoted": bool(quoted)}
        for quoted, bare in _TOKEN.findall(text or "")
    ]
    terms: list[str] = []
    fields: dict[str, object] = {}

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token["quoted"]:
            terms.append(token["text"])
            index += 1
            continue

        text_of_token = token["text"].strip('"')
        if not text_of_token:
            index += 1
            continue

        consumed = _consume(text_of_token, tokens, index, fields)
        if consumed is None:
            terms.append(text_of_token)
            index += 1
        else:
            index = consumed

    return VideoSearchQuery(
        terms=tuple(terms),
        source_name=_as_optional_str(fields.get("source")),
        tag_name=_as_optional_str(fields.get("tag")),
        rating=_as_pair(fields.get("rating")),
        duration=_as_pair(fields.get("duration")),
        watch_state=_as_optional_str(fields.get("watch_state")),
    )


def _consume(token: str, tokens: list[dict], index: int, fields: dict[str, object]) -> int | None:
    """Read one filter out of ``token`` (plus lookahead), or None if it is a keyword."""
    if token in WATCH_STATES:
        fields["watch_state"] = WATCH_STATES[token]
        return index + 1

    inline = _NAME_INLINE.match(token)
    if inline:
        fields[NAME_KEYS[inline.group("key").lower()]] = inline.group("value").strip().strip('"')
        return index + 1

    bare = _NAME_BARE.match(token)
    if bare and index + 1 < len(tokens):
        following = tokens[index + 1]["text"].strip('"')
        if following:
            fields[NAME_KEYS[bare.group("key").lower()]] = following
            return index + 2
        return None

    if not _STANDALONE_COMPARISON.match(token):
        position = _assign_comparison(token, index + 1, fields, require_key=False)
        return position or None
    return _consume_comparison(token, tokens, index, fields)


def _consume_comparison(
    token: str, tokens: list[dict], index: int, fields: dict[str, object]
) -> int | None:
    """Absorb a key, operator and value that the user split with spaces."""
    buffer = token
    position = index + 1
    while position < len(tokens) and not tokens[position]["quoted"]:
        following = tokens[position]["text"].strip('"')
        if not _looks_like_comparison_tail(buffer, following):
            break
        buffer += following
        position += 1
        if _COMPARISON.match(buffer):
            break

    result = _assign_comparison(buffer, position, fields, require_key=token not in OPERATORS)
    return result or None


def _looks_like_comparison_tail(buffer: str, following: str) -> bool:
    if following in OPERATORS:
        return following not in buffer
    return bool(following) and (following[0].isdigit() or following[0] == ".")


def _assign_comparison(
    candidate: str, position: int, fields: dict[str, object], require_key: bool
) -> int:
    """Store a parsed comparison, returning ``position`` or 0 when it is no match."""
    match = _COMPARISON.match(candidate)
    if not match:
        return 0
    key = (match.group("key") or "").lower()
    if require_key and key not in COMPARISON_KEYS:
        return 0
    return _record_comparison(COMPARISON_KEYS.get(key), match.group("op"), match.group("value"), position, fields)


def _record_comparison(
    kind: str | None,
    operator: str,
    value: str,
    position: int,
    fields: dict[str, object],
) -> int:
    """Map ``2`` / ``40分钟`` / ``1.5小时`` onto the field the operator applies to."""
    seconds = _parse_duration(value, allow_bare=kind == "duration")
    if seconds is not None and kind in (None, "duration"):
        fields["duration"] = (OPERATORS[operator], seconds)
        return position
    if kind == "rating" and _INTEGER.match(value):
        fields["rating"] = (OPERATORS[operator], int(value))
        return position
    return 0


def _parse_duration(value: str, allow_bare: bool) -> int | None:
    """Read a duration literal as seconds; a unitless number means minutes."""
    if allow_bare and _INTEGER.match(value):
        return int(value) * 60
    parsed = _DURATION_VALUE.match(value)
    if not parsed:
        return None
    unit = DURATION_UNITS.get(parsed.group("unit").lower())
    if unit is None:
        return None
    return round(float(parsed.group("number")) * unit)


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_pair(value: object) -> tuple[str, int] | None:
    if isinstance(value, tuple) and len(value) == 2:
        return (value[0], value[1])
    return None
