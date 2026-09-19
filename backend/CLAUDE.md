# CLAUDE.md - 后端开发规范

## 技术栈

- Python 3.11+
- FastAPI 0.109+
- SQLAlchemy 2.0+（异步模式）
- aiosqlite（SQLite 异步驱动）
- APScheduler（定时任务）
- FFmpeg（视频处理）
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
│   │   └── ...
│   ├── models/            # 数据模型层
│   │   ├── video.py       # Video 模型
│   │   ├── source.py      # VideoSource 模型
│   │   └── ...
│   ├── services/          # 业务逻辑层
│   │   ├── video_service.py
│   │   └── ...
│   ├── utils/             # 工具函数
│   │   ├── ffmpeg.py      # FFmpeg 工具
│   │   ├── file_scanner.py # 目录扫描与探针
│   │   ├── video_search.py # 搜索串解析（源/标签/评分/时长/观看状态）
│   │   └── name_parser.py  # 文件名解析（片名、系列、季集、字幕组）
│   ├── scheduler/         # 定时任务
│   │   ├── scan_scheduler.py
│   │   └── tasks.py
│   ├── database/          # 数据库配置
│   │   ├── base.py        # SQLAlchemy 基类
│   │   └── session.py     # 会话管理
│   ├── config.py          # 配置管理
│   └── main.py            # 应用入口
├── tests/                 # 测试文件
│   ├── test_api/          # API 测试
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

    async def create(self, name: str) -> Example:
        """创建示例。"""
        example = Example(name=name)
        self.session.add(example)
        await self.session.commit()
        await self.session.refresh(example)
        return example

    async def get_by_id(self, example_id: int) -> Example | None:
        """获取示例。"""
        result = await self.session.execute(
            select(Example).where(Example.id == example_id)
        )
        return result.scalar_one_or_none()
```

### 3. 创建 API

```python
# src/api/examples.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
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
    service: ExampleService = Depends(get_example_service),
) -> ExampleResponse:
    """创建示例。"""
    return await service.create(name=data.name)
```

### 4. 注册路由

```python
# src/main.py
from src.api.examples import router as examples_router
app.include_router(examples_router)
```

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

`init_db()` 只有 `Base.metadata.create_all`，它只补建新表、**从不修改已存在的表**。因此给已有表加约束或索引时，要把补齐用的 SQL 写成模块常量放在 `src/database/session.py`，在 `init_db` 里紧随 `create_all` 执行，并保证幂等（`IF NOT EXISTS`、先清洗再加约束）。参考 `play_history` 的"每部视频一行"：先 `DEDUPE_PLAY_HISTORY` 折叠老库的重复行，再建 `ix_play_history_video_id` 唯一索引——顺序反了会直接建索引失败。

加**列**走的是同一条路的另一支：`ADDED_COLUMNS` 三元组（表名、列名、`ALTER TABLE ... ADD COLUMN`）配 `PRAGMA table_info` 探测，缺哪列补哪列，再单独建需要的索引（`VIDEOS_SERIES_INDEX`）。这类修复只在启动时跑，测试用的 `db_session` 直接 `create_all` 建全新库，所以新列必须同时在模型里声明。

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
├── test_api/
│   ├── test_videos.py
│   └── test_sources.py
├── test_services/
│   ├── test_video_service.py
│   └── test_source_service.py
└── test_models/
    ├── test_video.py
    └── test_source.py
```

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
