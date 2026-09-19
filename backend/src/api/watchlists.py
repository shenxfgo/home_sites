"""Watchlist API endpoints for hand-picked queues."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.video_service import attach_watch_progress
from src.services.watchlist_service import WatchlistService
from src.api.videos import VideoResponse

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


class WatchlistCreate(BaseModel):
    """Request model for creating a watchlist."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=512)


class WatchlistUpdate(BaseModel):
    """Request model for renaming a watchlist."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=512)


class WatchlistVideoRequest(BaseModel):
    """Request model for putting one title into a watchlist."""

    video_id: int


class WatchlistResponse(BaseModel):
    """A watchlist and the queue of titles it holds, in the order added."""

    id: int
    name: str
    description: str | None
    created_at: datetime
    items: list[VideoResponse]

    model_config = {"from_attributes": True}


async def get_watchlist_service(
    session: AsyncSession = Depends(get_session),
) -> WatchlistService:
    """Dependency to get WatchlistService instance."""
    return WatchlistService(session)


async def _respond(session: AsyncSession, watchlist) -> WatchlistResponse:
    """Attach the stored watch position so the queue can say what is left."""
    videos = [item.video for item in watchlist.items if item.video]
    await attach_watch_progress(session, videos)
    return WatchlistResponse(
        id=watchlist.id,
        name=watchlist.name,
        description=watchlist.description,
        created_at=watchlist.created_at,
        items=[VideoResponse.model_validate(video) for video in videos],
    )


@router.get("", response_model=list[WatchlistResponse])
async def list_watchlists(
    video_id: int | None = Query(None, ge=1, description="Only lists holding this title"),
    service: WatchlistService = Depends(get_watchlist_service),
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistResponse]:
    """List every watchlist, or only those containing ``video_id``."""
    watchlists = await service.list_watchlists(video_id=video_id)
    return [await _respond(session, watchlist) for watchlist in watchlists]


@router.post("", response_model=WatchlistResponse, status_code=201)
async def create_watchlist(
    data: WatchlistCreate,
    service: WatchlistService = Depends(get_watchlist_service),
    session: AsyncSession = Depends(get_session),
) -> WatchlistResponse:
    """Create an empty watchlist."""
    watchlist = await service.create(name=data.name, description=data.description)
    return await _respond(session, watchlist)


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: int,
    service: WatchlistService = Depends(get_watchlist_service),
    session: AsyncSession = Depends(get_session),
) -> WatchlistResponse:
    """Get one watchlist with its queue."""
    watchlist = await service.get_watchlist(watchlist_id)
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return await _respond(session, watchlist)


@router.put("/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: int,
    data: WatchlistUpdate,
    service: WatchlistService = Depends(get_watchlist_service),
    session: AsyncSession = Depends(get_session),
) -> WatchlistResponse:
    """Rename a watchlist or edit its description."""
    try:
        watchlist = await service.update(watchlist_id, **data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _respond(session, watchlist)


@router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: int,
    service: WatchlistService = Depends(get_watchlist_service),
) -> None:
    """Delete a watchlist. The titles themselves stay in the library."""
    try:
        await service.delete(watchlist_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{watchlist_id}/videos", response_model=WatchlistResponse)
async def add_video_to_watchlist(
    watchlist_id: int,
    data: WatchlistVideoRequest,
    service: WatchlistService = Depends(get_watchlist_service),
    session: AsyncSession = Depends(get_session),
) -> WatchlistResponse:
    """Put a title at the end of the queue. Adding it twice is a no-op."""
    try:
        watchlist = await service.add_video(watchlist_id, data.video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _respond(session, watchlist)


@router.delete("/{watchlist_id}/videos/{video_id}", response_model=WatchlistResponse)
async def remove_video_from_watchlist(
    watchlist_id: int,
    video_id: int,
    service: WatchlistService = Depends(get_watchlist_service),
    session: AsyncSession = Depends(get_session),
) -> WatchlistResponse:
    """Take a title out of the queue without touching the library."""
    try:
        watchlist = await service.remove_video(watchlist_id, video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _respond(session, watchlist)
