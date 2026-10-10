"""Video management API endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_serializer, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.middleware.auth import get_current_user_id
from src.models.tag import Tag
from src.services.video_service import VideoService

router = APIRouter(prefix="/api/videos", tags=["videos"])


# Pydantic models for request/response
class TagResponse(BaseModel):
    """Response model for a tag."""

    id: int
    name: str
    color: str

    model_config = {"from_attributes": True}


class VideoResponse(BaseModel):
    """Response model for a video."""

    id: int
    source_id: int
    filepath: str
    title: str | None
    description: str | None
    duration: int | None
    file_size: int | None
    format: str | None
    resolution: str | None
    thumbnail_path: str | None
    series: str | None = None
    season: int | None = None
    episode: int | None = None
    #: The last scan could not find the file on disk.
    is_missing: bool = False
    rating: int
    view_count: int
    is_new: bool = False
    progress: int | None = None  # seconds watched, for the resume rail
    last_played_at: datetime | None
    created_at: datetime
    updated_at: datetime
    tags: list[TagResponse] = []

    model_config = {"from_attributes": True}

    @field_serializer("last_played_at", "created_at", "updated_at")
    @staticmethod
    def serialize_datetime(value: datetime | None) -> str | None:
        """Serialize datetime to ISO format string."""
        if value is None:
            return None
        return value.isoformat()


class VideoUpdate(BaseModel):
    """Request model for updating a video."""

    title: str | None = Field(None, min_length=1, max_length=512)
    description: str | None = None
    rating: int | None = Field(None, ge=0, le=5)
    tag_ids: list[int] | None = None

    @field_validator("rating")
    @classmethod
    def _rating_cannot_be_cleared(cls, value: int | None) -> int:
        """`videos.rating` 是 NOT NULL，所以这一列的 null 只能收在闸口。

        放行它会走到 `UPDATE videos SET rating=NULL`，数据库报 NotNullViolation，而路由那句
        `except ValueError` 接不住 SQLAlchemy 的 IntegrityError——真服务器上就是一次 500。
        界面上"清空评分"本来就是点回 0 星，不是一个缺值状态。标题和简介那一列可以为空，
        所以那两列照旧收 null。
        """
        if value is None:
            raise ValueError("评分不能留空：要清空请填 0")
        return value


class VideoListResponse(BaseModel):
    """Paginated video list response."""

    items: list[VideoResponse]
    total: int
    page: int
    page_size: int


class SeriesProgressResponse(BaseModel):
    """How far one parsed series has been watched."""

    series: str
    total: int
    finished: int
    watched: int
    next: VideoResponse | None = None

    model_config = {"from_attributes": True}


class DuplicateGroupResponse(BaseModel):
    """Library entries confirmed to hold the same bytes."""

    file_size: int
    duration: int | None
    count: int
    #: Bytes freed if every copy but the first is deleted.
    wasted_bytes: int
    #: The entry the scan would keep: the copy with the richest watch history.
    keep_id: int
    #: Copies, ``keep_id`` first.
    items: list[VideoResponse]

    model_config = {"from_attributes": True}


class ProgressRequest(BaseModel):
    """Request model for reporting playback progress."""

    progress: int = Field(..., ge=0, description="Playback progress in seconds")


async def get_video_service(
    session: AsyncSession = Depends(get_session),
) -> VideoService:
    """Dependency to get VideoService instance."""
    return VideoService(session)


@router.get("", response_model=VideoListResponse)
async def list_videos(
    source_id: int | None = None,
    tag_id: int | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> VideoListResponse:
    """Get paginated video list with optional filtering."""
    videos, total = await service.get_videos(
        user_id,
        source_id=source_id,
        tag_id=tag_id,
        search=search,
        page=page,
        page_size=page_size,
    )
    return VideoListResponse(
        items=videos,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/new", response_model=list[VideoResponse])
async def list_new_videos(
    source_id: int | None = None,
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> list[VideoResponse]:
    """Get the titles this account has not looked at yet."""
    videos = await service.get_new_videos(user_id, source_id=source_id)
    return videos


@router.get("/series", response_model=list[SeriesProgressResponse])
async def list_series_progress(
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> list[SeriesProgressResponse]:
    """Get every recognised series with how many episodes this account finished."""
    return await service.get_series_progress(user_id)


@router.get("/duplicates", response_model=list[DuplicateGroupResponse])
async def list_duplicates(
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> list[DuplicateGroupResponse]:
    """Report library entries whose files were confirmed byte-identical.

    Read-only, and on demand: it opens video files to hash them, which is far
    too slow to run while the home page loads.
    """
    return await service.get_duplicates(user_id)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: int,
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> VideoResponse:
    """Get a specific video."""
    video = await service.get_video_by_id(video_id, user_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    return video


@router.put("/{video_id}", response_model=VideoResponse)
async def update_video(
    video_id: int,
    data: VideoUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> VideoResponse:
    """Update video information."""
    update_data = data.model_dump(exclude_unset=True)

    # Handle tag assignment separately
    tag_ids = update_data.pop("tag_ids", None)

    if not update_data and tag_ids is None:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    # Resolve the tag list first: a request that names a tag which no longer exists is
    # refused as a whole, before any half of it has been written. The assignment below
    # replaces the entire set, so an unknown id left unchecked would quietly wipe the
    # tags this video already had.
    new_tags: list[Tag] | None = None
    if tag_ids is not None:
        result = await session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        new_tags = list(result.scalars().all())
        missing = sorted(set(tag_ids) - {tag.id for tag in new_tags})
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"标签不存在：{', '.join(str(tag_id) for tag_id in missing)}",
            )

    # Update basic fields
    if update_data:
        try:
            video = await service.update_video(video_id, user_id, **update_data)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        video = await service.get_video_by_id(video_id, user_id)
        if not video:
            raise HTTPException(status_code=404, detail="视频不存在")

    # Handle tag assignment
    if new_tags is not None:
        video.tags = new_tags
        await session.commit()
        await session.refresh(video)

    return video


@router.delete("/{video_id}", status_code=204)
async def delete_video(
    video_id: int,
    service: VideoService = Depends(get_video_service),
) -> None:
    """Delete a video."""
    try:
        await service.delete_video(video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/new/{video_id}/viewed", status_code=200)
async def mark_new_video_viewed(
    video_id: int,
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> dict:
    """Clear the new badge for this account only."""
    await service.mark_video_viewed(user_id, video_id)
    return {"status": "ok"}


@router.post("/{video_id}/play", status_code=200)
async def record_play(
    video_id: int,
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> dict:
    """Record that this account started playing a video."""
    try:
        await service.record_play(user_id, video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}


@router.post("/{video_id}/progress", status_code=200)
async def report_progress(
    video_id: int,
    data: ProgressRequest,
    user_id: int = Depends(get_current_user_id),
    service: VideoService = Depends(get_video_service),
) -> dict:
    """Report this account's playback progress."""
    try:
        await service.update_progress(user_id, video_id, data.progress)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok"}
