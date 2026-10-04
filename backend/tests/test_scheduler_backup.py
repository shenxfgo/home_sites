# tests/test_scheduler_backup.py
"""备份挂上去的三种方式都要有人守：每天一条（且只有一条）、醒来不跳过、启动会补跑。

成功不发通知是刻意的——#85 刚把"每晚一条心跳"删掉，备份成功每天都是同一句话。
所以"成功时 notifications 为空"这条反向断言和失败通知一样重要。
"""

from sqlalchemy import select

from src import backup
from src.models.notification import Notification
from src.scheduler import tasks as task_module
from src.scheduler.scan_scheduler import (
    BACKUP_CATCHUP_JOB_ID,
    BACKUP_JOB_ID,
    ScanScheduler,
)
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


def test_the_nightly_job_is_not_skipped_when_the_machine_wakes_late():
    """默认宽限 1 秒：睡着半小时醒来，这一轮就被无声跳过，一整天没有备份。"""
    instance = ScanScheduler()
    instance.add_backup_job("03:30")

    job = next(job for job in instance.scheduler.get_jobs() if job.id == BACKUP_JOB_ID)
    assert job.misfire_grace_time is None
    assert job.coalesce is True


def test_the_catchup_job_is_armed_once():
    """重启一次装一条，装两条就是启动即两遍 pg_dump。"""
    instance = ScanScheduler()
    instance.add_backup_catchup_job()
    instance.add_backup_catchup_job()

    jobs = [
        job for job in instance.scheduler.get_jobs() if job.id == BACKUP_CATCHUP_JOB_ID
    ]
    assert len(jobs) == 1
    assert str(jobs[0].trigger).startswith("date[")


def test_removing_an_unarmed_catchup_job_is_quiet():
    ScanScheduler().remove_backup_catchup_job()


async def test_a_stale_backup_dir_is_fixed_at_startup(tmp_path, monkeypatch):
    """目录里一个能读的备份都没有（装好没到过 03:30、目录被清过、关机好几天），
    启动就得先补一趟，而不是等下一个夜晚。"""
    calls = _backup_dir(monkeypatch, tmp_path)

    await task_module.backup_catchup_task()

    assert len(calls) == 1
    assert calls[0]["backup_dir"] == str(tmp_path)


async def test_a_recent_dump_means_startup_says_and_does_nothing(tmp_path, monkeypatch):
    """昨夜好好的时候启动不能顺手再 dump 一遍——那是第二份内容和第二轮轮转。"""
    (tmp_path / "home_sites_20261005T033000Z.dump").write_bytes(b"x")
    calls = _backup_dir(monkeypatch, tmp_path)

    await task_module.backup_catchup_task()

    assert calls == []


async def test_a_failing_catchup_says_which_run_it_was(
    db_session, tmp_path, monkeypatch
):
    """补跑也失败时，标题要看得出这是启动补的那趟，而不是昨夜定时的。"""
    task_module_shared(monkeypatch, db_session)
    _backup_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(backup, "run_backup", _explode)

    await task_module.backup_catchup_task()

    rows = (
        await db_session.execute(select(Notification).order_by(Notification.id))
    ).scalars().all()
    assert [row.type for row in rows] == ["backup_error"]
    assert rows[0].title == "补跑数据库备份失败"


def task_module_shared(monkeypatch, session) -> None:
    """让调度任务复用用例的连接，而不是去连真库。"""
    monkeypatch.setattr(task_module, "async_session_maker", _SharedSession(session))


def _backup_dir(monkeypatch, tmp_path) -> list[dict]:
    """把任务读到的备份目录按到用例目录上，并截下每一次真跑出去的备份。"""
    calls: list[dict] = []

    def fake_run_backup(**kwargs):
        calls.append(kwargs)
        return str(tmp_path / "home_sites_20261005T033000Z.dump")

    monkeypatch.setattr(task_module.settings, "backup_dir", str(tmp_path))
    monkeypatch.setattr(backup, "run_backup", fake_run_backup)
    return calls


def _explode(**_kwargs) -> str:
    raise RuntimeError("pg_dump 没找到")
