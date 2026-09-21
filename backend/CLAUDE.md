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
│   │   ├── auth.py        # 登录/登出/当前用户/改密/我的设备（列表 + 退出单台，没有注册接口）
│   │   ├── users.py       # 账号管理（仅 owner）：列/建/改角色/停用启用/重置密码/踢下线，没有删除账号
│   │   ├── preferences.py # 个人偏好 GET/PUT（按 user_id 一行 JSON，登录用户各写各的）
│   │   └── ...
│   ├── models/            # 数据模型层
│   │   ├── video.py       # Video 模型
│   │   ├── source.py      # VideoSource 模型
│   │   ├── user.py        # User / UserSession 模型（会话只存 token 的 sha256）
│   │   ├── preference.py  # UserPreference 模型（(user_id PK, prefs JSON)，界面偏好按人）
│   │   ├── watch_event.py # WatchEvent 模型（观看时长的追加式日志）
│   │   ├── watchlist.py   # Watchlist / WatchlistItem 模型（手排队列，一行一条排队记录；清单归 owner_id）
│   │   ├── read_state.py  # NewVideoRead / NotificationRead（广播内容"谁读过哪一条"）
│   │   ├── favorite.py    # 个人数据一律带 user_id：收藏、历史、观看日志唯一约束都按 (人, 影片)
│   │   └── ...
│   ├── services/          # 业务逻辑层
│   │   ├── video_service.py
│   │   ├── watchlist_service.py # 片单读写，返回前一定重新查，别拿身份映射里的旧集合
│   │   ├── auth_service.py      # 口令校验、会话签发/撤销（全部或单台）、滑动续期、登录限流计数器
│   │   ├── preference_service.py # 偏好的读与按键合并写；能落库的键由 API 层的 Pydantic 模型限定
│   │   └── ...
│   ├── middleware/        # HTTP 中间件
│   │   └── auth.py        # 默认拒绝的鉴权 + 角色网关（MEMBER_WRITE_PATHS / OWNER_ONLY_READ_PATHS）+ get_current_user / get_current_user_id / get_session_token / require_owner
│   ├── storage/           # 取文件的接缝：上层只知道 locator 字符串，不知道文件在哪、怎么读
│   │   ├── base.py        # MediaStorage 协议 + Capabilities + FoundFile + UnsupportedStorage + S3_SCHEME
│   │   ├── local.py       # 本地与 NAS 共用的一份实现（NAS 就是挂载成本地路径）
│   │   ├── s3.py          # boto3 那份，只读，Capabilities.local_path=False
│   │   └── __init__.py    # storage_for_source(type) / storage_for_locator(路径) / fingerprint(路径)
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
│   ├── test_storage/      # 存储接缝用例：本地 locator 逐字节不变、S3（moto 在内存里演一个桶）、扫描走接缝
│   ├── test_middleware/   # 鉴权中间件测试（两张全路由扫面：匿名必 401、member 打管理面必 403）
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

角色同理，而且**新加接口要动的地方在中间件，不在路由上**：成员该能写的接口必须登记进 `MEMBER_WRITE_PATHS`，否则成员一律 403（忘了登记会立刻被 `test_roles.py` 的扫面用例和使用者发现，这正是想要的失败方向）；管理面（账号、系统配置）连读都限 owner 的话写进 `OWNER_ONLY_READ_PATHS`。只有确实需要拿到操作者 `User` 对象的路由（改角色、停用、重置密码）才额外挂 `Depends(require_owner)`。

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

`sessions` 没有自增 id，所以「我的设备」拿这枚摘要当行的地址用（`TOKEN_HASH_HEX` 是 `auth_service` 与中间件共用的一份形状）：路由用 `Path(pattern=TOKEN_HASH_HEX)` 卡参数，形状不对在路由层就是 422；中间件白名单里对应一条 `^/api/auth/sessions/{摘要}$`，成员也在 `MEMBER_WRITE_PATHS` 里放行这一条。`AuthService.revoke_session(user_id, token_hash)` 的匹配条件带上 `user_id`，所以别人的摘要只会得到 404 而不是把他踢下线；列表（`list_sessions`）按 `last_seen_at` 倒序取全部行、不做分页，一个家的浏览器就几台。响应回给浏览器的是摘要，不是 Cookie 值。

归属分两种。**属于人**的表带外键列：`favorites`/`play_history`/`watch_events` 有 `user_id`，`watchlists` 有 `owner_id`，唯一约束都是 `(人, 影片)` 或 `(owner_id, name)` 这种成对形式；`watchlist_items` 不加列，归属随它所在的清单。**全库广播**的内容只有一份行——`new_videos`（扫描日志）与 `notifications`（系统通知）——"读过没"另记在 `new_video_reads`/`notification_reads`（复合主键天然去重），响应里的 `read`/`is_new` 是 service 现查现挂的临时属性，不在模型列里。因此标记已读是 INSERT 而不是 UPDATE，`unread_count` 走 `~EXISTS`；删掉一条通知则是全家一起少一条，它没有归属列，所以这两个删除口不在 `MEMBER_WRITE_PATHS` 里——语义仍是家庭级，只是动手的换成 owner。删影片时 `delete_videos_cascade` 要连 `new_video_reads` 一起清（SQLite 不执行 `ON DELETE CASCADE`，得手写）。

`settings` 与 `user_preferences` 是两张不同的表，别混：前者全家一份（扫描间隔、缩略图尺寸、默认转码格式），改一次所有人的播放都受影响，读写都限 owner；后者一人一份（`user_id` 主键 + `prefs` JSON），走 `/api/preferences`，成员改自己的主题不该碰着别人的屏幕。写入是按键合并（`save_prefs` 只覆盖 patch 里非空的键），响应字段由 API 层的 Pydantic 模型限定，所以加一项偏好只是加一个字段，不必改表。JSON 列的坑：原地 `row.prefs["k"]=v` SQLAlchemy 看不见，必须换一个新 dict 赋回去。

从 `settings.theme` 迁到 `user_preferences` 靠 `session.py` 里两条幂等 SQL：`INHERIT_THEME_IN_PREFERENCES` 把全家共用的那个老值发给每个还没有偏好行的账号（`INSERT OR IGNORE`，重复启动不会覆盖任何人改过的值），`DROP_SHARED_THEME_SETTING` 再删掉 `settings` 里的 `theme` 行。顺序不能反，反了所有人的选择就凭空变成默认浅色。

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

## 存储接缝（src/storage）

上层（api / services）手上只有一个 locator 字符串，也就是 `videos.filepath`：`D:\…`、`\\nas\…`、`s3://bucket/key`。要碰这个文件就走 `src/storage/__init__.py`，别在业务代码里 `open()` 或 `os.path.*`：

- `storage_for_source(source.type)`：列举整个源时用，按 `type` 分发（`local` 与 `nas` 用同一份本地实现，`minio` 用 S3 实现）
- `storage_for_locator(video.filepath)`：只有单条记录时用，靠 `s3://` 前缀自己判断，省掉每次 Range 请求都去 join `video_sources`

几条必须守住的：

- **`utils/` 不能 import `src.storage`**：`storage/__init__.py` 会加载两份实现，实现又依赖 utils，一 import 就绕成环、服务起不来。所以"什么算视频文件"留在 `utils/file_scanner.py`，首尾各 1MB 的摘要算法留在 `utils/file_fingerprint.py`，由存储层反向引用它们
- **locator 的字符串形状就是扫描去重的键**：`filepath` 靠全等比对，分隔符差一个就会让整库既"全部新增"又"全部丢失"。`LocalMediaStorage.list_videos()` 直接复用原来那份 `scan_directory()`（`os.walk` + `os.path.join`）就是为了这一点；要动路径拼接，先看 `tests/test_storage/test_local_storage.py` 里那几条逐字节比对
- **够不着不等于空**：只有 `reachable()` 为真才允许把记录标成丢失。凭证写错、挂载盘掉线都走 `reachable() == False`，此时列表当空处理但一行都不判定
- **能力问 `capabilities`，别嗅探 `s3://`**：`local_path` 是真正承重的位——FFmpeg 得在文件里 seek，对象存储给不了，于是缩略图、转码、内嵌字幕一起关闭；`sidecar_subtitles` 管外挂字幕那条路。拿不到本地路径的路由返回中文 400，不是 500
- **S3 客户端按配置缓存，不按进程缓存**：用户改完 `.env` 之后，进程里那台旧密钥签的客户端还在偷偷用

`boto3` 是可选依赖（`.[s3]`），不装也能起服务，真去读对象存储时才提示「请安装 .[s3]」；`moto`（在 `.[dev]` 里）在内存中演一个桶来测 S3 实现，不碰网络——它证明的是客户端接线正确，不代表真服务器就这么答，端点行为仍要人肉验一次。两个包都没装时相关用例 `importorskip` 跳过而不是报错。

## 测试规范

### 测试文件结构

```
tests/
├── conftest.py           # 公共 fixtures
├── test_database.py      # 旧库跑 apply_schema_fixes：归属列、索引替换、可重放
├── test_api/
│   ├── test_videos.py
│   ├── test_isolation.py # 两个已登录客户端互相够不着对方的数据
│   ├── test_users.py     # 账号管理面：护栏（不许停用自己、必须留下一个 owner）、降级即踢会话
│   ├── test_preferences.py # 偏好按人存、按键合并、默认值
│   └── test_sources.py
├── test_middleware/
│   ├── test_auth.py      # 全路由匿名 401 扫面 + CSRF/过期/停用/滑动续期
│   └── test_roles.py     # 全路由 member 403 扫面（另存一份成员可写清单）+ owner 通行
├── test_services/
│   ├── test_video_service.py
│   ├── test_isolation.py # 收藏/历史/片单/统计/已读，全部以"另一个人"的视角问一遍
│   ├── test_user_admin.py # AuthService 的建号/改角色/停用/重置密码/踢会话
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

- `make_user(username, role)` —— 现建一个账号，service 测试用它拿两个 `user_id`；`role` 默认 owner，测成员面时传 `ROLE_MEMBER`
- `user_id` —— 只想要"某个账号"的 service 测试直接拿它，替代以前裸写 `video.user_id=1` 那类假身份
- `make_signed_in_client(username, role)` —— 再登一个账号进同一个 `app`，返回带自己 Cookie 的 `AsyncClient`，于是"A 打 B 的行"能走真实路由拿到 403/404
- `make_client_for(user)` —— 已经握着 `User` 行（要它的 id，或待会儿要停用这个账号）时用这个，它只发会话不再建人
- `new_browser()` —— 独立 Cookie 罐的裸客户端：`client` 与 `anon_client` 其实是同一个对象，用密码走真实登录流程的用例必须另开一个罐子，否则会把主客户端的会话换掉

`anon_client` 默认带 `X-Requested-With: fetch`，因为中间件对所有非 GET 都要它；要测 403 分支就在单次请求上覆盖 `{CSRF_HEADER: ""}`——httpx 没法用 `None` 删掉客户端默认头。中间件里的 `async_session_maker` 由 `monkeypatch` 换成一个"交出会话但不关闭"的壳，测试才能与 `db_session` 看同一份数据。

新增 `/api/*` 端点不需要另写鉴权用例：`test_middleware/test_auth.py` 从 `app.openapi()["paths"]` 取所有非白名单端点（`{id}` 统一替换成 `1`，跳过 head/options）参数化成 401 断言。别改走 `app.routes`——这版 FastAPI 把 include 进来的路由存成 `_IncludedRouter` 对象，没有 `.path` 属性。

`test_middleware/test_roles.py` 用同一份 openapi 扫面角色面：每个写接口对 member 要么 403、要么在白名单里 404/2xx 通过。它**自带一份成员可写清单**（`MEMBER_WRITABLE_OPERATIONS`），与中间件的 `MEMBER_WRITE_PATHS` 一一对照——两边都要改才算放行一个接口，这是故意的：给成员开一个写口应当是一次显式决定，而不是某个路由忘了挂权限就默认谁都能写。这一处替路径参数填的值按形状走（`CONCRETE_PARAMS`）：`{token_hash}` 填的是一枚合法的 64 位十六进制摘要，替成 `1` 会先被中间件当成不认识的地址吃一个 403，扫面就分不清"角色被拒"和"参数不合法"（匿名那一轮没这个问题，401 排在角色判定之前）。

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
uv sync                       # 只装运行依赖
uv sync --extra dev           # 要跑 pytest（uv run pytest 用的是这一套，plain sync 连 dev 都不装）
uv sync --extra s3            # 要读对象存储视频源（boto3）

# 运行命令
uv run python script.py
uv run pytest
```
