# 🎬 Home Sites - 视频管理平台

个人视频管理、播放、扫描、转码的一站式解决方案。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🔐 登录与账号 | 全站默认需要登录（含封面、视频流、字幕这类原生请求），账号只能由命令行创建；会话存库，退出登录与踢下线立即生效，连续输错密码会临时锁定 |
| 👥 按人隔离的数据 | 收藏、播放进度、片单、观影统计、新片角标与通知已读都跟着账号走，两口子共用一个库也互不覆盖对方的进度 |
| 📁 视频源管理 | 支持本地目录、NAS、MinIO 多种视频源 |
| 🎥 视频播放 | 流式播放、从上次位置续播、键盘快捷键、A-B 段重放 |
| 💬 字幕支持 | 扫描自动识别外挂字幕，播放器可切换轨道（SRT/ASS/VTT → WebVTT），可调字号与延迟 |
| 🏷️ 标签管理 | 创建标签、为视频打标签、按标签筛选；扫描会按文件名自动补上系列名与字幕组标签 |
| 🎬 系列追更 | 文件名里的 `S01E02`、`第12集` 会被解析出来，首页"系列进度"横排说出每个系列看到第几集 |
| 🔍 多维度搜索 | 片名/简介/标签多词组合，支持 `源:`、`标签:`、`评分>=4`、`时长>40分钟`、`没看过` 等操作符，按相关度排序；关键词、标签、视频源、页码会同步到地址栏，链接可直接分享 |
| 📊 播放历史 | 记录播放进度、首页"继续观看"横排、卡片封面进度线 |
| ⭐ 收藏功能 | 视频收藏/取消收藏 |
| 🔔 通知系统 | 扫描/转码任务通知，已读状态按账号记，删除与清空是整个库共享的动作 |
| 🔄 转码服务 | 支持 MP4/WebM/AVI/MKV 格式转换 |
| ⏰ 自动扫描 | 定时自动扫描新视频 |
| 🗂️ 库内核对 | 扫描时找不到的文件标为"丢失"而非删记录，挂载回来后自动恢复；首页横幅给出"清理丢失记录"入口 |
| 📦 重复文件检测 | 视频源页按需检测：按大小与时长分组后再读文件首尾各 1MB 哈希确认，列出副本与可回收空间，一键移除多余记录（只删记录，不动磁盘） |
| 📈 观影统计 | `/stats` 页给出本月与区间观看时长、看过部数、最长连看天数，附逐日柱状图与标签时长分布（纯 CSS 绘制，无图表库） |
| 📝 片单/合集 | `/watchlists` 页把"今晚看这些"排队成一份份清单，影片详情页一个「片单」按钮即可勾选归属；移出与删除只动队列，影片留在库里 |
| ⚙️ 应用设置 | 主题切换、扫描配置 |
| 🌙 深色模式 | 支持浅色/深色/跟随系统 |
| ⌨️ 快捷键 | `/` 聚焦搜索框、`?` 打开快捷键说明；倍速、音量、字幕偏好记住上次选择 |

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus |
| 后端 | Python 3.11+ + FastAPI + SQLAlchemy 2.0+ |
| 数据库 | SQLite 3（异步驱动） |
| 视频处理 | FFmpeg |
| 依赖管理 | uv（Python）、npm（Node.js） |
| 认证 | Cookie 会话（服务端存 `sha256(token)`）+ bcrypt 口令哈希 |

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

### 建第一个账号

全站需要登录才能访问，而项目**没有注册接口**——账号只能在后端目录用命令行创建：

```bash
cd backend
uv run python -m src.cli create-user --username admin --role owner   # 密码交互式输入，至少 8 位
uv run python -m src.cli list-users                                 # 查看已有账号与上次登录时间
```

之后访问 http://localhost:5173 会先跳登录页。其余命令见 [使用指南 › 登录与账号](#8-登录与账号)。

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
│   │   ├── api/            # API 路由（74 个端点）
│   │   ├── models/         # 数据模型（17 张表）
│   │   ├── services/       # 业务逻辑
│   │   ├── middleware/     # 鉴权中间件（默认拒绝）
│   │   ├── scheduler/      # 定时任务
│   │   └── database/       # 数据库配置
│   ├── tests/              # 测试文件
│   └── pyproject.toml
├── frontend/                # 前端应用
│   ├── src/
│   │   ├── api/            # API 调用模块
│   │   ├── components/     # 可复用组件
│   │   ├── views/          # 页面组件（12 个）
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

除 `/api/auth/login`、`/api/auth/status` 与 `/health` 之外，所有 `/api/*` 都要带有效会话才回数据（未登录统一 401）。

### 主要 API 模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `/api/auth` | `POST login` / `POST logout` / `GET me` / `GET status` / `POST password`；无注册接口，账号走 CLI |
| 视频源 | `/api/sources` | 视频源 CRUD |
| 视频 | `/api/videos` | 视频管理、播放；`/api/videos/series` 汇总系列追更进度，`/api/videos/duplicates` 按需检测重复文件 |
| 字幕 | `/api/videos/{id}/subtitles` | 字幕轨道管理与 WebVTT 输出 |
| 标签 | `/api/tags` | 标签管理 |
| 历史 | `/api/history` | 当前账号的播放历史；`/api/history/stats` 汇总本人观看时长、连看天数与标签分布 |
| 收藏 | `/api/favorites` | 当前账号的收藏 |
| 片单 | `/api/watchlists` | 当前账号的手排队列（今晚看这些）；`?video_id=` 反查某部片在自己的哪些片单里，重名只在本人范围内冲突（409） |
| 扫描 | `/api/scan` | 视频扫描 |
| 转码 | `/api/transcode` | 视频转码 |
| 通知 | `/api/notifications` | 通知管理、单条删除、一键清空 |
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

### 7. 多维度搜索

首页搜索框里空格分词，词与词取交集，每个词同时匹配片名、简介和标签名：

1. `深夜 测试` 找片名或简介里同时出现这两个词的片子；`"深夜 测试"` 加引号按整句匹配
2. `源:NAS` 只在某个视频源里找，`标签:剧集` 只找挂了某个标签的片子（与右侧标签下拉等效，可叠加）
3. `评分>=4`、`时长>40分钟` 做数值筛选；`时长` 后的裸数字按分钟算，`评分` 不写单位即可
4. `没看过` / `未看完` / `已看完` 按你自己的观看状态过滤（同一片子在别人眼里是什么状态不影响结果）；`丢失` 只列扫描时找不到文件的记录
5. 命中片名排在只命中简介或标签前面；点搜索框右侧的 `?` 可以看完整语法

### 8. 登录与账号

1. 打开任意页面都会先跳到 `/login`，登录后回到原来的地址；顶栏右侧的用户胶囊里可以退出登录
2. 建号、改角色、列账号都在后端目录用命令行：

   ```bash
   uv run python -m src.cli create-user --username dad --display-name "爸爸"       # 默认 member 角色
   uv run python -m src.cli create-user --username admin --role owner
   uv run python -m src.cli list-users
   uv run python -m src.cli set-role --username dad --role owner
   uv run python -m src.cli revoke-sessions --username dad                        # 把某个账号的全部浏览器踢下线
   ```

3. 账号名限 3-64 位小写字母、数字与 `. _ -`（登录时大小写与首尾空格不影响），密码至少 8 位、上限 72 字节
4. 默认 12 小时过期，勾选"记住我 30 天"则按 30 天；期间持续使用会自动续期
5. 同一个账号连续输错密码 5 次会锁定 10 分钟（按"来源 IP + 账号"计，重启后端即清零）
6. 数据按账号隔离：收藏、播放进度、片单、观影统计、"新片"角标与通知已读都只算自己的，按别人的 id 改删自己的接口会拿到 404；影片本身、标签、视频源仍是全家共享的一份库
7. `owner` 与 `member` 目前都能调用全部接口，角色网关（管理类的写接口只归 owner）排在 M3
8. 升级到有账号之前的库会自动完成：加归属列、把老数据回填给**第一个** `create-user --role owner` 的账号，因此第一次建 owner 前请先复制一份 `data/videos.db`（备份文件如今等同于备份全家的登录凭据与观看记录）

## 🔧 环境变量

创建 `backend/.env` 文件：

```env
DATABASE_URL=sqlite+aiosqlite:///./data/videos.db
VIDEO_STORAGE_PATH=./data/videos
THUMBNAIL_PATH=./data/thumbnails
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# 认证（都可省略，下面是默认值）
SESSION_HOURS=12             # 普通会话有效期
REMEMBER_ME_DAYS=30          # 勾选"记住我"时的有效期
AUTH_COOKIE_SECURE=false     # 只在 https 访问时改 true，否则 Cookie 不会被发送
LOGIN_MAX_FAILURES=5         # 连续失败几次锁定
LOGIN_LOCKOUT_MINUTES=10     # 锁定多久
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
