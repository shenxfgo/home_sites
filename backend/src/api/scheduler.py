"""Scheduler management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database import get_session
from src.scheduler import scheduler
from src.models.source import VideoSource

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class JobResponse(BaseModel):
    """Response model for a scheduled job."""

    id: str
    name: str | None
    trigger: str
    next_run_time: str | None


class AddJobRequest(BaseModel):
    """Request model for adding a job."""

    source_id: int
    interval: int


class SchedulerStatusResponse(BaseModel):
    """Response model for scheduler status."""

    is_running: bool
    jobs_count: int


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs() -> list[JobResponse]:
    """List all scheduled jobs."""
    return scheduler.get_jobs()


@router.post("/jobs", status_code=201)
async def add_job(
    data: AddJobRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Add a scheduled scan job for a source."""
    # Verify source exists
    result = await session.execute(
        select(VideoSource).where(VideoSource.id == data.source_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    scheduler.add_source_job(data.source_id, data.interval)
    return {"message": f"Job added for source {data.source_id}"}


@router.delete("/jobs/{source_id}", status_code=204)
async def remove_job(source_id: int) -> None:
    """Remove a scheduled scan job."""
    scheduler.remove_source_job(source_id)


@router.get("/status", response_model=SchedulerStatusResponse)
async def get_status() -> SchedulerStatusResponse:
    """Get scheduler status."""
    return SchedulerStatusResponse(
        is_running=scheduler.is_running,
        jobs_count=len(scheduler.get_jobs()),
    )
