"""Transcode API endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.transcode_service import TranscodeService

router = APIRouter(prefix="/api/transcode", tags=["transcode"])


class TranscodeRequest(BaseModel):
    """Request model for transcoding."""
    target_format: str


class TranscodeResponse(BaseModel):
    """Response model for transcoding."""
    video_id: int
    status: str
    target_format: str
    output_path: str


class TranscodeStatusResponse(BaseModel):
    """Response model for transcoding status."""
    video_id: int
    is_transcoding: bool
    status: str
    progress: float = 0.0
    target_format: str | None = None
    output_path: str | None = None
    error: str | None = None


class TranscodeProductResponse(BaseModel):
    """One product this video has already been transcoded into.

    `size_bytes` 是**这次请求当场 stat 出来的**，不是表里的抄本；文件没了就是 `None`。
    `deleted_at` 是"哪一次核对发现它没了"，所以它是历史，不是现状 —— 现状只看
    `size_bytes`。
    """
    id: int
    target_format: str
    output_path: str
    size_bytes: int | None
    created_at: datetime
    deleted_at: datetime | None


class FormatInfo(BaseModel):
    """Format information."""
    format: str
    codec: str
    extension: str


async def get_transcode_service(
    session: AsyncSession = Depends(get_session),
) -> TranscodeService:
    """Dependency to get TranscodeService instance."""
    return TranscodeService(session)


@router.post("/{video_id}", response_model=TranscodeResponse)
async def transcode_video_endpoint(
    video_id: int,
    data: TranscodeRequest,
    service: TranscodeService = Depends(get_transcode_service),
) -> TranscodeResponse:
    """Start transcoding a video."""
    try:
        result = await service.transcode(video_id, data.target_format)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{video_id}/status", response_model=TranscodeStatusResponse)
async def get_transcode_status(
    video_id: int,
    service: TranscodeService = Depends(get_transcode_service),
) -> TranscodeStatusResponse:
    """Get transcoding status."""
    return await service.get_status(video_id)


@router.get("/{video_id}/outputs", response_model=list[TranscodeProductResponse])
async def list_transcode_products(
    video_id: int,
    service: TranscodeService = Depends(get_transcode_service),
) -> list[TranscodeProductResponse]:
    """Products this video has already been transcoded into, newest first.

    服务重启之后 `_jobs` 那本账就空了，这一条是产物唯一还在的出处（#154）。
    """
    return [TranscodeProductResponse(**item) for item in await service.list_outputs(video_id)]


@router.post("/{video_id}/cancel", status_code=204)
async def cancel_transcode(
    video_id: int,
    service: TranscodeService = Depends(get_transcode_service),
) -> None:
    """Cancel an active transcoding task."""
    try:
        await service.cancel(video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/formats", response_model=list[FormatInfo])
async def get_supported_formats_endpoint(
    service: TranscodeService = Depends(get_transcode_service),
) -> list[FormatInfo]:
    """Get list of supported transcoding formats."""
    return service.get_supported_formats()
