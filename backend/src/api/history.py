"""Playback history API endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.history_service import HistoryService
from src.api.videos import VideoResponse

router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryResponse(BaseModel):
    """Response model for history record."""

    id: int
    video_id: int
    played_at: datetime
    progress: int
    completed: bool
    video_title: str | None = None

    model_config = {"from_attributes": True}


class HistoryListResponse(BaseModel):
    """Paginated history list response."""

    items: list[HistoryResponse]
    total: int
    page: int
    page_size: int


class WatchDayResponse(BaseModel):
    """One bar of the daily chart."""

    date: str
    seconds: int
    videos: int


class WatchTagResponse(BaseModel):
    """How many watched seconds a tag accounts for."""

    name: str
    color: str
    seconds: int


class WatchStatsResponse(BaseModel):
    """What the watch-event log adds up to over a window of days."""

    days: int
    window_seconds: int
    month_seconds: int
    videos_watched: int
    active_days: int
    longest_streak_days: int
    daily: list[WatchDayResponse]
    tags: list[WatchTagResponse]


async def get_history_service(
    session: AsyncSession = Depends(get_session),
) -> HistoryService:
    """Dependency to get HistoryService instance."""
    return HistoryService(session)


@router.get("", response_model=HistoryListResponse)
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: HistoryService = Depends(get_history_service),
) -> HistoryListResponse:
    """Get playback history."""
    history, total = await service.get_history(page=page, page_size=page_size)
    return HistoryListResponse(
        items=[
            HistoryResponse(
                id=record.id,
                video_id=record.video_id,
                played_at=record.played_at,
                progress=record.progress,
                completed=record.completed,
                video_title=record.video.title if record.video else None,
            )
            for record in history
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/continue", response_model=list[VideoResponse])
async def get_continue_list(
    service: HistoryService = Depends(get_history_service),
) -> list[VideoResponse]:
    """Get videos to continue watching."""
    return await service.get_continue_list()


@router.get("/stats", response_model=WatchStatsResponse)
async def get_watch_stats(
    days: int = Query(30, ge=7, le=365),
    service: HistoryService = Depends(get_history_service),
) -> WatchStatsResponse:
    """Aggregate the watch-event log into hours, a streak and a tag split."""
    return await service.get_stats(days=days)


@router.delete("/{history_id}", status_code=204)
async def delete_history(
    history_id: int,
    service: HistoryService = Depends(get_history_service),
) -> None:
    """Delete a history record."""
    try:
        await service.delete_history(history_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
