"""账号管理命令行。

应用没有注册接口，账号只能在这里建：

    uv run python -m src.cli create-user --username admin --role owner
    uv run python -m src.cli list-users
    uv run python -m src.cli set-role --username admin --role member
    uv run python -m src.cli revoke-sessions --username admin
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from src.database import async_session_maker, init_db
from src.models.user import ROLES
from src.services.auth_service import AuthService, normalize_username


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="src.cli", description="视频库账号管理")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="新建账号")
    create.add_argument("--username", required=True)
    create.add_argument("--role", choices=ROLES, default="member")
    create.add_argument("--display-name", default=None)
    create.add_argument("--password", default=None, help="省略时交互式输入（推荐）")

    sub.add_parser("list-users", help="列出账号")

    set_role = sub.add_parser("set-role", help="修改角色")
    set_role.add_argument("--username", required=True)
    set_role.add_argument("--role", required=True, choices=ROLES)

    revoke = sub.add_parser("revoke-sessions", help="撤销会话（踢下线）")
    revoke.add_argument("--username", default=None, help="省略则撤销全部账号的会话")

    return parser


async def _create_user(service: AuthService, args: argparse.Namespace) -> int:
    password = args.password or _prompt_password()
    try:
        user = await service.create_user(
            args.username, password, role=args.role, display_name=args.display_name
        )
    except ValueError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    print(f"已创建账号 {user.username}（角色 {user.role}）")
    return 0


def _prompt_password() -> str:
    """Ask twice so a typo does not lock someone out of an account just made."""
    first = getpass.getpass("密码：")
    if len(first) < 8:
        raise SystemExit("失败：密码至少 8 位")
    if getpass.getpass("再输入一次：") != first:
        raise SystemExit("失败：两次输入不一致")
    return first


async def _list_users(service: AuthService) -> int:
    users = await service.list_users()
    if not users:
        print("还没有账号，执行 create-user 新建第一个。")
        return 0
    for user in users:
        state = "启用" if user.is_active else "已停用"
        last = user.last_login_at.strftime("%Y-%m-%d %H:%M") if user.last_login_at else "从未登录"
        print(f"#{user.id:<4} {user.username:<20} {user.role:<7} {state:<4} 上次登录 {last}")
    return 0


async def _set_role(service: AuthService, args: argparse.Namespace) -> int:
    user = await service.get_user_by_username(args.username)
    if not user:
        print(f"失败：账号 {normalize_username(args.username)} 不存在", file=sys.stderr)
        return 1
    await service.set_role(user, args.role)
    print(f"{user.username} 的角色已改为 {user.role}")
    return 0


async def _revoke_sessions(service: AuthService, args: argparse.Namespace) -> int:
    if args.username:
        user = await service.get_user_by_username(args.username)
        if not user:
            print(f"失败：账号 {normalize_username(args.username)} 不存在", file=sys.stderr)
            return 1
        removed = await service.revoke_sessions(user.id)
    else:
        removed = 0
        for user in await service.list_users():
            removed += await service.revoke_sessions(user.id)
    print(f"已撤销 {removed} 个会话")
    return 0


async def _run(args: argparse.Namespace) -> int:
    await init_db()
    async with async_session_maker() as session:
        service = AuthService(session)
        if args.command == "create-user":
            return await _create_user(service, args)
        if args.command == "list-users":
            return await _list_users(service)
        if args.command == "set-role":
            return await _set_role(service, args)
        return await _revoke_sessions(service, args)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
