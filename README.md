# 🎬 Home Sites - 视频管理平台

个人视频管理、播放、扫描、转码的一站式解决方案。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📁 视频源管理 | 支持本地目录、NAS、MinIO 多种视频源 |
| 🎥 视频播放 | 流式播放、进度记忆、键盘快捷键、A-B 段重放 |
| 💬 字幕支持 | 扫描自动识别外挂字幕，播放器可切换轨道（SRT/ASS/VTT → WebVTT） |
| 🏷️ 标签管理 | 创建标签、为视频打标签、按标签筛选 |
| 📊 播放历史 | 记录播放进度、继续观看 |
| ⭐ 收藏功能 | 视频收藏/取消收藏 |
| 🔔 通知系统 | 扫描/转码任务通知 |
| 🔄 转码服务 | 支持 MP4/WebM/AVI/MKV 格式转换 |
| ⏰ 自动扫描 | 定时自动扫描新视频 |
| ⚙️ 应用设置 | 主题切换、扫描配置 |
| 🌙 深色模式 | 支持浅色/深色/跟随系统 |

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus |
| 后端 | Python 3.11+ + FastAPI + SQLAlchemy 2.0+ |
| 数据库 | SQLite 3（异步驱动） |
| 视频处理 | FFmpeg |
| 依赖管理 | uv（Python）、npm（Node.js） |

## 🚀 快速开始

### 前置要求

- Python 3.11+
- Node.js 18+
- FFmpeg（用于视频转码）
- uv（Python 包管理器）

### 安装步骤

```bash
# 克隆项目
git clone <repository-url>
cd home_sites

# 后端 setup
cd backend
uv sync

# 前端 setup
cd ../frontend
npm install
```

### 启动服务

```bash
# 启动后端（在 backend 目录）
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端（在 frontend 目录）
npm run dev
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

## 📁 项目结构

```
home_sites/
├── backend/                 # 后端服务
│   ├── src/
│   │   ├── api/            # API 路由（55 个端点）
│   │   ├── models/         # 数据模型（10 个）
│   │   ├── services/       # 业务逻辑
│   │   ├── scheduler/      # 定时任务
│   │   └── database/       # 数据库配置
│   ├── tests/              # 测试文件
│   └── pyproject.toml
├── frontend/                # 前端应用
│   ├── src/
│   │   ├── api/            # API 调用模块
│   │   ├── components/     # 可复用组件
│   │   ├── views/          # 页面组件（10 个）
│   │   ├── composables/    # 组合式函数
│   │   ├── layouts/        # 布局组件
│   │   ├── styles/         # 样式文件
│   │   └── router/         # 路由配置
│   ├── tests/              # 单元测试（Vitest + jsdom）
│   ├── e2e/                # 端到端测试（Playwright）
│   ├── vitest.config.ts
│   ├── playwright.config.ts
│   └── package.json
├── docs/                    # 文档
│   ├── specs/              # 设计文档
│   └── superpowers/        # 开发计划
├── CLAUDE.md                # 项目规范
├── CHANGELOG.md             # 更新日志
└── README.md                # 本文件
```

## 📖 API 文档

启动后端后访问 Swagger UI：http://localhost:8000/docs

### 主要 API 模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 视频源 | `/api/sources` | 视频源 CRUD |
| 视频 | `/api/videos` | 视频管理、播放 |
| 字幕 | `/api/videos/{id}/subtitles` | 字幕轨道管理与 WebVTT 输出 |
| 标签 | `/api/tags` | 标签管理 |
| 历史 | `/api/history` | 播放历史 |
| 收藏 | `/api/favorites` | 收藏功能 |
| 扫描 | `/api/scan` | 视频扫描 |
| 转码 | `/api/transcode` | 视频转码 |
| 通知 | `/api/notifications` | 通知管理 |
| 设置 | `/api/settings` | 应用设置 |
| 调度器 | `/api/scheduler` | 定时任务 |

## 🎯 使用指南

### 1. 添加视频源

1. 访问 http://localhost:5173/sources
2. 点击"添加视频源"
3. 填写视频源信息（名称、类型、路径）
4. 保存后点击"扫描"按钮

### 2. 观看视频

1. 访问 http://localhost:5173（首页）
2. 点击视频卡片进入详情页
3. 点击播放按钮开始观看
4. 播放进度会自动保存

### 3. 管理标签

1. 访问 http://localhost:5173/tags 创建标签
2. 在视频详情页点击 ➕ 按钮添加标签
3. 在首页使用标签筛选视频

### 4. 切换主题

1. 访问 http://localhost:5173/settings
2. 在"界面设置"中选择主题
3. 支持浅色/深色/跟随系统

### 5. 外挂字幕

1. 把字幕文件放在视频同目录，命名为 `视频名.srt`、`视频名.zh.srt`、`视频名.中文.vtt` 等（支持 srt / ass / ssa / vtt）
2. 在视频源页面点击"扫描"，字幕会自动登记为该视频的轨道
3. 播放视频中点击右下角 `CC` 按钮选择字幕，浏览器只渲染 WebVTT，其他格式由后端实时转换

### 6. A-B 段重放

1. 播放到想重复的起点，点击控制条上的 `A`
2. 继续播放（或拖动进度条）到终点，点击 `B`
3. 进度条上会高亮这段区间，播到 `B` 自动回到 `A` 继续循环
4. 点击 `✕` 清除区间；切换视频时也会自动清除

## 🔧 环境变量

创建 `backend/.env` 文件：

```env
DATABASE_URL=sqlite+aiosqlite:///./data/videos.db
VIDEO_STORAGE_PATH=./data/videos
THUMBNAIL_PATH=./data/thumbnails
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## 🧪 测试

```bash
# 后端测试
cd backend
uv run pytest

# 前端单元测试（Vitest + jsdom）
cd frontend
npm run test

# 前端端到端测试（Playwright，自带接口 mock，无需启动后端）
npm run test:e2e

# 前端构建检查
npm run build
```

首次运行 e2e 需要先装浏览器：`npx playwright install chromium`。国内网络下它默认的 `cdn.playwright.dev` 会重定向到 `storage.googleapis.com`，实测只有约 115 KB/s（镜像站 12 MB/s），上百 MB 的下载会看起来卡死。改用镜像站即可：

```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright npx playwright install chromium
```

## 📝 开发规范

- 所有文档使用中文
- 代码注释使用中文
- Git 提交信息使用英文（Conventional Commits）
- 详细规范请查看 [CLAUDE.md](./CLAUDE.md)

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**享受你的视频管理体验！** 🎬
