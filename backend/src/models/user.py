from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"
ROLES: tuple[str, str] = (ROLE_OWNER, ROLE_MEMBER)


class User(Base):
    """A person who can sign in. Accounts are created from the CLI, never by a
    public form, so there is no self-service registration path to guard.

    Disabling instead of deleting keeps one member's history and favourites
    readable if they come back to the shared library later.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ('{ROLE_OWNER}', '{ROLE_MEMBER}')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_MEMBER)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class UserSession(Base):
    """One signed-in browser, keyed by the hash of its cookie token.

    Storing sessions rather than signing the token is what makes 退出登录 and
    踢下线 real: the row disappears, so the cookie stops working immediately.
    """

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)

    def __repr__(self) -> str:
        return f"<UserSession(user_id={self.user_id}, expires_at={self.expires_at})>"
