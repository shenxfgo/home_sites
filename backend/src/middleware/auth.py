"""请求级鉴权：默认拒绝的中间件，以及给路由用的当前用户依赖。

默认拒绝而不是逐路由挂 Depends：/api 下的端点数量只会增长，漏挂一个就等于整套
方案失效，而且新加接口的人未必知道要挂。反过来“忘记放行”会立刻挡在手上，是能被
发现的 bug。
"""

from typing import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from src.database import get_session
from src.database.session import async_session_maker
from src.models.user import User
from src.services.auth_service import COOKIE_NAME, AuthService

# 登录前必须可达的接口，其余 /api/* 一律要求有效会话。
PUBLIC_API_PATHS = frozenset({"/api/auth/login", "/api/auth/status"})

# 跨站表单发不出这个头，配合 SameSite=Lax 就足够挡住 CSRF。
CSRF_HEADER = "x-requested-with"
CSRF_HEADER_VALUE = "fetch"


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

        # 只留 id：ORM 对象属于这个短命会话，路由要用得走自己的会话。
        request.state.user_id = user.id
        request.state.session_token = token
        return await call_next(request)


def _unauthorized() -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": "未认证"})


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


async def get_session_token(request: Request) -> str:
    """The raw session token, so a route can revoke its own session."""
    token = getattr(request.state, "session_token", None)
    if not token:  # pragma: no cover
        raise HTTPException(status_code=401, detail="未认证")
    return token
