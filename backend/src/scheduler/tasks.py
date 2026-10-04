"""Scheduled tasks: source scans and the daily database backup."""
import asyncio
import logging

from src import backup
from src.config import settings
from src.database import async_session_maker
from src.services.scan_service import ScanService
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# 扫描完成的通知由 ScanService.scan_source 自己发（库里变了才发）。这里只负责
# 把异常变成一条通知：任务要是也发一条，一轮定时扫描就会对同一次扫描说两遍。


async def scan_source_task(source_id: int) -> None:
    """Task to scan a specific video source."""
    async with async_session_maker() as session:
        try:
            service = ScanService(session)
            await service.scan_source(source_id)
        except Exception as e:
            logger.exception("Scheduled scan failed for source %d", source_id)
            # Log error and create error notification
            try:
                notification_service = NotificationService(session)
                await notification_service.create(
                    type="scan_error",
                    title="定时扫描失败",
                    message=f"视频源扫描失败: {str(e)}",
                    data={"source_id": source_id, "error": str(e)},
                )
            except Exception:
                logger.exception("Failed to create error notification for source %d", source_id)


async def scan_all_active_task() -> None:
    """Task to scan all active video sources."""
    async with async_session_maker() as session:
        try:
            service = ScanService(session)
            await service.scan_all_active()
        except Exception as e:
            logger.exception("Full active scan failed")
            try:
                notification_service = NotificationService(session)
                await notification_service.create(
                    type="scan_error",
                    title="全量扫描失败",
                    message=f"全量扫描失败: {str(e)}",
                    data={"error": str(e)},
                )
            except Exception:
                logger.exception("Failed to create error notification for full scan")


async def backup_database_task() -> None:
    """Daily ``pg_dump``, run off the event loop.

    Success is silent — a notification every night would be the heartbeat #85
    just removed. Failure is the change worth announcing, and it is the only way
    anyone learns the backups stopped: the dump files themselves look fine.
    """
    try:
        await asyncio.to_thread(
            backup.run_backup,
            database_url=settings.database_url,
            backup_dir=settings.backup_dir,
            keep_days=settings.backup_keep_days,
            pg_bindir=settings.pg_bindir,
        )
    except Exception as e:
        logger.exception("Scheduled database backup failed")
        try:
            async with async_session_maker() as session:
                await NotificationService(session).create(
                    type="backup_error",
                    title="每日数据库备份失败",
                    message=f"PostgreSQL 备份没有完成: {e}",
                    data={"error": str(e)},
                )
        except Exception:
            logger.exception("Failed to create the backup error notification")
