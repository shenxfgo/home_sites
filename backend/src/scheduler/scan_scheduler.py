"""Scan scheduler using APScheduler."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)


class ScanScheduler:
    """Scheduler for automatic video scanning."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_jobstore(MemoryJobStore(), default="memory")
        self._started = False

    def start(self) -> None:
        """Start the scheduler."""
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("Scan scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._started:
            self.scheduler.shutdown()
            self._started = False
            logger.info("Scan scheduler stopped")

    def add_source_job(self, source_id: int, interval: int) -> None:
        """Add a periodic scan job for a source."""
        from src.scheduler.tasks import scan_source_task

        job_id = f"scan_source_{source_id}"

        # Remove existing job if any
        self.remove_source_job(source_id)

        # Add new job
        self.scheduler.add_job(
            scan_source_task,
            trigger=IntervalTrigger(seconds=interval),
            id=job_id,
            args=[source_id],
            replace_existing=True,
        )
        logger.info("Scheduled scan job for source %d (interval: %ds)", source_id, interval)

    def remove_source_job(self, source_id: int) -> None:
        """Remove a scan job for a source."""
        job_id = f"scan_source_{source_id}"
        try:
            self.scheduler.remove_job(job_id)
            logger.info("Removed scan job for source %d", source_id)
        except Exception:
            pass  # Job doesn't exist

    def get_jobs(self) -> list[dict]:
        """Get all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._started


# Global scheduler instance
scheduler = ScanScheduler()
