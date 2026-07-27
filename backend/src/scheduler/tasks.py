"""Scheduled tasks for scanning."""
import logging

from src.database import async_session_maker
from src.services.scan_service import ScanService
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def scan_source_task(source_id: int) -> None:
    """Task to scan a specific video source."""
    async with async_session_maker() as session:
        try:
            service = ScanService(session)
            result = await service.scan_source(source_id)

            # Create notification
            notification_service = NotificationService(session)
            await notification_service.create(
                type="scheduled_scan",
                title="定时扫描完成",
                message=f"视频源扫描完成，发现 {result.get('new_videos', 0)} 个新视频",
                data=result,
            )
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
            result = await service.scan_all_active()

            # Create notification
            notification_service = NotificationService(session)
            await notification_service.create(
                type="scheduled_scan",
                title="全量扫描完成",
                message=f"所有视频源扫描完成，共发现 {result.get('total_new_videos', 0)} 个新视频",
                data=result,
            )
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
