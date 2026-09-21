"""认证服务：口令校验、会话签发与撤销、账号管理。

会话存库而不是签发自包含 token，是为了让 退出登录 与 踢下线 真的生效：
删掉 sessions 行，Cookie 立刻失效。
"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.favorite import Favorite
from src.models.history import PlayHistory
from src.models.user import ROLES, ROLE_OWNER, User, UserSession
from src.models.watch_event import WatchEvent
from src.models.watchlist import Watchlist
from src.utils.password import hash_password, password_too_long, verify_password

# 浏览器原生资源请求（<video> / <img> / <track>）只能靠 Cookie 带上身份。
COOKIE_NAME = "sid"

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,64}$")
MIN_PASSWORD_CHARS = 8

# 口令或账号错误时对外只说这一句：不区分“用户不存在”，避免把账号枚举出去。
INVALID_CREDENTIALS = "账号或密码错误"


def normalize_username(raw: str) -> str:
    """Trim and lowercase the login name so 大小写 不影响同一个账号。"""
    return raw.strip().lower()


def hash_token(token: str) -> str:
    """Only the digest of a session token is stored, never the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# sessions 的主键就是这枚摘要，所以"我的设备"拿它当地址用：它是 sha256 的十六进制
# 输出（不是 Cookie 值，也推不回原 token），但仍只有 64 个字符这一种合法形状。
TOKEN_HASH_HEX = r"[0-9a-f]{64}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """SQLite 的 DATETIME 读回来不带 tzinfo，而写入的一律是 UTC。"""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _column_exists(session: AsyncSession, table: str, column: str) -> bool:
    """Whether a leftover column is still in the schema (it is never added back)."""
    rows = await session.execute(text(f"PRAGMA table_info({table})"))
    return column in {row[1] for row in rows}


class AuthService:
    """Everything the auth API and the CLI need from the user/session tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------- 查询 ----------

    async def needs_setup(self) -> bool:
        """True while no account exists, i.e. nobody can sign in yet."""
        result = await self.session.execute(select(User.id).limit(1))
        return result.scalar_one_or_none() is None

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == normalize_username(username))
        )
        return result.scalar_one_or_none()

    async def list_users(self) -> list[User]:
        result = await self.session.execute(select(User).order_by(User.id))
        return list(result.scalars().all())

    # ---------- 登录 ----------

    async def authenticate(self, username: str, password: str) -> User | None:
        """Return the user when credentials pass, otherwise None.

        A disabled account fails the same way a wrong password does, so the
        response never confirms that a username exists.
        """
        user = await self.get_user_by_username(username)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def create_session(
        self, user: User, *, remember: bool = False, user_agent: str | None = None
    ) -> str:
        """Issue a session and return the raw token; only its hash is stored."""
        lifetime = timedelta(days=settings.remember_me_days) if remember else timedelta(
            hours=settings.session_hours
        )
        token = secrets.token_urlsafe(32)
        self.session.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user.id,
                expires_at=_utc_now() + lifetime,
                user_agent=(user_agent or "")[:256] or None,
            )
        )
        user.last_login_at = _utc_now()
        await self.session.commit()
        return token

    async def resolve_session(self, token: str) -> tuple[User, UserSession] | None:
        """Map a cookie token to its user, sliding a short session forward.

        The slide window is the session's original lifetime, so a 记住我 session
        keeps its 30-day horizon without storing the flag separately.
        """
        result = await self.session.execute(
            select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        sess = result.scalar_one_or_none()
        if not sess:
            return None

        now = _utc_now()
        expires_at = _as_utc(sess.expires_at)
        if expires_at <= now:
            await self.session.delete(sess)
            await self.session.commit()
            return None

        user = await self.session.get(User, sess.user_id)
        if user is None or not user.is_active:
            return None

        lifetime = expires_at - _as_utc(sess.created_at)
        if (now - _as_utc(sess.last_seen_at)).total_seconds() >= 300:
            sess.last_seen_at = now
            sess.expires_at = now + lifetime
            await self.session.commit()

        return user, sess

    async def logout(self, token: str) -> None:
        await self.session.execute(
            delete(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        await self.session.commit()

    async def revoke_sessions(self, user_id: int, *, keep_token_hash: str | None = None) -> int:
        """Drop a user's sessions, optionally sparing the caller's own."""
        stmt = delete(UserSession).where(UserSession.user_id == user_id)
        if keep_token_hash:
            stmt = stmt.where(UserSession.token_hash != keep_token_hash)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0

    async def list_sessions(self, user_id: int) -> list[UserSession]:
        """This account's live sessions, newest activity first.

        No pagination: a household has a handful of browsers, and the rows
        disappear on their own when they expire or get revoked.
        """
        result = await self.session.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.last_seen_at.desc(), UserSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_session(self, user_id: int, token_hash: str) -> bool:
        """Sign out one browser of this account; False when the row is not its own.

        The user_id is part of the match on purpose: the caller addresses a
        session by its digest, and without the scope a guessed hash would sign
        out a stranger's device.
        """
        result = await self.session.execute(
            delete(UserSession).where(
                UserSession.user_id == user_id, UserSession.token_hash == token_hash
            )
        )
        await self.session.commit()
        return (result.rowcount or 0) > 0

    # ---------- 账号 ----------

    async def create_user(
        self,
        username: str,
        password: str,
        *,
        role: str = "member",
        display_name: str | None = None,
    ) -> User:
        """Create an account. The CLI is the only caller until M3 adds 用户管理."""
        cleaned = normalize_username(username)
        if not USERNAME_RE.match(cleaned):
            raise ValueError("账号名需为 3-64 位小写字母、数字或 . _ -")
        validate_password_strength(password)
        if role not in ROLES:
            raise ValueError(f"角色只能是 {'/'.join(ROLES)}")
        if await self.get_user_by_username(cleaned):
            raise ValueError("账号已存在")

        user = User(
            username=cleaned,
            password_hash=hash_password(password),
            role=role,
            display_name=(display_name or cleaned)[:64],
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        if role == ROLE_OWNER:
            # The first owner inherits whatever a single-user database already
            # wrote; later ones find nothing left to claim.
            await self.claim_legacy_rows(user.id)
        return user

    async def claim_legacy_rows(self, user_id: int) -> None:
        """Hand every unowned row over to ``user_id``.

        Upgrade order is what this fixes: the household already watched and
        favourited titles before accounts existed, and without a claim the
        history and favourites would come back empty on the first login and
        look like deleted data.
        """
        for model, column in (
            (Favorite, Favorite.user_id),
            (PlayHistory, PlayHistory.user_id),
            (WatchEvent, WatchEvent.user_id),
            (Watchlist, Watchlist.owner_id),
        ):
            await self.session.execute(
                update(model).where(column.is_(None)).values(**{column.name: user_id})
            )
        await self.session.commit()
        await self._inherit_read_state(user_id)

    async def _inherit_read_state(self, user_id: int) -> None:
        """Turn the pre-split global ``viewed`` / ``read`` flags into read rows.

        Those two columns only exist in a database written before read state
        moved to per-person tables, so each statement is skipped when its column
        is gone rather than failing the whole upgrade.
        """
        for table, flag, read_table, fk_column in (
            ("new_videos", "viewed", "new_video_reads", "new_video_id"),
            ("notifications", "read", "notification_reads", "notification_id"),
        ):
            if not await _column_exists(self.session, table, flag):
                continue
            await self.session.execute(
                text(
                    f"INSERT OR IGNORE INTO {read_table} ({fk_column}, user_id) "
                    f"SELECT id, :user_id FROM {table} WHERE {flag} = 1"
                ),
                {"user_id": user_id},
            )
        await self.session.commit()

    async def change_password(
        self, user: User, old_password: str, new_password: str, *, keep_token_hash: str
    ) -> None:
        """Rotate the password, then sign every other device out."""
        if not verify_password(old_password, user.password_hash):
            raise ValueError("原密码不正确")
        validate_password_strength(new_password)
        user.password_hash = hash_password(new_password)
        await self.session.commit()
        await self.revoke_sessions(user.id, keep_token_hash=keep_token_hash)

    async def set_role(self, user: User, role: str) -> User:
        if role not in ROLES:
            raise ValueError(f"角色只能是 {'/'.join(ROLES)}")
        if user.role == ROLE_OWNER and role != ROLE_OWNER:
            await self._require_another_owner(user, "降级")
        user.role = role
        await self.session.commit()
        return user

    async def set_active(self, user: User, active: bool) -> User:
        if not active:
            await self._require_another_owner(user, "停用")
        user.is_active = active
        if not active:
            await self.revoke_sessions(user.id)
        await self.session.commit()
        return user

    async def reset_password(self, user: User, new_password: str) -> User:
        """Set a new password without the old one, then sign that account out.

        Only 用户管理 calls this — an owner handing a forgotten password back —
        so every session of that account is dropped and the person has to sign
        in with the new one. Self-service changes go through
        :meth:`change_password`, which keeps the caller's session alive.
        """
        validate_password_strength(new_password)
        user.password_hash = hash_password(new_password)
        await self.session.commit()
        await self.revoke_sessions(user.id)
        return user

    async def count_owners(self, *, exclude_user_id: int | None = None) -> int:
        """How many usable administrators there are, optionally sparing one."""
        stmt = select(User.id).where(User.role == ROLE_OWNER, User.is_active.is_(True))
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        result = await self.session.execute(stmt)
        return len(result.all())

    async def _require_another_owner(self, user: User, action: str) -> None:
        """Refuse to lock the household out of its own admin surface.

        一个只剩管理员的库要是被降级或被停用，就再没人能改视频源、扫描、建号，
        命令行之外的恢复途径也没了。
        """
        if user.role != ROLE_OWNER:
            return
        if await self.count_owners(exclude_user_id=user.id) == 0:
            raise ValueError(f"至少要保留一个可用的管理员，不能{action}最后一个")


def validate_password_strength(password: str) -> None:
    """Reject passwords bcrypt cannot fully use, or that are trivially short."""
    if len(password) < MIN_PASSWORD_CHARS:
        raise ValueError(f"密码至少 {MIN_PASSWORD_CHARS} 位")
    if password_too_long(password):
        raise ValueError("密码过长（上限 72 字节）")


def login_rate_limiter() -> "LoginRateLimiter":
    """The process-wide limiter; module level on purpose, like scan progress."""
    global _RATE_LIMITER
    if _RATE_LIMITER is None:
        _RATE_LIMITER = LoginRateLimiter(
            max_failures=settings.login_max_failures,
            lockout_seconds=settings.login_lockout_minutes * 60,
        )
    return _RATE_LIMITER


_RATE_LIMITER: "LoginRateLimiter | None" = None


class LoginRateLimiter:
    """In-memory failure counter, keyed by client IP and account.

    Survives nothing across restarts, which is acceptable for a home LAN: the
    goal is to stop a scripted guesser, not a determined attacker.
    """

    def __init__(self, *, max_failures: int, lockout_seconds: int) -> None:
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._failures: dict[tuple[str, str], tuple[int, datetime]] = {}

    def locked_for(self, key: tuple[str, str]) -> int:
        """Seconds left on the lockout, or 0 when the caller may try."""
        entry = self._failures.get(key)
        if not entry:
            return 0
        count, last_at = entry
        if count < self.max_failures:
            return 0
        elapsed = (_utc_now() - last_at).total_seconds()
        left = self.lockout_seconds - elapsed
        if left <= 0:
            self._failures.pop(key, None)
            return 0
        return int(left) + 1

    def record_failure(self, key: tuple[str, str]) -> None:
        count, last_at = self._failures.get(key, (0, _utc_now()))
        if (_utc_now() - last_at).total_seconds() > self.lockout_seconds:
            count = 0
        self._failures[key] = (count + 1, _utc_now())

    def record_success(self, key: tuple[str, str]) -> None:
        self._failures.pop(key, None)

    def reset(self) -> None:
        """Test hook: forget every recorded failure."""
        self._failures.clear()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<LoginRateLimiter tracked={len(self._failures)}>"


def user_payload(user: User) -> dict[str, Any]:
    """The shape /api/auth/me and a successful login hand to the frontend."""
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "display_name": user.display_name,
    }


def session_payload(sess: UserSession, *, current: bool = False) -> dict[str, Any]:
    """One row of 我的设备: which browser still holds this session open.

    ``token_hash`` is the digest rather than the cookie value, so echoing it
    back to the browser leaks nothing and still gives the frontend an address
    to revoke that device by.
    """
    return {
        "token_hash": sess.token_hash,
        "current": current,
        "user_agent": sess.user_agent,
        "created_at": sess.created_at,
        "last_seen_at": sess.last_seen_at,
        "expires_at": sess.expires_at,
    }
