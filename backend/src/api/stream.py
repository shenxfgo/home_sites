"""Video streaming API endpoints."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.video import Video

router = APIRouter(prefix="/api/videos", tags=["streaming"])

CHUNK_SIZE = 1024 * 1024  # 1MB


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Stream video with Range support for seeking.

    In production, this would stream from local/NAS/MinIO storage.
    For now, serves the file directly if it exists locally.
    """
    # The row is read directly rather than through VideoService: streaming only
    # needs the path, and the service call would add a per-person history lookup.
    video = await session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    filepath = video.filepath

    # Check if file exists locally
    if os.path.isfile(filepath):
        file_size = os.path.getsize(filepath)
        content_type = _get_content_type(filepath)

        # Handle Range request for seeking
        range_header = request.headers.get("range")
        if range_header:
            return _handle_range_request(filepath, range_header, file_size, content_type)

        # Return full file
        return FileResponse(
            path=filepath,
            media_type=content_type,
            filename=os.path.basename(filepath),
        )

    # Placeholder response for non-local files
    return {
        "message": f"Stream endpoint for video {video_id}",
        "filepath": filepath,
        "note": "File not found locally. In production, this would stream from storage.",
    }


@router.get("/{video_id}/thumbnail")
async def get_thumbnail(
    video_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get video thumbnail.

    Returns the thumbnail file if available, or a placeholder response.
    """
    video = await session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.thumbnail_path and os.path.isfile(video.thumbnail_path):
        return FileResponse(
            path=video.thumbnail_path,
            media_type="image/jpeg",
        )

    return {"thumbnail": None, "message": "No thumbnail available"}


def _get_content_type(filepath: str) -> str:
    """Determine content type based on file extension."""
    ext = Path(filepath).suffix.lower()
    content_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".flv": "video/x-flv",
        ".wmv": "video/x-ms-wmv",
        ".m4v": "video/mp4",
    }
    return content_types.get(ext, "video/mp4")


def _handle_range_request(
    filepath: str, range_header: str, file_size: int, content_type: str
) -> StreamingResponse:
    """Handle HTTP Range request for video seeking."""
    last_byte = file_size - 1
    try:
        # Parse Range spec: "bytes=0-1023", "bytes=1024-", "bytes=-1024"
        spec = range_header.split("=", 1)[1].split(",", 1)[0].strip()
        raw_start, _, raw_end = spec.partition("-")
        if raw_start:
            start = int(raw_start)
            end = int(raw_end) if raw_end else last_byte
        else:
            # 后缀区间：最后 N 个字节（非 faststart 的 mp4 用整文件在尾部的 moov）
            suffix = int(raw_end)
            start = max(0, file_size - suffix)
            end = last_byte
    except (ValueError, IndexError):
        raise HTTPException(status_code=416, detail="Invalid Range header")

    # 越界按 RFC 7233 收敛到文件末尾，而不是回 416，否则播放器会从头重载
    end = min(end, last_byte)
    if start > end or start < 0:
        raise HTTPException(status_code=416, detail="Range not satisfiable")

    content_length = end - start + 1

    def file_iterator():
        with open(filepath, "rb") as f:
            f.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": content_type,
    }

    return StreamingResponse(
        file_iterator(),
        status_code=206,
        headers=headers,
        media_type=content_type,
    )
