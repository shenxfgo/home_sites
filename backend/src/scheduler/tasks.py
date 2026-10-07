"""Scheduled tasks: source scans and the daily database backup."""
import asyncio
import logging

from src import backup
from src.config import settings
from src.database import async_session_maker
from src.services.notification_service import NotificationService
from src.services.scan_service import ScanService
from src.services.setting_service import SettingService

logger = logging.getLogger(__name__)

# 扫描完成的通知由 ScanService.scan_source 自己发（库里变了才发）。这里只负责
# 把异常变成一条通知：任务要是也发一条，一轮定时扫描就会对同一次扫描说两遍。


async def scan_source_task(source_id: int) -> None:
    """Task to scan a specific video source."""
    async with async_session_maker() as session:
        # 设置页那个「自动扫描」开关管的就是这一行：关了整轮不走。放在任务里而不是
        # ScanService 里，是因为人按「扫描」按钮那一下从来不该归这个开关管。
        if not await SettingService(session).is_auto_scan_enabled():
            return
        try:
            service = ScanService(session)
            await service.scan_source(source_id)
        except Exception as e:
            logger.exception("Scheduled scan failed for source %d", source_id)
            # 先把会话倒干净再写通知：扫描要是死在 flush 上（撞唯一约束就是这样），
            # 会话就带着 PendingRollback 状态到了这里，紧接着的 INSERT 只会再抛一次，
            # 被下面那个 `except` 吞掉——于是"失败一定发通知"这条路径在最需要它的
            # 那种失败上是死的。真机上的现场就是 0 条 scan_error 配上一整日志的
            # IntegrityError 回溯。
            await session.rollback()
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
        # 这一路目前没有挂载点（`main.py` 只按源挂），闸门照加：将来它被挂上去的
        # 时候，设置页那个开关不能再是第二次装饰。
        if not await SettingService(session).is_auto_scan_enabled():
            return
        try:
            service = ScanService(session)
            await service.scan_all_active()
        except Exception as e:
            logger.exception("Full active scan failed")
            await session.rollback()  # 同上：脏会话写不进通知
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
    just removed. Failure is worth announcing; that "nothing was announced" and
    "nothing ever ran" look the same is what :func:`backup_catchup_task` is for.
    """
    await _dump_and_notify("每日")


async def backup_catchup_task() -> None:
    """One dump at startup when the database has gone without one for too long.

    The nightly cron fires only if the process is alive at that minute, and a
    process that was simply *off* never even misfires — it recomputes tomorrow's
    run on boot. Nothing says "there has been no backup for four days" louder
    than a fresh dump, or the failure to produce one.

    Only armed on PostgreSQL (see ``main.py``), so no dialect check here.
    """
    if not backup.is_stale(settings.backup_dir):
        return
    await _dump_and_notify("补跑")


async def _dump_and_notify(kind: str) -> None:
    """Run one backup; announce only the failure, prefixed by which job ran it."""
    try:
        await asyncio.to_thread(
            backup.run_backup,
            database_url=settings.database_url,
            backup_dir=settings.backup_dir,
            keep_days=settings.backup_keep_days,
            pg_bindir=settings.pg_bindir,
        )
    except Exception as e:
        logger.exception("Database backup failed (%s)", kind)
        try:
            async with async_session_maker() as session:
                await NotificationService(session).create(
                    type="backup_error",
                    title=f"{kind}数据库备份失败",
                    message=f"PostgreSQL 备份没有完成: {e}",
                    data={"error": str(e), "kind": kind},
                )
        except Exception:
            logger.exception("Failed to create the backup error notification")
