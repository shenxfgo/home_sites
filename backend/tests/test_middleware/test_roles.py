"""成员（member）能碰哪些接口：只许改自己那份数据，管理面一律 403。

这里独立列一份"成员可写"清单，和中间件里的 ``MEMBER_WRITE_PATHS`` 一一对照。两
份名单都得改才算通过——这是故意的：放行一个新写接口应当是一次显式决定，而不是某
个路由忘了挂权限就默认谁都能写。
"""

import re

import pytest
import pytest_asyncio

from src.main import app
from src.middleware.auth import PUBLIC_API_PATHS
from src.models.user import ROLE_MEMBER, ROLE_OWNER
from src.services.auth_service import TOKEN_HASH_HEX

FORBIDDEN = "需要管理员权限"

# method + 路径模板（openapi 里的原始写法，不带具体 id）
MEMBER_WRITABLE_OPERATIONS = {
    "POST /api/auth/logout",
    "POST /api/auth/password",
    "DELETE /api/auth/sessions/{token_hash}",
    "PUT /api/preferences",
    "POST /api/favorites/{video_id}",
    "DELETE /api/favorites/{video_id}",
    "DELETE /api/history/{history_id}",
    "POST /api/notifications/{notification_id}/read",
    "POST /api/notifications/read-all",
    "POST /api/videos/new/{video_id}/viewed",
    "POST /api/videos/{video_id}/play",
    "POST /api/videos/{video_id}/progress",
    "POST /api/watchlists",
    "PUT /api/watchlists/{watchlist_id}",
    "DELETE /api/watchlists/{watchlist_id}",
    "POST /api/watchlists/{watchlist_id}/videos",
    "DELETE /api/watchlists/{watchlist_id}/videos/{video_id}",
}

# 成员连读都不给的管理面（读接口只看登录，这是唯一的例外）
OWNER_ONLY_READ_PATHS = ["/api/settings", "/api/users"]


# 路径参数要按形状填："我的设备"放行的是严格的 64 位十六进制摘要，替成 "1" 会先
# 被中间件当成不认识的地址吃一个 403，扫面就分不清"角色被拒"和"参数不合法"。
CONCRETE_PARAMS = {"token_hash": "ab" * 32}


def _concrete(path: str) -> str:
    """``/api/videos/{video_id}`` -> ``/api/videos/1``; the middleware never routes."""
    return re.sub(r"\{([^}]+)\}", lambda match: CONCRETE_PARAMS.get(match.group(1), "1"), path)


def test_the_sample_session_digest_has_the_shape_the_middleware_expects():
    assert re.fullmatch(TOKEN_HASH_HEX, CONCRETE_PARAMS["token_hash"])


def _mutating_operations() -> list[tuple[str, str, str]]:
    """Every advertised write operation, concretised for a request.

    登录接口不在这场扫面里：它公开可达，角色判断在它身上没有意义，而
    ``test_api/test_auth.py`` 已经覆盖了它。
    """
    return sorted(
        (method.upper(), path, _concrete(path))
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api") and path not in PUBLIC_API_PATHS
        for method in operations
        if method not in ("get", "head", "options")
    )


def test_the_sweep_covers_every_member_writable_operation():
    """No stale entries: everything listed as allowed must still be advertised."""
    advertised = {f"{method} {path}" for method, path, _ in _mutating_operations()}

    assert MEMBER_WRITABLE_OPERATIONS - advertised == set()


@pytest_asyncio.fixture
async def member_client(make_signed_in_client):
    """A signed-in account with no administrative rights."""
    return await make_signed_in_client("member-one", ROLE_MEMBER)


@pytest.mark.parametrize(("method", "template", "url"), _mutating_operations())
async def test_a_member_may_only_write_their_own_rows(member_client, method, template, url):
    response = await member_client.request(method, url, json={})

    if f"{method} {template}" in MEMBER_WRITABLE_OPERATIONS:
        assert response.status_code != 403, f"{method} {template} 应当放行给成员"
    else:
        assert response.status_code == 403
        assert response.json()["detail"] == FORBIDDEN


@pytest.mark.parametrize("path", OWNER_ONLY_READ_PATHS)
async def test_the_management_surface_is_not_even_readable(member_client, path):
    assert (await member_client.get(path)).status_code == 403


@pytest.mark.parametrize("path", OWNER_ONLY_READ_PATHS)
async def test_an_owner_reads_the_management_surface(client, path):
    assert (await client.get(path)).status_code == 200


async def test_a_member_keeps_the_library_readable(member_client):
    """挡住的是管理面，不是看电影：读接口对两种角色完全一样。"""
    for path in ("/api/videos", "/api/tags", "/api/notifications", "/api/history/stats"):
        assert (await member_client.get(path)).status_code == 200


async def test_an_owner_still_writes_the_management_surface(make_signed_in_client):
    """同样的请求换成 owner 就得通，否则上面那场 403 说明不了角色。"""
    owner = await make_signed_in_client("owner-two", ROLE_OWNER)

    response = await owner.post("/api/tags", json={"name": "纪录片"})

    assert response.status_code in (200, 201)
