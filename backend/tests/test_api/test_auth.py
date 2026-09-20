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
    user = await _alice(db_session)
    await service.set_active(user, False)

    assert (await _login(anon_client)).status_code == 401


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


async def test_a_member_can_reach_the_api(client, db_session):
    """M1 has no role gating yet; M3 makes this a 403 and updates this test."""
    await AuthService(db_session).create_user("bob", PASSWORD, role=ROLE_MEMBER)

    assert (await client.get("/api/videos")).status_code == 200
