"""TagService for tag CRUD operations."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.tag import Tag, video_tags
from src.models.video import Video


class DuplicateTagNameError(ValueError):
    """A tag already carries that name.

    ``tags.name`` is unique at the database level and renaming is a click away
    in the UI, so the routes answer 409 instead of letting the IntegrityError
    surface as a 500 — and instead of leaving the session poisoned for the
    request that follows.
    """


class TagService:
    """Service for managing tags."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _existing_tag_id(self, name: str) -> int | None:
        """Return the id of the tag already carrying ``name``, if any."""
        result = await self.session.execute(select(Tag.id).where(Tag.name == name))
        return result.scalar_one_or_none()

    async def create(self, name: str, color: str = "#409eff") -> Tag:
        """Create a new tag."""
        if await self._existing_tag_id(name) is not None:
            raise DuplicateTagNameError(f"标签「{name}」已存在")

        tag = Tag(name=name, color=color)
        self.session.add(tag)
        await self.session.commit()
        await self.session.refresh(tag)
        return tag

    async def get_by_id(self, tag_id: int) -> Tag | None:
        """Get a tag by ID."""
        result = await self.session.execute(
            select(Tag).where(Tag.id == tag_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Tag]:
        """List all tags."""
        result = await self.session.execute(select(Tag))
        return list(result.scalars().all())

    async def list_all_with_counts(self) -> list[tuple[Tag, int]]:
        """List all tags with their associated video counts."""
        result = await self.session.execute(
            select(Tag, func.count(video_tags.c.video_id).label("video_count"))
            .outerjoin(video_tags, Tag.id == video_tags.c.tag_id)
            .group_by(Tag.id)
            .order_by(Tag.name)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def update(self, tag_id: int, **kwargs: object) -> Tag:
        """Update a tag."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            raise ValueError(f"Tag with id {tag_id} not found")

        new_name = kwargs.get("name")
        if isinstance(new_name, str) and new_name != tag.name:
            if await self._existing_tag_id(new_name) is not None:
                raise DuplicateTagNameError(f"标签「{new_name}」已存在")

        for key, value in kwargs.items():
            if hasattr(tag, key):
                setattr(tag, key, value)

        await self.session.commit()
        await self.session.refresh(tag)
        return tag

    async def delete(self, tag_id: int) -> None:
        """Delete a tag."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            raise ValueError(f"Tag with id {tag_id} not found")

        await self.session.delete(tag)
        await self.session.commit()

    async def get_videos_by_tag(self, tag_id: int) -> list[Video]:
        """Get all videos with a specific tag."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            raise ValueError(f"Tag with id {tag_id} not found")

        result = await self.session.execute(
            select(Tag).where(Tag.id == tag_id).options(selectinload(Tag.videos))
        )
        tag = result.scalar_one()
        return list(tag.videos)

    async def add_tags_to_video(self, video_id: int, tag_ids: list[int]) -> None:
        """Add multiple tags to a video."""
        result = await self.session.execute(
            select(Video).where(Video.id == video_id).options(selectinload(Video.tags))
        )
        video = result.scalar_one_or_none()
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        for tag_id in tag_ids:
            tag = await self.get_by_id(tag_id)
            if tag and tag not in video.tags:
                video.tags.append(tag)

        await self.session.commit()

    async def remove_tag_from_video(self, video_id: int, tag_id: int) -> None:
        """Remove a tag from a video."""
        result = await self.session.execute(
            select(Video).where(Video.id == video_id).options(selectinload(Video.tags))
        )
        video = result.scalar_one_or_none()
        if not video:
            raise ValueError(f"Video with id {video_id} not found")

        tag = await self.get_by_id(tag_id)
        if tag and tag in video.tags:
            video.tags.remove(tag)
            await self.session.commit()
