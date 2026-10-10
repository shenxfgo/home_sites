"""认证依赖里那两道从 HTTP 走不到的保险。

中间件先答了 401/403，所以 `get_current_user` 的复查（用户行没了 / 已被停用）和
`require_role` 的角色闸门在接口那条路上永远撞不到：前者 #135 量过一次——把那半句
`not user.is_active` 删掉，整套用例全绿，因为「停用会切断会话」是删除会话那一半签的字；
后者连行覆盖都只缺 190 那一句 raise，189 的判断和 191 的放行都被 owner 的请求走过了。

按 #165 / #172 / #178 的先例，这一族直接敲依赖本身：请求用一条真的 ASGI scope 造，
中间件留下的 `state.user_id` 照实写上去，会话用真的 `db_session`。

九格变异（只动这两道闸门所在的四行，`src/middleware/auth.py` 提交时一个字节没改）实测：

- 只丢 `is_active` 那半句 -> 红 1（停用那条），只丢「行没了」那半句 -> 红 1（失踪那条）。
  两种形状各自单独钉过一次，合在一条 `or` 里也不算被一条用例盖住。
- 整道闸门改成永远不成立 -> 红 2；状态码 401->403 -> 红 2；中文文案换掉 -> 红 2。
- 角色闸门改成永远不成立 -> 红 1，**只有这一格**说明成员其实一条 HTTP 用例都到不了这里。
- 角色的回答 403->401 -> 红 1；文案换成「未认证」-> 红 1。
- 判断反过来（`in` 代替 `not in`）-> 红 22：`/api/users` 那六条挂着 `require_owner` 的路由
  上，20 条真请求全红（本文件 2 条）。放行面早被真请求签过，没人敲过的一直只有拒绝面。
"""

from http import HTTPStatus

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.middleware.auth import get_current_user, require_owner
from src.models.user import ROLE_MEMBER, ROLE_OWNER

UNAUTHENTICATED = "未认证"
FORBIDDEN = "需要管理员权限"


def _request_left_by_the_middleware(user_id: int) -> Request:
    """一条中间件已经放行、只在 `state` 上留下 id 的请求。"""
    request = Request({"type": "http"})
    request.state.user_id = user_id
    return request


@pytest.mark.asyncio
async def test_the_dependency_refuses_a_user_row_that_is_gone(db_session):
    """会话还活着、用户行没了：这道复查是唯一还站在路由前面的闸门。"""
    with pytest.raises(HTTPException) as info:
        await get_current_user(_request_left_by_the_middleware(9_999_999), db_session)

    assert info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert info.value.detail == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_the_dependency_refuses_an_account_disabled_after_the_token_was_issued(
    db_session, make_user
):
    """`user is None` 与 `not user.is_active` 是同一句里的两种形状，各钉一次。"""
    frozen = await make_user("frozen-account")
    frozen.is_active = False
    await db_session.commit()

    with pytest.raises(HTTPException) as info:
        await get_current_user(_request_left_by_the_middleware(frozen.id), db_session)

    assert info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert info.value.detail == UNAUTHENTICATED


@pytest.mark.asyncio
async def test_the_dependency_hands_the_route_the_row_it_just_checked(db_session, signed_in_user):
    """正向对照：闸门不是永远拒绝，放行时交出去的就是那一行。"""
    user = await get_current_user(_request_left_by_the_middleware(signed_in_user.id), db_session)

    assert user.id == signed_in_user.id
    assert user.username == "tester"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_require_owner_refuses_a_member_that_reached_the_dependency(db_session, make_user):
    """成员今天到不了这一层，是因为中间件先说了「需要管理员权限」。"""
    member = await make_user("member-belt", role=ROLE_MEMBER)

    with pytest.raises(HTTPException) as info:
        await require_owner(user=member)

    assert info.value.status_code == HTTPStatus.FORBIDDEN
    assert info.value.detail == FORBIDDEN


@pytest.mark.asyncio
async def test_require_owner_hands_back_the_owner_it_checked(db_session, make_user):
    owner = await make_user("owner-belt", role=ROLE_OWNER)

    user = await require_owner(user=owner)

    assert user.id == owner.id
    assert user.role == ROLE_OWNER
