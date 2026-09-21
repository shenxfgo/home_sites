# 🎬 Home Sites - 视频管理平台

个人视频管理、播放、扫描、转码的一站式解决方案。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🔐 登录与账号 | 全站默认需要登录（含封面、视频流、字幕这类原生请求），账号只能由命令行或管理员在 `/users` 页创建；会话存库，退出登录与踢下线立即生效，连续输错密码会临时锁定；`/profile` 的「登录设备」列出这个账号还挂在哪些浏览器上，可以只退掉其中一台 |
| 👥 按人隔离的数据 | 收藏、播放进度、片单、观影统计、新片角标与通知已读都跟着账号走，两口子共用一个库也互不覆盖对方的进度；主题偏好也按人保存，换台设备登录还是同一套界面 |
| 📁 视频源管理 | 支持本地目录、NAS（SMB/NFS 挂载后按本地路径添加）与对象存储（S3/MinIO/RustFS 等任何讲 S3 协议的服务，路径写成 `s3://bucket/前缀`）。对象存储是只读的：能列库、能按 Range 播放，缩略图、转码与字幕对它关闭，且要先装 `.[s3]` 依赖并配好凭证 |
| 🎥 视频播放 | 流式播放、从上次位置续播、键盘快捷键、A-B 段重放 |
| 💬 字幕支持 | 扫描自动识别外挂字幕，播放器可切换轨道（SRT/ASS/VTT → WebVTT），可调字号与延迟 |
| 🏷️ 标签管理 | 创建标签、为视频打标签、按标签筛选；扫描会按文件名自动补上系列名与字幕组标签 |
| 🎬 系列追更 | 文件名里的 `S01E02`、`第12集` 会被解析出来，首页"系列进度"横排说出每个系列看到第几集 |
| 🔍 多维度搜索 | 片名/简介/标签多词组合，支持 `源:`、`标签:`、`评分>=4`、`时长>40分钟`、`没看过` 等操作符，按相关度排序；关键词、标签、视频源、页码会同步到地址栏，链接可直接分享 |
| 📊 播放历史 | 记录播放进度、首页"继续观看"横排、卡片封面进度线 |
| ⭐ 收藏功能 | 视频收藏/取消收藏 |
| 🔔 通知系统 | 扫描/转码任务通知，已读状态按账号记，删除与清空是整个库共享的动作且只有管理员能做 |
| 🔄 转码服务 | 支持 MP4/WebM/AVI/MKV 格式转换 |
| ⏰ 自动扫描 | 定时自动扫描新视频 |
| 🗂️ 库内核对 | 扫描时找不到的文件标为"丢失"而非删记录，挂载回来后自动恢复；首页横幅给出"清理丢失记录"入口 |
| 📦 重复文件检测 | 视频源页按需检测：按大小与时长分组后再读文件首尾各 1MB 哈希确认，列出副本与可回收空间，一键移除多余记录（只删记录，不动磁盘）。本地与对象存储走同一份哈希口径，桶里的副本也能和本地块对得上 |
| 📈 观影统计 | `/stats` 页给出本月与区间观看时长、看过部数、最长连看天数，附逐日柱状图与标签时长分布（纯 CSS 绘制，无图表库） |
| 📝 片单/合集 | `/watchlists` 页把"今晚看这些"排队成一份份清单，影片详情页一个「片单」按钮即可勾选归属；移出与删除只动队列，影片留在库里 |
| ⚙️ 应用设置 | `/settings` 系统配置（扫描、转码、缩略图，只归管理员）；`/profile` 个人设置（主题、改密码、登录设备）；`/users` 账号管理 |
| 🌙 深色模式 | 支持浅色/深色/跟随系统，跟着账号走 |
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
uv sync                                      # 只跑起来用这个
uv sync --extra dev --extra s3               # 要跑测试、或打算接对象存储视频源

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

全站需要登录才能访问，而项目**没有注册接口**——第一个账号（家里唯一的管理员，也就是 owner）只能在后端目录用命令行创建，之后的账号可以由 owner 在 `/users` 页面上建：

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
│   │   ├── api/            # API 路由（65 条路径 / 84 个操作）
│   │   ├── models/         # 数据模型（18 张表）
│   │   ├── services/       # 业务逻辑
│   │   ├── storage/        # 取文件的接缝：本地/NAS 一份实现，S3/MinIO 一份实现
│   │   ├── middleware/     # 鉴权中间件（默认拒绝）
│   │   ├── scheduler/      # 定时任务
│   │   └── database/       # 数据库配置
│   ├── tests/              # 测试文件
│   └── pyproject.toml
├── frontend/                # 前端应用
│   ├── src/
│   │   ├── api/            # API 调用模块
│   │   ├── components/     # 可复用组件
│   │   ├── views/          # 页面组件（14 个）
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

除 `/api/auth/login`、`/api/auth/status` 与 `/health` 之外，所有 `/api/*` 都要带有效会话才回数据（未登录统一 401）；`member` 只能读库和改自己那份数据，管理面的写接口与 `/api/users`、`/api/settings` 一律 403。

### 主要 API 模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `/api/auth` | `POST login` / `POST logout` / `GET me` / `GET status` / `POST password`；`GET sessions` 与 `DELETE sessions/{token_hash}` 是"登录设备"的读与单台退出；无注册接口 |
| 账号管理 | `/api/users` | 仅 owner：列账号、建号、改角色、停用启用、重置密码、踢下线；没有删除账号，停用保留其历史 |
| 个人偏好 | `/api/preferences` | `GET` / `PUT`，按账号存那份偏好（目前是主题）；登录用户都能读写自己的 |
| 视频源 | `/api/sources` | 视频源 CRUD（owner）。`type` 取 `local` / `nas` / `minio`，`minio` 的路径必须以 `s3://` 开头，两者不匹配回 400；对象存储侧只读，没有上传或删除对象的操作 |
| 视频 | `/api/videos` | 视频管理、播放；`/api/videos/series` 汇总系列追更进度，`/api/videos/duplicates` 按需检测重复文件 |
| 字幕 | `/api/videos/{id}/subtitles` | 字幕轨道管理与 WebVTT 输出 |
| 标签 | `/api/tags` | 标签管理（写操作归 owner） |
| 历史 | `/api/history` | 当前账号的播放历史；`/api/history/stats` 汇总本人观看时长、连看天数与标签分布 |
| 收藏 | `/api/favorites` | 当前账号的收藏 |
| 片单 | `/api/watchlists` | 当前账号的手排队列（今晚看这些）；`?video_id=` 反查某部片在自己的哪些片单里，重名只在本人范围内冲突（409） |
| 扫描 | `/api/scan` | 视频扫描（owner） |
| 转码 | `/api/transcode` | 视频转码（owner） |
| 通知 | `/api/notifications` | 通知列表与已读按账号记；单条删除、一键清空影响所有人且只归 owner |
| 设置 | `/api/settings` | 系统配置，读写都限 owner（界面偏好已移到 `/api/preferences`） |
| 调度器 | `/api/scheduler` | 定时任务（owner） |

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

1. 点顶栏右侧的用户胶囊 → 「个人设置」（http://localhost:5173/profile）
2. 在"界面"里选主题，支持浅色/深色/跟随系统
3. 主题存进账号而不是这台浏览器：退出后换个账号登录会看到那个账号自己的主题

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

1. 打开任意页面都会先跳到 `/login`，登录后回到原来的地址；顶栏右侧的用户胶囊里可以进「个人设置」和退出登录
2. 两种建号途径，都要求密码至少 8 位：
   - owner 登录后打开 `/users`，可以建号、改角色、启用/停用、重置密码、把某个账号的全部浏览器踢下线
   - 命令行（第一个账号只能用这个方式建，因为那时还没有 owner）：

   ```bash
   uv run python -m src.cli create-user --username admin --role owner
   uv run python -m src.cli list-users
   uv run python -m src.cli set-role --username dad --role owner
   uv run python -m src.cli revoke-sessions --username dad                        # 把某个账号的全部浏览器踢下线
   ```

   对外仍然**没有注册接口**，`/api/users` 只归 owner 调用。
3. 账号名限 3-64 位小写字母、数字与 `. _ -`（登录时大小写与首尾空格不影响），密码至少 8 位、上限 72 字节
4. 默认 12 小时过期，勾选"记住我 30 天"则按 30 天；期间持续使用会自动续期
   - `/profile` 的「登录设备」列出这个账号当前还登录着的浏览器，按 User-Agent 显示成 `Chrome · Windows`、`Safari · iOS` 这样（认不出来就原样截一段），标出"当前设备"那一台，每行给出最近活动与有效期
   - 「退出」只退掉选中的那一台，正在用的这台不受影响；别人账号的设备不在列表里，猜地址也退不动（404）
   - 改密码会顺手退掉其他所有浏览器，只有当前这台保留
5. 同一个账号连续输错密码 5 次会锁定 10 分钟（按"来源 IP + 账号"计，重启后端即清零）
6. 数据按账号隔离：收藏、播放进度、片单、观影统计、"新片"角标与通知已读都只算自己的，按别人的 id 改删自己的接口会拿到 404；主题偏好也存进账号，换台设备登录还是同一套界面（倍速、音量、字幕字号/延迟仍按浏览器记）；影片本身、标签、视频源仍是全家共享的一份库
7. 角色分两档，判定方向都是默认拒绝：
   - `member` 只能读库和改自己那份数据；视频源增删改与扫描、转码、删视频、改视频元数据、标签管理、系统设置、删通知、账号管理一律 403，前端连入口都不显示（入口藏起来只是体验，中间件那一道才是真的拦截）
   - `/api/users`、`/api/settings` 连读都限 owner：账号清单、在线设备数、局域网路径对成员没有用处
   - 保底规则：不能停用或降级自己，也必须留下至少一个可用的 owner，否则返回 400 而不是把全家关在门外
8. 升级到有账号之前的库会自动完成：加归属列、把老数据回填给**第一个** `create-user --role owner` 的账号，因此第一次建 owner 前请先复制一份 `data/videos.db`（备份文件如今等同于备份全家的登录凭据与观看记录）

### 9. 对象存储视频源（S3 / MinIO）

1. 先补依赖再重启后端：`uv sync --extra s3`。不装也能正常启动，只是这类源读不到东西，接口会给中文提示
2. 在 `backend/.env` 里填 `S3_ACCESS_KEY_ID` 与 `S3_SECRET_ACCESS_KEY`；自建 MinIO/RustFS 再加 `S3_ENDPOINT_URL`（留空就是连 AWS）
3. `/sources` → 添加视频源 → 类型选 `S3 / MinIO`，路径写 `s3://bucket/前缀`（只到 bucket 就是扫整个桶）。类型和路径不匹配会直接 400，不会让你扫完发现是空的
4. 扫描与播放跟本地源一样：列表按前缀递归，播放走 HTTP Range，拖进度条只取那一段的字节
5. 这类源有几项能力是关掉的，前端连入口都不给，直接调接口返回中文 400 而不是 500：
   - 扫描时不生成缩略图（列表沿用无封面占位）
   - 不能转码、不能挂外挂字幕、取不了内嵌字幕

   原因只有一个：这些都要 FFmpeg 打开一个本地文件，对象存储给不了。需要它们就把片放回本地盘或挂载盘
6. 凭证写错、桶够不着时，这个源已入库的记录保持原样，**不会**被标成"丢失"——"读不到"和"文件真没了"是两回事
7. 重复文件检测跨得过去：桶里的副本与本地块用同一份"首尾各 1MB"哈希比对，故意不用 ETag（那是整文件 MD5，分片上传时又是另一套算法，混在一起比就永远匹配不上）

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

# 对象存储（只在添加 S3/MinIO 类型视频源时需要，见使用指南第 9 节）
S3_ENDPOINT_URL=             # 留空即连 AWS；自建 MinIO/RustFS 填 http://192.168.1.10:9000
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=            # 留空则对象存储源按"够不着"处理，不会把库读成空的
S3_SECRET_ACCESS_KEY=
S3_ADDRESSING_STYLE=auto     # 自建 MinIO 用域名寻址失败时改 path
```

## 🌐 公网部署注意事项

这个项目按"家里内网、可信的人用"来设计，鉴权本身没有公网假设。要把它放到能被互联网访问到的位置，下面几处必须先动：

1. **`AUTH_COOKIE_SECURE=true`，并且只通过 https 提供访问**。登录凭据就是 `sid` 这一枚 Cookie（`HttpOnly` + `SameSite=Lax`），明文 http 下它会被中间人直接拿走，而拿走等于拿走这个账号——会话还会随使用滑动续期，被偷的那枚可以一直有效。这一位只由配置决定，后端不看请求是从代理来的还是直连来的
2. **反代终止 https 时，把 `X-Forwarded-Proto` 一并转发**（`proxy_set_header X-Forwarded-Proto $scheme;`）。后端目前不解析任何 `X-Forwarded-*`，所以生成的绝对 URL、`request.url.scheme` 仍按后端自身的 http 计算——现在没有哪条响应依赖它，但加上这一条才不会在下次改动里变成坑
3. **登录限流在反代后会失真**：失败次数按 `(来源 IP, 账号)` 计，套一层反代之后全家所有人的来源 IP 都是反代那一台，某个人连续输错 5 次会把所有人一起锁在门外 10 分钟。两种解法：让 uvicorn 只信任你自己的反代并从 `X-Forwarded-For` 取真实来源（`--proxy-headers --forwarded-allow-ips=127.0.0.1`），或者把 `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_MINUTES` 调成能接受的组合。这一步不做，公网上的爆破会顺手把主人关在外面
4. **`CORS_ORIGINS` 填实际域名**。带 Cookie 的跨域必须精确到 origin，`*` 与凭据不能同时开
5. **`backend/.env` 与 `backend/data/` 不进仓库**（两者都已在 `.gitignore` 里）。`data/videos.db` 现在含 `users` 与 `sessions` 两张表，备份它等同于备份全家的口令哈希与仍在有效的登录凭据，别把它放进公开仓库、云盘共享目录或镜像里
6. **没有注册接口，也没有自助找回密码**：管理员密码丢了只能走命令行（`create-user` 建新 owner，或 `revoke-sessions` 把人踢下线）。公网部署前先确认自己还留着一条能进后端机器的路
7. **视频库对全体登录账号可见**：目前只有 owner / member 两档角色，member 能看能改自己那份数据，但没有"某个源只对某个人可见"这一层（要限制得另做 `source_acl`）。家里之外的人不要建账号

## 🧪 测试

```bash
# 后端测试（需要 .[dev] 依赖；没装 .[s3] 时对象存储的 2 个用例会跳过而不是报错）
cd backend
uv sync --extra dev --extra s3
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
