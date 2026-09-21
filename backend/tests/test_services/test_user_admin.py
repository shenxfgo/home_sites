"""账号管理在服务层的样子：两条护栏、一次改密、一次踢下线。

接口那边的用例见 ``tests/test_api/test_users.py``，这里管的是规则本身——把
"最后一个管理员"这道判断留在服务层，命令行和界面就走的是同一套约束。
"""

import pytest

from src.models.user import ROLE_MEMBER, ROLE_OWNER
from src.services.auth_service import AuthService
from src.utils.password import verify_password

PASSWORD = "long-enough-password"
ANOTHER = "another-long-enough"


@pytest.fixture
def auth(db_session):
    return AuthService(db_session)


async def _owner(auth, username="owner") -> object:
    return await auth.create_user(username, PASSWORD, role=ROLE_OWNER)


async def test_creating_the_first_owner_reports_one_admin(auth):
    await _owner(auth)

    assert await auth.count_owners() == 1


async def test_the_last_admin_cannot_be_demoted(auth):
    owner = await _owner(auth)

    with pytest.raises(ValueError) as exc:
        await auth.set_role(owner, ROLE_MEMBER)

    assert "至少要保留一个可用的管理员" in str(exc.value)
    assert owner.role == ROLE_OWNER  # 报错之后没有被顺手改掉


async def test_a_second_admin_unblocks_the_demotion(auth):
    owner = await _owner(auth)
    backup = await _owner(auth, "backup")

    await auth.set_role(backup, ROLE_MEMBER)

    assert backup.role == ROLE_MEMBER
    assert await auth.count_owners() == 1


async def test_the_last_admin_cannot_be_disabled(auth):
    owner = await _owner(auth)

    with pytest.raises(ValueError) as exc:
        await auth.set_active(owner, False)

    assert "至少要保留一个可用的管理员" in str(exc.value)
    assert owner.is_active is True


async def test_a_demoted_admin_no_longer_counts_as_available(auth):
    owner = await _owner(auth)
    backup = await _owner(auth, "backup")
    await auth.set_role(backup, ROLE_MEMBER)
    await auth.set_active(backup, False)

    # 停用的成员不算后备，所以还是只剩一个能用的管理员。
    assert await auth.count_owners() == 1
    with pytest.raises(ValueError):
        await auth.set_active(owner, False)


async def _sessions_of(auth, user_id: int) -> int:
    from sqlalchemy import func, select

    from src.models.user import UserSession

    return await auth.session.scalar(
        select(func.count(UserSession.token_hash)).where(UserSession.user_id == user_id)
    )


async def test_resetting_a_password_replaces_the_hash_and_signs_everyone_out(auth):
    member = await auth.create_user("forgetful", PASSWORD)
    token = await auth.create_session(member)
    assert await _sessions_of(auth, member.id) == 1

    await auth.reset_password(member, ANOTHER)

    assert verify_password(ANOTHER, member.password_hash)
    assert not verify_password(PASSWORD, member.password_hash)
    assert await _sessions_of(auth, member.id) == 0

    # 新密码能换回一枚新会话。
    fresh = await auth.authenticate("forgetful", ANOTHER)
    assert fresh is not None
    new_token = await auth.create_session(fresh)
    assert new_token != token
    assert await _sessions_of(auth, member.id) == 1


async def test_a_short_password_never_reaches_the_hash(auth):
    member = await auth.create_user("shorty", PASSWORD)

    with pytest.raises(ValueError) as exc:
        await auth.reset_password(member, "tiny")

    assert "至少" in str(exc.value)
    assert verify_password(PASSWORD, member.password_hash)
