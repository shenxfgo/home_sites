# 更新日志

## 2026-09-20

### 新增功能：片单/合集，"今晚看这些"先排成一份队列

- **两张表而不是一个 JSON 字段**：`watchlists(name, description, created_at)` + `watchlist_items(watchlist_id, video_id, added_at)`，后者带 `UniqueConstraint(watchlist_id, video_id)` 与 `cascade="all, delete-orphan"`。用真正的关联实体而不是 `Table` 中间表，是因为接口要立刻把刚改完的队列返回去。顺序按加入时间排（`order_by("WatchlistItem.id")`），没有 `position` 列——本片单不支持手工拖动排序
- **一个 SQLAlchemy 异步坑**：同一个 session 里做了原始插入/删除之后，身份映射中的 ORM 对象仍持有**旧的集合**，直接返回会给前端一份过期的队列（实测 11 个用例连片单都读成空的）。`watchlist_service._with_videos()` 统一带 `execution_options(populate_existing=True)`，写入方法一律重新查一遍再返回；`create()` 也不能直接返回刚 `add` 的对象，那时集合根本还没加载，访问即 `MissingGreenlet`
- **端点**：新增 7 个普通 CRUD —— `GET/POST /api/watchlists`（`GET` 支持 `?video_id=` 反查这部片在哪些片单里）、`GET/PUT/DELETE /api/watchlists/{id}`、`POST /api/watchlists/{id}/videos`、`DELETE /api/watchlists/{id}/videos/{video_id}`。**没有新增任何能碰磁盘或提权的端点**，删除片单只删排队行，删影片时 `WatchlistItem` 已加进 `delete_videos_cascade` 的表清单
- **界面**：顶栏第 6 项"片单"→ `/watchlists`，每份片单一张卡：片名按序号排列、显示"已看"位置、时长求和（`2 部 · 共 1:01:05`），可新建/重命名/移出/删除。影片详情页加「片单」按钮，弹窗里勾选归属（进入时按后端返回的队列预勾），保存只发差集；弹窗底部还能直接"新建片单并加入"
- **文案讲清楚边界**：移出的 toast 明写"已把「X」移出片单，影片仍在库里"，删除片单的确认框明写"影片本身不会被动"——都是实测行为，不是措辞
- **测试**：后端 245 → 261 passed（服务层 9 例、新端点 7 例，含"删片单不动影片""删影片清队列"）；前端单测 182 → 199 passed（片单页 13 例、详情页弹窗 4 例）；Playwright e2e 50 → 55 passed；`npm run build`、`npm run typecheck:test` 通过
- **验证**：隔离后端（临时库 + `:8010`，前端 `:4173` 代理过去，用完即删），种 3 部片 + 2 份片单（一份两条队列、一份空）。真实浏览器实测：顶栏顺序 `首页/视频源/播放历史/观影统计/收藏/片单/标签管理/设置`，页首"2 个片单 · 2 条排队"，队列两行 `1 深夜测试 1:05 · 已看 0:42`、`2 周末纪录片 1:00:00`（行高 56/53px），空片单只留一句"这个片单还空着，去影片详情页点「加入片单」"。详情页弹窗预勾正确（`今晚看这些 2 部` checked、`还没排片 0 部` 未勾），勾上后者保存 → 页首变"3 条排队"且空片单里出现该片；点"移出" → toast"已把「深夜测试」移出片单，影片仍在库里"，同时直接 `GET /api/videos/1` 仍是 **200 `深夜测试`**，库里那行确实没动；删除片单先弹确认（文案含"影片本身不会被动"），取消后仍是 2 张卡、确认后 1 张且 `GET /api/watchlists` 只剩 `还没排片`。两套主题取值：浅色卡底 `rgb(255,255,255)` / 边框 `rgb(226,228,234)` / 圆角 12px / 正文 `rgb(23,25,31)`，深色卡底 `rgb(20,23,30)` / 边框 `rgb(38,43,54)` / 正文 `rgb(233,235,239)` / 页面底 `rgb(11,13,18)`
- **已知边界**：片单不支持拖拽排序与跨片单去重（同一部片可以同时在几份片单里，各占一条），也不做"看完自动出队"——那需要另一套与统计页联动的规则

### 新增功能：观影统计页，本月看了多少小时、连看了几天

- **为什么要加一张表**：`play_history` 每部片只有一行，存的是"看到哪儿"，问不出"这个月看了多久"。新增追加式日志 `watch_events(video_id, seconds, occurred_at)`，`occurred_at` 上建索引；删除视频时随级联一起清（`delete_videos_cascade` 的表清单已加）
- **写入点只有一个**：`VideoService.update_progress` 里算增量 `gained = max(0, 新进度 - 旧进度)`，只有正数才落一行。往回拖进度条不计数，同一秒不会被算两次；`play` 与 `progress` 都走这条路，不需要第二个写入点
- **端点**：只新增 1 个只读聚合 `GET /api/history/stats?days=N`（7–365，默认 30，注册在 `/{history_id}` 之前），返回总量、本月量、看过部数、有记录天数、最长连看、逐日数组与标签分布，**没有新增任何能碰磁盘或提权的端点**
- **口径写进代码注释**：日界取 UTC 日历天（与库里的存储一致，东八区凌晨的观看会归到前一天），区间按天数零填充以保证图表每天有柱子；"本月"是墙上那个自然月的 1 号起算，不是"最近 30 天"
- **界面**：顶栏第 4 项"观影统计"→ `/stats`。四张数字卡（本月观看 / N 天内 / 看过影片 / 最长连看）、一张逐日柱状图、一段标签时长条。柱高与标签条宽都按区间内最大值百分比算，**没有引入任何图表库**，纯 CSS 绘制；时间窗可切 7 / 30 / 90 / 365 天，切换即重新请求
- **测试**：后端 235 → 245 passed（统计服务 4 例、进度增量 3 例、新端点 3 例）；前端单测 174 → 182 passed（Stats 视图 8 例）；Playwright e2e 46 → 50 passed；`npm run build`、`npm run typecheck:test` 通过
- **验证**：隔离后端（临时库 + `:8010`，前端 `:4173` 代理过去，用完即删）。种 3 部片、两条标签、3 条回填日志后，走真实接口 `POST /videos/2/play` → `progress=300` → 回拖 `180` → `780`，今天累计只记 **900 秒**（300+600，回拖的 120 秒没被重复计入）；`/api/history/stats?days=30` 返回 `window_seconds=11400`、`videos_watched=3`、`active_days=4`、`longest_streak_days=2`（09-15、09-16 连着，之后断开），标签分布 纪录片 6000 > 悬疑 5400。真实浏览器实测：卡片显示"本月观看 3.2 小时 / 30 天内 3.2 小时 / 看过影片 3 部 / 最长连看 2 天 · 4 天有记录"，30 根柱子峰值 160px（当天 5400s）、次高 52.79px（1800s，即 33%）、空白天 3.2px（2% 下限）；标签条宽度比 = 1.000 与 0.900，颜色 `rgb(31,122,68)` / `rgb(124,108,255)`；点"近 7 天"请求变成 `?days=7`、柱子剩 7 根、坐标轴改"9月13日 → 9月19日"。两套主题取值：深色卡底 `#14171e`、柱子 `rgba(124,108,255,.12)`，浅色卡底 `#ffffff`、正文 `#17191f`
- **已知边界**：统计从本次改造起开始积累，改造之前的观看时长无法回推（历史行只剩最后一次位置）；老库首次升级时该页是空的，属于预期而非 bug

### 新增功能：重复文件检测，先比大小与时长再读首尾哈希确认

- **两级筛选**：`GET /api/videos/duplicates` 先在 SQL 里按 `(file_size, duration)` 分组并 `HAVING COUNT(*) > 1`（这一步免费），只把撞进同一桶的行读成 Python 行；每个候选文件再读**首尾各 1MB** 做 SHA-256（`backend/src/utils/file_fingerprint.py`）确认内容一致，光大小相同不算重复。哈希在 `asyncio.to_thread` 里跑并用 `gather` 并发，不把事件循环按住；每次请求最多探 300 个文件，按可回收空间从大到小花这笔读预算
- **打不开就不猜**：`edge_fingerprint` 读不到文件返回 `None`，该行进不了任何组——没挂载的共享盘、已经删掉的文件都不会被当成别人的副本，与"丢失"那套语义对得上
- **建议保留哪一份有依据**：后端直接给出 `keep_id`，规则是"看过次数多 > 有播放进度 > 更早入库"，看过的副本不会被顺手标成待删
- **端点改动**：只新增 1 个只读聚合 `GET /api/videos/duplicates`（注册在 `/{video_id}` 之前），删除仍复用既有 `DELETE /api/videos/{id}`，**没有新增任何能碰磁盘的端点**
- **界面**：视频源页底部一张"重复文件检测"卡片，按需点"开始检测"（探针要读文件，首页自动加载里不放）；每组显示份数、每份大小、多占空间与可回收总量，副本按路径排列，建议保留的那行挂"建议保留"；"移除记录"逐条删、"移除多余记录"一次删掉除保留外的全部，都要确认
- **文案讲清楚边界**：确认框明写"将从库里移除 N 条记录。磁盘上的文件不会被动，请到文件管理器里删掉它，否则下次扫描会重新收录"——实测确实如此，删完重扫 `new_videos=1` 会把它带回来
- **测试**：后端 224 → 235 passed（指纹 5 例、服务层 4 例、新端点 2 例）；前端单测 165 → 174 passed（检测卡片 9 例）；Playwright e2e 43 → 46 passed；`npm run build`、`npm run typecheck:test` 通过
- **验证**：隔离后端（临时库 `dupproof.db` + `:8010`，前端 `:4173` 代理过去，用完即删）。种 3 个大小都是 3145728 字节的样片，其中两份字节完全相同、第三份只有开头 16 字节不同 → 扫描 `files_found=3, new_videos=3`，`/api/videos/duplicates` 只回 1 组 2 份（`count=2`、`wasted_bytes=3145728`、`keep_id=1`），大小相同内容不同的那份**没有误报**。真实浏览器两套主题各走一遍：卡片显示"1 组重复，多占 1 份 · 可回收 3.0 MB"、2 行副本、"建议保留"落在保留行上；页面 `scrollWidth 1234 == innerWidth 1234` 无横向溢出，路径列 clientWidth 943px 未溢出；点"移除多余记录"→ 确认框 → toast"已移除 1 条重复记录"，组随即消失、按钮变"重新检测"，库从 3 行变 2 行（剩下的正是 `午夜列车` 与 `另一部电影`），而磁盘上那个备份文件仍是 3145728 字节没被动过；重新检测显示"没有发现内容完全相同的文件。"，探针 14ms。深色实测取值：卡底 `#14171e`、组底 `#1e222b`、正文 `#e9ebef`、路径 `#98a0ad`、保留标签 `#67c23a`（对比度约 7:1），浅色为 `#ffffff` / `#eef0f4` / `#17191f` / `#5f6673`
- **已知盲区**：两份文件长度相同、只有中间不同（例如换过片头广告的同体积重编）时首尾哈希分不出来。要收口得引入全文件哈希与缓存，属于另开一轮的活，本次按"首尾哈希"的既定方案实现

### 新增功能：文件不见了先标"丢失"，确认删掉了再清记录

- **扫描不再悄悄删库**：`videos` 新增 `is_missing` 列（`ADDED_COLUMNS` 自动补，老库默认 0）。一次扫描结束后，源里已知但这次没找到的文件只是打上标记，行、播放历史、收藏、标签全部保留；文件回来再扫描会自动清掉标记，不会重复入库
- **挂载点整块不见时不判丢失**：只有 `os.path.isdir(source.path)` 为真才做判定。NAS 没挂载时目录列表也是空的，若照此判定会把整库刷成丢失；实测把源目录改名后重扫，`files_found=0` 而两条记录仍是 `is_missing=False`
- **搜索框多一个状态词 `丢失`**：与 `没看过 / 未看完 / 已看完` 同一层，`丢失` / `已丢失` / `missing` 都认，可与其他条件叠加（`丢失 标签:悬疑`）。因此本次**没有新增任何端点**，丢失记录走的就是 `GET /api/videos?search=丢失`
- **卡片**：丢失的封面去色压暗（`grayscale(1)` + 45% 不透明度），左上角挂"丢失"角标；"新"角标让位，因为此时"新不新"已经不是重点
- **首页横幅**：进页面时发一次 `page_size=1` 的探测请求拿总数，有丢失才显示横幅；"查看"把 `丢失` 填进搜索框（同步进 `?q=`），"清理丢失记录"先确认再逐条走既有 `DELETE /api/videos/{id}`，取消即一条不动。最多翻 20 页 × 100 条，失败条数单独提示
- **测试**：后端 217 → 224 passed（扫描标记 3 例、服务层筛选 1 例、列表字段与筛选 1 例、解析器 2 例）；前端单测 157 → 165 passed（卡片 3 例、横幅 5 例）；Playwright e2e 41 → 43 passed；`npm run build`、`npm run typecheck:test` 通过
- **验证**：隔离后端（临时库 + 2 个 ffmpeg 样片 + `:8010` 前端）实测。① 扫描 2 个文件 → 两条 `is_missing=False` 且都有缩略图；② 删掉 `gone_away.mp4` 重扫 → `files_found=1`、`new_videos=0`，该行 `is_missing=True` 而另一行仍 `False`；③ `?search=丢失` → `total=1` 只回那一条；④ 把文件复制回去再扫 → 标记自动清回 `False`，`new_videos=0`；⑤ 真实浏览器里封面实测 `filter: grayscale(1)`、`opacity: 0.45`（宽 296px），横幅文案"1 个文件已不在磁盘上"，点"查看"后只剩 1 张卡片且地址为 `?q=%E4%B8%A2%E5%A4%B1`，点"清理丢失记录"→ 取消后仍是 2 张、确认后变 1 张，刷新与直接查接口都是 `total=0`。两套主题各自复核横幅配色：浅色底 `#ffffff` / 边框 `#e2e4ea` / 文字 `#17191f`，深色底 `#1a1e27` / 边框 `#262b36` / 文字 `#e9ebef`

## 2026-09-19

### 新增功能：文件名解析出系列与季集，首页报"看到第几集"

- **解析器 `backend/src/utils/name_parser.py`**：从文件名里读出片名、系列、季、集、字幕组。认 `S01E02`、`1x03`、`Episode 5`、`EP 5`、`Part 2`、`第12集/话/期` 六种写法；先剥掉 `[NC-Raws]`、`(04)`、`{sub}` 这类括号内容，再清掉 `1080p`、`x265`、`WEB-DL`、`HDR10+`、`H.264`、`REMUX` 等发布噪声，小数（`3.14 圆`）与 `16:9` 不会被拆坏。认不出任何标记的文件保持原样，只是没有系列
- **自动打标签**：扫描出的剧集自动挂上"系列名 + 字幕组"两个标签，同一个系列的每一集共用同一行标签（实测 3 集只建了 1 个 `Severance` 标签，`video_count=3`）。标签走既有 `tags` 表，因此 `标签:海边的日子` 这种搜索写法直接就能用，没有新增筛选面
- **三列新数据 + 存量库自动补列**：`videos` 新增 `series/season/episode`（可空）与 `ix_videos_series` 索引。`create_all` 不改已存在的表，所以 `init_db` 加了 `ADDED_COLUMNS`：用 `PRAGMA table_info` 探测缺哪列就 `ALTER TABLE ADD COLUMN` 补哪列，老库启动即跟上，不需要手工迁移
- **回填不覆盖人工整理**：已入库的文件再扫描一次，只在 `series` 为空时补坐标、自动标签**追加**而非替换，改过的片名与手动标签原样保留（实测：抹掉 4 行的坐标与标签后重扫，坐标与标签都回来了，`new_videos` 仍为 0，片名没动）
- **首页"系列进度"横排**：新端点 `GET /api/videos/series` 一次分组查询算出每个系列的总集数、看完数、看过数，只把未看完的集读成行，按 `season, episode` 取下一集。横排显示 `1/3` 与"看到 S01E02"，点一下直接进下一集；全看完显示"已看完"且不再可点。卡片右上角同时挂 `S01E02` 角标（无季的写法显示 `第12集`）
- **本次端点改动**：只有 1 个只读聚合 `GET /api/videos/series`，`VideoResponse` 多带 `series/season/episode` 三个字段
- **测试**：后端 198 → 217 passed（解析器 13 例、系列聚合 3 例、扫描登记与回填 3 例、列表字段 1 例）；前端单测 149 → 157 passed（卡片角标 2 例、横排 5 例、api 路径 1 例）；Playwright e2e 39 → 41 passed；`npm run build` 通过
- **验证**：隔离后端（临时库 + 4 个 ffmpeg 样片）实测。① 手工 `DROP COLUMN` 造出升级前的库，重启后 `PRAGMA table_info` 显示 `series/season/episode` 与 `ix_videos_series` 均已补回；② 扫描 4 个文件读出 `Severance S01E01/02/03` → `(Severance, 1, 1/2/3)`、`[NC-Raws] 海边的日子 第12集` → `(海边的日子, None, 12)` 且标签为 `['海边的日子','NC-Raws']`；③ E01 看完（4/4）、E02 看到 2 秒后，`/api/videos/series` 返回 `Severance total 3 finished 1 watched 2 next=(2, progress 2)`、`海边的日子 total 1 finished 0 watched 0 next=(4, progress None)`；④ 清空坐标与标签后重扫，两处数据原样恢复。真实浏览器侧由 e2e 覆盖：进度线按 `1/3` 铺到轨道宽度的 33.3%，像素实测填充落在 30%~40% 区间，点横排跳到 `/videos/1`
- **顺带发现**：`POST /videos/{id}/progress` 的 `progress` 是整数字段，传 `1.5` 会 422（`int_from_float`）。播放器上报时已经 `Math.floor`，所以线上不会踩到，本次未改协议

### 新增功能：首页续播、可分享地址、通知清理与播放器偏好

- **列表接口带回观看位置**：`VideoResponse` 新增 `progress`（秒，没看过为 `null`），由已有的 `play_history` 行直接带出，`GET /api/videos` 不必再逐条查历史。卡片封面底部据此画一条进度线，看完（≥99.5%）不画
- **首页"继续观看"横排**：走既有的 `GET /api/history/continue`，显示片名、还剩多久与进度条，点进去直接续播。本次没有为此新增端点
- **筛选条件同步到地址栏**：`?q=`、`?tag=`、`?source=`、`?page=`、`?size=` 五个键进 URL，刷新、后退前进、直接发链接都能还原。默认值不写入（`page=1` 会被规范化掉），输入防抖 400ms，URL 反向驱动时不再回写；关键词走 `router.replace`，敲字不堆历史。垃圾参数回落默认（`?page=abc`、`?size=-5` 当作没填）
- **通知可单条删除、可一键清空**：新增 `DELETE /api/notifications/{id}` 与 `DELETE /api/notifications`（本次唯一的端点改动，均为普通删除，无新增特权面）。清空要 4 秒内点第二次"确认清空"，超时自动收回，避免手滑抹掉整列
- **全局快捷键**：`/` 聚焦搜索框、`?` 打开快捷键说明；焦点在输入框/文本域内时两个键都不拦截
- **播放器偏好持久化**：倍速、音量、静音、字幕字号、字幕延迟存 localStorage（`player-prefs`），换片、刷新都保留。字号改的是 `<video>` 的 `font-size`，延迟改的是真实 cue 的 `startTime/endTime`
- **测试**：后端 189 → 198 passed；前端单测 94 → 149 passed（17 文件）、Playwright e2e 27 → 39 passed；`npm run typecheck:test` 无输出、`npm run build` 通过
- **验证**：真实浏览器连当前代码后端（临时库、两部 ffmpeg 样片）。片长 20 秒、存位 6 秒 → 列表返回 `progress: 6`，横排进度条 196px/填充 58.8px、卡片 296px/填充 88.8px，均为精确 30%，没看过的另一部返回 `null` 且无进度线；敲"夜空"地址栏变 `?q=夜空`，深链 `/?q=海边&tag=1` 还原出 1 张卡片；2 条通知删 1 条（未读角标 2→1）、清空后服务端 `total` 为 0；播放器设 1.5 倍速、音量 0.3988，刷新后原样恢复，字幕字号 +2 后首条 cue 由 1.0s 延后到 1.5s，重载停在续播点 6.0s
- **生效前提**：本轮给 `VideoResponse` 加了 `progress`、给通知加了 DELETE。用 `--reload` 起的后端会自动跟上；已经在跑的旧进程要重启才认这些字段——尤其注意从别的工作目录起的服务用的是另一份相对路径 `./data/videos.db`，看到的库根本不是同一个

### 修复问题：关键词不上地址栏、字幕延迟在浏览器里失效

- **关键词只在内存里**：`handleSearch()` 只调了 `loadVideos()`，标签/源/页码同步了 URL，唯独搜索词没有，"复制链接"分享出去的地址打开是全量列表。改为提交搜索时一并写 URL
- **字幕延迟真机完全无效**：`<track>` 的 `load` 事件 Chromium 只在元素上发、从不在 `TextTrack` 上发，旧代码监听的是后者；同时轨道刚启用时浏览器会先给一个**空 cue 列表**（真值），缓存判断把它当成"已解析"存了下来，此后再不取基准时间。改为监听元素 `load`、空列表不算已捕获。单测原先用 `TextTrack` 上的 `load` 模拟，浏览器不发的这个事件测试却发了——两处 e2e 与单测都改按元素事件驱动，并补了"先给空列表再补 cues"一例
- **单测里的键盘监听串场**：`VideoPlayer` 的监听挂在 `document` 上，挂载后的 wrapper 不卸载就会替整个文件继续应答按键，导致 10 例 `Unhandled Errors`。改为集中登记并逐个卸载

### 新增功能：主页多维度搜索

- **多关键词 AND、每词跨字段 OR**：`search` 由原来的“只 LIKE 片名”改为按空格切词，词与词之间取交集；单个词同时命中片名、简介、标签名任意一个即算命中。引号包裹的 `"深夜 测试"` 作为一个整句匹配，不拆词
- **通配符转义**：用户输入的 `%` 与 `_` 之前会当作 SQL LIKE 通配符（搜 `_` 能命中所有视频）。现在按 `LIKE ... ESCAPE '\'` 转义，`100%` 只命中片名真含 `100%` 的那一部
- **结构化操作符**：新增纯文本解析器 `backend/src/utils/video_search.py`，同一个搜索框支持 `源:NAS`、`标签:剧集`（全角冒号、冒号后带空格都认）、`评分>=4`、`时长>40分钟`、`没看过` / `未看完` / `已看完`。识别不了的 `key:value` 一律退回关键词，所以 `16:9`、`http://x` 这类片名不会被误吞；`时长` 后的裸数字按分钟理解（`时长>=90` 即 5400 秒），无键比较则必须带单位（`>40分钟`、`>1.5小时`）
- **相关度排序**：命中片名记 2 分、命中简介或标签名记 1 分，多词累加后按分数倒序，同分再按 `created_at desc, id desc`；没写关键词时维持原来的时间倒序。因此搜“暗涌”时片名叫《暗涌》的排在只有简介提到的《前夜》前面
- **计数不再靠 join**：标签、观看状态一律走 `EXISTS` 子查询，`tag_id` 与 `source_id` 筛选也改为子查询。原来 join 标签表会让“同时挂两个标签”的片子出现两行、`total` 一起虚高，分页随之错位
- **主页接上标签筛选**：后端 `tag_id` 参数一直存在但前端从未调用，首页搜索框右侧补了一个可搜索的标签下拉，与关键词、视频源筛选可叠加
- **搜索框 UI**：右侧新增语法提示气泡（`:persistent="false"`，未打开时不进 DOM，避免与通知面板抢 `.el-popover` 选择器）；空状态改成会说明“没有与「xxx」匹配的结果”，并在确实存在筛选条件时给出“清除筛选”按钮，一键清空输入与标签
- **接口面没有扩大**：仍然只有 `GET /api/videos` 的 `search` / `tag_id` 参数，未新增端点
- **测试**：后端 164 → 189 passed（解析器 13 例钉住每种写法，服务层 12 例覆盖跨字段 OR、AND、引号、各操作符、观看状态三分、相关度排序、通配符字面量、双标签只返回一次、与下拉筛选叠加）；前端单测 88 → 94（`tests/views/Home.spec.ts` 6 例）；Playwright e2e 25 → 27
- **验证**：真实浏览器连当前代码后端（临时 5 部 ffmpeg 样片、2 个视频源、2 个标签）。实测命中：`暗涌` → 《暗涌》《前夜》（相关度生效）、`标签:公路` → 2 部、`暗涌 港口` → 1 部、`评分>=4` → 2 部、`时长>15分钟` → 1 部、`源:备份` → 1 部、`100%` → 《100% 胶片》、`没看过` → 4 部、`未看完` → 1 部、`已看完` → 0 部、`标签:悬疑 评分>=4` → 1 部；标签下拉发出 `tag_id=3` 得 2 张卡片；空状态提示与“清除筛选”恢复 5 部并清空输入。两套主题各自复核新增元素对比度，深色 6.33 ~ 15.02、浅色 5.34 ~ 17.57，均 ≥4.5:1
- **收尾**：临时样片库与两个视频源通过应用自身的删除接口级联清理（源、视频、播放历史、缩略图文件），未用裸 SQL；用户原有的 4 张缩略图与 6 条扫描通知保留（通知没有删除端点，故本次新增的 2 条 `scan_complete` 一并留下）

### 修复问题：播放历史与"新"角标

- **看一次留下两条记录、继续观看同一部出现两次**：`play_history` 每次 `POST /videos/{id}/play` 都插入新行。改为每部视频一行（`PlayHistory.video_id` 加 `unique=True`），`record_play` 与 `update_progress` 共用 `_get_or_create_history`。`create_all` 不会改动已存在的表，因此 `init_db` 先把老库的重复行折叠成"最后一次观看"那条，再建唯一索引
- **看完还是"播放中"**：`completed` 只在越过终点那一瞬间置真且永不回落，进度 45/120 的行因此一直停在未完成。改为每次上报按时长重算（新增 `is_completed`，容差取片长的 5%、上限 10 秒），倒回去看会自动变回未完成。同时把"播放时间"列名改为"最后观看"、状态标签"播放中"改为"未看完"，并在每次进度上报时刷新 `played_at`
- **进度只在每 30 秒和卸载时上报**：暂停、拖完进度条松手、播完都不上报，"看到哪儿"和实际位置能差半分钟。改为这几处都上报；卸载上报要求本次确实播放过，避免只打开详情页凭空多一条历史
- **"新"角标与看不看过无关**：`VideoCard.vue` 拿 `created_at` 算 24 小时 / 7 天，而扫描写入的 `new_videos.viewed` 前端从未读取（`markVideoViewed` 接口无人调用），于是播完仍挂着"新"、超过 7 天的未看片又提前丢角标。改为列表接口返回 `is_new`（有未看的扫描记录），首次播放即清；角标只留一档"新"，去掉按文件年龄编造的"本周"
- **历史计数把整表读进内存**：`get_history` 用 `len(所有行)` 当 `total`，改为 `select(func.count(PlayHistory.id))`
- **测试**：后端 155 → 164 passed（每部一行、播放清角标、倒回重开未完成、`is_completed` 容差、老库重复行折叠、继续观看每部一次）；前端单测 82 → 88、Playwright e2e 25 passed、`npm run build` 通过
- **验证**：真实浏览器连真实后端。首页"暗涌 / 归途"有角标、已播过的"前夜"没有；在播放器里点开"暗涌"后回首页角标消失；639px 宽的进度条拖到 62% → 播放位置 37.2s 并上报 37；拖到 99% → 59.4s 落在 1:00 的容差内，历史行状态转为"已完成"并退出继续观看；历史表 3 行对应 3 部视频，按"最后观看"倒序

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
