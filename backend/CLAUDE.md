# CLAUDE.md - 后端开发规范

## 技术栈

- Python 3.11+
- FastAPI 0.109+
- SQLAlchemy 2.0+（异步模式）
- aiosqlite（SQLite 异步驱动）
- APScheduler（定时任务）
- FFmpeg（视频处理）
- bcrypt（口令哈希，cost 12；不引 `python-jose` / `passlib`，前者是 JWT 才需要的，后者停更且与 bcrypt>=4 有兼容告警）
- uv（依赖管理）

## 代码规范

### Python 风格

```python
# 遵循 PEP 8，4 空格缩进
# 使用类型提示
async def get_video(video_id: int) -> Video | None:
    """获取视频详情。
    
    Args:
        video_id: 视频 ID
        
    Returns:
        Video 对象或 None
    """
    pass
```

### 命名规范

- 文件名：snake_case（如 `video_service.py`）
- 类名：PascalCase（如 `VideoService`）
- 函数名：snake_case（如 `get_video`）
- 常量：UPPER_CASE（如 `VIDEO_EXTENSIONS`）

### 导入顺序

```python
# 1. 标准库
import os
from datetime import datetime

# 2. 第三方库
from fastapi import APIRouter
from sqlalchemy import select

# 3. 本地模块
from src.config import settings
from src.models.video import Video
```

## 目录结构

```
backend/
├── src/
│   ├── api/                # API 路由层
│   │   ├── videos.py      # 视频 API
│   │   ├── sources.py     # 视频源 API
│   │   ├── auth.py        # 登录/登出/当前用户/改密（没有注册接口）
│   │   └── ...
│   ├── models/            # 数据模型层
│   │   ├── video.py       # Video 模型
│   │   ├── source.py      # VideoSource 模型
│   │   ├── user.py        # User / UserSession 模型（会话只存 token 的 sha256）
│   │   ├── watch_event.py # WatchEvent 模型（观看时长的追加式日志）
│   │   ├── watchlist.py   # Watchlist / WatchlistItem 模型（手排队列，一行一条排队记录；清单归 owner_id）
│   │   ├── read_state.py  # NewVideoRead / NotificationRead（广播内容"谁读过哪一条"）
│   │   ├── favorite.py    # 个人数据一律带 user_id：收藏、历史、观看日志唯一约束都按 (人, 影片)
│   │   └── ...
│   ├── services/          # 业务逻辑层
│   │   ├── video_service.py
│   │   ├── watchlist_service.py # 片单读写，返回前一定重新查，别拿身份映射里的旧集合
│   │   ├── auth_service.py      # 口令校验、会话签发/撤销、滑动续期、登录限流计数器
│   │   └── ...
│   ├── middleware/        # HTTP 中间件
│   │   └── auth.py        # 默认拒绝的鉴权中间件 + get_current_user / get_current_user_id / get_session_token
│   ├── utils/             # 工具函数
│   │   ├── ffmpeg.py      # FFmpeg 工具
│   │   ├── file_scanner.py # 目录扫描与探针
│   │   ├── password.py    # bcrypt 哈希与校验（72 字节上限）
│   │   ├── video_search.py # 搜索串解析（源/标签/评分/时长/观看状态/丢失）
│   │   ├── file_fingerprint.py # 首尾 1MB 哈希，用来确认两份文件真是同一份
│   │   └── name_parser.py  # 文件名解析（片名、系列、季集、字幕组）
│   ├── scheduler/         # 定时任务
│   │   ├── scan_scheduler.py
│   │   └── tasks.py
│   ├── database/          # 数据库配置
│   │   ├── base.py        # SQLAlchemy 基类
│   │   └── session.py     # 会话管理
│   ├── cli.py             # 账号管理命令行（create-user / list-users / set-role / revoke-sessions）
│   ├── config.py          # 配置管理
│   └── main.py            # 应用入口
├── tests/                 # 测试文件
│   ├── conftest.py        # 共享 fixtures：db_session / anon_client / client（已登录）+ make_user / user_id / make_signed_in_client
│   ├── test_api/          # API 测试
│   ├── test_middleware/   # 鉴权中间件测试（含"每个端点匿名必 401"的全路由扫面）
│   ├── test_services/     # 服务测试
│   └── test_models/       # 模型测试
└── pyproject.toml         # 项目配置
```

## 开发流程

### 1. 创建新模型

```python
# src/models/example.py
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.database.base import Base


class Example(Base):
    """示例模型。"""

    __tablename__ = "examples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Example(id={self.id}, name='{self.name}')>"
```

### 2. 创建 Service

```python
# src/services/example_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.example import Example


class ExampleService:
    """示例服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, name: str) -> Example:
        """创建属于调用者的示例。"""
        example = Example(user_id=user_id, name=name)
        self.session.add(example)
        await self.session.commit()
        await self.session.refresh(example)
        return example

    async def get_by_id(self, user_id: int, example_id: int) -> Example | None:
        """获取示例。归属条件是查询的一部分：别人的行当不存在。"""
        result = await self.session.execute(
            select(Example).where(
                Example.id == example_id, Example.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
```

个人数据的 service 方法一律把 `user_id` 放在第一个参数（`session` 在构造函数里），写路径都先经这样一把带归属的读取，越权才会统一变成"找不到"而不是 500 或误改。全库共享的行（`videos`、`tags`、`video_sources`）反过来，不要按人过滤。

### 3. 创建 API

```python
# src/api/examples.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.middleware.auth import get_current_user_id
from src.services.example_service import ExampleService

router = APIRouter(prefix="/api/examples", tags=["examples"])


class ExampleCreate(BaseModel):
    """创建示例请求。"""
    name: str = Field(..., min_length=1, max_length=255)


class ExampleResponse(BaseModel):
    """示例响应。"""
    id: int
    name: str

    model_config = {"from_attributes": True}


async def get_example_service(
    session: AsyncSession = Depends(get_session),
) -> ExampleService:
    return ExampleService(session)


@router.post("", response_model=ExampleResponse, status_code=201)
async def create_example(
    data: ExampleCreate,
    user_id: int = Depends(get_current_user_id),
    service: ExampleService = Depends(get_example_service),
) -> ExampleResponse:
    """创建示例。"""
    return await service.create(user_id, name=data.name)
```

中间件已经保证登录，路由不必再判 401；`user_id` 只用于取"当前这份数据属于谁"。

### 4. 注册路由

```python
# src/main.py
from src.api.examples import router as examples_router
app.include_router(examples_router)
```

新路由一注册就落在 `AuthMiddleware` 后面，匿名请求拿到的就是 401，不需要（也不应该）自己往依赖里挂鉴权。确实要公开的话得改 `PUBLIC_API_PATHS`，目前只有登录与登录页的状态探测在里面。路由内部取当前用户用 `Depends(get_current_user)`，要知道自己这枚会话就用 `Depends(get_session_token)`。

### 5. 编写测试

```python
# tests/test_services/test_example_service.py
import pytest
from src.services.example_service import ExampleService


@pytest.mark.asyncio
async def test_create_example(db_session):
    """测试创建示例。"""
    service = ExampleService(db_session)
    example = await service.create(name="测试")
    assert example.id is not None
    assert example.name == "测试"
```

## 数据库规范

### 建表与改表

`init_db()` 只有 `Base.metadata.create_all`，它只补建新表、**从不修改已存在的表**。因此给已有表加约束或索引时，要把补齐用的 SQL 写成模块常量放在 `src/database/session.py`，在 `init_db` 里紧随 `create_all` 执行，并保证幂等（`IF NOT EXISTS`、先清洗再加约束）。参考 `play_history` 的"每人每片一行"：先 `DEDUPE_PLAY_HISTORY` 按 `(user_id, video_id)` 折叠老库的重复行，`DROP INDEX IF EXISTS ix_play_history_video_id` 去掉"每部视频全局一行"的旧唯一索引，再建 `ux_play_history_user_video`——顺序反了会直接建索引失败。`favorites`（`DEDUPE_FAVORITES`）与 `watchlists`（`DEDUPE_WATCHLIST_NAMES`，重名改写成 `X (2)`）同理。

加**列**走的是同一条路的另一支：`ADDED_COLUMNS` 三元组（表名、列名、`ALTER TABLE ... ADD COLUMN`）配 `PRAGMA table_info` 探测，缺哪列补哪列，再单独建需要的索引（`VIDEOS_SERIES_INDEX`、`OWNERSHIP_INDEXES`）。SQLite 的 `ADD COLUMN` 不能带非默认值的 `NOT NULL`，所以四个归属列在库里是可空的，只有模型声明为 `nullable=False`。这类修复只在启动时跑（`apply_schema_fixes(conn)`，整体可重放），测试用的 `db_session` 直接 `create_all` 建全新库，所以新列与新索引必须同时在模型里声明。

账号相关的两张表：`users`（`username` 唯一、`password_hash`、`role` 带 `CheckConstraint`、`is_active` 用停用代替删除）与 `sessions`（主键是 `token_hash`，即 Cookie 里那枚 token 的 SHA-256）。存摘要而不是 token 本身，是为了让"库被读走"不等于"人人可冒用"；删行即失效，因此退出登录和踢下线不需要等 Cookie 自然过期。会话寿命不存字段，滑动续期时按 `expires_at - created_at` 反推，"记住我"就不必单独记一档。

归属分两种。**属于人**的表带外键列：`favorites`/`play_history`/`watch_events` 有 `user_id`，`watchlists` 有 `owner_id`，唯一约束都是 `(人, 影片)` 或 `(owner_id, name)` 这种成对形式；`watchlist_items` 不加列，归属随它所在的清单。**全库广播**的内容只有一份行——`new_videos`（扫描日志）与 `notifications`（系统通知）——"读过没"另记在 `new_video_reads`/`notification_reads`（复合主键天然去重），响应里的 `read`/`is_new` 是 service 现查现挂的临时属性，不在模型列里。因此标记已读是 INSERT 而不是 UPDATE，`unread_count` 走 `~EXISTS`；删掉一条通知则是全家一起少一条，它没有归属列，M3 用 `require_role` 收敛到 owner。删影片时 `delete_videos_cascade` 要连 `new_video_reads` 一起清（SQLite 不执行 `ON DELETE CASCADE`，得手写）。

老库升级后的第一次 `create-user --role owner` 会顺手认领：`AuthService.claim_legacy_rows` 把 `user_id IS NULL` 的行交给这个账号，并把旧的 `new_videos.viewed` / `notifications.read` 一次性翻译成两张 `_reads` 表的记录（列已不存在就跳过）。这一步不做，升级后收藏与历史看起来就像被清空了。

### 模型定义

```python
# 使用 SQLAlchemy 2.0+ 风格
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    __tablename__ = "my_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)  # 使用 timezone.utc
    )
```

### 关系定义

```python
# 一对多关系
class Parent(Base):
    children: Mapped[list["Child"]] = relationship(back_populates="parent")

class Child(Base):
    parent_id: Mapped[int] = mapped_column(ForeignKey("parents.id"))
    parent: Mapped["Parent"] = relationship(back_populates="children")

# 多对多关系
class Video(Base):
    tags: Mapped[list["Tag"]] = relationship(
        secondary=video_tags, 
        back_populates="videos",
        lazy="selectin"  # 异步加载
    )
```

## 测试规范

### 测试文件结构

```
tests/
├── conftest.py           # 公共 fixtures
├── test_database.py      # 旧库跑 apply_schema_fixes：归属列、索引替换、可重放
├── test_api/
│   ├── test_videos.py
│   ├── test_isolation.py # 两个已登录客户端互相够不着对方的数据
│   └── test_sources.py
├── test_middleware/
│   └── test_auth.py      # 全路由匿名 401 扫面 + CSRF/过期/停用/滑动续期
├── test_services/
│   ├── test_video_service.py
│   ├── test_isolation.py # 收藏/历史/片单/统计/已读，全部以"另一个人"的视角问一遍
│   └── test_source_service.py
└── test_models/
    ├── test_video.py
    └── test_source.py
```

### 共享的 HTTP fixtures（不要再在各测试文件里复制）

`tests/conftest.py` 提供三份：

- `db_session` —— 每个用例一个临时库
- `anon_client` —— 未登录的 `AsyncClient`，中间件走真实逻辑；服务替身由 `extra_overrides` 这个可覆盖 fixture 注入，测试文件里写 `async def extra_overrides(): return {get_video_service: override}` 即可，不必再自带 `client`
- `client` —— `anon_client` 外加一枚有效会话 Cookie（`signed_in_user` 会建 owner 账号和对应 `sessions` 行）

隔离用例需要"第二个人"，同一份 `db_session` 上再加三个 fixture：

- `make_user(username, role)` —— 现建一个账号，service 测试用它拿两个 `user_id`
- `user_id` —— 只想要"某个账号"的 service 测试直接拿它，替代以前裸写 `video.user_id=1` 那类假身份
- `make_signed_in_client(username)` —— 再登一个账号进同一个 `app`，返回带自己 Cookie 的 `AsyncClient`，于是"A 打 B 的行"能走真实路由拿到 404

`anon_client` 默认带 `X-Requested-With: fetch`，因为中间件对所有非 GET 都要它；要测 403 分支就在单次请求上覆盖 `{CSRF_HEADER: ""}`——httpx 没法用 `None` 删掉客户端默认头。中间件里的 `async_session_maker` 由 `monkeypatch` 换成一个"交出会话但不关闭"的壳，测试才能与 `db_session` 看同一份数据。

新增 `/api/*` 端点不需要另写鉴权用例：`test_middleware/test_auth.py` 从 `app.openapi()["paths"]` 取所有非白名单端点（`{id}` 统一替换成 `1`，跳过 head/options）参数化成 401 断言。别改走 `app.routes`——这版 FastAPI 把 include 进来的路由存成 `_IncludedRouter` 对象，没有 `.path` 属性。

### 测试示例

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_video(client: AsyncClient):
    """测试创建视频 API。"""
    response = await client.post("/api/videos", json={
        "title": "测试视频",
        "filepath": "/test/video.mp4",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "测试视频"
```

## 常见问题

### 1. 异步会话

```python
# 正确：使用 async_session_maker
async with async_session_maker() as session:
    result = await session.execute(query)

# 错误：不要在异步函数中使用同步会话
```

### 2. 关系加载

```python
# 异步环境下使用 selectin 或 joined 加载关系
tags: Mapped[list["Tag"]] = relationship(
    secondary=video_tags,
    lazy="selectin"  # 避免 MissingGreenlet 错误
)
```

### 3. 时区处理

```python
# 使用 timezone.utc 而不是 datetime.utcnow()
from datetime import datetime, timezone

created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc)
)
```

SQLite 不存时区：写进去的是 UTC，读回来的 `datetime` **不带 tzinfo**，和 `datetime.now(timezone.utc)` 直接比大小会抛 `can't compare offset-naive and offset-aware datetimes`。凡要拿库里读出的时间做比较或运算，先过一道 `_as_utc()`（`value if value.tzinfo else value.replace(tzinfo=timezone.utc)`），`auth_service` 里就是这么做的。

同理，测试里改过某行的时间后要看真实结果，用 `await db_session.refresh(row)` 重新读；`expire_all()` 之后靠关系属性懒加载会抛 `MissingGreenlet`。

## 依赖管理

```bash
# 添加依赖
uv add package-name

# 添加开发依赖
uv add --dev package-name

# 同步依赖
uv sync

# 运行命令
uv run python script.py
uv run pytest
```
