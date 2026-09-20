"""NotificationService for notification operations."""
from sqlalchemy import delete, exists, select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification
from src.models.read_state import NotificationRead


class NotificationService:
    """Service for managing notifications.

    The feed itself is a broadcast: a scan or a transcode happened once, so one
    row is shared by the household. What is personal is whether *you* have read
    it, which lives in ``notification_reads``. Deleting stays a library-level
    action and is gated to owners at the API.
    """

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
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[Notification], int]:
        """Get paginated notifications with the caller's read flag attached."""
        total = await self.session.scalar(
            select(func.count()).select_from(Notification)
        )

        query = (
            select(Notification)
            .order_by(desc(Notification.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        notifications = list(result.scalars().all())

        # One indexed lookup serves the page, the same way the resume rail reads
        # its positions, so the response keeps its per-item ``read`` field.
        read_ids = set(
            (
                await self.session.execute(
                    select(NotificationRead.notification_id).where(
                        NotificationRead.user_id == user_id,
                        NotificationRead.notification_id.in_(
                            [n.id for n in notifications] or [-1]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for notification in notifications:
            notification.read = notification.id in read_ids

        return notifications, total

    async def get_unread_count(self, user_id: int) -> int:
        """Count the notifications this account has not read yet."""
        query = (
            select(func.count())
            .select_from(Notification)
            .where(
                ~exists(
                    select(NotificationRead.notification_id).where(
                        NotificationRead.notification_id == Notification.id,
                        NotificationRead.user_id == user_id,
                    )
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def mark_read(self, user_id: int, notification_id: int) -> None:
        """Record that the caller has read a notification."""
        notification = await self.session.get(Notification, notification_id)
        if not notification:
            raise ValueError(f"Notification with id {notification_id} not found")

        already = await self.session.scalar(
            select(NotificationRead).where(
                NotificationRead.notification_id == notification_id,
                NotificationRead.user_id == user_id,
            )
        )
        if not already:
            self.session.add(
                NotificationRead(notification_id=notification_id, user_id=user_id)
            )
            await self.session.commit()

    async def mark_all_read(self, user_id: int) -> None:
        """Record every notification as read for the caller."""
        unread = await self.session.execute(
            select(Notification.id).where(
                ~exists(
                    select(NotificationRead.notification_id).where(
                        NotificationRead.notification_id == Notification.id,
                        NotificationRead.user_id == user_id,
                    )
                )
            )
        )
        for notification_id in unread.scalars():
            self.session.add(
                NotificationRead(notification_id=notification_id, user_id=user_id)
            )
        await self.session.commit()

    async def delete_notification(self, notification_id: int) -> None:
        """Delete a single notification for the whole household."""
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
