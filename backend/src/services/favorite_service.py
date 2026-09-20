"""FavoriteService for favorites operations."""
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.favorite import Favorite
from src.models.video import Video


class FavoriteService:
    """Service for managing one person's favorites.

    Every query is scoped by ``user_id``: a household shares one library, but
    "kept" is a per-account judgement, and a row that belongs to somebody else
    must not even be reachable by id.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_favorites(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[Video], int]:
        """Get paginated favorite videos."""
        total = await self.session.scalar(
            select(func.count())
            .select_from(Favorite)
            .where(Favorite.user_id == user_id)
        )

        query = (
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .order_by(desc(Favorite.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(selectinload(Favorite.video))
        )
        result = await self.session.execute(query)
        favorites = list(result.scalars().all())
        videos = [f.video for f in favorites if f.video]

        return videos, total

    async def add_favorite(self, user_id: int, video_id: int) -> Favorite:
        """Add a video to the caller's favorites."""
        existing = await self.session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id, Favorite.video_id == video_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Video already in favorites")

        favorite = Favorite(user_id=user_id, video_id=video_id)
        self.session.add(favorite)
        await self.session.commit()
        await self.session.refresh(favorite)
        return favorite

    async def remove_favorite(self, user_id: int, video_id: int) -> None:
        """Remove a video from the caller's favorites."""
        result = await self.session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id, Favorite.video_id == video_id
            )
        )
        favorite = result.scalar_one_or_none()
        if not favorite:
            raise ValueError("Video not in favorites")

        await self.session.delete(favorite)
        await self.session.commit()

    async def is_favorite(self, user_id: int, video_id: int) -> bool:
        """Check if a video is in the caller's favorites."""
        result = await self.session.execute(
            select(Favorite.id).where(
                Favorite.user_id == user_id, Favorite.video_id == video_id
            )
        )
        return result.scalar_one_or_none() is not None
