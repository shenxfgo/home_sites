"""界面偏好接口：每个人一份，登录即生效，不共享。

顺带把 M3 的另一半钉住：``settings`` 里不再有 ``theme``，那个键已经归到个人偏好，
而系统配置只认白名单里的几个键名。
"""

import pytest
from sqlalchemy import select

from src.models.preference import UserPreference
from src.models.setting import Setting
from src.models.user import ROLE_MEMBER


async def test_preferences_start_at_the_default_theme(client):
    assert (await client.get("/api/preferences")).json() == {"theme": "light"}


async def test_a_theme_choice_comes_back_after_it_is_saved(client):
    saved = await client.put("/api/preferences", json={"theme": "dark"})
    assert saved.status_code == 200
    assert saved.json() == {"theme": "dark"}

    assert (await client.get("/api/preferences")).json() == {"theme": "dark"}


async def test_an_empty_patch_leaves_the_choice_alone(client):
    await client.put("/api/preferences", json={"theme": "auto"})

    assert (await client.put("/api/preferences", json={})).json() == {"theme": "auto"}


async def test_one_persons_theme_is_not_everyones(client, make_signed_in_client):
    await client.put("/api/preferences", json={"theme": "dark"})
    other = await make_signed_in_client("roommate", ROLE_MEMBER)

    assert (await other.get("/api/preferences")).json() == {"theme": "light"}

    await other.put("/api/preferences", json={"theme": "auto"})
    assert (await client.get("/api/preferences")).json() == {"theme": "dark"}
    assert (await other.get("/api/preferences")).json() == {"theme": "auto"}


async def test_an_unknown_theme_is_refused(client):
    response = await client.put("/api/preferences", json={"theme": "neon"})

    assert response.status_code == 422


async def test_the_written_row_belongs_to_the_caller(client, db_session, signed_in_user):
    await client.put("/api/preferences", json={"theme": "dark"})

    row = await db_session.get(UserPreference, signed_in_user.id)
    assert row is not None
    assert row.prefs == {"theme": "dark"}


async def test_the_shared_theme_setting_is_gone(client):
    """``/api/settings`` 只留系统配置，主题不再是它能读写的一项。"""
    body = (await client.get("/api/settings")).json()

    assert "theme" not in body
    assert set(body) == {
        "auto_scan_enabled",
        "auto_scan_interval",
        "default_transcode_format",
        "thumbnail_width",
        "thumbnail_height",
    }


async def test_an_unknown_settings_key_is_refused(client, db_session):
    response = await client.put("/api/settings/theme", json={"value": "dark"})

    assert response.status_code == 400
    assert "未知的配置项" in response.json()["detail"]

    result = await db_session.execute(select(Setting).where(Setting.key == "theme"))
    assert result.scalar_one_or_none() is None


async def test_a_known_settings_key_still_writes(client):
    response = await client.put(
        "/api/settings/auto_scan_interval", json={"value": "7200"}
    )

    assert response.status_code == 200
    assert response.json() == {"key": "auto_scan_interval", "value": "7200"}

    # 再写一次走的是"那一行已经存在"的那条分支（第一次是建行）
    await client.put("/api/settings/auto_scan_interval", json={"value": "900"})

    assert (await client.get("/api/settings/auto_scan_interval")).json() == {
        "key": "auto_scan_interval",
        "value": "900",
    }


@pytest.mark.parametrize(
    "key", ["auto_scan_interval", "thumbnail_width", "thumbnail_height"]
)
async def test_a_number_setting_refuses_a_value_the_read_path_cannot_parse(client, key):
    """单键 PUT 认键名，原先不认值。

    整份 PUT 走的是 `AllSettingsResponse`，Pydantic 会挡；这一条走的是
    `SettingUpdate(value: str)`，写什么进库什么，而 `GET /api/settings` 读回来时
    对这三个键做的是 `int(...)`——于是一次写入就把整个设置页打成 500。
    """
    response = await client.put(f"/api/settings/{key}", json={"value": "not-a-number"})

    assert response.status_code == 400
    assert "必须是整数" in response.json()["detail"]

    assert (await client.get("/api/settings")).status_code == 200


BULK = {
    "auto_scan_enabled": False,
    "auto_scan_interval": 7200,
    "default_transcode_format": "webm",
    "thumbnail_width": 640,
    "thumbnail_height": 480,
}


async def test_the_bulk_put_echoes_what_it_was_asked(client):
    """整份 PUT 的回显就是请求体——所以"它 200 了"什么都不说明。"""
    echoed = await client.put("/api/settings", json=BULK)

    assert echoed.status_code == 200
    assert echoed.json() == BULK


async def test_the_bulk_put_is_what_the_read_later_shows(client):
    """换一路读才算数：写进去的是 Text 列，读回来的是 typed 的五项。"""
    await client.put("/api/settings", json=BULK)

    assert (await client.get("/api/settings")).json() == BULK
    raw = await client.get("/api/settings/auto_scan_interval")
    assert raw.json() == {"key": "auto_scan_interval", "value": "7200"}


async def test_a_bulk_put_that_omits_a_key_resets_it(client):
    """漏一个键不是"那个键不动"，是**回到代码默认值**。

    `AllSettingsResponse` 五个字段都带默认值，少传一个 Pydantic 就替它填上，服务端
    再把这五个一起写库。界面每次都发全五项所以碰不到，但这条边界值得钉住。
    """
    await client.put("/api/settings", json=BULK)
    partial = {k: v for k, v in BULK.items() if k != "thumbnail_width"}

    await client.put("/api/settings", json=partial)

    assert (await client.get("/api/settings")).json()["thumbnail_width"] == 320


async def test_a_key_nobody_wrote_reads_back_empty(client):
    """单键 GET 认不出"没这一行"和"这一行是空串"——它一律回空串。"""
    missing = await client.get("/api/settings/default_transcode_format")

    assert missing.status_code == 200
    assert missing.json() == {"key": "default_transcode_format", "value": ""}
