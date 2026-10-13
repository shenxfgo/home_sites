# tests/test_settings_wired_into_pipelines.py
"""系统配置那四项第一次真的管事——这几条钉的是「同一个口径」本身。

`/api/settings` 的往返一直是绿的（`test_api/test_preferences.py`），绿的是"写进去
能读回来"，不是"有人按它办事"。四项里只有总开关在 #150 拿到了读者；这一单把剩下
四项接进管线：

- 扫描间隔 → 新建视频源没填间隔时的默认值（`SourceService.create`）
- 缩略图宽、高 → 扫描时 ffmpeg 的 `scale=W:H`（`generate_thumbnail`）
- 默认转码格式 → 转码页那个下拉的初值（读者在前端，接口契约不变：目标格式仍是
  必填项，缺了照旧 422）

这里重点量的不是"各自能用"，而是**设置页读到的和管线用的是不是同一个东西**：一张
全局 KV 表，两个读者各写一套解析规则，同一个字符串就有两种真值。所以既有用例走
"从 API 写、从管线读"的完整链路，也有一条把写闸门和读回退摆在同一张取值表上对撞。
"""

import subprocess

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from src.api.settings import INT_SETTING_KEYS, _check_setting_value
from src.models.setting import Setting
from src.models.source import VideoSource
from src.services import scan_service as scan_module
from src.services.setting_service import (
    AUTO_SCAN_INTERVAL_KEY,
    DEFAULT_AUTO_SCAN_INTERVAL,
    SettingService,
    parse_int_setting,
    setting_number,
)
from src.utils import file_scanner


class _FakeRun:
    """记下 ffmpeg 的参数，再落下一个文件当作封面。"""

    def __init__(self) -> None:
        self.argv: list[str] = []

    def __call__(self, cmd, **_kwargs):
        self.argv = list(cmd)
        with open(cmd[-1], "wb"):
            pass
        return subprocess.CompletedProcess(cmd, 0, "", "")


async def _row(db_session, key: str, value: str) -> None:
    """留下一行设置——直接写表，绕开写闸门（脏行那条用例要的就是这个）。"""
    existing = await db_session.get(Setting, key)
    if existing:
        existing.value = value
    else:
        db_session.add(Setting(key=key, value=value))
    await db_session.commit()


async def _local_source(db_session, tmp_path) -> VideoSource:
    """一个真目录、一个看着像影片的假文件。直接建模型——别走 SourceService，
    那会往全局调度器上挂一个真任务。"""
    (tmp_path / "a.mp4").write_bytes(b"dummy")
    source = VideoSource(name="配置源", path=str(tmp_path), type="local")
    db_session.add(source)
    await db_session.commit()
    return source


def _probe_off(monkeypatch) -> None:
    def fake_info(*_args, **_kwargs):
        return {"duration": 100, "resolution": "1920x1080", "format": "mp4"}

    monkeypatch.setattr(scan_module, "extract_video_info", fake_info)


def _gate_accepts(key: str, raw: str) -> bool:
    try:
        _check_setting_value(key, raw)
    except HTTPException:
        return False
    return True


async def test_the_settings_page_and_a_new_source_share_one_interval(client):
    """间隔写进设置页，新片源没填就得用它——写是 API，读也得是这条链路。"""
    await client.put("/api/settings/auto_scan_interval", json={"value": "900"})

    created = await client.post(
        "/api/sources", json={"name": "跟着设置走", "path": "/mnt/a", "type": "local"}
    )

    assert created.status_code == 201
    assert created.json()["scan_interval"] == 900
    assert (await client.get("/api/settings")).json()["auto_scan_interval"] == 900


async def test_an_explicit_interval_on_the_source_still_wins(client):
    """这一项是**默认值**，不是覆盖：源自己填了就用它自己的。"""
    await client.put("/api/settings/auto_scan_interval", json={"value": "900"})

    created = await client.post(
        "/api/sources",
        json={
            "name": "自己有主意",
            "path": "/mnt/b",
            "type": "local",
            "scan_interval": 7200,
        },
    )

    assert created.json()["scan_interval"] == 7200


async def test_a_source_created_without_a_row_keeps_the_code_default(client):
    """一个字没写过的新库：默认值来自代码，而不是"这一行是空串所以是 0"。"""
    created = await client.post(
        "/api/sources", json={"name": "新库的源", "path": "/mnt/c", "type": "local"}
    )

    assert created.json()["scan_interval"] == DEFAULT_AUTO_SCAN_INTERVAL


async def test_an_interval_too_small_to_be_a_source_interval_is_refused(client, db_session):
    """这个数的意义是"一个源的间隔"，能写的范围就是源间隔能取的范围。

    放行 30 的话，那一行读回来是 30、挂上调度器却是每 30 秒扫一遍全库——而
    `POST /api/sources` 自己从来不肯收 30。
    """
    response = await client.put("/api/settings/auto_scan_interval", json={"value": "30"})

    assert response.status_code == 400
    assert "取值范围" in response.json()["detail"]

    result = await db_session.execute(
        select(Setting).where(Setting.key == AUTO_SCAN_INTERVAL_KEY)
    )
    assert result.scalar_one_or_none() is None


async def test_the_cover_size_written_here_reaches_ffmpeg(db_session, monkeypatch, tmp_path):
    """封面的宽高从这张表走到 ffmpeg 的参数里。

    这里打的是真链路：设置行 → `scan_source` 一轮 → `generate_thumbnail` 的 argv。
    只测解析函数的话，"接上了"这句话没人签过字。
    """
    fake = _FakeRun()
    monkeypatch.setattr(file_scanner.subprocess, "run", fake)
    _probe_off(monkeypatch)
    monkeypatch.setattr(scan_module.settings, "thumbnail_path", str(tmp_path / "covers"))
    await _row(db_session, "thumbnail_width", "640")
    await _row(db_session, "thumbnail_height", "360")
    source = await _local_source(db_session, tmp_path)

    result = await scan_module.ScanService(db_session).scan_source(source.id)

    assert result["new_videos"] == 1
    assert fake.argv[fake.argv.index("-vf") + 1] == "scale=640:360"


async def test_a_cover_size_nobody_wrote_lands_on_the_default_pair(
    db_session, monkeypatch, tmp_path
):
    """空表也能刷封面：回退的那一对数字和设置页读到的是同一份。"""
    fake = _FakeRun()
    monkeypatch.setattr(file_scanner.subprocess, "run", fake)
    _probe_off(monkeypatch)
    monkeypatch.setattr(scan_module.settings, "thumbnail_path", str(tmp_path / "covers"))
    source = await _local_source(db_session, tmp_path)

    await scan_module.ScanService(db_session).scan_source(source.id)

    assert fake.argv[fake.argv.index("-vf") + 1] == "scale=320:180"
    assert await SettingService(db_session).get_thumbnail_size() == (320, 180)


@pytest.mark.parametrize(
    "raw",
    [
        "60",
        "3600",
        "86400",
        "59",
        "86401",
        "0",
        "-1",
        "",
        "abc",
        "3.5",
        " 12 x",
        " 900 ",
        "00900",
    ],
)
def test_the_write_gate_and_the_reader_agree_on_every_shape(raw: str):
    """门口放行的和管线上留下的，必须是同一批字符串。

    判据写两份迟早会分家：一边放行、一边回退，设置页就会出现"我存了 30，页面上写着
    3600，挂上去的却是每 30 秒"。这条把写闸门和读回退摆在同一张取值表上对撞。
    """
    key = AUTO_SCAN_INTERVAL_KEY
    number = setting_number(raw)
    # 回退成默认值 = 这一行对这个键什么都没说；数字活着才算"留下"。
    kept = number is not None and parse_int_setting(key, raw) == number

    assert _gate_accepts(key, raw) is kept


def test_every_int_setting_key_is_gateable_and_readable():
    """数字键这张名单不能有一头缺着：能写的必须能判，判得住的必须读得回来。"""
    assert INT_SETTING_KEYS == {AUTO_SCAN_INTERVAL_KEY, "thumbnail_width", "thumbnail_height"}
    for key in INT_SETTING_KEYS:
        assert not _gate_accepts(key, "not-a-number")
        assert parse_int_setting(key, "not-a-number") == parse_int_setting(key, None)


async def test_a_junk_row_reads_back_the_default_instead_of_500(client, db_session):
    """手工 SQL 写进去的一行脏值不该把设置页打成 500。

    写闸门挡得住 API 这一侧，挡不住直接对表写话。以前 GET 里那句 `int(...)` 会把
    整页打崩；现在它和管线共用同一份回退，两边读到同一个默认值——这才是"一种真值"。
    """
    await _row(db_session, "thumbnail_width", "wide")
    await _row(db_session, AUTO_SCAN_INTERVAL_KEY, "0")

    body = (await client.get("/api/settings")).json()

    assert body["thumbnail_width"] == 320
    assert body["auto_scan_interval"] == DEFAULT_AUTO_SCAN_INTERVAL


async def test_the_default_format_is_readable_but_the_api_still_demands_one(client):
    """这一项的读者是界面，接口契约一个字没改。

    转码请求里的目标格式仍是必填项，服务端不替人填默认：缺了照旧 422。这条同时
    钉住"设置页写的那个格式前端读得到"和"422 还在"。
    """
    await client.put("/api/settings/default_transcode_format", json={"value": "webm"})

    assert (await client.get("/api/settings")).json()["default_transcode_format"] == "webm"
    assert (await client.post("/api/transcode/1", json={})).status_code == 422
