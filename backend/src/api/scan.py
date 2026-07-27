"""Scan service API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.services.scan_service import ScanService

router = APIRouter(prefix="/api", tags=["scan"])


class ScanResultResponse(BaseModel):
    """Response model for scan results."""

    source_id: int | None = None
    files_found: int = 0
    new_videos: int = 0
    sources_scanned: int | None = None
    total_files: int | None = None
    total_new_videos: int | None = None


class ScanProgressResponse(BaseModel):
    """Response model for scan progress."""

    is_scanning: bool
    current_source: str | None = None
    sources_total: int = 0
    sources_completed: int = 0
    files_found: int = 0
    new_videos: int = 0


async def get_scan_service(
    session: AsyncSession = Depends(get_session),
) -> ScanService:
    """Dependency to get ScanService instance."""
    return ScanService(session)


@router.post("/sources/{source_id}/scan", response_model=ScanResultResponse)
async def scan_source(
    source_id: int,
    service: ScanService = Depends(get_scan_service),
) -> ScanResultResponse:
    """Scan a single video source for new videos."""
    try:
        result = await service.scan_source(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ScanResultResponse(**result)


@router.post("/scan/all", response_model=ScanResultResponse)
async def scan_all(
    service: ScanService = Depends(get_scan_service),
) -> ScanResultResponse:
    """Scan all active video sources."""
    result = await service.scan_all_active()
    return ScanResultResponse(**result)


@router.get("/scan/progress", response_model=ScanProgressResponse)
async def get_scan_progress(
    service: ScanService = Depends(get_scan_service),
) -> ScanProgressResponse:
    """Get the current scan progress."""
    progress = service.get_scan_progress()
    return ScanProgressResponse(**progress)


@router.post("/scan/stop", status_code=200)
async def stop_scan(
    service: ScanService = Depends(get_scan_service),
) -> dict:
    """Stop the current scan."""
    await service.stop_scan()
    return {"status": "ok"}
