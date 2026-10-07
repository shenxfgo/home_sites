# tests/test_scheduler_auto_scan_switch.py
"""设置页上那个「自动扫描」开关管不着任何东西——这几条是它的第一个消费者。

`/api/settings` 把五项写进 `settings` 表再原样读回来，往返一路绿灯
（`test_api/test_preferences.py` 钉的就是这个往返）。可全仓 grep 显示，除了这个
API 自己，没有任何代码读这张表：把开关拨到关、保存、刷新回来还在那儿，而调度器
照旧按每个源自己的间隔一轮一轮地扫。页面上那句「启用后将按照设定的间隔自动扫描
视频源」里，只有"自动扫描"四个字一直在发生，跟开关没关系。

闸门落在**定时任务**上，不落在 `ScanService` 上：设置页写的是"自动"扫描，人按
"扫描"按钮那一下从来不该归它管。第 4 条钉的就是这个位置——把闸门挪进 service
的话，第 4 条会红而前三条全绿。
"""

from sqlalchemy import select

from src.models.setting import Setting
from src.models.source import VideoSource
from src.models.video import Video
from src.scheduler import tasks as task_module
from src.services import scan_service as scan_module
from tests.conftest import _SharedSession


def _share_session(monkeypatch, session) -> None:
    """让定时任务复用用例的会话，而不是去连真库。"""
    monkeypatch.setattr(task_module, "async_session_maker", _SharedSession(session))


def _no_media_tools(monkeypatch) -> None:
    """目录是真的，容器是假的——这一条要量的是"扫没扫"，不是 ffprobe。"""

    def fake_info(*_args, **_kwargs):
        return {"duration": 100, "resolution": "1920x1080", "format": "mp4"}

    monkeypatch.setattr(scan_module, "extract_video_info", fake_info)
    monkeypatch.setattr(scan_module, "generate_thumbnail", lambda *_a, **_k: "")


async def _switch(db_session, value: str) -> None:
    """按设置页写入的那个形状（`str(False).lower()`）留下这一行。"""
    existing = await db_session.get(Setting, "auto_scan_enabled")
    if existing:
        existing.value = value
    else:
        db_session.add(Setting(key="auto_scan_enabled", value=value))
    await db_session.commit()


async def _source_with_a_video(db_session, tmp_path) -> VideoSource:
    """一个真目录、一个看着像影片的假文件。直接建模型——别走 SourceService，
    那会往全局调度器上挂一个真任务。"""
    (tmp_path / "a.mp4").write_bytes(b"dummy")
    source = VideoSource(name="开关源", path=str(tmp_path), type="local")
    db_session.add(source)
    await db_session.commit()
    return source


async def _scanned(db_session, source_id: int) -> int:
    """这一轮扫进了几部影片。"""
    rows = (
        await db_session.execute(select(Video).where(Video.source_id == source_id))
    ).scalars().all()
    return len(rows)


async def test_a_disabled_switch_skips_the_scheduled_round(db_session, monkeypatch, tmp_path):
    """关了就整轮不走：目录里那个文件这一轮不该进库。"""
    _share_session(monkeypatch, db_session)
    _no_media_tools(monkeypatch)
    source = await _source_with_a_video(db_session, tmp_path)
    await _switch(db_session, "false")

    await task_module.scan_source_task(source.id)

    assert await _scanned(db_session, source.id) == 0
    await db_session.refresh(source)
    assert source.last_scan_at is None


async def test_no_row_written_yet_means_auto_scan_is_on(db_session, monkeypatch, tmp_path):
    """默认必须是开：新库那张表是空的，一个字都没写过的人不该被静默停扫。"""
    _share_session(monkeypatch, db_session)
    _no_media_tools(monkeypatch)
    source = await _source_with_a_video(db_session, tmp_path)

    await task_module.scan_source_task(source.id)

    assert await _scanned(db_session, source.id) == 1


async def test_flipping_the_switch_back_on_resumes_scanning(db_session, monkeypatch, tmp_path):
    """开关是每轮现读的，不是启动时读一次就记住的——否则"晚上停、早上开"要么得
    重启，要么根本不会自己回来。"""
    _share_session(monkeypatch, db_session)
    _no_media_tools(monkeypatch)
    source = await _source_with_a_video(db_session, tmp_path)

    await _switch(db_session, "false")
    await task_module.scan_source_task(source.id)
    assert await _scanned(db_session, source.id) == 0

    await _switch(db_session, "true")
    await task_module.scan_source_task(source.id)
    assert await _scanned(db_session, source.id) == 1


async def test_a_manual_scan_is_not_governed_by_the_switch(
    client, db_session, monkeypatch, tmp_path
):
    """人按的那一下不受总开关管辖：这条把闸门钉在任务上，而不是 service 里。"""
    _no_media_tools(monkeypatch)
    source = await _source_with_a_video(db_session, tmp_path)
    await _switch(db_session, "false")

    response = await client.post(f"/api/sources/{source.id}/scan")

    assert response.status_code == 200
    assert response.json()["new_videos"] == 1


async def test_the_full_scan_round_honours_the_switch_too(db_session, monkeypatch, tmp_path):
    """`scan_all_active_task` 目前没有挂载点，闸门照加——将来挂上去时它不能又是一
    个装饰。开着的那一半同时证明这一轮的跳过不是无条件 return。"""
    _share_session(monkeypatch, db_session)
    _no_media_tools(monkeypatch)
    source = await _source_with_a_video(db_session, tmp_path)

    await _switch(db_session, "false")
    await task_module.scan_all_active_task()
    assert await _scanned(db_session, source.id) == 0

    await _switch(db_session, "true")
    await task_module.scan_all_active_task()
    assert await _scanned(db_session, source.id) == 1
