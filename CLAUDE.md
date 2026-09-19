# CLAUDE.md - 项目总体规范

## 项目概述

视频管理平台 - 支持 1000+ 视频的个人视频管理、播放、扫描、转码等功能。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus（播放器为手写组件，未引入 Video.js） |
| 后端 | Python 3.11+ + FastAPI + SQLAlchemy 2.0+ + APScheduler |
| 数据库 | SQLite 3（aiosqlite 异步驱动） |
| 视频处理 | FFmpeg |
| 依赖管理 | uv（Python）、npm（Node.js） |
| 部署 | Docker Compose |

## 已实现功能

| 功能 | 说明 |
|------|------|
| 视频源管理 | 本地/NAS/MinIO 视频源配置 |
| 视频列表 | 多维度搜索（片名/简介/标签多词 AND，`源:` `标签:` `评分>=` `时长>` `没看过` `丢失` 等操作符，按相关度排序）、标签与视频源筛选、分页；筛选条件同步到 URL query，链接可分享 |
| 视频播放 | 流式播放、进度记录、A-B 段重放、倍速与音量偏好持久化 |
| 字幕支持 | 扫描登记外挂字幕，后端转 WebVTT，播放器可切换轨道、调字号与延迟 |
| 标签管理 | 创建标签、视频打标签；扫描按文件名自动挂上系列名与字幕组标签 |
| 系列追更 | 文件名解析出 `S01E02`、`第12集` 等季集坐标（`videos.series/season/episode`），`GET /api/videos/series` 汇总每个系列看到第几集，首页横排与卡片角标展示 |
| 播放历史 | 记录播放进度、首页"继续观看"横排、卡片封面进度线 |
| 收藏功能 | 视频收藏/取消收藏 |
| 通知系统 | 扫描/转码通知，支持单条删除与一键清空 |
| 转码服务 | 多格式转码 |
| 自动扫描 | APScheduler 定时扫描 |
| 库内核对 | 扫描时找不到的文件只置 `videos.is_missing`，行与历史保留；源目录整体不可访问时不判定；首页横幅可逐条走 `DELETE /api/videos/{id}` 清理 |
| 应用设置 | 主题切换、扫描配置 |
| 深色模式 | 支持浅色/深色/跟随系统 |
| 全局快捷键 | `/` 聚焦搜索框、`?` 打开快捷键说明（输入框内不拦截） |

## 📋 文档更新规范

**重要规则：当增加或修改系统功能时，必须同步更新以下文档：**

### 触发条件

以下操作需要触发文档更新：
1. 新增 API 端点
2. 新增/修改数据模型
3. 新增前端页面或组件
4. 修改现有功能行为
5. 新增配置项
6. 修复重要 Bug

### 需要更新的文档

| 文档 | 更新内容 |
|------|----------|
| `CHANGELOG.md` | 记录变更内容、新增功能、修复问题 |
| `README.md` | 更新功能列表、API 文档链接 |
| `CLAUDE.md` | 更新已实现功能列表 |
| `frontend/CLAUDE.md` | 前端相关变更 |
| `backend/CLAUDE.md` | 后端相关变更 |

### 更新模板

**CHANGELOG.md 格式：**
```markdown
## YYYY-MM-DD

### 新增功能
- 功能描述

### 修复问题
- 问题描述

### 文件变更
- 新增文件: xx 个
- 修改文件: xx 个
```

### 检查清单

完成代码修改后，请确认：
- [ ] CHANGELOG.md 已更新
- [ ] README.md 功能列表已更新（如有新功能）
- [ ] CLAUDE.md 已实现功能已更新（如有新功能）
- [ ] API 文档已更新（如有新端点）

## 项目结构

```
home_sites/
├── backend/                 # 后端服务
│   ├── src/                # 源代码
│   │   ├── api/            # API 路由
│   │   ├── models/         # 数据模型
│   │   ├── services/       # 业务逻辑
│   │   ├── utils/          # 工具函数
│   │   ├── scheduler/      # 定时任务
│   │   ├── database/       # 数据库配置
│   │   ├── config.py       # 配置管理
│   │   └── main.py         # 应用入口
│   ├── tests/              # 测试文件
│   └── pyproject.toml      # 项目配置
├── frontend/                # 前端应用
│   ├── src/
│   │   ├── api/            # API 调用
│   │   ├── components/     # 组件
│   │   ├── views/          # 页面
│   │   ├── router/         # 路由
│   │   ├── types/          # TypeScript 类型
│   │   ├── layouts/        # 布局
│   │   └── styles/         # 样式
│   └── package.json
└── docs/                    # 文档
    ├── specs/              # 设计文档
    └── superpowers/        # 开发计划
```

## 开发规范

### 代码风格

**后端（Python）：**
- 遵循 PEP 8
- 4 空格缩进
- 使用 async/await 处理 I/O
- 类型提示（Type Hints）
- Docstring 文档

**前端（TypeScript）：**
- Vue 3 Composition API
- `<script setup>` 语法
- TypeScript 严格模式
- ESLint + Prettier 格式化

### 提交规范

使用 Conventional Commits：
```
feat: 新功能
fix: 修复
docs: 文档
style: 格式
refactor: 重构
test: 测试
chore: 构建/工具
```

### 测试要求

**后端：**
- 所有 Service 必须有单元测试
- 所有 API 必须有集成测试
- 测试覆盖率 > 80%

**前端：**
- 关键组件有单元测试
- E2E 测试覆盖主要流程

## 运行命令

### 后端
```bash
cd backend
uv sync                    # 安装依赖
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000  # 启动开发服务器
uv run pytest              # 运行测试
```

### 前端
```bash
cd frontend
npm install                # 安装依赖
npm run dev                # 启动开发服务器
npm run build              # 构建生产版本（vue-tsc -b && vite build）
npm run test               # 单元测试（Vitest，tests/ 目录）
npm run test:watch         # 单元测试 watch 模式
npm run test:coverage      # 单元测试 + 覆盖率
npm run test:e2e           # 端到端测试（Playwright，自动拉起 dev server）
npm run typecheck:test     # 只检查测试代码类型
```

## API 文档

启动后端后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 环境变量

创建 `.env` 文件配置：
```env
DATABASE_URL=sqlite+aiosqlite:///./data/videos.db
VIDEO_STORAGE_PATH=./data/videos
THUMBNAIL_PATH=./data/thumbnails
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## 注意事项

1. 所有文档使用中文
2. 代码注释使用中文
3. Git 提交信息使用英文
4. 数据库使用异步驱动（aiosqlite）
5. 视频文件路径使用相对路径或配置化
