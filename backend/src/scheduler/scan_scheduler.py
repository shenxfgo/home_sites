"""Periodic jobs inside the app process: source scans and the daily backup."""
import logging

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

#: 备份任务的固定 id：每天一条，重新挂载时靠它替换掉旧的。
BACKUP_JOB_ID = "backup_database"

#: 启动补跑的固定 id：一次性任务，跑完即走，重新挂载时同样靠它替换。
BACKUP_CATCHUP_JOB_ID = "backup_database_catchup"


class ScanScheduler:
    """Scheduler for the app's periodic work.

    The name says "scan" because scanning came first; the backup job lives here
    too on purpose. Two ``AsyncIOScheduler`` instances in one process would each
    fire their own copy of every job, and one of them would be a pg_dump.
    """

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

    def add_backup_job(self, time_of_day: str) -> None:
        """Arm the daily database backup at ``HH:MM`` (server local time)."""
        from src.backup import parse_time_of_day
        from src.scheduler.tasks import backup_database_task

        hour, minute = parse_time_of_day(time_of_day)
        self.remove_backup_job()
        self.scheduler.add_job(
            backup_database_task,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=BACKUP_JOB_ID,
            replace_existing=True,
            # 到点没跑成（机器睡着、事件循环被占住）也要在醒来的第一时间补上。
            # 默认宽限只有 1 秒：晚过一秒这一轮就整轮无声跳过，一天都不备份。
            misfire_grace_time=None,
            coalesce=True,
        )
        logger.info("Scheduled daily backup at %02d:%02d", hour, minute)

    def add_backup_catchup_job(self) -> None:
        """Arm a one-shot backup check that runs as soon as the loop starts.

        The nightly job only fires while the process is alive at that minute, and
        a *stopped* process never misfires — it just recomputes the next run on
        boot. This catches the case the grace time can't reach.
        """
        from src.scheduler.tasks import backup_catchup_task

        self.remove_backup_catchup_job()
        self.scheduler.add_job(
            backup_catchup_task,
            trigger=DateTrigger(),
            id=BACKUP_CATCHUP_JOB_ID,
            replace_existing=True,
            misfire_grace_time=None,
        )
        logger.info("Armed database backup catch-up check at startup")

    def remove_backup_catchup_job(self) -> None:
        """Drop the startup catch-up check, if it is armed."""
        try:
            self.scheduler.remove_job(BACKUP_CATCHUP_JOB_ID)
        except Exception:
            pass  # Job doesn't exist

    def remove_backup_job(self) -> None:
        """Drop the daily backup job, if it is armed."""
        try:
            self.scheduler.remove_job(BACKUP_JOB_ID)
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
