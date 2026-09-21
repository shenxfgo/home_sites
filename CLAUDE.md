# CLAUDE.md - 项目总体规范

## 项目概述

视频管理平台 - 支持 1000+ 视频的个人视频管理、播放、扫描、转码等功能。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus（播放器为手写组件，未引入 Video.js） |
| 后端 | Python 3.11+ + FastAPI + SQLAlchemy 2.0+ + APScheduler |
| 数据库 | SQLite 3（aiosqlite 异步驱动） |
| 认证 | Cookie 会话（服务端表存 token 摘要）+ bcrypt，不用 JWT：`<video>` / `<img>` / `<track>` 的原生请求带不了 `Authorization` |
| 视频处理 | FFmpeg |
| 依赖管理 | uv（Python）、npm（Node.js） |
| 部署 | 暂无容器编排：后端 `uv run uvicorn src.main:app`、前端 `npm run dev`（README 的公网部署一节是反代 https 的前提清单） |

## 已实现功能

| 功能 | 说明 |
|------|------|
| 登录与访问控制 | `users` + `sessions` 两张表，bcrypt 校验口令，Cookie 会话（存 `sha256(token)`）；`AuthMiddleware` 默认拒绝所有 `/api/*`，只放行登录与状态探测，非 GET 另需 `X-Requested-With: fetch`；连续失败按 IP+账号 锁定。没有注册接口：第一个账号由 `src/cli.py create-user` 建，之后 owner 可在 `/api/users` 或 `/users` 页建号 |
| 角色网关（owner / member） | 判定放在同一个中间件里，方向仍是默认拒绝：`MEMBER_WRITE_PATHS` 白名单列出成员唯一能写的路径（收藏、历史、片单、已读、播放进度、自己的偏好/密码/退出自己名下的某台设备），非 GET 且不在表内一律 403；`OWNER_ONLY_READ_PATHS` 把 `/api/users*`、`/api/settings*` 的**读**也收给 owner（"读接口只看登录"的有意例外）。需要拿到操作者身份的少数路由再挂 `require_owner`。护栏：不能停用/降级自己，必须留下一个可用 owner（400）。前端按这同一张表收口可见入口（连成员可访问页面上的库级按钮一起，见 `frontend/CLAUDE.md`） |
| 我的设备 | `GET /api/auth/sessions` 列出这个账号当前还有效的会话（按最近活动倒序），`DELETE /api/auth/sessions/{token_hash}` 只退掉其中一台、当前这台不动。`sessions` 没有自增 id，行的地址就是那枚 sha256 摘要（不是 Cookie 值，也推不回原 token），删除按 `(user_id, token_hash)` 联合定位——猜别人的摘要只会 404；`user_agent` 只用来决定界面这一行显示什么，任何判断都不看它 |
| 数据归属（按人隔离） | `favorites`/`play_history`/`watch_events` 带 `user_id`、`watchlists` 带 `owner_id`，`new_videos` 与 `notifications` 保持全局一行、已读改由 `new_video_reads`/`notification_reads` 记录；service 层每个方法第一个参数就是 `user_id`，按别人的 id 读写一律 404，`POST /api/watchlists` 重名（同一账号内）返回 409。老库首次启动自动迁移，无归属的行回填给第一个 owner 账号 |
| 偏好按人存 | `user_preferences(user_id PK, prefs JSON)` 与 `GET/PUT /api/preferences`，写入按键合并；目前只放 `theme`，倍速/音量/字幕字号与延迟仍在 `localStorage`（跟着浏览器走是刻意的，见认证设计文档的偏差说明）。`settings` 表退化为纯系统配置（扫描间隔、缩略图、默认转码格式），读写都限 owner |
| 视频源管理 | 三类源：本地、NAS（挂载后按本地路径添加，与本地共用同一份读取实现）、对象存储（`type=minio`，路径 `s3://bucket/前缀`，走 boto3，任何讲 S3 协议的服务都能连）。取文件统一收在 `src/storage/` 这道接缝后面，能力由 `Capabilities` 说明：对象存储只支持列举与 Range 播放，缩略图、转码、外挂与内嵌字幕对它关闭（路由返回中文 400）。类型与路径写法不匹配时创建/更新直接 400 |
| 视频列表 | 多维度搜索（片名/简介/标签多词 AND，`源:` `标签:` `评分>=` `时长>` `没看过` `丢失` 等操作符，按相关度排序）、标签与视频源筛选、分页；筛选条件同步到 URL query，链接可分享 |
| 视频播放 | 流式播放、进度记录、A-B 段重放、倍速与音量偏好持久化。Range 读取由 `src/storage/` 提供：本地/NAS 走 `FileResponse` + 分段，对象存储按 `Range` 拉对应字节后分块流式返回 |
| 字幕支持 | 扫描登记外挂字幕，后端转 WebVTT，播放器可切换轨道、调字号与延迟 |
| 标签管理 | 创建标签、视频打标签；扫描按文件名自动挂上系列名与字幕组标签 |
| 系列追更 | 文件名解析出 `S01E02`、`第12集` 等季集坐标（`videos.series/season/episode`），`GET /api/videos/series` 汇总每个系列看到第几集，首页横排与卡片角标展示 |
| 播放历史 | 记录本人的播放进度（每人每片一行）、首页"继续观看"横排、卡片封面进度线 |
| 收藏功能 | 视频收藏/取消收藏，只看得到自己的那份 |
| 通知系统 | 扫描/转码通知，全库一份；已读与未读数按账号算，单条删除与一键清空影响所有人，因此只归 owner |
| 转码服务 | 多格式转码 |
| 自动扫描 | APScheduler 定时扫描 |
| 库内核对 | 扫描时找不到的文件只置 `videos.is_missing`，行与历史保留；源整体够不着（挂载盘掉线、桶没配凭证或不可达）时不判定丢失；首页横幅可逐条走 `DELETE /api/videos/{id}` 清理 |
| 重复文件检测 | `GET /api/videos/duplicates`（只读）按 `file_size`+`duration` 分组后再读文件首尾各 1MB 做 SHA-256 确认，给出 `keep_id`（看过优先）与可回收空间；视频源页按需检测，删除仍走既有 DELETE。摘要口径只定义在 `src/utils/file_fingerprint.py`，本地与对象存储共用，跨源比对才对得上 |
| 观影统计 | 追加式日志 `watch_events` 记录每次进度的正增量，`GET /api/history/stats?days=N`（只读）按 UTC 日历天聚合出本月/区间时长、看过部数、最长连看与标签分布；`/stats` 页纯 CSS 画图，未引入图表库 |
| 片单/合集 | `watchlists` + `watchlist_items` 两张表存手排队列（按加入顺序，不记位置），`/api/watchlists` 7 个普通 CRUD 端点（含进出队列与 `?video_id=` 反查）；`/watchlists` 页可新建/改名/删除，影片详情页「片单」按钮勾选归属，移出与删除只动队列行、影片留在库里 |
| 应用设置 | `/settings` 只剩系统配置（owner 可见），主题这类个人偏好移到 `/profile` |
| 深色模式 | 支持浅色/深色/跟随系统，主题存在账号上、登录后按人拉回 |
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
│   │   ├── storage/        # 取文件的接缝：base（协议 + Capabilities）、local（本地/NAS）、s3
│   │   ├── middleware/     # 鉴权中间件（默认拒绝 + current_user 依赖）
│   │   ├── utils/          # 工具函数
│   │   ├── scheduler/      # 定时任务
│   │   ├── database/       # 数据库配置
│   │   ├── cli.py          # 账号管理命令行（建号/列账号/改角色/踢下线）
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
- 新增 `/api/*` 端点不必另写鉴权用例：`tests/test_middleware/test_auth.py` 会遍历 openapi 里每个非白名单端点断言匿名 401，`test_roles.py` 同样扫面断言 member 一律 403 —— 两张表（`MEMBER_WRITE_PATHS` / `OWNER_ONLY_READ_PATHS`）漏登记时红的是测试，不是线上
- 碰到"某个人的数据"的读写必须有隔离用例（`tests/test_services/test_isolation.py`、`tests/test_api/test_isolation.py`）：A 的列表里查不到 B 的行，A 按 B 的 id 改删要变成 404/报错；fixture 用 `make_user`/`user_id`（service 层）与 `make_signed_in_client`（再要一个登录客户端）

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
uv run python -m src.cli create-user --username admin --role owner  # 建账号（对外没有注册接口，第一个 owner 只能这样建）
uv run python -m src.cli list-users      # 列出账号
uv run python -m src.cli revoke-sessions # 踢下线（省略 --username 则清全部会话）
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

# Auth（有默认值，可整体省略）
SESSION_HOURS=12
REMEMBER_ME_DAYS=30
AUTH_COOKIE_SECURE=false      # 改 true 之前先确认站点走 https，否则 Cookie 不会发送
LOGIN_MAX_FAILURES=5
LOGIN_LOCKOUT_MINUTES=10
```

会话不签发自包含 token：`sessions` 表存的是 token 的 SHA-256，删行即失效，所以退出登录与踢下线是真实的。

「我的设备」里那一行的地址就是这枚摘要本身：`sessions` 的主键是 `token_hash`，没有自增 id，所以 `DELETE /api/auth/sessions/{token_hash}` 按 `(user_id, token_hash)` 联合定位——形状不对（不是 64 位十六进制）在路由层就是 422，属于别人或已经不存在的行是 404，两种情况都退不掉任何会话。响应里回到浏览器的是摘要而不是 Cookie 值，`user_agent` 只用于展示。

### 放到公网之前

- `AUTH_COOKIE_SECURE=true`，并且只有 https 入口。`sid` 是唯一凭据，明文 http 下被中间人拿走等于账号被拿走，而它还会随使用滑动续期
- 后端不解析 `X-Forwarded-*`：登录限流按 `request.client.host` + 账号计数，反代之后全家所有人的来源 IP 都压成反代那一台，一个人连错 5 次会把所有人锁 10 分钟。要么让 uvicorn 只信任本机反代并取 XFF（`--proxy-headers --forwarded-allow-ips=127.0.0.1`），要么调 `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_MINUTES`
- `CORS_ORIGINS` 精确到实际域名（带 Cookie 的跨域不能写 `*`）；`backend/.env` 与 `backend/data/` 留在仓库之外，`videos.db` 现在装着口令哈希与仍然有效的会话

完整清单见 README 的「公网部署注意事项」。

个人数据（收藏/进度/片单/统计/已读）都以 `user_id` 为键，影片库本身是共享的一份：`videos`、`tags`、`video_sources`、`subtitles` 都不加归属列，`videos.view_count`/`rating` 仍是全站热度。加归属列只能走 `init_db()` 的幂等 SQL（项目没有 Alembic），并且必须同时声明在模型上——测试用的内存库只跑 `create_all`；执行迁移前先复制一份 `data/videos.db`。

界面偏好走 `user_preferences.prefs` 这个 JSON  blob（按 `user_id` 一行，写入按键合并），不再往 `settings` 里塞个人字段：`settings` 是全家一份的系统配置，改一次所有人的播放都受影响，两者混在一张表里迟早有人在成员机器上写全局值。

## 注意事项

1. 所有文档使用中文
2. 代码注释使用中文
3. Git 提交信息使用英文
4. 数据库使用异步驱动（aiosqlite）
5. 视频文件路径使用相对路径或配置化
