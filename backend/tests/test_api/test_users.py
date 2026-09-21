"""用户管理接口：建号、改角色、停用启用、重置密码、踢下线，只有 owner 用得动。

角色网关本身在 ``test_middleware/test_roles.py`` 里逐端点扫过，这里测的是这些操作
做完之后库里与登录状态究竟是什么样子——包括两条护栏：不能停用自己，不能让库里
一个可用管理员都不剩。
"""

import pytest

from src.models.user import ROLE_MEMBER, ROLE_OWNER
from src.services.auth_service import login_rate_limiter

PASSWORD = "a-quiet-home-lab"
OTHER_PASSWORD = "another-quiet-lab"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """用例之间不互相锁定：登录尝试会经过同一个进程内限流器。"""
    login_rate_limiter().reset()
    yield
    login_rate_limiter().reset()


async def _create(client, username: str, *, role: str = ROLE_MEMBER) -> dict:
    response = await client.post(
        "/api/users", json={"username": username, "password": PASSWORD, "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _sign_in(browser, username: str, password: str = PASSWORD):
    return await browser.post("/api/auth/login", json={"username": username, "password": password})


async def test_creating_an_account_also_makes_it_signable(client, new_browser):
    created = await _create(client, "guest")

    assert created["username"] == "guest"
    assert created["role"] == ROLE_MEMBER
    assert created["is_active"] is True
    assert created["signed_in_devices"] == 0
    assert (await _sign_in(await new_browser(), "guest")).status_code == 200


async def test_listing_users_shows_every_account_and_its_open_browsers(
    client, make_user, make_client_for
):
    member = await make_user("guest", ROLE_MEMBER)
    await make_client_for(member)  # 他开着 1 个浏览器

    rows = (await client.get("/api/users")).json()

    assert [row["username"] for row in rows] == ["tester", "guest"]
    by_name = {row["username"]: row for row in rows}
    assert by_name["guest"]["signed_in_devices"] == 1
    # tester 的那一枚是夹具替他签的：会话数就是"有几个浏览器还登着"。
    assert by_name["tester"]["signed_in_devices"] == 1


async def test_a_duplicate_username_is_refused(client):
    await _create(client, "guest")

    again = await client.post(
        "/api/users", json={"username": "guest", "password": PASSWORD}
    )

    assert again.status_code == 400
    assert again.json()["detail"] == "账号已存在"


async def test_a_weak_password_is_refused_before_anything_is_written(client):
    response = await client.post(
        "/api/users", json={"username": "tiny", "password": "short"}
    )

    assert response.status_code == 400
    assert "至少" in response.json()["detail"]


async def test_promoting_a_member_takes_effect_on_the_next_request(
    client, make_user, make_client_for
):
    member = await make_user("climber", ROLE_MEMBER)
    browser = await make_client_for(member)

    # 还没升级之前，管理面对他是 403。
    assert (await browser.post("/api/tags", json={"name": "试试"})).status_code == 403

    updated = await client.put(f"/api/users/{member.id}/role", json={"role": ROLE_OWNER})

    assert updated.json()["role"] == ROLE_OWNER
    # 角色是每次请求现查的，所以同一枚 Cookie 下一跳就有新权限，不必重新登录。
    assert (await browser.post("/api/tags", json={"name": "试试"})).status_code in (200, 201)


async def test_demoting_the_last_admin_is_refused(client, signed_in_user):
    response = await client.put(
        f"/api/users/{signed_in_user.id}/role", json={"role": ROLE_MEMBER}
    )

    assert response.status_code == 400
    assert "至少要保留一个可用的管理员" in response.json()["detail"]


async def test_disabling_your_own_account_is_refused(client, signed_in_user):
    response = await client.put(
        f"/api/users/{signed_in_user.id}/status", json={"is_active": False}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "不能停用自己的账号"


async def test_disabling_an_account_cuts_its_open_browsers_off(
    client, make_user, make_client_for
):
    member = await make_user("offduty", ROLE_MEMBER)
    browser = await make_client_for(member)
    assert (await browser.get("/api/videos")).status_code == 200

    response = await client.put(
        f"/api/users/{member.id}/status", json={"is_active": False}
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    # 会话是被一起删掉的，不是靠 is_active 在请求时把关。
    assert response.json()["signed_in_devices"] == 0
    assert (await browser.get("/api/videos")).status_code == 401


async def test_resetting_a_password_signs_that_account_out_and_the_new_one_works(
    client, new_browser
):
    created = await _create(client, "forgetful")
    browser = await new_browser()
    signed_in = await _sign_in(browser, "forgetful")
    assert signed_in.status_code == 200

    reset = await client.post(
        f"/api/users/{created['id']}/password", json={"new_password": OTHER_PASSWORD}
    )
    assert reset.status_code == 204

    # 那台浏览器手里的 Cookie 当场作废，老密码也不再生效。
    assert (await browser.get("/api/videos")).status_code == 401
    assert (await _sign_in(browser, "forgetful")).status_code == 401
    assert (await _sign_in(browser, "forgetful", OTHER_PASSWORD)).status_code == 200


async def test_revoking_sessions_reports_what_it_dropped(client, new_browser):
    created = await _create(client, "tourist")
    for _ in range(2):  # 两台设备各自登一次
        await _sign_in(await new_browser(), "tourist")

    revoked = await client.delete(f"/api/users/{created['id']}/sessions")

    assert revoked.json() == {"revoked": 2}
    assert (await client.get("/api/users")).json()[1]["signed_in_devices"] == 0


async def test_an_unknown_account_is_404(client):
    assert (
        await client.put("/api/users/9999/role", json={"role": ROLE_OWNER})
    ).status_code == 404
    assert (await client.delete("/api/users/9999/sessions")).status_code == 404
    assert (
        await client.post("/api/users/9999/password", json={"new_password": PASSWORD})
    ).status_code == 404
