"""锁定的「到期」那一路：窗口走完真的放行、旧计数真的忘掉。

`auth_service.py` 里限流器的到期分支（:408-410）和慢猜测者的计数清零（:416）此前
一次也没被执行过——`test_auth.py` 那条只钉住了「五次之后会锁」，从没钉过「锁会自己解开」。
线上有人被锁十分钟之后以为账号坏了，这一路必须有人签字。

时钟是假的：整模块 monkeypatch `auth_service._utc_now`，一步跳满一个窗口，不睡 600 秒。

变异电池（2026-10-08 实测，一次一处，六处全红）：M1 `left <= 0` → `<` 红 3 条，
M2 删掉那次 `pop` 红 1 条（抹账），M3 删掉 `return 0` 红 3 条（到期那一瞬 `int(0)+1 == 1`
还是真值，账号被永久锁死），M4 `Retry-After` 不递减红 1 条，M5 删掉 `record_failure`
的整段重置红 1 条，M6 重置条件 `>` → `>=` 红 1 条（整窗口间隔那条）。
原有 `test_auth.py` 那二十几条在六轮里一条没红——这一族此前确实无人看着。

有一格是**拆不红**的，记在这里而不是假装钉住：接口那一层的"慢猜测者"（每 601 秒错一次）
在 M2 和 M5 下都照旧全绿（临时探针实测，两条接口层用例各跑一轮，探针文件跑完即删），
因为路由每次都先问 `locked_for`——`:409` 的 pop 会把旧账先抹掉，删了 pop 还有 `:416`
的重置。两道守卫是刻意重叠的，所以 `:416` 只能像上面那样钉在计数器这一层
（`record_failure` 之间不读锁）。
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.models.user import ROLE_OWNER
from src.services import auth_service as auth_module
from src.services.auth_service import AuthService, LoginRateLimiter, login_rate_limiter

PASSWORD = "a-quiet-home-lab"
KEY = ("127.0.0.1", "alice")


class Clock:
    """A frozen UTC clock the test advances by whole windows."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch):
    fake = Clock(datetime(2026, 10, 8, 3, 0, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(auth_module, "_utc_now", fake)
    return fake


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """The limiter is process-wide, so one test's failures must not leak."""
    login_rate_limiter().reset()
    yield
    login_rate_limiter().reset()


def _limiter() -> LoginRateLimiter:
    """A standalone limiter reading the thresholds the shipped route uses."""
    live = login_rate_limiter()
    return LoginRateLimiter(max_failures=live.max_failures, lockout_seconds=live.lockout_seconds)


async def _alice(db_session):
    return await AuthService(db_session).create_user("alice", PASSWORD, role=ROLE_OWNER)


async def _login(client, username="alice", password=PASSWORD):
    return await client.post(
        "/api/auth/login",
        json={"username": username, "password": password, "remember": False},
    )


async def _fail(limiter: LoginRateLimiter, clock: Clock, times: int, gap: float) -> None:
    """`times` failures `gap` seconds apart, asked straight of the counter."""
    for index in range(times):
        if index:
            clock.advance(gap)
        limiter.record_failure(KEY)


async def test_the_lock_lifts_at_the_exact_end_of_the_window(clock):
    limiter = _limiter()
    await _fail(limiter, clock, limiter.max_failures, 0)

    clock.advance(limiter.lockout_seconds - 1)
    assert limiter.locked_for(KEY) > 0

    clock.advance(1)
    assert limiter.locked_for(KEY) == 0


async def test_an_expired_lock_is_forgotten_so_the_next_failure_starts_at_one(clock):
    limiter = _limiter()
    await _fail(limiter, clock, limiter.max_failures, 0)

    clock.advance(limiter.lockout_seconds)
    assert limiter.locked_for(KEY) == 0

    # 放行之后这条必须已经从表里抹掉：留着旧计数的话，下一次失败是第 6 格，
    # 而第 6 格在窗口之内又会把账号锁死——等于锁从来不解开。
    limiter.record_failure(KEY)
    assert limiter.locked_for(KEY) == 0


async def test_gaps_of_exactly_the_window_still_add_up_to_a_lock(clock):
    limiter = _limiter()
    await _fail(limiter, clock, limiter.max_failures, limiter.lockout_seconds)

    # 刻意选下的边界：只有「比窗口还慢」才清零，隔整整一个窗口照样累加。
    assert limiter.locked_for(KEY) > 0


async def test_failures_far_apart_never_accumulate_into_a_lock(clock):
    limiter = _limiter()
    await _fail(limiter, clock, limiter.max_failures * 2, limiter.lockout_seconds + 1)

    assert limiter.locked_for(KEY) == 0


async def test_the_api_locks_and_then_lets_the_account_back_in(anon_client, db_session, clock):
    await _alice(db_session)
    limiter = login_rate_limiter()

    for _ in range(limiter.max_failures):
        assert (await _login(anon_client, password="wrong-one")).status_code == 401
    assert (await _login(anon_client)).status_code == 429

    clock.advance(limiter.lockout_seconds)
    assert (await _login(anon_client)).status_code == 200
    # 解锁不是只放开这一把钥匙：旧计数一并抹掉，下一轮失败重新从第一格数起。
    assert (await _login(anon_client, password="wrong-one")).status_code == 401
    assert (await _login(anon_client, password="wrong-one")).status_code == 401


async def test_retry_after_counts_the_remaining_seconds_down(anon_client, db_session, clock):
    await _alice(db_session)
    limiter = login_rate_limiter()

    for _ in range(limiter.max_failures):
        await _login(anon_client, password="wrong-one")

    first = int((await _login(anon_client)).headers["retry-after"])
    clock.advance(300)
    second = int((await _login(anon_client)).headers["retry-after"])

    assert first == limiter.lockout_seconds + 1
    assert second == first - 300
