"""Object storage over the S3 wire protocol.

MinIO, RustFS, Ceph RGW and the cloud buckets all speak this protocol, so there
is no per-vendor client here -- ``S3_ENDPOINT_URL`` decides where it points.

Read-only by design. The missing capabilities are not polish: with no file a
local process can open, FFmpeg cannot seek inside a video, so thumbnails,
transcode and embedded-subtitle extraction stay gated off (see
``Capabilities.local_path``).
"""
from src.config import settings
from src.storage.base import (
    CHUNK_SIZE,
    S3_SCHEME,
    Capabilities,
    FoundFile,
    UnsupportedStorage,
)
from src.utils.file_fingerprint import EDGE_BYTES, hash_edges
from src.utils.file_scanner import VIDEO_EXTENSIONS

try:  # S3 支持是可选依赖，没装也不该挡住服务启动
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - 未安装 .[s3] 时走这里
    class ClientError(Exception):
        """占位类。真正的 S3 调用会先撞到「请安装 .[s3]」那句提示。"""


def split_root(root: str) -> tuple[str, str]:
    """``s3://bucket/shows`` -> ``("bucket", "shows/")``.

    A bare bucket means the whole bucket; a trailing slash is added so a prefix
    never also matches ``shows-extra/`` next to it.
    """
    body = root[len(S3_SCHEME):] if root.startswith(S3_SCHEME) else root
    bucket, _, prefix = body.partition("/")
    if not bucket:
        raise UnsupportedStorage(f"对象存储路径缺少 bucket 名：{root}")
    prefix = prefix.strip("/")
    return bucket, f"{prefix}/" if prefix else ""


def split_locator(locator: str) -> tuple[str, str]:
    """``s3://bucket/shows/01.mkv`` -> ``("bucket", "shows/01.mkv")``."""
    body = locator[len(S3_SCHEME):] if locator.startswith(S3_SCHEME) else locator
    bucket, _, key = body.partition("/")
    if not bucket or not key:
        raise UnsupportedStorage(f"不是合法的对象存储地址：{locator}")
    return bucket, key


def _extension_of(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot > 0 else ""


class S3MediaStorage:
    """List a bucket and stream one object's byte range."""

    capabilities = Capabilities(
        streaming=True, local_path=False, sidecar_subtitles=False
    )

    def __init__(self) -> None:
        self._client_cache = None
        self._client_key: tuple[str, ...] | None = None

    # -- client ---------------------------------------------------------

    def _client(self):
        """Build once per configuration, not once per process.

        The cache has to notice a credential change: a client built under one
        set of keys keeps using them forever, which turns "the user fixed their
        ``.env`` and reloaded" into a request signed with the old pair.
        """
        key = (
            settings.s3_endpoint_url,
            settings.s3_region,
            settings.s3_access_key_id,
            settings.s3_secret_access_key,
            settings.s3_addressing_style,
        )
        if self._client_cache is None or self._client_key != key:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:
                raise UnsupportedStorage(
                    '读取对象存储需要额外依赖，请安装后重启服务：pip install -e ".[s3]"'
                ) from exc
            if not settings.s3_access_key_id or not settings.s3_secret_access_key:
                raise UnsupportedStorage(
                    "尚未配置对象存储凭证，请在 backend/.env 里设置 "
                    "S3_ACCESS_KEY_ID 与 S3_SECRET_ACCESS_KEY"
                )
            self._client_cache = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": settings.s3_addressing_style},
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
            self._client_key = key
        return self._client_cache

    @staticmethod
    def _error_code(exc: Exception) -> str:
        return str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))

    # -- seam -----------------------------------------------------------

    def reachable(self, root: str) -> bool:
        """Whether the bucket answers at all.

        A bucket that will not talk back reports unreachable rather than empty:
        a wrong credential must not look like "the user deleted everything".
        """
        try:
            client = self._client()
        except UnsupportedStorage:
            return False
        try:
            client.head_bucket(Bucket=split_root(root)[0])
        except ClientError:
            return False
        return True

    def list_videos(self, root: str) -> list[FoundFile]:
        client = self._client()
        bucket, prefix = split_root(root)

        found: list[FoundFile] = []
        for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefix
        ):
            for item in page.get("Contents", []):
                filename = item["Key"].rsplit("/", 1)[-1]
                extension = _extension_of(filename)
                if extension not in VIDEO_EXTENSIONS:
                    continue
                found.append(
                    FoundFile(
                        locator=f"{S3_SCHEME}{bucket}/{item['Key']}",
                        filename=filename,
                        extension=extension,
                        size=int(item["Size"]),
                    )
                )
        return found

    def exists(self, locator: str) -> bool:
        return self.size(locator) is not None

    def size(self, locator: str) -> int | None:
        try:
            client = self._client()
        except UnsupportedStorage:
            # 凭证没配好等同于"这个文件读不到"：让播放回落到占位响应，
            # 而不是每部对象存储上的影片都抛 500。
            return None
        bucket, key = split_locator(locator)
        try:
            head = client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if self._error_code(exc) in {"404", "NoSuchKey", "NoSuchBucket"}:
                return None
            raise
        return int(head["ContentLength"])

    def iter_range(self, locator: str, start: int, end: int):
        client = self._client()
        bucket, key = split_locator(locator)
        body = client.get_object(
            Bucket=bucket, Key=key, Range=f"bytes={start}-{end}"
        )["Body"]
        remaining = end - start + 1
        while remaining > 0:
            chunk = body.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk

    def edge_fingerprint(self, locator: str) -> str | None:
        """Hash the same first and last megabyte the local storage hashes.

        Deliberately not the ETag: that is the MD5 of the whole object, and
        something else again for a multipart upload. Mixing two digest families
        into one comparison would silently stop the duplicate check from ever
        matching a local copy against a bucket copy. Two range reads cost less
        than that surprise.
        """
        try:
            total = self.size(locator)
            if total is None:
                return None
            head = b"".join(self.iter_range(locator, 0, EDGE_BYTES - 1))
            tail = b"".join(
                self.iter_range(locator, max(0, total - EDGE_BYTES), total - 1)
            )
        except Exception:
            # 读不到就说明此刻没法判断，交给调用方按"不是重复"处理
            return None
        return hash_edges(head, tail)

    def local_path(self, locator: str) -> str:
        raise UnsupportedStorage(
            "对象存储里的文件没有本地路径，转码、缩略图与内嵌字幕暂不支持这类视频源"
        )
