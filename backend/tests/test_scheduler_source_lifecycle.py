"""片源的生命周期和调度任务是同步的——此前这三条边一条都没有断言。

``SourceService`` 的 create / update / delete 都会动 ``scan_source_{id}`` 这个任务，
而整个测试集里没有任何一处读过调度器（只有备份任务的断言）。少掉其中一行不会让
任何测试变红，代价却是进程内多一个永远扫不到东西的任务：被删掉的片源继续按原间隔
醒来，每轮换回一条「定时扫描失败」通知——#85 那一类只会自己长大的东西正是这个形状。

用例把 ``src.services.source_service`` 和 ``src.api.scheduler`` 里那个全局
``scheduler`` 换成新建的 :class:`ScanScheduler`：真任务、真 APScheduler 作业表，
但绝不往那个跨用例存活的全局实例上挂东西（片源接口每一条 create 都在往上挂）。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.scheduler.scan_scheduler import ScanScheduler
from src.services.source_service import SourceService


@pytest_asyncio.fixture
async def sched(monkeypatch) -> ScanScheduler:
    """A scheduler instance of one's own, patched into both callers."""
    instance = ScanScheduler()
    monkeypatch.setattr("src.services.source_service.scheduler", instance)
    monkeypatch.setattr("src.api.scheduler.scheduler", instance)
    yield instance
    if instance.is_running:
        instance.stop()


def _job_ids(instance: ScanScheduler) -> list[str]:
    """The armed job ids, straight off the jobstore.

    读的是 APScheduler 的原始 job 而不是 :meth:`ScanScheduler.get_jobs`：未启动的
    调度器上挂着的任务还没有 ``next_run_time`` 这个属性，那个包装只有在启动后才可
    用——而生命周期这几条边不该依赖启动。
    """
    return sorted(job.id for job in instance.scheduler.get_jobs())


def _trigger(instance: ScanScheduler, source_id: int) -> str:
    job = next(
        job for job in instance.scheduler.get_jobs() if job.id == f"scan_source_{source_id}"
    )
    return str(job.trigger)


async def _create(db_session: AsyncSession, **kwargs) -> int:
    """Create a source through the service and hand back its id."""
    fields = {"name": "客厅", "path": "D:/videos/living", "type": "local", "scan_interval": 1800}
    fields.update(kwargs)
    source = await SourceService(db_session).create(**fields)
    return source.id


@pytest.mark.asyncio
async def test_creating_an_active_source_arms_a_job_at_its_own_interval(db_session, sched):
    source_id = await _create(db_session, scan_interval=1800)

    assert _job_ids(sched) == [f"scan_source_{source_id}"]
    assert _trigger(sched, source_id) == "interval[0:30:00]"


@pytest.mark.asyncio
async def test_an_inactive_source_is_not_armed(db_session, sched):
    await _create(db_session, is_active=False)

    assert _job_ids(sched) == []


@pytest.mark.asyncio
async def test_deactivating_a_source_disarms_its_job(db_session, sched):
    source_id = await _create(db_session)
    assert _job_ids(sched) == [f"scan_source_{source_id}"]

    await SourceService(db_session).update(source_id, is_active=False)

    assert _job_ids(sched) == []


@pytest.mark.asyncio
async def test_reactivating_a_source_arms_it_again(db_session, sched):
    source_id = await _create(db_session)
    service = SourceService(db_session)
    await service.update(source_id, is_active=False)

    await service.update(source_id, is_active=True)

    assert _job_ids(sched) == [f"scan_source_{source_id}"]


@pytest.mark.asyncio
async def test_changing_the_interval_replaces_the_job_instead_of_adding_one(db_session, sched):
    source_id = await _create(db_session, scan_interval=1800)

    await SourceService(db_session).update(source_id, scan_interval=7200)

    assert _job_ids(sched) == [f"scan_source_{source_id}"]
    assert _trigger(sched, source_id) == "interval[2:00:00]"


@pytest.mark.asyncio
async def test_renaming_a_source_leaves_the_job_alone(db_session, sched):
    source_id = await _create(db_session, scan_interval=1800)

    await SourceService(db_session).update(source_id, name="影音室")

    assert _job_ids(sched) == [f"scan_source_{source_id}"]
    assert _trigger(sched, source_id) == "interval[0:30:00]"


@pytest.mark.asyncio
async def test_deleting_a_source_disarms_its_job(db_session, sched):
    source_id = await _create(db_session)

    await SourceService(db_session).delete(source_id)

    assert _job_ids(sched) == []


@pytest.mark.asyncio
async def test_the_status_endpoint_reports_the_running_scheduler(client, db_session, sched):
    source_id = await _create(db_session)
    sched.start()

    response = await client.get("/api/scheduler/status")

    assert response.status_code == 200
    assert response.json() == {"is_running": True, "jobs_count": 1}
    assert _job_ids(sched) == [f"scan_source_{source_id}"]


@pytest.mark.asyncio
async def test_the_jobs_endpoint_lists_the_armed_scan_job(client, db_session, sched):
    source_id = await _create(db_session, scan_interval=1800)
    sched.start()

    response = await client.get("/api/scheduler/jobs")

    assert response.status_code == 200
    (job,) = response.json()
    assert job["id"] == f"scan_source_{source_id}"
    assert job["trigger"] == "interval[0:30:00]"
    # 未启动时挂上去的任务还没有 next_run_time，是 start() 才把它们排上时间轴的。
    assert job["next_run_time"] is not None


@pytest.mark.asyncio
async def test_the_api_arms_a_job_for_a_source_that_exists(client, db_session, sched):
    source_id = await _create(db_session, scan_interval=1800)

    response = await client.post(
        "/api/scheduler/jobs", json={"source_id": source_id, "interval": 900}
    )

    assert response.status_code == 201
    assert _job_ids(sched) == [f"scan_source_{source_id}"]
    assert _trigger(sched, source_id) == "interval[0:15:00]"


@pytest.mark.asyncio
async def test_the_api_refuses_to_arm_a_job_for_a_source_that_is_not_there(client, sched):
    response = await client.post("/api/scheduler/jobs", json={"source_id": 4242, "interval": 900})

    assert response.status_code == 404
    assert _job_ids(sched) == []


@pytest.mark.asyncio
async def test_the_api_disarms_a_job_and_a_second_call_is_still_ok(client, db_session, sched):
    source_id = await _create(db_session)

    first = await client.delete(f"/api/scheduler/jobs/{source_id}")
    second = await client.delete(f"/api/scheduler/jobs/{source_id}")

    assert first.status_code == 204
    assert second.status_code == 204
    assert _job_ids(sched) == []
