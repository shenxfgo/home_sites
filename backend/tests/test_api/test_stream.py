"""Tests for the HTTP Range handling that backs video seeking."""
import pytest

from fastapi import HTTPException

from src.api.stream import _handle_range_request

FILE_SIZE = 4096


def request_range(tmp_path, range_header: str, file_size: int = FILE_SIZE):
    """Build the streaming response for a range request against a real file."""
    filepath = tmp_path / "sample.mp4"
    filepath.write_bytes(bytes(range(256)) * (file_size // 256 + 1))
    return _handle_range_request(
        str(filepath), range_header, file_size, "video/mp4"
    )


def test_open_ended_range_streams_to_end_of_file(tmp_path):
    """bytes=N- covers the rest of the file."""
    response = request_range(tmp_path, "bytes=1000-")

    assert response.status_code == 206
    assert response.headers["Content-Range"] == f"bytes 1000-{FILE_SIZE - 1}/{FILE_SIZE}"
    assert response.headers["Content-Length"] == str(FILE_SIZE - 1000)


def test_closed_range_respects_both_bounds(tmp_path):
    """bytes=start-end covers exactly that slice."""
    response = request_range(tmp_path, "bytes=100-199")

    assert response.headers["Content-Range"] == f"bytes 100-199/{FILE_SIZE}"
    assert response.headers["Content-Length"] == "100"


def test_suffix_range_returns_the_tail_of_the_file(tmp_path):
    """bytes=-N means the LAST N bytes, not the first ones."""
    response = request_range(tmp_path, "bytes=-512")

    assert response.headers["Content-Range"] == f"bytes {FILE_SIZE - 512}-{FILE_SIZE - 1}/{FILE_SIZE}"
    assert response.headers["Content-Length"] == "512"


def test_suffix_range_larger_than_file_is_clamped(tmp_path):
    """A suffix longer than the file starts at byte 0."""
    response = request_range(tmp_path, "bytes=-999999")

    assert response.headers["Content-Range"] == f"bytes 0-{FILE_SIZE - 1}/{FILE_SIZE}"


def test_end_beyond_file_is_clamped_instead_of_rejected(tmp_path):
    """Players ask for more than exists; rejecting them restarts the download."""
    response = request_range(tmp_path, f"bytes=100-{FILE_SIZE * 10}")

    assert response.headers["Content-Range"] == f"bytes 100-{FILE_SIZE - 1}/{FILE_SIZE}"


async def test_body_matches_declared_length(tmp_path):
    """The streamed bytes must match Content-Range, or the demuxer seeks astray."""
    response = request_range(tmp_path, "bytes=-512")

    body = b"".join([chunk async for chunk in response.body_iterator])
    assert len(body) == 512
    assert body == (bytes(range(256)) * 17)[FILE_SIZE - 512 : FILE_SIZE]


@pytest.mark.parametrize("header", ["bytes=abc-", "bytes=-", "bytes=999999-", "garbage"])
def test_unusable_ranges_are_rejected(tmp_path, header):
    with pytest.raises(HTTPException) as exc:
        request_range(tmp_path, header)

    assert exc.value.status_code == 416
