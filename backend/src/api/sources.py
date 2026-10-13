"""Source management API endpoints."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationInfo, field_serializer, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.setting_service import SCAN_INTERVAL_MAX, SCAN_INTERVAL_MIN
from src.services.source_service import SourceService
from src.storage.base import S3_SCHEME

router = APIRouter(prefix="/api/sources", tags=["sources"])

# 库里这五列全是 NOT NULL（`src/models/source.py`），所以差量 PUT 里的显式 null 只能收在
# 闸口（#211 ①甲）。放行它会走到 `UPDATE video_sources SET <列>=NULL`，数据库报
# NotNullViolation，而路由那句 `except ValueError` 接不住 SQLAlchemy 的 IntegrityError——真
# 服务器上就是一次 500；`path` 那格还更早在 `_check_path_shape` 里对 None 调 `.startswith`
# 就 AttributeError。键是接口字段名（422 的 loc 用它），值是那句中文里的主语。
_NOT_NULL_COLUMN_LABELS = {
    "name": "名称",
    "path": "路径",
    "type": "类型",
    "scan_interval": "扫描间隔",
    "is_active": "启用状态",
}


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
    # 没填 = 用系统配置里那一项，而不是这里再写死一个 3600：一个默认值只该有一个
    # 出处。区间和设置页那一项共用同一对常量。
    scan_interval: int | None = Field(
        default=None, ge=SCAN_INTERVAL_MIN, le=SCAN_INTERVAL_MAX
    )
    is_active: bool = Field(default=True)


class SourceUpdate(BaseModel):
    """Request model for updating a source."""

    name: str | None = Field(None, min_length=1, max_length=255)
    path: str | None = Field(None, min_length=1, max_length=1024)
    type: Literal["local", "nas", "minio"] | None = None
    scan_interval: int | None = Field(
        None, ge=SCAN_INTERVAL_MIN, le=SCAN_INTERVAL_MAX
    )
    is_active: bool | None = None

    # 字段清单就从那张表出生：列和中文名不可能各走各的（少一个键就是 500，而不是
    # 一句看不见的漏拦）。
    @field_validator(*_NOT_NULL_COLUMN_LABELS)
    @classmethod
    def _not_null_columns_cannot_be_cleared(
        cls, value: object, info: ValidationInfo
    ) -> object:
        """「省略」是不改，「显式 null」是清空，而这一列清不得。

        闸口只在值真被送来时才跑——pydantic 不校验默认值，所以界面那种只带改动项的差量
        body 照旧合法（那格由用例钉着）。
        """
        if value is None:
            raise PydanticCustomError(
                "cannot_be_cleared",
                "{label}不能留空",
                # 清单就是从这张表生的，所以 field_name 既不会是 None，也不会缺键。
                {"label": _NOT_NULL_COLUMN_LABELS[str(info.field_name)]},
            )
        return value


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
        raise HTTPException(status_code=404, detail="视频源不存在")
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
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

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
