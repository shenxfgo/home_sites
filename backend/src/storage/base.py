"""Storage seam: the one place where a media locator turns into bytes.

A locator is a self-describing string -- a Windows path, a UNC share, or
``s3://bucket/show/01.mkv`` -- stored verbatim in ``Video.filepath``. The reader
is picked from the locator rather than from ``video_sources`` so that streaming
does not need a join on every Range request.
"""
from dataclasses import dataclass
from typing import Iterator, Protocol

S3_SCHEME = "s3://"

#: Bytes per chunk on the streaming path.
CHUNK_SIZE = 1024 * 1024


class UnsupportedStorage(Exception):
    """Asked something this storage cannot do.

    Raised at the seam so routes can turn it into a readable 400 instead of
    letting a subprocess fail on a path that is not a path.
    """


@dataclass(frozen=True)
class FoundFile:
    """One video file a scan discovered, before it becomes a ``Video`` row."""

    locator: str
    filename: str
    extension: str
    size: int


@dataclass(frozen=True)
class Capabilities:
    """What a storage can do, so callers ask instead of guessing.

    ``local_path`` is the load-bearing one: it says a local process may open the
    locator. FFmpeg, ffprobe and the WebVTT conversion all rest on it, and none
    of them can be patched into working by reading harder -- an object store has
    no file for them to seek around.
    """

    streaming: bool
    local_path: bool
    sidecar_subtitles: bool


class MediaStorage(Protocol):
    """Read side of a media store: list a source, then fetch one file's bytes."""

    capabilities: Capabilities

    def reachable(self, root: str) -> bool:
        """Whether the root can be talked to at all.

        A scan that cannot reach its source reports no files, and the caller
        must not read that as "everything is gone".
        """

    def list_videos(self, root: str) -> list[FoundFile]:
        """Every video file under ``root``, recursively."""

    def exists(self, locator: str) -> bool: ...

    def size(self, locator: str) -> int | None:
        """Size in bytes, or ``None`` when the file cannot be stat'ed."""

    def iter_range(self, locator: str, start: int, end: int) -> Iterator[bytes]:
        """Bytes from ``start`` through ``end``, both inclusive.

        Implementations must not touch the file until the first chunk is asked
        for: a response has already committed its headers by then.
        """

    def edge_fingerprint(self, locator: str) -> str | None:
        """Digest confirming two same-sized files hold the same bytes.

        ``None`` means "could not read", which is never a duplicate of anything.
        """

    def local_path(self, locator: str) -> str:
        """The locator as a path a local subprocess may open.

        Raises ``UnsupportedStorage`` when ``capabilities.local_path`` is false.
        """
