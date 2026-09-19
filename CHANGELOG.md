# 更新日志

## 2026-09-19

### 界面改造：玻璃拟态 → 深色影院风

- **主题基座重写**：删除 `styles/glass.css`，新建 `styles/theme.css`。两套主题同源一套令牌（浅色纸白分层、深色近黑影院黑），去掉 `backdrop-filter`、渐变光斑与大圆角，圆角收敛为 `--radius-panel: 12px` / `--radius-tile: 10px`。`--glass-*` 与 `.glass-panel` 作为历史命名保留成主题钩子，各组件只消费变量
- **强调色拆成两档**：`--accent`（写在表面上的文字/图标色，浅色 `#5b48e0`、深色 `#a99dff`）与 `--accent-fill`（垫白字的实底色 `#6a58f5`）。同一个紫色无法同时满足白字 4.5:1 与深底 4.5:1，混用直接导致"紫底紫字"
- **顶栏与导航**：`MainLayout.vue` 的胶囊玻璃条改为实色 sticky 顶栏（1px 下边框分隔），导航项由玻璃胶囊改为文字 + 12% 紫染选中底
- **封面优先的卡片**：`VideoCard.vue` 去掉卡片外框与内边距，封面成为唯一视觉主体（圆角裁切、悬浮 1.04 缩放 + 投影、时长角标改深色底），标题/元信息/评分改为纯文字排布
- **数据色标签**：`el-tag` 的 `color` 属性落成内联 `background-color`，色相由用户自选，白字压上去最低只有 1.7:1。用主题底色覆一层 78% 不透明膜把它压成同色相浅染、文字回到主题文字色，色相由浅染与 1px 描边保留；纯 CSS 实现，不改组件逻辑
- **实底语义按钮**：深色下 Element Plus 的语义基色是给文字用的（偏亮），"扫描全部"白字压 `#67c23a` 只有 2.24:1、"删除"压 `#f56c6c` 2.9:1、未读角标 2.9:1；换成同色相深色档 `--success-solid` / `--danger-solid` / `--warning-solid`，浅色下语义色兼作两档所以整体取深
- **占位与次要文字**：Element Plus 占位色 `#a8abb2` 在白底只有 2.3:1，浅色下并到次要文字色；次要文字由 `#676e7c` 加深到 `#5f6673`，使其压在 12% 紫染底上也到 5:1
- **不动的部分**：`VideoPlayer.vue` 控制条保持原样（A-B 高亮段的紫色与进度条几何有 e2e 像素断言），只替换其余页面
- **验证**：浏览器实测两套主题 × 9 条路由，逐节点做 WCAG 相对亮度对比度计算（含 alpha 合成、隐藏节点过滤），每套 438 个文本节点全部 ≥4.5:1，0 例失败；浅色"添加视频源"对话框单独复核 10 节点通过。回归：前端单测 83 passed、Playwright e2e 25 passed、`npm run typecheck:test` 无输出、`npm run build` 入口 276.07 kB / gzip 90.24 kB 无体积告警
- **文档**：`frontend/CLAUDE.md` 的"使用 CSS 变量"与"深色模式"两节按新令牌重写，原文示例里的 `--primary-color` / `--bg-color` 系列早已不存在

## 2026-09-18

### 新增功能：播放器 A-B 段重放

- **控制条新增 A-B 组**：`VideoPlayer.vue` 在快进按钮之后加入 `A` / `B` / `✕` 三个按钮，`A` 记录当前播放位置为起点，`B` 记录终点，`✕` 仅在已标记时出现用于清除；鼠标悬停时按钮标题实时显示 `A 点：0:10` 这样的时间戳
- **区间校验**：`B` 按钮在播放位置尚未越过 `A` 之前保持禁用，重复标记 `A` 时若已落在旧终点之后则一并清掉旧终点，避免出现无意义区间
- **循环行为**：`timeupdate` 中检测播放位置到达 `B` 即回到 `A` 继续播放；拖动进度条越过 `B` 同样会被拉回 `A`，清除区间后恢复正常；切换视频自动清除
- **可视化**：进度条上用半透明高亮段（`.progress-loop`）画出 A-B 区间，两端是亮紫描边加柔光；区间有效时 A-B 组浮出一枚淡紫玻璃胶囊，与控制条的玻璃拟态风格一致，未标记时保持透明、不与相邻图标按钮抢视觉
- **测试**：`tests/components/VideoPlayer.spec.ts` 新增 5 例（B 在播放位置越过 A 前禁用、终点不晚于起点时拒绝、经过 B 回到 A 且高亮区间、进度条高亮段的绘制与清除、拖到 B 之后被拉回并在清除后放行），前端单测 78 → 83；另有 2 例浏览器端用例见下方"E2E 首次在本机跑通"

### 性能优化：入口 chunk 由 769 kB 降到 276 kB

- **告警真实原因不是路由分割**：`src/router/index.ts` 的 9 条路由本来就是 `() => import(...)` 动态导入。体积来自 `main.ts` 的 `app.use(ElementPlus)` 与 `import * as ElementPlusIconsVue` 后逐个 `app.component()`：前者引用了全部组件、后者把 293 个图标组件全部打进入口，tree-shaking 完全失效
- **改为按需注册**：`main.ts` 只 `app.use()` 模板里真正出现的 27 个组件（与 `grep -rhoE '<el-[a-z-]+'` 的结果逐一对应），图标交给各组件从 `@element-plus/icons-vue` 局部导入，不做全局注册；未新增任何依赖
- **`v-loading` 指令随组件一起丢了**：去掉 `app.use(ElementPlus)` 后 7 个视图的 `v-loading` 全部报 `Failed to resolve directive: loading`（在跑起来的页面里逐个路由验证时发现的，构建与单测都不会报）。补 `app.use(ElLoading)` 注册指令
- **效果**：`dist/assets/index-*.js` 769.67 kB / gzip 243.56 kB → 276.08 kB / gzip 90.25 kB，`client-*.js` 134.69 kB → 111.78 kB，`npm run build` 不再输出 "Some chunks are larger than 500 kB"
- **仍保留**：`element-plus/dist/index.css` 整包引入（入口 CSS 367.89 kB / gzip 50.45 kB）。改成按需样式需要引入 `unplugin-vue-components` 之类的插件并调整 CSS 顺序，玻璃拟态主题大量覆盖 Element Plus 样式，顺序一变就可能整片失效，本轮不动

### 修复问题：拖动进度条不是跳到点击位置

- **进度条按整台播放器的宽度算比例**：`VideoPlayer.vue` 的 `seek()` 用 `.video-player` 的矩形换算百分比，而点击目标是控制条中间那一段 `.progress-bar`，因此点击位置与落点时间不成比例、且随窗口宽度变化，表现为"随机跳动"。改为以进度条自身的矩形换算，并钳制在 0 ~ 时长之间
- **只有 click、没有真正的拖拽**：改为 `pointerdown` 起拖、在 `window` 上监听 `pointermove` / `pointerup` / `pointercancel`，指针移出进度条仍然跟手；组件卸载与切换视频时清理监听。拖拽期间填充条直接跟随指针（`fillPercent`），避免浏览器尚未完成 seek 时进度条回跳。`.progress-bar` 增加 `touch-action: none`，触屏拖动不再变成页面滚动
- **暂停时进度条完全点不到**：`v-if` 的大播放按钮覆盖层 `inset: 0` 覆盖整个画面且绘制在控制条之上，暂停状态点击进度条会命中它并变成"继续播放"。控制条加 `z-index: 2`
- **后缀 Range 返回了错误的字节**：`bytes=-N` 被解析成"前 N 字节"，而按 RFC 7233 它是"最后 N 字节"（moov 在文件尾部的 mp4 会用到），浏览器拿到错误字节会导致 seek 失败或重载。同时把超出文件末尾的区间收敛到 EOF 而不是回 416
- **验证**：真实浏览器（60 秒样片）点击进度条 25% / 50% / 90% 分别落在 14.9s / 29.9s / 53.9s（旧算法为 16s / 24.6s / 38.4s）；暂停态命中测试确认最上层元素为进度条
- **测试**：新增 `frontend/tests/components/VideoPlayer.spec.ts` 拖拽/点击跳转 7 例、`backend/tests/test_api/test_stream.py` Range 语义 10 例；前端单测 62 → 78 passed，后端 145 → 155 passed，`npm run build` 通过

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
- 剩余告警：单块 chunk 超过 500 kB，建议后续按路由做代码分割（后续复核：路由本就是动态导入，真实原因与修复见上方"性能优化"一节，告警已消除）

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
- **E2E 首次在本机跑通（20 → 25 例全绿）**：此前 Playwright 浏览器一直装不上，`npx playwright install chromium` 看似卡死。实测默认 `cdn.playwright.dev` 会 302 到 `storage.googleapis.com`，本机只有 115 KB/s（114.6 MiB 的 headless shell 要下 17 分钟），换 `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright` 后为 12 MB/s、一次装完。`README.md` 测试一节已记录该命令
- **e2e 改用真实片段**：接口替身原先给 `/videos/{id}/stream` 返回空 body，浏览器拿不到时长，所有跳转逻辑在 e2e 里根本无法执行。现在内联一段 1.8 KB 的真实 H.264 片段（`e2e/fixtures.ts` 的 `SAMPLE_MP4`，30 秒 / 64x36 / 1 fps），e2e 因此能验证真实的 seek 与真实像素布局，仍然不依赖后端与 FFmpeg
  - 片段必须是 16:9：一开始用 16x16 的方块，`<video>` 按固有宽高比把播放器撑高，控制条被顶到 720 高的视口之外，表现为"点击进度条毫无反应"（CDP 直接报 `Input.dispatchMouseEvent: Invalid parameters`）
  - 替身必须支持 Range：`route.fulfill` 不带 `Accept-Ranges`/`Content-Length` 时，Chromium 的 `video.seekable` 是空的 `[[0, 0]]`，即使 `buffered` 已经覆盖 0~30 秒、`readyState` 到 4，赋值 `currentTime` 也会被静默丢弃。新增 `respondMedia()` 按后端同样的语义处理 `bytes=N-` / `bytes=N-M` / 后缀区间并回 206
- **新增 e2e 用例**：`e2e/player.spec.ts` 补 5 例——真实时长显示、点击跳转（7.5s / 15s / 27s）、按住拖动全程跟手且越过两端收敛到 0 与时长（含松开后填充条不回弹）、A-B 段重放（按真实像素校验高亮段左右边界与宽度、经过 B 点回跳、清除后放行）、切换视频后区间自动清除
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
