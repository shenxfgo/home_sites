"""Tests for the auth API: login, session cookie, me, logout, password change."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.models.user import ROLE_MEMBER, ROLE_OWNER, UserSession
from src.services.auth_service import (
    COOKIE_NAME,
    INVALID_CREDENTIALS,
    AuthService,
    hash_token,
    login_rate_limiter,
)
from src.utils.password import hash_password, verify_password

PASSWORD = "a-quiet-home-lab"
NEW_PASSWORD = "a-new-quiet-home-lab"

# 后端原样存下登录时的 User-Agent，"我的设备"读的就是这一句。
IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """The limiter is process-wide, so one test's failures must not leak."""
    login_rate_limiter().reset()
    yield
    login_rate_limiter().reset()


async def _sessions(db_session) -> list[UserSession]:
    result = await db_session.execute(select(UserSession))
    return list(result.scalars().all())


async def _alice(db_session):
    return await AuthService(db_session).create_user("alice", PASSWORD, role=ROLE_OWNER)


async def _login(client, username="alice", password=PASSWORD, remember=False):
    return await client.post(
        "/api/auth/login",
        json={"username": username, "password": password, "remember": remember},
    )


async def test_login_returns_the_user_and_sets_an_httponly_cookie(anon_client, db_session):
    await _alice(db_session)

    response = await _login(anon_client)

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "username": "alice",
        "role": "owner",
        "display_name": "alice",
    }
    cookie = response.headers["set-cookie"]
    assert f"{COOKIE_NAME}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=43200" in cookie  # settings.session_hours is 12

    me = await anon_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_only_the_token_hash_is_stored(anon_client, db_session):
    await _alice(db_session)

    token = (await _login(anon_client)).cookies.get(COOKIE_NAME)
    rows = await _sessions(db_session)

    assert [row.token_hash for row in rows] == [hash_token(token)]
    assert token not in rows[0].token_hash


async def test_remember_me_lengthens_the_cookie_and_the_row(anon_client, db_session):
    await _alice(db_session)

    response = await _login(anon_client, remember=True)

    assert "Max-Age=2592000" in response.headers["set-cookie"]  # 30 days
    (row,) = await _sessions(db_session)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    assert row.expires_at - now_utc > timedelta(days=29)


async def test_a_wrong_password_and_an_unknown_account_say_the_same_thing(
    anon_client, db_session
):
    await _alice(db_session)

    bad_password = await _login(anon_client, password="not-the-password")
    unknown_account = await _login(anon_client, username="nobody", password=PASSWORD)

    assert bad_password.status_code == unknown_account.status_code == 401
    assert bad_password.json()["detail"] == unknown_account.json()["detail"]
    assert bad_password.json()["detail"] == INVALID_CREDENTIALS


async def test_login_ignores_case_and_surrounding_space(anon_client, db_session):
    await _alice(db_session)

    assert (await _login(anon_client, username="  ALIce ")).status_code == 200


async def test_a_disabled_account_cannot_sign_in(anon_client, db_session):
    service = AuthService(db_session)
    await _alice(db_session)  # 库里得留一个管理员，被停用的是下面那位成员
    member = await service.create_user("bob", PASSWORD, role=ROLE_MEMBER)
    await service.set_active(member, False)

    assert (await _login(anon_client, username="bob")).status_code == 401


async def test_five_failures_lock_the_account_until_the_window_ends(anon_client, db_session):
    await _alice(db_session)

    codes = [(await _login(anon_client, password="wrong-one")).status_code for _ in range(5)]
    locked = await _login(anon_client, password=PASSWORD)

    assert codes == [401] * 5
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


async def test_a_success_clears_the_failure_count(anon_client, db_session):
    await _alice(db_session)

    for _ in range(3):
        await _login(anon_client, password="wrong")

    assert (await _login(anon_client)).status_code == 200


async def test_status_reports_anonymous_and_setup_state(anon_client, db_session):
    empty = await anon_client.get("/api/auth/status")
    assert empty.status_code == 200
    assert empty.json() == {"authenticated": False, "needs_setup": True}

    await _alice(db_session)
    await _login(anon_client)

    signed_in = await anon_client.get("/api/auth/status")
    assert signed_in.json() == {"authenticated": True, "needs_setup": False}


async def test_me_is_refused_without_a_session(anon_client):
    response = await anon_client.get("/api/auth/me")

    assert response.status_code == 401


async def test_logout_deletes_the_session_row_not_just_the_cookie(anon_client, db_session):
    await _alice(db_session)
    await _login(anon_client)

    assert (await anon_client.post("/api/auth/logout")).status_code == 204

    assert (await anon_client.get("/api/auth/me")).status_code == 401
    assert await _sessions(db_session) == []


async def test_my_devices_list_every_browser_and_mark_this_one(
    anon_client, new_browser, db_session
):
    await _alice(db_session)
    await _login(anon_client)
    here = hash_token(anon_client.cookies.get(COOKIE_NAME))
    phone = await new_browser()
    await _login(phone, remember=True)
    there = hash_token(phone.cookies.get(COOKIE_NAME))

    response = await anon_client.get("/api/auth/sessions")
    rows = response.json()

    assert {row["token_hash"] for row in rows} == {here, there}
    assert [row["token_hash"] for row in rows if row["current"]] == [here]
    for row in rows:
        assert row["expires_at"] and row["created_at"]
    # 列表里只出现摘要：把 Cookie 值 echo 回来等于把会话交到任何能读响应的人手上。
    assert anon_client.cookies.get(COOKIE_NAME) not in response.text
    assert phone.cookies.get(COOKIE_NAME) not in response.text
    await phone.aclose()


async def test_the_device_list_records_the_browser_string(new_browser, db_session):
    """登录时存进 sessions.user_agent 的那句话，就是"我的设备"要显示的内容。"""
    await _alice(db_session)
    phone = await new_browser()
    await phone.post(
        "/api/auth/login",
        json={"username": "alice", "password": PASSWORD, "remember": False},
        headers={"user-agent": IPHONE_UA},
    )

    rows = (await phone.get("/api/auth/sessions")).json()

    assert [row["user_agent"] for row in rows] == [IPHONE_UA]
    await phone.aclose()


async def test_the_device_list_only_covers_the_signed_in_account(anon_client, db_session):
    service = AuthService(db_session)
    await _alice(db_session)
    bob = await service.create_user("bob", PASSWORD, role=ROLE_MEMBER)
    await service.create_session(bob)
    await _login(anon_client)

    rows = (await anon_client.get("/api/auth/sessions")).json()
    assert [row["token_hash"] for row in rows] == [
        hash_token(anon_client.cookies.get(COOKIE_NAME))
    ]


async def test_revoking_a_device_signs_out_that_browser_only(
    anon_client, new_browser, db_session
):
    await _alice(db_session)
    await _login(anon_client)
    here = hash_token(anon_client.cookies.get(COOKIE_NAME))
    phone = await new_browser()
    await _login(phone)
    there = hash_token(phone.cookies.get(COOKIE_NAME))

    assert (await anon_client.delete(f"/api/auth/sessions/{there}")).status_code == 204

    assert (await phone.get("/api/auth/me")).status_code == 401
    assert (await anon_client.get("/api/auth/me")).status_code == 200
    remaining = (await anon_client.get("/api/auth/sessions")).json()
    assert [row["token_hash"] for row in remaining] == [here]
    await phone.aclose()


async def test_a_member_lists_and_revokes_their_own_devices(make_signed_in_client):
    """退出自己名下某台设备动的是本人会话，角色网关不该把它拦在门外。"""
    kid = await make_signed_in_client("kid", ROLE_MEMBER)

    rows = (await kid.get("/api/auth/sessions")).json()
    assert len(rows) == 1 and rows[0]["current"] is True

    assert (await kid.delete(f"/api/auth/sessions/{rows[0]['token_hash']}")).status_code == 204
    assert (await kid.get("/api/auth/me")).status_code == 401


async def test_revoking_a_digest_that_belongs_to_somebody_else_is_a_404(
    client, db_session, signed_in_user
):
    """按摘要退出别人那台设备：既不该成功，也不该把对方踢下线。"""
    service = AuthService(db_session)
    other = await service.create_user("bob", PASSWORD, role=ROLE_MEMBER)
    foreign_token = await service.create_session(other)

    response = await client.delete(f"/api/auth/sessions/{hash_token(foreign_token)}")

    assert response.status_code == 404
    assert await service.resolve_session(foreign_token) is not None


async def test_a_digest_that_is_not_a_digest_at_all_is_rejected(client):
    """路径参数只接受 64 位十六进制，形状不对轮不到碰数据库。"""
    assert (await client.delete("/api/auth/sessions/not-a-hash")).status_code == 422


async def test_changing_the_password_keeps_this_device_and_drops_the_others(
    client, db_session, signed_in_user
):
    service = AuthService(db_session)
    signed_in_user.password_hash = hash_password(PASSWORD)
    await db_session.commit()
    other_token = await service.create_session(signed_in_user)

    response = await client.post(
        "/api/auth/password", json={"old_password": PASSWORD, "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 200  # this session survives
    assert await service.resolve_session(other_token) is None
    assert await service.authenticate("tester", PASSWORD) is None
    assert await service.authenticate("tester", NEW_PASSWORD) is not None


async def test_changing_the_password_with_a_wrong_old_one_is_rejected(
    client, db_session, signed_in_user
):
    signed_in_user.password_hash = hash_password(PASSWORD)
    await db_session.commit()

    response = await client.post(
        "/api/auth/password",
        json={"old_password": "not-it", "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 400
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_changing_to_a_weak_password_is_rejected(client, db_session, signed_in_user):
    signed_in_user.password_hash = hash_password(PASSWORD)
    await db_session.commit()

    response = await client.post(
        "/api/auth/password", json={"old_password": PASSWORD, "new_password": "short"}
    )

    assert response.status_code == 400
    kept = await AuthService(db_session).get_user(signed_in_user.id)
    assert verify_password(PASSWORD, kept.password_hash)


async def test_a_member_can_reach_the_library(client, db_session):
    """角色网关挡的是管理面；看电影对两种角色一样。"""
    await AuthService(db_session).create_user("bob", PASSWORD, role=ROLE_MEMBER)

    assert (await client.get("/api/videos")).status_code == 200
