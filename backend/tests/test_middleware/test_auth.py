"""The default-deny middleware: who gets 401, 403, or through."""
import re
from datetime import datetime, timedelta, timezone

import pytest

from src.main import app
from src.middleware.auth import CSRF_HEADER, PUBLIC_API_PATHS
from src.models.user import UserSession
from src.services.auth_service import (
    COOKIE_NAME,
    INVALID_CREDENTIALS,
    AuthService,
    hash_token,
)

UNAUTHENTICATED = "未认证"


def _concrete(path: str) -> str:
    """``/api/videos/{video_id}`` -> ``/api/videos/1``; the middleware never routes."""
    return re.sub(r"\{[^}]+\}", "1", path)


def _api_calls() -> list[tuple[str, str]]:
    """Every operation the API advertises, except the two login endpoints.

    Read from the OpenAPI schema rather than ``app.routes``: this FastAPI keeps
    included routers wrapped, so the flat list is only there after startup.
    """
    return sorted(
        (method.upper(), _concrete(path))
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api") and path not in PUBLIC_API_PATHS
        for method in operations
        if method not in ("head", "options")
    )


@pytest.mark.parametrize(("method", "path"), _api_calls())
async def test_every_api_endpoint_denies_an_anonymous_caller(anon_client, method, path):
    """The sweep is the point: a route nobody remembered to guard still 401s."""
    response = await anon_client.request(method, path)

    assert response.status_code == 401
    assert response.json()["detail"] == UNAUTHENTICATED


async def test_the_login_endpoints_stay_reachable(anon_client):
    status = await anon_client.get("/api/auth/status")
    failed = await anon_client.post(
        "/api/auth/login", json={"username": "nobody", "password": "wrong"}
    )

    assert status.status_code == 200
    assert failed.status_code == 401
    assert failed.json()["detail"] == INVALID_CREDENTIALS


async def test_non_api_paths_are_not_gated(anon_client):
    assert (await anon_client.get("/health")).status_code == 200
    # The SPA shell is public by design; the data behind it is not.
    assert (await anon_client.get("/")).status_code != 401


async def test_a_write_without_the_custom_header_is_refused(client):
    """A cross-site form sends cookies but cannot set this header."""
    response = await client.post("/api/videos/1/play", headers={CSRF_HEADER: ""})

    assert response.status_code == 403


async def test_a_read_needs_no_custom_header(client):
    """<video>/<img>/<track> requests carry the cookie and no extra header."""
    response = await client.get("/api/videos", headers={CSRF_HEADER: ""})

    assert response.status_code == 200


async def test_an_unknown_token_is_the_same_as_no_token(anon_client):
    anon_client.cookies.set(COOKIE_NAME, "never-issued")

    assert (await anon_client.get("/api/videos")).status_code == 401


async def test_an_expired_session_is_refused_and_cleaned_up(
    anon_client, db_session, signed_in_user
):
    stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    db_session.add(
        UserSession(
            token_hash=hash_token("expired-token"),
            user_id=signed_in_user.id,
            expires_at=stale,
            last_seen_at=stale,
        )
    )
    await db_session.commit()
    anon_client.cookies.set(COOKIE_NAME, "expired-token")

    assert (await anon_client.get("/api/videos")).status_code == 401
    assert await db_session.get(UserSession, hash_token("expired-token")) is None


async def test_disabling_an_account_signs_its_sessions_out(client, db_session, signed_in_user):
    await AuthService(db_session).set_active(signed_in_user, False)

    assert (await client.get("/api/videos")).status_code == 401


async def test_an_account_used_for_a_while_gets_its_session_pushed_forward(client, db_session):
    token_hash = hash_token(client.cookies.get(COOKIE_NAME))
    row = await db_session.get(UserSession, token_hash)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    row.created_at = now_utc - timedelta(hours=12)  # the sliding window is the lifetime
    row.last_seen_at = now_utc - timedelta(minutes=10)
    row.expires_at = now_utc + timedelta(minutes=1)
    await db_session.commit()

    assert (await client.get("/api/videos")).status_code == 200

    await db_session.refresh(row)  # the values that were written, not the ones we set
    assert row.expires_at > now_utc + timedelta(hours=11)
    assert row.last_seen_at > now_utc - timedelta(minutes=5)
