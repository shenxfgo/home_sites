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
    played_at: str
    progress: int
    completed: bool

    model_config = {"from_attributes": True}

    @field_serializer("played_at")
    @staticmethod
    def serialize_played_at(value: datetime | str) -> str:
        """Serialize played_at to ISO format string."""
        if isinstance(value, datetime):
            return value.isoformat()
        return value


class HistoryListResponse(BaseModel):
    """Paginated history list response."""

    items: list[HistoryResponse]
    total: int
    page: int
    page_size: int


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
        items=history,
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
