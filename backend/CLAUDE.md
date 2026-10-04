# CLAUDE.md - 后端开发规范

## 技术栈

- Python 3.11+
- FastAPI 0.109+
- SQLAlchemy 2.0+（异步模式）+ Alembic（schema 的唯一出处，两种方言都走它）
- aiosqlite（SQLite 异步驱动）/ asyncpg（PostgreSQL 异步驱动，`[postgres]` 可选依赖）
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
│   │   ├── base.py        # MediaStorage 协议 + Capabilities + FoundFile + UnsupportedStorageError + S3_SCHEME
│   │   ├── local.py       # 本地与 NAS 共用的一份实现（NAS 就是挂载成本地路径）
│   │   ├── s3.py          # boto3 那份，只读，Capabilities.local_path=False
│   │   └── __init__.py    # storage_for_source(type) / storage_for_locator(路径) / fingerprint(路径)
│   ├── utils/             # 工具函数
│   │   ├── ffmpeg.py      # FFmpeg 工具
│   │   ├── file_scanner.py # 目录扫描与探针
│   │   ├── password.py    # bcrypt 哈希与校验（72 字节上限）
│   │   ├── video_search.py # 搜索串解析（源/标签/评分/时长/观看状态/丢失）
│   │   ├── file_fingerprint.py # 首尾 1MB 哈希，用来确认两份文件真是同一份
│   │   ├── time.py      # 把库里读出的时刻统一收成带 UTC 时区（SQLite 读回来永远不带 tz）
│   │   └── name_parser.py  # 文件名解析（片名、系列、季集、字幕组）
│   ├── scheduler/         # 定时任务
│   │   ├── scan_scheduler.py  # 源扫描（interval）+ 每日备份（cron）+ 启动补跑（一次性），共用这一个调度器
│   │   └── tasks.py       # 任务体：失败才写通知，成功不吭声
│   ├── database/          # 数据库配置
│   │   ├── base.py        # SQLAlchemy 基类
│   │   ├── migrations.py  # 驱动 Alembic 的那三只函数（upgrade_head / stamp_head / current_revision）
│   │   └── session.py     # 会话管理 + init_db 选路 + 老库的一次性补齐
│   ├── backup.py          # 每日 pg_dump：口令只走子进程环境、写完用 pg_restore -l 验一次、按文件名形状轮转
│   ├── cli.py             # 账号管理命令行（create-user / list-users / set-role / revoke-sessions）
│   ├── db_audit.py        # 换数据库前的只读审计（`uv run python -m src.db_audit`）
│   ├── db_transfer.py     # 搬家：一个事务内插完并对账，对不上就整体回滚（`uv run python -m src.db_transfer --from <老库> --to <新库>`）
│   ├── e2e_seed.py        # 真后端 e2e 的一次性现场：造媒体 → TRUNCATE → 建 owner + member → 走真扫描（`python -m src.e2e_seed`，由前端的 test:e2e:real 调用）
│   ├── config.py          # 配置管理
│   └── main.py            # 应用入口
├── alembic/               # schema 的出处（版本化迁移）
│   ├── env.py             # 连接串从 settings 取；应用启动时经 config.attributes 复用同一条连接
│   └── versions/          # 0001 是基线，此后一律新增修订
├── deploy/                # 运维脚本模板：进版本库，但里面永远不该有口令
│   └── pg-provision.example.sql  # 建角色和两个库，__REPLACE_ME__ 由用的人换掉
├── tests/                 # 测试文件
│   ├── conftest.py        # 共享 fixtures：db_session / anon_client / client（已登录）+ make_user / user_id / make_signed_in_client
│   ├── support.py         # ensure_source / ensure_video：PG 真执行外键，子行必须先有父行
│   ├── test_api/          # API 测试
│   ├── test_backup.py     # 备份用例：假子进程演 pg_dump/pg_restore，断言真实 argv/env、读不回即删、轮转只认自己的文件名
│   ├── test_scheduler_backup.py # 挂载与通知：重新挂载只留一条任务；失败写 backup_error，成功一条都不写
│   ├── test_db_audit.py   # 审计用例：造一个每类问题各一条的脏库，证明检查还活着
│   ├── test_db_transfer.py # 搬家用例：空库闸门、对账失败即回滚、时间戳跨方言不偏、报告与审计同一个数
│   ├── test_e2e_seed.py  # 播种闸门：库名不带 _test 就拒绝、整目录删除只允许发生在 backend/data/e2e 之下、媒体字节没被搬坏
│   ├── test_migrations.py # Alembic 三条启动路线：空库、老库、已版本化
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

模型写完之后补两句：在 `src/models/__init__.py` 里注册（`alembic/env.py` 靠 `import src.models` 才能看见全部表），然后给它配一个修订——`DATABASE_URL=... .venv/Scripts/alembic.exe revision --autogenerate -m add_example`。只改模型不写修订的话，新库和老库都会缺这张表，`tests/test_migrations.py` 会立刻变红。

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

角色同理，而且**新加接口要动的地方在中间件，不在路由上**：成员该能写的接口必须登记进 `MEMBER_WRITE_PATHS`，否则成员一律 403（忘了登记会立刻被 `test_roles.py` 的扫面用例和使用者发现，这正是想要的失败方向）；管理面（账号、系统配置）连读都限 owner 的话写进 `OWNER_ONLY_READ_PATHS`。只有确实需要拿到操作者 `User` 对象的路由（改角色、停用、重置密码）才额外挂 `Depends(require_owner)`。`/api/users` 那一组是**两道都拦**（每个端点都要 `actor` 来做"不能停用/降级自己"那几条护栏，所以它们本来就挂），而两道回的 403 连 `detail` 都一模一样——从外面完全分不出是哪一层拦的。这不叫冗余，契约是"成员读不到管理面"而不是"哪一层拦的"，但记着它：只摘一道，打真后端的 e2e 也不会红（这一单实测过一次全绿的变异）。

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

Schema 的出处只有一个：Alembic（`backend/alembic/`）。基线修订 `0001` 把模型声明的全部表、索引、约束一次建齐，**改表请写新修订，不要再往启动流程里加 SQL**：

```bash
# 连接串从 src/config.settings 取，alembic.ini 里不留 sqlalchemy.url
DATABASE_URL="postgresql+asyncpg://..." .venv/Scripts/alembic.exe revision --autogenerate -m "add_xxx"
```

`init_db()` 只认库、选路，三条路（权威描述在 `src/database/migrations.py` 的模块注释）：

- **空库**（新装的 PG，或新开的 SQLite 文件）：`upgrade_head`，表由基线建出来。
- **有表却没有 `alembic_version` 行**（Alembic 之前用 `create_all` 写出来的老库）：先 `apply_schema_fixes` 补齐成基线的形状，再 `stamp_head` 认领基线，从此和新建的库站在同一个版本上。
- **已有版本行**：`upgrade_head` 只补跑待执行的修订，平时是空操作。

`apply_schema_fixes`（`src/database/session.py`）因此只剩一次性用途：只在"老库认领基线"那一次启动里跑。它做的事是 `ADDED_COLUMNS` 补列、`DEDUPE_PLAY_HISTORY`/`DEDUPE_FAVORITES` 按 `(user_id, video_id)` 折叠老库的重复行、`DROP INDEX IF EXISTS ix_play_history_video_id` 换掉"每部视频全局一行"的旧唯一索引再建 `ux_play_history_user_video` 这一类 `(人, 影片)` 索引、`DEDUPE_WATCHLIST_NAMES` 把重名片单改写成 `X (2)`、`INHERIT_THEME_IN_PREFERENCES` 迁主题。顺序仍然要紧（先清洗再加唯一约束，反了建索引直接失败），语句仍然要求幂等（老库年龄未知，可能已经带了一部分）。**新功能别往这里加**——写修订。

约束和索引必须同时声明在模型上：SQLite 那条测试路的 `db_session` 是 `create_all` 建的全新库，只写修订它在测试里形同不存在。改完模型若 `tests/test_migrations.py::test_the_baseline_describes_the_models_exactly` 变红，就是加了列忘了配修订。

老库里 SQLite 的 `ADD COLUMN` 不能带非默认值的 `NOT NULL`，所以四个归属列在**老库**里是可空的，只有模型声明 `nullable=False`；新建的库（走基线）严格。

### PostgreSQL

`DATABASE_URL` 指哪就连哪，SQLite 与 PostgreSQL 两种方言都支持（PG 用 `postgresql+asyncpg://`）。建库模板 `backend/deploy/pg-provision.example.sql`（进版本库，口令位置是 `__REPLACE_ME__`，用的人自己换成真口令；换好之后的那份另存到 `data/` 里，别提交）：角色 `home_sites_app` 只有 LOGIN，两个库 `home_sites`（真库）与 `home_sites_test`（测试专用），`ENCODING=UTF8`、`LC_COLLATE`/`LC_CTYPE` 钉死 `C`。表结构不在模板里建，由 `0001` 基线在首次启动时建。

- **为什么是 C**：C 的排序就是 UTF-8 字节序，正好等于 SQLite 一直在用的 `BINARY`。换成 `en_US.UTF-8` 之类的 ICU 规则，切换当天整个片库的 `ORDER BY title` 会静默重排一遍。
- **测试库**：`settings.test_database_url`（写在 `backend/.env` 的 `TEST_DATABASE_URL`）指定；不设就回落到 SQLite 内存库（老路子）。`tests/conftest.py` 和搬家脚本的 PG 用例读的是同一个出处。PG 上每个用例靠 `TRUNCATE ... RESTART IDENTITY CASCADE` 隔离，`RESTART IDENTITY` 保证第一个自增 id 还是 1，用例里写死的 id 不用跟着改。schema 只在第一次用例前建一次，走的就是 `0001` 基线。也正因为那句 TRUNCATE，**同一时间只能有一套 pytest 打 `home_sites_test`**：两套并发会在 TRUNCATE 上互等，实测报出一大片 `DeadlockDetectedError`，看着像代码坏了。
- **报数前先问"这套跑在哪种方言上"，判据是环境而不是命令长什么样**（2026-10-05 踩过）：`tests/conftest.py` 读的是 `settings.test_database_url`，而 pydantic 的 `Settings` 会加载 `backend/.env`——本机那份就带着 `TEST_DATABASE_URL`，所以**裸 `pytest` 跑的是 PostgreSQL**，不是 SQLite。环境变量优先级高于 `.env`，要真·SQLite 得显式清空：`TEST_DATABASE_URL= pytest ...`（Windows 下走 bash 才这么好使）。两条能证实方言的痕迹：SQLite 那套会打出 `SKIPPED [1] tests/test_db_transfer.py:335: 需要真 PostgreSQL：设 TEST_DATABASE_URL 才跑`，PG 那套 0 skip；两边的通过数本来就差这一条，别把 717 和 "716 + 1 skipped" 读成两次一样的回归。写文档/提交信息时报方言前先看一眼有没有这条 skip。这条现在有机器兜着：`tests/conftest.py::pytest_report_header` 会在头部印「测试库: 真库 postgresql …」或「测试库: 内存 SQLite …」，**但 `-q` 会把它一起吞掉**，所以要看见它得用不带 `-q` 的跑法。
- **PG 真的执行外键**，SQLite 默认不执行（`PRAGMA foreign_keys` 是关的）。所以库里那些"没有父亲的子行"是历史遗留，PG 一律拒收；测试里也一样——用 `tests/support.py` 的 `ensure_source`/`ensure_video` 先造出真正的父行，别手工去凑 id。应用侧同样补了存在性校验（`FavoriteService.add_favorite` 对不存在的 `video_id` 抛 `ValueError` → 400，而不是 500）。
- **时间列一律写 `DateTime(timezone=True)`**：靠推断落下来的 naive `TIMESTAMP` 遇上 aware 的默认值，asyncpg 会直接 `DataError`（`settings.updated_at` 踩过）。读出来的时刻要做比较/减法的，先过 `as_utc()`。
- **时区的坑在写入侧，不在读取侧**：asyncpg 读 `timestamptz` 还给的是 UTC-aware 值，但送一个**不带 tzinfo** 的 `datetime` 进去时，它是按**数据库会话时区**理解的（本机 `SHOW timezone` = `Asia/Shanghai`，于是整体偏 8 小时）。SQLite 读回来却永远是 naive。所以凡是跨库读写时间（`db_transfer` 从老库捞行就是这里翻过车），先 `as_utc()` 补上时区再交给对面，别指望两边自己凑得齐。

账号相关的两张表：`users`（`username` 唯一、`password_hash`、`role` 带 `CheckConstraint`、`is_active` 用停用代替删除）与 `sessions`（主键是 `token_hash`，即 Cookie 里那枚 token 的 SHA-256）。存摘要而不是 token 本身，是为了让"库被读走"不等于"人人可冒用"；删行即失效，因此退出登录和踢下线不需要等 Cookie 自然过期。会话寿命不存字段，滑动续期时按 `expires_at - created_at` 反推，"记住我"就不必单独记一档。

`sessions` 没有自增 id，所以「我的设备」拿这枚摘要当行的地址用（`TOKEN_HASH_HEX` 是 `auth_service` 与中间件共用的一份形状）：路由用 `Path(pattern=TOKEN_HASH_HEX)` 卡参数，形状不对在路由层就是 422；中间件白名单里对应一条 `^/api/auth/sessions/{摘要}$`，成员也在 `MEMBER_WRITE_PATHS` 里放行这一条。`AuthService.revoke_session(user_id, token_hash)` 的匹配条件带上 `user_id`，所以别人的摘要只会得到 404 而不是把他踢下线；列表（`list_sessions`）按 `last_seen_at` 倒序取全部行、不做分页，一个家的浏览器就几台。响应回给浏览器的是摘要，不是 Cookie 值。

归属分两种。**属于人**的表带外键列：`favorites`/`play_history`/`watch_events` 有 `user_id`，`watchlists` 有 `owner_id`，唯一约束都是 `(人, 影片)` 或 `(owner_id, name)` 这种成对形式；`watchlist_items` 不加列，归属随它所在的清单。**全库广播**的内容只有一份行——`new_videos`（扫描日志）与 `notifications`（系统通知）——"读过没"另记在 `new_video_reads`/`notification_reads`（复合主键天然去重），响应里的 `read`/`is_new` 是 service 现查现挂的临时属性，不在模型列里。因此标记已读是 INSERT 而不是 UPDATE，`unread_count` 走 `~EXISTS`；删掉一条通知则是全家一起少一条，它没有归属列，所以这两个删除口不在 `MEMBER_WRITE_PATHS` 里——语义仍是家庭级，只是动手的换成 owner。删影片（或整个视频源）时 `delete_videos_cascade` 要连 `new_video_reads` 一起清——它挂在 `new_videos` 上，是这条链最深的孩子。

级联的孩子清单只有一处出处：`video_service.VIDEO_CHILD_TABLES`，外键指向 `videos.id` 的表一张不落（`play_history`/`favorites`/`new_videos`/`subtitles`/`watch_events`/`watchlist_items`/`video_tags`）。清单统一存 `Table` 而非 ORM 模型——关联表 `video_tags` 没有模型，列只能从 `.c` 上取，一份形状一个循环就能过完。`tests/test_services/test_video_service.py::test_the_explicit_cascade_list_is_every_child_of_videos` 拿 `Base.metadata` 现算出"所有引用 `videos.id` 的表"跟这张清单对账，新加一张却忘了登记时这条用例要红。

两个方言朝**相反方向**失效：PG 真的执行 `ON DELETE CASCADE`，SQLite 默认连外键都不查、于是悄悄留下孤儿行。只信 schema 声明，SQLite 上的测试永远发现不了漏表；只信手写清单，加了表却不登记，PG 那边当场 500。所以显式删除留着——为的是"由这一处决定删除带走什么"，两边同一个答案。代价是这张清单必须有人守，于是守卫做成用例，不靠记性。

删行之外还带走封面：`delete_videos_cascade` 把这些行的 `thumbnail_path` 返回给调用方，调用方**提交之后**再调 `delete_cover_files` 落盘删除（顺序反了的话，回滚的删除会留下"行还在、图没了"的影片）。封面只由 `scan_service` 生成在本地磁盘，S3 源在 `scan_service.py:256` 的 `local_path` 闸门上根本不会生成，所以清理走服务层的 `os.remove` 就够了，**没有**给 `MediaStorage` 加 `delete()`——那个 seam 是只读的，而且 UI 明说删记录不动磁盘上的视频，一个能删对象的口子比它要修的孤儿文件更危险。

通知只有一个写入方：`ScanService.scan_source` 发 `scan_complete`，`TranscodeService` 发 `transcode_complete`/`transcode_error`，`src/scheduler/tasks.py` 只在异常时补一条——扫描炸了是 `scan_error`，每日备份炸了是 `backup_error`。调度任务**不再**对同一个结果再播一条——曾经两处各写一份，六个源跑一轮就是 12 条。另一半规则是"变了才说"：`new_videos`、`subtitles_found`、`is_missing` 翻转（`missing_flips`）三个计数全为零就不写，因为一轮定时扫描的常态就是"什么都没变"，而扫过没扫过本来就记在 `video_sources.last_scan_at` 上，不需要通知当心跳。这条规则由 `tests/test_services/test_scan_service.py` 末尾四例钉住（一轮只播一次 / 零变化不播 / 文件消失要播 / 新增字幕要播）。后两例是防止静得太狠：文件消失和新加字幕都不体现在 `new_videos` 上，只看新增计数会把它们一起静掉。备份这边同理：成功每晚一次、说的都是同一句话，所以 `tests/test_scheduler_backup.py` 里"成功时 notifications 为空"是刻意保住的一条。

`settings` 与 `user_preferences` 是两张不同的表，别混：前者全家一份（扫描间隔、缩略图尺寸、默认转码格式），改一次所有人的播放都受影响，读写都限 owner；后者一人一份（`user_id` 主键 + `prefs` JSON），走 `/api/preferences`，成员改自己的主题不该碰着别人的屏幕。写入是按键合并（`save_prefs` 只覆盖 patch 里非空的键），响应字段由 API 层的 Pydantic 模型限定，所以加一项偏好只是加一个字段，不必改表。JSON 列的坑：原地 `row.prefs["k"]=v` SQLAlchemy 看不见，必须换一个新 dict 赋回去。

从 `settings.theme` 迁到 `user_preferences` 靠 `session.py` 里两条幂等 SQL：`INHERIT_THEME_IN_PREFERENCES` 把全家共用的那个老值发给每个还没有偏好行的账号（写入条件写成 `WHERE NOT EXISTS`，重复启动不会覆盖任何人改过的值），`DROP_SHARED_THEME_SETTING` 再删掉 `settings` 里的 `theme` 行。顺序不能反，反了所有人的选择就凭空变成默认浅色。

老库升级后的第一次 `create-user --role owner` 会顺手认领：`AuthService.claim_legacy_rows` 把 `user_id IS NULL` 的行交给这个账号，并把旧的 `new_videos.viewed` / `notifications.read` 一次性翻译成两张 `_reads` 表的记录（列已不存在就跳过）。这一步不做，升级后收藏与历史看起来就像被清空了。

**裸 SQL 的方言纪律**：`src/` 里手写的 SQL 一律按"PG 也能跑"来写，SQLite 独有的写法只允许留在 `src/db_audit.py`（它读的就是那个老的 SQLite 文件）。已清掉的几类和它们的替身：

- **NULL 安全的相等**：`a IS b` 是 SQLite 的写法，PG 那边叫 `IS NOT DISTINCT FROM`，没有两家通用的拼法，所以 `DEDUPE_PLAY_HISTORY`/`DEDUPE_FAVORITES` 摊开写成 `(a = b OR (a IS NULL AND b IS NULL))`。别图省事退回 `=`：归属列在老库里全是 NULL，用 `=` 这些行压根不进分组，去重会静默变成空操作（不是删错，是一个都不删）。
- **"有了就别插"**：`INSERT OR IGNORE`（SQLite）和 `ON CONFLICT DO NOTHING`（PG）也是两家不同。统一写成 `INSERT ... SELECT ... WHERE NOT EXISTS`，规则只有一份，还顺便说清了"哪一对键算重复"——`_inherit_read_state` 和 `INHERIT_THEME_IN_PREFERENCES` 都是这个形状。
- **表结构反射**：`PRAGMA table_info` 换成 `session.py` 的 `table_columns()`，它内部走 `inspect().get_columns()`，问每种方言问法不同、答案同形。踩过的坑：`run_sync` 两家递进来的东西不一样——连接那家给同步连接，会话那家给同步会话，把会话直接交给检查器会抛 `NoInspectionAvailable`，所以会话一侧走 `session_table_columns()`。
- **取日历日**：PG 没有 `date()` 函数，SQLite 的 `CAST(x AS DATE)` 又会把文本折成数字，两家没有中立形式，所以 `get_stats` 读原始事件行、在 Python 里归桶。这类"不报错、只静默给空结果"的差异比语法错误危险得多。
- **时间戳**：SQLite 存下去的是永远不带偏移的 UTC 文本，PG 的 `TIMESTAMP WITH TIME ZONE` 则按会话时区还一个带偏移的值。跨这两家做比较、分组或展示的，一律先过 `src/utils/time.py::as_utc()`。

`ilike(..., escape="\\")` 不用动：SQLAlchemy 2.0 在 SQLite 上编译成 `lower(x) LIKE lower(?) ESCAPE '\'`，在 PG 上编译成 `x ILIKE %(p)s ESCAPE '\'`，转义语义一致（实测两家各编译一遍，不是靠印象）。

换数据库之前先跑 `uv run python -m src.db_audit`（`src/db_audit.py`）。它只以 `mode=ro` 打开库文件，拿模型的 `Base.metadata` 和库里的实际 schema 对账，报九类问题：schema 漂移、库里没落实的外键约束、孤儿行、值类型不对、VARCHAR 超长、整数超出 PG 的 32 位 `integer`、NOT NULL 列里的 NULL、解析不了的日期与 JSON，并给每张表算一个方言无关的内容摘要（布尔→true/false、时间→UTC ISO、JSON→键排序，整表排序后哈希），搬完在目标库上再算一遍对得上才算搬全。之所以要有这么个脚本而不是"迁过去看报不报错"：SQLite 的类型亲和、不检查长度、不执行外键这三件事会让一批数据在 SQLite 里存得很好，到 PG 那边要么被拒要么被静改写；而只存在于库里的列（如认领后剩下的 `viewed`/`read`）会不会丢数据，只有数一遍非空值才知道。报告写到 `data/migration-audit-<日期>.md`（`data/` 不进版本库），stdout 只打 ASCII——控制台是 cp936。用例在 `tests/test_db_audit.py`，那里造了一个每类问题都有一条的脏库；真库跑出来的"一切正常"证明不了检查还活着。

搬家的顺序：审计（`db_audit`）→ 目标库建空（`deploy/pg-provision.example.sql`，schema 由 `0001` 基线建，别手工建表）→ `db_transfer --from <老库> --to <新库> --dry-run` 预演 → 去掉 `--dry-run` 正式搬。`--dry-run` 会一路跑到对账通过再整体回滚，新库不留一行，所以它和正式搬用的是同一条代码路，预演过了才算过。目标库必须已建表且为空，否则直接中止。搬的时候 `sessions` 整表跳过（旧 token 到了新库也不该还能用），`alembic_version` 也不搬；自增序列会推到当前最大值。方向是双向的：回滚到 SQLite 就把它当目标库再搬一次，`_reset_sequences` 两种方言都实现了。

真后端 e2e 的现场由 `src/e2e_seed.py` 一手准备，前端只负责把它串在 uvicorn 之前起（`frontend/CLAUDE.md` 的「打真后端的端到端测试」）。这里有两道闸门，理由和 `db_transfer` 一样——"连哪个库""清哪个目录"都只看一条环境变量，所以判据不能靠调用方自觉：库名必须以 `_test` 结尾才允许 TRUNCATE，非 PostgreSQL 方言直接拒收（这套用例要证明的就是和生产同一个方言）；媒体目录必须落在 `backend/data/e2e` 之下才允许整目录删除，否则报错发生在任何删除之前。**媒体夹具在这个进程里写，不放在前端的 Playwright 配置里写**：那个配置文件会被执行好几遍（主进程 + 每个 worker），写在配置里的副作用会在播种之后把 `data/e2e` 再清一次，留下的现象是库里的封面路径指向一个不存在的文件。扫描产物同样只核对不解释：1 部片子、1 条字幕、1 张封面，对不上就在起步时失败，而不是让每条用例各炸一次——封面这一项是为了 FFmpeg 不在 PATH 上时报"ffmpeg 抽不出封面"，而不是报一个看不出根因的图片加载失败。个人的那两行（一次观看进度 + 一条片单）也走**服务层本身**（`VideoService.record_play`/`update_progress`、`WatchlistService`），不手写 INSERT：`completed` 是 `is_completed()` 按 `duration` 的尾部容差算出来的，继续观看那条轨只读 `completed == False` 的行，自己抄一份判定规则的话规则一改夹具就悄悄失真，变成"库里说看完了、界面上还在轨里"这种两边都自洽的假象。账号建**两个**（owner + member，都走 `AuthService.create_user`）：member 那份不写任何个人数据，专门给角色网关那条用例撞真中间件用。这里的核对闸门查的是 `users.role` 这一列而不是行数——那条用例断言的全是 403，"member 那行压根没建成"和"账号真没权限"在现场长得一模一样。**播种不建任何标签**：标签那条用例把 `GET /api/tags` 整张表当成"只有我自己建的那两个"来断言（一个挂了片子、一个没挂，好让 `video_count` 各数各的），将来谁在播种里加标签就会把它弄红，加的若是带影片的标签更会——那个 0 才是它的判据。

每日备份在 `src/backup.py`，挂载在 `main.py` 的 lifespan 里，走的是应用自己的 APScheduler（`add_backup_job` 是每天那条 cron，`add_backup_catchup_job` 是启动时那条一次性检查，两者和扫描共用同一个调度器——两个调度器会让每个任务各跑一遍）。核心是 `run_backup()`：从 `settings.database_url` 拆出连接参数，起 `pg_dump -Fc --no-owner`，然后 `pg_restore -l` 把清单读回来，读不回的文件**当场删掉**。三个约束是这块的意义所在，改之前先看用例：

- **口令只进子进程的 `PGPASSWORD`，绝不进 argv**（命令行在进程列表里是明文），也不进日志——`PgTarget` 把口令排除在 `repr` 外，`BackupError` 的文案只带 pg_dump 自己的 stderr。用例是 `tests/test_backup.py::test_password_only_travels_in_the_child_environment`，它断言的是真实 argv/env，真跑一次 pg_dump 反而证不了这件事。
- **轮转按文件名形状认领**（`home_sites_<UTC 到秒>.dump`），不是按前缀：`data/pg-backups/` 里本来就躺着手工快照 `home_sites_post_account_cleanup_20261004_154215.dump`，按前缀认亲会在七天后把某次改动唯一的现场备份清掉。`BACKUP_KEEP_DAYS=0` 是"不轮转"，不是"全清"。
- **只在 PG 上挂载**，且成功不发通知（#85 定的"变了才说"），失败发一条 `backup_error`（标题分「每日」和「补跑」，看得出是哪一趟炸的）。"悄悄停掉的备份没人报"这一条已经补上，靠的是两个口子：`add_backup_job` 带 `misfire_grace_time=None`（默认 1 秒——到点时进程睡着/事件循环正忙，醒来就把这一轮**无声跳过**，一天就这么没了；实测把 next_run_time 挪到 5 小时前，默认配置直接 skip，带上这条才跑）；`add_backup_catchup_job` 是启动时的一次性检查，用 `backup.is_stale()` 问"最新一份还在 36 小时内吗"，不是就当场补 dump（进程压根没开着的那一轮不存在 misfire，只能靠这个）。36 小时故意比 24 小时长一截，否则昨夜好好的时候启动会误判成出事。

`pg_dump`/`pg_restore` 由 `pg_binary()` 找：`PG_BINDIR` 指目录（Windows 上服务端的 bin 默认不在 `PATH`，本机的值写在 `backend/.env`，不进版本库），留空按 `PATH` 找；两边都找不到就直接失败并把办法写进错误里——凌晨三点没人看见的"找不到 pg_dump"等于没有备份。

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
- **`videos.filepath` 的唯一约束是全库的，而扫描的"认识哪些文件"只按本源查**：`scan_service` 里那句 `existing` 过滤带 `source_id`，所以两个源指向同一个目录（或一个目录被挂两次）时，别源建过的路径会看着像新片。每文件外面那层 `begin_nested()`（SAVEPOINT）确实兜得住，整轮不会炸——代价是每个撞车文件每轮撞一次唯一约束、日志刷一整段回溯，而界面上永远看不到"这片子是别的源建的"。所以插之前先 `select(Video.source_id).where(Video.filepath == filepath)` 问一次归属，有主就跳过并计入 `foreign_paths`（`tests/test_services/test_scan_service.py`）
- **Windows 的 junction 会被走进**：`os.path.islink()` 对 junction 回 `False`，`os.walk` 因此把它当普通目录递归——源目录里放一个指向第二块盘的联接点，那块盘就一起进库，这正是跨盘片库想要的形状。权限闸门不在遍历，而在"只有 owner 能加视频源"（他能加的本来就包括整块盘），所以**别在 `scan_directory` 里加 realpath 判定**：那会把跨盘的库扫成半套。这条形状由 `tests/test_utils/test_file_scanner.py::test_a_junction_is_walked_into` 用真 junction 钉住（非 Windows 自动跳过，POSIX 软链的行为相反）
- **够不着不等于空**：只有 `reachable()` 为真才允许把记录标成丢失。凭证写错、挂载盘掉线都走 `reachable() == False`，此时列表当空处理但一行都不判定
- **能力问 `capabilities`，别嗅探 `s3://`**：`local_path` 是真正承重的位——FFmpeg 得在文件里 seek，对象存储给不了，于是缩略图、转码、内嵌字幕一起关闭；`sidecar_subtitles` 管外挂字幕那条路。拿不到本地路径的路由返回中文 400，不是 500
- **S3 客户端按配置缓存，不按进程缓存**：用户改完 `.env` 之后，进程里那台旧密钥签的客户端还在偷偷用

### 封面落盘

- **文件名由 locator 派生并带一段摘要**：`{原文件名}-{sha256(locator)[:12]}.jpg`，落在 `THUMBNAIL_PATH/{source_id}/` 下（`scan_service._thumbnail_target`）。只按 basename 命名的话，同一视频源的不同子目录里的同名视频（`a/01.mp4` 与 `b/01.mp4`）会写到同一个 `01.jpg`，后扫的那张悄悄盖掉前一张，两行都显示"有封面"，看不出坏过
- **`THUMBNAIL_PATH` 的相对值在配置层就按 `backend/` 展开成绝对路径**：库里 `videos.thumbnail_path` 存的是算出来的完整字符串，读取端（`stream.py` 的 `os.path.isfile`）按进程工作目录解析它，相对值会让"从仓库根目录启动"变成全库无封面。同类的 `DATABASE_URL` 与 `.env` 本身仍是 cwd 相对，**从 `backend/` 启动服务这个约定没取消**
- **设置页的「缩略图宽度 / 高度」没有接**：`generate_thumbnail` 里的 `scale=320:-1` 和 `-ss 00:00:01` 是硬编码，那两个值只是存进 `settings` 表、无人读取。要真做成可配得改函数签名并把设置读进来，别以为改表单就行
- **封面跟着记录走**：删影片或删整个视频源时，`delete_videos_cascade` 把被删行的 `thumbnail_path` 交给调用方，提交成功后由 `delete_cover_files` 从磁盘移除；漏了这一步就是永久孤儿文件（删行不碰磁盘，重扫又会按同一个派生名新建一张，盘上只会越攒越多）。视频本体**永远不删**——那是用户的片，不是应用生成的。细节见「数据模型」一节

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

- **失败通知不能写在刚失败的那个会话上**：`scheduler/tasks.py` 的 `except` 里原本直接拿扫描用的会话建 `scan_error`，而扫描要是死在 `flush()` 上（撞唯一约束就是这个形状），会话已经带着 `PendingRollback` 状态进了这个分支，紧接着那条 INSERT 只会再抛一次，被下一层 `except Exception: logger.exception(...)` 无声咽掉。真机上的现场因此是「0 条 `scan_error` 配上一整日志的 `IntegrityError` 回溯」——承诺"失败一定发通知"的路径，恰好在最需要它的失败形状上是死的。写通知前先 `await session.rollback()`（用例：`tests/test_scheduler_scan.py`）
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

SQLite 不存时区：写进去的是 UTC，读回来的 `datetime` **不带 tzinfo**，和 `datetime.now(timezone.utc)` 直接比大小会抛 `can't compare offset-naive and offset-aware datetimes`。凡要拿库里读出的时间做比较或运算，先过一道 `as_utc()`（`src/utils/time.py`：没带 tz 就当作 UTC，带了就换算到 UTC），`auth_service` 与 `history_service` 用的都是这一份。

换成 PG 后这条规则不能丢：`TIMESTAMP WITH TIME ZONE` 还回来的是**带偏移**的值，而且偏移按数据库会话时区给，不一定正好是 UTC。所以 naive/aware 的分岔要一直留着，别改成"直接信任库里给的 tzinfo"。

同理，测试里改过某行的时间后要看真实结果，用 `await db_session.refresh(row)` 重新读；`expire_all()` 之后靠关系属性懒加载会抛 `MissingGreenlet`。

**关系只要被响应模型读到，就必须写进那一条查询**（2026-10-05 实测）。`VideoResponse` 带 `tags`，而 `get_videos_by_tag` 是经多对多的 `Tag.videos` 走到影片的，那批影片的 `tags` 没有被关系上的 `lazy="selectin"` 带上，序列化时（pydantic 是同步的）一碰就是 greenlet 之外的 IO → 端点 500。写法是把它链到底：`selectinload(Tag.videos).selectinload(Video.tags)`。别指望默认加载兜住：同样用 `expire_all()` 造冷会话，经**多对一**（`PlayHistory.video` / `Favorite.video` / `WatchlistItem.video`）的五个读接口都能带回标签，只有经多对多集合那一头会漏（`tests/test_api/test_video_reads_with_a_cold_session.py` 钉的就是这个差别）。我没从文档里推出一条"什么时候默认加载会生效"的一般规则，所以按戒律走，别去赌那个形状。

### 4. 类型检查剩下的两类边界

`mypy src` 现在这 34 项不是"注解还没写完"，是两处刻意保留的形状。别指望总数降到 0，也别为了凑数加 `cast`：

- **端点返回 ORM 对象，而返回注解就是 response 模型**（27 项，全在 `src/api/`）。FastAPI 在序列化时用 `from_attributes` 把 `Video` 变成 `VideoResponse`，静态检查看不到这一步。真要清零只有两条路：每个端点显式 `VideoResponse.model_validate(...)`，或者把注解摘掉改用 `response_model=`——两种都会改到 API 层一贯的写法，属于设计决定，得单独议
- **service 层往模型实例上挂瞬态属性**（`Video.progress`、`Video.is_new`、`Notification.read`，7 项），为的是响应模型顺手读到"这一部你看到哪了"。SQLAlchemy 2.0.51 不认非 `Mapped` 的类级注解（直接 `MappedAnnotationError`），而这个版本还没有 `Unmapped`，所以在模型侧声明这条路走不通；根治是让这类数据别寄存在模型上

写 SQL 表达式时记一条：`Video.title` 这类 ORM 属性在类型上是 `InstrumentedAttribute[str | None]`，它既不是 `ColumnElement[str]` 也不是 `KeyedColumnElement[str]` 的子类型。要接住它并用 `.ilike`，参数标成裸 `ColumnOperators`（见 `video_service._like`）。

### 5. 覆盖率：闸门是 80，但只在带 `--cov` 的全量跑上生效

`[tool.coverage.report] fail_under = 80`（2026-10-04 挂上，当时实测 86%——那是下面那条未修正的读数）。没写成 pytest 的 `addopts`，是因为那样"只跑一个文件"也会去比总量——一个文件的覆盖率天然不到 80，报回来的红和"测试坏了"长得一模一样，纯属误导。要量就明说：`pytest -q --cov=src`。

**读报告前先知道这一条：coverage 默认会把异步代码少算。**SQLAlchemy 的 async 引擎每个 `await` 都要过一次 greenlet 切换，而 coverage 不认 greenlet 时行追踪器在切换后丢失——于是**函数体里那些落在 `await` 之后的行会被报成"没执行"**，哪怕用例就是从那几行走出来的。`pyproject.toml` 里的 `[tool.coverage.run] concurrency = ["greenlet", "thread"]`（2026-10-05 挂上）就是为这一条；两边实测同一套全量：未配置 TOTAL **86%**（589 miss），配上 **91.49%**（364 miss），两次都是 698 passed + 1 skipped，所以少算的确实是执行过的行。同一套标签用例在两种配置下分别报 `api/tags.py` 76% / **100%**、`tag_service.py` 37% / **97%**。

所以看覆盖率只有两条戒律：

- 别拿单文件百分比当"这里没测"的证据去补用例，先看 `tests/` 里到底有没有走过那条路径
- 别为了让报告好看抬高 `fail_under`：80 在未修正的读数上就还有余量，修正后余量更大，动它只会把历史数字弄丢

下面那份薄位置清单是**修正后**重测的（SQLite 全量 717 passed + 1 skipped，TOTAL 92%，2026-10-05 复量；清单里个别条目另标了自己更晚的重量时间）：

- `utils/ffmpeg.py` **23%**——转码要真 FFmpeg 和真片子才跑得动，桩不出真形状没有意义
- `scheduler/tasks.py` **62%**（2026-10-05 补上启动补跑之后重量的，此前 57%）——缺的还是 `scan_source_task` / `scan_all_active_task` 两个包装的函数体（自己开会话、把异常变成一条 `scan_error` 通知）；测试和被调的定时任务都是直接走 `ScanService`，只有两条备份任务（每晚 + 启动补跑）是端到端测过的
- `src/e2e_seed.py` **55%**（2026-10-05 加第二个账号之后重量的，PostgreSQL 全量 718 passed，此前 58%）——一次性库的播种与重置，主要活在打真后端的 e2e 那个进程里，pytest 进程只 import 和调其中一部分（`seed()` 整段 177–280 行没人走，它要真 PG、真媒体目录和真 FFmpeg；`seed_user_stats` 从 2026-10-05 起有一条用例直接过它）
- `api/settings.py` **71%**——批量改配置和单键读写两条端点没人调（界面走的是另一套偏好接口）
- `api/stream.py` **72%**——整文件直读那两个分支和"封面文件不在"的兜底；`Range` 分段由打真后端的 e2e 覆盖，不在这份读数里

标签那套在 2026-10-05 补上了接口层用例（`tests/test_api/test_tags.py`，八个端点各过一遍，顺带把"重名建标签回 500"改成 409），`api/tags.py` 100%、`tag_service.py` 97%，不再是空白。这几处都是有意的取舍，不是漏了；别为了让总数好看去造只断言"没抛异常"的用例。

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

# 静态检查（在 backend/ 目录下跑，配置在 pyproject.toml）
.venv/Scripts/ruff.exe check .    # 2026-10-04 起为 0 项，红了就说明是新代码带来的
.venv/Scripts/mypy.exe src        # 2026-10-04 从 95 降到 34，看单文件增量而不是总数

# 覆盖率（闸门在 [tool.coverage.report] 的 fail_under=80，只有带 --cov 才生效）
TEST_DATABASE_URL= .venv/Scripts/pytest.exe -q --cov=src   # 全量跑，2026-10-05 实测 91%（greenlet 修正后的读数）
```
