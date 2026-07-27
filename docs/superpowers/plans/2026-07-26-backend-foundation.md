# 后端基础与核心功能实现计划

> **致 agentic 工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐步实施此计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 构建后端 API 基础架构，包括项目结构、数据库模型、视频管理和扫描服务。

**架构：** FastAPI 后端配合 SQLAlchemy ORM、SQLite 数据库、模块化服务层和 RESTful API 端点。遵循依赖注入模式进行服务管理。

**技术栈：** Python 3.11+、FastAPI、SQLAlchemy 2.0+、APScheduler、uv 依赖管理

## 全局约束

- Python 版本：3.11+
- 使用 `uv` 进行 Python 依赖管理（而非 pip/poetry）
- 遵循 PEP 8 代码风格，4 空格缩进
- 数据库：SQLite 3
- 尽可能使用 async/await 处理 I/O 操作
- 所有函数签名使用类型提示
- API 响应遵循 JSON 格式，统一错误处理
- 所有新代码必须有对应的测试
- 提交信息遵循 conventional commits 格式

---

## 阶段一：项目结构与配置

### 任务 1：创建后端项目结构

**文件：**
- 创建：`backend/pyproject.toml`
- 创建：`backend/README.md`
- 创建：`backend/.gitignore`

**接口：**
- 依赖：无
- 产出：用于 uv 依赖管理的项目配置文件

- [ ] **步骤 1：创建包含 uv 项目配置的 pyproject.toml**

```toml
[project]
name = "video-platform-backend"
version = "0.1.0"
description = "Video management platform backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.25",
    "aiosqlite>=0.19.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "apscheduler>=3.10.4",
    "python-multipart>=0.0.6",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "python-dotenv>=1.0.0",
    "ffmpeg-python>=0.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.4",
    "pytest-asyncio>=0.23.3",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "black>=24.1.0",
    "ruff>=0.2.0",
    "mypy>=1.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]
target-version = "py311"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **步骤 2：创建包含项目概览的 README.md**

```markdown
# Video Platform Backend

Backend API for video management platform.

## Development

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## Testing

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html
```
```

- [ ] **步骤 3：创建 .gitignore**

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
env.bak/
venv.bak/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/
data/
*.db
*.db-journal
.env
.env.local
```

- [ ] **步骤 4：提交**

```bash
cd backend
git add pyproject.toml README.md .gitignore
git commit -m "feat: create backend project structure and configuration"
```

---

### 任务 2：创建配置管理

**文件：**
- 创建：`backend/src/config.py`
- 创建：`backend/.env.example`

**接口：**
- 依赖：pyproject.toml 中的 pydantic-settings
- 产出：基于环境变量配置的 `Settings` 类

- [ ] **步骤 1：创建包含配置模板的 .env.example**

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./data/videos.db

# Video Storage
VIDEO_STORAGE_PATH=./data/videos
THUMBNAIL_PATH=./data/thumbnails

# API Settings
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Scan Settings
DEFAULT_SCAN_INTERVAL=3600
```

- [ ] **步骤 2：编写配置的失败测试**

```python
# tests/test_config.py
import os
from pydantic import ValidationError
import pytest

def test_load_default_settings():
    """Test that settings load with default values"""
    from src.config import Settings

    settings = Settings()

    assert settings.api_port == 8000
    assert settings.api_host == "0.0.0.0"
    assert "sqlite" in settings.database_url


def test_load_settings_from_env():
    """Test that settings load from environment variables"""
    os.environ["API_PORT"] = "9000"
    os.environ["API_HOST"] = "127.0.0.1"

    from src.config import Settings
    settings = Settings()

    assert settings.api_port == 9000
    assert settings.api_host == "127.0.0.1"


def test_invalid_port_raises_validation_error():
    """Test that invalid port raises ValidationError"""
    os.environ["API_PORT"] = "invalid"

    from src.config import Settings

    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **步骤 3：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_config.py -v
```
预期结果：失败，提示 "module 'src.config' not found"

- [ ] **步骤 4：编写 config.py 的最小实现**

```python
# backend/src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/videos.db"

    # Video Storage
    video_storage_path: str = "./data/videos"
    thumbnail_path: str = "./data/thumbnails"

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Scan Settings
    default_scan_interval: int = 3600

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings = Settings()
```

- [ ] **步骤 5：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_config.py -v
```
预期结果：通过

- [ ] **步骤 6：提交**

```bash
cd backend
git add src/config.py .env.example tests/test_config.py
git commit -m "feat: add configuration management with environment variables"
```

---

## 阶段二：数据库模型

### 任务 3：设置数据库基础设施

**文件：**
- 创建：`backend/src/database/base.py`
- 创建：`backend/src/database/session.py`
- 创建：`backend/src/database/__init__.py`

**接口：**
- 依赖：`src/config` 中的 `Settings`
- 产出：`async_session_maker`、`Base` 声明基类、`init_db()` 函数

- [ ] **步骤 1：编写数据库初始化的失败测试**

```python
# tests/test_database.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_database_initialization():
    """Test that database can be initialized"""
    from src.database import init_db, async_session_maker
    from sqlalchemy import text

    await init_db()

    async with async_session_maker() as session:
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = result.fetchall()
        # Should have no tables initially, just the database created
        assert isinstance(tables, list)
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_database.py -v
```
预期结果：失败，提示 "module 'src.database' not found"

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/database/base.py
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    pass
```

```python
# backend/src/database/session.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from .base import Base


# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

# Create async session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Initialize database and create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Dependency injection for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
```

```python
# backend/src/database/__init__.py
from .base import Base
from .session import engine, async_session_maker, init_db, get_session

__all__ = ["Base", "engine", "async_session_maker", "init_db", "get_session"]
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_database.py -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/database/ tests/test_database.py
git commit -m "feat: set up database infrastructure with async SQLAlchemy"
```

---

### 任务 4：创建视频源模型

**文件：**
- 创建：`backend/src/models/source.py`
- 创建：`backend/src/models/__init__.py`

**接口：**
- 依赖：`src.database.base` 中的 `Base`
- 产出：`VideoSource` 模型类

- [ ] **步骤 1：编写 VideoSource 模型的失败测试**

```python
# tests/test_models/test_source.py
import pytest
from datetime import datetime


@pytest.mark.asyncio
async def test_create_video_source():
    """Test creating a video source"""
    from src.models.source import VideoSource
    from src.database import async_session_maker

    source = VideoSource(
        name="Test Collection",
        path="/test/path",
        type="local",
        scan_interval=3600,
        is_active=True,
    )

    async with async_session_maker() as session:
        session.add(source)
        await session.commit()
        await session.refresh(source)

        assert source.id is not None
        assert source.name == "Test Collection"
        assert source.path == "/test/path"
        assert source.type == "local"
        assert source.scan_interval == 3600
        assert source.is_active is True
        assert source.created_at is not None


@pytest.mark.asyncio
async def test_video_source_type_validation():
    """Test that video source type must be valid"""
    from src.models.source import VideoSource
    from sqlalchemy.exc import IntegrityError

    source = VideoSource(
        name="Invalid Source",
        path="/test/path",
        type="invalid_type",  # Should be 'local', 'nas', or 'minio'
    )

    async with async_session_maker() as session:
        session.add(source)
        with pytest.raises(IntegrityError):
            await session.commit()
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_models/test_source.py -v
```
预期结果：失败，提示 "module 'src.models.source' not found"

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/models/source.py
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class VideoSource(Base):
    """Video source configuration for scanning videos from different locations."""

    __tablename__ = "video_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'local' | 'nas' | 'minio'
    scan_interval: Mapped[int] = mapped_column(Integer, default=3600)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )

    def __repr__(self) -> str:
        return f"<VideoSource(id={self.id}, name='{self.name}', type='{self.type}')>"
```

```python
# backend/src/models/__init__.py
from .source import VideoSource

__all__ = ["VideoSource"]
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_models/test_source.py -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/models/ tests/test_models/
git commit -m "feat: add VideoSource model"
```

---

### 任务 5：创建视频模型

**文件：**
- 修改：`backend/src/models/__init__.py`
- 创建：`backend/src/models/video.py`

**接口：**
- 依赖：`src.database.base` 中的 `Base`
- 产出：与 VideoSource 关联的 `Video` 模型类

- [ ] **步骤 1：编写 Video 模型的失败测试**

```python
# tests/test_models/test_video.py
import pytest
from datetime import datetime


@pytest.mark.asyncio
async def test_create_video():
    """Test creating a video record"""
    from src.models.video import Video
    from src.models.source import VideoSource
    from src.database import async_session_maker

    # Create a source first
    source = VideoSource(name="Test Source", path="/test", type="local")

    async with async_session_maker() as session:
        session.add(source)
        await session.commit()
        await session.refresh(source)

        # Create video
        video = Video(
            source_id=source.id,
            filepath="/test/video.mp4",
            title="Test Video",
            description="A test video",
            duration=600,  # 10 minutes
            file_size=1024000,
            format="mp4",
            resolution="1920x1080",
            rating=5,
            view_count=0,
        )

        session.add(video)
        await session.commit()
        await session.refresh(video)

        assert video.id is not None
        assert video.source_id == source.id
        assert video.title == "Test Video"
        assert video.duration == 600
        assert video.rating == 5
        assert video.view_count == 0


@pytest.mark.asyncio
async def test_video_source_relationship():
    """Test that video has relationship to source"""
    from src.models.video import Video
    from src.models.source import VideoSource
    from src.database import async_session_maker

    async with async_session_maker() as session:
        source = VideoSource(name="Test", path="/test", type="local")
        session.add(source)
        await session.commit()

        video = Video(
            source_id=source.id,
            filepath="/test/video.mp4",
            title="Video",
        )
        session.add(video)
        await session.commit()

        # Refresh to load relationship
        await session.refresh(video)

        assert video.source is not None
        assert video.source.name == "Test"
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_models/test_video.py -v
```
预期结果：失败，提示 "module 'src.models.video' not found"

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/models/video.py
from sqlalchemy import String, Integer, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from src.database.base import Base


class Video(Base):
    """Video metadata and information."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("video_sources.id", ondelete="CASCADE")
    )
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seconds
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_played_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )

    # Relationships
    source = relationship("VideoSource", backref="videos")

    def __repr__(self) -> str:
        return f"<Video(id={self.id}, title='{self.title}', filepath='{self.filepath}')>"
```

```python
# backend/src/models/__init__.py
from .source import VideoSource
from .video import Video

__all__ = ["VideoSource", "Video"]
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_models/test_video.py -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/models/video.py tests/test_models/test_video.py
git commit -m "feat: add Video model with source relationship"
```

---

### 任务 6：创建 Tag 和 VideoTag 模型

**文件：**
- 修改：`backend/src/models/__init__.py`
- 创建：`backend/src/models/tag.py`

**接口：**
- 依赖：`src.database.base` 中的 `Base`、`src.models.video` 中的 `Video`
- 产出：`Tag` 模型、`VideoTag` 关联表

- [ ] **步骤 1：编写 Tag 模型的失败测试**

```python
# tests/test_models/test_tag.py
import pytest


@pytest.mark.asyncio
async def test_create_tag():
    """Test creating a tag"""
    from src.models.tag import Tag
    from src.database import async_session_maker

    tag = Tag(name="Action", color="#ff0000")

    async with async_session_maker() as session:
        session.add(tag)
        await session.commit()
        await session.refresh(tag)

        assert tag.id is not None
        assert tag.name == "Action"
        assert tag.color == "#ff0000"


@pytest.mark.asyncio
async def test_video_tag_association():
    """Test many-to-many relationship between videos and tags"""
    from src.models.tag import Tag
    from src.models.video import Video
    from src.models.source import VideoSource
    from src.database import async_session_maker

    async with async_session_maker() as session:
        # Create source and video
        source = VideoSource(name="Test", path="/test", type="local")
        session.add(source)
        await session.commit()

        video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
        session.add(video)
        await session.commit()

        # Create tags
        tag1 = Tag(name="Action", color="#ff0000")
        tag2 = Tag(name="Sci-Fi", color="#00ff00")
        session.add(tag1)
        session.add(tag2)
        await session.commit()

        # Associate tags with video
        video.tags.extend([tag1, tag2])
        await session.commit()

        # Refresh and check
        await session.refresh(video)
        assert len(video.tags) == 2
        assert tag1 in video.tags
        assert tag2 in video.tags
        assert video in tag1.videos
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_models/test_tag.py -v
```
预期结果：失败，提示 "module 'src.models.tag' not found"

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/models/tag.py
from sqlalchemy import String, Integer, DateTime, ForeignKey, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from src.database.base import Base


# Association table for many-to-many relationship
video_tags = Table(
    "video_tags",
    Base.metadata,
    Column("video_id", ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """Tag for categorizing videos."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(20), default="#409eff")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )

    # Relationships
    videos = relationship("Video", secondary=video_tags, back_populates="tags")

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}')>"
```

注意：需要在 Video 模型中添加 tags 关联：

```python
# 在 backend/src/models/video.py 中，source 关联之后添加：
from src.models.tag import video_tags

# 在 Video 类中添加：
tags = relationship("Tag", secondary=video_tags, back_populates="videos")
```

还需要在 tag.py 中导入 Column：
```python
from sqlalchemy import String, Integer, DateTime, ForeignKey, Table, Column
```

```python
# backend/src/models/__init__.py
from .source import VideoSource
from .video import Video
from .tag import Tag, video_tags

__all__ = ["VideoSource", "Video", "Tag", "video_tags"]
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_models/test_tag.py -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/models/tag.py tests/test_models/test_tag.py
git commit -m "feat: add Tag model with many-to-many video relationship"
```

---

### 任务 7：创建其余模型（History、Favorites、Notifications、NewVideos、Subtitles）

**文件：**
- 修改：`backend/src/models/__init__.py`
- 创建：`backend/src/models/history.py`
- 创建：`backend/src/models/favorite.py`
- 创建：`backend/src/models/notification.py`
- 创建：`backend/src/models/new_video.py`
- 创建：`backend/src/models/subtitle.py`

**接口：**
- 依赖：现有模型中的 `Base`、`Video`
- 产出：额外的模型类

- [ ] **步骤 1：编写所有其余模型的失败测试**

```python
# tests/test_models/test_history.py
import pytest


@pytest.mark.asyncio
async def test_create_play_history():
    """Test creating play history record"""
    from src.models.history import PlayHistory
    from src.models.video import Video
    from src.models.source import VideoSource
    from src.database import async_session_maker

    async with async_session_maker() as session:
        source = VideoSource(name="Test", path="/test", type="local")
        session.add(source)
        await session.commit()

        video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
        session.add(video)
        await session.commit()

        history = PlayHistory(video_id=video.id, progress=120, completed=False)
        session.add(history)
        await session.commit()
        await session.refresh(history)

        assert history.id is not None
        assert history.video_id == video.id
        assert history.progress == 120
        assert history.completed is False


# tests/test_models/test_favorite.py
@pytest.mark.asyncio
async def test_create_favorite():
    """Test creating favorite"""
    from src.models.favorite import Favorite
    from src.models.video import Video
    from src.models.source import VideoSource
    from src.database import async_session_maker

    async with async_session_maker() as session:
        source = VideoSource(name="Test", path="/test", type="local")
        session.add(source)
        await session.commit()

        video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
        session.add(video)
        await session.commit()

        favorite = Favorite(video_id=video.id)
        session.add(favorite)
        await session.commit()
        await session.refresh(favorite)

        assert favorite.id is not None
        assert favorite.video_id == video.id


# tests/test_models/test_notification.py
@pytest.mark.asyncio
async def test_create_notification():
    """Test creating notification"""
    from src.models.notification import Notification
    from src.database import async_session_maker
    import json

    notification = Notification(
        type="scan_complete",
        title="Scan Complete",
        message="Found 5 new videos",
        data={"count": 5, "source_id": 1},
    )

    async with async_session_maker() as session:
        session.add(notification)
        await session.commit()
        await session.refresh(notification)

        assert notification.id is not None
        assert notification.type == "scan_complete"
        assert notification.read is False
        assert notification.data == {"count": 5, "source_id": 1}


# tests/test_models/test_new_video.py
@pytest.mark.asyncio
async def test_create_new_video():
    """Test creating new video record"""
    from src.models.new_video import NewVideo
    from src.models.video import Video
    from src.models.source import VideoSource
    from src.database import async_session_maker

    async with async_session_maker() as session:
        source = VideoSource(name="Test", path="/test", type="local")
        session.add(source)
        await session.commit()

        video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
        session.add(video)
        await session.commit()

        new_video = NewVideo(video_id=video.id, source_id=source.id)
        session.add(new_video)
        await session.commit()
        await session.refresh(new_video)

        assert new_video.id is not None
        assert new_video.video_id == video.id
        assert new_video.source_id == source.id
        assert new_video.viewed is False


# tests/test_models/test_subtitle.py
@pytest.mark.asyncio
async def test_create_subtitle():
    """Test creating subtitle record"""
    from src.models.subtitle import Subtitle
    from src.models.video import Video
    from src.models.source import VideoSource
    from src.database import async_session_maker

    async with async_session_maker() as session:
        source = VideoSource(name="Test", path="/test", type="local")
        session.add(source)
        await session.commit()

        video = Video(source_id=source.id, filepath="/test/video.mp4", title="Video")
        session.add(video)
        await session.commit()

        subtitle = Subtitle(
            video_id=video.id, language="zh", filepath="/test/sub.srt", label="中文"
        )
        session.add(subtitle)
        await session.commit()
        await session.refresh(subtitle)

        assert subtitle.id is not None
        assert subtitle.video_id == video.id
        assert subtitle.language == "zh"
        assert subtitle.label == "中文"
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_models/test_history.py tests/test_models/test_favorite.py tests/test_models/test_notification.py tests/test_models/test_new_video.py tests/test_models/test_subtitle.py -v
```
预期结果：失败，提示模块未找到

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/models/history.py
from sqlalchemy import Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class PlayHistory(Base):
    """Record of video playback."""

    __tablename__ = "play_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)  # seconds
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<PlayHistory(id={self.id}, video_id={self.video_id}, progress={self.progress}s)>"
```

```python
# backend/src/models/favorite.py
from sqlalchemy import Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class Favorite(Base):
    """Favorite videos."""

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )

    def __repr__(self) -> str:
        return f"<Favorite(id={self.id}, video_id={self.video_id})>"
```

```python
# backend/src/models/notification.py
from sqlalchemy import String, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base
from typing import Any


class Notification(Base):
    """System notifications."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type='{self.type}', title='{self.title}')>"
```

```python
# backend/src/models/new_video.py
from sqlalchemy import Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class NewVideo(Base):
    """Track newly discovered videos."""

    __tablename__ = "new_videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("video_sources.id", ondelete="CASCADE")
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )
    viewed: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<NewVideo(id={self.id}, video_id={self.video_id}, viewed={self.viewed})>"
```

```python
# backend/src/models/subtitle.py
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class Subtitle(Base):
    """Subtitle files for videos."""

    __tablename__ = "subtitles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False)
    label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )

    def __repr__(self) -> str:
        return f"<Subtitle(id={self.id}, video_id={self.video_id}, language='{self.language}')>"
```

```python
# backend/src/models/__init__.py
from .source import VideoSource
from .video import Video
from .tag import Tag, video_tags
from .history import PlayHistory
from .favorite import Favorite
from .notification import Notification
from .new_video import NewVideo
from .subtitle import Subtitle

__all__ = [
    "VideoSource",
    "Video",
    "Tag",
    "video_tags",
    "PlayHistory",
    "Favorite",
    "Notification",
    "NewVideo",
    "Subtitle",
]
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_models/ -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/models/ tests/test_models/
git commit -m "feat: add remaining database models (history, favorites, notifications, new_videos, subtitles)"
```

---

## 阶段三：FastAPI 应用设置

### 任务 8：创建主应用入口

**文件：**
- 创建：`backend/src/main.py`
- 创建：`backend/src/__init__.py`

**接口：**
- 依赖：`src.config` 中的 `Settings`、所有模型、数据库初始化
- 产出：带有 CORS 中间件的 FastAPI 应用实例

- [ ] **步骤 1：编写主应用的失败测试**

```python
# tests/test_main.py
import pytest
from fastapi.testclient import TestClient


def test_app_creation():
    """Test that FastAPI app can be created"""
    from src.main import app

    assert app is not None


def test_cors_middleware():
    """Test that CORS middleware is configured"""
    from src.main import app

    # Check for CORS middleware
    cors_middleware = None
    for middleware in app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            cors_middleware = middleware
            break

    assert cors_middleware is not None


def test_health_check():
    """Test health check endpoint"""
    from src.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_docs():
    """Test that API docs are available"""
    from src.main import app

    client = TestClient(app)
    response = client.get("/docs")

    assert response.status_code == 200
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_main.py -v
```
预期结果：失败，提示 "module 'src.main' not found"

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/__init__.py
# 用于包初始化的空文件
```

```python
# backend/src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.database import init_db

# Create FastAPI app
app = FastAPI(
    title="Video Platform API",
    description="Backend API for video management platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    await init_db()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_main.py -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/ tests/test_main.py
git commit -m "feat: create FastAPI application with CORS and health check"
```

---

## 阶段四：视频源管理 API

### 任务 9：创建 SourceService

**文件：**
- 创建：`backend/src/services/__init__.py`
- 创建：`backend/src/services/source_service.py`

**接口：**
- 依赖：`VideoSource` 模型、数据库会话
- 产出：具有 CRUD 操作的 `SourceService` 类

- [ ] **步骤 1：编写 SourceService 的失败测试**

```python
# tests/test_services/test_source_service.py
import pytest
from datetime import datetime


@pytest.mark.asyncio
async def test_create_source():
    """Test creating a video source"""
    from src.services.source_service import SourceService
    from src.database import async_session_maker

    async with async_session_maker() as session:
        service = SourceService(session)
        source = await service.create(
            name="My Collection",
            path="/media/collection",
            type="local",
            scan_interval=1800,
        )

        assert source.id is not None
        assert source.name == "My Collection"
        assert source.path == "/media/collection"
        assert source.type == "local"
        assert source.scan_interval == 1800


@pytest.mark.asyncio
async def test_list_sources():
    """Test listing all video sources"""
    from src.services.source_service import SourceService
    from src.database import async_session_maker

    async with async_session_maker() as session:
        service = SourceService(session)

        # Create multiple sources
        await service.create(name="Source 1", path="/path1", type="local")
        await service.create(name="Source 2", path="/path2", type="nas")
        await service.create(name="Source 3", path="/path3", type="minio")

        sources = await service.list_all()

        assert len(sources) == 3
        assert any(s.name == "Source 1" for s in sources)
        assert any(s.name == "Source 2" for s in sources)
        assert any(s.name == "Source 3" for s in sources)


@pytest.mark.asyncio
async def test_get_source_by_id():
    """Test getting a specific source by ID"""
    from src.services.source_service import SourceService
    from src.database import async_session_maker

    async with async_session_maker() as session:
        service = SourceService(session)
        created = await service.create(name="Test", path="/test", type="local")

        retrieved = await service.get_by_id(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test"


@pytest.mark.asyncio
async def test_update_source():
    """Test updating a source"""
    from src.services.source_service import SourceService
    from src.database import async_session_maker

    async with async_session_maker() as session:
        service = SourceService(session)
        created = await service.create(name="Original", path="/test", type="local")

        updated = await service.update(created.id, name="Updated", scan_interval=7200)

        assert updated.name == "Updated"
        assert updated.scan_interval == 7200


@pytest.mark.asyncio
async def test_delete_source():
    """Test deleting a source"""
    from src.services.source_service import SourceService
    from src.database import async_session_maker

    async with async_session_maker() as session:
        service = SourceService(session)
        created = await service.create(name="To Delete", path="/test", type="local")

        await service.delete(created.id)

        deleted = await service.get_by_id(created.id)
        assert deleted is None


@pytest.mark.asyncio
async def test_update_last_scan():
    """Test updating last_scan_at timestamp"""
    from src.services.source_service import SourceService
    from src.database import async_session_maker

    async with async_session_maker() as session:
        service = SourceService(session)
        created = await service.create(name="Test", path="/test", type="local")

        await service.update_last_scan(created.id)

        updated = await service.get_by_id(created.id)
        assert updated.last_scan_at is not None
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_services/test_source_service.py -v
```
预期结果：失败，提示 "module 'src.services.source_service' not found"

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/services/__init__.py
# 用于包初始化的空文件
```

```python
# backend/src/services/source_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.source import VideoSource
from datetime import datetime


class SourceService:
    """Service for managing video sources."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        name: str,
        path: str,
        type: str,  # noqa: A002
        scan_interval: int = 3600,
        is_active: bool = True,
    ) -> VideoSource:
        """Create a new video source."""
        source = VideoSource(
            name=name,
            path=path,
            type=type,
            scan_interval=scan_interval,
            is_active=is_active,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def get_by_id(self, source_id: int) -> VideoSource | None:
        """Get a source by ID."""
        result = await self.session.execute(
            select(VideoSource).where(VideoSource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = False) -> list[VideoSource]:
        """List all video sources."""
        query = select(VideoSource)
        if active_only:
            query = query.where(VideoSource.is_active == True)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        source_id: int,
        **kwargs,
    ) -> VideoSource:
        """Update a video source."""
        source = await self.get_by_id(source_id)
        if not source:
            raise ValueError(f"Source with id {source_id} not found")

        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)

        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def delete(self, source_id: int) -> None:
        """Delete a video source."""
        source = await self.get_by_id(source_id)
        if not source:
            raise ValueError(f"Source with id {source_id} not found")

        await self.session.delete(source)
        await self.session.commit()

    async def update_last_scan(self, source_id: int) -> None:
        """Update the last_scan_at timestamp for a source."""
        await self.update(source_id, last_scan_at=datetime.utcnow())
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_services/test_source_service.py -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/services/ tests/test_services/
git commit -m "feat: implement SourceService for video source CRUD operations"
```

---

### 任务 10：创建视频源 API 端点

**文件：**
- 创建：`backend/src/api/__init__.py`
- 创建：`backend/src/api/sources.py`

**接口：**
- 依赖：`src.services.source_service` 中的 `SourceService`
- 产出：用于视频源管理的 REST API 端点

- [ ] **步骤 1：编写视频源 API 端点的失败测试**

```python
# tests/test_api/test_sources.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with initialized database."""
    from src.main import app
    from src.database import init_db
    import asyncio

    # Initialize database
    asyncio.run(init_db())

    return TestClient(app)


def test_list_sources_empty(client):
    """Test listing sources when empty"""
    response = client.get("/api/sources")

    assert response.status_code == 200
    assert response.json() == []


def test_create_source(client):
    """Test creating a source"""
    data = {
        "name": "Test Collection",
        "path": "/test/path",
        "type": "local",
        "scan_interval": 3600,
    }

    response = client.post("/api/sources", json=data)

    assert response.status_code == 201
    result = response.json()
    assert result["name"] == "Test Collection"
    assert result["path"] == "/test/path"
    assert result["type"] == "local"
    assert result["scan_interval"] == 3600
    assert "id" in result


def test_get_source(client):
    """Test getting a specific source"""
    # Create a source first
    create_data = {
        "name": "Test Source",
        "path": "/test/path",
        "type": "local",
    }
    create_response = client.post("/api/sources", json=create_data)
    source_id = create_response.json()["id"]

    # Get the source
    response = client.get(f"/api/sources/{source_id}")

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == source_id
    assert result["name"] == "Test Source"


def test_update_source(client):
    """Test updating a source"""
    # Create a source first
    create_data = {"name": "Original", "path": "/test", "type": "local"}
    create_response = client.post("/api/sources", json=create_data)
    source_id = create_response.json()["id"]

    # Update the source
    update_data = {"name": "Updated", "scan_interval": 7200}
    response = client.put(f"/api/sources/{source_id}", json=update_data)

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Updated"
    assert result["scan_interval"] == 7200


def test_delete_source(client):
    """Test deleting a source"""
    # Create a source first
    create_data = {"name": "To Delete", "path": "/test", "type": "local"}
    create_response = client.post("/api/sources", json=create_data)
    source_id = create_response.json()["id"]

    # Delete the source
    response = client.delete(f"/api/sources/{source_id}")

    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(f"/api/sources/{source_id}")
    assert get_response.status_code == 404


def test_create_source_invalid_type(client):
    """Test creating a source with invalid type"""
    data = {"name": "Invalid", "path": "/test", "type": "invalid"}

    response = client.post("/api/sources", json=data)

    assert response.status_code == 422  # Validation error


def test_get_nonexistent_source(client):
    """Test getting a source that doesn't exist"""
    response = client.get("/api/sources/99999")

    assert response.status_code == 404
```

- [ ] **步骤 2：运行测试验证其失败**

```bash
cd backend
uv run pytest tests/test_api/test_sources.py -v
```
预期结果：失败，所有端点返回 404

- [ ] **步骤 3：编写最小实现**

```python
# backend/src/api/__init__.py
# 用于包初始化的空文件
```

```python
# backend/src/api/sources.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, validator
from typing import Literal
from src.database import get_session
from src.services.source_service import SourceService

router = APIRouter(prefix="/api/sources", tags=["sources"])


# Pydantic models
class SourceCreate(BaseModel):
    """Request model for creating a source."""

    name: str = Field(..., min_length=1, max_length=255)
    path: str = Field(..., min_length=1, max_length=1024)
    type: Literal["local", "nas", "minio"]
    scan_interval: int = Field(default=3600, ge=60, le=86400)
    is_active: bool = Field(default=True)


class SourceUpdate(BaseModel):
    """Request model for updating a source."""

    name: str | None = Field(None, min_length=1, max_length=255)
    path: str | None = Field(None, min_length=1, max_length=1024)
    type: Literal["local", "nas", "minio"] | None = None
    scan_interval: int | None = Field(None, ge=60, le=86400)
    is_active: bool | None = None


class SourceResponse(BaseModel):
    """Response model for a source."""

    id: int
    name: str
    path: str
    type: str  # noqa: A003
    scan_interval: int
    last_scan_at: str | None
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


# Helper function to get service
async def get_source_service(session: AsyncSession = Depends(get_session)) -> SourceService:
    """Dependency to get SourceService instance."""
    return SourceService(session)


# API Endpoints
@router.get("", response_model=list[SourceResponse])
async def list_sources(
    active_only: bool = False,
    service: SourceService = Depends(get_source_service),
) -> list[SourceResponse]:
    """List all video sources."""
    sources = await service.list_all(active_only=active_only)
    return sources


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(
    data: SourceCreate,
    service: SourceService = Depends(get_source_service),
) -> SourceResponse:
    """Create a new video source."""
    source = await service.create(
        name=data.name,
        path=data.path,
        type=data.type,
        scan_interval=data.scan_interval,
        is_active=data.is_active,
    )
    return source


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: int,
    service: SourceService = Depends(get_source_service),
) -> SourceResponse:
    """Get a specific video source."""
    source = await service.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int,
    data: SourceUpdate,
    service: SourceService = Depends(get_source_service),
) -> SourceResponse:
    """Update a video source."""
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        source = await service.update(source_id, **update_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    service: SourceService = Depends(get_source_service),
) -> None:
    """Delete a video source."""
    try:
        await service.delete(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

还需要在 main.py 中添加路由：

```python
# 在 backend/src/main.py 中，健康检查端点之后添加：
from src.api.sources import router as sources_router

app.include_router(sources_router)
```

- [ ] **步骤 4：运行测试验证其通过**

```bash
cd backend
uv run pytest tests/test_api/test_sources.py -v
```
预期结果：通过

- [ ] **步骤 5：提交**

```bash
cd backend
git add src/api/sources.py src/main.py tests/test_api/
git commit -m "feat: add source management API endpoints"
```

---

## 验证

完成所有任务后，验证实现：

```bash
# 1. 运行所有测试
cd backend
uv run pytest -v

# 2. 检查测试覆盖率
uv run pytest --cov=src --cov-report=term-missing

# 3. 启动服务器
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 4. 测试 API 端点
curl http://localhost:8000/health
curl http://localhost:8000/api/sources
curl http://localhost:8000/docs

# 5. 验证数据库
ls -la data/
```

预期结果：
- 所有测试通过（覆盖率 80% 以上）
- 服务器成功启动
- 健康检查返回 200
- API 文档可通过 /docs 访问
- SQLite 数据库已在 data/ 目录创建
- 可通过 API 创建/列出/更新/删除视频源

---

## 后续步骤

完成此计划后，继续进行：
1. 视频管理 API（CRUD、搜索、批量操作）
2. 扫描服务实现
3. 通知系统
4. FFmpeg 集成（转码和缩略图生成）

详见下一个实现计划。
