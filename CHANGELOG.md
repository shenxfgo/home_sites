# 更新日志

## 2026-10-05

### 修复 + 新增：文件挂载回来那一轮，通知不能再写「已找不到」；真后端 e2e 加到 13 条（丢失标记）

- **动因**：`is_missing` 那一列是这一套里唯一"扫描会改写已有行"的路径，而它从没在真库上签过字——替身夹具把 `is_missing: false` 抄在 `fixtures.ts` 里，翻不翻由前端自己说了算；`丢失` 那一个算子、首页那条横幅和「查看」按钮也全部只对着一份虚构响应渲染。加这条用例要把整条往返走一遍：搬走文件 → 扫 → 界面上读到丢失 → 搬回来 → 再扫 → 那一行原样还在。
- **原症状**（往返走出来的，不是推测）：写用例时照着"通知按方向说两句话"读 `scan_service.py:336-370`，发现翻转计数只数"翻了几行"，不看朝哪个方向翻——`missing_flips` 一个计数器、文案一句「N 个文件已找不到」。于是**挂载回来那一轮通知写的还是「已找不到」**，而那恰恰是好消息：界面上同时显示"1 个文件已找不到"和一部马上能播的片子。
- **红在先**：`tests/test_services/test_scan_service.py:714` 的 `test_returned_file_announces_a_return` 先跑红，实测 `At index 2 diff`——第三条通知的 message 期望「…1 个文件已找回」，收到「…1 个文件已找不到」。docstring 里写的就是这句话的原因。
- **修复**：`ScanService.scan_source` 把那个计数器拆成 `files_lost` / `files_found_again` 两个方向，文案按方向各加一小句（「，N 个文件已找不到」/「，N 个文件已找回」），而通知 `data` 里的 `missing_changed` 仍是两者之和——前端和既有测试读的那一个键没换名字。"变了才说"那道闸门照旧：一轮纯零变化的定时扫描仍然一句不发。
- **用例 13（丢失标记与那条横幅）**：`renameSync` 把 `data/e2e/media/e2e_sample.mp4` 搬到同级的 `hidden/`，`POST /api/sources/1/scan`，核对四件事（那一次报 `files_found=0`、库里那一行**还在**且只是 `is_missing` 翻了、`GET /api/videos?search=丢失` 读到同一条、通知新增一行且 `data` 是 `{source_id:1,new_count:0,subtitles_found:0,missing_changed:1}`）；界面上核 `.missing-bar` 那句「1 个文件已不在磁盘上」、卡片角上的「丢失」标、「查看」把 `丢失` 填进搜索框。再搬回来扫一遍，核 `id` 未变 + `thumbnails/` 下每个 `.jpg` 的「相对路径 + 内容 sha1」逐项相等 + `play_history` 那一行的 `id` 未变 + 新那条通知说的是「已找回」。`finally` 保证文件回位。
- **五个变异，五个都红**（每个改完单独 `-g 消失` 跑，跑完 `cp` 还原，还原后再整跑一遍）：① 翻转块换成 `if False:` → 红在 `:937`（`is_missing` 期望 true 收到 false）；② 两个方向计数器合回一个 `files_lost`（= 提交前那版的行为）→ 红在 `:979`（`toContain('1 个文件已找回')`）；③ 那道闸门去掉 missing 项（`if new_videos or subtitles_found:`）→ 红在 `:942`（通知数期望 2 收到 1）；④ 摘掉「查看」的 `@click` → 红在 `:960`（搜索框期望 `丢失` 收到空）；⑤ 横幅条件从 `missingCount > 0` 改成 `> 1` → 红在 `:956`（`.missing-bar` 找不到）。没有一次"改了代码用例照样绿"。
- **踩到的两处**：一是这台机器上经 Bash 与 Edit 落盘的反斜杠会被吃掉一半：我要写的是"两个反斜杠组成的正则字符类"，文件里只剩一个，`typecheck:test` 报回来的却是 `Unterminated string literal（TS 把斜杠当成了正则的结束符），查了三方才确认写入层和编译器之间出的问题，而不是断言写错；改用 `node:path` 的 `sep` 做归一（`split(sep).join('/')`），既不再需要正则字面量，Windows 与 POSIX 两边都成立。二是**扫描响应的形状以 HTTP 模型为准，不是服务层那个 dict**：`ScanResultResponse` 里没有 `foreign_paths`（服务层算了，但永远过不了边界），且它和"扫全部源"共用，那一侧才有的 `sources_scanned` / `total_*` 在这里全是 `null`——第一版照抄服务层，红在这两处；现在 `scanSource()` 只挑四项并在注释里写明为什么挑。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 12 → 13；`frontend/CLAUDE.md` 逐条那段补第 13 条要签的三样东西，顺序段从"十二条"改"十三条"（链尾加 `→ 丢失标记`，`-g` 命令从五条列成六条，并写明第 10/11/12 条的"倒数第二"各自改口、第 13 条为什么必须压轴：它中途把媒体文件搬走，任何还要扫到那个文件的用例都不能排在它后面）；`CLAUDE.md` 的「库内核对」那一行补上方向与"封面/历史都保留"；`backend/CLAUDE.md` 的通知一节把 `missing_flips` 改成两个方向计数并写明"方向也要说"，钉住它的用例从四例改五例。
- **验证**：真后端 e2e **13 passed**（单 worker 串行，53.6 秒；第 12 条 20.4 秒、第 13 条 2.0 秒；五个变异全部还原之后重跑）；`-g 消失` 单独跑 **1 passed**（8.0 秒含起跑，能自足是因为起点就是播种后的 1 行通知 + 1 部片子，中间两次扫描都由它自己发）；后端 PostgreSQL 全量 **726 passed**（3:32，725 → 726 是本单新增那条服务层用例），`--cov=src` 总覆盖 **91.89%**；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数）；前端单测 **281 passed**、`typecheck:test` 绿、`npm run build` 绿、桩 e2e **82 passed**（34.5 秒，这一晚没抖）。跑完 `data/e2e/` 的磁盘状态实测回到原样（`media/` 两个文件在、`hidden/` 空）。
- **覆盖面现状**：浏览器用例总数实测 **95** 条——打真库 **13** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。仍然零真库签字的读路径只剩：转码任务那条长流程。`storage.reachable()` 那道闸门（源整体够不着时不判定丢失）不在 e2e 范围内——它要的是一个"列不出来"的源，`tests/test_services/test_scan_service.py` 那份假存储带这个开关，服务层已经钉住。

### 修复 + 新增：越界的 `?page=` 会让首页同屏说两句反话；真后端 e2e 加到 12 条（搜索与筛选）

- **动因**：搜索与筛选是这一套界面里唯一**从没在真库上签过字**的读路径，而且它有两处替身挡不住的松动。一是 `frontend/e2e/fixtures.ts` 里的 `matchesSearch` 是拿 TypeScript 把 `backend/src/utils/video_search.py` **又实现了一遍**（那份函数自己的注释就写着这件事），两份实现各自测自己那一侧，谁改了对方都不知道。二是替身的 `/videos` 处理器**根本不读 `page` / `page_size`**，永远回 `{page: 1, page_size: 20}`——所以那 82 条桩用例里"翻到第 3 页"全是虚构的，界面写进地址栏的页码从来没被服务器看过一眼。
- **用例 12（搜索与筛选的分面）**：夹具自己建（不借第 8 条留下的标签），这样它能单独 `-g 搜索框` 跑，改一处后端约二十秒出结论。十五个词每个都核到**三处一致**：卡片数、服务器对同一个字符串报的 `total`、地址栏里那个词——写成 `expectSearch()` 不是为了省字，而是因为这条的断言本身就是"三处得是同一件事"，摊开抄十几遍总有一遍只核对其中两处。真库才给得出的三件事：ILIKE 不区分大小写（替身是 `toLowerCase` + `includes`，换一种 collation 又是另一套）、`标签:` 与 `源:` 这两个算子真被解析器认下（写成关键词一律 0 条，所以"命中 1 条"本身就是证据）、观看状态读的是**这个账号**的历史——换成员登录后同一个 `未看完` 必须是 0 条而 `没看过` 是 1 条，同库同一片子两个人报的数不一样，只有真中间件加真库给得出这个差别。再加上 `%` / `_` 两个手打工配符必须是字面量，以及两个下拉（源、标签）的选项本身就来自真库。
- **原症状**（先跑出来的证据，不是推测）：`page.goto('/?page=2')` → `Expected: 1 / Received: 0` 张卡片（`library.real.spec.ts:780`），失败快照里同屏写着「共 1 个视频」和「添加视频源并扫描即可开始使用」。`?page=` 是首页自己写进地址栏的，分享一条链接、或者浏览器后退回到筛选前的那一页，都可能带回来一个已经不存在的页——那一页确实是空的，库里却不空。
- **修复**：`views/Home.vue` 的 `loadVideos()` 读到"这一页空、库不空、而页码越界"时钳回最后一页再读一次（`Math.max(1, Math.ceil(total / page_size))`）。终止性是显然的：钳完那一页 `currentPage > lastPage` 就为假；地址栏由已有的 `watch([selectedSourceId, selectedTagId, currentPage, pageSize], pushQuery)` 顺手改过来，没有新机制。全空库不会被钳（`total > 0` 是闸门），否则"第 4 页不存在"会变成"第 1 页空白"，比原来更难懂。
- **红在先（四次变异，三次红一次绿，那一次绿是这一单的发现）**：
  - 摘掉 `_like` 里那三层 `replace`（`video_service.py:198`）→ 红在 `expectSearch(page, '%', 0)`（`:773`，实测 1 张卡）：`%` 和 `_` 都成了"匹配一切"。
  - 从 `_played` 的 EXISTS 里删掉 `PlayHistory.user_id == user_id` → 红在成员那一句 `expectSearch(page, '未看完', 0)`（`:796`，实测 1 条）：owner 的历史被算到了成员头上。
  - 从 `NAME_KEYS` 里删掉 `"标签"` → 红在 `expectSearch(page, '标签:深夜', 1)`（`:761`，实测 0 张卡）：算子退回成关键词。
  - 删掉 `_tagged_with` 里跟外层影片相关的那一句 `.where(video_tags.c.video_id == Video.id)` → **用例照样绿**。根因很直白：库里只有一部片子，相关与不相关长得一模一样，而那个"没挂过片子"的标签在 `video_tags` 里根本没有行，走 `JOIN video_tags` 的 EXISTS 永远看不见它——所以 `无人挂载 → 0` 这条钉的是"没挂载的标签不算命中"，不是我原先以为的"标签匹配不是全库开关"。**这条注释已经改成实话**，并且写明界面这一侧要真钉住它得有第二步（两部片子各挂不同标签，正是第 13 条要造的形状）。它不是没人管：`tests/test_services/test_video_search.py` 里那两条（`test_a_keyword_also_matches_the_description_and_tag_names`、`test_tag_keyword_only_looks_at_tag_names`）实测把同一个变异判红了。
- **踩到的两处**：一是 `expect(locator).toHaveCount(n)` 在"数量本来就不变"的那些探针上**不是同步点**，会当场通过而什么都没等到，第一次跑就是撞上那 400ms 防抖之前读到空地址栏——现在 `expectSearch` 先 `expect.poll` 地址栏，它才是防抖之后第一件事。二是 `{...new URL(u).searchParams}` **永远是 `{}`**（`URLSearchParams` 的条目只在迭代器上，没有可枚举的自有属性），害我差点以为应用没把页码擦掉；写了个一次性探针 spec 实测应用 200ms 内就稳定在 `?q=e2e`，是我的断言假红（探针与 `test-results/` 已删，一行没留）。
- **用例（前端单测）**：`tests/views/Home.spec.ts` 补两条。一条把那个钳位钉在缝上：`total: 60` 的库、`?page=4`，断言请求序列是 `[1, 4, 3]`（`[0]` 是丢失记录数那根探针）并核到卡片渲染出来、地址栏跟着变成 `page=3`；**红在先**——把 `Home.vue` 临时换回提交前那版跑，实测 `expected [ 1, 4 ] to deeply equal [ 1, 4, 3 ]`。另一条钉住反面：空库（`total: 0`）落在 `?page=4` 上必须**不**被钳，`listVideos` 仍只有两次、地址栏仍是 `page=4`。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 11 → 12；`frontend/CLAUDE.md` 的顺序段从"十一条"改"十二条"，补了第 12 条为什么排在最后（它往 `tags` 留两个标签、其中一个挂在播种那部片子上，而第 8 条把整张标签表当成"只有我自己那两个"并要那个空标签 `video_count` 留在 0），`-g` 命令从四条列成五条，还写明界面从此会擦掉越界页码——将来谁的用例落在"第 N 页"上再断地址栏，都得先等这一次钳位跑完。这一单没改任何后端代码（四个变异各自 `cp` 还原，还原后整跑一遍 PG 才是证据），`backend/CLAUDE.md` 的薄位置清单与搜索谓词那两句按现状不动。
- **验证**：真后端 e2e **12 passed**（单 worker 串行，54.5 秒，第 12 条自己 21.3 秒；四次变异全部还原之后重跑）；`-g 搜索框` 单独跑 **1 passed**（约 26 秒含起跑）；后端 PostgreSQL 全量 **725 passed**（3:09，与上一单同数——本单没提交后端代码）；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数）；前端单测 **281 passed**（279 → 281 是本单新增两条）、`typecheck:test` 绿、`npm run build` 绿。桩 e2e 这晚**没有一次跑到 82**：三次整跑分别是 81 / 80 / 81，抖的两次都落在 `player.spec.ts` 那两个靠计时器走的用例（`:119`、`:189`），单独重跑这两条 **2 passed（4.2 秒，1.7s 与 2.1s）**，而整套里它们要 5.4s 与 7.0s。原因查到了机器上：那个 `ShadowBot\xbot_interpreter` 一直在后台活着，还另起了一份 `npm run dev`（Vite 4173）和第二个 uvicorn 8001，与测试抢 CPU。按既有结论处理：**重跑一遍再判是不是回归**，且 `test:e2e:real` 与 `pytest` 永远不并行（两套都 TRUNCATE `home_sites_test`）。
- **覆盖面现状**：浏览器用例总数实测 **94** 条——打真库 **12** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。仍然零真库签字的读路径：丢失标记与那条横幅（`is_missing` 的翻转、`丢失` 算子、清理按钮）、转码任务那条长流程。


### 修复 + 新增：单键写系统配置能把设置页打成 500；真后端 e2e 加到 11 条

- **动因**：`PUT /api/settings/{key}` 认键名（白名单，M3 加的），**不认值**——它收的是裸 `value: str`，写什么进库什么。而 `GET /api/settings` 读回来的时候对 `auto_scan_interval` / `thumbnail_width` / `thumbnail_height` 三个键做 `int(...)`。于是一次写入就把整个设置页永久打成 500，直到有人手工去改库里那一行。整份的 `PUT /api/settings` 不会有这个问题：它走 `AllSettingsResponse`，Pydantic 替它挡了。
- **原症状**（先跑出来的证据，不是推测）：`PUT /api/settings/thumbnail_width {"value":"abc"}` → 200，随后 `GET /api/settings` 抛 `ValueError: invalid literal for int() with base 10: 'abc'`（`api/settings.py:63`）。
- **修复**：`INT_SETTING_KEYS` + `_check_setting_value`，规则只有一条——**写进去的值必须能被读回来的那条路径解析**。不合法的键值现在 400，报错文案点名是哪个键、必须是什么。刻意**没有**加范围校验：那三个数在项目里目前没有任何消费者（`grep auto_scan_interval` 只命中 `api/settings.py` 自己），定时扫描用的是源级别的 `scan_interval`，所以"0 秒扫一次"现在还伤不到谁，等有消费者了再按那个消费者的约束收。
- **用例（后端）**：`tests/test_api/test_preferences.py` 参数化三条（三个数字键各一），断 400 **并且** `GET /api/settings` 仍是 200。红在先：改完之后跑，`assert 200 == 400` 三条同时红，先看着它红再写修复。顺手把这一面缺的四条补齐——整份 `PUT` 的回显、整份 `PUT` 之后换一路读（含 Text 列原文）、单键再写一次走"那一行已存在"的分支、以及"漏一个键 = 回到代码默认值"这条边界（`AllSettingsResponse` 五个字段都带默认值，少传一个 Pydantic 替它填上；界面每次都发全五项所以碰不到）。这一面此前是 `api/settings.py` **71%**，量完是 100%（缺的只有那一行"已存在就改值"）。
- **用例 11（真后端 e2e，系统配置）**：这一条要签的是**"保存成功"和"库里有没有那一行"是两件事**——`PUT /api/settings` 直接把请求体送回，替身夹具里连库都不碰，所以界面上那句「设置已保存」什么也没证明。用例先断 `settings` 表空着时读回来的是五项代码默认值，再用单键 PUT 把两个数字键写成非默认值，然后在界面上改扫描间隔（每小时 → 每 2 小时）和自动扫描开关、点保存，**换 `GET /api/settings` 这一路**核对五项，再 `GET /api/settings/auto_scan_interval` 核对库里那一格的原文是字符串 `"7200"`（Text→int 那层强制转换只在真库上存在），刷新后界面读回同一个值，最后打一次坏值证明 400 之后库里没被写坏。
- **红在先（四次变异：三次红、一次绿，那一次绿写下来）**：
  - 注释掉 `update_settings` 里的 `await session.commit()` → 红在 `expect(await readSettings(page)).toEqual(saved)`（`:658`）。**这一条就是"回显不算数"的证据**：服务器照旧回 200、界面照旧弹「设置已保存」，什么都没写进去。
  - 从整份 PUT 的字典里删掉 `"auto_scan_interval"`（界面真改过的那个键）→ 同一个位置红：`Expected 7200 / Received 3600`。
  - 删掉 `"thumbnail_height"`（界面上**没**动过的键）→ **全绿**。这是一次有价值的失败：漏写一个键不会让它回到默认值，只是**不再覆盖**，库里留的还是上一次写进去的那个数。默认值只在"那一行根本不存在"时生效。所以"先写成非默认值"这步买到的是最后那句 400 的对照（那一格没被写坏），不是"漏写键"的探针。
  - 摘掉 `_check_setting_value(key, data.value)` → 红在 `expect(poisoned.status).toBe(400)`（`:677`，实际 200），紧接着那句 `readSettings` 也会红——**这就是当年那个 500**。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 10 → 11，顺序段写清第 11 条为什么排在最后（它开头断的是空表、末尾留下四行非默认值；顺序在这里不是硬约束，因为播种那趟 `TRUNCATE` 走 `business_tables()` 会连 `settings` 一起清），`backend/CLAUDE.md` 的 §设置接口补一句值这一道校验和"范围校验为什么暂不加"。
- **验证**：真后端 e2e **11 passed**（31.3 秒，四次变异全部还原之后重跑）；`-g 系统配置` 单独跑 **1 passed**（8.6 秒）；后端 PostgreSQL 全量 **725 passed**（718 → 725 是本单新增的七条），带 `--cov` 再跑一遍确认 `api/settings.py` 71% → **100%**、TOTAL 仍是 **92%**；`typecheck:test` 绿；前端单测 **279 passed**、桩 e2e **82 passed**；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数）。
- **覆盖面现状**：浏览器用例总数实测 **93** 条——打真库 **11** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。仍然零真库签字的读路径：搜索与筛选的分面、转码任务那条长流程。


### 新增：真后端 e2e 加到 10 条——同一个目录挂两个源，扫它不出重复片、删它不伤别人的片子

- **动因**：`videos.filepath` 是**全库唯一**的，而"两个源指向同一个目录"恰好是这个约束唯一的日常成因（#102：那样每轮扫描都会撞一次 `IntegrityError`）。这个数据形状在此前九条真库用例里一次没出现过——播种只留一个源，替身夹具更是连唯一约束都没有：`page.route` 给什么前端就信什么，"重复插一行"这种事在替身侧根本不构成错误。同一批还没人签字的是源本身的读写面：`last_scan_at` 只有 `scan_service.py:330` 一个写入方，界面上那格「从未」到底是 null 还是没渲染；而 `source_service.delete` 的谓词写反一位字符就会删掉别人的片子。
- **用例 10（同目录双源）**：先读 `GET /api/sources`，把播种那个源逐字段钉住（名字 `E2E local`、`type=local`、`is_active`、`scan_interval=3600`），其中 `last_scan_at` **必须非 null**——它是播种那趟真扫描盖上去的，界面上那一格因此不是「从未」。然后在页面上走完整个生命周期：「添加视频源」填同名不同叫法、路径**照抄**播种那个源的路径，`POST /api/sources/{id}/scan` 扫它，断言 `files_found=1`（文件确实被看到了，否则"没新增"只是因为扫了个空目录）而 `new_videos=0`（#102 的不变量）；库里仍然只有一部片子、`source_id` 仍是 1、`/api/videos/1/thumbnail` 仍然回一张非空的封面（归属没被抢走）；时间戳只盖在被扫的那一个源上，源 1 那一格仍是播种时的**同一个字符串**。最后从界面点删除、走 `ElMessageBox` 确认，回到只剩播种那一个源，而**那部片子和它的封面字节数一个都没变**。
- **红在先（这条钉的也是既有契约，所以照样用变异证明能红——但这三次结果是"两次红、一次绿"，那一次绿本身就是这一单的发现）**：
  - `scan_service.py:330` 的 `source.last_scan_at = datetime.now(timezone.utc)` 注释掉 → 红在 `expect(seeded?.last_scan_at).not.toBeNull()`（`:525`）。这一句顺带证明「从未」那格读的确实是这个字段。
  - `source_service.py:99` 的谓词 `Video.source_id == source_id` 写成 `!=` → 红在 `expect(afterDelete.total).toBe(1)`（`:588`，实测 **Expected 1 / Received 0**）：删第二个源把第一个源的片子带走了。这是这一单最想要的证据——**这个操作在替身夹具里连数据都不会变**，删错了也没人知道。
  - `scan_service.py:260` 那道跨源 `holder` 跳过改成 `if False:`（等于把 #102 的修复还原）→ **用例照样绿**（`1 passed`）。但 uvicorn 日志里露出了当年的原症状：`asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint "videos_filepath_key"`，紧跟着 SQLAlchemy 的 `IntegrityError`。根因在 `scan_service.py:323-327`：每个文件各自一个 `try/except Exception` + SAVEPOINT，所以唯一约束冲突当场被吞掉、`new_videos` 依然是 0、HTTP 依然 200。**#102 修的是日志里的那一坨堆栈，不是界面上的任何一个数**——而 HTTP 层看不出区别，所以这条用例守的是**不变量**（全局唯一 filepath ⇒ 不产生重复行、不 500、不抢归属），不是那处修复。这与 #106 记下的"两道闸门冗余、只摘一道不会红"是同一类发现：**缝能守住结果，守不住过程；过程只有一份日志。**
  - 两次变异各改各的文件、各跑一次 `-g 同一个目录`（只命中这一条）、每次 `git checkout --` 后立即核对 `git status` 只剩本单要交的那一个文件，无 `DEBUG-` 残留。
- **踩到的两处接线**：一是扫描端点的路径（router prefix 本身就是 `/api`，真调的是 `POST /api/sources/{id}/scan`，照着 axios 组件里的 `/sources/${id}/scan` 拼会 404）；二是 `GET /api/videos` 回的是 `{total, items}`，对它用整对象 `toEqual` 会连带 `items` 一起比，这条只需要 `total`，就单独 `JSON.parse(...) as { total: number }` 取一个字段——与上一单 `ScanResultResponse` 那三个 `| None` 字段是同一个教训。
- **为什么它排在最后**：它新建源、扫一遍、再删掉，末尾是把 `GET /api/sources` 整张表当成"只剩播种那一个"来断言的——放在任何一条前面都可能把别人数源的断言弄红。也因此**播种不能预置第二个源**。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 9 → 10；`frontend/CLAUDE.md` 的顺序段从"九条"改"十条"，补了第 10 条为什么排最后、`/api/sources/{id}/scan` 那个前缀坑，以及证明能红用的第三条 `-g` 命令；`backend/CLAUDE.md` 的 §真后端 e2e 补一句"源表只留一个，预置第二个就会弄红这条用例"。
- **验证**：打真后端的 e2e **10 passed**（单 worker 串行，28.5 秒，三次变异全部还原之后重跑）；`-g 同一个目录` 单独跑 **1 passed**（8.9 秒）；后端 PostgreSQL 全量 **718 passed**（被变异过的两个后端文件还原后整跑一遍才是证据）；`typecheck:test` 绿；前端单测 **279 passed**、桩 e2e **82 passed**；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数，本单未提交任何后端代码改动）。
- **覆盖面现状**：浏览器用例总数实测 **92** 条——打真库 **10** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。仍然零真库签字的读路径：设置（系统配置那套键值，播种从不写 `settings` 表）、搜索与筛选的分面。


### 新增：真后端 e2e 加到 9 条——通知是广播的、已读是按人的，而"零新增那一轮"从此发不出通知

- **动因**：#85 修的是"定时扫描每轮同一条链路写两行、零新增也照发"，把通知流刷成一堵墙的那种 bug。它的修复只有两道**观察面**：`scan_service.py:347` 那道"库没变就不发"的闸门，和 `notification_reads` 那张 `(notification_id, user_id)` 复合主键表。前者在替身夹具里根本不存在（夹具给一份写死的列表，扫不扫都一样），后者要求**两个人对同一条记录有不同状态**——替身只有一份 `read`。这一单把这两面一起接到真库上。
- **用例 9（通知）**：起点是播种那趟**真扫描**留下的那一行——`total == 1`、`type == scan_complete`、`read == false`，文案里的「发现 1 个新视频」「1 条字幕」和 `data` 里的 `{source_id: 1, new_count: 1, subtitles_found: 1, missing_changed: 0}` 全是扫描器的计数器（`data` 那一列顺带成了 JSON 列在真库上的往返检查）。顶栏铃铛的角标文本是 `1`，弹层里 `.notification-item` 带 `unread` 类。然后 **#85 的回归位置**：`POST /api/sources/1/scan` 对同一批文件再扫一遍，回 `files_found=1 / new_videos=0 / subtitles_found=0`（"确实扫到了文件"和"库没变"两句要同时成立，否则"没发通知"只是因为没扫东西），而 `GET /api/notifications` 的 `total` **必须还是 1**。已读那一半走界面：点「全部已读」之后**刷新**再从接口读——不刷新就只证明了前端那句乐观更新——`read` 变 `true`、`/api/notifications/unread` 回 `{count: 0}`。反向的一半才是这条用例的意义：换成员登录，`total` 仍是 1 且 `items[0].id` 就是同一条（feed 是广播的），但对他 `read` 仍是 `false`、`unread` 仍是 1；而他能把整条流清空的那两个 `DELETE` 拿到 403（库级破坏性操作不在 `MEMBER_WRITE_PATHS` 里），删完库里那一行还在。
- **踩到的两处接线**：扫描端点的真实路径是 `/api/sources/{id}/scan`（`api/scan.py` 的 router prefix 就是 `/api`，不是 `/api/scan`；前端 axios 的 baseURL 才是 `/api`，所以照着界面写法拼出来的是 404），以及 `ScanResultResponse` 里那三个 `| None` 字段在无类型注解的 JSON 上会渲染成 `null`——用 `toEqual(整对象)` 断言会被这些"没用的字段"绊倒，改成逐字段断言。
- **红在先（这条对着未改动的代码也是绿的：它钉的是既有契约，所以照样用变异证明能红，三次各恰好 1 例红）**：
  - `scan_service.py:347` 的 `if new_videos or subtitles_found or missing_flips:` 换成 `if True:`（= 把 #85 还原）→ 红在 `expect((await readNotifications(page)).total).toBe(1)`，实测 **Expected 1 / Received 2**（`:473`）。这一条就是这单想要的证据：**症状与当年那堵墙一模一样，而且它只有在真链路上才量得到**——替身那侧"扫不扫都回同一份列表"是自洽的。
  - `notification_service.get_notifications` 里那句 `NotificationRead.user_id == user_id` 摘掉（已读变成"谁读过都算读过"）→ 红在 `expect(memberView.items[0]?.read).toBe(false)`（`:490`，实际 true）。**这句断言无法用"两边都从接口取"来替代**：owner 侧 `read` 变 true 是它自己点出来的，成员侧仍读到 true 才说明 join 漏了人。
  - `scan_service.py:348` 的文案去掉 `发现 {new_videos} 个新视频` 那半句 → 红在 `toContain('发现 1 个新视频')`（`:451`），实测 Received `"视频源 E2E local 扫描完成、1 条字幕"`（顺带量到播种那个源的真名）。
  - 最后那两句（成员 `DELETE` 403、`unread` 接口）**没有单独变异**：403 的机制与用例 6 完全同源（同一份 `MEMBER_WRITE_PATHS`，那一单已经证过摘名单会红），这里只是把通知这条路径也纳入名单覆盖；`/unread` 的按人计数与上面第二条共用同一张表，变异点也是同一处。记下来是为了不把"跑过三次变异"误读成"每条断言都被证过"。
  - 三次变异各改各的文件、各跑一次 `-g 通知是广播`（只命中这一条）、每次 `git checkout --` 后立即核对 `git status` 只剩本单要交的那一个文件，无 `DEBUG-` 残留。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 8 → 9；`frontend/CLAUDE.md` 的顺序那一段从"八条"改"九条"，并写清为什么标签和通知这两条都排在后面（它们各自把一张表当成"只有我自己的那些"，而通知那条还会再扫一遍、给 owner 写下已读、往 source 上盖新的 `last_scan_at`）；`backend/CLAUDE.md` 的 §真后端 e2e 补一句"通知同理——播种只留那一趟扫描写的那一条，多发一条就会弄红这条用例"。
- **验证**：打真后端的 e2e **9 passed**（单 worker 串行，25.9 秒，三次变异全部还原之后重跑）；`-g 通知是广播` 单独跑 **1 passed**（8.1 秒，这条自足）；后端 PostgreSQL 全量 **718 passed**（3:05——被变异过的两个后端文件还原后整跑一遍才是证据）；`typecheck:test` 绿；前端单测 **279 passed**、桩 e2e **82 passed**（34 秒那套，跑时后台没有别的东西压着）；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数，本单未提交任何后端代码改动）。
- **覆盖面现状**：浏览器用例总数实测 **91** 条——打真库 **9** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。仍然零真库签字的读路径：视频源（`/api/sources`，含"两个源指向同一目录"那个数据形状）、设置（系统配置那套键值）、搜索与筛选的分面。


### 新增：真后端 e2e 加到 8 条——标签挂到真影片上，那个 500 有了回归位置

- **动因**：`/api/tags` 这一面带过一个真 bug（#101：`GET /api/tags/{id}/videos` 回 500，`MissingGreenlet`）。它的根因是**关系加载**——序列化是同步的，而那一查经多对多的 `Tag.videos` 走到影片时没有预取第二层 `video.tags`，于是属性访问变成 greenlet 之外的一次 IO。这件事在替身夹具里不可能出现（`page.route` 直接给一份 JSON，没有会话、没有关系），所以前端那 82 条桩用例对着它永远是绿的；只有真库才拦得住。播种**一个标签都不建**，所以建标签这一下走的也是真接口。
- **用例 8（标签）**：`/tags` 页上点「添加标签」填「真库标签」建出来，卡片先是「0 个视频」；再 `POST /api/tags/video/1` 带上 `{tag_ids:[那个 id]}` 回 204（界面上这个动作在影片详情页，这里走接口把两步分开），刷新后同一张卡变「1 个视频」。**另外只建不挂一个「没挂过片子的标签」**——它必须留在「0 个视频」，这一句是让 `video_count` 无处可藏的关键：那个数要是全局的、或者是常数，两个标签就会显示同一个数。最后 `GET /api/tags/{id}/videos` 断言状态码仍是 200（#101 的回归位置），且回来的那部片子带着**自己的** `tags` 集合、里面就是刚挂上的那个 id。
- **一个必须写下来的口径**：`GET /api/tags` 是按 `Tag.name` 排序的，而中文在 PG 与 SQLite 上的排序规则不保证一致，所以那两行的期望写成 `Object.fromEntries(rows.map(...))` 的**映射**而不是数组——这条要在两种方言上都能过，数组顺序就不是可依赖的断言。同理，用例里没有任何 id 常数（除了播种实测的 `id=1` 影片），标签 id 一律从接口回读。
- **红在先（这条对着未改动的代码也是绿的：它钉的是既有契约，所以照样用变异证明能红，三次各恰好 1 例红）**：
  - `tag_service.get_videos_by_tag` 里把第二层 `.selectinload(Video.tags)` 摘掉（等于把 #101 的修复还原）→ 红在 `expect(videos.status).toBe(200)`，实测 **Received: 500**（`library.real.spec.ts:418`）。这是这一单最想要的证据：**症状和当年那个 bug 逐字一样，而它只有在打真库的缝上才量得到。**
  - `tag_service.add_tags_to_video` 的 `video.tags.append(tag)` 换成 `pass`（commit 照做，等于挂了个寂寞）→ 红在 `toContainText('1 个视频')`（`:394`），而前面那句 204 照绿——**状态码说成功了，库里没有**，这正是"只断言状态码"的空洞。
  - `api/tags.py` 的 `video_count=count` 写死成 `1` → 红在最早那句 `toContainText('0 个视频')`（`:380`）：新建还没挂片子的标签不该有数。接上一单那条经验（凡是"界面显示的就是接口给的"都要再配一句"这个值不可能是常数"），这里的"不可能是常数"就是那个**故意不挂片子**的第二个标签。
  - 三次变异各改各的文件、各跑一次 `npx playwright test -c playwright.real.config.ts -g 标签挂在真影片`、每次 `git checkout --` 后立即核对 `git status` 只剩本单要交的那一个文件，无 `DEBUG-` 残留。这一条用例是自足的（自己建标签、只依赖播种那部影片），所以单独挑它跑是安全的——和用例 6 那种"挑着跑会连带前一条红"不同，这条已写进 `frontend/CLAUDE.md` 的顺序段。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md`（覆盖面那句 + 顺序那一段：八条的顺序、标签条排最后的原因、`-g` 的安全边界）三处计数 7 → 8；`backend/CLAUDE.md` 的 §真后端 e2e 补一句「播种不建任何标签」以及为什么（将来谁在播种里加标签就会弄红整表映射那句，带影片的更会）。这一单没改任何后端代码，`src/e2e_seed.py` 的覆盖率与上一单同数。
- **验证**：打真后端的 e2e **8 passed**（单 worker 串行，23.4 秒，三次变异还原之后重跑）；后端 PostgreSQL 全量 **718 passed**（3:06——这一单改过又还原过两个后端文件，整跑一遍才是"还原干净"的证据）；前端单测 **279 passed**、桩 e2e **82 passed**（34.8 秒，这次后台没有别的东西压着，一次过）、`typecheck:test` 绿；`ruff check .` **0 项**、`mypy src` **34 项**（与上一单同数，被变异过的两个文件已回到基线）。
- **覆盖面现状**：浏览器用例总数实测 **90** 条——打真库 **8** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。仍然零真库签字的读路径：视频源（`/api/sources`，含"两个源指向同一目录"那个数据形状）、设置（系统配置那套键值）、通知、搜索与筛选的分面。


### 新增：真后端 e2e 加到 7 条——统计页的整窗和用户管理那格设备数第一次由后台算给界面看

- **动因**：上一单把"成员被真中间件拦"这一面签了字，owner 这一面的读路径还是零签字。挑的两处都不是"字段有没有"，而是**只有后台才能算出来的东西**：`/api/history/stats` 的 `daily` 要按 `days` 零填充整窗（替身夹具里那个数组是前端抄的几天，而且它完全可以不理查询参数），`/api/users` 的 `signed_in_devices` 是 `user_sessions` 的行数——只有真登录会产生真行。
- **用例 7（管理面两页）**：先 `GET /api/history/stats?days=30`，断言 `days` 回显 30、`daily` 恰好 30 格、30 个 `date` 互不重复（零填充不是"有几天算几天"），且至少一格 `seconds > 0`（播种那一行 `watch_events` 得真的落在窗口里）；`/stats` 页面的 `.bar-cell` 数到 30，「看过影片」那张卡上的数字就是接口里的 `videos_watched`（期望值从接口取，不往用例里抄第二个数）。然后点「近 7 天」：页面重画成 7 格，接口再问一次 `days=7` 也是 7 格，且 `window_seconds` 不会超过 30 天那一个（7 天窗口是 30 天窗口的子集）——前端自己数那 30 格永远发现不了"后端把 `days` 忽略了"。用户管理那页表格两行（播种的两个账号），「登录设备」那一列（第四格）逐行等于接口对应账号的 `signed_in_devices`，另加 owner 那一格 `>= 1`：owner 此刻就登录在这台浏览器上。
- **红在先（这条对着未改动的代码也是绿的：它钉的是既有契约，所以照样用变异证明能红，三次各恰好 1 例红）**：
  - `api/history.py` 里把 `get_stats(user_id, days=days)` 改成写死 `days=30` → 红在 `await expect(page.locator('.bar-cell')).toHaveCount(7)`（实测 Expected 7 / Received 30，`library.real.spec.ts:344`）。
  - `history_service.get_stats` 的零填充循环换成"只列出有事件的那几天" → 红在 `expect(month.daily).toHaveLength(30)`（Received length: 1，`:331`）。顺带量到一个事实：播种那条事件的 UTC 日期在跨 00:00 UTC 前后会变（本机 19:00 UTC 时还是前一天），所以这条用例里**没有任何日期常数**，日期只核对"30 个互不重复"。
  - `api/users.py` 的 `signed_in_devices=result.scalar() or 0` 改成写死 `0` → 红在 `expect(owner?.signed_in_devices).toBeGreaterThanOrEqual(1)`（`:358`）。这一条最值得记：**DOM↔接口 那句对照本身拦不住它**（两边都是 0 也一样相等），把这一格接到真会话行上的那根线是 `>= 1`；凡是"界面显示的就是接口给的"这种写法，都要再配一句"这个值不可能是常数"。
  - 三次变异各改各的文件、各跑一次、每次 `git checkout --` 该文件后立即核对 `git status` 只剩本单要交的那一个，`grep DEBUG-m` 无残留。
- **顺手量到的**：用 `-g 管理面` 过滤会同时命中用例 6 的标题（它的标题里有"管理面连读都 403"），于是只跑两条时用例 6 红在 `['今晚看这些', '周末再看']`——那正是"顺序即约定"的表现，不是回归；挑着跑要用 `-g 后台算出来` 这种只命中一条的说法。这条已写进 `frontend/CLAUDE.md` 的顺序那一段。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数从 6 改 7，覆盖面那句补上"第 7 条签的是两页的算法"，顺序那段补上"管理面两页可以单独跑、用例 6 不可以"。这一单没动后端一行代码，所以 `backend/CLAUDE.md` 与播种模块没有变化。
- **验证**：打真后端的 e2e **7 passed**（单 worker 串行，20.8 秒）；`typecheck:test` 绿；后端 PostgreSQL 全量 **718 passed**（3:11——三次变异全部 `git checkout --` 还原之后再跑一整遍，这才是"还原干净"的证据，不是只看 `git status`）；桩 e2e 第一次 **81 passed + 1 failed**（`player.spec.ts:119` 的 A-B 段重放），单独重跑该用例 **2 passed**、整套重跑 **82 passed**；前端单测 **279 passed**。桩那套的抖动这一晚换了第三个用例（上一单是 `:92` 和 `:189` 两条），全都是 `player.spec.ts` 里靠计时器走的用例，且都在后台压着别的东西时出现——按既有结论处理：**重跑一遍再判是不是回归**。
- **覆盖面现状**：浏览器用例总数实测 **89** 条——打真库 **7** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。仍然零真库签字的读路径：视频源（`/api/sources`，含那一带一直在讨论的"两个源指向同一目录"的数据形状）、标签管理、设置（系统配置那套键值）、通知、搜索与筛选的分面。


### 新增：真后端 e2e 加到 6 条——成员角色网关第一次撞上真中间件

- **动因**：替身夹具里那份 `MEMBER_WRITE` 是 `backend/src/middleware/auth.py` 名单的手抄本，前端单测和 82 条桩 e2e 都只对着一份可能抄歪的副本绿；而且真后端那一套夹具到这一单之前**只有一个账号**，"归属过滤"这条契约在真库上从来没被第二个人验过。这一单把两件事一起补上：播种多建一个 member，用例 6 用同一个浏览器上下文换两次身份。
- **播种侧**（`src/e2e_seed.py`）：`AuthService.create_user(..., role="member")` 建 `e2e_member`，display_name「E2E 成员」，**不写任何个人数据**——所以"成员从 0 开始加收藏""同名片单在本人范围内不冲突"这两句有东西可对。核对闸门查的是 `users.role` 这一列而不是行数：这条用例断言全是 403，"member 那行压根没建成 member"在现场和"真没权限"长得一模一样，查行数就等于把夹具坏掉伪装成用例通过。摘要多回 `member_username` 和 `users`，界面与用例都不再各自抄第二个账号名。
- **用例 6（角色网关）**：成员侧先看界面（顶栏恰好只剩「首页/播放历史/观影统计/收藏/片单」五个、用户菜单里没有「用户管理」、手敲 `/settings` 被守卫送回首页），再看请求——`GET /api/users` 与 `/api/settings` **连读都 403** 且 `detail` 是「需要管理员权限」；`DELETE /api/videos/1` 也 403，这里刻意带上 `x-requested-with: fetch`，因为中间件是**先查这个头、再查角色**，不带头的话两条 403 分不出是谁挡的；紧接着 `GET /api/videos/1` 回 200，证明那一行没被删（拒绝发生在服务层之前）。反向的一半：名单内的写必须真通，`POST /api/favorites/1` 回 201 并能在收藏页读到，`POST /api/watchlists` 用**和 owner 那份播种同名**的「今晚看这些」回 201 而不是 409（片单名的唯一性只在本人范围内成立），成员列表里也只有这一条；换回 owner 后仍是自己那两条片单、收藏 `total` 仍是 1——两个人在同一个库里各读各的。
- **顺手修的接线**：`fetchInPage()` 的第三个参数从"请求头表"改成真正的 fetch init（`method`/`body`/`headers`），否则这条用例只能测 GET；`signIn(page, username)` 支持第二个账号，并且**进 `/login` 先清 cookie**——已登录的人撞 `/login` 会被守卫直接送回首页、表单根本不渲染，这个现象第一次跑就是 30 秒超时（真库实测），而它同时是"同一个上下文里换身份"的前提。
- **红在先（这条用例对着未改动的代码本来就是绿的：它钉的是既有契约，所以用变异证明能红）**：
  - 只从 `OWNER_ONLY_READ_PATHS` 里摘掉 `/api/users` → **全 6 条照绿**。原因不是用例软，是这一面有**两层**闸门：路由上还有 `Depends(require_owner)`，而且两层回的状态码和 `detail` 一模一样，从外面分不出来。把两层一起摘掉才红在用例 6 的 `expect(blocked.status, path).toBe(403)`（`library.real.spec.ts:273`）。这一条值得单独记：**契约是"成员读不到管理面"，不是"哪一层拦的"**，所以少摘一层不红是正确行为，不是覆盖漏洞。
  - 去掉 `watchlist_service.py:_require_free_name` 里的 `Watchlist.owner_id == user_id` → 红在 `expect(named.status).toBe(201)`（`:299`，实际 409）。
  - 摘掉 `MainLayout.vue` 里「设置」那条的 `ownerOnly` → 红在 `expect(labels).toEqual([...])`（`:263`）。注意路由守卫用的是 `meta.roles`，和顶栏这两个开关是**两处独立真值**，所以这一变异不会让守卫那句跳转红——两句都在才都拦得住。
  - 三次变异各恰好 1 例红、其余 5 例照绿；每次改回后 `git status` 只剩本单要交的三个文件，无 `DEBUG-` 残留。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md`（覆盖面那句 + 顺序约定那条重写：六条的顺序、两个账号、清 cookie 的理由、闸门查 role 列的理由）、`backend/CLAUDE.md`（§真后端 e2e 补上为什么建两个账号，文件树那行改成"建 owner + member"）。
- **验证**：打真后端的 e2e **6 passed**（单 worker 串行，18.6 秒）；`tests/test_e2e_seed.py` **9 passed**；播种脚本单跑一遍摘要为 `users=2`、`role=owner`、`member_username=e2e_member`；后端 PostgreSQL 全量 **718 passed**（3:30）、真 SQLite **717 passed + 1 skipped**（0:46，`TEST_DATABASE_URL=` 那套，两套都是在播种脚本最后那次改动之后各重跑的）；带覆盖率的 PostgreSQL 全量 `src/e2e_seed.py` **58% → 55%**（新加的行全在 `seed()` 那段只有真 PG + 真 FFmpeg 才走得到的里面）、TOTAL **92%**；前端单测 **279 passed**、`typecheck:test` 绿、`ruff check .` **0 项**、`mypy src/e2e_seed.py` 干净（全项目 **34 项**与上一单同数）。桩 e2e 这一轮报 **80 passed + 2 failed**（`player.spec.ts` 的进度条拖动与偏好记忆两条），当时后台压着覆盖率全量在跑——单独重跑这两条 **2 passed**，判为 CPU 争抢下的计时抖动，不是回归。
- **覆盖面现状（先更正上一单的数：它是数错了，不是口径不同）**：浏览器用例总数实测 **88** 条——打真库 **6** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身（上一单写的"85 里 5 条、其余 80 条"两个数都不对，`npx playwright test --list` 现量的是 82 + 6）。用户管理、视频源、观影统计、设置这几页的读路径仍然没有真库签字；替身那份 `MEMBER_WRITE` 的手抄风险这单只覆盖了"成员被拦"这一面，"owner 全通"那一面仍只有桩。

### 新增：真后端 e2e 从 3 条加宽到 5 条——继续观看那条轨和片单页也到真库签了字

- **动因**：#81 立起"打真后端"那条缝时只压了三条链路（登录、字幕/流式、收藏），其余页面仍是前端对着手抄的替身响应自己绿。这一单挑的两条，共同点是**界面上那个数是另一张表算出来的**：继续观看的"剩 0:12"和进度条宽度来自 `PlayHistory.progress` 被抄到影片对象上（`history_service.py:78`），片单里那条"已看 0:18"是 `api/watchlists.py:62` 现查的 `attach_watch_progress`。替身夹具给不给这一列，前端都不会红；只有真后端不给才会红。
- **播种侧新增 `seed_user_stats`（`src/e2e_seed.py`）**：一次观看进度（`record_play` + `update_progress` 到 18 秒）加一条带说明的片单，全部走**服务层本身**，不手写 INSERT。理由是 `completed` 由 `is_completed()` 按 `duration` 的尾部容差算（30 秒的片子门槛是 28.5 秒），而那条轨只读 `completed == False` 的行——夹具自己抄一份判定，容差规则一改就悄悄失真成"库里说看完了、界面上还在轨里"，两边看着都自洽。落库之后**只选列不选实体**地重查一遍（这个进程是 `expire_on_commit=False`，读刚 commit 过的 ORM 实例拿到的是内存值不是库里的值），再加四道闸门：历史行数、`[progress]`/`[completed]` 的具体形状、片单条目数，对不上就起步即失败。
- **用例 4（继续观看）**：先 `GET /api/history/continue` 拿真行，断言 `progress` 非空且 `0 < progress < duration`；首页 `.resume-rail` 的"1 部没看完"、`剩 …` 文案、进度条内联宽度（读样式串里的百分比，不拿 px 比）全部用**后端那一行**算出来的期望值去比，期望值不往用例里抄第二个 18；点进去落到 `/videos/1`，`/history` 上同一行的 `.continue-card` 也读得到。
- **用例 5（片单）**：`GET /api/watchlists/1` 的 `items[0].progress` 不为 null（这条最容易被替身糊过去），页首「1 个片单 · 1 条排队」、`.list-desc` 正是播种写的那句说明、`.queue-meta` 含「已看 …」；再从详情页的弹窗新建「周末再看」并把这部片子放进去，页首变「2 个片单 · 2 条排队」，并向 `GET /api/watchlists` 回读核对条目总数确实是 2——不是前端把刚点那一下乐观地留在内存里。
- **红在先（这两条对着 HEAD 本来就是绿的：它们钉的是既有契约而不是修复，所以用变异来证明能红）**：去掉 `history_service.py:78` 那句 `record.video.progress = record.progress` → 用例 4 红在 `expect(row.progress).not.toBeNull()`；跳过 `api/watchlists.py:62` 的 `attach_watch_progress(...)` → 用例 5 红在 `expect(list.items[0].progress).not.toBeNull()`。两次各恰好 1 例红、其余 4 例照绿，改回后 `git diff --stat` 只剩本单要交的文件、`grep DEBUG-` 无残留。
- **顺手修的夹具缺陷**：扫描没写出影片行时，`video_ids[0]` 会先抛 `IndexError`，把"扫描没产出片子"这个根因盖成一句看不懂的栈——现在把那条计数核对挪到写入之前，报的仍是同一句话。这段只有坏夹具才走得到，要真 PG + 真媒体目录 + 真 FFmpeg，pytest 侧没有为它单独立例，也没做变异证明。
- **顺序成了约定**：用例 5 自己会往库里新建一条片单，所以"只核对 1 个片单"的那一段必须排在它前面。`playwright.real.config.ts` 里那句"三条用例共用一个库"的注释改成了这件事（`workers: 1` + 非并发的理由也从"互相清行"更正为"共用一次播种、后写的会改前一条的计数"）。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md`（覆盖面那句按新读法重写）、`backend/CLAUDE.md`（播种为什么走服务层、`src/e2e_seed.py` 覆盖率 57% → **58%**、薄位置清单的复量时间）四处从"3 条"改成"5 条"。
- **验证**：打真后端的 e2e **5 passed**（串行单 worker，约 16 秒）；`tests/test_e2e_seed.py` **9 passed**（新增那条要求 `completed` 归 `is_completed()` 说了算、片单名与说明都落库）；后端 PostgreSQL 全量 **718 passed**（3:44）、真 SQLite **717 passed + 1 skipped**（1:16，`TEST_DATABASE_URL=` 那套，判据见上一单），两套串行；带覆盖率的 SQLite 全量 **TOTAL 92%**；前端单测 **279 passed**、桩 e2e **82 passed**、`typecheck:test` 绿；`ruff check .` **0 项**、`mypy src` **34 项**（与上一单同数，改过的文件零新增）
- **覆盖面现状（别把这条读成"缺口关上了"）**：85 条浏览器用例里打真库的是 **5** 条，其余 80 条继续对着 `e2e/fixtures.ts` 的替身。用户管理、视频源、观影统计、设置这几页的读路径仍然没有签字。

### 更正：此前几单报的"SQLite 全量"跑的其实是 PostgreSQL——判据在 `backend/.env` 里，不在命令行上

- **撞出来的经过**：这一晚连着几单都在末尾写"SQLite N passed + 1 skipped / PostgreSQL N+1 passed"，两边数字只差那条 PG-only 的搬迁用例。核对上一单的原始输出时才发现，被标成 SQLite 的那一套里根本没有 skip 行——它跑的就是 PG。命令一模一样（`python -m pytest`），差别只在环境变量
- **为什么会这样**：`tests/conftest.py:42` 取的是 `settings.test_database_url`，而 pydantic 的 `Settings` 会读 `backend/.env`；这台机器的 `.env` 在 2026-10-04 切 PG 时就把 `TEST_DATABASE_URL` 一并写进去了（指向 `home_sites_test`）。所以**裸 `pytest` 是 PostgreSQL**，之前那种"默认走内存 SQLite"的理解在切库之后就失效了，而我一直在按失效的理解报数
- **正确的取法**：真 SQLite 要显式清空——`TEST_DATABASE_URL= python -m pytest ...`（环境变量在 pydantic-settings 里压过 `.env`）。判据也简单：**看到 `tests/test_db_transfer.py:335` 那条 skip（"需要真 PostgreSQL：设 TEST_DATABASE_URL 才跑"）才是 SQLite 跑过**，PG 那一套是 0 skipped
- **这一单把两家各重测了一遍**：SQLite **716 passed + 1 skipped**、PG **717 passed**，用例数一致，所以上几单的功能结论没有受影响，受影响的只是"这套是在哪种方言上验的"这句话
- **写进文档的是纪律，另加一个会自己报话的头部**：光立纪律拦不住——判据不在命令行上。所以 `tests/conftest.py` 加了 `pytest_report_header`，每次运行在头部印「测试库: 真库 postgresql（TEST_DATABASE_URL 来自环境或 backend/.env）」或「测试库: 内存 SQLite（TEST_DATABASE_URL 为空…）」，两种方言各实测一遍都印对。注意 **`-q` 会把这段一起吞掉**，要看见它得用不带 `-q` 的跑法；`backend/CLAUDE.md` 的 PostgreSQL 一节把这两条印记（头部 + `test_db_transfer.py:335` 的 skip）都写成了报数前的检查项
- **此前各单里被标成 SQLite 的通过数没有回头改**——它们里有些是真 SQLite（早期确实带过空值，且都记着 `+ 1 skipped`），事后无从分辨；与其 retro 重写历史，不如把判别方法立起来

### 修复：两个视频源指向同一目录时每轮定时扫描都在刷回溯，而那条本该报出问题的 `scan_error` 通知从来没落地过

- **动因**：验证上一单（备份补跑）时在真机器上留下的日志里，每 30/60 分钟就刷一段完整的 `IntegrityError` 回溯：`duplicate key value violates unique constraint "videos_filepath_key"`。原因是 `video_sources` 里 5 号和 6 号都指着 `backend/data/test_videos`（6 号是转码走查时留下的），而"这个文件我认识吗"的判断只看**本源**的行，别源建过的路径就被当成新片重插一次
- **第一个假设被自己的复现打脸**：以为撞一次唯一约束会把整轮扫描带走。真写用例跑，两条都绿——`scan_service.py` 每个文件外面套着一层 `begin_nested()`（SAVEPOINT），单次失败只回滚那一个文件。所以缺陷不是"整轮炸"，是另外两件事，下面分开修
- **改法 A（`scan_service.py`）**：插之前先问一句这条路径归谁（`select(Video.source_id).where(Video.filepath == filepath)`），有主了就 `logger.info` 跳过并计入新加的 `foreign_paths`，返回值与 docstring 一并带上这个键。为什么不"撞了让 SAVEPOINT 救"：撞一次日志就是一整段回溯、每轮对每个撞车文件重撞一次，而界面上永远看不到"这片子是别的源建的"
- **改法 B（`scheduler/tasks.py`）才是这单真正的死路**：`except` 里直接拿**刚被失败 flush 弄脏的那个会话**去写通知，那条 `create()` 自己就抛 `PendingRollbackError`，再被下一层 `except Exception: logger.exception(...)` 咽掉。真机现场因此是「0 条 `scan_error` 配上一整日志的 `IntegrityError` 回溯」——"扫描失败一定发通知"这条承诺，恰好在最需要它的失败形状上是死的。修法是写通知之前 `await session.rollback()`，两处（单源与全量）都补
- **先红**：`tests/test_services/test_scan_service.py` 新增两条在 HEAD 上报 `KeyError: 'foreign_paths'`（其中一条同时暴露 SAVEPOINT 之后同会话下一查的 `PendingRollbackError`——撞一次不能把同一份清单里那部真正的新片一起带走），`tests/test_scheduler_scan.py`（新增文件，2 条）报的是 `PendingRollbackError`；四条都在 HEAD 的 `git worktree` 里验过红，补完实现两种方言各绿
- **顺带记下但没动的数据问题**：`video_sources` 的 1–4 号指向的路径根本不存在（`/data/videos`、`/tmp/test_videos`、`/tmp/api_test`、`/tmp/api_test2`），却都是 `is_active=t`，每轮扫一次空目录。删行是动真库的数据，留给用户点头
- **验证**：真 SQLite（`TEST_DATABASE_URL=`）**716 passed + 1 skipped**、PostgreSQL **717 passed**，两套串行；`src/scheduler/tasks.py` **62% → 92%**、`scan_service.py` **96%**；`ruff check .` **0 项**、`mypy src` **34 项**（与上一单同数，改过的两个文件各零项）；打真后端的 e2e **3 passed**（10.8s，扫描这条路径由真 uvicorn 走了一遍）
- **真机复核（throwaway 脚本直连 `home_sites` 各扫一遍 5 号与 6 号源，用完即删）**：两边都是 `files_found=6, new_videos=0, foreign_paths=3`，日志里是六行「跳过 …：这条路径已属于视频源 N」，**一段回溯都没有**；`notifications` 仍是 4 行（零新增照旧不吭声，#85 那条约定没被破坏）。顺带量到真实的数据形状：这两个源把同一个目录**对半分**了（5 号占 `sample_1..3.mp4`，6 号占 `long_720p.mp4` 与 `sub/` 下两条），所以撞车不是"某一个源是多余的"，而是历史插入顺序把同一批文件劈成了两半——这一单没去动它
- **生效条件**：:8000 已重启到这份工作树（PID 40184，日志 `data/dev-102.log` / `dev-102.err.log`），下一轮定时扫描起就走新路径

### 修复：`GET /api/tags/{id}/videos` 的 500——响应模型要读的关系，得写进查询里

- **怎么撞出来的**：跑全量带覆盖率的套件时偶然红了一条，`GET /api/tags/{id}/videos` 回 500，`api/tags.py:118` 那里报 `ResponseValidationError: {'loc': ('response', 0, 'tags'), 'msg': "Error extracting attribute: MissingGreenlet: greenlet_spawn has not been called"}`。同一套用例重跑又是绿的——它取决于会话里那枚 `Video` 实例当时冷不冷
- **先红**：把那个状态钉死的用例是 `tests/test_api/test_tags.py::test_videos_of_a_tag_come_back_whether_or_not_the_session_is_cold`，用 `db_session.expire_all()` 造出"会话里已有同名实例且已过期"。在 HEAD 的 `git worktree` 里验的红：同两个文件 1 failed（就是这条，报的正是上面那句 `MissingGreenlet`）+ 31 passed，验完删掉工作树
- **根因**：`VideoResponse` 带着 `tags`，而这一查是经**多对多**的 `Tag.videos` 走到影片的，那批影片的 `tags` 集合没有被关系上的 `lazy="selectin"` 带上。pydantic 的序列化是同步的，于是那一下属性访问就是一次 greenlet 之外的 IO。改法是把要加载的关系写明：`selectinload(Tag.videos).selectinload(Video.tags)`
- **这不是给生产补的活 500**：会话工厂是 `expire_on_commit=False`，每个请求又各一个新会话，所以今天真服务器走不到这条。修它是因为**状态码不该取决于会话冷热**——同一句查询、同一个端点，会话热的时候 200、冷的时候 500，那是一条谁都可能踩上的脆性
- **顺手把同一形状的其它读接口都扫了一遍**：新文件 `tests/test_api/test_video_reads_with_a_cold_session.py`（5 条：影片列表、单取、继续观看、收藏列表、片单详情）。这 5 条在 HEAD 上**本来就是绿的**，钉的是既有不变量而不是修复。差别有实测的形状：经**多对一**（`PlayHistory.video` / `Favorite.video` / `WatchlistItem.video`）走同样的冷会话都能带出标签，只有经多对多集合那一头会漏。为什么多对一没漏，我没能从文档里推出一条一般规则，所以纪律写成"响应模型碰到的关系就写进查询"，不指望默认加载兜住
- **验证**：`tests/test_api/test_tags.py` 27 passed、`test_video_reads_with_a_cold_session.py` 5 passed，两种方言各一遍（真 SQLite 与真 PG 各 32 passed）；`ruff check .` 0 项，`mypy src` 34 项（与上一单同数，一处没动）；全量数字在下一单末尾

### 修复：漏掉的每晚备份不再无声消失——醒来补跑，启动时按目录补一趟

- **动因**：`03:30` 那条 cron 只在"那个分钟进程正好活着"时执行。机器睡着、进程被占用，APScheduler 默认只给 **1 秒**宽限，过了就把这一轮丢掉，只在日志里留一行；而备份成功本来就不发通知（#85 定的"变了才说"），于是"备份已经停了三天"和"备份一直健康"看起来一模一样。`tasks.py` 里原先写着"失败通知是人们得知备份停了的唯一途径"——这个假设正是这一单要纠正的
- **机制是实测出来的，不是读文档读的**：临时脚本把这条 cron 的 `next_run_time` 推到 5 小时前。默认配置打出 `Run time of job "backup_database_task" was missed by 5:00:00.000878`，函数一次都没进；换成 `misfire_grace_time=None` 之后同一份脚本立刻跑出 dump。另一半是**进程压根没开着**的那种漏：没有 misfire 可言，APScheduler 重启时直接把下次执行算到明天，所以宽限救不了它，只能靠启动时主动看一眼目录
- **`backup.is_stale()`**：最新的 dump 超过 **36 小时**（或目录空、目录不存在、里面只有手工命名的快照）就算陈旧。线故意比 24 小时长一截——否则昨夜健康、今天 04:00 重启一次服务，也会被当成出了事；stat 拿不到文件时间按陈旧算而不是抛，这条跑在启动路径上，一条悬空记录不该把服务带倒
- **启动补跑挂成一次性任务**（`add_backup_catchup_job`：`DateTrigger` + 独立 job id，先拆后装，跑完自己从任务表里消失），和每晚那条用同一个闸门（`BACKUP_ENABLED` 且 URL 是 PostgreSQL）一起装；任务体只做一件事——陈旧就 dump，成功照旧一声不吭
- **失败通知现在分得清是哪一趟**：每日那条还是「每日数据库备份失败」，补跑那条是「补跑数据库备份失败」（`data.kind` 也带上了）。两条 dump 走的是同一个 `_dump_and_notify`，不再各写一遍异常处理
- **先红**：`tests/test_backup.py` 在 HEAD 上跑到的是 `ImportError: cannot import name 'is_stale'`，`tests/test_scheduler_backup.py` 是 `ImportError: cannot import name 'BACKUP_CATCHUP_JOB_ID'`（用一份 `git worktree` 的 HEAD 检出验的，验完删掉）；补完实现后两个文件 18 + 11 全绿
- **端到端复核**：一次性脚本把 cron 那一轮推到 5 小时前再启动调度器，跑出两趟 dump（misfire 的每晚 + 空目录的启动补跑），catch-up 任务随后自己消失，每晚那条的 `next_run_time` 正常落到明天 03:30。脚本用完即删，没有留在仓库里
- **一个故意不铺的守卫**：进程活着但被卡住超过 36 小时时，醒来那一趟和启动那一趟会各 dump 一次。两份都是可恢复的备份、轮转照旧，多一次 pg_dump 不值得为它加一层跨任务状态
- **验证**：`ruff check .` **0 项**、`mypy src` **34 项**（与前一单同数，这一单没有新增，也没有落在改过的文件上）；SQLite 全量 **706 passed + 1 skipped**、PostgreSQL 全量 **707 passed**（两套串行）；前端单测 **279 passed**、桩 e2e **82 passed**、打真后端的 e2e **3 passed**；`src/backup.py` 在这两份用例下是 **95%**（剩 6 行：pg_dump 的几条兜底和 `is_stale` 里 stat 失败的分支）
- **生效条件**：这些都在进程启动时挂载，正在跑的后端要重启才会带上新的宽限配置和补跑任务

### 修正：coverage 一直在少算异步代码，配上 `concurrency = ["greenlet", "thread"]` 之后薄位置重测了一遍

- **是怎么撞出来的**：上一单给标签接口补完 26 条用例，报告说 `api/tags.py` 只有 76%、`tag_service.py` 只有 37%，可这些用例明明就是从 `create()` / `update()` 的函数体走出去的。去对照 `watchlists`（74% / 45%）才发现不是标签一处的怪事——**全仓的异步代码都被少算**，缺的行整齐地都排在某个 `await` 之后
- **根因**：SQLAlchemy 的 async 引擎是用 greenlet 把同步 API 桥到协程上的，每个 `await` 都过一次 greenlet 切换；coverage 默认不知道有 greenlet，行追踪器在切换回来之后没有重新装上，于是那一段执行不记账。修法是 `backend/pyproject.toml` 加一段 `[tool.coverage.run] concurrency = ["greenlet", "thread"]`，让 coverage 换成 greenlet 感知的追踪器并同时接管 `threading.settrace`（调度任务跑在自己的线程里）
- **改的只有配置，`src/` 一行没动**：同一套全量在两种配置下的读数——TOTAL **86%（589 miss）→ 91.49%（364 miss）**，而两次都是 698 passed + 1 skipped。通过数一致正是这条修正该有的形状：被补回来的确实是一直在执行的行，不是新测了什么
- **薄位置清单按修正后的读数重测**（76 个 `src/` 文件里 26 个已到 100%）：`utils/ffmpeg.py` **23%**（同步的 subprocess 调用，本来就不吃这个修正，转码要真 FFmpeg 和真片子）、`scheduler/tasks.py` **57%**（缺的是 `scan_source_task` / `scan_all_active_task` 两个包装的函数体和它们的 `scan_error` 通知分支——测试是直接调 `ScanService` 的）、`src/e2e_seed.py` **57%**（活在打真后端的 e2e 那个进程里，pytest 进程只 import 和调一部分）、`api/settings.py` **71%**（批量改配置和单键读写两条端点没人调）、`api/stream.py` **72%**（整文件直读与"封面文件不在"的兜底；`Range` 分段由真后端 e2e 覆盖，不在这份读数里）
- **反过来纠正一句上一单的话**：`tag_service.py` 此前记的 32% 有两三成是少算，但接口层确实几乎没测——把新增那 26 条排除掉、用修正后的配置重测，是 `api/tags.py` **58%** / `tag_service.py` **39%**。补完之后 **100% / 97%**（还剩 51-52 行，是没人调用过的 `list_all()`）
- **闸门 80 保持不动**：未修正的读数本来就过 80，动了它会把 2026-10-04 那条历史数字读歪；余量由 6 个点变成 9 个点，是同一份用例被更如实地记账而已。`backend/CLAUDE.md` 第 5 节现在把"看单文件百分比之前先确认这条配置在"写成戒律
- **验证**：这条改的是度量而不是行为，所以没有"先红"那一步——红的是那 225 行此前一直被误报成空白。`ruff check .` **0 项**、`mypy src` **34 项**（都没碰 `src/`，与上一单同数）；带覆盖率 PostgreSQL 全量 **699 passed**，TOTAL **91.51%**（363 miss）、SQLite **698 passed + 1 skipped**，TOTAL **91.49%**（364 miss），两套串行跑，通过数与修正前一致

### 修复：重名建标签此前是 500（`IntegrityError` 顶到 ASGI 层），现在回 409 并带标签名

- **动因**：给标签接口补集成测试时撞出来的。`tags.name` 上明写着唯一约束，而界面上"新建标签"和"改名"都是点得到的日常操作——重名是使用者的常态（手滑），不是异常。之前它直接把 `sqlalchemy.exc.IntegrityError` 抛穿 ASGI，真服务器上就是 500，界面弹「Operation failed: Request failed with status code 500」；更糟的是失败的那一次会把会话弄脏，同一进程里紧接着的下一条查询回 `PendingRollbackError`
- **先红**：`tests/test_api/test_tags.py`（新增 26 条）在修复前跑出的就是这两条红——`test_a_second_tag_with_the_same_name_conflicts_instead_of_500`、`test_renaming_onto_an_existing_name_conflicts`，其余 24 条绿；报的是 `UNIQUE constraint failed: tags.name`
- **改法按仓库已有的惯例**：`services/tag_service.py` 加 `DuplicateTagNameError(ValueError)`，`create()` 与 `update()` 在写之前先按名字查一次 id（改名时同名到自己不算冲突），抛中文详情「标签「科幻」已存在」；`api/tags.py` 的 POST 与 PUT 把它映射成 **409**，且 `except` 排在通用的 `ValueError`→404 **之前**（它是子类，顺序反了就会把重名报成"标签不存在"）。这一处与 `watchlists` 的 `DuplicateWatchlistNameError` 是同一个形状：服务层判别异常，接口层负责状态码
- **为什么是先查而不是捕获 `IntegrityError`**：预检让失败的那一次根本不进 `commit()`，会话保持干净；捕获 `IntegrityError` 则要先弄脏再回滚，而回滚会把同一请求里已做的别的改动一起带走。竞态窗口（两个请求同时建同名）仍然由数据库唯一约束兜底，只是那种情况下会退回 500——写标签是 owner 一个人的手，这条路不去铺
- **接口层此前完全没有测试**：八个端点都在界面上被用着（`Tags.vue` 建改删、`VideoDetail.vue` 贴与摘、`Home.vue` 读列表算片库分布），覆盖到的只有模型用例和角色扫面。这 26 条把默认色、非法色 422、空 patch 400、单取/删/改的 404、删掉在用标签只走关联不碰影片、贴标签幂等、失效 tag id 跳过不判死整次请求、以及"按标签查影片"的空结果与 404 都钉住
- **两处我自己假设错了，改的是用例不是代码**：一是 `order_by(Tag.name)` 排的是 **UTF-8 字节序**而非拼音（SQLite 的 BINARY、PG 建库时钉死的 `C` collation 都是字节序，两种方言给同一个答案：剧 U+5267 排在 动 U+52A8 之前）；二是接口和用例共用 `db_session` 时，那条影片的 `tags` 集合在贴标签时已经加载过，删完标签不 `expire_all()` 就会读到身份映射里的旧集合——真服务每个请求一个新会话，不会有这个现象，所以用例里显式失效并写明原因
- **验证**：`ruff check .` **0 项**、`mypy src` **34 项**（与上一单同数，`api/tags.py` 那三条"端点返回 ORM 对象"是既有基线，这一单没去动）；带覆盖率的 PostgreSQL 全量 **699 passed**（3:10）、SQLite **698 passed + 1 skipped**（59s），两套串行跑；前端单测 **279 passed**、桩 e2e **82 passed**、打真后端的 e2e **3 passed**
- **顺带量到的一件事（这一单没改，只记下来）**：那 26 条把 `api/tags.py` 打到 100%、`tag_service.py` 打到 97%，前提是给 coverage 配上 `concurrency = ["greenlet", "thread"]`；默认配置下同样的用例只报 **76% / 37%**。原因是 SQLAlchemy 的 async 引擎每个 `await` 过一次 greenlet 切换，行追踪器在切换后丢失，于是落在 `await` 之后的真被执行过的行被报成空白——全量 TOTAL 同样被少算（86% vs 91.49%，两次通过数一致）。这条对方程式的接口层和服务层普遍成立，所以此前那些"某某文件只有 32%"的薄位置清单要打折读，已写进 `backend/CLAUDE.md`

## 2026-10-04

### 补测试：`src/cli.py` 与 `utils/file_scanner.py` 从 0% / 38% 到 100%，覆盖率闸门挂上 80

- **动因**：积压里那条"装了不用"——`pyproject.toml` 有 `pytest-cov` 依赖却没有任何覆盖率配置，而两个模块是彻底的空白：`src/cli.py` 0%（全仓没有一处 import 它，tests 里那些 `create_user` 匹配全是 `AuthService.create_user`），意味着**建第一个账号和老数据认领这两条路从来没被执行过**；`utils/file_scanner.py` 38%，`os.stat` 失效、ffprobe 不存在、ffmpeg 挂死那些分支一个都没碰过。这两个恰是"新装的库第一次启动"和"盘掉线/工具没装"两条最坏的现场
- **`tests/test_cli.py`（新增，29 条）**：参数表（默认角色、`--username` 必填、角色不在清单里当场 `SystemExit`）、口令问两次的三条分支（过短、两次不一致）、四个命令的处理器逐个过真库（拿 `db_session` 上的 `AuthService`，不 mock 服务层），以及 `main` / `_run` 的分发矩阵——四条命令各测一次"解析出来的命令名走到对应的处理器"，`_run` 那条兜底的 `return await _revoke_sessions(...)` 因此不再是"拼错命令名也悄悄踢下线"的暗区。交互输入按本项目一贯做法绕过 `getpass`（Windows 上它读控制台不读管道），改成给 `getpass.getpass` 打补丁
- **`tests/test_utils/test_file_scanner.py`（新增 23 条）**：真 `tmp_path` 下的递归（非 ASCII 目录名、大小写后缀统一小写入库、字幕/封面/说明文件不进结果）、`ffprobe` 输出的每种坏形状（回 `N/A` 的时长、只有音频流、有视频流却没尺寸、输出被截断成非 JSON、`returncode != 0`），以及 `ffmpeg` 的"回 0 但没写出文件"这一类骗人成功。探针是打补丁替换 `subprocess.run`，转真工具留给打真后端的 e2e
- **写用例时自己踩的两处，都是我对代码的假设错了**：一是 `os.walk` 在 Windows 上**会**走进 junction（`os.path.islink()` 对 junction 回 `False`，于是它被当成普通目录递归）；二是 `generate_thumbnail` 的 `-ss` 其实排在 `-i` **之后**（解码到 1 秒处的精确取帧，不是快速 seek）。两条都没去"修"，改成把实际形状钉住并在用例里写清为什么这是想要的行为——跨盘片库正是靠 junction 扫得全，而闸门在"只有 owner 能加视频源"上，遍历阶段再拦一层只会把库扫成半套
- **那条 junction 用例是真跑出来的**：`cmd /c mklink /J` 不需要管理员权限（`os.symlink` 才需要），所以现场造一个指向库外目录的联接点、让它被扫到，而不是 `skip` 掉假装验过
- **护栏的形状**：`fail_under = 80` 写在 `[tool.coverage.report]` 而不是 pytest 的 `addopts`。区别是后者会让"只跑一个文件"也去比总量，一个文件天然不到 80，报回来的红和"测试坏了"长得一模一样。现在只有显式 `pytest -q --cov=src` 才闸门，实测能红：单跑那个扫描文件时报 `Required test coverage of 80.0% not reached. Total coverage: 39.20%`。同时排除 `if __name__ == .__main__.:` 那行——模块入口守卫靠 import 走不到，留给真机 `python -m src.cli`
- **没去凑数的地方**：`utils/ffmpeg.py` 23%（要真 FFmpeg 和真片子）、`services/tag_service.py` 32% 与 `api/tags.py` 59%、`scheduler/tasks.py` 71%，位置写进 `backend/CLAUDE.md`，别用只断言"没抛异常"的用例把总数抬上去
- **验证**：这套新用例是**给既有行为补覆盖**，不是修 bug，所以没有"先红"那一步——红的是那两个模块此前从未被执行。`ruff check src tests` **0 项**、`mypy src` **34 项**（未触碰 `src/`，两处数字都与上一单相同）；全量带覆盖率 SQLite **672 passed + 1 skipped**（56s，TOTAL 86%）、PG **673 passed**（3:03，TOTAL 86%），两套串行跑


### 清理：mypy 从 95 项降到 34 项，剩下的 34 项是两类边界，不是漏了注解

- **动因**：和 ruff 那一单同一个理由——总数长期不为零，"报红"就没有信息量。这一单只关"注解真的缺失或写错"的那些，关不掉的按类留下并写清为什么
- **配置**：`backend/pyproject.toml` 加 `[[tool.mypy.overrides]]`，只对 `apscheduler.*`、`boto3.*`、`botocore.*` 关掉"缺 stub 即报错"。缺的是别人的声明，不是我们的注解；范围钉死在这三个包，其余照旧，`warn_unused_configs` 也不会因此误报
- **补的是真漏的注解**：存储层两个 `iter_range` → `Iterator[bytes]`、`_client` → `Any`（如实承认 boto3 客户端是外来的动态对象，而不是伪造一个精确类型）、`file_iterator`、`_respond(watchlist: Watchlist)`、`**kwargs: Any`（值是按 `hasattr` 挑着往模型上设的，写死一种只会骗过检查器），以及 `video_service` 里 9 个内部表达式函数的 `ColumnElement[bool]`
- **三处是写错了，值得单独说**：`_with_videos() -> select` 拿构造函数当类型；`get_session() -> AsyncSession` 其实是个异步生成器（改 `AsyncIterator[AsyncSession]`）；`AuthMiddleware.__init__` 的 `app` 标成 `Callable[..., Awaitable[Response]]`，和 `BaseHTTPMiddleware` 要的 `ASGIApp` 不是一回事——这一处改对之后，`main.py` 那条 `add_middleware` 的报错跟着消失，两条错是一个源头
- **SQLAlchemy 的类型形状是这单最费探针的地方**：`Video.title` 在类型上是 `InstrumentedAttribute[str | None]`，`ColumnElement[str]` 和 `KeyedColumnElement[str]` 都不收；`TypedColumnElement` 运行时有、mypy 看不见（`sqlalchemy.sql.expression` 与 `.elements` 都试过）。于是 `_like` 收裸 `ColumnOperators`（`.ilike` 真正住的接口），返回的布尔表达式 cast 一次。另外这个 2.0.51 还没有 `Unmapped`（`from sqlalchemy.orm import Unmapped` 直接 ImportError），"在模型上声明瞬态属性"那条路走不通——不是不想，是没有
- **`warn_return_any` 那几处逐个收窄**：`json.loads` 两处、`getattr` 一处、`_scan_state[...]` 一处、`proc.stdout` 一处。都因为声明比实际宽（`json.loads` 只到 Any），没有一处是为了凑数
- **顺手改准三处等价写法**：`total` 由 `session.scalar(count)` 改为 `execute(...).scalar_one()`（COUNT 必回一行，`scalar()` 那个 `Optional` 是给"可能没有行"的一般查询准备的）；三处 DML 的 `result.rowcount` cast 成 `CursorResult`（`rowcount` 只在那个类上，且不为这个数字再发一条 count 查询）；watchlist 三个写路径的回读收进 `_read_back`，同一个判空不必各写一遍
- **全程只加了 1 处 `# type: ignore`**：`src/storage/s3.py` 里"导入失败就用占位类"的 `ClientError`（`no-redef`）。重复定义正是那段的意图，豁免这一条比把可选依赖变成硬依赖便宜得多
- **这次唯一动了运行时数据形状的地方**：`get_duplicates` 的分组改成 `(file_size, group)` 一路带下去，于是 `wasted_bytes` 用的是分组键而不是再从可空的 `Video.file_size` 上读一次——值相同（同组本就同大小），但这是行为面，重复检测的用例覆盖它
- **剩下的 34 项不该在这一单里关**：27 项在 `src/api/*`，形态都是"端点的返回注解就是 FastAPI 的 response_model，函数体返回 ORM 对象或 dict，序列化时才由 `from_attributes` 转换"。清零只有两条路：每个端点显式 `XxxResponse.model_validate(...)`，或者把注解摘掉改用 `response_model=`——那都会改到 API 层的写法，是设计决定，不是清理。另外 7 项是挂在模型实例上的瞬态属性（`Video.progress`、`Video.is_new`、`Notification.read`），由 service 层贴上去给响应模型读；真要清，得把这这类数据从模型上挪走
- **没开 `sqlalchemy.ext.mypy.plugin`**：它能吃掉一部分 Row 推导，但会同时引入一整批待核的新报错，深夜无人复核不合适
- **验证**：`ruff check .` **0 项**；`mypy src` **34 项**（95→72→34）；后端 PG **621 passed**（2:43）、SQLite **620 passed + 1 skipped**（43s），两套串行跑的；打真后端的 e2e **3 passed**（10.7s，收藏、流式 `Range`、字幕这三条链路正好压在改动上）；前端未触碰

### 清理：ruff 的 99 项既有欠账归零，改完"lint 红了"才重新成为证据

- **动因**：`ruff check .` 长期报 99 项，于是每次改动只能靠"这个文件改前改后各几条"来判断，"全绿"这个信号对本项目是废的。这一单把它清干净，之后 ruff 报红就只可能是新代码带来的
- **按类的处理方式**：`I001` 53（导入排序）、`W292` 4（缺末行换行）、`F401` 9（未用导入）走 `--fix`；`F841` 8（绑了不用的局部变量）手改，全在测试里，都是"造数据只为副作用"的那类夹具——**保留调用、去掉赋值**，删掉调用会把被测前提一起删了；`E501` 17 折行；`N818` 4 改异常名；`E402` 4 用 per-file-ignores 放行
- **四个异常是改名，不是豁免规则**：`_Rollback`→`_RollbackError`、`DuplicateWatchlistName`→`DuplicateWatchlistNameError`、`UnsupportedStorage`→`UnsupportedStorageError`、`StreamNotFound`→`StreamNotFoundError`。理由是这条规则总共只有 4 处违反，改名是几十处机械替换，而全局豁免会让以后所有同类命名都失明。`backend/CLAUDE.md` 的目录地图里那行同步改了
- **`E402` 只豁免 `tests/test_storage/test_s3_storage.py` 一个文件**，理由写在配置注释里：那个文件必须先把 S3 的环境变量摆好再 import boto3/moto，导入天然不在顶部。这是四条同类项共有的、唯一正确的形状，不是"测试文件可以乱来"
- **配置**：`select` 从 `[tool.ruff]` 顶层挪进 `[tool.ruff.lint]`（顶层形状已废弃，之前每次运行都打一行警告，噪音盖过信号），新增 `[tool.ruff.lint.per-file-ignores]`。`line-length = 100` 和 black 保持一致，没动
- **没开 `--unsafe-fixes`**：那 8 项隐藏修复会改语义（比如把带副作用的调用整行删掉），这一单的验收标准是"行为一点没变"，不能拿它换计数
- **`F401` 没误删转发用**：`src/models/__init__.py` 那批 `from .x import Y` 看着"没被引用"，其实是给 `from src.models import Y` 和 SQLAlchemy 注册映射用的——因为有 `__all__`，ruff 只重排不删除，diff 逐行核对过
- **折行翻过一次车，被自家工具链抓住**：批量改写脚本里 `"1\n00:00:01,000…"` 的转义层数少了一层，`tests/test_api/test_subtitles.py` 的默认字幕串被写成真空行、文件语法坏了。是 `ruff` 的 `invalid-syntax` 和 `python -m compileall` 报出来的，不是靠"错误数变少了"——统计会掩盖这种坏，逐条看才是办法
- **验证**：`ruff check .` **0 项**；后端 SQLite **620 passed + 1 skipped**（43s）、PG **621 passed**（2:47）；打真后端的 e2e **3 passed**（10.7s，重命名过的异常和流式路径都在那条链上跑过）；前端未触碰。中途那次 PG 假红是**自己并发跑了两套 pytest**：两套同时对 `home_sites_test` 下 `TRUNCATE`，互等出满屏 `DeadlockDetectedError`，与代码无关，已把"同一时间只能有一套"写进 `backend/CLAUDE.md`

### 新增：3 条打真后端的端到端用例，替身夹具之外的契约签字

- **动因**：82 条 e2e 全部靠 `page.route` 假接口，响应该长什么样子是**写在前端测试里**的——前后端各测各的理解，中间没人对账。补一套一条 mock 都没有的用例，请求走完 Vite 代理 → uvicorn → PostgreSQL
- **覆盖面（按选定的 3 条）**：真表单登录换来真 cookie、首页渲染的是真扫描写出来的那一行（含真 FFmpeg 抽的 320×180 封面）；详情页字幕轨 + 流式接口（`/subtitles/1/stream` 回的是 sidecar 真转换出的 WebVTT，`/stream` 带 `Range` 回 `206` 且 `Content-Range` 的总长对得上，还测了贴着片尾的最后 8 字节）；点收藏 → 刷新仍是"已收藏" → `/favorites` 读得到同一行，并向后端核对 `total`
- **`backend/src/e2e_seed.py`（新增）**：账号走 `AuthService.create_user`、影片行走 `ScanService.scan_source`，**不手写 INSERT**——手搓种子行会跟着扫描规则的漂移一起过时。收尾核对 1 部片 / 1 条字幕 / 1 张封面，对不上就在起步时失败，而不是让三条用例各炸一次；封面单列一项是因为 FFmpeg 不在 PATH 上时现象是"图片加载失败的谜"，报错要点名 ffmpeg
- **两道闸门**：库名必须以 `_test` 结尾才允许 TRUNCATE，非 PG 方言一律拒收（这套用例的意义就是验生产那个方言）；整目录删除只允许发生在 `backend/data/e2e` 之下，判据不满足时拒绝发生在任何删除之前。前端 `env.ts` 里另有一道同样的检查，让它在起服务器之前就失败；实测把 `E2E_DATABASE_URL` 指向 `home_sites` 时报 `refusing to run e2e against home_sites`，一台服务器都没起
- **踩到的坑，也是这套接线的头号规矩**：Playwright 的**配置文件会被执行好几遍**（主进程一次 + 每个 worker 一次，本机实测三个进程）。媒体夹具原先就在配置求值期写盘，于是播种之后 `data/e2e` 又被清一次——库里的封面路径指向一个已不存在的文件，表现为 `naturalWidth=0` 反复重试 14 次。媒体准备整个移进 `e2e_seed.py`（和扫描同进程同顺序），配置里只留只读的 `testDatabaseUrl()`
- **顺带被自家新用例抓到一条**：`Path.write_text` 在 Windows 文本模式会把 `\n` 再翻成 `\r\n`，sidecar 成了 `\r\r\n`。改成按字节写，用例比对的是字节
- **接线**：`playwright.real.config.ts` 两条 `webServer` 串成一条 `&&`（`python -m src.e2e_seed && uvicorn`），一次性后端打 127.0.0.1:8099、Vite 打 4174，两边 `reuseExistingServer: false`——**绝不复用开发者手动起着的 :8000**，否则测试数据写进真库。`vite.config.ts` 的代理目标参数化为 `process.env.E2E_API_TARGET ?? 'http://localhost:8000'`（默认不变）；`THUMBNAIL_PATH` 指进一次性目录、`BACKUP_ENABLED=false`（连的是测试方言，不该挂夜间转储）、`E2E_PASSWORD` 只走环境变量不进 argv
- **默认 e2e 配置 `testIgnore` 掉 `e2e/real`**，否则那 82 条会连真库一起跑；`package.json` 加 `test:e2e:real`，`tsconfig.vitest.json` 纳入新配置文件（`typecheck:test` 因此覆盖它）
- **测试**：后端 SQLite **620 passed + 1 skipped**、PG **621 passed**（+8 例 `tests/test_e2e_seed.py`）；前端单测 **279** 与替身 e2e **82** 均未受影响；真后端 e2e **3 passed（15s）**
- **红在先**：四次变异各恰好 1 例红——`Content-Range` 去掉 `/总长` → 流式那条；`FavoriteStatusResponse(is_favorite=False)` → 收藏那条（替身永远测不出这种错，因为两侧是同一份理解）；封面路由改成永不回文件 → 首页那条；播种闸门去掉 `_test` 规则 → 2 例拒绝用例红。逐项 `git checkout` 还原后用 `sha256sum -c` 复核原样
- **没做**：历史、片单、用户管理这些页面仍只有替身覆盖；这套用例不进 CI（要一个能连的 PG 和 PATH 上的 ffmpeg），先当本地合同测试用

### 新增：PostgreSQL 每日自动备份，外加一份不含口令的建库模板

- **动因**：真库切到 PG 之后，片库、账号、收藏、历史只有一个出处——`home_sites` 那个库，盘掉了就全没。此前唯一的备份是搬家当天手工敲的那两次 `pg_dump`
- **触发选了应用内 APScheduler 每日任务**，不是系统的计划任务：扫描本来就挂在同一个 `AsyncIOScheduler` 上，备份跟着后端进程走，部署时不用维护第二套排程。代价说清楚——后端没跑的那一晚就不备份
- **`backend/src/backup.py`（新增）**：`pg_dump -Fc --no-owner` 写完，**立刻用 `pg_restore -l` 把归档读回来**；读不回、或 pg_dump 报成功但文件是 0 字节，就删掉那个文件再抛错。留一份读不回来的 dump 比不备份更危险——出事那天你以为它有
- **口令只进子进程的环境变量**（`PGPASSWORD`），一个字节都不进 argv：argv 在 Windows 上是任何进程都能读到的。`PgTarget.password` 标了 `field(repr=False)`，异常文本只带 pg_dump 自己的 stderr（截 400 字）。用例直接断言命令里没有任何一项含口令
- **轮转只认自己写出来的那个文件名**：`home_sites_\d{8}T\d{6}Z\.dump`。按前缀认亲会误伤——`data/pg-backups/` 里本来就躺着手工快照 `home_sites_post_account_cleanup_20261004_154215.dump`，一周后"轮转"会把某次改动唯一的现场备份删掉。轮转用例就是拿这两个真实手工文件名跑的
- **通知沿用 #85 定的"变了才说"**：备份成功一条都不写，失败写一条 `backup_error`（界面里进红色告警图标）。可见性的代价写在 README 里——悄悄停掉的备份只能靠目录本身或红色通知发现，`GET /api/scheduler/jobs` 能看出作业挂没挂上
- **配置五个**：`BACKUP_ENABLED` / `BACKUP_DIR` / `BACKUP_KEEP_DAYS` / `BACKUP_TIME`（默认 03:30）/ `PG_BINDIR`。`backup_time` 在 `Settings` 的 validator 里校验 `HH:MM`，让它**在启动时炸**而不是凌晨三点炸；`backup_dir` 和 `thumbnail_path` 复用同一条锚定到 `backend/` 的规则。挂载前有方言闸门，SQLite 库整条路不挂
- **`pg_binary` 的存在是因为这台机器**：`pg_dump.exe` 在 `D:/Program Files/PostgreSQL/18/bin`，不在 PATH 上。给了 `PG_BINDIR` 就按 `stem` 和 `stem + ".exe"` 两种拼法找（Windows 上不补 `.exe` 会静默找不到），没给才回落 `shutil.which`，都没有就报一条点名 `PG_BINDIR` 的错
- **建库模板入版本库**：`backend/deploy/pg-provision.example.sql`，口令写 `__REPLACE_ME__` 占位，填好的那份留本地 `data/`。模板里两个库的 `LC_COLLATE` 钉死 `C`，理由写在注释里
- **测试**：后端 590 → SQLite **612 passed + 1 skipped**（45s）、PG **613 passed**（2:58）。新增 23 例：`tests/test_backup.py` 16（口令只在 env、URL→argv 映射、文件名形状、读不回就删文件、0 字节拒绝、pg_dump 失败原话上抛、轮转保住手工快照、`keep_days=0` 不轮转、SQLite 在动手前就被拒、缺二进制点名 PG_BINDIR、时间解析矩阵…）、`tests/test_scheduler_backup.py` 5（重复挂载只留一个作业、失败恰好写一条通知、成功**一条都不写**、通知写不进去也不把异常抛回调度器）、`tests/test_config.py` 2。前端 278 → **279 passed**
- **红在先**：`backup.py` 的三条护栏各做一次变异——口令改进行进 argv、轮转改成按前缀认领、去掉读回校验，每次都恰好 1 例红，改回后 `sha256sum` 复核原样；前端那一例对着 HEAD 的 `NotificationCenter.vue` 跑过是红的
- **真机跑过一次**：另起一次性 uvicorn（127.0.0.1:8015、`BACKUP_TIME=19:56`、备份写到临时目录），到点产出 `home_sites_20261004T115600Z.dump`，51,257 字节，`pg_restore -l` 数出 160 行 TOC / 38 个 TABLE，通知表里 `backup_error` **0** 条、原有通知一行没多。随后杀掉进程、删掉临时产物，:8000 的后端已重启到新代码（`/health` 200、`/api/videos` 仍 401、启动日志无异常）
- **lint / mypy**：`ruff` 对 8 个后端文件在 HEAD 与改动后同为 **7 条既有项**且逐项同源，三个新文件零项；`mypy` 4 → 5，多的那条是 `apscheduler.triggers.cron` 缺 stub 的 `import-untyped`，不是本次代码的类型问题
- **没做**：不带手动触发的端点或 CLI 子命令（超出本单）。想知道"库今天有没有被保"，看 `backup.latest_backup()` 和 `GET /api/scheduler/jobs`

### 修复：删掉记录之后，应用生成的封面永远留在盘上

- **症状**：删影片与删整个视频源的级联只删数据库行，`videos.thumbnail_path` 指的那张 jpg 无人过问，且重扫会按同一条派生规则再落一张，盘上只会越攒越多。真库清点：7 行影片对 23 个封面文件，按文件名核对**至少 6 张**已无任何行引用（`5f5fb38` 改名之前的老命名也计在内，所以 6 是下限）
- **改法**：`delete_videos_cascade` 现在把被删行的 `thumbnail_path` 回给调用方，调用方 `commit()` **之后**再交给 `delete_cover_files()` 落盘。顺序不能反——先删图再提交的话，事务一回滚就留下"行还在、图没了"的影片，列表上是一片占位
- **没照工单原设想给 `MediaStorage` 加 `delete()`**：封面从来只落本地盘（`scan_service.py:256` 的 `local_path` 闸门，对象存储源根本不生成），而三个删除入口的确认框都写着"磁盘上的视频不会被动"。往一个刻意只读的 seam 上开一个能删对象的口子，风险大于它要修的孤儿文件
- **只删应用自己生成的东西**：`delete_cover_files` 只吃 `thumbnail_path`，媒体文件不在其列。图已经不在、或老行里 `./data/thumbnails\...` 这种遗留写法，一律跳过并 warn——行已经提交，为一张残图回 500 会把库弄得更难看
- **顺带核了级联清单与 schema（原 #84）**：模型 21 条外键、`0001` 基线 21 条、真库 `pg_constraint` 21 条且 `confdeltype` 全是 `c`，三边本就一致，工单猜的"清单漏表"不成立。真正的债是**这张清单没人守**，于是把外键挂 `videos.id` 的表收成一处 `VIDEO_CHILD_TABLES`（统一 `Table` 形状，因为关联表 `video_tags` 没有模型、列只能从 `.c` 取），并加用例 `test_the_explicit_cascade_list_is_every_child_of_videos` 拿 `Base.metadata` 现算全集对账——新加一张表忘了登记就会红
- **docstring 与文档不再只讲 SQLite**：原话"SQLite 不执行 `ON DELETE CASCADE`，得手写"换成两边都成立的版本——两个方言朝**相反方向**失效（PG 真会级联，SQLite 静默留孤儿行），只信任何一边都会在另一边失明；显式清单的意义是"由这一处决定删除带走什么"，代价是它必须有用例守着
- **界面文案跟着说实话**：删重复记录与首页"清理丢失记录"两个确认框原先说"磁盘上的文件不会被动"，现在补上"记录生成的封面会一并删掉"，视频本体仍是不动的
- **测试**：后端 583 → SQLite **589 passed + 1 skipped**（44s），PG **590 passed**（新增 6 例：删影片带走封面但绝不碰媒体文件、级联只报路径以便回滚保图、死路径与遗留路径容错、删源带走本片封面且不带别源的封面、HTTP 入口带走封面、清单等于元数据全集）。其中 5 例对着修前的 HEAD 验过是红的（临时把两个 service 文件覆盖成 `git show HEAD:` 的版本再跑：4 failed / 47 passed；随后 `sha256sum -c` 确认原样恢复）。"死路径容错"一例在 HEAD 也过，它是防止新代码在遗留行上炸开的护栏，不算本次回归的证据
- **前端**：单测 **278 passed**（28 文件）、`e2e/sources.spec.ts` + `e2e/home.spec.ts` **24 passed**、`typecheck:test` 干净；两处文案断言同步改过
- **lint / mypy 无新增**：`ruff` 对四个后端文件在 HEAD 与改动后同为 9 条既有项，`mypy` 两个 service 文件同为 21 条既有项
- **真 HTTP 走查用的是一次性库**：另起真 uvicorn 进程 + 临时 SQLite 库 + 临时封面目录（不碰 :8000 上跑着的后端，也不碰真库和真缩略图目录）。`DELETE /api/videos/1` 回 204，那一行的封面当场消失，同一目录里的视频文件原样留着，再 GET 是 404；`DELETE /api/sources/1` 同样 204。第一遍脚本吃了个 403——写操作要带 `X-Requested-With: fetch`（`middleware/auth.py:120`），不是权限问题
- **还差两步**：真库那 6+ 张既有孤儿封面**没动**（删文件不可逆，等一句确认）；:8000 上跑着的后端是无 `--reload` 的旧进程，本次改动要重启才生效

### 修复：转码页把服务端的失败原因全吞了，六个 catch 无一能说出为什么

- **症状是一句兜底文案走天下**：源文件被移走时后端明明回了「源文件已不在原路径」，页面上只显示「转码失败」；格式列表拉不到时界面只是一片空白，连解释都没有（原因只进了 `console.error`）
- **根因是一行早已失效的取法**：`api/client.ts` 的拦截器 `reject` 的是现场 `new Error(detail)`，`error.response` 根本不在上面，所以 `error.response?.data?.detail || '转码失败'` **永远**走到右边那条。2e0d121 规范化了 422 文案，可这些调用点取不到值，规范化了的原文照样被丢掉
- **范围比原标题小**：核对代码后确认轮询失败那处已有 `transcodeStatus.error ?? '转码失败'`（转码本身失败的原因能显示），真正坏掉的是六个 catch 的取法，外加 `fetchFormats`/`fetchStatus` 只往控制台写、不告诉界面试图
- **一个 `errorReason(error)` 而不是六处各写一遍三元**：取 `message`，非 Error 的 reject 回 `null`；`ElMessageBox` 取消时 reject 的正是字符串 `'cancel'`，得先挡掉再谈"失败"
- **轮询失败改成留在卡片上**：状态 1.5 秒问一次，服务端一挂就弹一屏 toast。现在原因写在「转码状态」卡片的新行 `.status-fetch-error`（告警色，和转码本身失败的红色 `.status-error` 区分，因为卡片上留着的是**上一次**的值），toast 只在用户主动进页那一次给；接口恢复应答后这一行自动消失，切视频时也会清掉，不会把上一个 id 的报错挂在新页面上
- **测试**：前端单测 271 → **278 passed**（`tests/views/Transcode.spec.ts` 9 → 16：视频/格式/状态三处各出一条原因、首次失败只弹一次、轮询失败不堆 toast、恢复后清行、开始与取消两处透传服务端原话）。替身按拦截器的真实形状失败（`reject(new Error(msg))`），用例才测得到视图有没有把那句话显示出来
- **两条 e2e 补在浏览器这一层**：`e2e/transcode.spec.ts` 4 → 6 例，走的是真 axios 拦截器 + FastAPI 形状的错误体（404 `视频不存在`、503 `转码服务未就绪`），只有替身回数据。新增的 7 条单测与 2 条 e2e **都对着修前的 HEAD 验过是红的**（临时 `git checkout` 掉 `Transcode.vue` 跑一遍：单测 7 failed / 9 passed，e2e 2 failed / 4 passed，随后原样恢复）
- **`typecheck:test` 与 `build` 干净**，顺带改掉 `frontend/CLAUDE.md` 里 `timeout: 10000` 与代码 `15000` 不符的片段，并把"catch 里只能读 `error.message`"写成显式约定
- **还差一步真人点一次**：真后端上转码页的登录态只有 `admin` 的口令能造，而那个口令不进聊天，所以本轮的验证停在真浏览器 + 真拦截器 + 替身回数据这一层；要打真后端的 e2e 契约缺口另记在待办里

### 修复：定时扫描一轮往通知流里写两条，零新增也照发

- **症状是没人操作也在涨的通知表**：`notifications` 三个小时从 105 行涨到 147 行，149 行里 **145 行的内容是"发现 0 个新视频"**
- **成因是同一条路上两个写入方**：`ScanService.scan_source` 扫完无条件写一条 `scan_complete`（`scan_service.py:321`），`src/scheduler/tasks.py` 的定时任务又对同一份结果补一条 `scheduled_scan`——一个源一轮两条，六个源（一个 1800s + 五个 3600s）约 14 条/小时，且没有任何保留策略，只有 owner 手动"清空"
- **改法一，单一写入方**：调度任务不再自己播"完成"通知，扫描通知只有 `scan_service` 一个出处；任务只保留异常路径的 `scan_error`（失败只有捕获得到）。`scan_all_active` 那条 N+1 顺带没了——原先是每源一条再加一条全库摘要。手动扫描与定时扫描从此说同一句话
- **改法二，变了才说**：`new_videos`、`subtitles_found`、`is_missing` 翻转数三个全为零就不写。扫过没扫过本来就记在 `video_sources.last_scan_at` 上、扫描页也在展示，不需要拿通知当心跳
- **两类变化没被一起静掉**：文件消失与老片旁边新增字幕都不体现在"新片"计数上，只看 `new_videos` 会把它们吞了。文案因此会带上「、N 条字幕」「，N 个文件已找不到」，`data` 里也一并记 `subtitles_found` 与 `missing_changed`
- **诊断顺序按红用例走**：先花 1.4 秒造出反馈回路把成因钉死（连着调两次 `scan_source_task` → 4 行通知），改完转绿；这四例留在 `tests/test_services/test_scan_service.py` 末尾当回归，并确认它们**对着修前的 HEAD 全红**（临时 `git checkout` 那两个源文件跑一遍：4 failed / 1 passed，随后原样恢复）
- **真库也跑过一次**：直接调用应用自己的 `scan_source_task(1)` 打在真 PG 库上，写入 **0** 条通知；当时最新一行 `scheduled_scan` 是旧进程 08:24 那一轮留下的，正好是新旧代码的对照
- **测试**：后端 579 → **583 passed**（+4：一轮只播一次 / 零变化不播 / 文件消失要播 / 新增字幕要播）。SQLite **583 passed + 1 skipped**（2:28），PG **584 passed**（12:45，多的那行是只在 PG 上跑的搬迁用例）
- **真库收尾两步**：先 `pg_dump -Fc` 备份到 `data/pg-backups/home_sites-before-notification-cleanup-20261004-165507.dump`，再删掉历史噪音 159 行（`type IN ('scan_complete','scheduled_scan')` 且文案结尾就是"发现 0 个新视频"；到清点时旧进程又多播了 14 行，所以不是 145）。表里 163 行 → **4 行**，留下的正是"发现 4 个新视频""发现 3 个新视频"两条扫描通知加两条转码通知，`notification_reads` 本来就是 0，没连带删掉任何人的已读记录。删除条件把文案锚在结尾，是为了别误伤新写法里"发现 0 个新视频，1 个文件已找不到"那种确实有话说的行
- **生效前提已处理**：原先跑在 :8000 的后进程没带 `--reload`，用的还是旧代码（它 08:24 那一轮还在播两条），已重启成新进程，`/health` 返回 200。会话在 PG 的 `sessions` 表里，重启不掉登录

### 迁移：真库换到 PostgreSQL，schema 交给 Alembic，数据整体搬迁后切换

- **顺序是 P0 审计 → P1 清方言 → P2 空库跑通 → P3 搬数据 → P4 切换**，一步不能跳：没看清老库的毛病就改 SQL，改完也不知道是谁改坏的；方言没清干净就建表，PG 会在一半数据上拒收
- **`src/db_audit.py`（只读）**：以 `mode=ro` 打开库，拿模型的 `Base.metadata` 和库里实际的 schema 对账，报九类问题（schema 漂移、没落实的外键、孤儿行、值类型不对、VARCHAR 超长、整数超出 PG 的 32 位 `integer`、NOT NULL 里的 NULL、解析不了的日期与 JSON），并给每张表算一个**方言无关**的内容摘要。之所以不是"迁过去看报不报错"：SQLite 的类型亲和、不查长度、不执行外键这三件事，会让一批数据在 SQLite 里存得好好的，到 PG 要么被拒要么被静改写。真库跑出来 0 个阻塞项，报告在 `data/migration-audit-2026-10-03.md`（`data/` 不进版本库），stdout 只打 ASCII——控制台是 cp936
- **P1 清掉的四类 SQLite 专有写法**，每一类都有等价且两边同义的替身：`keep.user_id IS current.user_id` → `(= OR (两边都 IS NULL))`（归属未认领的行是 NULL，用 `=` 会让这些行从分组里掉出去、一条都去重不掉）；`INSERT OR IGNORE` → `WHERE NOT EXISTS`（PG 那边叫 `ON CONFLICT DO NOTHING`，`NOT EXISTS` 两边是同一个意思，规则只留一处）；`PRAGMA table_info` → SQLAlchemy 的 `inspect().get_columns()`，包成 `table_columns` / `session_table_columns`（`run_sync` 给连接和给会话递的东西不一样，直接把会话交给检查器会 `NoInspectionAvailable`）；按日历分桶的 SQL 挪进 Python，两边各自算自己的时区
- **Alembic 成为 schema 的唯一出处**：基线修订 `0001` 建齐模型声明的 18 张表。`init_db()` 从此只**选路线**不建表——空库走 `upgrade_head`；有表却没有 `alembic_version` 行的老库先 `apply_schema_fixes` 补齐成基线的形状再 `stamp_head` 认领，从此和新建库站在同一架版本上；已版本化的只补挂着的修订。`apply_schema_fixes` 仍然是幂等的（年龄不明的库可能已经带了一部分），但不再是每次启动都跑，只在认领基线那一次
- **`alembic.ini` 里 `sqlalchemy.url` 留空**，连接串从 `src.config.settings` 取（`alembic/env.py` 经 `config.attributes` 复用同一条连接）：口令只存在于 `backend/.env`，不进版本库
- **`asyncpg` 是 `[postgres]` 可选依赖**，所以按旧文档 `uv sync` 之后把 `DATABASE_URL` 指到 PG 会连驱动都没有——README 的安装步骤、前置要求、技术栈、环境变量四处一起补上 `--extra postgres`
- **`src/db_transfer.py`（搬家）**：一个事务内按外键拓扑序插入，**同一次事务里**把每张表读回来重算摘要比对，对不上整体回滚，所以不存在"搬了一半"的库。`--dry-run` 一路跑到对账通过再回滚，和正式搬的是同一条代码路，预演过了才算过。`sessions` 整表跳过（旧 token 到新库不该还能用），`alembic_version` 不搬，自增序列推到当前最大值，目标库必须已建表且为空否则直接中止。真库 17 张表 151 行预演通过后正式落库，提交后独立复核一遍跨库摘要：`mismatched: NONE`
- **翻过一次的车：时间戳整体偏 8 小时**。坑在**写入侧不在读取侧**——asyncpg 读 `timestamptz` 还给的是 UTC-aware 值，但送进去一个不带 `tzinfo` 的 `datetime` 时，它按**数据库会话时区**理解（本机 `Asia/Shanghai`，+8）。而 SQLite 读回来永远是 naive，于是从老库捞出的行原样写进 PG 就集体早 8 小时，10 张带时间列的表全部对不上账。修法是 `_read()` 里对每个 `datetime` 过一遍 `as_utc()`。这条由两个用例钉住：naive 值必须被读成 UTC、搬进 PG 目标库后时刻不变
- **审计和搬家现在报的是同一个数**：摘要的行文本从两处各自的拼接里抽成 `db_audit.row_text` 共用，`tests/test_db_transfer.py` 里有用例断言审计算出的摘要等于搬家记录的源摘要。之前两边一个是带列名的、一个是裸值，永远不可能相等，也就永远核对不上
- **测试的方言开关收成一个出处**：`settings.test_database_url`（`backend/.env` 的 `TEST_DATABASE_URL`），`tests/conftest.py` 和搬家的 PG 用例都读它，换库不用再另设环境变量。PG 上每个用例靠 `TRUNCATE ... RESTART IDENTITY CASCADE` 隔离，`RESTART IDENTITY` 保证第一个自增 id 还是 1，用例里写死的 id 不用跟着改；schema 一次会话只建一次，走的就是 `0001` 基线。新增 `tests/support.py` 的 `ensure_source` / `ensure_video`：PG 真的执行外键，子行必须先有父行，不能手工凑 id
- **P4 切换与真机走查**：`.env` 指到 `home_sites`，后端跑在 PG 上，浏览器走查 21 项全过（登录、首页、列表、详情、播放器、收藏、片单、历史、统计、标签、设置、用户、个人、转码页）。时序类页面重点看：历史页把库里 `03:27:46Z` 那一行显示成本地 `2026/10/4 11:27:46`，即时刻存对了、只是按浏览器时区展示；统计页的日桶落在 10月4日，连看天数正确。播放器 `duration=60 / seekable=60 / seek 到 30.0`，说明 Range 流式在这套组合下照常工作
- **回滚预案实测过，不是纸面的**：老 SQLite 文件切换后原样在盘，退回一行配置即可（代价是切换后的新增）。想把增量带走就反向再搬一次——新建一个 SQLite 文件启动一次让基线建表，再 `db_transfer --from <PG> --to <新文件>`。这条今天真跑了一遍：153 行，`MISMATCHED: NONE`，`_reset_sequences` 两种方言都实现了
- **顺手修掉一处文档与代码不符**：`CLAUDE.md` 写着"项目没有 Alembic，加列只能走 `init_db()` 的幂等 SQL"——这句在 P2 之后就是错的，会直接把下一个人引到已经废弃的路上，改成"改表只有一条路：写 Alembic 修订 + 约束同时声明在模型上"。`backend/CLAUDE.md` 里"PG 按会话时区给值"那句同样不准，改成上面那条写入侧的说法
- **一条被本地配置污染的用例**：`tests/test_config.py::test_load_default_settings` 断言的是代码里声明的默认值（SQLite），但 `Settings()` 会读开发者机器上的 `backend/.env`——真库一切到 PG 它就红。改成 `Settings(_env_file=None)`，用例守的东西一点没变，但不再能被任何人的 `.env` 弄红
- **测试**：后端 577 → **580 passed**（+3：naive 值必须按 UTC 读、搬进 PG 目标库时刻不变、审计与搬家报同一个数）。两种方言各跑一遍——PG 上 **580 passed**（6:41），`TEST_DATABASE_URL` 留空的 SQLite 上 **579 passed + 1 skipped**（47s，跳的是那条只可能在 PG 上验的搬迁用例）。前端未动
- **仍然没有的东西，别照着旧文档以为有**：MySQL 不支持（只有 SQLite/PG 两种方言）；没有 Docker Compose；`data/pg-provision.sql` 与 `backend/.env` 不进版本库，建库要超级用户执行，口令不走聊天——本地生成凭据、把 SQL 交给人执行

## 2026-10-02

### 修复：登录时空着点登录，提示是 `[object Object],[object Object]`

- **报上来的是一句乱码，根因在全站共用的那行代码**：`api/client.ts` 的响应拦截器过去写 `error.response?.data?.detail ?? error.message`。字符串型 `detail`（后端手写的中文 400/401/404）走这条路没问题，但 pydantic 的 422 把 `detail` 装成**对象数组**，两个条目拼起来就是那句 `[object Object],[object Object]`。登录接口的 `username`/`password` 都写 `min_length=1`，所以字段留空正好一次踩中两条
- **摊平放在拦截器里，不给每个表单各写一份**：`flattenDetail()` 把数组收成「字段 原因；字段 原因」，按 `type` 查表翻中文（`missing`→不能为空、`string_too_long`→长度最多 N 个字符、`greater_than_equal`→不能小于 N、`int_parsing`→必须是整数、`string_pattern_mismatch`→格式不正确…），表里没有的类型**退回 `msg` 原文**——留着英文也比留乱码有用
- **`min_length=1` 特判成「不能为空」**：后端用它表达"必填"，说「长度至少 1 个字符」是机器话
- **字段名取 `loc` 里除第 0 项之后最后一个字符串**：第 0 项是 `body`/`query`/`path` 这类定位 scope，末尾的数字是列表下标。中途先写过一版"按 scope 名单过滤"的实现，`{loc:['body','path']}` 直接被过滤成空——而 `path` 恰好是视频源的字段名，用例当场把它钉住了：body 里真叫 `path` 的字段必须还能报出 `path`
- **登录页另外加了空值前置校验**：账号或密码为空时本地给一句「请输入账号和密码」并直接返回，不发请求。登录框的两个字段服务端只要求非空，**故意没有在前端校验密码长度**——长度不够属于"这个账号密码不对"，应该由 401 那句话说，前端提前拦反而泄了口令策略
- **不迁移、不改后端**：422 的形状是 FastAPI 的约定，全站 84 个操作共用，改后端响应格式去迁就一个显示问题不划算
- **测试**：前端单测 263 → **271 passed**（28 文件，+8：422 数组摊平、四类 `type` 逐条说人话、空数组退回传输层消息、认不出的条目形状也有话可看，登录页三条空值分支）。Playwright e2e 79 → **80**（新增一例空白表单：断言 `.error` 文案，并挂 `page.on('request')` 断言 `/api/auth/login` 一次都没发出去）
- **验证到什么程度**：**跑过一次真后端**——临时把 `client.defaults.baseURL` 指到 `127.0.0.1:8000`、`adapter` 换成 `http` 打真实 `/auth/login`，`{username:'',password:''}` 经拦截器得到 `username 不能为空；password 不能为空`（脚本与临时产物已删）。**真机页面也走过**：登录页只填账号提交，页面显示「请输入密码」且没有发出登录请求。`npm run build` 与 `typecheck:test` 通过，入口 286.29 kB / gzip 93.04 kB 未变。应用内浏览器的指针操作仍不可用（`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`，视口 0×0），提交这一步是脚本触发 `form.requestSubmit()` 走原生提交流程，等价于点登录按钮
- **一处 flake 记录在案**：全量 e2e 首跑见 `登录成功后回到原本要看的页面` 失败一次，串行（9 通过）与再并发（80 通过）各重跑一次都干净，判为 9 worker 抢冷启动 Vite 变换，未复现，也与本次改动无因果（该用例走的是 401 那条字符串分支）
- **未修的一处同源问题**：`views/Transcode.vue:147` 与 `:168` 读的是 `error.response?.data?.detail`，而拦截器 `reject` 出去的是普通 `Error`、`response` 早就不在上面了——这两处实际永远落到 `|| '转码失败'`，后端那句中文原因一直在被丢掉。它不在本次报告范围内，改法（改读 `e.message`）会连带影响转码页的提示文案，留作单独一条

## 2026-09-22

### 修复：封面被同名视频互相覆盖，以及封面目录跟着启动目录跑

- **两处都是"静默失效"型**，一起修是因为同源：封面文件名过去只由原片 basename 推出来。`a/01.mp4` 与 `b/01.mp4` 落在同一个视频源下时写到同一个 `1/01.jpg`，后扫的那张把前一张盖掉，两行都"有封面"、日志什么都没写。第二类同理，`THUMBNAIL_PATH=./data/thumbnails` 是相对值，而库里存的是**算出来的完整字符串**，读取端 `os.path.isfile` 按进程工作目录解析它——从仓库根目录启动服务，全库封面就变成占位图
- **封面名改成 `{原文件名}-{sha256(locator)[:12]}.jpg`**（`scan_service._thumbnail_target`）：保留可读的文件名前缀便于排查，尾部摘要用整个 locator 算，locator 本来就是库里的唯一键，所以"同名不同目录"必然分出两个文件
- **相对路径在配置层就锚定到 `backend/`**（`config.py` 新增 `BACKEND_ROOT` 与一个 `field_validator`），而不是在每个使用点各自 `abspath`。绝对值与空值原样放过——测试把封面目录指到 tmp，空值表示关掉封面生成。**没有取消"从 `backend/` 启动"这个约定**：`DATABASE_URL` 和 `.env` 本身仍然是 cwd 相对的，那两处才是启动目录真正的依赖
- **不迁移、不回填**：老行的 `thumbnail_path` 指向旧文件，文件还在、照常能读；但**过去已经被盖掉过的那一张不会自愈**——重扫在 `known → continue` 那一步就跳过了，要恢复只能删掉该行重扫。家里库里有没有这种行没人知道，因为盖掉的时候什么都没留
- **顺带修掉测试自身的污染**：`tests/test_config.py` 用 `os.environ` 写 `API_PORT=invalid` 且不清理，同进程里后面任何一个 `Settings()` 都会带着这个值炸掉。新加的两条配置用例正好排在它后面才暴露出来，改用 `monkeypatch.setenv` 后整套用例顺序无关
- **实测而非只跑测试**：从仓库根目录 import 配置，`thumbnail_path` 得到 `D:\...\backend\data\thumbnails`（绝对）；`/library/a/01.mp4` 与 `/library/b/01.mp4` 分别得到 `01-7623c3398c9a.jpg` 与 `01-ecd7af4f3df0.jpg`
- **测试**：后端 539 → **542 passed**（55.8s，+3：同名两子目录各留一张封面、相对值锚定、绝对值与空值放过）。前端未动
- **未修的三处已知问题**：设置页的「缩略图宽度 / 高度」存进表但 `generate_thumbnail` 里 `scale=320:-1` 是硬编码，是摆设（已写进 `backend/CLAUDE.md` 免得下一个人去改表单）；`VIDEO_STORAGE_PATH` 全仓除定义外无人读取，是死配置；扫描里的 ffprobe 是事件循环内同步 `subprocess.run`，本机毫秒级看不出来，一旦喂网络地址就会卡住整个 API——这是对象存储取元数据的前置条件

## 2026-09-21

### 重构 + 新增功能：取文件收成一道接缝（`src/storage/`），对象存储视频源落地

- **先改文档，再写代码**：README 的"支持 MinIO"、CLAUDE.md 技术栈的"Docker Compose 部署"都是写了没做（`type` 只有一个枚举值，仓库里没有 Dockerfile）。上一轮核对代码后把三处文档改成现状，这一轮才把对象存储真的接出来——顺序不能反过来，文档一旦跑到实现前面，后面所有人都按它估工
- **接缝只有一句**：上层拿到的永远是 `videos.filepath` 这个 locator 字符串，列举整源用 `storage_for_source(source.type)`，读单个文件用 `storage_for_locator(video.filepath)`。**分成两个函数是刻意的**：地址本身自描述（`D:\…` / `\\nas\…` / `s3://bucket/key`），所以播放每换一个 Range 都不用回库 join `video_sources` 去问"这是哪个源"
- **本地实现就是原来那份 `os.walk`**：`LocalMediaStorage.list_videos()` 直接复用 `scan_directory()` 而没有重写成 pathlib。原因是 `Video.filepath` 靠**字符串全等**做去重键，分隔符差一个就会让整库同时变成"全部新增"和"全部丢失"。这条不变量由 `test_local_storage.py` 钉住：同一棵目录树分别按原样、带尾分隔符、正斜杠三种写法走一遍，新旧两份列表逐字节比对
- **NAS 与本地共用一份实现**：SMB/NFS 挂载之后就是本地路径，这里没有任何挂载协议。真要说清"我是挂载盘"的能力得另放一层，这期不做
- **能力用 `Capabilities(streaming, local_path, sidecar_subtitles)` 问，不嗅探 `s3://`**：真正承重的只有 `local_path` 那一位——FFmpeg 得能 `open()` 一个文件并在里面 seek，对象存储给不了。于是缩略图（扫描时直接跳过）、转码、内嵌字幕提取、外挂字幕登记四项一起关，路由回中文 400 而不是 500。前端不需要为此加分支：拦截器把那句话原样弹出来
- **"够不着"和"空"是两回事**：只有 `reachable()` 为真才允许把记录标成 `is_missing`。挂载盘掉线、`S3_ACCESS_KEY_ID` 填错都走 False，此时列表当空处理但一行都不判定——否则改错一个字符就把整库灰掉。同一条也管凭证缺失时的 `size()`：返回 `None` 让播放回落到占位响应，而不是每部桶里的影片都抛 500
- **首尾各 1MB 的摘要只定义一处**（`utils/file_fingerprint.py` 的 `hash_edges`），两份实现都调它。故意不用 ETag：那是整个对象的 MD5，分片上传时又是另一套算法，两种摘要混进同一个比较里，本地块与桶里副本就永远匹配不上——而且匹配不上时不会报错，只会安静地"没有重复"
- **顺手改掉一个进程级缓存的坑**：S3 client 一开始按"进程里建一次"缓存，用例立刻表现为拿旧密钥签出的 403。现在按 `(endpoint, region, access_key, secret, addressing_style)` 这个元组缓存，用户改完 `backend/.env` 才会真的换客户端
- **层的方向是被两次的循环导入教出来的**：`src/utils/*` 不能 import `src.storage`——`storage/__init__.py` 会加载两份实现，实现又依赖 utils，一 import 就绕成环、服务起不来。所以"什么算视频文件"留在 `file_scanner.py`、摘要算法留在 `file_fingerprint.py`，由存储层反向引用
- **依赖是可选的**：`boto3` 在 `.[s3]` extra 里、`import` 延迟到真要建客户端时，没装也能起服务，读到对象存储才提示「请安装 .[s3]」。测试用 `moto`（进 `.[dev]`）在内存里演一个桶，不碰网络；两个包都没装时相关用例 `importorskip` 跳过而不是整文件报错。**顺带发现 README 少写了一步**：`uv sync` 连 `dev` extra 都不装（实测会把 pytest 一起删掉），跑测试要 `uv sync --extra dev --extra s3`
- **类型与路径不匹配现在当场 400**：`minio` 不以 `s3://` 开头、`local`/`nas` 却填了 `s3://`，过去都会安静地扫出一个空列表。更新时按**合并后的值**判，不是只看请求里带的那一半字段——只改 path 也得对得上库里那行的 type
- **测试**：后端 495 → **539 passed**（+44。`tests/test_storage/` 新增 35 例：本地实现 9 / 分发与能力真值表 12 / moto 桶 10 / 扫描走接缝 4，其中包含"桶里的副本与同一份字节在本地算出的摘要一致"这条跨提供方断言）+ `test_api/test_storage_gates.py` 6 例（四项能力各一条 400、凭证缺失时播放不 500、重复检测读不到摘要时返回空而非崩）+ `test_api/test_sources.py` 3 例。前端单测 264 不变，Playwright e2e 78 → **79**（新增一例：类型切到 `S3 / MinIO` 时占位符换成 `s3://` 写法、能力说明出现）；`npm run build` 入口 286.29 kB / gzip 93.05 kB 未变
- **端点没有增加**：仍是 65 条路径 / 84 个操作、18 张表。这一轮唯一的新写面是 `POST/PUT /api/sources` 上多出来的格式校验，对象存储侧只读，没有任何上传或删除对象的路径
- **验证到什么程度**：S3 那份实现验的是"客户端接线正确"（moto 在进程内拦 botocore），**不等于**真 MinIO 端点行为一致——虚拟主机寻址与 path 寻址、自建服务的 `S3_ENDPOINT_URL` 都要人肉连一次才算数。本地/NAS 那一路是逐字节行为保持，539 例里原本就有的扫描与 Range 播放用例（`test_stream.py` 10 例，含开放尾、闭区间、后缀、越界钳制与非法区间）一行没改仍通过
- **已知边界**：桶里的影片没有缩略图（前端显示无封面占位）、不能转码、两种字幕都不登记，要这些只能把片放回本地或挂载盘——对象存储上做这些得先落临时文件再喂 FFmpeg，收益抵不过复杂度；扫描入库时这类行的 `duration`/分辨率为 `None`（探针同样要本地文件）；没有批量导入、没有按人的源可见性；`S3_ADDRESSING_STYLE` 默认 `auto`，自建 MinIO 用域名寻址失败时要手改成 `path`

### 新增功能：我的设备（M4 收尾），一个账号看得见、也退得掉自己挂在哪些浏览器上

- **这一期收的是设计文档 M4 那一行**：`sessions.user_agent` 从 M1 就存着，但一直只在 `/users` 里以"在线设备数"一个数字露面。现在 `/profile` 最后一张卡把它摊开——这个账号当前还登录着哪几台浏览器、每台最近什么时候活动、什么时候过期，并且可以只退掉其中一台，不必把整个账号踢下线
- **行的地址就是那枚摘要**：`sessions` 的主键是 `token_hash`，没有自增 id，所以 `DELETE /api/auth/sessions/{token_hash}` 直接拿 sha256 的十六进制输出当地址用（它是摘要、不是 Cookie 值，也推不回原 token）。合法形状 `[0-9a-f]{64}` 收在 `TOKEN_HASH_HEX` 一处，被路由的 `Path(pattern=...)` 和中间件白名单那条正则共用——形状不对在路由层就是 422，不会先撞上角色判定把"参数不合法"和"角色被拒"混成一个 403
- **撤销按 `(user_id, token_hash)` 联合定位**：少了 `user_id` 这一半，一枚猜中的摘要就能把陌生人的浏览器退掉；现在别人的摘要只会得到 404。列表同样只覆盖本人名下的行，响应回给浏览器的是摘要，用例断言过整个响应体里不含 Cookie 原值
- **这是 M3 之后第一次给成员开写口**：`MEMBER_WRITE_PATHS` 14 → 15 条，`test_roles.py` 的 `MEMBER_WRITABLE_OPERATIONS` 与 e2e 替身的 `MEMBER_WRITE` 同步跟上（三张清单一起改是 M3 定下的规矩）。这一条不需要额外的角色判断——它动的会话行本来就按人 scoped，界面上成员也只看得到自己的
- **不做分页，也不给"退出全部"**：一个家的浏览器就几台，行会随过期自然消失。"全部退出"已经有两处各管一档：顶栏「退出登录」只管这台，`/users` 的踢下线管这个账号所有台——再加一个同名按钮只会让人误判它的作用范围
- **User-Agent 只决定这一行显示什么**：`deviceLabel()` 把它翻成 `Chrome · Windows`、`Safari · iOS` 这类文案，认不出来就原样截 40 字符留个能核对的痕迹（走查时 `curl/8.19.0` 就是这么显示的）。任何判断都不依据它——那句话是客户端自己写的，改起来不需要成本
- **端点变化**：新增 2 个操作，全库 63 条路径 / 82 个操作 → **65 条路径 / 84 个操作**，表数不变（18 张），**没有新增任何能碰磁盘或提权的端点**，读写的还是 `sessions` 那一张
- **顺手修掉一处只有真机才会看见的脏**：`NotificationCenter` 在 `onMounted` 里无条件打 `/api/notifications` 与 `/unread`，而顶栏会比会话探测先挂上来，于是每次进登录页控制台都留一对 401。改成 `watch(isAuthenticated, ..., { immediate: true })`——不能退回"在 `onMounted` 里判一次登录态"，首帧那次挂载恰恰就是还没有会话的那一帧，而登录完成后组件也不会重新挂载。这是"中间件会拒绝的操作，界面上就不该留入口"第一次管到顶栏自己身上
- **测试**：后端 484 → 495 passed（`test_api/test_auth.py` 15 → 22 例，新增 7 例：列表覆盖范围与"当前这台"标记、UA 原样记录、只覆盖登录账号本人、退一台不动另一台、成员管得动自己名下、别人的摘要 404、不是摘要的形状 422；两张扫面表各自随端点自动涨——匿名 401 从 87 → 89 例，成员 403 从 51 → 53 例，都不用手写）。前端单测 257 → 264 passed（28 文件；`Profile` 登录设备 6 例 + `NotificationCenter` 无会话不请求 1 例）、Playwright e2e 75 → 78 passed（`login.spec.ts` +2、`roles.spec.ts` +1）；`npm run build` 通过，入口 286.29 kB / gzip 93.05 kB；`npm run typecheck:test` 干净
- **e2e 替身这次要改的不止清单**：`fixtures.ts` 的 `/auth/sessions` 分支做成**有状态**——`revokedDevices` 记下退过哪些摘要，重复退返回 404，改密码会顺手把另一台标成已退。这样"点退出 → 行数少一"在浏览器测里是真发生的，而不是接口永远回 200。顺带把 `.profile-card` "第几张"这种定位换成 `card-account` / `card-theme` / `card-password` / `card-devices` 四个语义 class：加一张卡就会错位，M3 的改密码用例已经踩过一次
- **验证**：拿**真实库的副本**（`backend/data/walkthrough_m4.db`）起后端 + vite，管理员与成员两个走查账号，再用 curl 以 iPhone Safari / Android Chrome / Edge 三种 User-Agent 造出额外会话（其中一副带 `remember`）。真实浏览器逐账号走查：管理员那张卡列出 9 行，`Safari · iOS` 一行的有效期是 30 天后、其余是 12 小时（`记住我` 与滑动续期在界面上对得上），当前这台是 `当前设备` 标签 + 「顶栏的『退出登录』管这一台」而没有按钮，`curl/8.19.0` 原样显示；点「退出」后该行当场消失并提示"该设备已退出，下次要用密码重新登录"，服务端那行也确实没了（重读少一条，再退同一摘要 404）；换成成员账号登录，同一张卡只剩他自己名下三台，顶栏仍然只有 5 个入口。全程 console 无报错
- **公网部署注意事项**（新增 README「公网部署注意事项」一节 + CLAUDE.md「放到公网之前」）：`AUTH_COOKIE_SECURE=true` 只在 https 下有意义，而 `sid` 就是唯一凭据、还会随使用滑动续期；后端不解析任何 `X-Forwarded-*`，登录限流按 `request.client.host` + 账号计数，反代之后全家所有人的来源 IP 压成反代那一台——一个人连错 5 次会把所有人锁在门外 10 分钟，要么让 uvicorn 只信任本机反代并取 XFF（`--proxy-headers --forwarded-allow-ips=127.0.0.1`），要么调 `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_MINUTES`；`CORS_ORIGINS` 精确到实际域名（带 Cookie 不能 `*`）；`data/videos.db` 现在装着口令哈希与仍然有效的会话，备份它等同于备份全家的凭据
- **已知边界**：设备只有"浏览器"这一档粒度，同一台浏览器开两个 profile 会显示成两行一模一样的 `Chrome · Windows`（要区分只能给每行加一个短摘要前缀，这一期没做）；`user_agent` 不解析机型，平板与手机都归 `iOS`/`Android`；不做"新设备登录时通知我"，那要先让通知按人收敛（M2 就记下的那条待定设计）；角色仍然只有 owner / member 两档，没有按视频源的可见性。至此设计文档 §分期实施 的四期全部落地

### 新增功能：角色网关与账号管理（M3），成员看不见也点不动管理面

- **这一轮补的是 M2 留的口子**：M2 之后数据已经按人隔离，但"谁能改库"还是全员平等——任何登录账号都能删影片、改视频源、扫盘。M3 把角色落进请求路径，并给出两个界面：owner 的 `/users`（建号、改角色、停用、重置密码、踢下线）和每个人的 `/profile`（账号信息、主题、改密码）
- **判定仍然放在中间件，两张表**：`AuthMiddleware` 里新增 `MEMBER_WRITE_PATHS`（14 条正则，成员唯一能写的路径）与 `OWNER_ONLY_READ_PATHS`（4 条）。方向和 M1 的默认拒绝一致——**成员能写什么是一份白名单，不是"哪些禁他"**，非 GET 且不在表内一律 403 `需要管理员权限`。用正则而不是 `{id}` 字面量比对，是因为中间件不参与路由解析，拿到的是原始路径
- **少数路由再挂 `require_owner`**：需要"操作者是谁"的判断（例如不能停用自己、不能改自己的角色）没法用路径表达，就在依赖里拿 `User` 再判
- **管理面的读也收两处**：`/api/users*` 与 `/api/settings*` 连 GET 都限 owner——账号清单、在线设备数、局域网路径对成员没有用处。这是"读接口只看登录"这条总原则的**有意例外**，写进了设计文档的偏差说明，别照抄
- **三条护栏**：不能停用或降级自己（400 `不能停用自己的账号`），必须留下至少一个可用 owner（400 `至少要保留一个可用的管理员…`），把别人降级或停用时顺手撤销其会话。另外没有"删除账号"这一档，只有停用——历史、收藏、片单都是真数据，删号等于连带清掉一个人看过的东西
- **`settings` 与 `user_preferences` 拆开了**：主题是账号的属性，系统配置（扫描目录、转码格式、缩略图尺寸）才是全屋共用。新增 `user_preferences(user_id, prefs JSON)` 与 `GET/PUT /api/preferences`。**JSON 列的老坑**：原地改 `prefs` 这个 dict，SQLAlchemy 察觉不到变化，必须整体赋新值并 `flag_modified`，否则接口 200、库里没动
- **迁移两条语句，顺序即语义**：`INHERIT_THEME_IN_PREFERENCES` 先把共享 `settings.theme` 的老值复制成"每个还没有偏好行的账号"的一份，`DROP_SHARED_THEME_SETTING` 再删那个共享键——反过来执行就等于把所有人的主题都抹回默认。仍然走 `apply_schema_fixes` 的启动幂等重放，**首次执行前请先复制一份 `backend/data/videos.db`**
- **端点变化**：`/api/users` 5 条路径 6 个操作 + `/api/preferences` 2 个操作，全是账号表与 `sessions` 上的读写，**没有新增任何能碰磁盘或提权的端点**；`/api/settings*` 收窄为纯系统配置。全库现为 63 条路径 / 82 个操作、18 张表
- **前端角色面三层**：路由表上 `meta: { roles: ['owner'] }` + 守卫里未登录先跳登录、角色不够回首页（不是进去吃一串 403）；顶栏导航项与用户菜单按 `isOwner` 显隐；**同一判断一路带到按钮**——首页横幅的「清理丢失记录」、影片详情的「转码 / 编辑 / 删除」与标签行加号、通知弹层的「清空」与逐条删除，这些走的都是成员禁写接口，一律 `v-if="isOwner"`，`/videos/:id/transcode` 整页也标成 owner。判据只有一条：**中间件会拒绝的操作，界面上就不该留入口**
- **一个只有真机才能发现的坑**：主题与角色用的 `el-radio-group` / `el-radio` 忘了加进 `src/main.ts` 的按需注册列表，浏览器里整块不渲染（Vue 只警告一次），而单测全绿——`tests/setup.ts` 装的是全量 Element Plus 插件。已在 `frontend/CLAUDE.md` 记成硬约束：新增 `el-*` 必须同步注册列表
- **测试**：后端 396 → 484 passed。M3 新增 4 个文件 78 例——`tests/test_middleware/test_roles.py` 51 例（**独立列一份"成员可写"清单，和中间件的表一一对照**，放行一个新写接口必须是显式决定；其余把 openapi 里每个非白名单写端点用成员身份打一遍）、`test_api/test_users.py` 11、`test_api/test_preferences.py` 9、`test_services/test_user_admin.py` 7（护栏与降级踢会话）。M1 的匿名扫面从 71 例涨到 87 例，随端点增减自动跟随 openapi，无需手写。前端单测 219 → 257 passed（28 文件；`VideoDetail` 角色门 2 例、`Home` 成员无清理入口 1 例、`NotificationCenter` 成员无删除入口 1 例、路由守卫补 `/videos/:id/transcode`）；Playwright e2e 61 → 75 passed（`e2e/roles.spec.ts` 14 例）；`npm run build` 通过，入口 286.25 kB / gzip 93.04 kB；`npm run typecheck:test` 顺带修掉三处此前就存在的类型报错（axios 头返回类型、两个未使用的导入）
- **e2e 替身跟着中间件走**：`e2e/fixtures.ts` 里的成员禁写不再手写路径清单，改为一条 `MEMBER_WRITE` 正则一比一抄 `MEMBER_WRITE_PATHS`——名单外的写请求一律 403。后端放行或新收一条写接口时，两张表和 `roles.spec.ts` 的期望要一起改，否则浏览器测的是替身而不是后端
- **验证**：拿**真实库的副本**（`backend/data/walkthrough_m3.db`，M2 之前的状态）起后端 + vite，库里四个账号：两个 owner（`walkthrough`、`m3owner`）、两个成员（`m3member`、界面里新建的 `m3ui`）。老库迁移后 1 条收藏 + 3 条历史归第一个 owner，没有丢行。真实浏览器逐账号走查：owner 顶栏 8 项、成员 5 项（`首页/播放历史/观影统计/收藏/片单`）；owner 用户菜单三项（个人设置 / 用户管理 / 退出登录）、成员只有两项；成员手敲 `/users`、`/settings`、`/videos/1/transcode` 都被带回 `/`；主题按人——`m3owner` 存深色后 `data-theme=dark` 且库里是 `user_preferences = {"theme": "dark"}` 而 `settings` 仍然空，**同一台浏览器**退出后换 `m3member` 登录回到 `data-theme=light`（他一份都没存过）；同一份 50 条广播通知，成员面板里只有「全部已读」一个按钮、`.notification-remove` 0 个，管理员同一面板是「全部已读 / 清空」外加 50 个逐条 ✕；成员首页横幅只剩「查看」，影片详情页只剩 `播放 / 收藏 / 片单` 三个按钮且标签行没有加号，管理员同页 6 个按钮 + 1 个加号；`/users` 表格里本人那一行的开关与"踢下线"是禁用的，把最后一个 owner 降级会报错并弹回原样。全程无 console 报错
- **已知边界**：角色只有 owner / member 两档，没有按视频源的可见性（`source_acl` 另说）；`notifications` 仍是全家广播，"删除通知 / 清空"是家庭级操作，这一轮按 M2 记下的那条待定设计走角色网关收敛（只归 owner 看得见），要按人收敛仍需加 `user_id`；播放器偏好（倍速、音量、字幕字号与延迟）仍按浏览器记，不跟人；"我的设备"会话列表没有做，`/api/users/{id}/sessions` 目前只会报设备数

## 2026-09-20

### 新增功能：数据按人隔离（M2 数据归属），收藏/历史/片单/统计跟着账号走

- **为什么先做这一层**：M1 之后只有"登录 / 未登录"两档，但库里所有行都是全家共用一份——A 拖进度会把 B 的续播位置覆盖掉。这一轮不动界面，只把"这行数据是谁的"落进 schema 与 service 层
- **5 张表加归属列 + 2 张已读表**：`favorites.user_id`、`play_history.user_id`、`watch_events.user_id`、`watchlists.user_id`（owner）、`new_videos` 与 `notifications` 不改结构，改为新增 `new_video_reads(video_id, user_id)` 与 `notification_reads(notification_id, user_id)` 两张纯关系表——**已读是"每个人一条记录"，不是原表上的一个布尔字段**，否则第一个人点掉角标全家就都"看过"了
- **约束跟着换**：`play_history.video_id` 原来的单列唯一换成 `(video_id, user_id)` 联合唯一，`favorites` 同理，`watchlists.name` 的全局唯一换成 `(user_id, name)` 联合唯一（所以两口子可以各建一份"今晚看这些"）。这些约束同时写在模型上，因为测试库是 `create_all` 建出来的，只加迁移 SQL 会在测试里形同不存在
- **SQLite 的两个事实决定了迁移形状**：`ADD COLUMN` 不能带非空默认值，所以老库加出来的 `user_id` 是 nullable，而模型里声明 `nullable=False`——新库严格、老库回填后重新建约束；唯一索引对 `NULL` 视为互不相等，所以老库残留的重复行必须先用 `DEDUPE_*` 语句按 `keep.user_id IS current.user_id` 去过一遍，再 `DROP` 旧索引、建新索引，否则建索引直接失败
- **迁移没有 Alembic，靠幂等重放**：全部收进 `database/session.py` 的 `apply_schema_fixes(conn)`（`create_all` → `PRAGMA table_info` 补列 → 去重 → 换索引 → 建归属索引），启动即执行，重复启动无副作用。**首次执行前请先复制一份 `backend/data/videos.db`**
- **老数据归第一个 owner**：`AuthService.claim_legacy_rows(user_id)` 把所有 `user_id IS NULL` 的行 UPDATE 给当前账号，`_inherit_read_state` 再把老 `new_videos.viewed` / `notifications.read` 布尔位翻译成 `_reads` 行（用 `_column_exists` 判断老库有没有这一列）。**只在第一次 `create-user --role owner` 时触发**，第二个 owner 不会把别人的数据抢走
- **service 层一律 `user_id` 打头**：`favorite_service` / `history_service` / `watchlist_service` / `notification_service` 的每个方法第一个参数都是 `user_id`，查不到即 `ValueError`（API 转 404）。片单的越权收口只有一处：`WatchlistService.get_watchlist` 带 owner 条件，其余读改写都从它拿对象，所以"按裸 id 命中别人的行"在结构上不可能
- **每档视角的相关子查询**：`_played(user_id)`、`_finished(user_id)`、`_unread_new_video(user_id)` 三个 `EXISTS` 助手让"看过了 / 已看完 / 有未读新片角标"随请求者变化。所以 `GET /api/videos/1` 对 A 返回 `progress=90`、对 B 返回 `progress=10`；搜索操作符 `已看完` 与 `没看过` 也是按人算的；系列进度"下一集"两个人指向不同集数
- **越权清单（设计文档 §越权面）逐条修掉**：删除历史记录、标记通知已读、片单读改写与加删条目、`mark_video_viewed` 全部改成按 `(id, user_id)` 定位。**一个例外**：`notifications` 是全家广播、没有 owner 列，所以"删除通知 / 清空通知"仍然是全屋共享的操作——删了就大家都没了。这不是漏洞而是待定设计（原话写进 `backend/CLAUDE.md` 与用例 docstring），要按人收敛应该加 `user_id` 或走角色网关，归到 M3
- **测试**：后端 372 → 396 passed。新增 `tests/test_services/test_isolation.py` 13 例（收藏互不可见且可同名共存、按 id 删别人的历史行报错、统计 600 vs 60、片单六条路全 raise、进度按调用者、看片状态操作符、系列 next、角标标记、通知已读）、`tests/test_api/test_isolation.py` 9 例（同一份越权清单走 HTTP + 两个已登录 client）、`tests/test_database.py` 重写为 4 例迁移用例（补列、换索引、去重、重放幂等）；fixtures 补 `make_user` / `user_id` / `make_signed_in_client`。前端 219 passed、Playwright e2e 61 passed、`npm run build` 通过（本轮无界面改动）
- **验证**：拿**真实库的副本**（`backend/data/walkthrough_m2.db`）启动，迁移后逐表核对——列加上了、`play_history` 的单列唯一索引换成了联合唯一、1 条收藏 + 3 条历史被第一个 owner 完整继承、**没有一行被丢掉**；`_reads` 是空的属预期（老库里那两个布尔位当时都没置过）。再用两个账号走真实 HTTP：`A history total: 3 / B history total: 0`、`B deletes A history row -> 404`、同名片单两边各建一份 `1 2`、未读角标 `A 90 / B 91`。最后在真实浏览器里登录 xiaofeng（2 条收藏、角标 90、1 份片单）→ 退出 → 登录 guest（"暂无收藏视频"、只看得到自己那条历史、只剩自己的片单、角标 91），无 console 报错
- **已知边界**：`role` 仍未参与鉴权，通知删除是家庭级操作；视频库本身对全体登录用户可见（要按源限制得另做 `source_acl`）；M1 之前的观看时长仍无法回推

### 新增功能：登录与访问控制（多用户认证骨架）

- **为什么是 Cookie 会话而不是 JWT**：播放器、封面、字幕走的是 `<video>` / `<img>` / `<track>` 的原生请求，浏览器不会替它们带 `Authorization` 头；要签名 token 就得把身份塞进 URL，缩略图地址随之变成一份可以转发给别人长期使用的凭证。改为服务端会话，新增 `users` 与 `sessions` 两张表，Cookie 名 `sid`，`HttpOnly` + `SameSite=Lax` + `Path=/`
- **库里只存 `sha256(token)`**：`secrets.token_urlsafe(32)` 发给浏览器，落库的是它的摘要。所以"退出登录"和"踢下线"是真会生效的——删掉 `sessions` 行，那枚 Cookie 当场失效
- **默认拒绝，而不是逐路由挂 `Depends`**：`AuthMiddleware` 对所有 `/api/*` 回 401，只放行 `/api/auth/login` 与 `/api/auth/status`。漏挂一个端点等于整套方案失效，而"忘记放行"会立刻挡在手上，是能被发现的 bug。中间件在 CORS 之后注册，预检 OPTIONS 不会被 401 拦掉
- **CSRF 两道**：`SameSite=Lax` 之外，非 GET 还要求 `X-Requested-With: fetch`（跨站表单发不出这个头）。403 分支排在 401 之后，否则未登录会被误报成 CSRF 失败
- **口令**：直接用 bcrypt（cost 12），删掉 `python-jose` 与 `passlib`——后者自 2020 年起停更、与 bcrypt>=4 有兼容告警。bcrypt 只看前 72 字节，超过就在入口报错而不是悄悄截断。账号不存在与密码错误给同一句"账号或密码错误"，不把账号枚举出去
- **防爆破**：进程内按 `(客户端 IP, 账号)` 计数，5 次失败锁 10 分钟并回 429 + `Retry-After`，登录成功即清零。重启清零是可接受的：家用局域网要拦的是脚本，不是专业攻击者
- **滑动续期**：过期时间随请求向前推，窗口取会话自身寿命（`expires_at - created_at`），因此"记住我"不需要单独存标记；写库节流到每 300 秒一次。**SQLite 坑**：`DateTime(timezone=True)` 读回来是 naive 的，比较前必须补 `tzinfo=utc`；测试里别用 `expire_all()` + `session.get()` 重读，会 `MissingGreenlet`，要 `await db_session.refresh(row)`
- **端点**：新增 5 个 `/api/auth/*` —— `POST login`（签发会话并写 Cookie）、`GET status`（公开，登录页用它判断已登录与否、是否需要建号）、`GET me`、`POST logout`、`POST password`（改密后保住当前会话、踢掉其他设备）。**没有注册接口**，账号只能由命令行创建
- **账号管理命令行**：`uv run python -m src.cli` 下的 `create-user`（密码交互输入两次，可 `--role owner`）、`list-users`、`set-role`、`revoke-sessions`
- **前端**：`api/auth.ts` + `useAuth` composable（模块级 ref 共享状态，不引 Pinia）；`client.ts` 默认带 `X-Requested-With: fetch`，拦截到 401（`/auth/*` 自身除外）就清掉本地身份并跳登录，`?redirect=` 记录原地址——只跟站内相对路径，`//host` 会被浏览器按协议相对地址解析。登录页是裸页：`App.vue` 按 `route.meta.public` 决定套不套 MainLayout，没有账号时提示里直接给出建号命令。`beforeEach` 守卫先 `load()` 再放行；顶栏右侧加用户胶囊（账号 + 角色 + 退出登录）
- **Playwright 严格模式**：有了用户菜单之后页面上存在两个 `.el-popover`，通知相关用例全部命中两处。给两个弹层分别加 `popper-class="notification-popper"` / `"user-popper"`，选择器随之收紧
- **测试**：后端 590 → 684 passed（`test_api/test_auth.py` 15 例；`test_middleware/test_auth.py` 79 例，其中 71 例把 openapi 里每个非白名单 `/api` 端点用匿名请求逐个打一遍——本仓库这版 FastAPI 的 `app.routes` 里子路由是 `_IncludedRouter`、没有 `.path`，所以扫面取 `app.openapi()["paths"]`）；前端单测 199 → 219 passed（`useAuth` 6、登录页 5、auth api 2、401 拦截 2、用户菜单 2、路由守卫 7）；Playwright e2e 55 → 61 passed；`npm run build` 通过（入口 280.61 kB / gzip 91.73 kB）。顺带把 7 个 api 测试文件里各复制一份的 `client` fixture 收进 `tests/conftest.py`：`anon_client`（匿名）与 `client`（已登录），服务替身经 `extra_overrides` 注入
- **验证**：真实后端 + 真实库 + vite 走全链路。CLI 建号后匿名访问首页被跳去 `/login?redirect=/`；登录后首页 8 张卡片、7 张缩略图全部 `naturalWidth > 0`（原生资源请求确实带上了会话 Cookie），`document.cookie` 读不到 `sid`（HttpOnly）；刷新身份仍在，弹层显示 `walkthrough 管理员`；退出后回到登录页且顶栏消失，此时 `GET /api/videos` 与 `/api/auth/me` 都是 401；错密码显示后端原话"账号或密码错误"，密码框被清空
- **已知边界**：当前只有"登录 / 未登录"两档，`role` 已入库但还没参与鉴权（角色网关与用户管理页是下一步）；数据仍是全家共享，历史、收藏、片单暂时不分人；局域网 http 访问时 `AUTH_COOKIE_SECURE=false`，套上 https 才需要打开

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
