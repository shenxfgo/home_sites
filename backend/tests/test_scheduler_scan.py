# tests/test_scheduler_scan.py
"""定时扫描的失败必须落到人能看见的地方——这一条此前是死代码。

`scan_source_task` 与 `scan_all_active_task` 都写了"异常就发一条 `scan_error`
通知"，可它复用的正是刚失败的那个会话：`flush()` 撞了唯一约束之后会话进入
PendingRollback 状态，紧接着的 INSERT 只会再抛一次，于是被内层的 `except` 吞掉。
真机上的现场是 `notifications` 里 0 条 `scan_error`，而 stderr 每 30 分钟重复一段
`IntegrityError`——失败一直在发生，只是没人能看见。
"""

from unittest.mock import patch

from sqlalchemy import select

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
