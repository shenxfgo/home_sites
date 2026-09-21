"""The local storage has to keep producing exactly what was stored before.

``Video.filepath`` is the only key the scan dedupes on, so a locator that
differs from the old walker's string by one separator re-inserts and
mass-marks-missing every row in the library.
"""
import os

import pytest

from src.storage import storage_for_source
from src.utils.file_fingerprint import edge_fingerprint
from src.utils.file_scanner import scan_directory


@pytest.fixture
def tree(tmp_path):
    """A small directory: two videos, a text file and a non-ASCII subtree."""
    nested = tmp_path / "第一季"
    nested.mkdir()
    (tmp_path / "movie.mp4").write_bytes(b"a" * 2048)
    (tmp_path / "movie.txt").write_bytes(b"not a video")
    (tmp_path / "UPPER.MKV").write_bytes(b"b" * 10)
    (nested / "第01集.ass").write_text("subtitle", encoding="utf-8")
    (nested / "第01集.mkv").write_bytes(b"c" * 5)
    return str(tmp_path)


@pytest.mark.parametrize(
    "shape",
    ["as_is", "trailing_sep", "forward_slashes"],
)
def test_locators_are_byte_identical_to_the_pre_seam_walker(tree, shape):
    """Same strings the old ``os.walk`` code produced, for every path spelling."""
    if shape == "trailing_sep":
        root = tree + os.sep
    elif shape == "forward_slashes":
        root = tree.replace("\\", "/")
    else:
        root = tree

    before = [item["filepath"] for item in scan_directory(root)]
    after = [found.locator for found in storage_for_source("local").list_videos(root)]

    assert before, "目录里确实有视频，两边都空着不算通过"
    assert after == before


def test_lists_filename_extension_and_size(tree):
    found = {item.filename: item for item in storage_for_source("local").list_videos(tree)}

    assert found["movie.mp4"].size == 2048
    assert found["movie.mp4"].extension == ".mp4"
    assert found["UPPER.MKV"].extension == ".mkv"
    assert "movie.txt" not in found
    assert "第01集.ass" not in found


def test_iter_range_covers_both_bounds(tmp_path):
    payload = bytes(range(256)) * 8
    path = tmp_path / "sample.bin"
    path.write_bytes(payload)

    streamed = b"".join(storage_for_source("local").iter_range(str(path), 10, 19))

    assert streamed == payload[10:20]


def test_file_opens_only_when_the_first_chunk_is_asked_for(tmp_path):
    """响应头先提交，第一次取字节才准打开文件。"""
    generator = storage_for_source("local").iter_range(
        str(tmp_path / "missing.bin"), 0, 10
    )

    with pytest.raises(FileNotFoundError):
        next(generator)


def test_size_and_existence_of_a_gone_file(tmp_path):
    storage = storage_for_source("local")
    missing = str(tmp_path / "gone.mp4")

    assert storage.size(missing) is None
    assert storage.exists(missing) is False


def test_fingerprint_matches_the_shared_recipe(tmp_path):
    path = tmp_path / "v.mp4"
    path.write_bytes(b"z" * 5000)

    assert storage_for_source("local").edge_fingerprint(str(path)) == edge_fingerprint(
        str(path)
    )


def test_unreachable_root_is_reported_not_assumed(tmp_path):
    assert storage_for_source("local").reachable(str(tmp_path / "nope")) is False
    assert storage_for_source("local").reachable(str(tmp_path)) is True
