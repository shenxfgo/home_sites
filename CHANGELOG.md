# 更新日志

## 2026-09-18

### 界面改造

- **全站 UI 改为玻璃拟态风格**：半透明磨砂面板 + 渐变彩色背景 + 流动光斑 + 大圆角
  - 新增 `frontend/src/styles/glass.css` 设计令牌与主题基座，移除旧 `theme.css`
  - 引入 Element Plus 官方深色 `css-vars`，主色改为品牌紫 `#7c6cff`
- **布局改为顶部导航**：`MainLayout.vue` 移除左侧边栏，改为胶囊形玻璃顶栏（渐变 logo + 横向导航 + 通知中心）
- **组件风格统一**：VideoCard / SourceCard / NotificationCenter / VideoPlayer 套用玻璃卡片、悬浮上移动效、渐变角标与按钮
- **页面适配**：Home 新增渐变欢迎横幅与玻璃工具栏；Sources/History/Favorites/Transcode 占位图与卡片改用玻璃渐变；Settings/Tags 随全局 `el-card` 自动玻璃化
- **清理**：删除未使用的 Vite 脚手架残留 `HelloWorld.vue`、`style.css`

### 修复问题

端到端实测（扫描 → 播放 → 转码 → 收藏/历史 → 删除）发现并修复以下缺陷：

- **扫描含中文文件名的视频必然 500**：`ffprobe`/`ffmpeg` 的子进程输出按系统区域编码（中文 Windows 为 cp936）解码，抛 `UnicodeDecodeError` 后 stdout 变为 `None`。显式指定 `encoding="utf-8"`，并让单个文件失败只跳过（SAVEPOINT）而不中断整轮扫描
- **`/api` 双前缀导致请求 404**：`Transcode.vue` 与 `Sources.vue` 在 axios 实例（`baseURL: '/api'`）之外又写了 `/api/...`，转码页整页打不开、视频源扫描按钮全部失效
- **缩略图全站不显示**：界面直接把数据库里的文件路径绑到 `<img :src>`，改为统一走 `GET /api/videos/{id}/thumbnail`（新增 `thumbnailUrl()` helper）
- **转码进度与取消完全失效**：`TranscodeService` 按请求实例化，任务表是实例属性，因此状态永远返回 idle、取消永远 404。任务表改为模块级共享，并解析 `ffmpeg -progress` 输出实现真实进度、取消时真正结束 ffmpeg 进程并清理半成品文件
- **webm 转码必然失败**：音频编码器写死 `aac`，而 WebM 容器不允许 aac；改为按容器选择音频编码器（webm 用 `libopus`）
- **同格式转码会覆盖源文件**：`x.mp4 → mp4` 的输出路径与输入相同，`-y` 会直接毁掉原片；新增前置校验并拒绝
- **`/api/scan/progress` 与 `/api/scan/stop` 形同虚设**：与转码同类的请求态 bug，扫描状态改为模块级共享，并让扫描循环真正响应停止请求
- **删除有视频的视频源返回 500**：SQLAlchemy 试图把 `videos.source_id` 置空而该列 NOT NULL；改为显式级联删除。同时修复删除视频时收藏/历史/新视频/字幕行成为孤儿（SQLite 默认不启用外键，schema 里的 `ON DELETE CASCADE` 并不会生效）
- **播放历史显示"视频 #2"而非视频名**：`/api/history` 未返回标题，接口补充 `video_title`
- **无 404 路由**：访问未知路径为空白页，新增 `NotFound.vue` 与通配路由
- **测试**：新增 `tests/test_services/test_transcode_service.py`（转码状态共享、进度、取消、覆盖保护），后端用例 97 → 110

### 构建验证

- `npm run build`（`vue-tsc -b && vite build`）通过，先前报错的 tsconfig 项目引用问题已随本次改动消失
- 后端 `uv run pytest` 110 passed
- 剩余告警：单块 chunk 超过 500 kB，建议后续按路由做代码分割

### 前端测试

补齐了此前完全空白的前端测试（新增 devDependencies：`vitest`、`jsdom`、`@vue/test-utils`、`@vitest/coverage-v8`、`@playwright/test`）：

- **单元测试（Vitest，62 例 / 11 文件）**：`vitest.config.ts` + `tests/setup.ts`（全局注册 Element Plus 与图标、补 `ResizeObserver`、用例间清理 localStorage 与根节点主题标记）
  - `tests/api/`：axios 实例 `baseURL`、错误拦截器把后端 `detail` 透出为异常信息、`thumbnailUrl` 拼接；`paths.spec.ts` 自动遍历全部 api 模块，断言没有任何请求重复 `/api` 前缀（本次修复的 404 缺陷的回归护栏）
  - `tests/composables/useTheme.spec.ts`：浅色/深色/跟随系统的 `data-theme` 与 `dark` 类、localStorage 持久化、系统主题变更监听
  - `tests/components/`：VideoCard（缩略图地址、无缩略图占位、时长格式化、文件名兜底标题、标签超过 3 个折叠、新/本周角标、点击跳详情）、NotificationCenter（未读角标、单条已读减一、一键已读、空态）
  - `tests/views/`：Transcode（请求路径、进度条与轮询节奏、卸载即停止轮询、失败原因展示、确认后发起、未选格式拦截、取消任务、运行中禁用开始按钮）、Sources（列表、全部扫描、单源扫描、删除确认与取消、失败提示）、History（后端标题渲染、缺标题回退编号、继续观看、跳转、删除记录、空态）、NotFound
  - `tests/router.spec.ts`：路由表、未知路径落到 404、`document.title` 同步
- **端到端测试（Playwright，17 例）**：`playwright.config.ts` 自动拉起 `localhost:4173` 的 dev server；`e2e/fixtures.ts` 用一份带状态的接口替身覆盖整个 `/api`（含转码任务从 running 到 completed 的进度推进），因此 **E2E 不依赖后端与 FFmpeg**。覆盖首页缩略图真实解码、搜索过滤、卡片跳详情、历史标题回退、404 返回首页、转码全流程与取消、数据源扫描/删除、通知已读
- **脚本**：`npm run test` / `test:watch` / `test:coverage` / `test:e2e` / `typecheck:test`（`tsconfig.vitest.json` 单独纳入 `tests/`、`e2e/` 与两个配置的类型检查，不影响生产构建）
- **文档**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 的测试规范与命令改为实际可用内容（原先列出的 `npm run lint`、`npm run type-check` 脚本并不存在）

### 字幕支持

补齐设计文档里只有 `Subtitle` 模型、没有接口/发现/播放的最后一块功能：

- **扫描发现外挂字幕**：`backend/src/utils/subtitles.py` 识别视频同目录的 `.srt/.ass/.ssa/.vtt`（支持 `电影.srt`、`电影.zh.srt`、`电影.zh-CN.ass`、`电影.mp4.中文.vtt` 等命名），从文件名解析语言并生成轨道名；`ScanService.scan_source` 对新发现和**已入库**的视频都会登记字幕（按已存在字幕路径去重，重复扫描不产生重复行），扫描结果新增 `subtitles_found` / `total_subtitles`
- **字幕接口**：新增 `SubtitleService` 与 `backend/src/api/subtitles.py`
  - `GET /api/videos/{id}/subtitles` 列表、`POST` 登记同目录字幕文件、`DELETE /api/videos/{id}/subtitles/{sid}` 移除轨道
  - `GET /api/videos/{id}/subtitles/{sid}/stream` 输出 WebVTT；SRT 走纯 Python 转换，ASS/SSA 交给 `ffmpeg -f webvtt`，读取时按 UTF-8 → GB18030 回退（中文 Windows 常见编码）
  - **安全约束**：`POST` 只接受位于该视频所在目录之内的字幕文件，避免把接口变成任意本地文件读取入口
- **播放器加载轨道**：`frontend/src/api/subtitles.ts` + `types/subtitle.ts`；`VideoPlayer.vue` 挂载与切换视频时拉取轨道并渲染 `<track kind="subtitles">`，控制条新增 `CC` 菜单（关闭 / 各条字幕），因为播放器隐藏了原生控件，选中的轨道通过 `video.textTracks[].mode` 生效；补充 `video::cue` 底色
- **测试**：后端 110 → 145（字幕工具 12、`SubtitleService` 10、字幕 API 10、扫描登记 3），前端单元 62 → 71（`tests/components/VideoPlayer.spec.ts`）、E2E 17 → 20（`e2e/player.spec.ts`：详情页轨道渲染、菜单选中生效、无字幕不显示按钮），`npm run build` 与 `typecheck:test` 均通过
- **文档**：`README.md` 补充功能特性、API 模块与"外挂字幕"使用指引

## 2026-07-27

### 新增功能

#### 后端
- **Settings API** - 应用设置的增删改查接口
- **Setting 模型** - 存储应用配置的数据库模型

#### 前端
- **Settings 页面** - 应用设置界面，支持配置：
  - 扫描设置（自动扫描开关、间隔时间）
  - 转码设置（默认格式）
  - 缩略图设置（宽度、高度）
  - 界面设置（主题切换）

- **深色模式** - 完整的深色模式支持：
  - `useTheme` composable - 主题管理逻辑
  - `theme.css` - 深色模式样式定义
  - 支持浅色/深色/跟随系统三种模式
  - 主题保存到 localStorage

- **中文化** - 所有界面文字统一改为中文：
  - 侧边栏菜单
  - 页面标题
  - 按钮文字
  - 表单标签
  - 提示信息
  - 确认对话框

- **标签编辑功能** - 视频详情页支持添加/删除标签

- **扫描功能** - 视频源页面添加扫描按钮：
  - 扫描全部视频源
  - 扫描单个视频源

- **文档更新** - 新增和更新项目文档：
  - 创建 README.md - 项目说明文档
  - 更新 CLAUDE.md - 添加文档更新规范
  - 创建 CHANGELOG.md - 更新日志

### 修复问题

- **历史 API 500 错误** - 修复 `played_at` 字段类型不匹配问题
- **Settings API 404 错误** - 修复 API 路径重复 `/api` 前缀问题

### 文件变更

#### 新增文件
- `backend/src/models/setting.py` - Setting 数据模型
- `backend/src/api/settings.py` - Settings API 端点
- `frontend/src/api/settings.ts` - 前端 Settings API 模块
- `frontend/src/views/Settings.vue` - Settings 页面
- `frontend/src/views/Transcode.vue` - 转码页面
- `frontend/src/composables/useTheme.ts` - 主题管理 composable
- `frontend/src/styles/theme.css` - 深色模式样式
- `CHANGELOG.md` - 更新日志
- `README.md` - 项目说明文档

#### 修改文件
- `backend/src/main.py` - 注册 Settings 路由
- `backend/src/models/__init__.py` - 导入 Setting 模型
- `backend/src/api/history.py` - 修复 played_at 字段类型
- `frontend/src/main.ts` - 导入主题样式
- `frontend/src/App.vue` - 初始化主题
- `frontend/src/router/index.ts` - 添加转码页面路由
- `frontend/src/views/VideoDetail.vue` - 添加转码按钮和标签编辑功能
- `frontend/src/views/Sources.vue` - 添加扫描按钮
- `frontend/src/components/SourceCard.vue` - 添加扫描按钮
- `frontend/src/layouts/MainLayout.vue` - 深色模式支持
- `frontend/src/styles/global.css` - 全局样式
- `CLAUDE.md` - 更新项目文档，添加文档更新规范
- `frontend/CLAUDE.md` - 更新前端文档
- `.superpowers/sdd/progress.md` - 更新进度

## 2026-07-26

### 初始版本

- 后端基础框架搭建
- 前端基础框架搭建
- 数据模型定义
- API 端点实现
- 基础前端页面
