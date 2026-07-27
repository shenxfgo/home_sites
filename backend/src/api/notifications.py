"""Notification API endpoints."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.notification_service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    """Response model for a notification."""

    id: int
    type: str
    title: str
    message: str
    data: dict | None
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    @staticmethod
    def serialize_datetime(value: datetime) -> str:
        return value.isoformat()


class NotificationListResponse(BaseModel):
    """Paginated notification list response."""

    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    """Response model for unread count."""

    count: int


async def get_notification_service(
    session: AsyncSession = Depends(get_session),
) -> NotificationService:
    """Dependency to get NotificationService instance."""
    return NotificationService(session)


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    """Get notifications."""
    notifications, total = await service.get_notifications(
        page=page, page_size=page_size
    )
    return NotificationListResponse(
        items=notifications,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread", response_model=UnreadCountResponse)
async def get_unread_count(
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    """Get count of unread notifications."""
    count = await service.get_unread_count()
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: int,
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """Mark a notification as read."""
    try:
        await service.mark_read(notification_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/read-all", status_code=204)
async def mark_all_read(
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """Mark all notifications as read."""
    await service.mark_all_read()
