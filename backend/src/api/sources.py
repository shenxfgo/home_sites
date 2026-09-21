"""Source management API endpoints."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.source_service import SourceService
from src.storage.base import S3_SCHEME

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _check_path_shape(source_type: str, path: str) -> None:
    """Reject a path that contradicts its own type.

    The scanner picks a storage backend from ``type``, so a ``minio`` source
    typed as a folder scans nothing and an ``s3://`` path under ``local`` walks a
    directory named "s3:". Neither raises, they just come back empty.
    """
    looks_like_object_store = path.startswith(S3_SCHEME)
    if source_type == "minio" and not looks_like_object_store:
        raise HTTPException(
            status_code=400,
            detail=(
                f"对象存储视频源的路径需要以 {S3_SCHEME} 开头，"
                f"例如 {S3_SCHEME}my-videos/shows"
            ),
        )
    if source_type != "minio" and looks_like_object_store:
        raise HTTPException(
            status_code=400,
            detail=(
                "本地或 NAS 视频源请填写磁盘路径（如 D:\\videos 或 \\\\nas\\media）；"
                f"对象存储地址请把类型改为 MinIO（{S3_SCHEME} 开头）"
            ),
        )


# Pydantic models for request/response
class SourceCreate(BaseModel):
    """Request model for creating a source."""

    name: str = Field(..., min_length=1, max_length=255)
    path: str = Field(..., min_length=1, max_length=1024)
    type: Literal["local", "nas", "minio"]
    scan_interval: int = Field(default=3600, ge=60, le=86400)
    is_active: bool = Field(default=True)


class SourceUpdate(BaseModel):
    """Request model for updating a source."""

    name: str | None = Field(None, min_length=1, max_length=255)
    path: str | None = Field(None, min_length=1, max_length=1024)
    type: Literal["local", "nas", "minio"] | None = None
    scan_interval: int | None = Field(None, ge=60, le=86400)
    is_active: bool | None = None


class SourceResponse(BaseModel):
    """Response model for a source."""

    id: int
    name: str
    path: str
    type: str  # noqa: A003
    scan_interval: int
    last_scan_at: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("last_scan_at", "created_at")
    @staticmethod
    def serialize_datetime(value: datetime | None) -> str | None:
        """Serialize datetime to ISO format string."""
        if value is None:
            return None
        return value.isoformat()


async def get_source_service(
    session: AsyncSession = Depends(get_session),
) -> SourceService:
    """Dependency to get SourceService instance."""
    return SourceService(session)


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    active_only: bool = False,
    service: SourceService = Depends(get_source_service),
) -> list[SourceResponse]:
    """List all video sources."""
    sources = await service.list_all(active_only=active_only)
    return sources


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(
    data: SourceCreate,
    service: SourceService = Depends(get_source_service),
) -> SourceResponse:
    """Create a new video source."""
    _check_path_shape(data.type, data.path)
    source = await service.create(
        name=data.name,
        path=data.path,
        type=data.type,
        scan_interval=data.scan_interval,
        is_active=data.is_active,
    )
    return source


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: int,
    service: SourceService = Depends(get_source_service),
) -> SourceResponse:
    """Get a specific video source."""
    source = await service.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int,
    data: SourceUpdate,
    service: SourceService = Depends(get_source_service),
) -> SourceResponse:
    """Update a video source."""
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Half an edit is enough to break the pairing, so validate the values the
    # source would end up with, not just the ones the request happens to carry.
    if "type" in update_data or "path" in update_data:
        existing = await service.get_by_id(source_id)
        if existing:
            _check_path_shape(
                update_data.get("type", existing.type),
                update_data.get("path", existing.path),
            )

    try:
        source = await service.update(source_id, **update_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    service: SourceService = Depends(get_source_service),
) -> None:
    """Delete a video source."""
    try:
        await service.delete(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
