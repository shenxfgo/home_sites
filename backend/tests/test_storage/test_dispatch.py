"""Dispatch and the capability table the gates read.

The gates in routes and services ask ``capabilities`` instead of sniffing for
``s3://``, so this table is the contract they all depend on.
"""
import pytest

from src.storage import (
    Capabilities,
    S3MediaStorage,
    UnsupportedStorage,
    storage_for_locator,
    storage_for_source,
)
from src.storage.local import LocalMediaStorage


@pytest.mark.parametrize("source_type", ["local", "nas"])
def test_a_mounted_share_is_local_storage(source_type):
    """NAS 是挂载好的本地路径，故意与 local 共用一份实现。"""
    assert isinstance(storage_for_source(source_type), LocalMediaStorage)


def test_minio_is_s3_storage():
    assert isinstance(storage_for_source("minio"), S3MediaStorage)


def test_an_unknown_type_fails_loudly():
    with pytest.raises(UnsupportedStorage):
        storage_for_source("dropbox")


@pytest.mark.parametrize(
    "locator",
    ["s3://bucket/show/01.mkv", "s3://bucket/01.mkv"],
)
def test_an_object_locator_picks_the_object_store(locator):
    assert isinstance(storage_for_locator(locator), S3MediaStorage)


@pytest.mark.parametrize(
    "locator",
    ["D:/media/show/01.mkv", "\\\\nas\\share\\01.mkv", "/mnt/media/01.mkv"],
)
def test_a_plain_path_is_local_whatever_its_flavour(locator):
    assert isinstance(storage_for_locator(locator), LocalMediaStorage)


def test_local_can_do_everything():
    assert storage_for_source("local").capabilities == Capabilities(
        streaming=True, local_path=True, sidecar_subtitles=True
    )


def test_object_store_streams_but_cannot_feed_a_subprocess():
    """唯一的差别就是本地路径：FFmpeg 要在文件里 seek，对象存储给不了。"""
    assert storage_for_source("minio").capabilities == Capabilities(
        streaming=True, local_path=False, sidecar_subtitles=False
    )


def test_object_store_has_no_local_path_to_give():
    with pytest.raises(UnsupportedStorage, match="对象存储"):
        storage_for_locator("s3://bucket/01.mkv").local_path("s3://bucket/01.mkv")
