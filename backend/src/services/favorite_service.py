"""FavoriteService for favorites operations."""
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.favorite import Favorite
from src.models.video import Video


class FavoriteService:
    """Service for managing favorites."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_favorites(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Video], int]:
        """Get paginated favorite videos."""
        # Count total
        count_query = select(Favorite)
        result = await self.session.execute(count_query)
        all_favorites = list(result.scalars().all())
        total = len(all_favorites)

        # Get paginated with videos
        query = (
            select(Favorite)
            .order_by(desc(Favorite.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(selectinload(Favorite.video))
        )
        result = await self.session.execute(query)
        favorites = list(result.scalars().all())
        videos = [f.video for f in favorites if f.video]

        return videos, total

    async def add_favorite(self, video_id: int) -> Favorite:
        """Add a video to favorites."""
        # Check if already exists
        existing = await self.session.execute(
            select(Favorite).where(Favorite.video_id == video_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError("Video already in favorites")

        favorite = Favorite(video_id=video_id)
        self.session.add(favorite)
        await self.session.commit()
        await self.session.refresh(favorite)
        return favorite

    async def remove_favorite(self, video_id: int) -> None:
        """Remove a video from favorites."""
        result = await self.session.execute(
            select(Favorite).where(Favorite.video_id == video_id)
        )
        favorite = result.scalar_one_or_none()
        if not favorite:
            raise ValueError("Video not in favorites")

        await self.session.delete(favorite)
        await self.session.commit()

    async def is_favorite(self, video_id: int) -> bool:
        """Check if a video is in favorites."""
        result = await self.session.execute(
            select(Favorite).where(Favorite.video_id == video_id)
        )
        return result.scalar_one_or_none() is not None
