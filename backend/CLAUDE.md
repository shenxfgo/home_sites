# CLAUDE.md - 后端开发规范

## 技术栈

- Python 3.11+
- FastAPI 0.109+（`pyproject` 里只是下限，实际锁在 `uv.lock`：0.140.0，见「依赖管理 → 版本到底锁在哪」）
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
│   ├── export_openapi.py  # 生成/校验 `backend/openapi.json`（`python -m src.export_openapi [--check]`，离线）
│   ├── config.py          # 配置管理
│   └── main.py            # 应用入口
├── alembic/               # schema 的出处（版本化迁移）
│   ├── env.py             # 连接串从 settings 取；应用启动时经 config.attributes 复用同一条连接
│   └── versions/          # 0001 是基线，此后一律新增修订
├── deploy/                # 运维脚本模板：进版本库，但里面永远不该有口令
│   └── pg-provision.example.sql  # 建角色和两个库，__REPLACE_ME__ 由用的人换掉
├── openapi.json           # 提交在仓库里的路由表快照（由 src.export_openapi 生成，前端契约用例直接读这个文件）
├── tests/                 # 测试文件
│   ├── conftest.py        # 共享 fixtures：db_session / anon_client / client（已登录）+ make_user / user_id / make_signed_in_client
│   ├── support.py         # ensure_source / ensure_video：两种方言都执行外键，子行必须先有父行
│   ├── test_api/          # API 测试
│   ├── test_backup.py     # 备份用例：假子进程演 pg_dump/pg_restore，断言真实 argv/env、读不回即删、轮转只认自己的文件名
│   ├── test_scheduler_auto_scan_switch.py # 设置页那个总开关：关了整轮不扫 / 没写过算开 / 手工扫描不受它管
│   ├── test_scheduler_backup.py # 挂载与通知：重新挂载只留一条任务；失败写 backup_error，成功一条都不写
│   ├── test_scheduler_source_lifecycle.py # 片源的增删改与调度任务同步：挂上/拆掉/换间隔各钉一次，另外 /api/scheduler 那四个端点第一次被请求
│   ├── test_db_audit.py   # 审计用例：造一个每类问题各一条的脏库，证明检查还活着
│   ├── test_db_transfer.py # 搬家用例：空库闸门、对账失败即回滚、时间戳跨方言不偏、报告与审计同一个数
│   ├── test_e2e_seed.py  # 播种闸门：库名不带 _test 就拒绝、整目录删除只允许发生在 backend/data/e2e 之下（封面同规则）、媒体字节没被搬坏、清库那条语句的形状、命令行出口的退码与 stdout
│   ├── test_database_boot_routes.py # 真的调用 `init_db()` 和 `get_session()`：三条启动路线各跑一次、会话收尾还不还连接看池子
│   ├── test_migrations.py # Alembic 的零件：认库、补齐、stamp、upgrade（都在同步连接上，不经过 `init_db`）
│   ├── test_openapi_snapshot.py # 快照钉子：`backend/openapi.json` 和 `app.openapi()` 对不上就红（改了接口忘重跑导出就是这个）
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
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from src.database.base import Base
from src.database.types import UTCDateTime


class Example(Base):
    """示例模型。"""

    __tablename__ = "examples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc)
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

**注册完的最后一步是重跑 `uv run python -m src.export_openapi`**：路由表以 `backend/openapi.json` 的形式提交在仓库里，前端 14 份请求模块的 URL 是对着这份文件核对的（含那 4 条只返回字符串、不经过 axios 的浏览器地址构造器）。忘了重跑不会让后端用例失败在"接口不存在"上，而是让快照钉子和前端契约用例一起红在快照上——红是对的，只是原因在你的工作目录里，不在调用方。

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

这三条路由从前只有零件级的用例（`test_migrations.py` 在同步连接上分别试 `_is_unversioned_legacy` / `stamp_head` / `upgrade_head`），`init_db()` 本体一次也没被调用过——启动那一份用例（`test_app_boot_lifespan.py`）和 `test_cli.py` 都把它换成了只登记名字的替身。现在由 `tests/test_database_boot_routes.py`（8 条）真跑：每台引擎换成 `tmp_path` 上一个独立的 SQLite 文件库，因为 `init_db` 和 `get_session` 读的都是**模块级**的 `engine` / `async_session_maker`，留着默认值就是去动开发库。改这一段前值得知道三件实测出来的性质：

- **`async with engine.begin()` 那句不是装饰**（W6：换成 `engine.connect()` → 4 条全红）：迁移的 DDL 在这条连接的事务里，出块不提交就整体回滚，库里什么也没留下，而**不报任何错**——`upgrade_head` 自己跑得挺欢，红的是下一个读的人。
- **认库认错方向只有一头能红**：强制走 upgrade（W2）、漏掉 `stamp_head`（W3）、漏掉 `apply_schema_fixes`（W4）各红 1 条，红法都不同——W2 是 `OperationalError: table tags already exists`（老库里 upgrade 会对已存在的表再建一次，这一条不需要替身就能钉住分支），W3 是没有版本行，W4 是表只建了一半。反过来，**永远走补齐那一路（W1）全绿**：`create_all` 建出的表和基线一模一样，`stamp` 登记完也查不出来。差别只在"没跑修订"这件事上，而 `0001`/`0002` 两条目前都是纯 DDL，`create_all` 恰好能演出同样的结果——将来出现**带数据的修订**时这一格就是盲区，别以为补齐那条路是安全的替代品。同理，`stamp` 和补齐谁先谁后也钉不住（W5 全绿）；上面那句"顺序要紧"说的是 `apply_schema_fixes` **内部**的清洗与建索引，不是这两步之间。
- **会话收尾要拆成两个变量看**：`async with` 和 `finally: await session.close()` 各自都是**等价变异**（W7、W8 分别摘掉任一半都全绿，因为 `AsyncSession.__aexit__` 本来就会 `close()`），只有两个一起没（W9 → 红 2 条）连接才留在池里。还连接这件事**不能靠"会话还能不能用"来断**——实测一个已关闭的 `AsyncSession` 再执行语句不报错，也没有 `.closed` / `.is_closed` 属性可问，所以那两条用例读的是 `engine.pool.checkedout()`（用前 0、语句后 1、收尾后 0），异常那一路用 `generator.athrow()` 演。另外 `finally` 里补一句自动 commit 会红第 8 条（W10）——那条用例钉的是"没提交的写不会跟着会话出去"，钉不住"事务被回滚"（W9 下它照样绿：闲置的连接不会把未提交的写送给另一个读者）。

`apply_schema_fixes`（`src/database/session.py`）因此只剩一次性用途：只在"老库认领基线"那一次启动里跑。它做的事是 `ADDED_COLUMNS` 补列、`DEDUPE_PLAY_HISTORY`/`DEDUPE_FAVORITES` 按 `(user_id, video_id)` 折叠老库的重复行、`DROP INDEX IF EXISTS ix_play_history_video_id` 换掉"每部视频全局一行"的旧唯一索引再建 `ux_play_history_user_video` 这一类 `(人, 影片)` 索引、`DEDUPE_WATCHLIST_NAMES` 把重名片单改写成 `X (2)`、`INHERIT_THEME_IN_PREFERENCES` 迁主题。顺序仍然要紧（先清洗再加唯一约束，反了建索引直接失败），语句仍然要求幂等（老库年龄未知，可能已经带了一部分）。**新功能别往这里加**——写修订。

约束和索引必须同时声明在模型上：SQLite 那条测试路的 `db_session` 是 `create_all` 建的全新库，只写修订它在测试里形同不存在。改完模型若 `tests/test_migrations.py::test_the_baseline_describes_the_models_exactly` 变红，就是加了列忘了配修订。

老库里 SQLite 的 `ADD COLUMN` 不能带非默认值的 `NOT NULL`，所以四个归属列在**老库**里是可空的，只有模型声明 `nullable=False`；新建的库（走基线）严格。

### PostgreSQL

`DATABASE_URL` 指哪就连哪，SQLite 与 PostgreSQL 两种方言都支持（PG 用 `postgresql+asyncpg://`），但**代码里声明的默认值是 PostgreSQL**（`Settings.database_url`，用例：`tests/test_config.py::test_load_default_settings`）。默认值不带口令，所以一份没有 `.env` 的检出会在第一次启动就连不上——这是要的：旧的 SQLite 默认值会安静地建出一个空文件、空库，看起来像装好了。SQLite 这条路还在，只是必须显式指。驱动 `asyncpg` 因此在核心依赖里，`--extra postgres` 这个 extra 已经删掉了。建库模板 `backend/deploy/pg-provision.example.sql`（进版本库，口令位置是 `__REPLACE_ME__`，用的人自己换成真口令；换好之后的那份另存到 `data/` 里，别提交）：角色 `home_sites_app` 只有 LOGIN，两个库 `home_sites`（真库）与 `home_sites_test`（测试专用），`ENCODING=UTF8`、`LC_COLLATE`/`LC_CTYPE` 钉死 `C`。表结构不在模板里建，由 `0001` 基线在首次启动时建。

- **为什么是 C**：C 的排序就是 UTF-8 字节序，正好等于 SQLite 一直在用的 `BINARY`。换成 `en_US.UTF-8` 之类的 ICU 规则，切换当天整个片库的 `ORDER BY title` 会静默重排一遍。
- **测试库**：`settings.test_database_url`（写在 `backend/.env` 的 `TEST_DATABASE_URL`）指定；不设就回落到 SQLite 内存库（老路子）。`tests/conftest.py` 和搬家脚本的 PG 用例读的是同一个出处。PG 上每个用例靠 `TRUNCATE ... RESTART IDENTITY CASCADE` 隔离，`RESTART IDENTITY` 保证第一个自增 id 还是 1，用例里写死的 id 不用跟着改。schema 只在第一次用例前建一次，走的就是 `0001` 基线。也正因为那句 TRUNCATE，**同一时间只能有一套 pytest 打 `home_sites_test`**：两套并发会在 TRUNCATE 上互等，实测报出一大片 `DeadlockDetectedError`，看着像代码坏了。
- **报数前先问"这套跑在哪种方言上"，判据是环境而不是命令长什么样**（2026-10-05 踩过）：`tests/conftest.py` 读的是 `settings.test_database_url`，而 pydantic 的 `Settings` 会加载 `backend/.env`——本机那份就带着 `TEST_DATABASE_URL`，所以**裸 `pytest` 跑的是 PostgreSQL**，不是 SQLite。环境变量优先级高于 `.env`，要真·SQLite 得显式清空：`TEST_DATABASE_URL= pytest ...`（Windows 下走 bash 才这么好使）。两条能证实方言的痕迹：SQLite 那套会打出 `SKIPPED [1] tests/test_db_transfer.py:335: 需要真 PostgreSQL：设 TEST_DATABASE_URL 才跑`，PG 那套 0 skip；两边的通过数本来就差这一条，别把 717 和 "716 + 1 skipped" 读成两次一样的回归。写文档/提交信息时报方言前先看一眼有没有这条 skip。这条现在有机器兜着：`tests/conftest.py::pytest_report_header` 会在头部印「测试库: 真库 postgresql …」或「测试库: 内存 SQLite …」，**但 `-q` 会把它一起吞掉**，所以要看见它得用不带 `-q` 的跑法。
- **两种方言现在都真的执行外键**：PG 出厂就强制；SQLite 每个连接的 `PRAGMA foreign_keys` 出厂是**关**的（官网写明这是为老应用留的向后兼容），所以 `session.py` 在引擎上挂了一个连接事件补那一句（`enforce_sqlite_foreign_keys`，用例 `tests/test_sqlite_foreign_keys.py`）。挂的位置有讲究：要在**第一次连接之前**挂，内存 SQLite 用 StaticPool、同一条连接一路用到底，晚挂的事件对它不生效——`tests/conftest.py` 因此在两个分支里各挂一次。库里那些"没有父亲的子行"是这段开关之前的历史遗留（`db_audit` 报 `orphan_row` 的那一类），新写的行两边都进不去了；测试里也一样——用 `tests/support.py` 的 `ensure_source`/`ensure_video` 先造出真正的父行，别手工去凑 id。应用侧同样补了存在性校验（`FavoriteService.add_favorite` 对不存在的 `video_id` 抛 `ValueError` → 400，而不是 500）。**挂了这个开关的只有两个引擎**：启动那个模块级 `engine`，和 `tests/conftest.py` 里用例用的那个。`db_audit`（只读，读的是脏库）、`db_transfer`（老库里可能真有孤儿行，强制了会把搬迁中止）和 `test_migrations.py` 那些自建的引擎都还是 SQLite 的出厂默认——不是漏了，是那几个地方的目的就是要碰不干净的数据。
- **时间列一律写 `UTCDateTime()`（`src/database/types.py`），不要写裸的 `DateTime(timezone=True)`**：它的 `impl` 就是那句 `DateTime(timezone=True)`，所以两种方言编译出来的建表语句逐字节不变、不需要迁移（`tests/test_utc_datetime_columns.py` 第三条钉的正是这一点，全仓 21 个时间列一条也不能落在外面）。靠推断落下来的 naive `TIMESTAMP` 遇上 aware 的默认值，asyncpg 会直接 `DataError`（`settings.updated_at` 踩过）。它另外补的那半件事是**读回来带 `tzinfo=UTC`**，见下面「时区处理」。
- **凡是拿 `col.type` 分流的代码，判时间列必须走 `is_datetime_column()`**：`TypeDecorator` 的实例**不是** `DateTime` 的实例（实测），所以 `isinstance(col.type, DateTime)` 在换成 `UTCDateTime` 之后会静默地永远为假。`src/db_audit.py` 有三处这样的分流（`:98` 的类型违例、`canonical_value` 的时间归一、`bad_datetime`），改这三处是这一单真正的连带代价——不跟着改的话审计脚本对时间列那一类检查一声不响地全过。
- **时区的坑在写入侧，不在读取侧**：asyncpg 读 `timestamptz` 还给的是 UTC-aware 值，但送一个**不带 tzinfo** 的 `datetime` 进去时，它是按**数据库会话时区**理解的（本机 `SHOW timezone` = `Asia/Shanghai`，于是整体偏 8 小时）。SQLite 读回来却永远是 naive。所以凡是跨库读写时间（`db_transfer` 从老库捞行就是这里翻过车），先 `as_utc()` 补上时区再交给对面，别指望两边自己凑得齐。

账号相关的两张表：`users`（`username` 唯一、`password_hash`、`role` 带 `CheckConstraint`、`is_active` 用停用代替删除）与 `sessions`（主键是 `token_hash`，即 Cookie 里那枚 token 的 SHA-256）。存摘要而不是 token 本身，是为了让"库被读走"不等于"人人可冒用"；删行即失效，因此退出登录和踢下线不需要等 Cookie 自然过期。会话寿命不存字段，滑动续期时按 `expires_at - created_at` 反推，"记住我"就不必单独记一档。

`sessions` 没有自增 id，所以「我的设备」拿这枚摘要当行的地址用（`TOKEN_HASH_HEX` 是 `auth_service` 与中间件共用的一份形状）：路由用 `Path(pattern=TOKEN_HASH_HEX)` 卡参数，形状不对在路由层就是 422；中间件白名单里对应一条 `^/api/auth/sessions/{摘要}$`，成员也在 `MEMBER_WRITE_PATHS` 里放行这一条。`AuthService.revoke_session(user_id, token_hash)` 的匹配条件带上 `user_id`，所以别人的摘要只会得到 404 而不是把他踢下线；列表（`list_sessions`）按 `last_seen_at` 倒序取全部行、不做分页，一个家的浏览器就几台；它列的是**活的**会话，所以先走一遍 `purge_expired_sessions(user_id)`——过期的那一行 `resolve_session` 早就拒绝了，可它要等**它自己的** Cookie 再被拿回来一次才会被删，而"我的设备"和用户管理那一格读的是列表，永远等不到那一次（`/api/users` 的 `signed_in_devices` 因此同样先清再数，两处共用这一个方法）。响应回给浏览器的是摘要，不是 Cookie 值。

归属分两种。**属于人**的表带外键列：`favorites`/`play_history`/`watch_events` 有 `user_id`，`watchlists` 有 `owner_id`，唯一约束都是 `(人, 影片)` 或 `(owner_id, name)` 这种成对形式；`watchlist_items` 不加列，归属随它所在的清单。**全库广播**的内容只有一份行——`new_videos`（扫描日志）与 `notifications`（系统通知）——"读过没"另记在 `new_video_reads`/`notification_reads`（复合主键天然去重），响应里的 `read`/`is_new` 是 service 现查现挂的临时属性，不在模型列里。因此标记已读是 INSERT 而不是 UPDATE，`unread_count` 走 `~EXISTS`；删掉一条通知则是全家一起少一条，它没有归属列，所以这两个删除口不在 `MEMBER_WRITE_PATHS` 里——语义仍是家庭级，只是动手的换成 owner。删影片（或整个视频源）时 `delete_videos_cascade` 要连 `new_video_reads` 一起清——它挂在 `new_videos` 上，是这条链最深的孩子。

级联的孩子清单只有一处出处：`video_service.VIDEO_CHILD_TABLES`，外键指向 `videos.id` 的表一张不落（`play_history`/`favorites`/`new_videos`/`subtitles`/`watch_events`/`watchlist_items`/`video_tags`/`transcode_outputs`）。清单统一存 `Table` 而非 ORM 模型——关联表 `video_tags` 没有模型，列只能从 `.c` 上取，一份形状一个循环就能过完。`tests/test_services/test_video_service.py::test_the_explicit_cascade_list_is_every_child_of_videos` 拿 `Base.metadata` 现算出"所有引用 `videos.id` 的表"跟这张清单对账，新加一张却忘了登记时这条用例要红。

这条清单存在的理由原本有一半在方言上：PG 真的执行 `ON DELETE CASCADE`，而 SQLite 在 #161 之前连外键都不查、批量删父表就悄悄留下孤儿行——只信 schema 声明，SQLite 上的测试永远发现不了漏表。那一半现在被连接事件补平了（见上面「两种方言现在都真的执行外键」），**但显式删除仍然留着**，理由换成两条更结实的：一是"由这一处决定删除带走什么"，两边同一个答案，不用去查每种方言在什么开关下才会级联；二是删行之外还要带走封面文件，schema 永远不知道哪张表存着路径。代价没变：这张清单必须有人守，于是守卫做成用例，不靠记性。

删行之外还带走应用自己生成的文件（封面 + #185 起的转码产物）：`delete_videos_cascade` 把这些行的 `thumbnail_path` 和 `transcode_outputs.output_path` 返回给调用方，调用方**提交之后**再调 `delete_generated_files` 落盘删除（顺序反了的话，回滚的删除会留下"行还在、图没了"的影片）。封面只由 `scan_service` 生成在本地磁盘，S3 源在 `scan_service.py:281` 的 `local_path` 闸门上根本不会生成，所以清理走服务层的 `os.remove` 就够了，**没有**给 `MediaStorage` 加 `delete()`——那个 seam 是只读的，而且 UI 明说删记录不动磁盘上的视频，一个能删对象的口子比它要修的孤儿文件更危险。产物那一头比封面多一道闸门：`_owned_products` 只认落在 `settings.transcode_output_dir` 里面的路径（`realpath` + `normcase` 比前缀），目录外的一律留着——那一列是库里的一串字符串，#154 之前写的就是源旁边，而那里是片库本身。这一步现在是三层签字：服务层那几条把路径喂成临时目录里的字符串，验的是「调用到了」；两个调用方**各**钉一条顺序（`VideoService.delete_video` 与 `SourceService.delete` 各自写一遍"提交在前、落盘在后"，级联只报名字，所以这一句钉两次不是一次）；`frontend/e2e/real/video-delete.real.spec.ts` 那一条从界面上点「删除」，核对真 `thumbnails/` 目录里少掉的正是这一张、别人的那几张一个字节没动（#118）。

通知只有一个写入方：`ScanService.scan_source` 发 `scan_complete`，`TranscodeService` 发 `transcode_complete`/`transcode_error`，`src/scheduler/tasks.py` 只在异常时补一条——扫描炸了是 `scan_error`，每日备份炸了是 `backup_error`。调度任务**不再**对同一个结果再播一条——曾经两处各写一份，六个源跑一轮就是 12 条。另一半规则是"变了才说"：`new_videos`、`subtitles_found`、`is_missing` 的翻转（`files_lost + files_found_again`，落进通知 `data` 时合成一个 `missing_changed`）、`subtitles_gone` 四项全为零就不写，因为一轮定时扫描的常态就是"什么都没变"，而扫过没扫过本来就记在 `video_sources.last_scan_at` 上，不需要通知当心跳。这条规则由 `tests/test_services/test_scan_service.py` 末尾六例钉住（一轮只播一次 / 零变化不播 / 文件消失要播 / 新增字幕要播 / 文件回来得说"回来" / 字幕文件没了要播且下一轮安静）。后四例是防止静得太狠：文件消失、新加字幕、挂载回来和字幕文件被移走都不体现在 `new_videos` 上，只看新增计数会把它们一起静掉。另一半规则是**方向**：丢掉与找回各说一句话（「N 个文件已找不到」/「N 个文件已找回」），只数"翻了几行"会把好消息写成坏消息——那正是界面上出现过的一句话，`missing_changed` 仍然是一个数，只是文案看方向。备份这边同理：成功每晚一次、说的都是同一句话，所以 `tests/test_scheduler_backup.py` 里"成功时 notifications 为空"是刻意保住的一条。

字幕那一半是**核对**，形状和影片行的 `is_missing` 不一样，而且是有意的：影片行留着改标记，`Subtitle` 那一行除了"这条轨存在"什么都不表达，所以文件不在了就删行（`SubtitleService.prune_missing`）。问的是**「文件还在吗」**（`os.path.isfile(row.filepath)`）而不是**「这轮扫描认得它吗」**——后者看着更"对称"，实际会每次扫描抹掉所有手工挂的轨道，因为 `find_subtitle_files` 只认由影片主干名推出来的那几种后缀（`movie.zh.srt`），`SubtitleService.add` 收下的名字可以完全不在那个模式里（`tests/test_services/test_scan_service.py::test_scan_keeps_hand_registered_subtitle_the_scanner_never_matches` 钉的就是这一格）。外面还有两道闸门，各自挡掉一种"整库被读空"：`storage.reachable(source.path)` 挡挂载盘没就绪（那一轮清单是空的，核对会把每条登记都删掉，`tests/test_storage/test_scan_through_seam.py::test_unreachable_share_keeps_registered_subtitles`），`storage.capabilities.sidecar_subtitles` 挡源类型被 `PUT /api/sources/{id}` 从本地改成对象存储——那些 `s3://` 地址在本地 `isfile` 看来永远"不存在"，不看能力就核对，一次扫描能把这类历史行整批删掉。`subtitles_gone` 只走服务层的返回 dict 和通知的 JSON 列，**没有**进 `ScanResultResponse`（和 `foreign_paths` 同一待遇：这个响应模型是固定的，多余的键被 Pydantic 丢掉），所以 `backend/openapi.json` 不用重导；但通知 `data` 那一列是前端 `toEqual` 在断言的契约，改它就要同步 `frontend/e2e/real/library.real.spec.ts` 那三处。

`settings` 与 `user_preferences` 是两张不同的表，别混：前者全家一份（扫描间隔、缩略图尺寸、默认转码格式），改一次所有人的播放都受影响，读写都限 owner；后者一人一份（`user_id` 主键 + `prefs` JSON），走 `/api/preferences`，成员改自己的主题不该碰着别人的屏幕。写入是按键合并（`save_prefs` 只覆盖 patch 里非空的键），响应字段由 API 层的 Pydantic 模型限定，所以加一项偏好只是加一个字段，不必改表。JSON 列的坑：原地 `row.prefs["k"]=v` SQLAlchemy 看不见，必须换一个新 dict 赋回去。

`settings` 那一面有两道校验，别只做一半：键名走 `SYSTEM_SETTING_KEYS` 白名单，值走 `_check_setting_value`。第二道存在的理由是第一道挡不住——`GET /api/settings` 把三个数字键 `int(...)` 回来，而单键 `PUT` 收的是裸字符串，于是"写进去一个读不回来的值"会把整个设置页永久打成 500（整份 `PUT` 有 Pydantic 挡着，从来没这个问题）。校验规则就一条：**写进去的值必须能被读回来的那条路径解析**。范围（负数、0）刻意不管：那三个键目前没有任何消费者，定时扫描读的是源级别的 `scan_interval`，等真有消费者了再按它的约束收口。

`settings` 表里现在**只有一个键真的在管事**：`auto_scan_enabled` 是自动扫描的总开关，读者是 `scheduler/tasks.py` 里那两个扫描包装任务，每轮现读（`SettingService.is_auto_scan_enabled`），关了就整轮不走、也不写任何通知——一轮被开关拦下的扫描不是事件，给它写一条就是 #85 刚删掉的那种心跳。解析规则只留 `setting_service.parse_auto_scan_enabled` 一份：没写过这一行算**开**（新库那张表本来就是空的，一个字没写过的人不该被静默停扫），设置页 `GET` 也走它；两处各写一套的话，同一个字符串就有两种真值。闸门刻意落在**任务**上而不是 `ScanService` 上：设置页说的是"自动"扫描，人按「扫描」按钮那一路不归它管。用例在 `tests/test_scheduler_auto_scan_switch.py`，五条各挡一种改法——把闸门从任务挪进 service，只会红在「手工扫描不该被管」那一条。另外四个键（`auto_scan_interval`、`default_transcode_format`、`thumbnail_width`、`thumbnail_height`）**仍是装饰**：存得进去、读得回来，`Settings.vue` 之外没有任何代码按它们做事——包括那个和源级别的 `scan_interval` 长得很像的间隔。

同一类闸口的另一半是**可空性**：请求模型里标 `X | None` 的字段，那一列必须真的收 `NULL`。`VideoUpdate.rating` 从前标的是 `int | None`（意思是"不填就不改"），而 `videos.rating` 那一列是 NOT NULL，于是 `{"rating": null}` 是一条一路好走的请求——Pydantic 放行、服务层 `setattr` 照单写库、asyncpg 在 `UPDATE videos SET rating=NULL` 上顶回来才炸成 500，而响应模型 `rating: int` 本来就从来发不出 null，那一半契约是假的。收口放在请求模型的 `field_validator` 上（得到一个 422 加一句原话），不放在服务层：这是**表示层的形状**，不是业务规则，而且 422 那套 `detail` 结构前端已经有统一处理。反面那一半同样要钉住——`title` / `description` 那两列可以为空，同样的 null 照旧 200，否则一次修复会顺手把合法输入一起挡在门外（用例：`tests/test_api/test_videos.py` 的 `test_an_explicit_null_rating_is_rejected_instead_of_500` 与 `test_an_explicit_null_title_is_still_allowed`；界面那一侧在 `frontend/e2e/real/video-edit.real.spec.ts`）。Pydantic v2 的口径量清楚过：`field_validator` **不跑**在"根本没提供"的字段上（`VideoUpdate().model_dump(exclude_unset=True)` 实测是 `{}`），只会跑在显式给进来的值上，所以"不填不改"和"填 null"这两件事天然分得开，闸口不必自己判 `model_fields_set`。


从 `settings.theme` 迁到 `user_preferences` 靠 `session.py` 里两条幂等 SQL：`INHERIT_THEME_IN_PREFERENCES` 把全家共用的那个老值发给每个还没有偏好行的账号（写入条件写成 `WHERE NOT EXISTS`，重复启动不会覆盖任何人改过的值），`DROP_SHARED_THEME_SETTING` 再删掉 `settings` 里的 `theme` 行。顺序不能反，反了所有人的选择就凭空变成默认浅色。

老库升级后的第一次 `create-user --role owner` 会顺手认领：`AuthService.claim_legacy_rows` 把 `user_id IS NULL` 的行交给这个账号，并把旧的 `new_videos.viewed` / `notifications.read` 一次性翻译成两张 `_reads` 表的记录（列已不存在就跳过）。这一步不做，升级后收藏与历史看起来就像被清空了。

**裸 SQL 的方言纪律**：`src/` 里手写的 SQL 一律按"PG 也能跑"来写，SQLite 独有的写法只允许留在 `src/db_audit.py`（它读的就是那个老的 SQLite 文件）。已清掉的几类和它们的替身：

- **NULL 安全的相等**：`a IS b` 是 SQLite 的写法，PG 那边叫 `IS NOT DISTINCT FROM`，没有两家通用的拼法，所以 `DEDUPE_PLAY_HISTORY`/`DEDUPE_FAVORITES` 摊开写成 `(a = b OR (a IS NULL AND b IS NULL))`。别图省事退回 `=`：归属列在老库里全是 NULL，用 `=` 这些行压根不进分组，去重会静默变成空操作（不是删错，是一个都不删）。
- **"有了就别插"**：`INSERT OR IGNORE`（SQLite）和 `ON CONFLICT DO NOTHING`（PG）也是两家不同。统一写成 `INSERT ... SELECT ... WHERE NOT EXISTS`，规则只有一份，还顺便说清了"哪一对键算重复"——`_inherit_read_state` 和 `INHERIT_THEME_IN_PREFERENCES` 都是这个形状。
- **表结构反射**：`PRAGMA table_info` 换成 `session.py` 的 `table_columns()`，它内部走 `inspect().get_columns()`，问每种方言问法不同、答案同形。踩过的坑：`run_sync` 两家递进来的东西不一样——连接那家给同步连接，会话那家给同步会话，把会话直接交给检查器会抛 `NoInspectionAvailable`，所以会话一侧走 `session_table_columns()`。
- **取日历日**：PG 没有 `date()` 函数，SQLite 的 `CAST(x AS DATE)` 又会把文本折成数字，两家没有中立形式，所以 `get_stats` 读原始事件行、在 Python 里归桶。这类"不报错、只静默给空结果"的差异比语法错误危险得多。
- **时间戳**：SQLite 存下去的是永远不带偏移的 UTC 文本，PG 的 `TIMESTAMP WITH TIME ZONE` 则按会话时区还一个带偏移的值。跨这两家做比较、分组或展示的，一律先过 `src/utils/time.py::as_utc()`。

`ilike(..., escape="\\")` 不用动：SQLAlchemy 2.0 在 SQLite 上编译成 `lower(x) LIKE lower(?) ESCAPE '\'`，在 PG 上编译成 `x ILIKE %(p)s ESCAPE '\'`，转义语义一致（实测两家各编译一遍，不是靠印象）。

换数据库之前先跑 `uv run python -m src.db_audit`（`src/db_audit.py`）。它只以 `mode=ro` 打开库文件，拿模型的 `Base.metadata` 和库里的实际 schema 对账，报九类问题：schema 漂移、库里没落实的外键约束、孤儿行、值类型不对、VARCHAR 超长、整数超出 PG 的 32 位 `integer`、NOT NULL 列里的 NULL、解析不了的日期与 JSON，并给每张表算一个方言无关的内容摘要（布尔→true/false、时间→UTC ISO、JSON→键排序，整表排序后哈希），搬完在目标库上再算一遍对得上才算搬全。之所以要有这么个脚本而不是"迁过去看报不报错"：SQLite 的类型亲和、不检查长度这两件事会让一批数据在 SQLite 里存得很好，到 PG 那边要么被拒要么被静改写；外键那一条 #161 起在应用连接上已经真强制，新的孤儿子行进不去了，`orphan_row` 那一类查的从此是开关之前那段历史留下的行（本机那五个老库 `PRAGMA foreign_key_check` 实测零违规，别的检出未必）。而只存在于库里的列（如认领后剩下的 `viewed`/`read`）会不会丢数据，只有数一遍非空值才知道。报告写到 `data/migration-audit-<日期>.md`（`data/` 不进版本库），stdout 只打 ASCII——控制台是 cp936。用例在 `tests/test_db_audit.py`，那里造了一个每类问题都有一条的脏库；真库跑出来的"一切正常"证明不了检查还活着。

搬家的顺序：审计（`db_audit`）→ 目标库建空（`deploy/pg-provision.example.sql`，schema 由 `0001` 基线建，别手工建表）→ `db_transfer --from <老库> --to <新库> --dry-run` 预演 → 去掉 `--dry-run` 正式搬。`--dry-run` 会一路跑到对账通过再整体回滚，新库不留一行，所以它和正式搬用的是同一条代码路，预演过了才算过。目标库必须已建表且为空，否则直接中止。搬的时候 `sessions` 整表跳过（旧 token 到了新库也不该还能用），`alembic_version` 也不搬；自增序列会推到当前最大值，但**只有 PG 这一头需要拨**——SQLite 在带显式 rowid 插进去时自己就把 `sqlite_sequence` 顶到那个值（#202 实测），而脚本原先那道「库里得有 `sqlite_sequence` 才拨」的保险拿的是反射清单，方言默认把 `sqlite_%` 内部表滤掉，于是两头都够不着，#206 按用户定夺（第三块面板⑩甲）删掉了那一格，不是把它修活。方向是双向的：回滚到 SQLite 就把它当目标库再搬一次，`_reset_sequences` 如今只认 PG。

真后端 e2e 的现场由 `src/e2e_seed.py` 一手准备，前端只负责把它串在 uvicorn 之前起（`frontend/CLAUDE.md` 的「打真后端的端到端测试」）。这里有两道闸门，理由和 `db_transfer` 一样——"连哪个库""清哪个目录"都只看一条环境变量，所以判据不能靠调用方自觉：库名必须以 `_test` 结尾才允许 TRUNCATE，非 PostgreSQL 方言直接拒收（这套用例要证明的就是和生产同一个方言）；媒体目录必须落在 `backend/data/e2e` 之下才允许整目录删除，否则报错发生在任何删除之前。**媒体夹具在这个进程里写，不放在前端的 Playwright 配置里写**：那个配置文件会被执行好几遍（主进程 + 每个 worker），写在配置里的副作用会在播种之后把 `data/e2e` 再清一次，留下的现象是库里的封面路径指向一个不存在的文件。扫描产物同样只核对不解释：1 部片子、1 条字幕、1 张封面，对不上就在起步时失败，而不是让每条用例各炸一次——封面这一项是为了 FFmpeg 不在 PATH 上时报"ffmpeg 抽不出封面"，而不是报一个看不出根因的图片加载失败。个人的那两行（一次观看进度 + 一条片单）也走**服务层本身**（`VideoService.record_play`/`update_progress`、`WatchlistService`），不手写 INSERT：`completed` 是 `is_completed()` 按 `duration` 的尾部容差算出来的，继续观看那条轨只读 `completed == False` 的行，自己抄一份判定规则的话规则一改夹具就悄悄失真，变成"库里说看完了、界面上还在轨里"这种两边都自洽的假象。账号建**两个**（owner + member，都走 `AuthService.create_user`）：member 那份不写任何个人数据，专门给角色网关那条用例撞真中间件用。这里的核对闸门查的是 `users.role` 这一列而不是行数——那条用例断言的全是 403，"member 那行压根没建成"和"账号真没权限"在现场长得一模一样。**播种不建任何标签**：标签那条用例把 `GET /api/tags` 整张表当成"只有我自己建的那两个"来断言（一个挂了片子、一个没挂，好让 `video_count` 各数各的），将来谁在播种里加标签就会把它弄红，加的若是带影片的标签更会——那个 0 才是它的判据。通知同理：播种只留下**那一趟扫描自己写的那一条** `scan_complete`（`scan_service.py:362` 那道"库没变就不发"的闸门在真链路上跑过一遍），而通知那条用例把 `notifications` 整表当成"只有一行"来断言，并且它自己还会再扫一次同一批文件来证明"零新增一条都不发"——所以在播种里多发一条通知，会直接弄红那条用例。源表也一样只留**一个**（`E2E local`，`last_scan_at` 已经被播种那趟扫描盖上）：同目录双源那条用例把 `GET /api/sources` 当成"播种那一个，加上它在页面上新建又删掉的那一个"来断言，末尾要求这张表回到只剩播种那一个，所以在播种里预置第二个源会直接弄红它；它故意不预置，为的就是让"从未 → 有时间戳"这一格变化真的发生一次。

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
        UTCDateTime(), 
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
- **生成的文件跟着记录走**：删影片或删整个视频源时，`delete_videos_cascade` 把被删行的 `thumbnail_path` 和 `transcode_outputs.output_path` 交给调用方，提交成功后由 `delete_generated_files`（#185 前叫 `delete_cover_files`）从磁盘移除；漏了这一步就是永久孤儿文件（删行不碰磁盘，重扫又会按同一个派生名新建一张封面，盘上只会越攒越多；产物目录压根不在扫描范围内，那一行又跟着影片一起没了，从此无人知晓）。产物那一头还有一道目录闸门，只认 `transcode_output_dir` 里面的路径。视频本体**永远不删**——那是用户的片，不是应用生成的。细节见「数据模型」一节

### 转码产物落盘（#154）

- **产物不能落在任何片源目录里**：`product_path(input_path, target_format, video_id)` 是 `transcode_output_dir/<影片 id>/<源文件名去扩展>.<格式>`。从前它是 `Path(input_path).with_suffix(...)`，也就是**源的旁边**，而那一半正是扫描范围——`file_scanner.scan_directory` 的 `os.walk` 一路下潜、没有排除名单，于是下一轮扫描把产物登记成一部新片子，同一部片子还能再转一遍
- **`TRANSCODE_OUTPUT_DIR` 的相对值和封面/备份目录一样，在配置层就按 `backend/` 展开成绝对路径**（`config.py` 的 `_anchor_under_backend`，三个 key 共用同一个 validator）。理由更硬：那串路径会**写进库里**（`transcode_outputs.output_path`），一个 cwd 相对的值意味着换启动位置就等于产物集体"消失"
- **按影片 id 分子目录，不是为了整洁**：平铺布局下两个片源里的同名片子（`data/a/movie.mp4` 与 `backups/movie.mp4`）会指向同一个产物，而 ffmpeg 带 `-y`，覆盖是静默发生的
- **同格式那道闸门留着，挡的理由换了**：产物不再落在源旁边，同格式不会**覆盖**源文件，但它仍然让产物和源**同名**——库里那行 `movie.mkv` 和产物表那行 `movie.mkv` 在人眼里是同一个东西，而这一单买的就是"产物看得见"。所以比的是源的扩展名而不是拼出来的路径
- **`transcode_outputs` 只在成功那一路写**（`_record_output` 挂在 `_run` 的 success 分支、`_notify` 之前）：失败的任务压根没有文件，取消的那一路 ffmpeg 已经把半截文件 `unlink` 掉了。往表里写一条"存在过、其实没有"的行，正是这一单要修掉的那种谎
- **`deleted_at` 唯一的写的人是读时核对**（`list_outputs()`）：产物目录在所有片源之外，扫描走不到它，除了这一次 `stat` 没人能说得出"那份文件没了"。反方向也一并翻回来（文件被放回去时标记清掉），否则这一列从漏报变成误报。`size_bytes` 是**这次请求当场 stat 的**，不是表里的抄本
- **服务重启之后 `_jobs` 那本账是空的**：`GET /api/transcode/{video_id}/outputs` 是产物唯一的出处（进程内存里的任务表不是持久层，别拿它回答"这片子转过什么"）
- **删影片会带走产物文件**（#185，第二块选项板⑦甲）：`delete_videos_cascade` 收集被删行的 `transcode_outputs.output_path`，和封面同一个顺序——**提交之后**才由调用方落盘。这一格从前是留白：行跟着 `videos` 没了（外键 CASCADE），盘上那份 `<输出目录>/<id>/` 里的文件留在原地，而产物目录不在任何片源的扫描范围内，没有任何东西会去扫它、也没有任何一行还指着它——永久孤儿。反过来说**顺序错了更难看的**：先删文件再提交，一次回滚留下的是"行还在、产物没了"，`GET /api/transcode/{id}/outputs` 会当着人的面报"文件已丢失"
- **那条 `output_path` 入不了片库**：收集这一头先过 `_owned_products`（`realpath` + `normcase` 比 `transcode_output_dir` 前缀）。这一列是库里的一串字符串，#154 之前写的就是**源的旁边**，放开删等于把手伸进片库——最坏的一格是同一部片子转成和源同名的容器（`movie.mp4` → `movie.mp4`），"删一条产物记录"变成"删掉用户真正的影片"。目录外的路径一律留着：宁可剩孤儿，不许误删


`boto3` 是可选依赖（`.[s3]`），不装也能起服务，真去读对象存储时才提示「请安装 .[s3]」；`moto`（在 `.[dev]` 里）在内存中演一个桶来测 S3 实现，不碰网络——它证明的是客户端接线正确，不代表真服务器就这么答，端点行为仍要人肉验一次。两个包都没装时相关用例 `importorskip` 跳过而不是报错。

## OpenAPI 快照（`openapi.json`）

前端有 14 份手写请求模块，形状规则（不带 `/api`、不以 `/` 结尾、没有 `//`）能挡住双前缀和拼接错位，但**挡不住段名写错**：`/videos/duplicates` 少写一个 `s` 在形状上完全合法，前端单测全绿，打到后端才发现是 404。所以路由表本身要有一份可核对的落盘产物。视图侧也不再就地拼 URL（`Sources.vue` / `Transcode.vue` 那 7 条在 #123 搬进了 `src/api/`），浏览器自己取的那四类地址（封面、播放流、两条字幕轨的 `src`）也在 #124 搬进去并按 GET 对同一张表核对，否则模块外的地址根本不进这份核对。

- **`python -m src.export_openapi` 生成/更新根目录的 `openapi.json`**（`--out` 换目标路径，`--check` 只比较不写盘，不一致就退出码 1）。产物是 `json.dumps(..., indent=2, sort_keys=True)` + 尾换行：键排序、缩进固定，diff 里才会只出现接口本身的变化。当前 66 条路径 / 85 个操作、5677 行。
- **导出不需要起服务**：`app.openapi()` 是离线构建的（实测把 `DATABASE_URL` 指到一个没人监听的端口照样出 66 条路径，且与提交的那份逐字节相同）。别顺手写"先启动 uvicorn 再抓 `/openapi.json`"的流程。
- **改了接口就要重跑一次导出**，否则红的是快照而不是调用方。`tests/test_openapi_snapshot.py` 是防腐钉子（比 `--check` 更严：直接把提交的文件和 `app.openapi()` 逐键比对象，注释、格式差异不会造成假红），删掉提交文件里的任何一条路径都会让它红——实测删 `/api/auth/sessions` 时 **9 条用例红 2 条**（2026-10-08 复量；红的是逐键比对那条和"`--check` 与快照同进同退"那条，另外 7 条不看提交文件所以照绿）。
- **写的人和核对的人用的是同一份判断**（#170 钉住这六行）：`--out` 那一趟只写 LF（`newline="\n"` 不是装饰——这份文件前端要读，两端换行不一致时 diff 里全是 `^M`），`--check` 比的是**解析后的对象**，所以同一份 schema 换个缩进或键序照样算一致；反过来不许把"谁顺手跑了个格式化"演成一次假的不一致。"读不出一个 schema"的三种面目都算不一致：文件还没生成（新克隆在第一次导出之前就是这个状态）、`--out` 指到一个目录（Windows 上抛 `PermissionError`、POSIX 上 `IsADirectoryError`，两支同属 `OSError`，所以用例别写死 errno）、内容不是 JSON（半截写入、或被补丁工具换成冲突标记）。打印那句里的路径条数是**从刚写出去的那份文件数出来的**，不是写死在代码里的数字。
- **`if not output.exists(): return False` 那一句不是守卫**，实测是等价变异：摘掉它之后读不存在的文件抛 `FileNotFoundError`，而它本身就是 `OSError`，被同一个 `except` 接住、照样返回 `False`，没有任何可观察差别。那一行只把语义写明白——别指望删了它会红，也别在它上面加"依赖它才成立"的逻辑。
- **这份快照有个下游消费者**：`frontend/tests/api/openapi-contract.spec.ts` 拿它核对前端真正会请求的地址（路径 + 方法 + 路径参数类型 + query 键名）。它读的是磁盘上的 JSON，不 import 后端，所以跨语言、不需要后端进程；代价就是上面那条——快照滞后，那边红的是快照。**两节各红各的，实测（#148）**：把 `src/api/videos.py` 里路由声明的 `search` 改名，红的是 `test_openapi_snapshot.py`（钉的是代码↔文件），前端那层照绿——因为它读的文件还没变；只改提交文件里的声明名，红的是前端那层（钉的是文件↔接口）。两段接起来才钉住「路由代码 ↔ 前端接口」，别指望任何单独一层。
- **没声明的查询参数会被静默忽略**（实测：`GET /api/videos?searsh=abc&page=1` 回 **200**，返回的是**没筛过**的第一页）。FastAPI 只把声明过的查询参数绑进函数签名，而 `backend/src` 无一处读 `request.query_params`（grep 零命中），所以前端拼错键名既不会 422 也不会 400，只会让筛选无声失效——这正是前端那层 query 钉子存在的理由（`frontend/CLAUDE.md` #148）。
- **别指望 `app.routes` 能枚举路由表**（这条在「共享的 HTTP fixtures」一节也写过）：这版 FastAPI 把 include 进来的路由存成 `_IncludedRouter` 对象，没有 `.path`，只列得到顶层 21 条。想核对"声明的路径确实注册了"，走 `app.openapi()`，不要走 `app.routes`。

## 测试规范

### 测试文件结构

```
tests/
├── conftest.py           # 公共 fixtures
├── test_database.py      # 旧库跑 apply_schema_fixes：归属列、索引替换、可重放
├── test_error_message_language.py # 第五层静态守卫：后端写给界面的每一句都得是中文（#188）
├── test_api/
│   ├── test_videos.py
│   ├── test_isolation.py # 两个已登录客户端互相够不着对方的数据
│   ├── test_users.py     # 账号管理面：护栏（不许停用自己、必须留下一个 owner）、降级即踢会话
│   ├── test_preferences.py # 偏好按人存、按键合并、默认值；系统配置的两道校验（键名白名单、值要能被读回来的那条路径解析）
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

### 第五层静态守卫：后端错误文案的语言（`tests/test_error_message_language.py`，#188）

界面那句 toast 是 `frontend/src/api/client.ts:100` 把 `error.response.data.detail` 原样当 Error message 拼出来的——**后端写哪种语言，用户就读哪种语言**。#131 那层守卫只看界面里写死的字面量，运行时从后端来的那句它看不见；反过来这一层也不管界面文案。两条守卫各管一半出面。

为什么用 Python 的 `ast` 而不是隔壁四条 Vitest 守卫那种正则遍历：被扫的源是 Python。正则要在 TypeScript 里再解析一遍 Python 字符串，会漏隐式拼接、被 docstring 假命中，而 `detail=某个常量名` 要查定义才能判——`ast` 对这些是免费的。三段式照抄 `frontend/tests/views/toast-language.spec.ts`：**扫描下限（41 个文件）/ 命中下限（140 站点、94 句自撰、46 转发）/ offenders 为空**。

出海的面是**三种形状**，少一种就会在全绿的同时留一句英文进 toast：`detail="…"`（api 写死）、`raise ValueError("…")`（经路由 `detail=str(e)` 出海，抛它的可能是 services / utils / storage），以及 `return False, "…"`（`transcode_video` 那一族不抛异常，那句进 `job.error` 经 `/api/transcode/status` 原样落进 `ElMessage.error(…)`，实测四条全在 `src/utils/ffmpeg.py`）。**边界也写下来了**：`passthrough` 那 46 处是转发型（`str(e)`、纯变量），这里没有可判的语言；ffmpeg 自己的 stderr、操作系统那句 `[Errno 2]`，语言不由我们决定，所以也不由这一层负责。`src/api/stream.py:73` 那个 JSONResponse 的 `message` 字段是刻意留下的例外——它是给 curl 看的端点回声，界面从不渲染它。

变异电池 `backend/Temp/m188_mut.py`（11 格：M1 api / M2 services / M3+M3b 那条 return 形状 / M4 扫描面缩成一层 / M5 f-string 两条识别路径 / M6 判据恒假 / M7 raise 遍历摘掉 / M8 跨模块常量 / 三格对照）实测 **9 红 + 2 绿**，两格绿是设计好的 A/B 对照（M9：同一句英文、摘掉 `return` 遍历 → 看不见，证明 M3 的红是那条遍历给的；D1：判据恒真 → 任何句子都不算违规，证明承重的是判据而不是命中数）。

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
    UTCDateTime(),
    default=lambda: datetime.now(timezone.utc)
)
```

SQLite 不存时区：写进去的是 UTC，裸 `DATETIME` 读回来的 `datetime` **不带 tzinfo**，和 `datetime.now(timezone.utc)` 直接比大小会抛 `can't compare offset-naive and offset-aware datetimes`。#162 把这件事收在列类型上：`UTCDateTime.process_result_value` 走的就是 `as_utc()` 那套语义（没带 tz 当作 UTC，带了就换算到 UTC），所以**经映射列读出来的时刻永远带 `tzinfo=UTC`**，两种方言还给的同一种形状。

为什么修在类型这一层、不是在调用点：病灶不是应用自己的比较，而是 SQLAlchemy 的 ORM 批量删除——`delete(UserSession).where(..., expires_at <= _utc_now())` 执行完，框架要在 **Python 里**按同一条 WHERE 把 identity map 里的对象重跑一遍（`orm/evaluator.py`）好把它们摘掉；identity map 里躺着的正是那批 naive 值，于是 `naive <= aware` 当场炸。应用代码怎么写都绕不开框架自己那次评估（`auth_service.purge_expired_sessions` 是唯一一处带时间比较的批量 DML，但这颗雷不该只由它躲）。

`as_utc()`（`src/utils/time.py`）还在，走的路也还在用：`db_transfer` 从老库里捞的是 **Core 行**、没经过映射列的类型，`auth_service`/`history_service` 里那几处比较也照旧先过一道——它对 aware 值是幂等的，留着不亏。

要在测试里重造这个现场（不管是验红还是以后查同类问题），得**换一个会话把行读回来并且取完**：同一会话里刚 `add` 完的对象带的是 Python 侧那个 aware 值，评估器比得出结果、红不了；只 `await session.scalars(...)` 不 `.all()`，identity map 里根本没有对象，也红不了；用 `expire_all()` 摆出"读回来"的形状，红点会跑到 `MissingGreenlet`（那是本机的同步惰性加载），钉不到病灶。三种摆法都实测过，能红的那一种是 `tests/test_utc_datetime_columns.py` 里写的那一种。

换成 PG 后上面这些一条都不能丢：`TIMESTAMP WITH TIME ZONE` 还回来的是**带偏移**的值，而且偏移按数据库会话时区给，不一定正好是 UTC——`UTCDateTime` 现在负责把它换算成 UTC，`as_utc()` 负责所有没经过映射列的来路。别改成"直接信任库里给的 tzinfo"。

同理，测试里改过某行的时间后要看真实结果，用 `await db_session.refresh(row)` 重新读；`expire_all()` 之后靠关系属性懒加载会抛 `MissingGreenlet`。

**关系只要被响应模型读到，就必须写进那一条查询**（2026-10-05 实测）。`VideoResponse` 带 `tags`，而 `get_videos_by_tag` 是经多对多的 `Tag.videos` 走到影片的，那批影片的 `tags` 没有被关系上的 `lazy="selectin"` 带上，序列化时（pydantic 是同步的）一碰就是 greenlet 之外的 IO → 端点 500。写法是把它链到底：`selectinload(Tag.videos).selectinload(Video.tags)`。别指望默认加载兜住：同样用 `expire_all()` 造冷会话，经**多对一**（`PlayHistory.video` / `Favorite.video` / `WatchlistItem.video`）的五个读接口都能带回标签，只有经多对多集合那一头会漏（`tests/test_api/test_video_reads_with_a_cold_session.py` 钉的就是这个差别）。我没从文档里推出一条"什么时候默认加载会生效"的一般规则，所以按戒律走，别去赌那个形状。

### 4. 类型检查剩下的两类边界

`mypy src` 现在这 34 项不是"注解还没写完"，是两处刻意保留的形状。别指望总数降到 0，也别为了凑数加 `cast`：

- **端点返回 ORM 对象，而返回注解就是 response 模型**（27 项，全在 `src/api/`）。FastAPI 在序列化时用 `from_attributes` 把 `Video` 变成 `VideoResponse`，静态检查看不到这一步。真要清零只有两条路：每个端点显式 `VideoResponse.model_validate(...)`，或者把注解摘掉改用 `response_model=`——两种都会改到 API 层一贯的写法，属于设计决定，得单独议
- **service 层往模型实例上挂瞬态属性**（`Video.progress`、`Video.is_new`、`Notification.read`，7 项），为的是响应模型顺手读到"这一部你看到哪了"。SQLAlchemy 2.0.51 不认非 `Mapped` 的类级注解（直接 `MappedAnnotationError`），而这个版本还没有 `Unmapped`，所以在模型侧声明这条路走不通；根治是让这类数据别寄存在模型上

写 SQL 表达式时记一条：`Video.title` 这类 ORM 属性在类型上是 `InstrumentedAttribute[str | None]`，它既不是 `ColumnElement[str]` 也不是 `KeyedColumnElement[str]` 的子类型。要接住它并用 `.ilike`，参数标成裸 `ColumnOperators`（见 `video_service._like`）。

### 5. 覆盖率：闸门是 80，但只在带 `--cov` 的全量跑上生效

`[tool.coverage.report] fail_under = 80`（2026-10-04 挂上，当时实测 86%——那是下面那条未修正的读数）。没写成 pytest 的 `addopts`，是因为那样"只跑一个文件"也会去比总量——一个文件的覆盖率天然不到 80，报回来的红和"测试坏了"长得一模一样，纯属误导。要量就明说：`pytest -q --cov=src`。

`--cov` 后面**只写目录，不写模块名**。`--cov=src.database.session` 这种写法本机连踩两次：解释器在 `asyncpg` 建连接的那一刻 `Windows fatal exception: access violation` 直接段错误，退出码 139，栈顶是 `connect_utils._create_ssl_connection`——测试本身一条没跑完，看起来却像"这套用例把进程弄坏了"。同一批文件换成 `--cov=src` 立刻正常（14 passed，`session.py` 那一行照读）。原因没有查实，先按"这条路上有个坑"记下来。

**读报告前先知道这一条：coverage 默认会把异步代码少算。**SQLAlchemy 的 async 引擎每个 `await` 都要过一次 greenlet 切换，而 coverage 不认 greenlet 时行追踪器在切换后丢失——于是**函数体里那些落在 `await` 之后的行会被报成"没执行"**，哪怕用例就是从那几行走出来的。`pyproject.toml` 里的 `[tool.coverage.run] concurrency = ["greenlet", "thread"]`（2026-10-05 挂上）就是为这一条；两边实测同一套全量：未配置 TOTAL **86%**（589 miss），配上 **91.49%**（364 miss），两次都是 698 passed + 1 skipped，所以少算的确实是执行过的行。同一套标签用例在两种配置下分别报 `api/tags.py` 76% / **100%**、`tag_service.py` 37% / **97%**。

所以看覆盖率只有两条戒律：

- 别拿单文件百分比当"这里没测"的证据去补用例，先看 `tests/` 里到底有没有走过那条路径
- 别为了让报告好看抬高 `fail_under`：80 在未修正的读数上就还有余量，修正后余量更大，动它只会把历史数字弄丢

下面那份薄位置清单是**修正后**重测的（SQLite 全量 717 passed + 1 skipped，TOTAL 92%，2026-10-05 复量；清单里个别条目另标了自己更晚的重量时间）：

- `src/utils/media_streams.py` 与 `src/utils/subtitles.py` **内嵌那一路也拒零 cue 的 WebVTT，两条路从此问同一个判据**（#208，2026-10-12 PG 全量 **1060 passed** 时重量，TOTAL **99.10%**——**4649** 句 / **42** 未覆盖，两个文件照旧各自 **0 缺 / 100%**）——第三块面板 ④（#155 剩下的那一半）用户选**甲**：内嵌这一路照补，但补的是**同一个判据**，否掉的是「两条路各写一套口径」。
  - **那个洞是量出来的**：本机 ffmpeg 实测——一份只有头部、一条 cue 都没有的 `.srt` 封进 `mov_text` 再抽出来，子进程回的是 **rc=0、stdout 恰好 7 字节（`WEBVTT` 加一个换行）、stderr 空**。旧闸门 `returncode != 0 or not stdout.strip()` 问的是「有没有写字节」，那四个字母算写了，于是接口照交 200，浏览器把那条轨标成 loaded（`cues.length === 0`）而**不发 `error`**——#146 那套「没能加载」的提示一辈子不执行，看的人只能靠盯着片子才发现这条轨是哑的。与 #187 外侧那个洞是同一个症状，只是发生在另一条路上。
  - **判据只有一句**：`has_a_cue` 从 `convert_to_webvtt` 里提出来放在 `subtitles.py`，正则一字未动（仍是 #140 那个 `_CUE_TIMESTAMP_LINE`，同时认 Python 的 `00:00:03.000 -->` 和 ffmpeg 省掉小时的 `00:05.000 -->`）。两处的 docstring 互相点名：改一边口径的人会在另一边读到「另一条路问的是这同一个问题」。这一句是深接口还是纯 DRY 有量法——电池 A3（判据永真）红 **10** 条、A4（判据永假）红 **19** 条，两格都是两条路一起塌，说明它确实是共用承重，不是各自抄一遍。
  - **新旧两道闸门各有各的原话**：子进程失败或整段空白 → 沿用 ffmpeg 自己的原因（「该轨无法转成 WebVTT」那条），子进程成功而里面没有 cue → 新闸门（「这条轨里没有解析出任何一条字幕」）。这一单的诚实记录：电池 A7（摘掉旧那道 `or not stdout.strip()`）第一次跑**是绿的**——「rc=0 且一个字都没写」这一格在改前根本没有钉子。补上 `test_extract_says_the_track_wrote_nothing_when_it_wrote_no_bytes` 之后 A7 才红 1 条。**别把新闸门当成旧闸门的替代品**，它接的是另一种失败。
  - **红是当场量的**：把两份源文件临时换成 HEAD 那一份再跑本单五条新用例，当场 **3 failed / 2 passed**——`test_media_streams.py:253` 与 `:276` 各是一个 `DID NOT RAISE`，API 那条是 `assert 200 == 415`。照旧绿的那两条各有理由：一条测的正是**旧**闸门本来就接住的形状（它是为了让 A7 变红而加的），一条是反面用例。跑完按 md5 换回工作区那一份。顺带把 `tests/test_error_message_language.py`（第五条守卫）在当前源码上跑成 **3 / 3**——新写那句原话本身就是中文。
  - **电池 9 格：7 红 / 2 绿，两格绿各有名字**（基线 **85 passed**，三份字幕文件在 SQLite 上）：A1 摘掉新闸门 → 红 3（这一单的三条签名用例），A2 改掉那句共用尾巴 → 红 3，A5 摘掉 ffmpeg 短写时间戳那一支 → 红 8，A8 **只**摘外挂那道（#187）→ 红 8——内嵌这几条没有替 #187 兜底，两边各签各的；**A6 绿 = 等价变异**（把闸门挪到缝合之前，`fold_blank_lines_inside_cues` 从不增删时间戳行，按设计就该绿）；**C1 绿 = 对照格**（只改 docstring 的一个词）。
  - **第一盘电池作废，原因是它自己脏**：那一版每格只重写「这格动的那个文件」，于是 A2 改过的那句话在 A3/A4/A5 跑的时候还留在磁盘上，那三格的红里混着我另一处改动；而它整个还跑在我补 A7 那条签名用例之前。两件事叠在一起，那一盘的所有格数作废。第二版每格之前先把**两个**文件都复原，再动一个变量，基线当场核到 **85 passed**（与 `--collect-only` 数出的 85 一致）。**规矩：电池必须在每一格开始前把所有被碰过的源文件回到 pristine，否则前一格的红会算到后一格头上。**
  - **一条旧测试被这单改掉了**：`test_both_child_processes_are_given_a_deadline_and_a_decoding_contract` 那份假装的 ffmpeg 正文从前是「`WEBVTT` 后面两个换行」（今天 430 行），正是这一单开始要拒的形状——它红在闸门上而不是红在它要测的那份 argv/kwargs 契约。按 #187 立下的连带规矩（假装的 stdout 必须带一条真 cue）换夹具，**不是放宽闸门**。
  - **没被牵连的**：`SubtitleConversionError` 在 `api/subtitles.py` 上对内嵌 GET 与外挂 POST 早就各自映射到 **415**，所以 `openapi.json`、那五条静态守卫（第五守卫只要求原话是中文）、前端一行没动；真后端 e2e 第 21 条（`video-embedded-subtitles.real.spec.ts`）不受影响——它现场编的那条 `mov_text` 带的是两句真 cue，签的仍是 200 加浏览器渲染出来的 cue。**没给它加第二个空壳片子**：那要一整轮扫描/删除循环，超出这一单的范围。
  - **读数**：PG 全量 **1060 passed**（用例 1055 → 1060，本单加 **5** 条：`test_media_streams.py` 4 条 + `test_api/test_subtitles.py` 1 条）/ TOTAL **99.10%**（**4649** 句 / **42** 缺，未覆盖清单与 #207 一字不差：仍然只有 `users.py:155-156`、`video_service.py:404` 与 `e2e_seed.py` 那 39 句留白）；全量分母 4644 → **4649**，涨的 5 句正是本单新写的 5 句（`extract_subtitle_webvtt` 的 `if` + `raise`，`has_a_cue` 的 `def` + docstring + `return`），它们全被执行到，所以分子没动；三份字幕文件在 SQLite 上 **85 passed**；`ruff check src tests` 干净（两处 E501 是我把中文按 1 列算写长了，ruff 按 2 列），`mypy src` 基线 **34** 未变；`media_streams.py` 217 行 md5 `a3b8a3fa0a527e14241a356a12f4606a`、`subtitles.py` 380 行 md5 `0f9018d90217ed8db3e5bd136b2005fd`。

- `src/utils/name_parser.py` **组名上限的单位从「字符」换成「显示列宽」**（#207，2026-10-12 PG 全量 **1055 passed** 时重量，TOTAL **99.10%**——**4644** 句 / **42** 未覆盖；这一格从 #193 的 69 句涨到 **72 句 0 缺 / 100%**）——第三块面板 ⑥ 用户选**甲**（按显示宽度封顶），否掉的是「照现状数字符」和「干脆按字节数算」。改的是 `_find_group` 里那道上限（今天 `name_parser.py:119`）加一个三行的私有助手 `_display_width`（`104-106`），用例 18 → **20 条**。改这一族前值得知道六件事：
  - **阈值一个字没动，动的只是量法**：`> 30` 还是 30，30 从「30 个字符」变成「30 列」。因为每个字符至少占一列，`宽度 ≤ 30 ⇒ 字符数 ≤ 30` 恒成立，新规则**只会多拒、不会多收**——所以这一单不可能带来「一个更长的组名被收进来」那类副作用，标签名、库里的行、前端的渲染都不受影响。见证是那条 ASCII 用例一字未动：37 个字母占 37 列，改前按字符拒它、改后按列宽拒它，`group == "NCM"` 照旧。
  - **量的形状**：`unicodedata.east_asian_width(ch)` 落在 `W` 或 `F` 的算两列，其余一列。汉字是 `W`，全角字母与全角连字符是 `F`（`Ａ`、`－` 各占两格），而 `α`、`·` 这类**歧义宽度 `A` 按一列算**——那是这一单选的口径，不是 Unicode 的规定，所以直接钉在用例里（C4 只当 `W` 宽 → 红一条、C5 只当 `F` 宽 → 红三条、C6 把 `A` 也算宽 → 红一条，三个类别各有一格签字）。
  - **边界恰好有两条用例卡住**：15 个汉字 = 正好 30 列 = 收下，16 个汉字 = 32 列 = 跳过，而这正是 30 个 ASCII 字母占的宽度——换成列宽之后两种名字在界面上一样长。电池 C3（`> 30` 写成 `>= 30`）红的那一条就是这格边界，别让下一个人把它当成「差一个无所谓」。
  - **这一单有真红，而且是量出来的**：两条中文用例打在**改前的源码**上当场红——依据是电池 C2，那一格就是把单位退回 `len(candidate)`，也就是改前那行本身，**2 failed** 正是这两条（另外三条用例与单位无关，照绿）。这与 #193/#205/#206 那几单「只加用例/只删码，定义上写不出红」不是同一种形状。
  - **电池 8 格全红、零格等价**：上限整句删掉 → 红三条（ASCII 那格 + 两条中文）；单位退回字符 → 红两条；边界挪一格 → 红一条；`W`/`F`/`A` 三类各拆各量 → 红一、三、一条；系数 2 改成 1、或整个 `return` 退回 `len(text)` → 各红三条。**这一族第一次没有等价格**，因为改的是单位口径，每个变量都有可观察后果。#193 那格结构性红不了的等价变异（`_find_group` 里「空候选或纯数字就跳过」那条 `continue`，今天 113-114）**本单原样未动**，它仍然是等价的。
  - **没被牵连的三样**：`ParsedName` 的字段与 `parse_video_filename` 的形状不变（`_display_width` 只服务于那一道闸门，除它之外零调用方），所以接口、`openapi.json`、那五条静态守卫、前端全部没动；`episode_label` 那条 census 也**原样留着**——面板 ⑤ 定的甲（接进接口、前端两处角标合一）落在待办的 **#209**，不在这一单。
  - **读数**：PG 全量 **1055 passed**（用例 1053 → 1055，#206 那次是删了一条、这一单加两条）/ `src/utils/name_parser.py` **72 句 / 0 缺 / 100%** / TOTAL **99.10%**（4644 句 / 42 缺——未覆盖清单**一个没动**，仍是 39 句 `seed()` 空白 + 3 句两处：`api/users.py:155-156`、`video_service.py:404`；这一单只往分子和分母各加三句全绿的代码）；`ruff check src tests` 干净，`mypy src` 基线 **34** 不变；SQLite 分支同日重测 `tests/test_utils` + `tests/test_services/test_scan_service.py` **183 passed**（这一族本来就不打库，重测只为钉「没有连带」）。`src/utils/name_parser.py` 147 行 md5 `c02cdcd860cd3f66b69b3ce2b67d5145`（改前 139 行 `83a01583508e101a0b253a4e08d401e6`）、`tests/test_utils/test_name_parser.py` 189 行 md5 `e38045746ff6966b8a1f5590bced0703`（改前 153 行 `c53352db4949286892dd8f5ee3203078`），两个文件改前改后都是纯 CRLF。

- `src/db_audit.py` 与 `src/db_transfer.py` **各自最后那 1 句被删掉，两个文件因此都到 100%**（#206，2026-10-12 PG 全量 **1053 passed** 时重量，TOTAL **99.10%**——**4641** 句 / **42** 未覆盖）——第三块面板 ⑨ + ⑩ 用户选**甲**：两处**已各自量出够不着**的死分支删掉，而不是把它修活、也不是照现状留着并说明。删的是 `db_audit._audit_table` 里 JSON 那半 `if isinstance(value, (dict, list)): pass`（sqlite3 从不把 dict 还给你；#201 的电池把它改成 `if False:` 整组全绿，那就是当时的量），和 `db_transfer._reset_sequences` 里「库里得有 `sqlite_sequence` 才拨」那一整格 `elif`（反射默认滤掉 `sqlite_%` 内部表，那个存在性判断恒假；#202 的电池强改成 `if True:` 红 12 条、报的是 `no such table`）。改这一族前值得知道六件事：
  - **分母掉 5、分子掉 3，而这两件事的区别正好是这一单的定义**：`db_audit` 那半边两句（分支头 `if isinstance(...)` 被执行过、`pass` 没有），`db_transfer` 那半边三句（`elif`、内层 `if`、体内那句跨四行的 `await conn.execute(...)`——**一个多行调用只算一句且记在第一行**）。于是 `db_audit.py` 268 → **266 句 0 缺**、`db_transfer.py` 181 → **178 句 0 缺**，已覆盖 4602 → **4599**。#205 那次是「分子只掉 1」，这一单真的少了 3 句**被执行过**的代码——「死分支」和「够不着的分支」的差别就在这：那句 `elif` 每一张表都跑一趟，只是永远跑不进去。
  - **这一单写不出红，而且是定义上写不出**：被删的那两句在两种方言下都执行不到，任何断言都摸不着它。见证是三样——两个 0 缺的读数；`tests/test_db_transfer.py` 24 → **23 条**（少的那条 `test_sqlite_keeps_its_own_counter_when_rows_arrive_with_explicit_ids` 是给那一格开死亡证明的，不是功能钉子）；全量 **1053 passed，一条没红**。**它没有失去签字**：同一件事仍由 `test_the_new_library_keeps_handing_out_fresh_ids` 在真路径上签着——新库是 Alembic `upgrade_head` 建出来的 SQLite 文件，搬完之后新写一条断言拿到的就是 4，撞号当场红。
  - **反射那道过滤的钉子留着，是一处口径不是遗漏**：面板记的是「pinning cases 随分支一起删」，而 `test_the_reflection_this_script_uses_cannot_see_the_sequence_table` 两头都签——它既给已删那一格开过死亡证明，也钉着 `_check_source` 那份「老库里多出来的表」清单（命令行那格 `len(warn) == 2` 就是它的后果：`sqlite_sequence` 一旦被反射看见，每次搬 SQLite 老库都会多报一句用户从没建过的内部表）。所以按「删证据、留活钉子」处理；要按字面全删，说一声。
  - **一处没动，因为它不在面板那「两处」里**：`db_audit._is_type_violation` 中 `not isinstance(value, bool)` 那半句排除是同样形状的够不着（bool 不会是 sqlite3 读回来的形状，#201 的电池把它也记成了等价格）。面板答的是「两处」，所以它照现状留着，源码未动。
  - **没有 idle 的东西带走，也没有「合成一处」**：`_table_names` 仍在 `_check_source`（`db_transfer.py:227`）活着、`text` 在别处有落点、`json` 仍由 `canonical_value` 用着，`ruff check src tests` 两处删完都干净。`canonical_value` 里那份**同名不同命**的 JSON 判断是活的（`db_transfer.py:219` 从 PG 读回来的就是 dict），两者不是同一段逻辑而是同一段话的两种用途，所以删那半不等于合并。
  - **读数与就地更正**：PG 全量 **1053 passed** / TOTAL **99.10%**（4641 句 / 42 缺），`ruff check src tests` 干净，`mypy src` 基线 **34** 不变；SQLite 分支同日重测 `tests/test_db_transfer.py` + `tests/test_db_audit.py` **56 passed + 1 skipped**。`src/db_audit.py` 515 行 md5 `8ad5dd05de3118ac3837d084bfedef35`、`src/db_transfer.py` 348 行 md5 `5dc8fc4143269c702e2a80fe901a0ef4`（行数与 #202 记的一致：删 6 行代码补 6 行 docstring）、`tests/test_db_transfer.py` 735 行 md5 `6abf94c25dd44a4c8850aff9bf3aec3f`；三个文件删前删后都是纯 LF。顺带就地更正一句当时就是假话的记录：`CHANGELOG.md` P4 那一轮写着「`_reset_sequences` 两种方言都实现了」，SQLite 那一半从写下那天起一次也没执行过——那次真跑 153 行没撞 id 是因为 SQLite 自己顶了计数器；本文件「搬家的顺序」那一段同一句已照改。这一单**动了源码**，是本轮十四单（#193 起）里第三次，前两次是 #204 修解析器、#205 删那个零调用方方法。

- `src/services/tag_service.py` **85 句里 2 句未覆盖 → 82 句 0 缺**（#205，2026-10-10 PG 全量 **1054 passed** 时重量，TOTAL **99.05%**——**4646** 句 / **44** 未覆盖）——这一单不做钉子，做的是删除：第三块面板 ⑦ 用户选**甲**（删掉 `list_all`），否掉的是「留着不测」和「给它找一个调用方」，与 #189 删 `ffmpeg.get_video_info`、#191 删 `VideoUpdate.tag_ids` 同一族。**删之前的零调用方普查是整单唯一依据**，所以重数了一遍：全仓 `list_all` 这个名字只剩 `source_service.py:53` 那份**同名不同家**的方法（它有 3 处落点——`api/sources.py:99` 与 `test_source_service.py:51/69`），而 `TagService.list_all` 在 `src/` 内零处、前端零处、`tests/` 里连 `tag_service` / `TagService` 这两个字都不出现——标签那 33 条用例全部从 `api/tags.py` 走进来，唯一被用到的清单方法是 `list_all_with_counts`（`api/tags.py:56`）。**没有一起带走的 import**：`select` / `Tag` / `func` / `video_tags` / `selectinload` / `Video` 六个名字各自都还有别的落点（前四个在 `list_all_with_counts`，后两个在 `get_videos_by_tag`），删完 `ruff check src tests` 仍干净，所以这一单只删那 4 行。**改这一族前值得知道**：
  - **这一单写不出红，是它的形状不是欠账**（#189 / #191 同一句）：没有任何一条断言的路径能走到被删的那个函数，为「它不在了」补钉子等于给一个负事实建档。见证是三个读数——① 上面那份零调用方普查；② `git diff --stat 9b0b191 HEAD -- backend/tests` 里除了 #204 那一个文件之外为空，也就是**测试目录这一单没动**，用例数因此保持 1054；③ 全仓 **4649 → 4646**（−3 句：那个 `def` 行加它体内两句）、未覆盖 **46 → 44**（掉的正是体内那两句 `73-74`）。那 3 句里只有 1 句被执行过——`def` 行在 import 时算一次命中，体内那两句从来没跑到——所以**分子掉 1、分母掉 3**（全仓对得上：已覆盖 4603 → 4602），这一文件因此从 98% 走到 100%，而不是「多测到了 2 行」。谁把 `list_all` 原样搬回来又不测，读数立刻回到 98%。
  - **未覆盖清单同步收窄**：有名有姓的从 7 句变 **5 句四处**——`db_audit.py:309` 与 `db_transfer.py:212`（两处已各自证够不着，**#206 已按第三块面板⑨⑩甲删掉**，此后这里少两处）、`api/users.py:155-156`（可推导地到不了）、`video_service.py:404`（上面那条 SQL 已排除 `file_size IS NULL`），另 39 句仍是 `e2e_seed.py` 里那道刻意留给真 e2e 链路的空白（#203）。#206 之后有名有姓的只剩 **3 句两处**。
- `src/db_transfer.py` **181 句里 24 句未覆盖 → 1 句 → 178 句 0 缺（100%）**（#202，2026-10-10 PG 全量 **1045** passed 时重量，TOTAL **98.60%**——4648 条语句 / **65** 未覆盖；11 条新用例落在 `tests/test_db_transfer.py`（13 → 24 条），全部在 `tmp_path` 里现造 SQLite 文件、不碰应用库，SQLite 分支同日重测同一文件 **23 passed + 1 skipped**；那最后 1 句所在的整个 `elif` 由 **#206** 按第三块面板⑩甲删掉，用例 24 → 23 条，SQLite 分支同日重测 **22 passed + 1 skipped**）——这一族的形状决定了补法：那 24 句里 **18 句是 `main()` 的整个函数体**，也就是说这个脚本从来没被当成命令行程序跑过一次。电池 **20 格：19 红、1 格等价**（等价那格正是「不是整数主键就不拨序列」那句 return，见下），源文件全程未动（md5 `6a80e728fa15b41228634bbfe9c149a8`）。改这一族前值得知道六件事：
  - **剩下那一句是死的，而且是两条各自独立的量**：`_reset_sequences` 里 `INSERT OR REPLACE INTO sqlite_sequence`（212）前面那道存在性检查（211）恒为假——SQLAlchemy 的 SQLite 反射默认把 `sqlite_%` 内部表滤掉（`AND name NOT LIKE 'sqlite~_%' ESCAPE '~'`），所以这张表永远不会出现在这个脚本自己的反射清单里。用例直接查 `sqlite_master` 把这一分界钉住；电池再把 211 改成 `if True:`，**12 条当场红**、报的是 `no such table: sqlite_sequence`——够得着的那句本身就站不住，因为它假设表在，而 SQLite 只在列真声明了 AUTOINCREMENT 时才建它。两种建表路径（`create_all` 与 Alembic 0001）出的都是没有 AUTOINCREMENT 的 `id INTEGER NOT NULL`，另一条用例又量了第二半：表一旦存在，SQLite 会在插入显式 rowid 时**自己**抬计数器（插 id 7 → `seq` 就是 7 → 下一条自动 8）。于是「删掉这个 elif / 换一条真够得着的查询 / 照现状留着」是一个真选择（待选清单第 10 项），源码未动。**#206 按第三块面板⑩甲选了「删掉这个 elif」**：那一格整个摘掉，`_reset_sequences` 如今只认 PG；给它当死亡证明的那条裸 sqlite3 用例（「表一旦存在，SQLite 自己抬计数器」）一起删了，而这件事并没有失去签字——`test_the_new_library_keeps_handing_out_fresh_ids` 走的是真路径（新库由 Alembic `upgrade_head` 建成 SQLite 文件），搬完之后新写一条断言拿到的就是 4，撞号当场红。留着的那条反射用例只钉过滤本身，它今天还有个活消费者：`_check_source` 那份「老库里多出来的表」清单。
  - **`--to` 的默认值就是应用自己那张贴着口令的连接串，所以那一条只能钉在纸面上**：真按默认值搬一次等于往开发库里写。用例把 `transfer` 换成记录用的替身，钉的是「argv 里没给地址时那个字符串确实取自 `settings.database_url`」这一步接线（含 --from/--to 没接反、--dry-run 确实传了下去），并断言那个哨串一个字也没进 stdout/stderr。同一纪律的另一半：**这台机器上永远不要 `main(["--help"])`**——argparse 会把 `--to` 的默认值连口令一起打进 usage，那是一次对着 cp936 控制台的泄漏。
  - **对账是这一族唯一能看见「值被改写」的探测器**：一条用例造的目标库把 `tags.name` 声明成 `INTEGER`，插 `'007'` 时 SQLite 不拒绝、不报错，当场按类型亲和转写成 7——只有提交前那次读回来比摘要抓得住它，摘要一红整笔回滚、目标库一行不留，而源库那一行仍然是 `("text", "007")`。这是 #201 那条亲和事实的反向用法：那边是「数字塞进文本列」，这边是「文本塞进数字列」。
  - **`_orphans` 那句 `continue` 从接口够不着，只能直接敲纯函数**：父表压根不在这次范围内（`sessions`）就没有可比的那一侧，而今天没有任何模型指向 `sessions`，两条路都到不了；沿 #199/#201 的先例直接调用，同一段放正反对照——把 `continue` 改成往下走会当场 KeyError，而把父表取值那一步整个跳过，则会让一条真孤儿行安静搬过去，那才是新库当场拒收的现场。`by_name` 那句 `raise KeyError` 反过来用真报告敲得动：会话表是唯一一个「模型里有、报告里没有」的名字。
  - **文本主键那格只有「有行」才敲得动，这也是电池唯一等价那格的成因**：`settings` 是全族唯一主键为文本的表，而它平时是空的——空表在前一句就 return 了，所以「有行 + 文本主键」这个组合此前从未被敲过。把「不是整数主键就不拨」那道守卫摘掉整组照绿，因为两种方言上 `settings` 都没有序列可拨，这一格是20 格里唯一记名的等价变异。
  - **WARN 行是中文，而模块 docstring 说「命令行输出保持 ASCII」——半真**（量出来的差异，源码未动）：表格行（`videos  rows=2  digest=OK`）确实全 ASCII，告警循环打出去的却是中文。两条断言按现状分开钉（一行所有字符 < 128 / 另一行必须有 > 127 的字符），改哪一边留给面板。顺带钉住一个事实：真实老库跑`main()` **至少两句 WARN**——`sessions` 在 `SKIP_TABLES` 里，所以它永远会作为「不在搬运范围内」报一次。
- `src/db_audit.py` **268 句里 38 句未覆盖 → 1 句 → 266 句 0 缺（100%）**（#201，2026-10-10 PG 全量 1034 passed 时重量，TOTAL **98.11%**——4648 条语句 / **88** 未覆盖；这一族**不打库**——17 条新用例全部在 `tmp_path` 里现造 SQLite 文件，审计自己以 `mode=ro` 打开，SQLite 分支同日重测同一文件 **34 passed**，整跑 0.5 秒）——前九轮清单里最大的一份脚本（38 句）由 `tests/test_db_audit.py`（17 → 34 条）钉住，变异电池 **39 格：37 红、2 格等价**（那两格正是本文件最后那一句的成因，见下）。改这一族前值得知道六件事：
  - **「往一列里塞个数字」那几格只能借 DATETIME 或 JSON 列，这是量出来的不是试出来的**：SQLite 的类型亲和是「倾向」——VARCHAR/TEXT 列会把 12345 当场转成文本存着，审计读回来就是文本，一条也报不出来；而声明成 `DATETIME` 和 `JSON` 的列拿到的是 NUMERIC 亲和，整数和浮点**真以数字形状存着**，BLOB 则谁都不转。所以 `type_mismatch` 那句「存的是 整数」以前一次也没被敲过。这一格配了一条负对照（`test_affinity_hides_a_number_stored_in_a_text_column`，先断 `typeof(title) == 'text'`）：后来人把用例改成往 `title` 里塞数字，改完照绿，敲的却不再是同一条分支。
  - **收口是按「类别 × 表」记的，而那句「同类问题还有更多」继承阻断位**：一张表报满 5 条后第 6 条换来一句元行、第 7 条起一句不多，另一张表照样从头数。所以孤儿行那一族的总数是 3 + 5 + 1，而**阻断项条数 ≠ 出问题的行数**——用例把这三件事分开断。电池里对应三格：`>=` 改 `>`（红 2 条）、`== SAMPLES_PER_CHECK` 改 `+ 1`（元行永远不出现）、记数那一行不改（元行每行重复一次）。
  - **`_audit_table` 直接喂手搭的 `Table` 是这一族唯一的接缝**：复合外键（两列一起指过去）当前模型里不存在，被跳过的理由只能现造。三张形状完全一样的子表各钉一条跳过理由——两列的约束、父表名字不在模型里（库里那张 `legacy_parent` 实实在在存在）、以及对照组「单列且父表是模型认识的」照常报孤儿。跳过外键不等于跳过这张表：行还是数了、摘要还是算了，这两句也在同一条用例里断。
  - **一句 NOT NULL 的闸门故意保持安静**：模型里带默认值的 NOT NULL 列，如果库里那一列是漂移出来的可空列且存了 NULL，审计**不报**——「这行到底进不进得了 PG」由 `db_transfer._null_in_required` 逐表算，它对带默认值的列一样会报。这条分界现在被 `test_a_null_in_a_modelled_default_column_stays_quiet` 钉住（把 `and col.default is None` 摘掉当场红），否则同一件事会被两处报警。
  - **报告文件是 UTF-8、控制台必须是 ASCII，这两条是同一件事的两半**：本机控制台 cp936，`🚫` 打出去就是一次 `UnicodeEncodeError`。CLI 那格钉的是退出码 2（库不存在，且不落报告）、stdout 每一行所有字符 < 128、类别计数按 `CATEGORIES` 的次序、`blocking=` 只数阻断项（它 ≠ findings 总数）、报告默认按 `migration-audit-<日期>.md` 落在库旁边且是 UTF-8（去掉 `encoding="utf-8"` 会当场炸，因为报告里有 emoji）。空库那一格还钉了「九类都要有节，一类没报要写'无。'」——分节漏掉一类是这份报告最安静的坏法。
  - **电池那两格等价的，正是这个文件最后一句没法覆盖的原因**：`_audit_table` 里 JSON 检查的 `if isinstance(value, (dict, list)): pass` 那一支（309）在 sqlite3 这条路上永远走不到——它从不把 dict 还给你；把它改成 `if False:` 整组 34 条全绿，这就是「这句是死的」的量。同一个原因还有一格：`_is_type_violation` 里那句 `not isinstance(value, bool)` 排除（bool 不会是 sqlite3 读回来的形状），删掉也全绿。而 `canonical_value` 里那份一模一样的 JSON 判断**是活的**——`db_transfer.py:219` 从 PG 读回来的就是 dict。于是留过一个问题：**同一个决定写了两遍、其中一遍够不着**，是照现状留着并说明、删掉 `_audit_table` 那半，还是合成一处。**#206 按第三块面板⑨甲选了「删掉那半」**：`if isinstance(value, (dict, list))` 连同那句 `pass` 一起摘掉，JSON 检查塌成一句 `try/except`（266 句 0 缺）。没有合成一处——活的那半在 `canonical_value` 里干的是「把 PG 还回的 dict 归一成一个可摘要的形状」，死的这半只是「承认 sqlite3 不会还回 dict」，是同一段话的两种用途而不是同一段逻辑。`_is_type_violation` 里 `not isinstance(value, bool)` 那半句排除**照旧没动**：面板答的是「两处」，它不在其中。未覆盖 125 → **88**，此后只剩 `db_transfer.py`（24）和 `e2e_seed.py`（58）两份脚本，加 5 句三处（`api/users.py:155-156`、`video_service.py:404`、`tag_service.py:73-74` 零调用方——#205 已按第三块面板⑦甲删掉，此后这里少一处）。

- `src/models/` **整树 16 份模型文件（含 `models/__init__.py`）全部 100%**——那 17 处 `__repr__` 的 return 第一次被逐条敲到（#200，2026-10-10 PG 全量 1017 passed 时重量，TOTAL **97.31%**——4648 条语句 / **125** 未覆盖；这一族**不打库**——19 条用例全是内存里的实例，SQLite 分支同日重测 `tests/test_models` 30 passed）——前两轮清单里最大的一块（17 句）由新建的 `tests/test_models/test_model_reprs.py` 钉住，电池 **19 格全红、无一等价**（17 格各红 1 条，另两格是接缝空格与开头那个 `<`，也各红 1 条），测试文本定稿之后整跑两遍、逐格结果一字未变。改这一族前值得知道四件事：
  - **为什么用等式钉，而不是给这 17 行标 `# pragma: no cover`**：标 pragma 要说的是「没有测试够得着」，而这一行就是 `repr(Favorite(id=11, user_id=12, video_id=13))`——内存里一句，不碰库、不碰夹具，所以标它是**假话**。仓里唯一那处 repr 上的 pragma（`auth_service.py:426` 的 `LoginRateLimiter`）是另一种形状：它内插 `len(self._failures)`，值随测试推进漂，等式钉不住，那一句 pragma 是真话。同仓还为「口令不许出现在 repr 里」真调过 `repr()`（`test_backup.py:262`）——repr 是出问题时人唯一读得到的东西，有产口就值得钉。
  - **一格红 2 条，而第二签正是崩溃那一条**：`sorted(self.prefs)` 换成 `self.prefs`，同时红掉 `UserPreference` 的等式和那条 `TypeError` 用例——让未落库实例炸掉的正是 `sorted` 这一手。所以「顺手去掉 sorted」看着像修了个 bug，实际是把排序契约和崩溃记录一起抹掉，而这两件事在测试里各有各的名字。
  - **17 个值全取成互不相同**（11/12/13 那样），于是「把 `id` 写成 `user_id`」这类串字段当场红：17 条签名是 17 个独立把手，没有一条 repr 靠别人代签。两处不是「看不出来错」的形状各配一格：五个多行 f-string 的**接缝空格**（少一个空格就是 `user_id=7video_id=8`），和 `TranscodeOutput` 那个**字段叫 `target_format`、标签写 `format`** 的名字错位（把标签改成字段名红 1 条）。
  - **盘点与本轮待选清单第 8 项**（这个「第 8 项」是 #178 以来那份「还等用户选」清单的第 8 条，不是 2026-10-09 十三叉面板里那个已经答过的 ⑧）：`src/models/` 18 个映射类里 17 个写了 repr，唯一没写的是 `Setting`（`settings` 表）——它落回默认实现，含地址、钉不了内容，所以那条用例钉的是「它确实没有自己的 repr」这个事实，将来谁补上这条就红。另一半：`UserPreference.prefs` 的 `default=dict` 只在 INSERT 时生效，内存里刚 new 出来的实例上它是 `None`，于是那行**为调试而生的 repr 在调试现场 `TypeError`**；全仓唯一构造点 `preference_service.py:38` 永远显式传 `prefs`，线上走不到，源码因此原样不动。选项：`sorted(self.prefs or {})` 让它不吃 `None` / 照现状记着（今天的用例已经钉住现状）/ 连带给 `Setting` 也补上 repr。未覆盖 142 → **125**，此后只剩两个名字：三份迁移与播种脚本 120 句（`db_audit.py` 38、`db_transfer.py` 24、`e2e_seed.py` 58）+ 5 句三处（`api/users.py:155-156` 可推导地到不了、`video_service.py:404` 上面那条 SQL 已排除、`tag_service.py:73-74` 零调用方——#205 已按第三块面板⑦甲删掉，此后这里少一处）。

- `src/middleware/auth.py` **99% → 100%**（#199，2026-10-10 PG 全量 998 passed 时重量，TOTAL 96.94%——4648 条语句 / 142 未覆盖；这一族**打库**——五条用例都要真账号行和真会话，SQLite 分支同日重测同一组 168 passed）——缺的两句 `156, 190` 是两道**从 HTTP 走不到的保险**：中间件先答 401/403，所以 `get_current_user` 那句「行没了或已被停用」和 `require_role` 那句「角色不对」在接口那条路上永远撞不到。现在由 `tests/test_middleware/test_dependency_belts.py`（新建，5 条）钉住，电池 **9 格全红**（红 1、1、2、2、2、1、1、22、1）。改这一族前值得知道五件事：
  - **一句 `or` 里的两种形状各钉一次**：只删 `not user.is_active` 那半句红 1 条（停用），只删 `user is None` 那半句红 1 条（失踪），整道闸门改成永远不成立红 2 条。「一条断言盖不住两种形状」是 #196/#197 那颗「一颗常数签不了两种字节序」的设计搬到闸门上。
  - **#135 那次「删掉半句整套全绿」至今成立，这正是本单存在的理由**：外部那条路上「停用会切断会话」是删除会话那一半签的字，不是这道复查。`require_role` 更干净——它的**拒绝面此前零外部签字**：把角色闸门改成永远不成立（成员被直接交回路由）只红新加的那 1 条，20 条真请求一条不红；而把判断反过来红 **22 条**（`/api/users` 上挂着 `require_owner` 的那六条路由上 20 条真请求全红，另 2 条是本文件那一对正负对照）。放行面一直有人签，没人签的只有拒绝面，差 21 条是量出来的。
  - **两道保险对外各说一句话，状态码和文案分开断**：401 改 403 红 2 条，中文文案换掉红 2 条；403 改 401 红 1 条，把那句换成「未认证」红 1 条。`get_current_user` 回 401 说「未认证」，`require_role` 回 403 说 `_FORBIDDEN_OWNER`（「需要管理员权限」）——后者是常量，别在依赖里另写一遍。
  - **第三道保险照旧没摘**：`if user_id is None`（152-153）源码上挂着 `# pragma: no cover`，本单没有把它变成用例。它要的是「中间件根本没跑过」这种状态，而那条路上中间件必然先答 401；要钉它得先把那行 pragma 删掉，那是一次显式决定，不是补覆盖率。
  - **这一单把 #198 那份「四种补不了」改成三种**：当时记的理由是「走到就意味着上一层失效」——按 #165 / #172 / #178 的先例，走不到不是不钉的理由，直接敲依赖就够了。未覆盖总数 144 → **142**；剩下记明理由的是 5 句三处：`api/users.py:155-156`（可推导地到不了）、`video_service.py:404`（上面那条 SQL 已排除）、`tag_service.py:71-74`（`list_all` 全仓零调用方——#205 已按第三块面板⑦甲删掉）。其余 137 句仍是 17 处模型 `__repr__` 加三份迁移与播种脚本的 120 句（此记于 #199；那 17 句已由 #200 逐条钉住，未覆盖 142 → 125）。

- `src/services/favorite_service.py` **97% → 100%**、`src/services/notification_service.py` **98% → 100%**、`src/services/watchlist_service.py` **99% → 100%**、`src/api/watchlists.py` **99% → 100%**、`src/api/sources.py` **99% → 100%**（#198，2026-10-10 PG 全量 993 passed 时重量，TOTAL 96.90%；这一族**打库**——七条新用例全部从 HTTP 进来，SQLite 分支同日重测这四个文件 36 passed）——缺的五句 `66 / 131 / 129 / 125 / 90` 是五种互不相同的「这句话一次也没从接口走进过」：收藏那道重复闸门、标记全部已读那个**循环体**、片单改名时「说明单独给不给」那道闸门、路由里 `except DuplicateWatchlistNameError` 与 `except ValueError` 的**先后次序**、以及 `get_source_service` 那个**函数体本身**。现在由 `tests/test_api/test_favorites.py`（新建，2 条）、`test_notifications.py`（5 → 6）、`test_watchlists.py`（7 → 10）、`test_sources.py`（17 → 18）钉住，电池 **7 格全红、每格恰好红 1 条、无一等价**。改这一族前值得知道四件事：
  - **一格一还原**：电池第一版把「按 md5 还原源码」写在整批跑完之后的 `finally` 里，于是 M2 报的是「红 2」——它继承的是 M1 那格留下的红。改成每格跑完立刻还原并验 md5 之后，七格各自恰好 1 条。这条是流程约束，不是发现：还原是**每格**的收尾，不属于整批。
  - **M1 的失败形状不是 201 而是 500**：把 `if existing.scalar_one_or_none():` 改成 `if False:`，第二次 POST 并不会安静地多写一行，而是撞在 `favorites.user_id, favorites.video_id` 那条唯一索引上抛 `IntegrityError`——路由只接 `except ValueError`，接不住它。所以这条闸门对外同时钉两件事：**回答是 400**，以及**它挡在那次写之前**。
  - **被替身演掉是覆盖率上最难看见的一种绿**：`test_sources.py` 的夹具一直把 `get_source_service` 挂在 `dependency_overrides` 上，于是那句 `return SourceService(session)` **一次也没被执行过**，而文件照样报 99%——缺的正是那一行。能签字它的只有一条**先把那项覆盖摘掉**、走真依赖、并且断言响应里真的是库里那条片源（`[item["name"] for item in ...] == ["source-7"]`）的用例；只断 200 的话替身照样绿。
  - **清单到这里合上了**：这一单之后 `src/` 剩下的 144 句未覆盖全部有名有姓——17 句是模型里的 `__repr__`（此记于 #198；#200 已逐条钉住，见上面那条）、120 句在 `db_audit.py`（38）/ `db_transfer.py`（24）/ `e2e_seed.py`（58）这三份迁移与播种脚本里那些要真库真数据才走到的分支，其余 7 句是四种「补不了」并已各自记明理由：`api/users.py:155-156`（可推导地到不了——`require_owner` 先过 `get_current_user`，那里对禁用/失踪用户已经 401，自我停用另有 `:151` 那条 400）、`middleware/auth.py:156, 190`（两道纵深防御的保险，走到就意味着上一层失效——此记于 #198，#199 改为直接敲依赖后已钉住）、`video_service.py:404`（上面那条 SQL 已把 `file_size IS NULL` 排除）、`tag_service.py:71-74`（`list_all` 全仓零调用方：按 #189 先例删掉，还是接进某个接口，是产品形状——面板选了删，#205 已落地）。

- `src/services/subtitle_service.py` **97% → 100%**、`src/storage/local.py` **97% → 100%**、`src/api/subtitles.py` **99% → 100%**（#197，2026-10-10 PG 全量 986 passed 时重量，TOTAL 96.79%；新加的四条自己一条库也不碰——只算路径、读字节、喂 None——但它们所在的三份测试文件是打库的，所以 SQLite 分支同日重测 47 passed）——缺的三处是一句话的三个面：`_within` 那道「字幕必须在影片旁边」的闸门在 `commonpath` 回答不了的时候要说「不在里面」（`169-171`），本地读的那条生成器在字节跑完时要收住（`57`），序列化器在没有创建时刻时要照实回 null（`58`）。现在由三份用例钉住（`tests/test_services/test_subtitle_service.py` +2、`tests/test_storage/test_local_storage.py` +1、`tests/test_api/test_subtitles.py` +1），电池 **6 格 = 5 红 + 1 格实测等价**。改这一族前值得知道三件事：
  - **同一支要两种形状**：`commonpath` 抛 ValueError 在生产里靠的是跨盘符（`C:\media` 对 `D:\shows`），而那一种只有 Windows 有；所以还配了一条在任何系统都抛的形状（一边绝对、一边相对混着写）。**边界说清楚**：混着写那条钉的是这一支的行为，不是那句注释点名的形状——一台只有一个盘或 POSIX 的机器上，盘符那一格只会 skip，注释里那句话就没人重新证过。
  - **M6 的爆炸半径是这一族最大的一格**：把 `== root` 反过来红 **14 条**（add/register/stream 一大家子都从这道闸门过），而把同一支换成 `return True` 只红新加的那两条——因为其余用例从没把字幕放到别的盘上。「一道闸门站着多少人」和「这一支有没有人签」是两回事，量出来才知道差 12 条。
  - **一格如实记为等价**：把 `break` 换成 `return` 全绿——在这条生成器里两种写法都是「就此结束」。这不是漏测，记下来只为别让下一个人以为那一格上有钉子。

- `src/utils/subtitles.py` **98% → 100%**（#196，2026-10-10 PG 全量 982 passed 时重量，TOTAL 96.71%；这一族**不打库**——用例只看文件名与字节头，SQLite 分支同日重测 36 passed）——缺的三句 `82, 211, 213` 是两处「一个元组里两颗常数各管一种字节序」和一个目录：`if not entry.is_file(): continue` 那道闸门、`startswith((b"\xff\xfe", b"\xfe\xff"))` 那对字节顺序记号、记事本另存为 UTF-8 那个必须吃掉的记号。现在由 `tests/test_utils/test_subtitles.py`（32 → 36 条，函数 32 → 35、其中一条 parametrize 两格）钉住，电池 **5 格全红、无一等价**。改这一族前值得知道三件事：
  - **「一颗常数签不了两种字节序」**——#194/#195 那条设计的第三次兑现：LE 与 BE 各一颗常数、parametrize 各一格。拿掉 LE 那颗只红 `bom-le`，拿掉 BE 那颗只红 `bom-be`。
  - **这一族的签字是等号，不是「读得出来」**：删掉 211 那一支之后，BOM-less 那半圈的 NUL 率猜拳照样能猜中同一种字节序，只是把 BOM 那两个字节本身解成开头一个 U+FEFF（LE/BE 两格实测都是这一个字符）。断「文本里有那句中文」在这一格上是**绿**的，只有 `read_subtitle_text(...) == body` 会红。
  - **82 那句 `continue` 是目录名唯一的出路**：叫 `movie.zh.srt` 的目录照样被 `os.scandir` 列出来、后缀照样合格。两种改法的宽度差七条——`continue` 换成 `pass`（闸门不跳过）恰好红 1 条，把 81 那道闸门整个反过来红 **8 条**（七条发现用例加这条新的）。

- `src/storage/s3.py` **95% → 100%**（#195，2026-10-10 PG 全量 978 passed 时重量，TOTAL 96.64%；这一族**不打库**——moto 在进程内截 botocore，SQLite 分支同日重测 40 passed）——缺的五句 `95-96, 180, 214-216` 是三道方向相同却互相顶的闸门：它们都在说「读不到」，可「读不到」分别是**没装依赖**、**权限不够**、**读到一半断了**。现在由 `tests/test_storage/test_s3_storage.py`（10 → 14 条）钉住，电池 **7 格全红、无一等价**。改这一族前值得知道四件事：
  - **moto 造不出这三格**：它按 S3 契约好好回答问题，而这三条要的是「包不存在」「权限被拒」「读一半断开」。于是用例走两条替身缝——`sys.modules["boto3"] = None` 让 `import boto3` 抛 `ImportError`（在一台**装了** boto3 的机器上，这是够到那一格的唯一办法），以及把 `_client` 换成 `SimpleNamespace(head_object=…, get_object=…)`。**签名的是闸门说什么，不是闸门会不会被撞到**：真机上 MinIO/RustFS 究竟回 `AccessDenied` 还是别的码，仍然没被证过——这一族的边界和整个 moto 用例集的边界是同一条。
  - **`size()` 那句 `raise` 是 `exists()` 的靠山**（`exists` 就是 `size(locator) is not None`）：把 180 换成 `return None`，或者往 178 那份「没找到」名单里多收一个 `AccessDenied`，红的都是同一条用例的两个断言。反过来 170-173（凭证没配好 → `None`）和 178-179（对象真没有 → `None`）**必须**继续是 `None`，否则每部挂在对象存储上的影片都要抛 500。这一族里「什么时候不许说没这个文件」是唯一的主轴，读代码时别把两处 `return None` 当成同一个意思。
  - **那颗 `RuntimeError` 是刻意和 `ClientError` 一起上的**（`edge_fingerprint` 那条 parametrize 两格）：M7（`except Exception` 改窄成只接 `ClientError`）只红 `anything-else` 那一格，M6（改成一个永远等不到的异常）两格都红——#194 那条「一颗异常签不了两种宽窄」的设计在这里兑现了。这条用例还**必须**断 `calls == ["head", "get"]`：凭证没配好时 `size()` 自己就回 `None`，那条路整块指纹对象都没去读，而 `is None` 那句照样成立（本单第一版就差点绿在这里）。
  - 电池里只有一格不是「恰好红一条」：**M3（把 `reachable` 那句 `except UnsupportedStorageError: return False` 拆掉）红 3 条**——新加的那条加上 `test_missing_credentials_are_unreachable_not_an_error` 和 `test_bucket_without_credentials_is_not_read_as_emptied`。这不是漏测，是那一格今天就有两个人签字，记下来只为别让下一个人以为红一条是常态。
- `src/scheduler/tasks.py` **93% → 100%**（#194，2026-10-10 PG 全量 974 passed 时重量，TOTAL 96.54%；这一族四条用例**打真库**，SQLite 分支同轮重测 32 passed）——缺的四句 `44-45, 69-70` 是同一道闸门抄了两份：`scan_source_task` 与 `scan_all_active_task` 各有一份「失败通知自己也写不出去」时的 `except Exception` + `logger.exception`。备份那一族早有同形状的一条用例，扫描这两路此前一条都没有。现在由 `tests/test_scheduler_scan.py`（2 → 4 条）钉住，电池 **7 格里 6 红 + 1 实测等价**。改这一族前值得知道三件事：
  - **断言要分两半钉，否则绿的是假的**：「`await` 没抛出异常」只签字那个 `try/except`；**日志里那两句话**加上 `exc_info` 里那颗异常类型才签字 `logger.exception`。只断前一半的话，把 `logger.exception` 降级成 `logger.error`（回溯就此丢掉，人再也看不出通知是怎么没写出去的）甚至整句删掉，用例照样全绿——而行覆盖对这两种改法**天生**不敏感，那一格无论如何都被走到了。这是 #178 那条「行覆盖 100% 和这一行有签字是两件事」的第二份证据，而且不用实测就能先验地断定；M3 / M4 两格实测各恰好红一条。
  - **两条用例挑的失败原因刻意不一样**：单源那格用 `PendingRollbackError`（真机上就是这颗：扫描死在 `flush()` 上、会话带着 PendingRollback 回来，紧接着的 INSERT 只会再抛一次），全量那格用 `OSError`（磁盘满了那一类，不在 SQLAlchemy 的层次里）。于是把两颗挪到任意一边、或把任何一格闸门改窄，都只会红其中一格（M5 改窄单源、M6 改窄全量，各红对应那条）。**诚实记录 M7**：把全量那格改成 `except OSError` 是全绿——那一格今天的异常恰好就是 `OSError`，一颗异常签不了两种宽窄，这不是漏测，别再为它找输入。
  - **「任务被永久移除」是假的，本单量过之后改口**：APScheduler 3.11.3 实测一条每秒触发的 cron job、函数每次都抛，3.2 秒里照样跑了 3 次、任务还挂在调度器上、`next_run_time` 也留着；`src/` 里没有任何 `add_listener`，没有东西在摘任务。这道闸门真正守的是两样：**任务对外承诺不抛**（今天只有调度器在兜，将来任何人直接 `await` 它——比如手工触发——就会拿到一个 500），以及**日志得说是哪一步炸的**（冒出去只剩 `Job "…" raised an exception`，分不清是扫描没跑成还是那条扫描通知没写出去）。`tests/test_scheduler_backup.py::test_a_notification_that_cannot_be_written_does_not_kill_the_job` 的注释原先按「永久移除」写着，本单一并改成实测口径。
- `src/utils/name_parser.py` **93% → 100%**（#193，2026-10-10 PG 全量 972 passed 时重量，TOTAL 96.45%；这一族用例**不打库**——测的是纯字符串解析，所以 SQLite 分支与它无关）——先前缺的五条语句 `57, 108, 112, 138-139` 分三件事：`57` 是 `episode_label` 在“没有集数”时那句早退、`108` 是找组名时“方括号里只剩空串或纯数字就跳过去”、`112` 是“候选组名长过 30 就跳过去”、`138-139` 是 `_number` 那句 `except (IndexError, ValueError, TypeError)`。现在由 `tests/test_utils/test_name_parser.py`（13 → 18 条，**#207 之后 20 条**）钉住，电池 **6 格里 5 红 + 1 等价**（#207 那一单的 8 格全红，见上面那一条），而那格等价不等实测就能证。改这一族前值得知道四件事：
  - **108 那条 `continue` 是永远红不了的格子，理由是结构性的**：任何让它成立的候选串（空串，或 `isdigit()` 全真的串）都必然过不了循环末尾那道“必须含一个拉丁字母或汉字”的检验，删掉它换不来任何可观察差别（M2 全绿，18 条）。全角数字与带圈数字都算 `isdigit()`、也都不在那道字符类里，所以这条证明不依赖某一颗输入。留着它的价值是把意图写在前面——别读成它挡过什么，也别再为它找用例。
  - **同一个数字、两种单位**：`112` 的上限数的是**字符**，不是字节也不是显示宽度。M3（删掉这句）红的是 ASCII 那格（37 个字母的组名被收下），M4（改成按 UTF-8 字节数算）**只**红中文那格（27 个汉字 = 81 字节，今天仍然当组名用）。这是本单量到的唯一“规则与直觉分叉”处：真实中文字幕组名不会长到 27 个汉字，所以它更像单位口径问题而不是缺陷——要不要按显示宽度封顶，留给面板，本单没动源码。**第三块面板 ⑥ 用户定了甲，#207 已把这一格的上限从字符改成显示列宽**（阈值仍是 30，只是量的是列），所以上面那句「27 个汉字今天仍然当组名用」到此为止是历史——M4 那一格（按 UTF-8 字节数算）也随之失去意义：字节、字符、列宽三种单位里今天用的是第三种，改前改后各红哪几格记在本文件 #207 那一条里。
  - **`57` 钉的那个属性今天在全仓零调用方**（census）：`episode_label` 在 `src/` 里没有任何读者——扫描只读 `series` / `season` / `episode` 和 `auto_tags`（`scan_service.py:164-171`），而前端那枚角标是把同一条三分支规则**自己写了两遍**（`VideoCard.vue:50-54`、`Home.vue:90-93`）。删它（#189 先例：零调用方的 `get_video_info` 是用户点头才删的）还是把它接进接口让前端只算一遍，都是产品形状的选择，留给下一块面板。**面板 ⑤ 已定甲（接进接口、前端只算一遍），落在待办的 #209**；#207 只换了上限的单位，这个属性和那两处前端副本都原样没动。
  - `138-139` 从 `parse_video_filename` 走不到（结构性理由：调用点先算 `has_season = "season" in match.groupdict()` 才敢问 `season`，而 `episode` 那一支每条模式都有），按 #165 / #172 / #178 的先例由用例直接敲 `_number` 那一层钉它。这一族的电池里它有两格签字（M5 删整个 try、M6 只从 `except` 拿掉 `IndexError`），两格都只红这一条。
- `src/utils/video_search.py` **96% → 100%**（#178，2026-10-10 PG 全量 967 passed 时重量，TOTAL 96.34%；这一族用例**不打库**——测的是纯字符串解析，所以 SQLite 分支与它无关。#204 依用户定夺①甲改了源码，重量时 PG 全量 **1054 passed**（#204 当时记的 1053 是错的，#205 复核并更正：那一单把这一族从 20 条改成 22 条，而 #203 的 1052 至今自洽——静态收集 1054、全量 1054，中间 `backend/tests` 零改动），这一文件 **127 句 / 0 缺**——比 #178 那 126 句多出的正是新增的 `OPERATOR_CHARS` 常量一行，TOTAL **99%**（4649 句 / 46 缺））——先前缺的五条语句 `129-130, 170, 187, 212` 全在"搜索框里那颗认不出来的 token 怎么办"这一族里：`129-130` 是光杆一个引号（`_TOKEN` 那条"或者一颗非空白"的分支允许 `"` 自己成一个 token，剥掉引号就成了空串）、`170` 是 `标签:` 后面紧跟的只剩一个孤立引号、`187` 是空格把比较式拆开时"尾巴不像数字就停手"那句 `break`、`212` 是"要键却没键"那道闸门。现在由 `tests/test_utils/test_video_search.py`（15 → 20 条；#204 之后 22 条）钉住，电池 **6 格里 4 红 + 2 实测等价**。改这一族前值得知道四件事：
  - **一次被拒绝的比较式从不留下痕迹，这是这一文件里"绿"和"钉得住"分得最开的地方**：`_assign_comparison` 返回 0 时 `_consume` 一律返回 None，外层循环于是**重新吐出原始 token** 并只前进一格——`buffer` 中途吞了什么、`position` 走到哪一格，全都丢掉。所以"187 那句 `break` 拆掉"在多数输入上没有任何可观察差别：`评分 abc` 拆不出它（M3 那格 20 条全绿），能钉住它的只有"这颗尾巴单独不成比较式、拼上去恰好成一条合法比较式"的形状，今天量到的是 `评分 >=4`。同理两处闸门是**等价变异**，别读成有签字：`_looks_like_comparison_tail` 里"缓冲里已经有这个运算符就不许再吞"那半句（M4 改成永远放行 → 全绿），以及尾巴"认小数点开头"那半句（M6 只认数字开头 → 全绿）。
  - **`212` 从 `parse_video_search` 走不到**（结构性证明，不是"没找到输入"）：`require_key=True` 只在 `_consume_comparison` 里出现，而能进那个函数的 token 必然整颗匹配过 `_STANDALONE_COMPARISON`，也就是它本身就是一颗比较键；`buffer` 又从它开头只往后续，所以匹配到的键永远在 `COMPARISON_KEYS` 里。按 #165 / #172 的先例，用例直接敲 `_assign_comparison` 那一层钉它，值用的是 `">=1.5小时"`：今天回 `0` 且 `fields` 一个键都不写，把闸门拆掉它会写进 `{'duration': ('>=', 5400)}`。**这颗值必须是带单位的那种**——`">=4"` 无论 `require_key` 取哪一边都不写任何东西（裸数字在没有键时不算时长），拿它做对照会得到一个假绿。
  - **本单量出的洞（第三块面板①甲，#204 已落地）：空格位置不对，整条筛选静默失效。** 当时实测五格（`parse_video_search` 的返回值，rating 与 duration 全为 None）：`评分 >= 4` → `('评分', '>=', '4')`；`评分 >=4` → `('评分', '>=4')`；`评分>= 4` → `('评分>=', '4')`；`rating >= 4`、`时长 >= 90` 同形。认得出的只有两种：运算符两侧**都不空**（`评分>=4`），或两侧都空而运算符是**单字符**（`评分 > 4`、`评分 ≥ 4`）。根因是那张运算符表在正则里的回溯：`_COMPARISON.match('评分>=')` 在 `>=` 后面要不到值时退到单字符运算符 `>`，把 `=` 当成值，于是 `_consume_comparison` 在"buffer 已经像一条比较式就收口"那一句提前 break，拿着一个假值 `'='` 去登记，登记被拒 → 上面那半句丢掉痕迹 → 用户那条筛选没了。**为什么这条不是边角输入**：`parse_video_search` 自己的 docstring 明写着"spaces around ``:`` and around an operator are ignored, so ``标签: 悬疑`` and ``评分 >= 4`` parse as intended"——那时它是假话。对照 `时长 <= 30秒` 却是**对的**（`('<=', 30)`），那是同一族里的偶然两段式：键那一轮被拒之后 `<=` 自己又进来一轮，这次值带单位所以登记成功；不带单位的 `时长 >= 90` 照样失效。用户选**甲**（修解析器），四条预备改法里否掉了"只把 docstring 改口"。
  - **#204 的源码改了三处，另有一句原样保留，改这一族前按这个清单读**：① 新增模块常量 `OPERATOR_CHARS`（运算符用到的字面字符），`_COMPARISON` 的**值**那一支改成不许以这些字符开头——这一句直接掐死"`>` 把 `=` 当值"的回溯；② `_STANDALONE_COMPARISON` 加上"键 + 运算符但还没值"这第三种形状，否则 `评分>= 4` 的前半截被当成关键词，后面那颗 `4` 再也拼不回去；③ `_looks_like_comparison_tail` 认"运算符打头的片段"（`>=4`）而不只认整颗运算符，并只允许出现一次。**原样保留的是那句 `break`**：它的前提（"buffer 已经像一条完整比较式"）到这一单才真的成立。**但面板上选的 甲（"只有真的登记上了才收口"）单独不够，这一条是量出来的**：把 甲 单独打在改前源码上（Temp 里现造一份只改这一句的模块，head / 只改甲 / 最终版三份对照同一批输入），`评分 >= 4`、`rating >= 4`、`时长 >= 90` 三格当场好，`评分 >=4` 与 `评分>= 4` 照旧失效——前者卡在尾巴只认整颗运算符，后者卡在"键+运算符只差值"不被认成半个比较式。所以落地的是 甲 的目标 + 乙 的机制 + 那两处形状；若哪天要把 甲 的机制也写进源码（给 break 再加一道登记判据），那是口径，回面板。**电池 8 格：5 红、3 格等价**——红的是值那一支的字符类（旧 `\S+`）、`OPERATOR_CHARS` 里漏掉 `=`、闸门少第三种形状、尾巴只认整颗运算符、`allow_bare` 松开；等价的三格都值一句：运算符表改成短的先排**全绿**（"先试最长"从来不是保险，保险是值那一支），运算符与值之间那段允许空白删掉**全绿**（空格在拼 token 时就被消掉，不进正则），"缓冲区已有运算符就不许再吞"改成永远放行也**全绿**（被拒绝的比较式从不留痕迹，这句只是把语义写明白，别当守卫信任）。**翻掉的一条用例**：`test_a_space_before_the_operator_still_drops_the_filter` 钉的是当时的实测行为，随这一单删掉，换成 `test_spaces_on_either_side_of_an_operator_keep_the_filter`；上面 #178 那句「去掉 187 的 break → 只有 `评分 >=4` 红」**因此不再成立**。负对照两条（`评分 4`、`评分 >= >= 4`）钉的是"没写运算符就不许凭空造出一条筛选"。
- `src/services/video_service.py` **98% → 99%**（#177，2026-10-09 PG 全量 931 passed 时重量，TOTAL 96.03%；SQLite 分支同轮 **930 passed + 1 skipped**）——缺的六句是 `114-115, 382, 402, 406, 634`，分属三个真行为，共同形状不是"哪条分支忘了测"，而是**磁盘配合、预算够花、影片还在**这三个前提从来没被同时打破过：`114-115` 是封面被别的句柄攥住时那句兜底（此前删影片的用例全是"磁盘配合"的场景）、`402`/`406` 是重复检测的读取预算（`_DUPLICATE_PROBE_MAX = 300` 趟）装不下某一整组时那句 `continue` 和它换来的空返回、`634` 是给一条已删影片报进度时那句早退。现在由 `tests/test_services/test_video_service.py`（38 → 45）和 `tests/test_api/test_videos.py`（29 → 30）补 **8 条**，变异电池 **13 格里 12 红 + 1 实测等价**。改这一族前值得知道：
  - **本单量出的洞（第二块选项板①甲，#179 已落地）**：`POST /api/videos/{id}/progress` 从前对一条已经不存在的影片回 **200 `{"status":"ok"}`**，而隔壁 `/play` 同样情况回 **404**（`api/videos.py:283-287` 接 `ValueError`，`290-299` 什么都没接）。播放器每几秒报一次、离开页面再报一次，删片恰好发生在中间。用户选**甲**：`update_progress` 看不见影片时 `raise ValueError`，路由接成 404，改动面就是量过的那 2 个文件。当时那两条钉现状的用例翻成 `test_a_progress_report_for_a_video_that_is_gone_raises_and_writes_nothing` 和 `..._answers_404`；电池 **W12 就是这条的最小预备 fix**，实测红恰好这 2 条、其余 73 条不动。落地后新量到的一条值得记住：这个 404 对用户**无声**——`VideoPlayer.vue:294` 是 `updateProgress(...).catch(console.error)`，而 `api/client.ts` 的拦截器只 reject 不弹提示，所以别给它补一条 toast。
  - **`382` 是类型钉子，不是漏测**：`if video.file_size is None: continue` 运行时走不到（上面那条 SQL 已经 `WHERE file_size IS NOT NULL`，`NULL IN (…)` 永远不为真）。实测两半——删掉这两行 75 条**全绿**，`mypy src` 从 34 涨到 **35**（`Argument 1 to "setdefault" ... incompatible type "tuple[int | None, int | None]"`）。所以这一文件落在 99% 是量出来的上限，别再为它找用例。
  - **`delete_generated_files`（#185 前叫 `delete_cover_files`）的两道闸门各挡一样东西，不是重复**（W13 实测红 5，我原先预测它等价）：级联清单那句 `if path` 挡的是 `None`（没封面的影片行 `thumbnail_path` 就是 `None`，而 `os.path.isfile(None)` 直接 `TypeError`），函数里的 `isfile` 挡的是"路径像样但文件已经没了"（老行那种 `./data/...` 前缀）。去掉任何一道都有一头露出来。
  - **读取预算在返回值里看不出来**：读满 300 趟和一组都没读，接口回的是同一个形状，所以只能量"到底读了几趟"——`_counted_fingerprints` 把模块里的 `fingerprint` 换成记账包装，**照样真调原函数**（#172 的教训：替身不许把要测的东西演掉）。计数一律从 `_DUPLICATE_PROBE_MAX` 推，不写死 300。
  - **封面那条是真造出来的失败**：`open(cover, "rb")` 攥着不放，`os.remove` 在这台机器上真回 `PermissionError [WinError 32]`（`chmod` 只读换来的是 winerror 5）。断言是三件事同时成立：行没了、文件还在、日志恰好一条且 `exc_info` 带着回溯。
  - **`634` 这一句承重，但 #177 给的理由要更正**：W11（拆掉这一句）当时记的是"PG 当场外键违例"，那是**推理不是重测**。#179 之后我把同一拆法重新跑了一遍：仍是红 2 条（服务层那条 + 接口那条，接口的 404 变成 500），可先炸的是第 639 行 `is_completed(progress, video.duration)` 的 `AttributeError: 'NoneType' object has no attribute 'duration'`——外键那一段（`_get_or_create_history` 插一条指向不存在影片的 `PlayHistory`，PG 违例、SQLite 也违例因为 #161 起连接上开着 `PRAGMA foreign_keys`）确实还在，只是被这句属性错误挡在后面，从来没有真的执行到。写在这里是因为**这正是"两种方言都承重"这类话最容易混进去的地方**：闸门挡住的东西要重新量，别顺着上一轮的说法抄。
  - **唯一红不了的格子是 W08**（拆掉 `if not probed: return []`，全绿）：`attach_watch_progress` 对空列表自己早退、`asyncio.gather()` 空参数回空、末句 `return groups` 也是 `[]`——三个理由叠在一起。
  - **换行**：`src/services/video_service.py` 在工作树里是 **CRLF**（#188 之后 671 CRLF / 0 lone LF，md5 `3404c33435db799f7ef8df1332b412af`；#179 时 649 / `bc494b5d4735b423fe64b1d7f5949b8c`，#177 时 645 / `a8bdf05149bfaed0e01baf93592b4fc9`），字节级改这一文件时锚点要按它自己的换行归一。**这一文件的锚点现在有一处会撞**：`update_progress` 与 `record_play` 的 `video = await self.get_video_by_id(...)` + `if not video:` + `raise ValueError(f"视频 #{video_id} 不存在")` 三句逐字相同（#179 之后才相同的），要改其中一处必须带上下文行做锚点。
- `src/services/scan_service.py` **96% → 100%**（#176，2026-10-09 PG 全量 923 passed 时重量，TOTAL 95.92%；SQLite 分支同轮 **922 passed + 1 skipped**）——缺的 7 句是 `183-184, 238-239, 331-333`，共同形状不是"哪条分支忘了测"，而是**一轮扫描的两种"半途"从来没被演过**：中途有人按停止（文件那一圈的闸门）和一个文件写库写坏了（每个文件外面那圈 `except Exception` 加它自己的 SAVEPOINT）。`183-184` 是 `is_scanning` 属性的函数体——进度接口读的是那张字典，这个属性零签字。原先唯一那条停止用例把 `scan_source` 整个换成替身，钉住了"剩下的**源**被跳过"，代价是"文件那一圈也认停止"和 `outermost` 那道闸门各自零签字。现在由 `tests/test_services/test_scan_service.py` 补到 **41 条**（本文件 33 → 41；连同 `tests/test_api/test_scan.py`、`tests/test_storage/test_scan_through_seam.py` 单跑时这一文件 196 句 0 缺），变异电池 **14 格里 13 红 + 1 实测等价**。改这一族前值得知道：
  - **本单量出的洞一（第二块选项板②甲，#182 已落地）：半途停掉的一轮不再写 `last_scan_at`。** 从前循环 `break` 之后 `source.last_scan_at` 照写、通知照发「视频源 X 扫描完成，发现 N 个新视频」，而清单里剩下的文件一个都没打开过——这一列是自动扫描（#150 那条链路）排下一轮的依据，记了时间就是宣布扫完了。用户选**甲**（停掉的那一轮不写时间戳），否掉的是"照写但通知改口"和"只在 docstring 承认近似"。今天留下的形状：`if not _scan_state["stop_requested"]` 只包住那一句赋值，**丢失核对和通知照旧**（清单是完整的，少的是处理；V11 那条钉子仍然成立——按了停止不许把没来得及扫的行刷成「已找不到」）。后果他也认了：手动停止之后源详情页那个"上次扫描时间"保持旧值，自动扫描因此更早重试。钉这一条的是 `test_a_stop_mid_source_leaves_the_rest_of_the_listing_alone` 末尾那句断言（从前断的是 `is not None`，V12 量过：翻转它恰好红这一条，其余 40 条不动）。
  - **本单量出的洞二（第二块选项板③甲，#183 已落地）：兜底现在两半圈都护。** 老片走 `known is not None` 那一条，它同样调 `_register_subtitles`，但那一句从前在 `try` **外面**（`try` 从新片那一段才开始）——新片坏了只是跳过，老片坏了整轮死：手动按钮那一路是一个 500（`api/scan.py` 只把 `ValueError` 映射成 404），定时那一路由 `scheduler/tasks.py` 的 `scan_error` 通知兜着。#183 把那半圈套进同一形状。**闸门是成对的，这一点别拆开看**：`except Exception` 只接住异常，真正不留脏写的是它里面那层 `begin_nested()`——只加前半句，老片那半圈写坏的字幕行会跟着这一轮最后的 `commit` 进库，再被同一轮的 `prune_missing` 判成「字幕文件已不存在」（今天这条红的就是通知那句多了这一段）。用例改名成 `test_a_known_videos_subtitle_failure_skips_only_that_one_row`（从前那条叫 `..._still_takes_the_round_down`，钉的是不对称的现状、断言它抛），电池 **V13** 是这一步的最小版；真字幕注册今天只做 add/flush、炸不出来，所以坏输入是假体喂进去的。
  - **`continue` 那一句是结构性等价（V05 全绿）**：它是循环体的最后一句，删掉与留着走到的是同一个循环末尾，所以这一格没有任何用例能红。真正有签字的是它上面那句 `logger.warning`（V06 红 1；用例断言 `record.exc_info is not None`，回溯丢了运维就只知道"跳过了"）和那层 `begin_nested`（V07 红 2：拆掉后半截行留在库里，下一轮把它当"已认识"永远跳过）。
  - **`_tracked_scan` 的 `outermost` 闸门两头各有钉子**：进场那一次重置挡住"按钮按早了把之后每一轮掐死"（V08 红 1），收尾只看 `outermost` 挡住"内层扫描把停止请求抹平、只停了一半"（V09 红 1）；收尾整块删掉红 6 条（V14），因为界面会永久卡在「正在扫描」，而 `POST /scan/stop` 救不回来。
  - **停止那一轮的 `files_found` 是清单数而不是处理数**（3 对 1），丢失核对用的同样是整份清单——所以按了停止不会把没来得及扫的行刷成「已找不到」（V11 改成不看清单红 8 条，其中 7 条是既有的核对/通知用例）。
  - **换行**：`src/services/scan_service.py` 在工作树里是 **CRLF**（#183 之后 454 CRLF / 0 lone LF，md5 `215077e4847669361979a2f3324ec7f5`；#182 时 444 / `ffd184c2614a0676507056f6321b3ec4`，#176 时 442 / `dd796a8f65a9a96364dbde447e10c4c7`），字节级改这一文件时锚点要按它自己的换行归一。**这一句在文件里有两处**（老片圈 #183 之后新增、新片圈原有），两处缩进不同（老片圈 24 个空格、新片圈 20 个），带先导空格的整行锚点分得开；只截 `async with self.session.begin_nested():` 那一段则命中两次——第一次跑电池就栽在这里（`anchor_count=2`，靠断点挡住才没跑错格子）。
- `src/utils/media_streams.py` **92% → 100%**（#175，2026-10-09 PG 全量 915 passed 时重量，TOTAL 95.77%；SQLite 分支同轮 **914 passed + 1 skipped**）——缺的 5 句是 `57-58, 66, 176-177`，共同形状不是"某条分支忘了测"而是**"探针跑不起来 / 输出不是预期那样"这一族从来没被演过**：`57-58` 是 ffprobe 回半截 JSON 时"当作读不出来"的兜底，`66` 是一条连 `tags` 都没有的轨（`65` 那个判断早有分支经过，缺的是它的 `return`），`176-177` 是提取时 ffmpeg 起不来 / 挂住 / 被拒绝。原先 10 条把 `subprocess.run` 换成替身演的是顺利那一路，argv 钉住了，代价和 #174 同形：**发出去的 `timeout` / `encoding` / `errors` 一格签字都没有**，两处异常元组里也只有 `FileNotFoundError` 一支被真抛过。现在由 `tests/test_utils/test_media_streams.py` 补到 **21 条**（#184 之后；替身记下 kwargs，并把喂进去的异常实例当作子进程真坏了往上 `raise`），变异电池 **17 格里 14 红 + 3 实测等价**。改这一族前值得知道：
  - **两处 `except (FileNotFoundError, subprocess.TimeoutExpired, OSError)` 的承重不均**：`FileNotFoundError` 和 `PermissionError` 都是 `OSError` 的子类，从元组里单独摘掉 `FileNotFoundError`（探测、提取各一处）实测**全绿**——Y11 / Y14 两格。有签字的是 `OSError`（Y10 红 2 条、Y13 红 1 条）和 `TimeoutExpired`（Y9 / Y12 各红 1 条）。别把这一格读成"三个成员各有钉子"。
  - **`text=True` 在这一文件里同样是等价参数**（Y8 全绿）：#174 的 Z4 同一族，`encoding="utf-8"` 一在，CPython 的 `subprocess` 就进文本模式。所以 kwargs 那条钉子**刻意不断言 `text`**，写了只会让人以为它有签字。
  - **本单量出的洞（第二块选项板④甲，#184 已落地）：探不到 ≠ 没有这条轨。** 从前 ffprobe **自己**跑不起来或非零退出时，`_run_ffprobe` 回 `{}` → `wanted` 是空集 → 接口说的是「文件里没有编号为 N 的字幕轨」并回 404：**真原因（工具没跑成）被换成了一句关于这部片子的假话**，而它恰是用户听得见、也修得了的那一句；对照 #142，外挂那一路后来把 ffmpeg 的原因带上了，这一路没有。#184 加 `ProbeFailedError`，`_run_ffprobe` 的三条出口（子进程抛 / 非零或空输出走 `ffmpeg_stderr_reason` / JSON 解不开）各 raise 一句，`extract_subtitle_webvtt` 让它穿出，路由在 `StreamNotFoundError` 之前 `except ProbeFailedError → 503`。用户选**甲**（分开说），状态码由第二块小板选**503**（否掉的是 415 和"仍 404 只改文案"）。`probe_streams` 仍然自己吃掉这个异常回 `probed: False`——详情页本来就有那个形状、端点照样 200，两边不同处理是刻意的。**`StreamNotFoundError` 从此只在真读到过清单时才发**（`extract_subtitle_webvtt` 开头那句 `os.path.isfile` → 404「视频文件不存在」仍然是真话）。电池 **Y17 是这一步的最小预备 fix**，当时红的那两条正是这两条；#184 的电池 **Z1/Z2/Z5 各红 1 条**（三条 raise 一枝一格，互不通用）、**Z3 红 4 条**（拆掉 `probe_streams` 那个 `except`）、**Z4 红 1 条**（503 改成 404）。接口那条 503 用例是在路由上 patch `extract_subtitle_webvtt`，所以状态码这一格签的是路由而不是工具层。
  - **语言标签有四个口子，两两不通用**：`""` 在 `tags.get("language") or tags.get("LANGUAGE")` 那一步就是假值（走 `65-66`），只有 `"  "` 能活到 `68` 撞集合里那个 `""`（Y3 只红空白那条）；`und` 与 `xxx` 是两个成员、各被一条独立用例撞（Y4 / Y5）；大写字面 `LANGUAGE` / `TITLE` 此前全库零签字（Y15 / Y16 各红 1 条）——打包器只写大写键时那一半是唯一读得出轨名的地方。
  - **测量到但选择不钉**：ffprobe 若回一段**合法但不是对象**的 JSON（`[]` / `null`），`probe_streams` 会把 `AttributeError` 送出接口外。真 ffprobe 带 `-print_format json` 不这样回，钉它只会留一条永远红不了的用例。
  - **换行**：`src/utils/media_streams.py` 在工作树里是 **CRLF**（#184 之后 205 CRLF / 0 lone LF，md5 `c01498826b252e6e612c733265a387ae`；#175 时 182 / `b7e76de876ad8a05db2351dfe4c4c462`），字节级改这一文件时锚点要按它自己的换行归一。同单的落点 `src/api/subtitles.py` 是 **纯 LF**（#187 之后 224 lone LF / 0 CRLF，md5 `831111e64e2b387ba720d67014fb1eca`；#184 时 219 / `fb771a7cacbb9fa661a5e1037e3bdd80`）——两个文件一套改动里换行相反，锚点归一要按各自的文件判断，别照抄隔壁。
- `src/backup.py` **95% → 100%**（#174，2026-10-09 PG 全量 905 passed 时重量，TOTAL 95.66%；SQLite 分支同轮 **904 passed + 1 skipped**）——缺的六行是四类各一，而**没有一类是"某条分支忘了测"**：`124` 是 `_run` 里那句真的 `subprocess.run`（备份那 18 条把 `_run` 整个换成替身，这台子进程从 pytest 进来一次也没起过）、`152` 是 `BACKUP_DIR` 为空那道闸门（今天没有调用方给过空串）、`217-218` 与 `266-267` 是轮转和陈旧判断各自那句 `except OSError`（要有"目录里列得出、`getmtime` 抛一次"的条目才走得到）。换掉 `_run` 本身是对的——"口令进不进 argv"只有在那一头钉得住，真跑一次 pg_dump 反而看不出来；代价是**发出去的 argv、环境变量、超时、还有那套解码参数本身一格签字都没有**。现在由 `tests/test_backup_child_process.py`（9 条）落在另一头：真起一个子进程（`sys.executable`，不依赖 pg_dump 在不在 PATH 上），三道兜底用**最小假体**走到真代码（只换 `os.listdir` 让 `getmtime` 真抛一次；或只换 `latest_backup` 指回一个不存在的路径），变异电池 **10 格里 8 红 1 实测等价 1 预备翻转**（那一格 Z10 已由 #181 落地，见下面第二条）。这一层的用例**不打库**（只用 `tmp_path` 摆文件），所以不需要测试库，也不与任何在跑的库用例冲突。改这一族前值得知道：
  - **`text=True` 是实测等价变异（Z4 全绿）**：只要留着 `encoding="utf-8"`，CPython 的 `subprocess` 本身就进文本模式，摘掉 `text=True` 那 27 条照绿。这一格是**声明**钉住的而不是用例钉住的（与 #172 那组有默认值的 `response_model` 字段同族），别读成"`text=True` 有签字"。
  - **`encoding` 和 `errors` 各承一个不同的重**：这台机器的控制台代码页是 cp936，去掉 `encoding="utf-8"` 后子进程那句中文诊断按本地代码页解成乱码——而那句正是失败通知里唯一的原因（Z1 红 1）；去掉 `errors="replace"` 后**一个**坏字节就把备份任务本身炸成 `UnicodeDecodeError`，连原因都发不出去（Z2 红 1，实测两个坏字节 → 两个 U+FFFD 而不抛）。
  - **`env=env` 是口令那道闸门的下半**（Z6 改成 `env=None` → 红 1）：`run_backup` 是 `env = {**os.environ}` 现抄一份再往上加 `PGPASSWORD`，所以 `_run` 一旦回落到父进程环境，**传一份"没有它"的环境也没用**，口令再也清不掉。用例因此钉的是"父进程有一个子进程不该有的键"，比"值进得去"值钱。
  - **`timeout` 是真转发的**（Z5 摘掉 → 红 1，且那一格真的让子进程挂了 30 秒）：pg_dump 挂住时任务必须有话可说，`TimeoutExpired` 是 `_run` 唯一的"子进程卡住"出口——注意它**不是** `BackupError`，现在由 `tasks.py` 那层 Broad `except Exception` 接住并写通知。
  - **`is_stale` 的 docstring 与代码现在是一致的（第二块选项板⑤甲，#181 已落地）**：#174 量出那个 `try` 只包住 `265` 那一次 stat——文件在 `latest_backup` 挑最新那一步**之前**就消失时，`FileNotFoundError` 从 `261` 外抛（`max(key=os.path.getmtime)` 自己就 stat）。调用方 `scheduler/tasks.py:93` 那句 `if not backup.is_stale(...)` 没有任何 `try` 包着（那句 `try` 在 `_dump_and_notify` 里面，要过了这一行才进得去），于是启动补跑在还没开始备份之前就死掉：库从此没有保险检查，也没有一条通知说得清为什么（#100 同族）。#181 把取"最新那一份"这一步一起并进 `try`，两条 stat 同一处理。顺带接受的后果：**目录整个读不出**（`listdir` 的 `PermissionError` 也是 `OSError`）现在同样答"没有保险"——这是刻意的，因为它下一步就是真去 dump，而那一趟的失败有自己的通知，比这里安静地返回 False 好。原来那条钉现状的用例（断言它抛）已翻成 `test_an_entry_that_was_already_gone_before_the_listing_counts_as_stale_too`，红过一次再改的代码（现 HEAD 上跑它 = `FileNotFoundError` 从 `241` 穿出）。
  - **换行**：`src/backup.py` 在工作树里是 **CRLF**（277 CRLF / 0 lone LF，md5 `1eb7195b58a09f5da2249a9bbfa73ed5`；#181 前为 273 / `7451c02d4b8b092ccf62c7ddbdadf997`），字节级改这一文件时锚点要按它自己的换行归一。
- `src/api/videos.py` **94% → 100%**（#173，2026-10-09 PG 全量 896 passed 时重量，TOTAL 95.53%；SQLite 分支同轮 **895 passed + 1 skipped**）——缺的八行（`236-238`、`242-248`）不是边角，是 **`PUT /api/videos/{id}` 上 `tag_ids` 那一路的整个函数体**：接口层此前只被 `POST /api/tags/video/{id}` 那一头敲过（append 语义），而 PUT 这头是 `video.tags = tags`——**整串换掉**。同一张 `video_tags` 上两条语义相反的写路径，中间那条零钉子。为什么界面上看不见：`VideoDetail.vue:234` 组装的请求只有 `title`/`description`/`rating`，`types/video.ts` 上那个 `tag_ids?` 从来没被发出去过（与 #151 那四个装饰配置项同族）——**#191 依第二块选项板⑫把它从前端类型里删了**，所以这一路今天的调用方只剩后端自己那 9 条用例，加上真后端 e2e 里两条裸 `JSON.stringify` 的请求（它们演的正是"任何别的客户端"）。现在由 `tests/test_api/test_video_tag_put_endpoint.py`（9 条 → ⑥/#180 之后 **11 条**）钉住，变异电池 **10 格里 9 红 1 绿**。改这一族前值得知道：
  - **这一单发现的那个洞（第二块选项板⑥甲，#180 已落地为拒绝）**：`select(Tag).where(Tag.id.in_(tag_ids))` 只回查得到的行，查不到的不当成错误，而后面那句是整串替换——拿一个已被删掉的标签 id 发一次 PUT，这部片子原有的标签会一起没了，接口照样回 200，也没有一句说得出"哪个 id 不存在"。对照 append 那头：同样忽略未知 id，但不动已有关系（`tag_service.py:147`）。用户选**拒绝**：路由现在先核对标签、再写字段，缺哪个就在 `detail` 里点出哪个号（`标签不存在：999999`），**核对搬到了字段更新之前**是有意的——否则 `{title, tag_ids}` 一起发时会留下"接口回 404 而标题已经改了"这种两边各自自洽的形状。三条新用例（`test_an_unknown_tag_id_is_refused_and_leaves_the_existing_set_alone`／`test_a_partly_known_tag_list_is_refused_before_anything_is_written`／`test_a_bad_tag_id_refuses_the_whole_request_including_the_field_half`）替掉了原来那条钉现状的；`[]` 仍然是一次**清空**的真写、`null` 仍然 400，这两半没动。`detail` 的措辞不钉（#188 已经把它换成中文「标签不存在：999999」，用例断的还是"句子里点得出那个号"，语言由第五条守卫钉）。
  - **`refresh(video)` 是不承重的**（M3 全绿，唯一的等价变异）：关系刚在同一个会话里赋过值，对象就在 identity map 里，序列化读的是内存那份。真正被 `test_the_replacement_is_committed_before_the_response_finishes` 钉住的是那句 `commit`（M2 摘掉 → 红 5 条：响应照样好看，库里没动）。别把这一格读成"重查过的值已经签了"。
  - **`[]` 和 `null` 是两件事，靠 `is not None` 分**（M4 写成真值判断 → 红 1 条）：`model_dump(exclude_unset=True)` 让"没带这个键"和"带了 null"落到同一个 `tag_ids is None`，所以 `{"tag_ids": []}` 是一次**清空**的真写，`{"tag_ids": null}` 走的是「没有需要更新的字段」那道闸门（M8 拆掉闸门 → 红 2 条）。
  - **只改标签不动 `videos.updated_at`，改标题动**：详情页 `VideoDetail.vue:454` 那个"更新于"因此认不出刚贴过标签——这是观察到的现状，不是钉子（`updated_at` 全仓不参与排序）。
  - **片子不存在时两半都 404，措辞不同**：`236-238` 那句不带 id、服务层那句带。用例钉"两句不一样 + 都是 404"，**不钉措辞**（#188 之后这两句都是中文，钉的仍是"一句带号、一句不带"这个形状差）。另记响应里标签的顺序是表顺序不是请求顺序，所以不许写顺序断言。
  - **锚点必须按目标文件的换行归一**：`src/api/videos.py` 在工作树里是 **CRLF**。别按目录推——2026-10-09 逐个量过 `src/**/*.py`，**80 个文件里 25 个是 CRLF**（`backup.py`、`main.py`、`src/api/*` 里 7 个、`src/services/*` 里 8 个），其余 LF；同一个目录里两种换行并存（`src/api/` 17 个文件中 7 个 CRLF）。字节级变异第一轮就因为这个 `anchor_count` 恒为 0——每一格都会被"锚点没命中"挡下，看起来像电池没事跑、其实是电池没跑。**判定换行只能用 `count(b'\r\n')` 对比 `count(b'\n')`**（两者相等才是纯 CRLF）：Git Bash 里 `grep -c $'\r'` 的模式会塌成空串、每行都算命中，永远等于行数——2026-10-09 就这样把一份纯 LF 的测试文件写成"197 CRLF"进了 CHANGELOG。另记：`core.autocrlf` 为真，**库里存的是 LF**，所以 `git show HEAD:文件` 的 md5 和工作树的 md5 天然不相等，别拿它当"没被翻过"的证据。
- `src/api/transcode.py` **89% → 100%** 与 `src/services/transcode_service.py` **89% → 100%**（#172，2026-10-09 PG 全量 887 passed 时重量；SQLite 分支同轮 **886 passed + 1 skipped**）——接口那一头缺的是 `87`（`GET /{video_id}/status` 的函数体）、`108-111`（取消的 try 加它那两句 `except ValueError → 404`）和 `119`（`GET /formats`）：pytest 对 `/api/transcode/*` 只发过两种请求（`POST /{video_id}` 成功那一路、`GET /{video_id}/outputs`），而前端一进转码页就并发读状态和格式表（`Transcode.vue:217`），之后每 1.5 秒轮一次状态。服务层那一头缺的是 `_notify` 整个本体（`168-183`）加 `155-158`（编码器抛异常的兜底）、`209-210`（`_record_output` 的 `except`）、`286`、`290`——原因是**替身把要测的东西演掉了**：13 处用例先把 `_notify` 换成 noop，注释给的理由是"别让后台任务写应用库"，而这条顾虑从 #154 起已有别的解法（同一个 fixture 把模块级 `async_session_maker` 指回测试库）。那 13 处今天照旧留着，只是由 `tests/test_services/test_transcode_notification.py`（7 条）在另一头真写了一行。五件量出来的性质，改这一族前值得知道：
  - **有默认值的字段在 HTTP 那层是拆不红的**（X1 全绿）：`TranscodeStatusResponse.error: str | None = None` 有默认值，`response_model` 构造时把服务层少给的那个键补成 `None`，所以这个形状是**声明**钉住的，不是用例钉住的；没有默认值的那两格才红得了（X1b 摘 `video_id`、X1c 把 `is_transcoding` 改成 camel，各红 5 条 `ResponseValidationError`）。
  - **两处 `except Exception` 共用同一个模块级 maker**，把它一炸到底会两处一起吞、两行都算"覆盖到了"而谁也没被钉住。所以分开坏：一条只坏 `session.scalar` 的包装会话钉 `_record_output`，另一条把 `NotificationService.create` 换成抛异常钉 `_notify`。
  - **取消不许发通知**——`except CancelledError` 里那句 `raise` 就是为这一条存在的（Y9：摘掉 `raise` 后每次取消多发一条假的失败通知）。`_notify` 写在 `try/finally` 的 `finally` 里，看着像"取消也要 announce"。
  - **`cancel()` 末尾那两行（`285-286`）是构造性不可达**：`transcode()` 先 `create_task` 再登记，而 `_run` 成功/失败/取消三路都写状态，所以"账上挂着 running 却没有任务对象"走不到。用例手工摆一条 `task=None` 钉它确实收敛成 `cancelled`，docstring 里声明是防御分支（与 #165 那两处同一处理）。
  - **状态那一路不查库**：影片行删了照样 200 + idle，因为 `get_status` 读的是进程内那本 `_jobs`——页面上的轮询代码只准备了"没在转"这一个分支，给它 404 会变成一句谁也说不清的报错。另记一句 `data.video_id`：通知里带着它，但全仓 `grep` 没有前端读它，用例钉它是因为真后端 e2e 第 15 条钉了它，**别把它读成"通知能点回那部片子"**。
- `src/database/session.py` **88% → 100%**（#171，2026-10-09 PG 全量 872 passed 时重量；SQLite 分支同轮 **871 passed + 1 skipped**）——先前缺的是 `205-210`（`init_db()` 的选路本体）和 `278-282`（`get_session()` 的 `yield` 与 `finally` 收尾）：`test_app_boot_lifespan.py` 和 `test_cli.py` 把 `init_db` 换成只登记名字的替身，HTTP 用例又都经 `dependency_overrides[get_session]` 借测试自己的会话，于是这两段"只有生产在跑"。现在由 `tests/test_database_boot_routes.py`（8 条）真跑——引擎换成 `tmp_path` 上的独立 SQLite 文件库，因为这两个函数读的是**模块级**的 `engine` / `async_session_maker`，留着默认值就是去动开发库。四件实测出来的性质写在上面「数据库迁移」那节，改动这一文件前去看：`engine.begin()` 换成 `connect()` 不报错、只让迁移整体静默回滚（W6 红 4 条）；"还不还连接"只能问 `pool.checkedout()`，因为关掉之后的 `AsyncSession` 什么都不抛；`finally: close()` 与 `async with` 各自都是等价变异（W7 / W8 全绿），只有两个一起没才红；认库恒真（永远走补齐）也全绿，因为今天的修订全是纯 DDL、`create_all` 恰好演得出来——**带数据的修订一出现，这一格就是盲区**。
- `src/export_openapi.py` **77.78% → 100%**（#170，2026-10-08 PG 全量 864 passed 时重量；SQLite 分支同轮 **863 passed + 1 skipped**）——先前缺的六行（`39, 42-43, 71-76`）不是某条分支，是**这个模块自己干活的那一路**：`matches()` 里"读不出一个 schema"的三支（文件还没生成 / `--out` 指到一个目录 / 内容不是 JSON）和 `main()` 不带 `--check` 时写盘那一整段。为什么这一格值得补：它是前端契约测试的对照表，而"写出去的那份"和"核对用的那份"是否同一判断，此前零钉子——不一致时红的是快照而不是调用方，调用方还在前端另一种语言里。三条量出来的性质，改这一文件前值得知道：`--check` 比的是**解析后的对象**不是字节（同一份 schema 换缩进换键序照样算一致，反过来不许把"谁顺手跑了个格式化"演成假的不一致，实测 V6 改回字符串比就红 1 条）；Windows 上 `--out` 指到目录抛的是 `PermissionError`、POSIX 上是 `IsADirectoryError`，同属 `OSError`，所以用例不许写死 errno；写盘那一路的 `newline="\n"` 是实参不是装饰（V5 摘掉 → 红 1 条，前端读到的就成 CRLF）。另记一句：`if not output.exists()` 是**等价变异**（V1 摘掉它照样 9 passed——`FileNotFoundError` 本就是 `OSError`，被同一个 `except` 接住），那一行只把语义写明白，别当守卫信任。
- `utils/ffmpeg.py` **23% → 89% → 100%**（#169 用假子进程把 `transcode_video` 钉住，2026-10-08 PG 全量 858 passed 时重量到 89%；#189 依用户定夺⑩删掉零调用方的 `get_video_info`，2026-10-10 PG 全量重测补满）——先前缺的 55 行不是"某条分支没测到"，是**整个 `transcode_video` 从 pytest 进来一次也没被调用过**：服务层用例把它整个换成替身，真 ffmpeg 又只在**另一个进程**里跑（`frontend/e2e/real/` 那四条：第 15 条真 FFmpeg 写出真文件、真读文件头，也用 `ffprobe` 核对产物里那两条流正是配方里那一对编码器；第 16 条让 ffmpeg 真失败一次，签的是那句原因从子进程一路走到接口、页面和真库；第 17 条杀的是一个真子进程，半截产物跟着它一起从磁盘上消失；第 25 条在另一支文件 `video-transcode-mp4.real.spec.ts` 里把 mp4 那一行的 `-c:a aac` 也签了——它从前被**源文件的后缀**挡着，当时同格式闸门比的是拼出来的路径、不比扩展名；#154 之后产物写在 `transcode_output_dir/<影片 id>/` 那一格，拼不出"和源同一个路径"，闸门改成比源的扩展名、理由换成"产物会和源同名"，换源这个办法因此照旧是唯一能让 mp4 那一行点起来的路），而那份执行永远不进这份读数。现在 `tests/test_utils/test_ffmpeg_encode_recipe.py`（14 条）用一个假子进程钉的是**发出请求的那一头**：argv 逐字对表（含 `-progress pipe:1`，以及 stderr 折进同一条管道——两处各一个缓冲，ffmpeg 会在写满 stderr 时卡住）、四个容器各配哪一对编码器（`webm` 那格单独钉 `libopus`：`-c:a aac` 在 webm 里是 ffmpeg 直接拒绝的配方，不是"效果差点"）、`out_time=` 怎么变成百分比并封顶 100、认不出的那一条时间戳只丢那一格、失败那句给的是 ffmpeg 自己的诊断行而机器可读的 `frame=` / `bitrate=` / `progress=` 一行不许混进去、什么诊断都没给时只许说退出码、管道断了要说得出原因且必须 kill 完再 reap、取消那一路 kill + reap + 半截产物 unlink（文件不在盘上也不能变成一次失败）+ `CancelledError` 原样抛上去。**两层对着同一个约定**：那四条签结果、这一层签请求，任何一头自己改了不通知对方都会红。这一文件现在**没有留白**：原先那 8 行（`35-56`）是 `get_video_info`，全仓 `grep` 只有它自己的定义和一份 2026-07-27 的计划文档、**没有任何调用方**——#189 把它删了。「给死代码写用例只会让它看起来是活的」这条判断没变，变的是不再留着它占一行百分比。
- `scheduler/tasks.py` **93%**（2026-10-07 补上「自动扫描」那道闸门之后重量的，此前 62%）——两个扫描任务现在各有 5 条用例端到端走过（`tests/test_scheduler_auto_scan_switch.py`：闸门、空表默认、开关拨回、手工扫描不归它管、全量那一轮），剩下缺的 44-45 / 69-70 是"失败通知自己也写不进库"那两层兜底，要有真机上的第二次异常才红得起来；只有两条备份任务（每晚 + 启动补跑）另有 `test_scheduler_backup.py` 盖着。**另记一处已经补上的**：#150 那次量到 `api/scheduler.py` **75%**（那四个管理端点从来没被请求过）、`scan_scheduler.py` **81%**（`start()` / `stop()` / `get_jobs()` / `is_running` 四段没人走）、`source_service.py:87`（关启用时拆任务那一句）0 引用——这三处于 2026-10-07 由 `tests/test_scheduler_source_lifecycle.py` 一起清到 **100%**，钉的是片源 create / update / delete 与调度任务那三条同步边（少一行不会红任何一条库里的用例，代价是进程里留一个永远扫不到东西的任务，每轮换回一条失败通知）。
- `src/e2e_seed.py` **55% → 70%**（#203，2026-10-10 PG 全量 1052 passed 时重量）——一次性库的播种与重置，主要活在打真后端的 e2e 那个进程里，pytest 进程只 import 和调其中一部分。剩下的 **39 句全部是 `seed()` 的体内（181–284）**，这是**故意留白**：它要真 PG、真媒体目录和真 FFmpeg，价值恰恰在"走的是真写入路径"，拿假会话演一遍就等于什么都没证（与 #172 同一条判断），所以它只由 `python -m src.e2e_seed && uvicorn …` 那条真后端链签字。这一单补上的是**从前一次也没从命令行进来过的部分**：`main()` 整段（两道环境变量的闸门、退码 2/0/1、stdout 只许是 ASCII JSON、失败那句不许带口令）和 `_truncate_all` 那条语句的形状（表名排序、跳版本表、`RESTART IDENTITY CASCADE` 三个实参一个都不许少）。三条量出来的性质，改这一文件前值得知道：
  - **封面目录的沙箱判据从前根本没被走到过**（`prepare_media` 里 `if root in thumbnails.parents`）：用例没换过 `e2e_seed.settings`，读到的永远是真 `backend/data/thumbnails`，判据恒假。现在两条对照各钉一侧——沙箱内的封面目录跟着清、沙箱外的一个字节不动。
  - **`business_tables` 是生产代码和测试脚手架共用的**（`tests/conftest.py` 每条用例的 TRUNCATE 就用它）：变异电池里"少减版本表"那一格在真 PG 测试库上把 `alembic_version` 一起清了，之后每条用例都死在 `_prepare_schema` 的 `DuplicateTableError`。用项目自己的 `stamp_head()` 恢复（19 张表、`revision=None` → `0002`），电池随后改成所有 pytest 子进程一律 `TEST_DATABASE_URL=` 走内存 SQLite——**碰这个文件的电池不许往真测试库上敲**。
  - **`.resolve()` 那一格是等价变异**（E4 去掉它 16 条全绿）：`config.py` 的 `_anchor_under_backend` 校验器已经把配置里的路径锚成绝对路径，所以这里再锚一次是重申而不是守卫——别把它读成"少了就逃逸"。
- `api/settings.py` **100%**（2026-10-05 补齐系统配置那一面之后重量的，PostgreSQL 全量 725 passed，此前 71%）——先前缺的就是整份 `PUT` 和单键读写这几条端点：`test_preferences.py` 只测过白名单拒绝和一次单键写入，`GET /api/settings` 的默认值那一路反而没人走
- `api/stream.py` **72% → 100%**（#164，2026-10-08）——先前缺的十七行（`37, 44-59, 90-100, 105-116`）不是"某条分支没测到"，是**整条路由从接口进来一次也没被走过**：`tests/test_api/test_stream.py` 直接调 `_handle_range_request`，Range 的边界语义有真文件签字，所以那函数看着很健康，而它上面的路由、`_get_content_type` 整张表、封面那两条（在盘上 / 不在盘上）全在盲区里。同一份十七行在只跑 16 条用例的子集和跑满 786 条的套件里读数**一模一样**——这就是判断"这一格只能由 pytest 补"而不是"e2e 已经盖住了"的依据（真后端 e2e 里浏览器确实放片子，那是另一个进程、不进这份读数）。现在由 `tests/test_api/test_stream_endpoint.py`（19 条 → **#190 之后 23 条**，其中 content-type 那张表按九行 + 兜底逐行钉住）钉到 100%（#190 重测：62 条语句 / 0 条未覆盖，新增的判零分支被四条零字节用例踩满）。三条量出来的性质，改这一文件前值得知道：
  - **本地那一路删掉路由里的 Range 分支照样全绿**（实测 M6）：`FileResponse` 自己就懂 `Range`，两种写法给出的 206 状态码、`Content-Range` 和正文一模一样。所以那条分支真正在服务的只有对象存储那一路——别按"本地也靠它"去改它的顺序。
  - **`capabilities.local_path` 是播放路径上唯一挡住 `s3://` 的东西**（M3：把它写死成 `True`）：本地用例全绿，对象那条给出 `OSError: [WinError 123] 文件名、目录名或卷标语法不正确。: 's3://media/shows/01.mkv'`，也就是真机上一个 500。
  - **0 字节的对象：#190 依用户定夺⑪改成"先判零再干净答"**（`if file_size == 0` → 一个空的 200，答案照本地那一路的 `FileResponse` 抄）。为什么它进得了"读得到"那一条分支：`size()` 对空对象回的是 `0`，**不是 `None`**。从前那一行把区间算成 `max(0, 0 - 1)` = `bytes=0-0`，而**空对象没有第 0 个字节**：moto 抛 `InvalidRange`，异常又是在响应头已经提交之后才从 `StreamingResponse` 的生成器里冒出来，真机上的形状是"播放器拿到一个断流的 200 + 服务端日志里一条异常"，不是 404 也不是干净的 500。**这一格最贵的一条是"绿"和"钉得住"不是一回事**：只留"响应是空 200"那种用例，把闸门拆掉、算术换成 `bytes=0--1` 照样全绿——moto 对那种越界区间安静回空，真桶不保证（#190 的电池里 M1、M3 两格第一次就是这么绿的）。所以 `test_the_empty_object_answer_never_asks_the_bucket_for_a_byte` 钉的是**有没有出门请求**：在 `storage.iter_range` 上架 spy，断言 `asked == []`，拆闸门立刻红。算术里那道 `max(0, ...)` 跟着删掉了——走到那一行 `file_size` 至少是 1，留着它反而让"有人拆掉闸门"变成一次只有 moto 才看得见的沉默。**还欠一句产品语义，等定夺**：零字节的片子在真机上就是坏片，"空的 200"只是与本地那一路对齐的答案，404 / 416 / 500 哪个算对⑪面板没选；哪天改码，那两条对照用例（桶里的空对象、磁盘上的空文件）必须一起翻。另外 #164 那条仍然成立：把 `max(0, file_size - 1)` 写成 `file_size`（也就是 end 越过文件末尾）**全绿**——越界的 end 被服务端收敛，正文一字节不差，而 `Content-Length` 来自 `str(file_size)` 而不是那个参数；这一条记下来是因为它**钉不住**，不是记它已经钉住了。
  - 封面那两条的红法是 `starlette.responses` 的 `RuntimeError`（M5：去掉 `os.path.isfile`），不是 404——行还在、文件不在了，这一格只能回"没有封面"。
- `utils/password.py` **85% → 100%**（#163，2026-10-08）——缺的 21-22 两行是 `verify_password` 里那句 `except ValueError: return False`，从来没一个用例喂过它一个真坏掉的哈希。**这一单真正该记住的是读数会骗人**：同一份读数里 `auth_service.py:369`（`raise ValueError("密码过长（上限 72 字节）")`）是缺的，可它上面那一行 `if password_too_long(password)` 每次建号都会被执行，`password.py:27` 那句 `return len(plain.encode("utf-8")) > 72` 也算"覆盖到了"——**一个从来没返回过 True 的布尔判断，在行覆盖率里长得和永远正确一模一样**。这一族缺口只能靠变异看出来（M1 拆掉闸门 → 红在 detail 换成 bcrypt 那句英文；M2 `>` 改成 `>=` → 红两条，其中 API 那条是从边界另一侧撞上的；M3 `except ValueError` 收窄成 `except TypeError` → 红在坏哈希那条；M4 把 `.encode("ascii")` 换成 `.encode("utf-8")` → **全绿**，这一处确实钉不到，已经写进用例 docstring 而不是假装钉住了）。另记一句界面那一头：`Users.vue` 的口令框没有 `maxlength`，所以"25 个汉字"不是构造出来的地址栏请求，是真打得进来的字。
- `api/users.py` **94% → 98%** 与 `auth_service.py` **97% → 99%**（#165，2026-10-08）——`tests/test_api/test_users.py` 把五条写路径"做成了之后是什么样子"都走过了一遍，缺的却是**拒绝那一侧**：坏角色（建号 `auth_service.py:234`、改角色 `:314`）、管理员重置口令时那两道强度闸门从这一头的映射（`users.py:172-173`，#163 钉的是另外两个调用方）、降级别人时连带踢掉他的浏览器（`users.py:137`），和"账号已停用"在会话解析那一层的把关（`auth_service.py:143`）。现在由 `tests/test_api/test_admin_write_gates.py`（8 条）钉住，N1–N7 逐条能红。**两处剩下的行是构造性不可达，别去补用例**：
  - `users.py:155-156`（`update_status` 的 `except ValueError → 400`）——`set_active` 只会因「除他之外没有别的可用管理员」而抛，而 actor 必然是一个可用的 owner（中间件按 `is_active` 把关），且"停用自己"在更早一句就被另一句 400 挡掉了，所以 actor 自己就是"除他之外的那个"。这一句是给未来少一层前置检查留的兜底。
  - `auth_service.py:143` 的前半句 `user is None`——`sessions.user_id` 声明的是 `ON DELETE CASCADE`，账号被删时会话行不可能留着。后半句（停用而会话还活着）真接口也造不出来（`set_active` 是删会话），所以那条用例**绕过接口直接写库**，并同时断言那一行还在——否则 401 会被误读成"会话没了"，闸门就白钉。
  另记一条**钉不住**的（实测 N8 全绿）：把 `create_user` 里的角色闸门整块挪到重名检查之后，八条照旧全绿——这一族钉的是"每道闸门给得出那句中文"，钉不住两句检查的先后。`users.py:134` 那条复合守卫的三个格子（降级别人 / 降级自己 / 升级别人）现在各有一条用例看着（N4/N5/N6），改它顺序或删半边之前值得知道。
- `auth_service.py` **99% → 100%**（#166，2026-10-08）——上一单记的那句"另开一单"这一单收掉了：最后缺的三行（`409-410, 416`）全在锁定的**下半句**上。`test_auth.py` 那条只钉过"五连败会锁"，"锁会自己解开"和"比窗口还慢的猜测者不该被攒成永久锁定"一次也没被执行过；现在由 `tests/test_api/test_login_lockout_expiry.py`（6 条）钉住，M1–M6 六个变异逐条能红。改这一族之前值得知道三条量出来的性质：
  - **只能用假时钟**：整模块 monkeypatch `auth_service._utc_now`，一步跳满一个窗口。真睡 600 秒跑不动，而"到期"恰好落在边界上，用挂钟的话读数取决于机器快慢。阈值也别写死——从 `login_rate_limiter()` 现读 `max_failures` / `lockout_seconds`，改配置时这六条不用跟着改。
  - **两处边界各差一个等号，是有意选的**：`locked_for` 用 `left <= 0`（正好走完即放行，M1 翻成 `<` 红 3 条），`record_failure` 用 `elapsed > lockout_seconds`（隔**整整**一个窗口仍算累加，M6 翻成 `>=` 红"整窗口间隔"那条）。所以"到期"和"清零"不是同一瞬间，别顺手统一这两个符号。
  - **`return 0` 那一句删不掉**（M3 红 3 条）：走到下面的 `int(left) + 1`，到期那一瞬 `left` 是 `0`，`int(0) + 1 == 1` 是真值——账号被永久锁死；再多过一秒 `left` 变负才碰巧为假。"解没解开"于是取决于到期之后过了几分之一秒。同理 M2（删掉那次 `pop`）红在"窗口走完之后再错一次就是第 6 格"。
  - **接口那一层的"慢猜测者"是拆不红的，别以为已经安全**（临时探针实测，两条接口层用例挂在 M2 / M5 上各跑一轮都是 `2 passed`，探针文件跑完即删）：路由每次都先问 `locked_for`，`:409` 的 pop 会把旧账先抹掉；就算删了 pop，`:416` 的重置还在。两道守卫是**刻意重叠**的，所以 `:416` 只能钉在计数器那一层（`record_failure` 之间不读锁），M5 就是那样红的。同一层里"走完窗口放开这一次"也不够——要追一条"紧接着再错两次仍是 401"，否则旧计数没忘干净时立刻又 429，红点会落在别的用例上。
- `src/main.py` **81% → 100%**（#167，2026-10-08）——缺的十二行全在 `lifespan` 里，也就是**应用自己的启动那一段**：建库、按表里现存的片源挂扫描、备份只在 PostgreSQL 上挂载、真的 `start()`、退出时真的 `stop()`。为什么全量八百条一次也没走过：`tests/` 里所有接口用例都骑 `httpx.ASGITransport`，而它**不触发 lifespan**（只有 `with TestClient(app)` 那种上下文管理器会），所以"启动"这一步在 pytest 这一套里从来没有入口。现在由 `tests/test_app_boot_lifespan.py`（7 条）钉住，P1–P9 九个变异全部能红。改这一段之前值得知道三件接线的性质：
  - **调度器必须是替身，而且要打在 `src.main.scheduler` 上**，不是进程级那个单例——否则一条用例挂的任务会漏进下一条的读数里。用例用的是一个记录顺序的子类（`BootScheduler.events`），断言的是**整条事件序列逐字相等**，所以"先建库再挂载"和"退出时关掉"这两条顺序都是钉住的。
  - **会话必须是借来的**（`_BorrowedSession`）：lifespan 那句 `async with async_session_maker()` 出来会 `close()`，直接换成真的 `async_session_maker` 会把测试自己的会话关掉。
  - **三个任务函数必须换成只登记不干事的替身，且替身打在 `src.scheduler.tasks` 模块上**（`scan_scheduler` 是在挂载那一刻从模块里取函数的，打在 `main` 上没用）。不放替身就是真机行为：启动补跑挂的是 `DateTrigger()`，`start()` 之后立刻执行，真跑一趟往真盘写一次 `pg_dump`；`scan_source_task` 用的又是全局会话，连的是 `settings.database_url` 那个真库。
  - 另记一条夹具上的坑：这个文件默认把 `settings.backup_enabled` 关成 `False`。本机 `.env` 里备份开着、库是 PG，不关的话钉片源的那几条会被启动顺手挂上的两个备份任务污染（第一版就是这么红的）。备份闸门的两半由后面三条用例各自显式摆好，所以关掉默认值不损失任何一格。

标签那套在 2026-10-05 补上了接口层用例（`tests/test_api/test_tags.py`，八个端点各过一遍，顺带把"重名建标签回 500"改成 409），`api/tags.py` 100%、`tag_service.py` 97%，不再是空白。**片单那三条写路径的签字处现在在浏览器那一头**（#145，2026-10-07）：`coverage report`（修正后的读数）显示 `api/watchlists.py:125`（PUT 路由那句 `raise HTTPException(409)`）和 `watchlist_service.py:129`（`watchlist.description = description`）在 pytest 这一套里**一次也没执行过**——409 只有 POST 那一路被撞过（`test_isolation.py:61`），也没有一条用例往一条已存在的片单上 PUT 过备注（`test_watchlist_service.py:126` 断的那个 `description is None`属于一条压根没写过备注的单）。这两行现在由 `frontend/e2e/real/watchlists.real.spec.ts`（真后端 e2e 第 26 条）走到，所以**改了 `WatchlistService.update` 之后别只看 pytest 全绿就以为没坏**：它那一半的签字在那套 e2e 里。另记一个盲区：`Watchlist.items` 上 `cascade="all, delete-orphan"`（ORM 侧）和 `watchlist_items.watchlist_id` 上 `ondelete="CASCADE"`（PG 侧）是同一个保证后面的两台机器，而第 26 条实测去掉 ORM 那一条会红在**移出**那一步——关系上没有 `delete-orphan` 时 `items.remove(item)` 走的是把外键置 null，PG 的 NOT NULL 当场 500——所以「删单」那一路的 cascade 至今仍是拆不红的，那一句只记不拆。这几处都是有意的取舍，不是漏了；别为了让总数好看去造只断言"没抛异常"的用例。

**标签名的裁剪只有一处出处：`TagService._clean_name`**（#130）。建和改两条写路径都先过它，裁完是空串就抛 `BlankTagNameError`（`ValueError` 的子类），路由把它翻成 400 并原样带上那句中文原因。为什么必须在服务层而不在界面收口：`tags.name` 的唯一约束算的是**整串**，`动作片` 与 `动作片␣` 是两行，而界面上是两张分不出来的卡片；`Field(..., min_length=1)` 数的是字符数，`"   "` 照样过校验建出一枚看不见的标签（这两条都是实测出来的现象，不是从文档推的）。只修前端的话任何客户端仍能往库里塞带空格的重复标签。**两处顺序是承重的，改动时别调**：`api/tags.py` 的 `update_tag` 里 `except BlankTagNameError` 必须排在 `except ValueError`（那条翻成 404「标签不存在」）**之前**——它本身就是 `ValueError`，晚一步那个 400 会悄悄降级成 404；`service.update` 里必须**先验名字再动任何 `setattr`**，否则一次带着 `{name, color}` 的失败改名会把颜色留下，`test_renaming_into_only_padding_is_refused_and_changes_nothing` 钉的就是后半句。扫描那条自动标签不需要跟着改：`name_parser._find_group` 早就 `.strip(" -_")` 了。

**ffmpeg 那句原因只有一处出处：`utils/subtitles.ffmpeg_stderr_reason`**（#142）。两条转换路径——外挂机翻 `_ffmpeg_to_webvtt`、内嵌轨翻 `media_streams.extract_subtitle_webvtt`——失败时都从这里取 stderr 的最后一条非空行（ffmpeg 在 `-loglevel error` 下把原因写在最后一行，实测 8.x：内容不是字幕的 `.ass` → 退出码 183，stderr 两行，最后一行是 `Error opening input files: Invalid data found when processing input`），各自只保留自己的那句前缀和"子进程什么也没说"时的兜底。为什么必须收在一处：`api/subtitles.py` 两个路由都是 `detail=str(e)`，而这边丢原因的修法在浏览器那头像"转换失败"四个字——那个人手上只有一部手机，看得到什么取决于走的是哪条路。内嵌那一路原本就带着原因，所以这一条不是把它改坏，是两条原本一边能诊断一边不能。**测试要钉住的是最后一段而不是兜底**：`stderr` 空、`returncode == 0` 但一个字节没转出来这两件事长得很像，只断言消息以「字幕转换失败」开头的话，把 `or not (result.stdout or "").strip()` 那一支删掉照样绿（`test_convert_ass_failure_without_a_reason_still_says_something` 钉的就是这一支）。

**字幕文件的编码只有一处出处：`utils/subtitles.read_subtitle_text`**（四层阶梯：UTF-16 BOM → UTF-8 BOM → 没有 BOM 的 UTF-16（#186）→ UTF-8，最后一层才是 gb18030 兜底）。两条转换支路（`.srt` 走 Python、`.vtt` 原样交出去）都拿它的结果当输入，而**读错编码永远不会报错**——它只会安静地交出一段合法但空白的轨，所以这一层的用例只能钉在"读出来的字"上，钉状态码或加载状态都签不住（真后端 e2e 第 23 条那句 `cues: []` 从前全绿就是这个道理）。

- **没有 BOM 的 UTF-16 是这一层里唯一需要"猜"的一级**（#186，第二块选项板⑧乙：这一单必须排在 #187 之前落地）。UTF-16LE 的字节序列 `decode('utf-8')` **不抛**（每个字符的低字节都是合法 ASCII），所以 gb18030 那道兜底压根轮不到；判据只有它留下的痕迹——ASCII 字符的高字节是 `0x00`。实测分界很宽：真 UTF-16 的字幕 NUL 率在 **0.35~0.50**，GBK / UTF-8 / 纯 ASCII 一律 **0.000**，阈值因此定在 0.1（单个漏进的 NUL 摊到 52 字节上是 0.019）。字节序靠"哪一半下标全是 NUL"判，不靠猜第二遍。
- **这一级只有一道判据闸门，外加一道除法保护，而且它必须能弃权**（电池 M1~M8 八格全红，`Temp/m186_mut.py`）：判据是 NUL 率，`not raw` 那一步只为"率是一次除法"存在（0 字节的 `.srt` 会被扫描按文件名登记成轨道，于是 `ZeroDivisionError` 挂在一条 HTTP 请求上 = 500），**不是**给"太短的文件"把关的——曾经有的 `len(raw) < 4` 和奇数长度两道闸门实测拆掉后全绿（奇数长度本来就 `decode` 失败、被弃权接住），按"没有钉子的分支就是没跑过的分支"删掉了。留下的两条半途因此钉的是**同一道弃权**：奇数字节断在长度对不上、偶数但尾部是孤立高位代理的断在码位本身，两条都不许把异常递出去。阈值调高到 0.9 让真文件掉回旧行为、不设闸门则把一份偶数长度的 ASCII 整份拆成乱码。**"挡错方向"的代价不对称**：少认一份是今天已经付的（那条轨空着），多认一份是把用户本来好的字幕换成别的字，所以这一层宁可放过、不许猜中。

**外挂字幕的名字只有一处出处：`utils/subtitles.sidecar_identity`**（#143）。扫描（`find_subtitle_files`）和手工挂载（`SubtitleService.add`）两条写路径都向它要同一对 `(language, label)`，文件名怎么切也只有一处（`_sidecar_suffix`：返回 `None` 表示「这不是这部片子的字幕」，扫描据此跳过兄弟文件的字幕，比如 `movie.mp4` 旁边的 `movie.mkv.zh.srt`）。为什么必须收在一处：手工那条路原先自己再切一次、规则还更松，于是同一个文件两种结果——`movie.chi.srt` 扫描给 `zh`、手工给 `chi`（那一列是界面 `srclang` 的出处），`movie.mp4.zh.srt` 手工两条字段都切成 `mp4.zh`。菜单上的名字来自 `LANGUAGE_NAMES` + `language_display_name`，这张表原本只住在 `media_streams`（内嵌那一路），现在两条来源共用一张，因为两类轨落在**同一个下拉框**里：一边「中文」一边 `chi` 就是那个人打开播放页看到的样子（真库里现在就躺着 `en` 和 `zh` 两行）。两条政策是承重的，别顺手改：认不出的代码**原样返回**（不给它编名字，也不用「未知语言」顶掉后缀里的信息）；**地区留在显示名里**（`zh-CN` → `中文（CN）`），否则简中繁中两条在菜单里同名、再也点不开。`language` 那一列在真库上是 `VARCHAR(10)`：客户端传来的值有 `Field(max_length=10)` 挡成 422，服务端自己派生的值没人挡——手工那条路以前把整个后缀塞进去，一部 `movie.这条是导演评论加长版说明.srt` 在 PostgreSQL 上就是 `value too long` → 500；现在非语言代码的后缀 `language` 一律留 `None`，说明性文字只在 `label` 里。**测试要钉的是两条路各算一次**：把内嵌那一路换成它自己的一张同名表（M8）全绿，这一层的共享只是 DRY；把手工那条路退回它自己的切法（M6）红 4 条，那才是这一单的签名线。

**一条 cue 都没有的转换算失败，判据只有一道，外挂三支与内嵌一支共用：`utils/subtitles.has_a_cue`**（闸门本体是 #187 立在 `convert_to_webvtt` 里的，第二块选项板⑧的子问一**甲** + 主问**乙**；#208 把它提成公开判据、按第三块面板 ④**甲**接到内嵌那一路）。判据是 `any(_CUE_TIMESTAMP_LINE.match(line) for line in webvtt.splitlines())`——就是 #140 为"把 cue 分隔符和游离空行分开"造的那个正则，它同时认 Python 那一路的 `00:00:03.000 -->` 和 ffmpeg 那一路省掉小时的 `00:05.000 -->`。为什么必须写在转换侧而不是界面侧：一份结构合法的空 WebVTT 交回 **200**，浏览器会把那条轨标成 loaded（`readyState` 2、`cues.length === 0`）、**不发 `error`**，于是 #146 那套「没能加载」的提示一辈子不执行——那个人看到的是菜单里一个照常可点、点开一个字都没有的条目。判成失败才让 415 和 `<track>` 的 `error` 事件第一次可达。**数的是转换之后的那份，不是磁盘上的那份**（M3 改用 SRT 那个带逗号的 `_TIMESTAMP_RANGE` 去数 → 红 9 条：三路转换全灭）。`.vtt` 逐字节透传那一支也过这道（子问一甲），代价是"只有头、没有 cue 的 `.vtt`"从此 415，M2 单独钉那一支（红恰好 1 条）。

- **手工与扫描之间那份不对称是政策，两头都有钉子**（⑧乙）：`SubtitleService.add` 在**包含检查之后**把文件真读一遍（`asyncio.to_thread(convert_to_webvtt, normalized)`），所以挂不上就是挂不上——异常在构造 `Subtitle` 之前抛出，库里没有那一行；扫描的 `register()` 照旧只看文件名（`test_scan_registers_a_sidecar_that_would_show_nothing` 钉的就是"空壳照样登记成轨道，那一行用户可以自己删"）。M6（把读文件装到包含检查之前）红 2 条、M9（给扫描也装上闸门）红 3 条——**别顺手统一这两条路**。`asyncio.to_thread` 那一层本身没有钉子（换成直接调用照样全绿：它挡的是"一次子进程占住事件循环"，pytest 里没有可观测差别），按现状记在这儿，别当成被签住的性质。
- **POST 回 415 而不是 400**：同一个 `SubtitleConversionError` 在这一族地址上只对应一个状态码，GET 读到零条 cue 是 415、POST 挂上同一个文件也是 415，不因为"这是写操作"就换第二套说法（M7 写成 400 → 红 1 条，M8 路由不收那个异常 → 红 1 条，症状变 500）。
- **连带的一条测试规矩**：假装的 ffmpeg stdout 从此**必须带一条真 cue**——`test_convert_ass_uses_ffmpeg` 那份假正文从前只是文本，闸门一落它就红在闸门上而不是红在被测的那一步。同理，#140 那条"头部分隔符"钉子的见证文件恰好一条 cue 都没有，这一单是把夹具换成一份真带 cue 的（`hello` 落在第一条时间戳之前）而**不是放宽闸门**。
- **内嵌那一支问的是同一句**（#208，第三块面板 ④**甲**）：这一支从前只看 ffmpeg 的退出码，而实测「只有头部的字幕封进 `mov_text` 再抽出来」正是 rc=0 加 7 字节，于是交出 200、浏览器标成 loaded、一个字都没有。⑧ 那条选项当时只覆盖「转换 + 手工 POST + 扫描」，这一支没有替用户擅自补上，而是留给 #208 —— 补的时候守住了面板 ④ 的原话：**同一个判据**，不是第二套口径。两句原话各管一种失败：子进程失败或整段空白说 ffmpeg 的原因，子进程成功而里面没 cue 说「这条轨里没有解析出任何一条字幕」。


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

### 版本到底锁在哪（#111 实测，别按编辑器告警改依赖）

- **`pyproject.toml` 的 `fastapi>=0.109.0` 只是下限**，真正决定装什么的是 `uv.lock`。实测（2026-10-05）：锁与 `.venv` 里 10 个关键包**零漂移**——fastapi 0.140.0 / starlette 1.3.1 / pydantic 2.13.4 / pydantic-core 2.46.4 / uvicorn 0.51.0 / anyio 4.14.2 / python-multipart 0.0.32 / alembic 1.20.0 / sqlalchemy 2.0.51 / httpx 0.28.1，Python 3.13.5；`uv lock --check` 退出码 0（锁与 pyproject 也是同步的）。
- **#111 写的"锁到 0.112.0"在仓库里找不到出处**：`backend/uv.lock` 是 2026-07-27 的 `1d77281` 才加进来的，从第一天起就是 0.140.0，此后四次改动一次没动过 fastapi；`git grep "0\.112"` 在所有被跟踪的文件里零命中。那个版本号来自仓库之外的解释器，不是我们的锁。
- **量版本必须用 `.venv/Scripts/python.exe`**：同一张对照表拿系统 python 跑，读出来是另一个环境的 fastapi 0.115.6 / starlette 0.41.3，会凭空得出一张"锁与环境漂移"的假表（这次就误读过一次，才发现差异全在解释器）。

### 升到 0.142 要动的面（评估结论：面很小，但这是依赖变更，等用户确认）

- `uv pip install --dry-run fastapi==0.142.2 --python .venv/Scripts/python.exe` 实测只动两件事：fastapi 0.140.0→0.142.2，外加新拖进一个 `opentelemetry-api==1.45.0`（来自 0.142.0 的"原生 OpenTelemetry 支持"）。starlette 保持 1.3.1、pydantic 不动，所以不是框架换代，是两个 wheel。
- 0.141.0 / 0.142.0 的 release notes 各只有一条 feature（`app.frontend(check_dir="auto")`、OpenTelemetry），没有 breaking 条目。0.142.1 修的恰好是 "included routers 重复包装端点"，就在 `_IncludedRouter` 那条路上——但改的是路由的内部结构，而我们两处全路由扫面读的是 `app.openapi()["paths"]`、不是 `app.routes`（见「OpenAPI 快照」），够不着断言的输入。
- **真要换版本，复核这三处就够**：① `app.routes` 的顶层条数与 `_IncludedRouter` 是否仍无 `.path`（实测 0.140.0 是 16 `_IncludedRouter` + 4 `Route` + 1 `APIRoute` = 21 条，与本文那条警告一致）；② `tests/test_main.py` 用 `app.user_middleware` 验 CORS；③ `tests/test_openapi_snapshot.py` 对上提交进来的 `openapi.json`（65 路径 / 84 操作）。当前 0.140.0 栈上全量后端 730 条绿，3 分 21 秒。
- 换版本之外唯一实打实告过的一条：`from fastapi.testclient import TestClient` 在 starlette 1.3.1 上是**导入即告警**（`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`），而 `TestClient` 只有历史遗留的 `test_main.py` 在用。它已改成与其余用例同一条 `httpx.ASGITransport` 路（`/health`、`/docs`、`/redoc` 都在中间件的"非 `/api` 直接放行"分支上，不需要 `db_session`，所以这里自建一个不带替身的 `public_client`），现在全量跑**零告警**。
