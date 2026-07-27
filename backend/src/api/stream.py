"""Video streaming API endpoints."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.video_service import VideoService

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
    service = VideoService(session)
    video = await service.get_video_by_id(video_id)
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
    service = VideoService(session)
    video = await service.get_video_by_id(video_id)
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
    try:
        # Parse Range header (e.g., "bytes=0-1023")
        ranges = range_header.replace("bytes=", "").split("-")
        start = int(ranges[0]) if ranges[0] else 0
        end = int(ranges[1]) if ranges[1] else file_size - 1
    except (ValueError, IndexError):
        raise HTTPException(status_code=416, detail="Invalid Range header")

    if start >= file_size or end >= file_size:
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
