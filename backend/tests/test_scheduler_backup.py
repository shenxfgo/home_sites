# tests/test_scheduler_backup.py
"""每日备份的两件事：任务挂得上（且只挂一条），失败必须变成一条看得见的通知。

成功不发通知是刻意的——#85 刚把"每晚一条心跳"删掉，备份成功每天都是同一句话。
所以"成功时 notifications 为空"这条反向断言和失败通知一样重要。
"""

from sqlalchemy import select

from src import backup
from src.models.notification import Notification
from src.scheduler import tasks as task_module
from src.scheduler.scan_scheduler import BACKUP_JOB_ID, ScanScheduler
from tests.conftest import _SharedSession


def test_backup_job_is_armed_once_and_replaced_on_rearm():
    """改时刻不能留下两条：每天两次 pg_dump 会写两份、也清两份。"""
    instance = ScanScheduler()
    instance.add_backup_job("03:30")
    instance.add_backup_job("04:15")

    jobs = [job for job in instance.scheduler.get_jobs() if job.id == BACKUP_JOB_ID]
    assert len(jobs) == 1
    assert str(jobs[0].trigger) == "cron[hour='4', minute='15']"


def test_removing_an_unarmed_backup_job_is_quiet():
    """启动时先拆后装是常态，拆不到东西不该炸。"""
    ScanScheduler().remove_backup_job()


async def test_a_failing_backup_shows_up_as_a_notification(db_session, monkeypatch):
    """备份失败的唯一出路就是让人看见，否则目录里的旧文件看着都挺正常。"""
    task_module_shared(monkeypatch, db_session)
    monkeypatch.setattr(backup, "run_backup", _explode)

    await task_module.backup_database_task()

    rows = (
        await db_session.execute(select(Notification).order_by(Notification.id))
    ).scalars().all()
    assert [row.type for row in rows] == ["backup_error"]
    assert "pg_dump 没找到" in rows[0].message
    assert rows[0].data["error"] == "pg_dump 没找到"


async def test_a_healthy_backup_says_nothing(db_session, monkeypatch):
    task_module_shared(monkeypatch, db_session)
    monkeypatch.setattr(backup, "run_backup", lambda **_kwargs: "/tmp/home_sites.dump")

    await task_module.backup_database_task()

    assert (
        await db_session.execute(select(Notification))
    ).scalars().all() == []


async def test_a_notification_that_cannot_be_written_does_not_kill_the_job(
    db_session, monkeypatch
):
    """写通知这一步也炸的时候异常不能冒回调度器——任务被永久移除比丢一条通知严重。"""
    task_module_shared(monkeypatch, db_session)
    monkeypatch.setattr(backup, "run_backup", _explode)

    async def broken_create(*_args, **_kwargs):
        raise RuntimeError("库也连不上")

    monkeypatch.setattr(task_module.NotificationService, "create", broken_create)

    await task_module.backup_database_task()  # 不抛异常，本身就是断言


def task_module_shared(monkeypatch, session) -> None:
    """让调度任务复用用例的连接，而不是去连真库。"""
    monkeypatch.setattr(task_module, "async_session_maker", _SharedSession(session))


def _explode(**_kwargs) -> str:
    raise RuntimeError("pg_dump 没找到")
