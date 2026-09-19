"""Subtitle management API endpoints."""
import asyncio
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.subtitle_service import SubtitleService
from src.utils.media_streams import (
    StreamNotFound,
    extract_subtitle_webvtt,
    probe_streams,
)
from src.utils.subtitles import (
    SUBTITLE_EXTENSIONS,
    SubtitleConversionError,
    convert_to_webvtt,
)

router = APIRouter(prefix="/api/videos", tags=["subtitles"])


class SubtitleResponse(BaseModel):
    """Response model for a subtitle track."""

    id: int
    video_id: int
    language: str | None
    filepath: str
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    @staticmethod
    def serialize_datetime(value: datetime | None) -> str | None:
        """Serialize datetime to ISO format string."""
        if value is None:
            return None
        return value.isoformat()


class SubtitleCreate(BaseModel):
    """Request model for registering a subtitle file."""

    filepath: str = Field(..., min_length=1, max_length=1024)
    language: str | None = Field(None, max_length=10)
    label: str | None = Field(None, max_length=50)


class EmbeddedSubtitleResponse(BaseModel):
    """One subtitle track carried inside the video file itself."""

    stream_index: int
    position: int
    codec: str
    language: str | None
    label: str
    supported: bool


class AudioTrackResponse(BaseModel):
    """One audio track inside the video file, for information only."""

    stream_index: int
    position: int
    codec: str
    language: str | None
    label: str
    default: bool


class MediaStreamsResponse(BaseModel):
    """What ffprobe found inside the container."""

    probed: bool
    container: str | None
    subtitles: list[EmbeddedSubtitleResponse]
    audio: list[AudioTrackResponse]


async def get_subtitle_service(
    session: AsyncSession = Depends(get_session),
) -> SubtitleService:
    """Dependency to get SubtitleService instance."""
    return SubtitleService(session)


@router.get("/{video_id}/subtitles", response_model=list[SubtitleResponse])
async def list_subtitles(
    video_id: int,
    service: SubtitleService = Depends(get_subtitle_service),
) -> list[SubtitleResponse]:
    """List the subtitle tracks of a video."""
    return await service.list_for_video(video_id)


@router.get("/{video_id}/subtitles/streams", response_model=MediaStreamsResponse)
async def list_media_streams(
    video_id: int,
    service: SubtitleService = Depends(get_subtitle_service),
) -> MediaStreamsResponse:
    """List the subtitle and audio tracks muxed inside the video file.

    Read-only: the file is opened by ffprobe and nothing is stored, so an
    embedded track never goes stale the way a cached row would.
    """
    video = await service.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    found = await asyncio.to_thread(probe_streams, video.filepath)
    return MediaStreamsResponse(**found)


@router.get("/{video_id}/subtitles/embedded/{stream_index}/stream")
async def stream_embedded_subtitle(
    video_id: int,
    stream_index: int,
    service: SubtitleService = Depends(get_subtitle_service),
) -> Response:
    """Extract one embedded subtitle as WebVTT, on demand and without temp files."""
    video = await service.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")

    try:
        payload = await asyncio.to_thread(
            extract_subtitle_webvtt, video.filepath, stream_index
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="视频文件不存在")
    except StreamNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SubtitleConversionError as e:
        raise HTTPException(status_code=415, detail=str(e))

    return Response(content=payload, media_type="text/vtt; charset=utf-8")


@router.post("/{video_id}/subtitles", response_model=SubtitleResponse, status_code=201)
async def add_subtitle(
    video_id: int,
    data: SubtitleCreate,
    service: SubtitleService = Depends(get_subtitle_service),
) -> SubtitleResponse:
    """Register a subtitle file that sits next to the video."""
    ext = os.path.splitext(data.filepath)[1].lower()
    if ext not in SUBTITLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的字幕格式: {ext or '未知'}")

    try:
        subtitle = await service.add(
            video_id,
            data.filepath,
            language=data.language,
            label=data.label,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return subtitle


@router.delete("/{video_id}/subtitles/{subtitle_id}", status_code=204)
async def delete_subtitle(
    video_id: int,
    subtitle_id: int,
    service: SubtitleService = Depends(get_subtitle_service),
) -> None:
    """Remove a subtitle track from a video."""
    try:
        await service.delete(video_id, subtitle_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{video_id}/subtitles/{subtitle_id}/stream")
async def stream_subtitle(
    video_id: int,
    subtitle_id: int,
    service: SubtitleService = Depends(get_subtitle_service),
) -> Response:
    """Serve a subtitle as WebVTT, the only format browsers render in a <track>."""
    subtitle = await service.get_subtitle(video_id, subtitle_id)
    if not subtitle:
        raise HTTPException(status_code=404, detail="Subtitle not found")

    try:
        payload = convert_to_webvtt(subtitle.filepath)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="字幕文件不存在")
    except SubtitleConversionError as e:
        raise HTTPException(status_code=415, detail=str(e))

    return Response(content=payload, media_type="text/vtt; charset=utf-8")
