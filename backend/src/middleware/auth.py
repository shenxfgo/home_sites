"""请求级鉴权：默认拒绝的中间件，以及给路由用的当前用户依赖。

默认拒绝而不是逐路由挂 Depends：/api 下的端点数量只会增长，漏挂一个就等于整套
方案失效，而且新加接口的人未必知道要挂。反过来“忘记放行”会立刻挡在手上，是能被
发现的 bug。

角色走同一个方向：成员只被放行"改自己那份数据"的写接口（见 MEMBER_WRITE_PATHS），
其余非 GET 一律 403。管理面漏登记最多是成员点了个按钮没反应，漏挂权限则是谁都能删库。
"""

from typing import Awaitable, Callable
import re

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from src.database import get_session
from src.database.session import async_session_maker
from src.models.user import ROLE_OWNER, User
from src.services.auth_service import COOKIE_NAME, TOKEN_HASH_HEX, AuthService

# 登录前必须可达的接口，其余 /api/* 一律要求有效会话。
PUBLIC_API_PATHS = frozenset({"/api/auth/login", "/api/auth/status"})

# 跨站表单发不出这个头，配合 SameSite=Lax 就足够挡住 CSRF。
CSRF_HEADER = "x-requested-with"
CSRF_HEADER_VALUE = "fetch"


def _path_pattern(literal: str) -> re.Pattern[str]:
    return re.compile(f"^{literal}$")


def _numbered(*segments: str) -> re.Pattern[str]:
    """把路径按段拼成正则，``{id}`` 那一段换成 ``\\d+``。"""
    return re.compile("^" + "".join(r"/\d+" if s == "{id}" else s for s in segments) + "$")


# 成员（非 owner）唯一可以写的路径：**只动自己那份数据**的接口。
#
# 这里列的是白名单而不是 owner 清单，理由和登录网关一样是方向问题：新加一个
# 管理写接口忘了登记，成员会得到 403，立刻就有人在手上喊；反过来默认放行，则是
# 静悄悄地把"谁能删库"交给了每一个登录用户。
MEMBER_WRITE_PATHS: tuple[re.Pattern[str], ...] = (
    _path_pattern("/api/auth/logout"),
    _path_pattern("/api/auth/password"),
    # 退出自己名下的某台设备同样只动本人的会话，路由再按 (hash, user_id) 定位。
    re.compile(rf"^/api/auth/sessions/{TOKEN_HASH_HEX}$"),
    _path_pattern("/api/preferences"),
    _numbered("/api/favorites", "{id}"),
    _numbered("/api/history", "{id}"),
    _numbered("/api/notifications", "{id}", "/read"),
    _path_pattern("/api/notifications/read-all"),
    _numbered("/api/videos/new", "{id}", "/viewed"),
    _numbered("/api/videos", "{id}", "/play"),
    _numbered("/api/videos", "{id}", "/progress"),
    _numbered("/api/watchlists"),
    _numbered("/api/watchlists", "{id}"),
    _numbered("/api/watchlists", "{id}", "/videos"),
    _numbered("/api/watchlists", "{id}", "/videos", "{id}"),
)

# 管理面本身就是账号清单与系统配置，成员连读都不该读到——这一条是"读接口只看
# 登录"的例外：给成员看"扫描间隔是多少"没有用处，只会多一处需要小心的入口。
OWNER_ONLY_READ_PATHS: tuple[re.Pattern[str], ...] = (
    _path_pattern("/api/users"),
    re.compile(r"^/api/users/\d+(/(role|status|password|sessions))?$"),
    _path_pattern("/api/settings"),
    re.compile(r"^/api/settings/.+$"),
)

_FORBIDDEN_OWNER = "需要管理员权限"


def member_may_write(path: str) -> bool:
    """Whether a signed-in member is allowed to send a write to ``path``."""
    return any(pattern.match(path) for pattern in MEMBER_WRITE_PATHS)


def member_may_read(path: str) -> bool:
    return not any(pattern.match(path) for pattern in OWNER_ONLY_READ_PATHS)


class AuthMiddleware(BaseHTTPMiddleware):
    """Attach ``request.state.user`` for every protected call, else 401."""

    def __init__(
        self,
        app: Callable[..., Awaitable[Response]],
        *,
        session_factory: Callable[[], AsyncSession] | None = None,
    ) -> None:
        super().__init__(app)
        # 不在这里固化：测试会替换模块级的 async_session_maker。
        self._session_factory = session_factory

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 静态资源与 SPA 路由不属于 API，交给下游处理。
        if not path.startswith("/api") or path in PUBLIC_API_PATHS:
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return _unauthorized()

        factory = self._session_factory or async_session_maker
        async with factory() as session:
            resolved = await AuthService(session).resolve_session(token)

        if resolved is None:
            return _unauthorized()

        user, _sess = resolved
        if request.method != "GET" and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
            return JSONResponse(status_code=403, content={"detail": "缺少请求头 X-Requested-With"})

        if user.role != ROLE_OWNER:
            if request.method == "GET":
                if not member_may_read(path):
                    return _forbidden()
            elif not member_may_write(path):
                return _forbidden()

        # 只留 id：ORM 对象属于这个短命会话，路由要用得走自己的会话。
        request.state.user_id = user.id
        request.state.user_role = user.role
        request.state.session_token = token
        return await call_next(request)


def _unauthorized() -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": "未认证"})


def _forbidden() -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": _FORBIDDEN_OWNER})


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """The signed-in user the middleware authenticated for this request."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:  # pragma: no cover - the middleware already answered 401
        raise HTTPException(status_code=401, detail="未认证")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="未认证")
    return user


async def get_current_user_id(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> int:
    """The signed-in id, for routes that only scope a query by it.

    Calling :func:`get_current_user` directly keeps this one lookup: as a
    sub-dependency FastAPI would otherwise resolve the user a second time.
    """
    return (await get_current_user(request, session)).id


async def get_session_token(request: Request) -> str:
    """The raw session token, so a route can revoke its own session."""
    token = getattr(request.state, "session_token", None)
    if not token:  # pragma: no cover
        raise HTTPException(status_code=401, detail="未认证")
    return token


def require_role(*roles: str) -> Callable[..., Awaitable[User]]:
    """A dependency that answers 403 unless the caller holds one of ``roles``.

    The middleware already refuses members on the management surface; this is
    for the handful of routes that need the acting :class:`User` anyway, so the
    rule reads off the signature instead of depending on a path pattern.
    """

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=_FORBIDDEN_OWNER)
        return user

    return _dependency


require_owner = require_role(ROLE_OWNER)
