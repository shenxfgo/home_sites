"""Tag management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.videos import VideoResponse
from src.database import get_session
from src.services.tag_service import BlankTagNameError, DuplicateTagNameError, TagService

router = APIRouter(prefix="/api/tags", tags=["tags"])

# 库里这两列都是 NOT NULL（`src/models/tag.py`），而 `color` 那格是界面点得到的：
# `Tags.vue` 的 `el-color-picker` 自带清空按钮，实测点它再点更新，PUT body 就是
# `{"color": null}`（#211 ②甲）。显式 null 放行到 `setattr` 之后就是 NotNullViolation，
# 路由那句 `except ValueError` 接不住 IntegrityError——真服务器上是一次 500。
_NOT_NULL_COLUMN_LABELS = {"name": "标签名", "color": "颜色"}


class TagCreate(BaseModel):
    """Request model for creating a tag."""

    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#409eff", pattern="^#[0-9a-fA-F]{6}$")


class TagUpdate(BaseModel):
    """Request model for updating a tag."""

    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")

    # 字段清单就从那张表出生：列和中文名不可能各走各的（漏一个键就是一次 500，
    # 而不是一句看不见的漏拦）。
    @field_validator(*_NOT_NULL_COLUMN_LABELS)
    @classmethod
    def _not_null_columns_cannot_be_cleared(
        cls, value: object, info: ValidationInfo
    ) -> object:
        """「省略」是不改，「显式 null」是清空，而这两列都清不得。

        界面上那个清空按钮由 `Tags.vue` 归回默认色（#211 ②甲），这道闸口管的是别的客户端
        ——包括 `name` 那一格结构上永远不该发生的清空。
        """
        if value is None:
            raise PydanticCustomError(
                "cannot_be_cleared",
                "{label}不能留空",
                # 清单就是从这张表生的，所以 field_name 既不会是 None，也不会缺键。
                {"label": _NOT_NULL_COLUMN_LABELS[str(info.field_name)]},
            )
        return value


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
    try:
        return await service.create(name=data.name, color=data.color)
    except DuplicateTagNameError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except BlankTagNameError as e:
        # 裁完就没了的名字和 `min_length=1` 挡不住的空白是同一件事，回 400 带原因。
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: int,
    service: TagService = Depends(get_tag_service),
) -> TagResponse:
    """Get a specific tag."""
    tag = await service.get_by_id(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
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
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    try:
        return await service.update(tag_id, **update_data)
    except DuplicateTagNameError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except BlankTagNameError as e:
        # 必须排在下面那条 `except ValueError` 之前：它也是 ValueError，
        # 晚一步就会被当成「标签不存在」的 404 吞掉。
        raise HTTPException(status_code=400, detail=str(e))
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
