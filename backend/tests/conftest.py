"""Shared fixtures.

`client` is signed in as an owner and `anon_client` carries no session cookie:
the auth middleware denies every /api route by default, so an unauthenticated
test client would only ever see 401. Both send the CSRF header the browser
client always sends, so a test that wants 403 passes its own value.

Ownership needs more than one person: `user_id` gives a service test an account
to write rows as, and `make_signed_in_client` adds further signed-in clients so
a test can ask for somebody else's data.
"""

import sys
import itertools
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add parent directory to Python path so 'src' becomes importable
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Import all models so they register with Base.metadata before create_all
import src.models  # noqa: F401, E402
from src.database import get_session  # noqa: E402
from src.database.base import Base  # noqa: E402
from src.main import app  # noqa: E402
from src.middleware.auth import CSRF_HEADER, CSRF_HEADER_VALUE  # noqa: E402
from src.models.user import ROLE_OWNER, User, UserSession  # noqa: E402
from src.services.auth_service import COOKIE_NAME, hash_token  # noqa: E402

TEST_SESSION_TOKEN = "test-session-token"


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh in-memory database session for each test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class _SharedSession:
    """Hand the test's session to the middleware without letting it close it."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> "_SharedSession":
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


@pytest_asyncio.fixture
async def extra_overrides() -> dict:
    """A test module replaces this to add its own dependency overrides."""
    return {}


@pytest_asyncio.fixture
async def make_user(db_session):
    """Create accounts on demand, so a test can name the people it needs."""
    counter = itertools.count(1)

    async def _make(username: str | None = None, role: str = ROLE_OWNER) -> User:
        user = User(
            username=username or f"person{next(counter)}",
            password_hash="not-used-in-tests",
            role=role,
        )
        db_session.add(user)
        await db_session.commit()
        return user

    return _make


@pytest_asyncio.fixture
async def user_id(make_user) -> int:
    """The id of a fresh account, for the service tests that need an owner."""
    return (await make_user("service-owner")).id


@pytest_asyncio.fixture
async def signed_in_user(db_session) -> User:
    """An owner with a live session row matching TEST_SESSION_TOKEN."""
    user = User(username="tester", password_hash="not-used-in-tests", role=ROLE_OWNER)
    db_session.add(user)
    await db_session.commit()
    now = datetime.now(timezone.utc)
    db_session.add(
        UserSession(
            token_hash=hash_token(TEST_SESSION_TOKEN),
            user_id=user.id,
            expires_at=now + timedelta(days=1),
            last_seen_at=now,
        )
    )
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def anon_client(db_session, extra_overrides, monkeypatch):
    """A client with no session cookie, for the 401 paths."""
    monkeypatch.setattr(
        "src.middleware.auth.async_session_maker", _SharedSession(db_session)
    )

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides.update(extra_overrides)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        # The real frontend sends this on every request; a test can override it
        # per-request to reach the CSRF branch.
        headers={CSRF_HEADER: CSRF_HEADER_VALUE},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(anon_client, signed_in_user):
    """A client signed in as an owner."""
    anon_client.cookies.set(COOKIE_NAME, TEST_SESSION_TOKEN)
    return anon_client


@pytest_asyncio.fixture
async def make_signed_in_client(db_session, anon_client, make_user):
    """Build a second signed-in client, so a test has two people to isolate.

    The extra client shares the session the middleware already resolves, which
    is what lets A ask for a row B owns and see the answer.
    """
    clients: list[httpx.AsyncClient] = []

    async def _make(username: str, role: str = ROLE_OWNER) -> httpx.AsyncClient:
        user = await make_user(username, role)
        token = f"token-{username}"
        now = datetime.now(timezone.utc)
        db_session.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user.id,
                expires_at=now + timedelta(days=1),
                last_seen_at=now,
            )
        )
        await db_session.commit()
        ac = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={CSRF_HEADER: CSRF_HEADER_VALUE},
            cookies={COOKIE_NAME: token},
        )
        clients.append(ac)
        return ac

    yield _make

    for ac in clients:
        await ac.aclose()
