"""HistoryService for playback history operations."""
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.history import PlayHistory
from src.models.video import Video


class HistoryService:
    """Service for managing playback history."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_history(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[PlayHistory], int]:
        """Get paginated playback history, most recent watch first."""
        total_result = await self.session.execute(
            select(func.count(PlayHistory.id))
        )
        total = total_result.scalar_one()

        query = (
            select(PlayHistory)
            .order_by(desc(PlayHistory.played_at))
            .options(selectinload(PlayHistory.video))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        history = list(result.scalars().all())

        return history, total

    async def get_continue_list(self) -> list[Video]:
        """Get videos left unfinished, the one most recently watched first.

        The history row already carries the position, so it is copied onto the
        video the resume rail renders instead of looking it up a second time.
        """
        query = (
            select(PlayHistory)
            .where(PlayHistory.completed == False)  # noqa: E712
            .order_by(desc(PlayHistory.played_at))
            .options(selectinload(PlayHistory.video))
            .limit(20)
        )
        result = await self.session.execute(query)
        history_items = list(result.scalars().all())
        videos = []
        for record in history_items:
            if record.video:
                record.video.progress = record.progress
                videos.append(record.video)
        return videos

    async def delete_history(self, history_id: int) -> None:
        """Delete a history record."""
        result = await self.session.execute(
            select(PlayHistory).where(PlayHistory.id == history_id)
        )
        history = result.scalar_one_or_none()
        if not history:
            raise ValueError(f"History with id {history_id} not found")

        await self.session.delete(history)
        await self.session.commit()
