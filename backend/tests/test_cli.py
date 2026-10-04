"""The account CLI: what an operator can type, and what they read back.

No app, no HTTP — the handlers take an ``AuthService``, so a test hands them the
session fixture's own database and one account. The plumbing around them
(``init_db`` and the engine's session maker) is swapped for a borrowed test
session so the command → handler dispatch is covered too.
"""

import argparse
import getpass
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from src import cli
from src.models.user import ROLE_MEMBER, ROLE_OWNER, UserSession
from src.services.auth_service import AuthService, hash_token
from src.utils.password import verify_password

GOOD_PASSWORD = "long-enough-passphrase"


def _args(**overrides) -> argparse.Namespace:
    """A parsed namespace, the way argparse hands one to a handler."""
    base = {
        "command": None,
        "username": None,
        "role": ROLE_MEMBER,
        "display_name": None,
        "password": GOOD_PASSWORD,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class _BorrowedSession:
    """Hand the CLI the test's session without letting it close the connection."""

    def __init__(self, session) -> None:
        self._session = session

    def __call__(self) -> "_BorrowedSession":
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


# ---------- 参数表 ----------


def test_create_user_defaults_to_member_and_asks_for_a_password():
    args = cli.build_parser().parse_args(["create-user", "--username", "admin"])
    assert args.command == "create-user"
    assert args.role == ROLE_MEMBER
    assert args.password is None
    assert args.display_name is None


def test_set_role_needs_both_the_account_and_the_new_role():
    args = cli.build_parser().parse_args(
        ["set-role", "--username", "admin", "--role", "member"]
    )
    assert (args.username, args.role) == ("admin", "member")
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["set-role", "--username", "admin"])


def test_revoke_sessions_username_is_optional():
    parser = cli.build_parser()
    assert parser.parse_args(["revoke-sessions"]).username is None
    assert parser.parse_args(["revoke-sessions", "--username", "admin"]).username == "admin"


def test_a_role_outside_the_list_is_rejected_before_any_query():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["create-user", "--username", "admin", "--role", "root"])


def test_no_command_is_not_a_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


# ---------- 交互式输入口令 ----------


def test_the_password_is_asked_twice_and_returned_once(monkeypatch):
    prompts: list[str] = []
    answers = iter([GOOD_PASSWORD, GOOD_PASSWORD])

    def fake_getpass(prompt: str = "") -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(getpass, "getpass", fake_getpass)
    assert cli._prompt_password() == GOOD_PASSWORD
    assert len(prompts) == 2


def test_a_short_password_stops_the_cli_before_it_writes(monkeypatch):
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "short")
    with pytest.raises(SystemExit) as excinfo:
        cli._prompt_password()
    assert "至少" in str(excinfo.value)


def test_two_different_entries_are_not_a_password(monkeypatch):
    answers = iter(["first-passphrase", "second-passphrase"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    with pytest.raises(SystemExit) as excinfo:
        cli._prompt_password()
    assert "不一致" in str(excinfo.value)


# ---------- create-user ----------


async def test_create_user_writes_the_account_and_echoes_it(db_session, capsys):
    service = AuthService(db_session)

    assert await cli._create_user(service, _args(username="Admin", role=ROLE_OWNER)) == 0

    user = await service.get_user_by_username("admin")
    assert user is not None
    assert user.role == ROLE_OWNER
    # 不给 --display-name 就沿用账号名，界面上不会出现空白昵称。
    assert user.display_name == "admin"
    assert "已创建账号 admin（角色 owner）" in capsys.readouterr().out


async def test_create_user_hashes_the_prompted_password(db_session, monkeypatch):
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": GOOD_PASSWORD)
    service = AuthService(db_session)

    assert await cli._create_user(
        service, _args(username="typed", password=None)
    ) == 0

    user = await service.get_user_by_username("typed")
    assert user is not None
    assert verify_password(GOOD_PASSWORD, user.password_hash)


async def test_create_user_reports_why_it_refused(db_session, capsys):
    service = AuthService(db_session)

    assert await cli._create_user(service, _args(username="bad name")) == 1

    assert "失败" in capsys.readouterr().err
    assert await service.get_user_by_username("bad name") is None


async def test_create_user_refuses_a_name_already_taken(db_session, make_user, capsys):
    await make_user("admin", ROLE_OWNER)

    assert await cli._create_user(AuthService(db_session), _args(username="ADMIN")) == 1

    assert "账号已存在" in capsys.readouterr().err


# ---------- list-users ----------


async def test_listing_an_empty_database_says_so(db_session, capsys):
    assert await cli._list_users(AuthService(db_session)) == 0
    assert "还没有账号" in capsys.readouterr().out


async def test_listing_shows_role_state_and_last_login(db_session, make_user, capsys):
    owner = await make_user("admin", ROLE_OWNER)
    owner.last_login_at = datetime(2026, 10, 4, 8, 30, tzinfo=timezone.utc)
    member = await make_user("viewer", ROLE_MEMBER)
    member.is_active = False
    await db_session.commit()

    assert await cli._list_users(AuthService(db_session)) == 0

    out = capsys.readouterr().out
    assert "2026-10-04 08:30" in out
    assert "启用" in out and "已停用" in out


async def test_listing_an_account_that_never_signed_in(db_session, make_user, capsys):
    await make_user("viewer", ROLE_MEMBER)

    await cli._list_users(AuthService(db_session))

    assert "从未登录" in capsys.readouterr().out


# ---------- set-role ----------


async def test_set_role_reaches_the_account(db_session, make_user, capsys):
    await make_user("viewer", ROLE_MEMBER)
    service = AuthService(db_session)

    assert await cli._set_role(service, _args(username="Viewer", role=ROLE_OWNER)) == 0

    assert (await service.get_user_by_username("viewer")).role == ROLE_OWNER
    assert "viewer 的角色已改为 owner" in capsys.readouterr().out


async def test_set_role_on_an_unknown_account(db_session, capsys):
    result = await cli._set_role(
        AuthService(db_session), _args(username="ghost", role=ROLE_MEMBER)
    )

    assert result == 1
    assert "不存在" in capsys.readouterr().err


async def test_set_role_cannot_demote_the_last_owner(db_session, make_user, capsys):
    await make_user("admin", ROLE_OWNER)
    service = AuthService(db_session)

    assert await cli._set_role(service, _args(username="admin", role=ROLE_MEMBER)) == 1

    assert "不能降级最后一个" in capsys.readouterr().err
    assert (await service.get_user_by_username("admin")).role == ROLE_OWNER


# ---------- revoke-sessions ----------


async def _give_a_device(db_session, user_id: int, token: str) -> None:
    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    db_session.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user_id,
            expires_at=now,
            last_seen_at=now,
        )
    )
    await db_session.commit()


async def test_revoke_sessions_targets_one_account(db_session, make_user, capsys):
    admin = await make_user("admin", ROLE_OWNER)
    viewer = await make_user("viewer", ROLE_MEMBER)
    await _give_a_device(db_session, admin.id, "admin-token")
    await _give_a_device(db_session, viewer.id, "viewer-token")

    assert await cli._revoke_sessions(
        AuthService(db_session), _args(command="revoke-sessions", username="admin")
    ) == 0

    assert "已撤销 1 个会话" in capsys.readouterr().out
    # viewer 的设备必须还在：撤销是按人来的，不是把所有人踢下线。
    remaining = (await db_session.execute(select(UserSession))).scalars().all()
    assert [s.user_id for s in remaining] == [viewer.id]


async def test_revoke_sessions_without_an_account_kicks_everyone_off(
    db_session, make_user, capsys
):
    admin = await make_user("admin", ROLE_OWNER)
    viewer = await make_user("viewer", ROLE_MEMBER)
    await _give_a_device(db_session, admin.id, "admin-token")
    await _give_a_device(db_session, viewer.id, "viewer-token")

    assert await cli._revoke_sessions(
        AuthService(db_session), _args(command="revoke-sessions", username=None)
    ) == 0

    assert "已撤销 2 个会话" in capsys.readouterr().out
    left = (
        await db_session.execute(select(func.count()).select_from(UserSession))
    ).scalar_one()
    assert left == 0


async def test_revoke_sessions_on_an_unknown_account(db_session, capsys):
    assert await cli._revoke_sessions(
        AuthService(db_session), _args(command="revoke-sessions", username="ghost")
    ) == 1

    assert "不存在" in capsys.readouterr().err


# ---------- 接线：main 与 _run ----------

_COMMANDS = [
    ("create-user", ["create-user", "--username", "admin"], "_create_user"),
    ("list-users", ["list-users"], "_list_users"),
    ("set-role", ["set-role", "--username", "admin", "--role", "member"], "_set_role"),
    ("revoke-sessions", ["revoke-sessions"], "_revoke_sessions"),
]


@pytest.mark.parametrize("command,argv,handler", _COMMANDS)
def test_main_dispatches_the_command_it_parsed(monkeypatch, command, argv, handler):
    seen: list[str] = []

    async def fake_run(args):
        seen.append(args.command)
        return 7

    monkeypatch.setattr(cli, "_run", fake_run)

    assert cli.main(argv) == 7
    assert seen == [command]


@pytest.mark.parametrize("command,argv,handler", _COMMANDS)
async def test_run_opens_one_session_and_calls_the_handler(
    db_session, monkeypatch, argv, command, handler
):
    """``_run`` 自己只做三件事：建好库、开一个会话、按命令名分发。"""
    started: list[str] = []

    async def fake_init_db() -> None:
        started.append("init_db")

    monkeypatch.setattr(cli, "init_db", fake_init_db)
    monkeypatch.setattr(cli, "async_session_maker", _BorrowedSession(db_session))
    called: list[tuple[str, AuthService]] = []

    async def fake_handler(service, args=None):
        called.append((handler, service))
        return 0

    monkeypatch.setattr(cli, handler, fake_handler)

    assert await cli._run(cli.build_parser().parse_args(argv)) == 0

    assert started == ["init_db"]
    assert [name for name, _ in called] == [handler]
    assert called[0][1].session is db_session
