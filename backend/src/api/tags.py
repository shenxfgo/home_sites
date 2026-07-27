"""Tag management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.tag_service import TagService
from src.api.videos import VideoResponse

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagCreate(BaseModel):
    """Request model for creating a tag."""

    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#409eff", pattern="^#[0-9a-fA-F]{6}$")


class TagUpdate(BaseModel):
    """Request model for updating a tag."""

    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")


class TagResponse(BaseModel):
    """Response model for a tag."""

    id: int
    name: str
    color: str
    video_count: int = 0

    model_config = {"from_attributes": True}


class AddTagsRequest(BaseModel):
    """Request model for adding tags to video."""

    tag_ids: list[int]


async def get_tag_service(
    session: AsyncSession = Depends(get_session),
) -> TagService:
    """Dependency to get TagService instance."""
    return TagService(session)


@router.get("", response_model=list[TagResponse])
async def list_tags(
    service: TagService = Depends(get_tag_service),
) -> list[TagResponse]:
    """List all tags with video counts."""
    tags_with_counts = await service.list_all_with_counts()
    return [
        TagResponse(id=tag.id, name=tag.name, color=tag.color, video_count=count)
        for tag, count in tags_with_counts
    ]


@router.post("", response_model=TagResponse, status_code=201)
async def create_tag(
    data: TagCreate,
    service: TagService = Depends(get_tag_service),
) -> TagResponse:
    """Create a new tag."""
    return await service.create(name=data.name, color=data.color)


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: int,
    service: TagService = Depends(get_tag_service),
) -> TagResponse:
    """Get a specific tag."""
    tag = await service.get_by_id(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    service: TagService = Depends(get_tag_service),
) -> TagResponse:
    """Update a tag."""
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        return await service.update(tag_id, **update_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    service: TagService = Depends(get_tag_service),
) -> None:
    """Delete a tag."""
    try:
        await service.delete(tag_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{tag_id}/videos", response_model=list[VideoResponse])
async def get_tag_videos(
    tag_id: int,
    service: TagService = Depends(get_tag_service),
) -> list[VideoResponse]:
    """Get all videos with a specific tag."""
    try:
        return await service.get_videos_by_tag(tag_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/video/{video_id}", status_code=204)
async def add_tags_to_video(
    video_id: int,
    data: AddTagsRequest,
    service: TagService = Depends(get_tag_service),
) -> None:
    """Add tags to a video."""
    try:
        await service.add_tags_to_video(video_id, data.tag_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/video/{video_id}/{tag_id}", status_code=204)
async def remove_tag_from_video(
    video_id: int,
    tag_id: int,
    service: TagService = Depends(get_tag_service),
) -> None:
    """Remove a tag from a video."""
    try:
        await service.remove_tag_from_video(video_id, tag_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
