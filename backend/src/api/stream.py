"""Video streaming API endpoints."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.video import Video
from src.storage import storage_for_locator

router = APIRouter(prefix="/api/videos", tags=["streaming"])


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Stream video with Range support for seeking.

    Where the bytes come from is the storage layer's business: the locator
    stored on the row says whether it is a path on disk or an object key.
    """
    # The row is read directly rather than through VideoService: streaming only
    # needs the path, and the service call would add a per-person history lookup.
    video = await session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    filepath = video.filepath
    storage = storage_for_locator(filepath)

    file_size = storage.size(filepath)
    if file_size is not None:
        content_type = _get_content_type(filepath)

        # Handle Range request for seeking
        range_header = request.headers.get("range")
        if range_header:
            return _handle_range_request(filepath, range_header, file_size, content_type)

        if storage.capabilities.local_path:
            return FileResponse(
                path=filepath,
                media_type=content_type,
                filename=os.path.basename(filepath),
            )

        # 对象存储没有本地文件可交给 FileResponse，整文件就是"从头读到尾的那一段"
        return StreamingResponse(
            storage.iter_range(filepath, 0, max(0, file_size - 1)),
            status_code=200,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Content-Type": content_type,
            },
            media_type=content_type,
        )

    # Placeholder response for files this process cannot read at all
    return {
        "message": f"Stream endpoint for video {video_id}",
        "filepath": filepath,
        "note": "文件当前读不到。挂载盘未就绪、对象存储凭证缺失或文件已删除都会走到这里。",
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
    locator: str, range_header: str, file_size: int, content_type: str
) -> StreamingResponse:
    """Handle HTTP Range request for video seeking.

    区间的解析与越界收敛留在这里，取字节交给存储层。参数收 locator 而不是收一
    个已打开的 reader，是为了让 tests/test_api/test_stream.py 能继续拿真实文件
    直接调这个函数验 RFC 7233 的边界语义——由它自己按地址挑存储，那套用例一行
    都不用改。
    """
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
        # 惰性交给存储层：响应头此刻已经提交，第一次取字节才真正打开文件。
        yield from storage_for_locator(locator).iter_range(locator, start, end)

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
