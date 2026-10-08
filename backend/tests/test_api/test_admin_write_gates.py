"""用户管理那五道写闸门，有四道从来没被真请求敲过。

覆盖率读数（#164 那次 805 条全量）指的位置：

- `src/api/users.py` 94%，缺 `137, 155-156, 172-173`
- `src/services/auth_service.py` 97%，缺 `143, 234, 314, 409-410, 416`

这一单钉住其中六道：建号时的坏角色（`auth_service.py:234`）、改角色时的坏角色
（`:314`）、管理员重置口令时那两道强度闸门从**这一头**敲进去（`users.py:172-173`，
#163 钉的是建号与自助改密那两个调用方）、降级别人时连带踢掉他的浏览器
（`users.py:137`，含那条复合守卫的三个格子），以及停用状态在会话解析那一头的
把关（`auth_service.py:143`）。

**`users.py:155-156` 钉不住，而且不是没想到。** 那两行是 `update_status` 里
`except ValueError → 400`；`set_active` 唯一会抛的分支是 `_require_another_owner(user, "停用")`，
而它只在「`user` 是 owner 且除他之外没有别的可用管理员」时抛。走路由时 actor 一定是
一个可用的 owner（中间件按 `is_active` 把关，见 `auth_service.py:143`），而
`user.id == actor.id` 的停用早在 `users.py:151-152` 就被另一句 400 挡掉了——所以
actor 本身就是「除他之外的那个可用管理员」，那句 raise 从接口进不来。它是给未来
少一层前置检查时留的兜底，这一层只能由 `test_users.py` 的 400 与服务层用例分别签字，
中间那两行按构造不可达。

`auth_service.py:409-410, 416` 是登录限流器的锁定期过期那一路，需要动时钟，另开一单。
`auth_service.py:143` 那一行的前半句（`user is None`）同理没法从接口造出来：
`sessions.user_id` 声明的是 `ON DELETE CASCADE`，账号被删时会话行不可能还留着。
后半句（账号停用而会话行还活着）真接口也造不出来——`set_active` 是删会话而不是打标
记——所以那一条用例绕过接口直接写库，钉的是「万一库里躺着这么一行，请求仍然吃 401」。

变异电池（一次一行，两个文件每轮都先从快照复位，跑完逐文件核对 md5；一次性脚本，跑完即删）：

- N1 `auth_service.py:234` raise -> pass → 红在建号那一条，`role="wizard"` 撞上
  `ck_users_role`，IntegrityError 一路穿到 500。
- N2 `:314` 同理 → 红在改角色那一条，同一个 CHECK 约束。
- N3 `users.py:172` 换成 `except KeyError` → 红在两条重置用例上，
  `ValueError: 密码至少 8 位` / `密码过长（上限 72 字节）` 从路由穿出去变 500。
- N4 `users.py:137` revoke -> pass → 红在"降级别人"那一条（设备数仍是 1，那台浏览器仍 200）。
- N5 `:134` 丢掉 `user.id != actor.id` → 红在"降级自己"那一条。
- N6 `:134` 丢掉 `user.role != ROLE_OWNER` → 红在"升级别人"那一条。
- N7 `auth_service.py:142` 只看 `user is None` → 红在"停用状态"那一条。
- N8 **绿**：把 `create_user` 的角色闸门整块挪到重名检查之后，八条照旧全绿——
  这一单钉的是"每道闸门给得出那句中文"，钉不住两句检查的先后。要钉它得再加一条
  "重名 + 坏角色"的用例，而那句先报谁本来就没有需求说过，所以记在这里不补。
"""

import pytest
from sqlalchemy import func, select

from src.models.user import ROLE_MEMBER, ROLE_OWNER, User, UserSession
from src.services.auth_service import login_rate_limiter

PASSWORD = "a-quiet-home-lab"
BAD_ROLE = "wizard"
ROLE_MESSAGE = "角色只能是 owner/member"
SHORT_MESSAGE = "密码至少 8 位"
LONG_MESSAGE = "密码过长（上限 72 字节）"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """用例之间不互相锁定：登录尝试会经过同一个进程内限流器。"""
    login_rate_limiter().reset()
    yield
    login_rate_limiter().reset()


async def _create(client, username: str) -> dict:
    response = await client.post(
        "/api/users", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _browser_count(db_session, user_id: int) -> int:
    """直接从 sessions 表数那一行了没有，不经由任何接口。

    接口的 `signed_in_devices` 是先 purge 过期行再数，用在这里会把"被闸门删掉了"
    和"只是过期了"混成一件事。
    """
    return (
        await db_session.execute(
            select(func.count(UserSession.token_hash)).where(UserSession.user_id == user_id)
        )
    ).scalar_one()


async def _sign_in(browser, username: str, password: str = PASSWORD):
    return await browser.post("/api/auth/login", json={"username": username, "password": password})


async def _rows(client) -> dict[str, dict]:
    return {row["username"]: row for row in (await client.get("/api/users")).json()}


async def test_creating_with_a_role_outside_the_two_known_names_is_refused(client, db_session):
    """建号时 `role="wizard"` 得到那句中文，而不是穿过闸门撞在库的 CHECK 上。

    `CreateUserRequest.role` 声明的是 `str`，Pydantic 那一头什么都收；这一道是
    唯一按 ROLES 核对的地方。少了它，写库时才被 `ck_users_role` 拦下——同一个
    请求变成 500 加一句 SQL 约束名（实测 N1），而 500 里没有任何人该看见的字。
    """
    response = await client.post(
        "/api/users", json={"username": "sorcerer", "password": PASSWORD, "role": BAD_ROLE}
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == ROLE_MESSAGE
    # 拒绝得干净：这个人根本没被建出来。
    assert (
        await db_session.execute(select(User).where(User.username == "sorcerer"))
    ).scalar_one_or_none() is None


async def test_reassigning_to_an_unknown_role_is_refused_and_changes_nothing(
    client, make_user, make_client_for, db_session
):
    """改角色那一路同理，而且被拒的那一次不留任何痕迹。

    `set_role` 的顺序是先核角色、再核"最后一个管理员"，所以这一句 400 既不会把
    角色写坏，也不会走到降级那条 `revoke_sessions`（实测 N2：删掉角色核对之后，
    角色列被写成 `wizard`，先撞 CHECK 约束变成 500）。
    """
    member = await make_user("climber", ROLE_MEMBER)
    browser = await make_client_for(member)

    response = await client.put(f"/api/users/{member.id}/role", json={"role": BAD_ROLE})

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == ROLE_MESSAGE
    assert (await _rows(client))["climber"]["role"] == ROLE_MEMBER
    # 被拒的写不该顺手把人的浏览器踢下线：那一行会话还在，请求照旧 200。
    assert await _browser_count(db_session, member.id) == 1
    assert (await browser.get("/api/videos")).status_code == 200


async def test_an_admin_reset_below_the_length_floor_leaves_the_password_alone(
    client, new_browser
):
    """管理员重置口令那一头，短口令也是 400，而且原来的口令照旧能用。

    闸门本体在 #163 已经钉过；这一条钉的是 `users.py:172-173` 那两行——
    路由把 `ValueError` 换成 400 的映射（实测 N3：删掉那两行，同一个请求变成
    500 未处理异常，`ValueError` 一路穿到 ASGI）。家用界面上"重置成一个弱口令"
    是会发生的操作，所以这一路必须给得出那句中文。
    """
    created = await _create(client, "forgetful")
    browser = await new_browser()
    assert (await _sign_in(browser, "forgetful")).status_code == 200
    before = (await _rows(client))["forgetful"]["signed_in_devices"]

    response = await client.post(
        f"/api/users/{created['id']}/password", json={"new_password": "short"}
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == SHORT_MESSAGE
    # 拒绝得彻底：旧口令还在生效，那台浏览器也没被"重置即登出"顺路踢掉。
    assert (await _rows(client))["forgetful"]["signed_in_devices"] == before
    assert (await browser.get("/api/videos")).status_code == 200
    assert (await _sign_in(await new_browser(), "forgetful")).status_code == 200


async def test_an_admin_reset_beyond_the_byte_ceiling_is_refused_in_chinese(
    client, new_browser
):
    """同一道映射的第二格：按字节算的那一句也要从这一头给得出来。

    `ResetPasswordRequest` 数的是字符（`max_length=200`），所以 25 个汉字（75 字节）
    在 Pydantic 那一头合法；只有服务层按字节核对才会给出「密码过长」。这一条不
    是重复 #163：那里敲的是建号与自助改密，管理员重置是第三个调用方。
    """
    created = await _create(client, "longone")

    response = await client.post(
        f"/api/users/{created['id']}/password", json={"new_password": "影" * 25}
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == LONG_MESSAGE
    assert (await _sign_in(await new_browser(), "longone")).status_code == 200


async def test_demoting_somebody_else_signs_his_browsers_out(
    client, make_user, make_client_for
):
    """降级别人时那一枚会话必须被删掉（`users.py:137`）。

    角色是每次请求现查的，所以删了会话行他才真的退出；只改角色的话，他手里那枚
    Cookie 会一路以成员身份继续用下去（实测 N4：删掉第 137 行，这一条红在
    `signed_in_devices` 仍是 1、那台浏览器照样 200）。
    """
    coowner = await make_user("coowner", ROLE_OWNER)
    browser = await make_client_for(coowner)
    assert (await browser.get("/api/users")).status_code == 200

    response = await client.put(f"/api/users/{coowner.id}/role", json={"role": ROLE_MEMBER})

    assert response.status_code == 200, response.text
    assert response.json()["role"] == ROLE_MEMBER
    assert response.json()["signed_in_devices"] == 0
    assert (await browser.get("/api/users")).status_code == 401


async def test_demoting_yourself_spares_the_browser_you_are_clicking_from(
    client, make_user, signed_in_user
):
    """同一条守卫的另一格：把自己降级不该把自已当场踢下线。

    路由注释写的是"让他看得见'我刚把自己降级了'"，这一格就是那句话的实体；
    把 `user.id != actor.id` 那一半去掉，降级自己会连自己的会话一起删掉（实测 N5），
    于是那次操作返回的 `signed_in_devices` 变成 0，Cookie 当场作废。
    """
    await make_user("coowner", ROLE_OWNER)  # 留着另一个可用管理员，降级才不被护栏挡住

    response = await client.put(
        f"/api/users/{signed_in_user.id}/role", json={"role": ROLE_MEMBER}
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == ROLE_MEMBER
    assert response.json()["signed_in_devices"] == 1
    # 还登着，但管理面对他关门了——401 才是"被踢下线"，这里要的是 403。
    assert (await client.get("/api/videos")).status_code == 200
    assert (await client.get("/api/users")).status_code == 403


async def test_promoting_somebody_else_does_not_touch_his_browsers(
    client, make_user, make_client_for
):
    """守卫的第一格：升级不是降级，角色的新值仍是 owner，所以谁也不该被踢。

    把 `user.role != ROLE_OWNER` 那一半去掉，升级别人会顺手删掉他的会话（实测 N6），
    他那台浏览器下一跳就 401——正好是"刚升我当管理员，我反倒被踢出管理面"那种荒唐结果。
    """
    member = await make_user("climber", ROLE_MEMBER)
    browser = await make_client_for(member)

    response = await client.put(f"/api/users/{member.id}/role", json={"role": ROLE_OWNER})

    assert response.status_code == 200, response.text
    assert response.json()["role"] == ROLE_OWNER
    assert response.json()["signed_in_devices"] == 1
    assert (await browser.get("/api/videos")).status_code == 200


async def test_an_account_disabled_behind_the_api_is_still_refused(
    client, make_user, make_client_for, db_session
):
    """会话解析那一头的 `is_active` 把关（`auth_service.py:143`）真的会把请求挡成 401。

    真接口造不出"停用但会话还活着"这个状态：`set_active` 是删会话，不是打标记
    （`test_users.py` 那条 停用即断浏览器 钉的就是删）。这一条绕过接口直接写库，
    钉的是万一库里躺着这么一行——手改过、搬迁搬坏、或者以后哪里少删了一次——
    请求仍然进不来。断言里同时核对那一行**还在**，否则 401 可能被误当成"会话没了"，
    这一道闸门就白钉了。
    """
    ghost = await make_user("ghost", ROLE_MEMBER)
    browser = await make_client_for(ghost)
    assert (await browser.get("/api/videos")).status_code == 200

    ghost.is_active = False
    await db_session.commit()

    assert (await browser.get("/api/videos")).status_code == 401
    assert await _browser_count(db_session, ghost.id) == 1
    # 同一枚 Cookie 连管理面都到不了，不是只挡住某一条读接口。
    assert (await browser.get("/api/users")).status_code == 401
