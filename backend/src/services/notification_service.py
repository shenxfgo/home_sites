"""NotificationService for notification operations."""
from sqlalchemy import delete, select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification


class NotificationService:
    """Service for managing notifications."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        type: str,
        title: str,
        message: str,
        data: dict | None = None,
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            type=type,
            title=title,
            message=message,
            data=data,
        )
        self.session.add(notification)
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def get_notifications(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Notification], int]:
        """Get paginated notifications."""
        # Count total
        count_query = select(func.count()).select_from(Notification)
        result = await self.session.execute(count_query)
        total = result.scalar() or 0

        # Get paginated
        query = (
            select(Notification)
            .order_by(desc(Notification.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        notifications = list(result.scalars().all())

        return notifications, total

    async def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        query = select(func.count()).select_from(Notification).where(Notification.read == False)  # noqa: E712
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def mark_read(self, notification_id: int) -> None:
        """Mark a notification as read."""
        result = await self.session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        if not notification:
            raise ValueError(f"Notification with id {notification_id} not found")

        notification.read = True
        await self.session.commit()

    async def mark_all_read(self) -> None:
        """Mark all notifications as read."""
        result = await self.session.execute(
            select(Notification).where(Notification.read == False)  # noqa: E712
        )
        notifications = list(result.scalars().all())

        for notification in notifications:
            notification.read = True

        await self.session.commit()

    async def delete_notification(self, notification_id: int) -> None:
        """Delete a single notification."""
        result = await self.session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        if not notification:
            raise ValueError(f"Notification with id {notification_id} not found")

        await self.session.delete(notification)
        await self.session.commit()

    async def clear_notifications(self) -> int:
        """Delete every notification and return how many went away."""
        result = await self.session.execute(delete(Notification))
        await self.session.commit()
        return result.rowcount or 0
