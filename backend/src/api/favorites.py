"""Favorites API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.middleware.auth import get_current_user_id
from src.services.favorite_service import FavoriteService
from src.api.videos import VideoResponse

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class FavoriteStatusResponse(BaseModel):
    """Response model for favorite status."""

    is_favorite: bool


class FavoriteListResponse(BaseModel):
    """Paginated favorites list response."""

    items: list[VideoResponse]
    total: int
    page: int
    page_size: int


async def get_favorite_service(
    session: AsyncSession = Depends(get_session),
) -> FavoriteService:
    """Dependency to get FavoriteService instance."""
    return FavoriteService(session)


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
) -> FavoriteListResponse:
    """Get favorite videos."""
    videos, total = await service.get_favorites(user_id, page=page, page_size=page_size)
    return FavoriteListResponse(
        items=videos,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{video_id}", status_code=201)
async def add_favorite(
    video_id: int,
    user_id: int = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
) -> dict:
    """Add a video to favorites."""
    try:
        await service.add_favorite(user_id, video_id)
        return {"message": "Added to favorites"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{video_id}", status_code=204)
async def remove_favorite(
    video_id: int,
    user_id: int = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
) -> None:
    """Remove a video from favorites."""
    try:
        await service.remove_favorite(user_id, video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{video_id}/status", response_model=FavoriteStatusResponse)
async def check_favorite(
    video_id: int,
    user_id: int = Depends(get_current_user_id),
    service: FavoriteService = Depends(get_favorite_service),
) -> FavoriteStatusResponse:
    """Check if a video is in favorites."""
    is_fav = await service.is_favorite(user_id, video_id)
    return FavoriteStatusResponse(is_favorite=is_fav)
