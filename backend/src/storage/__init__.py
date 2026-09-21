"""Pick whichever storage can read a given source or file.

The seam itself lives in ``src.storage.base``; this module only answers one
question -- given a video source (or an already-stored locator), which
implementation handles it.
"""
from src.storage.base import (
    CHUNK_SIZE,
    S3_SCHEME,
    Capabilities,
    FoundFile,
    MediaStorage,
    UnsupportedStorage,
)
from src.storage.local import LocalMediaStorage
from src.storage.s3 import S3MediaStorage

_local = LocalMediaStorage()
_s3 = S3MediaStorage()

# ``nas`` shares the local implementation deliberately: an SMB/NFS mount is a
# local path by the time this app sees it, and nothing here speaks a mount
# protocol. Adding a real mount client would belong somewhere else.
_BY_TYPE: dict[str, MediaStorage] = {"local": _local, "nas": _local, "minio": _s3}


def storage_for_source(source_type: str) -> MediaStorage:
    """The storage that lists and reads a source's files."""
    try:
        return _BY_TYPE[source_type]
    except KeyError:
        raise UnsupportedStorage(f"未知的视频源类型：{source_type}") from None


def storage_for_locator(locator: str) -> MediaStorage:
    """The storage a stored ``Video.filepath`` actually lives in.

    Dispatching on the address instead of on the source row is what keeps the
    streaming path free of a ``video_sources`` join on every Range request.
    """
    if locator.startswith(S3_SCHEME):
        return _s3
    return _local


def fingerprint(locator: str) -> str | None:
    """Digest one stored file's two ends, wherever it happens to live.

    The duplicate check works through a list of videos from several sources at
    once, so it should not have to pick a storage per row itself.
    """
    return storage_for_locator(locator).edge_fingerprint(locator)


__all__ = [
    "CHUNK_SIZE",
    "S3_SCHEME",
    "Capabilities",
    "FoundFile",
    "LocalMediaStorage",
    "MediaStorage",
    "S3MediaStorage",
    "UnsupportedStorage",
    "fingerprint",
    "storage_for_locator",
    "storage_for_source",
]
