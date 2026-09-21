# 视频管理平台设计文档

**创建日期：** 2026-07-26
**状态：** 设计中
**版本：** 1.0

---

## 目录

1. [项目概述](#项目概述)
2. [架构设计](#架构设计)
3. [核心模块](#核心模块)
4. [数据模型](#数据模型)
5. [API 设计](#api-设计)
6. [前端设计](#前端设计)
7. [安全考虑](#安全考虑)
8. [部署方案](#部署方案)

---

## 项目概述

### 目标
构建一个支持 1000+ 视频的个人视频管理平台，具备扫描、播放、管理、转码等功能。

### 核心需求

> 下面的标记记的是**当前实现状态**（2026-09-21 核过代码，同日补上对象存储），不是当初的承诺：⬜ 那两项当初写了 ✅ 但实际没有落地，别照着它估工。

- ✅ 多视频源配置（本地目录、NAS：挂载后按本地路径添加，与本地共用同一份读取实现）
- ✅ 对象存储视频源（S3/MinIO）：`src/storage/` 那道接缝下的第二份实现， boto3 走通用 S3 协议，路径写 `s3://bucket/前缀`。**只读**：能列库、能 Range 播放，缩略图/转码/字幕四项因需要本地文件而关闭（见 `README.md` 使用指南第 9 节）
- ✅ 自动/手动扫描新视频
- ✅ 视频信息管理（标题、封面、简介）
- ✅ 分类/标签管理
- ✅ 搜索功能（文件名、标签、元数据）
- ✅ 播放历史/收藏
- ✅ 评分和标记"已观看"
- ✅ 字幕支持
- ⬜ 批量操作：没有多选，`POST /api/tags/video/{video_id}` 一次只加一个标签
- ✅ 视频转码（支持多种格式）
- ✅ 新视频提醒和标注

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Video.js |
| 后端 | Python 3.11+ + FastAPI + SQLAlchemy + APScheduler |
| 数据库 | SQLite 3 |
| 视频处理 | FFmpeg |
| 部署 | Docker Compose |
| 依赖管理 | uv |

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue 3 + TypeScript)            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │ 视频列表 │  │ 播放器   │  │ 视频详情 │  │ 管理设置 │   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │ REST API (Axios)
┌─────────────────────────▼───────────────────────────────┐
│              后端 (FastAPI + Python)                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │  API 路由层                                      │   │
│  │  /videos  /scan  /sources  /history  /tags ...   │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  业务逻辑层                                      │   │
│  │  视频管理  扫描服务  转码服务  封面生成         │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  数据访问层 (SQLAlchemy ORM)                     │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│              数据层                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  SQLite     │  │  视频文件   │  │  FFmpeg     │    │
│  │  数据库     │  │  (多源)     │  │  服务       │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 模块划分

#### 后端模块
```
backend/src/
├── main.py                    # 应用入口
├── config.py                  # 配置管理
├── models/                    # 数据模型
│   ├── video.py
│   ├── source.py
│   ├── tag.py
│   └── history.py
├── api/                       # API 路由
│   ├── videos.py
│   ├── sources.py
│   ├── scan.py
│   └── ...
├── services/                  # 业务逻辑
│   ├── video_service.py
│   ├── scan_service.py
│   ├── transcode_service.py
│   └── ...
├── utils/                     # 工具函数
│   ├── ffmpeg.py
│   ├── file_walker.py
│   └── ...
└── database/                  # 数据库
    ├── session.py
    └── base.py
```

#### 前端模块
```
frontend/src/
├── main.ts                    # 应用入口
├── App.vue                    # 根组件
├── router/                    # 路由
│   └── index.ts
├── stores/                    # 状态管理
│   └── video.ts
├── api/                       # API 调用
│   └── video.ts
├── components/                # 组件
│   ├── VideoList.vue
│   ├── VideoPlayer.vue
│   ├── NotificationCenter.vue
│   ├── NewVideoBadge.vue
│   └── ...
└── views/                     # 页面
    ├── VideoList.vue
    ├── VideoDetail.vue
    └── ...
```

---

## 核心模块

### 后端服务模块

| 模块 | 职责 | 主要方法 |
|------|------|---------|
| **VideoService** | 视频增删改查、搜索 | `get_videos()`, `update_video()`, `search()` |
| **SourceService** | 视频源管理 | `add_source()`, `list_sources()`, `scan_source()` |
| **ScanService** | 文件扫描、新视频检测 | `scan_directory()`, `detect_new()` |
| **TranscodeService** | 视频转码、格式转换 | `transcode()`, `check_format()` |
| **ThumbnailService** | 封面生成 | `generate_thumbnail()` |
| **HistoryService** | 播放历史记录 | `record_play()`, `get_history()` |
| **TagService** | 标签管理 | `add_tag()`, `get_videos_by_tag()` |
| **NotificationService** | 通知管理 | `create_notification()`, `mark_read()` |

### 前端组件模块

| 组件 | 职责 |
|------|------|
| **VideoList** | 视频列表、筛选、搜索 |
| **VideoPlayer** | 视频播放器、字幕、进度 |
| **VideoDetail** | 视频详情、编辑、评分 |
| **SourceManager** | 视频源配置、扫描 |
| **VideoScanner** | 扫描进度、结果展示 |
| **TagManager** | 标签管理、批量打标签 |
| **HistoryViewer** | 播放历史、收藏列表 |
| **NotificationCenter** | 通知列表、小红点显示 |
| **NewVideoBadge** | 视频源卡片上的新视频数角标 |
| **ScanProgressDialog** | 扫描进度条 |
| **ScanSummaryDialog** | 扫描完成结果弹窗 |

---

## 数据模型

### 数据库表结构

#### video_sources - 视频源
```sql
CREATE TABLE video_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    path VARCHAR(1024) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'local' | 'nas' | 'minio'
    scan_interval INTEGER DEFAULT 3600,  -- 自动扫描间隔（秒）
    last_scan_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### videos - 视频
```sql
CREATE TABLE videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES video_sources(id),
    filepath VARCHAR(1024) NOT NULL UNIQUE,
    title VARCHAR(512),
    description TEXT,
    duration INTEGER,  -- 时长（秒）
    file_size BIGINT,
    format VARCHAR(20),  -- 'mp4' | 'mkv' | 'avi' | ...
    resolution VARCHAR(20),  -- '1920x1080'
    thumbnail_path VARCHAR(1024),
    rating INTEGER DEFAULT 0,  -- 评分 1-5
    view_count INTEGER DEFAULT 0,
    last_played_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### tags - 标签
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    color VARCHAR(20) DEFAULT '#409eff',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### video_tags - 视频标签关联（多对多）
```sql
CREATE TABLE video_tags (
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (video_id, tag_id)
);
```

#### play_history - 播放历史
```sql
CREATE TABLE play_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    progress INTEGER DEFAULT 0,  -- 播放进度（秒）
    completed BOOLEAN DEFAULT FALSE
);
```

#### favorites - 收藏
```sql
CREATE TABLE favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### subtitles - 字幕
```sql
CREATE TABLE subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    language VARCHAR(10),  -- 'zh' | 'en' | ...
    filepath VARCHAR(1024),
    label VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### new_videos - 新视频记录
```sql
CREATE TABLE new_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES video_sources(id),
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    viewed BOOLEAN DEFAULT FALSE
);
```

#### notifications - 通知
```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type VARCHAR(50) NOT NULL,  -- 'scan_complete' | 'new_video' | ...
    title VARCHAR(255) NOT NULL,
    message TEXT,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data JSON  -- 存储关联数据
);
```

---

## API 设计

### 视频管理

```
GET    /api/videos              # 获取视频列表
GET    /api/videos/{id}         # 获取视频详情
PUT    /api/videos/{id}         # 更新视频信息
DELETE /api/videos/{id}         # 删除视频
GET    /api/videos/new          # 获取新视频列表
POST   /api/videos/new/{id}/viewed  # 标记已查看
POST   /api/videos/{id}/play    # 开始播放
POST   /api/videos/{id}/progress  # 上报播放进度
GET    /api/videos/search       # 搜索视频
```

### 视频源管理

```
GET    /api/sources             # 获取视频源列表
POST   /api/sources             # 添加视频源
PUT    /api/sources/{id}        # 更新视频源
DELETE /api/sources/{id}        # 删除视频源
POST   /api/sources/{id}/scan   # 扫描视频源
GET    /api/sources/{id}/scan/status  # 获取扫描状态
```

### 扫描服务

```
POST   /api/scan/all            # 扫描所有视频源
POST   /api/scan/stop           # 停止扫描
GET    /api/scan/progress       # 获取扫描进度
```

### 标签管理

```
GET    /api/tags                # 获取标签列表
POST   /api/tags                # 创建标签
PUT    /api/tags/{id}           # 更新标签
DELETE /api/tags/{id}           # 删除标签
GET    /api/tags/{id}/videos    # 获取标签下的视频
POST   /api/videos/{id}/tags    # 批量添加标签
DELETE /api/videos/{id}/tags/{tag_id}  # 移除标签
```

### 播放历史

```
GET    /api/history             # 获取播放历史
GET    /api/history/continue    # 获取继续播放列表
DELETE /api/history/{id}        # 删除历史记录
```

### 收藏

```
GET    /api/favorites           # 获取收藏列表
POST   /api/favorites/{video_id}  # 添加收藏
DELETE /api/favorites/{video_id}  # 移除收藏
```

### 通知

```
GET    /api/notifications       # 获取通知列表
GET    /api/notifications/unread # 获取未读数量
POST   /api/notifications/{id}/read  # 标记已读
POST   /api/notifications/read-all  # 全部标记已读
```

### 转码服务

```
POST   /api/transcode/{id}      # 转码视频
GET    /api/transcode/{id}/status  # 获取转码状态
```

---

## 前端设计

### 页面结构

```
/
├── /              # 首页（视频列表）
├── /videos/:id    # 视频详情
├── /sources       # 视频源管理
├── /tags          # 标签管理
├── /history       # 播放历史
├── /favorites     # 收藏列表
└── /settings      # 设置
```

### 组件设计

#### VideoCard 视频卡片
```vue
<VideoCard>
  - 封面图
  - 标题（含新视频 🆕 标注）
  - 评分、时长
  - 标签列表
  - 新视频角标（NEW 蓝色标记）
</VideoCard>
```

#### 新视频标注规则
| 发现时间 | 标注样式 | 颜色 |
|---------|---------|------|
| 1天内 | "NEW" | 蓝色 |
| 3天内 | "最近" | 绿色 |
| 7天内 | "本周" | 黄色 |
| 7天以上 | 无显示 | - |

#### 通知中心设计
```
通知中心
├── 小红点（显示未读数量）
├── 通知列表
│   ├── 扫描完成
│   ├── 新视频提醒
│   └── 转码完成
└── 操作按钮
    - 标记已读
    - 全部已读
```

### 数据流设计

#### 扫描新视频流程
```
用户点击"扫描"
  ↓
前端调用 POST /api/sources/{id}/scan
  ↓
后端 ScanService.scan_directory()
  ├── 遍历目录
  ├── 读取文件元信息
  ├── 与数据库对比
  │   ├── 已存在 → 跳过
  │   └── 不存在 → 标记为新视频
  ├── 提取视频信息（时长、分辨率）
  ├── 生成封面
  ├── 保存到数据库
  └── 创建通知记录
  ↓
返回扫描结果
  ↓
前端显示进度 + 弹出结果
  ↓
更新界面：通知小红点、视频源角标、新视频标注
```

#### 视频播放流程
```
用户点击视频播放
  ↓
前端调用 POST /api/videos/{id}/play
  ↓
后端 HistoryService.record_play()
  ├── 创建/更新播放记录
  ├── 更新观看次数
  └── 标记新视频为已查看
  ↓
返回播放URL
  ↓
前端 VideoPlayer 加载视频
  ↓
定期上报播放进度（每30秒）
  ↓
播放结束或用户关闭
  ↓
前端调用 POST /api/history/{id}/complete
  ↓
更新播放记录完成状态
```

---

## 安全考虑

### 文件访问安全
- 视频文件只提供 URL 流式传输，不直接暴露文件系统路径
- 对象存储不用签名 URL（原设计写的这条路已改）：桶的凭证只在后端，浏览器始终打 `/api/videos/{id}/stream`，由后端带 `Range` 去取那一段字节再流式转出。代价是多一跳带宽，换来的是端点与密钥都不进前端，也不必给每部片算签名过期时间
- 支持配置访问白名单

### API 安全
- API 响应统一格式，避免信息泄露
- 文件上传大小限制
- 路径遍历防护

### 数据安全
- SQLite 数据库文件权限控制
- 敏感配置不提交到代码仓库

---

## 部署方案

### 开发环境
```bash
# 后端
cd backend
uv sync
uv run python main.py

# 前端
cd frontend
npm install
npm run dev
```

### 生产环境
```bash
docker-compose up -d
```

### Docker Compose 服务
```
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
```

---

## 测试策略

### 后端测试
| 测试类型 | 工具 | 覆盖范围 |
|---------|------|---------|
| 单元测试 | pytest | 各 Service、工具函数 |
| 集成测试 | pytest + testcontainers | API 接口、数据库操作 |
| 性能测试 | locust | 并发扫描、播放压力测试 |

### 前端测试
| 测试类型 | 工具 | 覆盖范围 |
|---------|------|---------|
| 单元测试 | Vitest | 组件、工具函数 |
| E2E测试 | Playwright | 用户操作流程 |

---

## 附录

### 技术决策记录 (ADR)
详见 `docs/decisions/` 目录。

### 变更日志
详见 `CHANGELOG.md`。

### 常见问题
详见 `FAQ.md`。