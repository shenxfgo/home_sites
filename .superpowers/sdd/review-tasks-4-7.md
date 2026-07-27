# Tasks 4-7 Review Package

## 任务概述

**任务范围：** Tasks 4-7（数据库模型）
**提交哈希：** 6a0052f, b7269b6, 0a405e2, ba9bfb1
**测试状态：** 11/11 通过

## 任务规范

### Task 4: VideoSource 模型
**文件：**
- 创建：`backend/src/models/source.py`
- 创建：`backend/src/models/__init__.py`

**接口：**
- 依赖：`src.database.base` 中的 `Base`
- 产出：`VideoSource` 模型类

### Task 5: Video 模型
**文件：**
- 修改：`backend/src/models/__init__.py`
- 创建：`backend/src/models/video.py`

**接口：**
- 依赖：`src.database.base` 中的 `Base`
- 产出：与 VideoSource 关联的 `Video` 模型类

### Task 6: Tag 和 VideoTag 模型
**文件：**
- 修改：`backend/src/models/__init__.py`
- 创建：`backend/src/models/tag.py`

**接口：**
- 依赖：`src.database.base` 中的 `Base`、`src.models.video` 中的 `Video`
- 产出：`Tag` 模型、`VideoTag` 关联表

### Task 7: 其余模型
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

## 实现报告

### 创建的文件

**模型文件 (backend/src/models/)：**
- `__init__.py` - 包导出
- `source.py` - VideoSource 模型
- `video.py` - Video 模型（与 source 关联）
- `tag.py` - Tag 模型和 video_tags 关联表
- `history.py` - PlayHistory 模型
- `favorite.py` - Favorite 模型
- `notification.py` - Notification 模型
- `new_video.py` - NewVideo 模型
- `subtitle.py` - Subtitle 模型

**测试文件 (backend/tests/test_models/)：**
- `__init__.py` - 测试包初始化
- `conftest.py` - 测试夹具（内存数据库）
- `test_source.py` - VideoSource 测试
- `test_video.py` - Video 测试
- `test_tag.py` - Tag/VideoTag 测试
- `test_history.py` - PlayHistory 测试
- `test_favorite.py` - Favorite 测试
- `test_notification.py` - Notification 测试
- `test_new_video.py` - NewVideo 测试
- `test_subtitle.py` - Subtitle 测试

### 测试结果

所有 11/11 测试通过：
- test_source.py: 2/2 通过
- test_video.py: 2/2 通过
- test_tag.py: 2/2 通过
- test_history.py: 1/1 通过
- test_favorite.py: 1/1 通过
- test_notification.py: 1/1 通过
- test_new_video.py: 1/1 通过
- test_subtitle.py: 1/1 通过

### 偏差说明

1. **测试隔离：** 测试使用内存 SQLite 数据库（通过 `db_session` 夹具），而不是生产环境的 `async_session_maker`。这提供了适当的测试隔离——每个测试获得一个全新的数据库。

2. **类型验证：** 在 `VideoSource.type` 上添加了 `CheckConstraint` 以强制有效值（'local'、'nas'、'minio'），这是 `test_video_source_type_validation` 测试所要求的。计划中的模型代码只有注释但没有实际约束。

3. **异步会话兼容性：** 在 `Video.tags` 和 `Tag.videos` 关系中添加了 `lazy="selectin"` 以正确处理异步会话。默认的延迟加载策略会导致异步 SQLAlchemy 会话出现 `MissingGreenlet` 错误。

## 审查要点

### 1. 规范符合性
- 文件路径是否与计划一致
- 模型字段是否与设计文档一致
- 关系定义是否正确

### 2. 代码质量
- 无 print 语句
- 无硬编码值
- 异常处理完整
- 日志记录完整

### 3. 测试覆盖
- 测试文件存在
- 测试覆盖主要功能
- 测试通过

### 4. 文档
- docstring 完整
- 注释清晰

## 附录：实际代码

### source.py
```python
from sqlalchemy import String, Integer, Boolean, DateTime, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class VideoSource(Base):
    """Video source configuration for scanning videos from different locations."""

    __tablename__ = "video_sources"
    __table_args__ = (
        CheckConstraint("type IN ('local', 'nas', 'minio')", name="valid_source_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    scan_interval: Mapped[int] = mapped_column(Integer, default=3600)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )

    def __repr__(self) -> str:
        return f"<VideoSource(id={self.id}, name='{self.name}', type='{self.type}')>"
```

### video.py
```python
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
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    tags = relationship("Tag", secondary="video_tags", back_populates="videos", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Video(id={self.id}, title='{self.title}', filepath='{self.filepath}')>"
```

### tag.py
```python
from sqlalchemy import String, Integer, DateTime, ForeignKey, Table, Column
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
    videos = relationship("Video", secondary=video_tags, back_populates="tags", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}')>"
```

### history.py
```python
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
    progress: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<PlayHistory(id={self.id}, video_id={self.video_id}, progress={self.progress}s)>"
```

### favorite.py
```python
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

### notification.py
```python
from sqlalchemy import String, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class Notification(Base):
    """System notifications."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type='{self.type}', read={self.read})>"
```

### new_video.py
```python
from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class NewVideo(Base):
    """Newly discovered videos awaiting review."""

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

### subtitle.py
```python
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from src.database.base import Base


class Subtitle(Base):
    """Video subtitle tracks."""

    __tablename__ = "subtitles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.utcnow()
    )

    def __repr__(self) -> str:
        return f"<Subtitle(id={self.id}, video_id={self.video_id}, language='{self.language}')>"
```

### __init__.py
```python
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
