"""应用启动那 23 行：`src/main.py:22-44` 的 lifespan 此前一次也没被执行过。

coverage 里 `src/main.py` 长期 81%，缺的就是这一整段——建库、按表里**现存**的片源挂
扫描任务、备份只在 PostgreSQL 上挂载、真的 `start()`、退出时真的 `stop()`。
相邻的两份用例都不从这一个入口进来：`test_scheduler_source_lifecycle.py` 钉的是片源
create / update / delete 那三条边（走 Service），`test_scheduler_backup.py` 钉的是备份
任务本身。于是"服务重启之后到底武装了什么"这一格一直是空的，而它恰好是唯一一个
**装错了也不报错**的地方：少一行 `start()`，界面照常能用，只是再没有一次定时扫描。

三个任务函数（`scan_source_task` / `backup_database_task` / `backup_catchup_task`）换成
只登记的替身：补跑那一个是 `DateTrigger()`，调度器一 start 就会立刻执行它，真跑一趟
就是往真盘上写一次 `pg_dump`，而定时扫描那个用的是全局会话——会连到 `settings.database_url`
上头去。调度器本身是真的 APScheduler，挂载与触发器都按真行为核对。
"""
from collections.abc import Iterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src import main as app_module
from src.config import settings
from src.models.source import VideoSource
from src.scheduler.scan_scheduler import (
    BACKUP_CATCHUP_JOB_ID,
    BACKUP_JOB_ID,
    ScanScheduler,
)

PG_URL = "postgresql+asyncpg://home_sites_app@127.0.0.1:5432/home_sites"
SQLITE_URL = "sqlite+aiosqlite:///./data/videos.db"


class BootScheduler(ScanScheduler):
    """A scheduler that records the order the boot path armed things."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def add_source_job(self, source_id: int, interval: int) -> None:
        self.events.append(f"source:{source_id}:{interval}")
        super().add_source_job(source_id, interval)

    def add_backup_job(self, time_of_day: str) -> None:
        self.events.append(f"backup:{time_of_day}")
        super().add_backup_job(time_of_day)

    def add_backup_catchup_job(self) -> None:
        self.events.append("backup_catchup")
        super().add_backup_catchup_job()

    def start(self) -> None:
        self.events.append("start")
        super().start()

    def stop(self) -> None:
        self.events.append("stop")
        super().stop()


class _BorrowedSession:
    """Hand the lifespan the test's session without letting it close the connection."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> "_BorrowedSession":
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


@pytest_asyncio.fixture
async def boot(db_session: AsyncSession, monkeypatch) -> Iterator[BootScheduler]:
    """The app's startup path, wired to this test's database and a scheduler of one's own."""
    sched = BootScheduler()

    async def fake_init_db() -> None:
        sched.events.append("init_db")

    async def idle_task(*_args: object) -> None:
        return None

    monkeypatch.setattr(app_module, "init_db", fake_init_db)
    monkeypatch.setattr(app_module, "async_session_maker", _BorrowedSession(db_session))
    monkeypatch.setattr(app_module, "scheduler", sched)
    # 真环境里备份是开着、库是 PostgreSQL 的，这一格不动它：钉片源那一路的用例不该
    # 被启动路径顺手挂上的两个备份任务污染。备份那一半由后面三个用例各自显式摆好。
    monkeypatch.setattr(settings, "backup_enabled", False)
    # 任务函数是在挂载那一刻从模块里取的，所以替身要打在 tasks 模块上。
    monkeypatch.setattr("src.scheduler.tasks.scan_source_task", idle_task)
    monkeypatch.setattr("src.scheduler.tasks.backup_database_task", idle_task)
    monkeypatch.setattr("src.scheduler.tasks.backup_catchup_task", idle_task)
    yield sched
    if sched.is_running:
        sched.stop()


async def _source(
    db_session: AsyncSession, *, name: str, interval: int, active: bool = True
) -> VideoSource:
    row = VideoSource(
        name=name,
        path=f"D:/videos/{name}",
        type="local",
        scan_interval=interval,
        is_active=active,
    )
    db_session.add(row)
    await db_session.flush()
    return row


def _job_ids(sched: ScanScheduler) -> list[str]:
    """Ids straight off APScheduler: an unstarted scheduler has no `next_run_time`."""
    return sorted(job.id for job in sched.scheduler.get_jobs())


def _trigger(sched: ScanScheduler, job_id: str) -> str:
    job = next(job for job in sched.scheduler.get_jobs() if job.id == job_id)
    return str(job.trigger)


async def test_boot_builds_the_schema_before_it_arms_anything(boot, db_session):
    await _source(db_session, name="客厅", interval=1800)

    async with app_module.lifespan(app_module.app):
        pass

    assert boot.events == ["init_db", "source:1:1800", "start", "stop"]


async def test_boot_with_an_empty_table_still_starts_the_scheduler(boot):
    async with app_module.lifespan(app_module.app):
        pass

    assert boot.events == ["init_db", "start", "stop"]


async def test_every_active_source_gets_a_job_at_its_own_interval(boot, db_session):
    near = await _source(db_session, name="近处", interval=60)
    far = await _source(db_session, name="远处", interval=1800)
    off = await _source(db_session, name="关掉的那个", interval=90, active=False)

    async with app_module.lifespan(app_module.app):
        pass

    assert _job_ids(boot) == [f"scan_source_{near.id}", f"scan_source_{far.id}"]
    assert f"scan_source_{off.id}" not in _job_ids(boot)
    # 间隔是从那一行读的，不是写死一个默认值：一分钟和半小时各归各的。
    assert _trigger(boot, f"scan_source_{near.id}") == "interval[0:01:00]"
    assert _trigger(boot, f"scan_source_{far.id}") == "interval[0:30:00]"


async def test_the_scheduler_is_started_inside_and_stopped_on_exit(boot, db_session):
    await _source(db_session, name="客厅", interval=1800)

    async with app_module.lifespan(app_module.app):
        assert boot.is_running

    assert not boot.is_running


async def test_postgres_arms_both_the_nightly_job_and_the_catchup(boot, monkeypatch):
    monkeypatch.setattr(settings, "backup_enabled", True)
    monkeypatch.setattr(settings, "backup_time", "07:15")
    monkeypatch.setattr(settings, "database_url", PG_URL)

    async with app_module.lifespan(app_module.app):
        pass

    assert "backup:07:15" in boot.events and "backup_catchup" in boot.events
    assert BACKUP_JOB_ID in _job_ids(boot)
    assert BACKUP_CATCHUP_JOB_ID in _job_ids(boot)
    # 挂载时间来自设置里的那一条配置，不是代码里写死的一个时刻。
    assert _trigger(boot, BACKUP_JOB_ID) == "cron[hour='7', minute='15']"


async def test_a_sqlite_url_arms_no_backup_jobs(boot, monkeypatch):
    monkeypatch.setattr(settings, "backup_enabled", True)
    monkeypatch.setattr(settings, "database_url", SQLITE_URL)

    async with app_module.lifespan(app_module.app):
        pass

    # pg_dump 备不了 SQLite：装了每晚只会多一条失败通知。
    assert BACKUP_JOB_ID not in _job_ids(boot)
    assert BACKUP_CATCHUP_JOB_ID not in _job_ids(boot)
    assert boot.events == ["init_db", "start", "stop"]


async def test_a_disabled_backup_is_not_armed_even_on_postgres(boot, monkeypatch):
    monkeypatch.setattr(settings, "backup_enabled", False)
    monkeypatch.setattr(settings, "database_url", PG_URL)

    async with app_module.lifespan(app_module.app):
        pass

    assert BACKUP_JOB_ID not in _job_ids(boot)
    assert boot.events == ["init_db", "start", "stop"]
