"""Local disk and mounted shares: the storage this app started with.

``nas`` deliberately shares this implementation. An SMB/NFS mount *is* a local
path by the time the app sees it, and nothing here speaks a mount protocol.
"""
import os

from src.storage.base import (
    CHUNK_SIZE,
    Capabilities,
    FoundFile,
)
from src.utils.file_fingerprint import edge_fingerprint
from src.utils.file_scanner import scan_directory


class LocalMediaStorage:
    """Read media straight off the filesystem the process can see."""

    capabilities = Capabilities(
        streaming=True, local_path=True, sidecar_subtitles=True
    )

    def reachable(self, root: str) -> bool:
        return os.path.isdir(root)

    def list_videos(self, root: str) -> list[FoundFile]:
        # 复用原来那份 os.walk。Video.filepath 是靠字符串全等去重的，locator
        # 差一个分隔符就会让整库既"全部新增"又"全部丢失"。
        return [
            FoundFile(
                locator=item["filepath"],
                filename=item["filename"],
                extension=item["extension"],
                size=item["file_size"],
            )
            for item in scan_directory(root)
        ]

    def exists(self, locator: str) -> bool:
        return os.path.isfile(locator)

    def size(self, locator: str) -> int | None:
        try:
            return os.path.getsize(locator)
        except OSError:
            return None

    def iter_range(self, locator: str, start: int, end: int):
        with open(locator, "rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def edge_fingerprint(self, locator: str) -> str | None:
        return edge_fingerprint(locator)

    def local_path(self, locator: str) -> str:
        return locator
