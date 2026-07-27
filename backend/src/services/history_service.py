"""HistoryService for playback history operations."""
from sqlalchemy import select, desc
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
        """Get paginated playback history."""
        # Count total
        count_query = select(PlayHistory)
        result = await self.session.execute(count_query)
        all_history = list(result.scalars().all())
        total = len(all_history)

        # Get paginated
        query = (
            select(PlayHistory)
            .order_by(desc(PlayHistory.played_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        history = list(result.scalars().all())

        return history, total

    async def get_continue_list(self) -> list[Video]:
        """Get videos that can be continued (not completed)."""
        query = (
            select(PlayHistory)
            .where(PlayHistory.completed == False)  # noqa: E712
            .order_by(desc(PlayHistory.played_at))
            .options(selectinload(PlayHistory.video))
            .limit(20)
        )
        result = await self.session.execute(query)
        history_items = list(result.scalars().all())
        return [h.video for h in history_items if h.video]

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
