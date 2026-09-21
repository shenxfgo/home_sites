"""界面偏好接口：每个人一份，登录即生效，不共享。

顺带把 M3 的另一半钉住：``settings`` 里不再有 ``theme``，那个键已经归到个人偏好，
而系统配置只认白名单里的几个键名。
"""

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
