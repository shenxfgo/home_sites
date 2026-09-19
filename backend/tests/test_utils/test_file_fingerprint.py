"""Tests for the edge fingerprint used to confirm two files match."""
from src.utils.file_fingerprint import edge_fingerprint


def _write(path, data: bytes):
    path.write_bytes(data)
    return str(path)


def test_identical_content_hashes_the_same(tmp_path):
    first = _write(tmp_path / "a.mkv", b"header" + b"x" * 50 + b"tail")
    second = _write(tmp_path / "b.mkv", b"header" + b"x" * 50 + b"tail")

    assert edge_fingerprint(first, block=8) == edge_fingerprint(second, block=8)


def test_a_recut_that_changes_the_length_is_separate(tmp_path):
    """A different middle usually shifts the tail window, which is enough here.

    Two files of the same length that differ only in the middle are the known
    blind spot; the scan already narrowed them by size and duration, and the
    edges keep the read cost fixed on a slow share.
    """
    first = _write(tmp_path / "a.mkv", b"header" + b"1" * 50 + b"tail")
    second = _write(tmp_path / "b.mkv", b"header" + b"2" * 60 + b"tail")

    assert edge_fingerprint(first, block=8) != edge_fingerprint(second, block=8)


def test_files_that_differ_only_at_the_tail_are_separate(tmp_path):
    first = _write(tmp_path / "a.mkv", b"header" + b"x" * 50 + b"tailAAAA")
    second = _write(tmp_path / "b.mkv", b"header" + b"x" * 50 + b"tailBBBB")

    assert edge_fingerprint(first, block=8) != edge_fingerprint(second, block=8)


def test_a_file_that_cannot_be_opened_has_no_fingerprint(tmp_path):
    gone = tmp_path / "unmounted" / "a.mkv"

    assert edge_fingerprint(str(gone)) is None


def test_a_directory_is_not_a_file(tmp_path):
    assert edge_fingerprint(str(tmp_path)) is None
