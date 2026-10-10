# tests/test_scheduler_scan.py
"""定时扫描的失败必须落到人能看见的地方——这一条此前是死代码。

`scan_source_task` 与 `scan_all_active_task` 都写了"异常就发一条 `scan_error`
通知"，可它复用的正是刚失败的那个会话：`flush()` 撞了唯一约束之后会话进入
PendingRollback 状态，紧接着的 INSERT 只会再抛一次，于是被内层的 `except` 吞掉。
真机上的现场是 `notifications` 里 0 条 `scan_error`，而 stderr 每 30 分钟重复一段
`IntegrityError`——失败一直在发生，只是没人能看见。

下面那两条钉的是**最后一道闸门**：失败通知自己也写不出去的时候（`tasks.py` 的
`44-45` 与 `69-70`），异常不能冒出任务。备份那一族早有同形状的
`test_scheduler_backup.py::test_a_notification_that_cannot_be_written_does_not_kill_the_job`，
扫描这两条一路此前没有对应用例。

这一道闸门到底在守什么，本单量过之后和先前的说法不一样：APScheduler 3.11 并不会
因为一次抛异常就把任务摘掉（实测一条每秒触发的 cron job，函数每次都抛，3.2 秒里照样
跑了 3 次、任务还在、`next_run_time` 还留着），所以"任务被永久移除"是假的（那句原先
写在备份那一族的注释里，本单一并改口）。真实代价是两样：**任务对外承诺不抛**（今天
只有调度器在兜，将来任何人直接 `await` 它——比如手工触发——就会拿到一个 500），以及
**日志里得说是哪一步炸的**（冒出去只剩 APScheduler 那句 `Job "…" raised an exception`，
人分不清是扫描还是那条扫描通知）。两条断言因此各钉一半：**异常没冒出来**钉的是那个
`try/except` 本身，**日志里那两句话**钉的是 `logger.exception`——只断言"没抛异常"的话，
把抱怨改成 `logger.error`（回溯就此丢掉）甚至整句删掉都还是绿的，而行覆盖对这两种改法
都不敏感，因为那一格无论如何都被走到了。两条用例挑的失败原因刻意不一样：一条是
`PendingRollbackError`（真机上就是这一颗），一条是 `OSError`（磁盘满了那一类，不是
SQLAlchemy 的层次）——把它俩挪到任意一边、或把闸门改窄，都会红其中一格（本单的电池
就是这么量的：每一路只被自己那一颗签名，`except OSError` 只留在全量那格会全绿，见
电池 M7）。
"""

import logging
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.exc import PendingRollbackError

from src.models.notification import Notification
from src.models.source import VideoSource
from src.models.video import Video
from src.scheduler import tasks as task_module
from src.services.scan_service import ScanService
from tests.conftest import _SharedSession


def _share_session(monkeypatch, session) -> None:
    """让定时任务复用用例的会话，而不是去连真库。"""
    monkeypatch.setattr(task_module, "async_session_maker", _SharedSession(session))


async def _poison_and_raise(session) -> None:
    """把会话弄脏之后让异常照原样冒出去，这就是真机上那次失败的样子。

    同一路径插两行：两种方言都在第二次 `flush()` 上撞唯一约束，会话就此带着
    PendingRollback 状态回到调度任务，而任务要写的正是那条失败通知。
    """
    source = VideoSource(name="脏会话源", path="/lib/dirty", type="local")
    session.add(source)
    await session.flush()
    for _ in range(2):
        session.add(
            Video(
                source_id=source.id,
                filepath="/lib/dirty/同一部.mp4",
                title="同一部",
                duration=10,
                file_size=1024,
                format="mp4",
            )
        )
        await session.flush()


async def _error_rows(session) -> list[tuple[str, str]]:
    rows = (
        await session.execute(
            select(Notification).where(Notification.type == "scan_error").order_by(
                Notification.id
            )
        )
    ).scalars().all()
    return [(row.title, row.message) for row in rows]


async def _notification_cannot_be_written(*_args, **_kwargs) -> None:
    """真机上"失败通知也写不出去"的那一颗：会话没能干净地回来。"""
    raise PendingRollbackError("会话还带着那次失败")


async def _notification_hit_the_disk(*_args, **_kwargs) -> None:
    """不是 SQLAlchemy 那一层的失败（磁盘满了这类）也得被同一道闸门接住。"""
    raise OSError("disk full")


def _task_logs(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "src.scheduler.tasks"]


async def test_a_poisoned_single_source_scan_still_announces_the_failure(
    db_session, monkeypatch
):
    _share_session(monkeypatch, db_session)

    async def explode(self, source_id: int) -> dict:
        await _poison_and_raise(self.session)
        return {}  # pragma: no cover — 上面已经抛了

    with patch.object(ScanService, "scan_source", explode):
        await task_module.scan_source_task(1)

    rows = await _error_rows(db_session)
    assert [title for title, _ in rows] == ["定时扫描失败"]
    # 文案里带的是服务端给的原因（两种方言的措辞不同，所以只钉前缀）。
    assert rows[0][1].startswith("视频源扫描失败: ")


async def test_a_poisoned_full_scan_still_announces_the_failure(db_session, monkeypatch):
    _share_session(monkeypatch, db_session)

    async def explode_all(self) -> dict:
        await _poison_and_raise(self.session)
        return {}  # pragma: no cover — 上面已经抛了

    with patch.object(ScanService, "scan_all_active", explode_all):
        await task_module.scan_all_active_task()

    rows = await _error_rows(db_session)
    assert [title for title, _ in rows] == ["全量扫描失败"]
    assert rows[0][1].startswith("全量扫描失败: ")


async def test_a_scan_failure_whose_notification_also_fails_leaves_a_trace(
    db_session, monkeypatch, caplog
):
    """扫描炸了、那条 `scan_error` 也炸了——异常不能冒回调度器，抱怨要留在日志里。"""
    _share_session(monkeypatch, db_session)

    async def explode(self, source_id: int) -> dict:
        await _poison_and_raise(self.session)
        return {}  # pragma: no cover — 上面已经抛了

    monkeypatch.setattr(
        task_module.NotificationService, "create", _notification_cannot_be_written
    )

    with caplog.at_level(logging.WARNING, logger="src.scheduler.tasks"), patch.object(
        ScanService, "scan_source", explode
    ):
        await task_module.scan_source_task(1)  # 不抛异常，本身就是断言

    assert await _error_rows(db_session) == []
    assert _task_logs(caplog) == [
        "Scheduled scan failed for source 1",
        "Failed to create error notification for source 1",
    ]
    # 第二句是 `logger.exception`：丢了回溯，人就再也看不出通知是怎么没写出去的。
    failing = next(
        r for r in caplog.records if r.getMessage().startswith("Failed to create")
    )
    assert isinstance(failing.exc_info[1], PendingRollbackError)


async def test_a_full_scan_failure_whose_notification_fails_for_another_reason_leaves_a_trace(
    db_session, monkeypatch, caplog
):
    """同一道闸门在另一路（`scan_all_active_task`）上，接的还不止数据库那一层。"""
    _share_session(monkeypatch, db_session)

    async def explode_all(self) -> dict:
        await _poison_and_raise(self.session)
        return {}  # pragma: no cover — 上面已经抛了

    monkeypatch.setattr(
        task_module.NotificationService, "create", _notification_hit_the_disk
    )

    with caplog.at_level(logging.WARNING, logger="src.scheduler.tasks"), patch.object(
        ScanService, "scan_all_active", explode_all
    ):
        await task_module.scan_all_active_task()  # 不抛异常，本身就是断言

    assert await _error_rows(db_session) == []
    assert _task_logs(caplog) == [
        "Full active scan failed",
        "Failed to create error notification for full scan",
    ]
    failing = next(
        r for r in caplog.records if r.getMessage().startswith("Failed to create")
    )
    assert isinstance(failing.exc_info[1], OSError)
