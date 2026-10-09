# 更新日志

## 2026-10-09
### 备份目录里那份转储在"挑最新"之前就消失时，启动补跑不再当场死掉（#181）

- **这一单修的是 #174 量出来那个洞**：`is_stale` 的 docstring 明写"stat 不出的条目按陈旧处理而不是抛异常，因为它跑在启动那一段，一个悬空条目不该把应用带下去"，可那个 `try` 从前只包住**后面那一次** stat。而 `latest_backup` 挑最新那一份用的是 `max(key=os.path.getmtime)`——同一个 `OSError` 只要早一步发生就从外面穿出去。调用方 `scheduler/tasks.py:93` 那句 `if not backup.is_stale(...)` 没有任何 `try` 包着（那句 `try` 在 `_dump_and_notify` 里面，要过了这一行才进得去），于是补跑在**还没开始备份之前**就死掉：库从此没有保险检查，也没有一条通知说得清为什么（#100 那一族"悄悄停掉的备份没人报"）。用户在第二块选项板上选**甲：把那两句一起纳入 `try`**。
- **红是先看过的**：先把 `test_an_entry_that_was_already_gone_before_the_listing_gets_out_as_an_error`（钉"会抛"的那条现状）翻成断言 `is_stale(...) is True`，在**未改的 `src/backup.py`** 上跑 = **1 failed / 8 passed**，失败信息正是量出的形状：`FileNotFoundError` 从 `latest_backup` 的 `max` 里抛出、经 `is_stale` 穿出。改完这一文件 **9 passed**。
- **顺带接受的后果（写在这里是因为它是个真实的取舍）**：`latest_backup` 里那句 `os.listdir` 失败也是 `OSError`，所以**目录整个读不出**现在同样答"没有保险"。这是刻意的——这一问句问的是"库现在有没有保险"，答"没有"的下一步就是真去 dump，而那一趟失败有自己的通知；比在这里安静地返回"还保险"要好。docstring 把这两条 stat 和这一后果都写清了。
- **没动的**：`latest_backup` 自己仍可抛（它的 docstring 从来没承诺相反，`is_stale` 是唯一调用方）；"挑完才消失"那条路径照旧由 `test_a_dump_that_vanishes_between_the_listing_and_the_stat_counts_as_stale` 钉着；轮转那两行 `except OSError` 不动。
- **基线**：后端 PG 全量 **933 passed**（用例总数不变——这一条是改写不是新增），SQLite 分支上被改动的两个文件 **27 passed**，`ruff check src tests` 干净，`mypy src` 仍是 **34** 条基线错误。`src/backup.py` 现在 **277 CRLF / 0 lone LF**，md5 `1eb7195b58a09f5da2249a9bbfa73ed5`；`tests/test_backup_child_process.py` **197 CRLF / 0 lone LF**，md5 `79156408f625d230ddb7d9795cc47e53`。
### 拿一个已被删掉的标签 id 发 PUT，从此不会把这部片子的标签一起带走（#180）

- **这一单修的是 #173 量出来那个洞**：`PUT /api/videos/{id}` 里 `select(Tag).where(Tag.id.in_(tag_ids))` 只回查得到的行，查不到的**不当成错误**，而后面那句 `video.tags = tags` 是**整串替换**——两者叠起来，一个已经被删掉的标签 id 就能把这部片子原有的标签一起清空，接口照样回 200，也没有一句说得出是哪个 id 不存在。用户在第二块选项板上选**甲：拒绝**。
- **形状**：路由先核对标签、缺哪个就在 404 的 `detail` 里点出哪个号（`Tag not found: 999999`），**核对挪到了字段更新之前**。这是有意的取舍，不是顺手：`{title, tag_ids}` 一起发、标签那半是坏的时候，如果按原顺序写，库里会是"标题已经改了、接口回了 404"——和本轮 #176 那半截行、#177 那条假进度同一个形状的假象。
- **红是先看过的**：三条新用例在未改的 `src/` 上如实红（这一文件 **3 failed / 8 passed**），改完再跑这一文件连同另两个标签相关文件共 **49 passed**，PG 全量跟着 **933 passed**。它们替掉了 `test_a_tag_id_that_is_not_in_the_table_takes_the_whole_set_with_it` 那条钉现状的用例。
- **没动的两半**（各有用例钉着，别读成一起改了）：`{"tag_ids": []}` 仍然是一次**清空**的真写，`{"tag_ids": null}` 仍然 400；append 那一头（`POST /api/tags/video/{id}`）依旧忽略未知 id 且不动已有关系——**两条写路径对未知 id 的态度现在是不同的**，这一处差别由 `tag_service.py:147` 那侧的用例继续钉着。
- **前端不受影响**：`VideoUpdate.tag_ids` 这个字段全仓没有任何调用方发过（贴标签走的是 `POST /api/tags/video/{id}`），所以 Vitest、替身 e2e 和静态守卫都不用改——它本身已排在 #191（删掉这个字段）上。
- **基线**：后端 PG 全量 **933 passed**（931 + 这一单净增 2 条），SQLite 分支被改动的两个文件 **16 passed**，`ruff check src tests` 干净，`mypy src` 仍是 **34** 条基线错误。`src/api/videos.py` 现在 313 CRLF / 0 lone LF，md5 `e84a1194632ead038d307e097b4382bd`。
### 报进度给一条已经不存在的影片，从此说"没这部片子"而不是"好的收到"（#179）

- **这一单修的是 #177 量出来那个洞**：`POST /api/videos/{id}/progress` 对一条播放途中被人删掉的影片回 **200 `{"status": "ok"}`**，而隔壁 `/play` 同样情况回 **404**。用户在第二块选项板上选**甲**：服务层看不见影片时 `raise ValueError`，路由像 `/play` 那样接住 `ValueError` 映射成 404。**改动就是量过的那 2 个文件**（`src/services/video_service.py:624-634`、`src/api/videos.py:290-299`），没有顺带清理。
- **红是先看过的**：先把两条用例改成新行为、在**未改的 `src/`** 上跑，两条如实红——服务层 `Failed: DID NOT RAISE ValueError`，接口 `assert 200 == 404`。改完 `src` 后这两条翻绿，同一条路 #177 的电池 **W12** 早就量过：它红恰好这 2 条，其余 73 条不动。
- **`update_progress` 的 docstring 跟着补了一句为什么这不是"尽力而为"**：播放器每几秒报一次、离开页面再报一次，删片恰好发生在中间——404 是它得知"没什么可报了"的唯一信号，静默的 ok 只会让它一直报下去。
- **落地后新量到的一件事（写在这里是为了别把它改回去）**：这个 404 对用户是**无声**的，这正是想要的形状。`VideoPlayer.vue:294` 写的是 `updateProgress(...).catch(console.error)`，而 `src/api/client.ts` 的拦截器只把 `detail` 摊成 Error 再 reject、自己从不弹提示，所以 404 既不会变成一条toast也不会变成一次白屏。**别顺手给它加提示**——播放器要的是停止上报，不是打扰看片的人。
- **openapi 快照不动**：路由仍只声明 `status_code=200`，`HTTPException` 的 404 不进 spec（`/play` 也一样），所以 `tests/test_openapi_snapshot.py` 与前端那四层静态守卫都不受影响。
- **顺手更正 #177 记下的一句理由**：那条写着"拆掉 `634` 这句早退（W11）会让 PG 当场外键违例"，是推理不是重测。这次把同一拆法重新跑了一遍：**仍红 2 条**（服务层那条 + 接口那条，404 变 500），可先炸的是第 639 行 `is_completed(progress, video.duration)` 的 `AttributeError: 'NoneType' object has no attribute 'duration'`——外键那一段确实还在，只是被这句属性错误挡在后面、从来没真的执行到。"两种方言都承重"这类话里，闸门挡住的东西要重新量一遍。
- **基线**：后端 PG 全量 **931 passed**（用例总数不变——两条是改写不是新增：`test_a_progress_report_for_a_video_that_is_gone_writes_nothing` → `..._raises_and_writes_nothing`，`..._still_answers_ok` → `..._answers_404`），`ruff check src tests` 干净，`mypy src` 仍是 **34** 条基线错误。四个文件的换行实测都还是纯 CRLF（`src/api/videos.py` 302、`src/services/video_service.py` 649、两份测试 517 / 921，lone LF 全 0）。
### 补上封面删不掉、重复检测的读取预算、报给一条已经不存在的影片——这三段尾巴只有顺利那一路从外面进来过（#177）

- **症状**：`src/services/video_service.py` 停在 **98%**（260 句缺 6：`114-115, 382, 402, 406, 634`）。缺的六句分属三个真行为，共同形状不是"哪条分支忘了测"，而是**磁盘配合、预算够花、影片还在**这三个前提从来没被同时打破过：`114-115` 是封面被别的句柄攥住时那句兜底，`402`/`406` 是重复检测的读取预算装不下某一整组时那句 `continue` 加它换来的空返回，`634` 是给一条已经删掉的影片报进度时那句早退。
- **回归用例 8 条**（`tests/test_services/test_video_service.py` 38 → 45，`tests/test_api/test_videos.py` 29 → 30；两文件单跑 **75 passed**）：读取预算四条（大组先花光、超预算的一组整组不读、正好花光的一组要读完、形单影只的那行不算指纹）、封面两条（真句柄攥着删不掉、从来没有过的路径一句不抱怨）、进度两条（服务层一行不写、接口那一路照回 ok）。
- **预算这件事只能数"读了几趟"**：读满 300 趟和一组都没读，接口回来的是同一个形状。所以 `_counted_fingerprints` 把 `fingerprint` 换成一个记账的包装——**照样真算，只是顺便记下读了哪些文件**（#172 的教训：替身不许把要测的东西演掉）。计数从 `_DUPLICATE_PROBE_MAX` 推而不写死 300，常量一改用例跟着改。
- **封面那条是真造出来的失败，不是假体**：`open(cover, "rb")` 攥着不放，`os.remove` 在这台机器上真回 `PermissionError [WinError 32] 另一个程序正在使用此文件`；`chmod` 只读换来的是 winerror 5。用例断言的是三件事一起成立：行没了、文件还在、日志里恰好一条且带着回溯。
- **本单量出的洞（待用户定夺）**：`POST /api/videos/{id}/progress` 对一条已经不存在的影片回 **200 `{"status": "ok"}`**，而隔壁 `/play` 同样情况回 **404**（`api/videos.py:283-287` 接 `ValueError`，`290-299` 什么都没接）。播放器每几秒报一次、离开页面再报一次，删片恰好发生在这中间。选项：**甲** 服务层看不见影片时 `raise ValueError`、路由接成 404——影响面量过是 **2 个文件**，电池 **W12 就是甲的最小预备 fix**，红恰好 2 条（正是钉现状那两条），其余 73 条不动；**乙** 保持 200，只在 docstring 承认"进度上报是尽力而为"；**丙** 200 但 body 带一个标志位，让播放器自己决定要不要继续报这一路。两条新用例钉的都是**现状**，不是认可。
- **`634` 那句早退是承重的，两种方言都承重**：拆掉它（W11）红 2 条——`_get_or_create_history` 会往 `PlayHistory` 插一条指向不存在影片的行，PG 当场外键违例；SQLite 也违例，因为 #161 起连接上开了 `PRAGMA foreign_keys`。
- **`382` 这一句钉不住，也不是还欠一条用例**：`if video.file_size is None: continue` 运行时走不到——上面那条 SQL 已经 `WHERE file_size IS NOT NULL`，而 `NULL IN (…)` 永远不为真。实测两半：**删掉这两行 75 条全绿；`mypy src` 从 34 涨到 35**，多出的正是 `Argument 1 to "setdefault" ... incompatible type "tuple[int | None, int | None]"; expected "tuple[int, int | None]"`。所以这一句由**类型检查钉着**而不是由用例钉着，本文件因此落在 **99%** 而不是 100%——这是量出来的上限，不是漏补。
- **变异电池（本单 `src/` 一句未改，电池代替红→绿）**：13 格 → **12 红 + 1 实测等价**。W08（拆掉 `if not probed: return []`）全绿：`attach_watch_progress` 对空列表自己就早退、`asyncio.gather()` 空参数回空、末句 `return groups` 也是 `[]`，三个理由叠在一起，这一格没有用例能红。
- **W13 是这一轮唯一预测错了的格子，而且红得有价值**：我原以为把级联那句 `return [path for path in covers if path]` 换成 `list(covers)` 会被 `delete_cover_files` 里的 `isfile` 闸门接住（预期等价），实测**红 5 条**——没有封面的影片行 `thumbnail_path` 就是 `None`，而 `os.path.isfile(None)` 直接 `TypeError`。**那两道闸门看着重复，各挡一样东西**：过滤挡 `None`，`isfile` 挡"路径像样但文件没了"（老行里那种 `./data/...` 前缀）。
- **每一格的承重面**：W01–W04（`except OSError` 换成 `except ValueError`、拆 `isfile` 闸门、丢 `exc_info`、丢路径）各红 1；W05（预算当无限）红 2、W06（只比较不扣减）红 1、W07（边界从"超过"挪成"达到"）红 1、W09（小组先来）红 1、W10（独苗也算指纹）红 1、W11/W12 各红 2。
- **换行**：`src/services/video_service.py` 在工作树里是 **CRLF**（645 CRLF / 0 lone LF，md5 `a8bdf05149bfaed0e01baf93592b4fc9`），字节级改这一文件时锚点要按它自己的换行归一；13 格每格先断言锚点恰好命中一次、字节确实变过，跑完立即按字节还原并复验 md5（`restored_md5` 全 True，收官 md5 与基线一致）。

### 扫描按了停止、撞上坏文件那两路第一次被真演过——顺带量出"停掉的那一轮"在界面上和"扫完了"一模一样（#176）

- **症状**：`src/services/scan_service.py` 停在 **96%**（196 句缺 7 句：`183-184, 238-239, 331-333`）。缺的三格有一个共同形状：**一轮扫描的两种"半途"从来没被演过**——扫到一半有人按停止，和一个文件写库写到一半坏了。`183-184` 是 `is_scanning` 这个属性的函数体（进度接口读的是那张字典，属性本身此前一次也没被任何用例读过）；`238-239` 是文件那一圈的停止闸门（那句 log 加那个 `break`）；`331-333` 是每个文件外面那圈 `except Exception`——代码里那句「单个文件失败只跳过，不中断整个视频源的扫描」一直只是注释。
- **原先的停止用例演的是替身**：`test_stop_scan_skips_remaining_sources` 把 `scan_source` 整个换成一个假函数，于是"剩下的**源**被跳过"钉住了；代价和 #174 / #175 同形——**"文件那一圈也认停止"这条真路径零签字**，而内层那圈 `_tracked_scan` 会不会顺手把停止请求抹平（`outermost` 那道闸门到底承不承重）同样没人演过。坏文件那一圈更是上一条用例都没碰过。
- **回归用例 8 条**（本文件 33 → 41 条；连同 `tests/test_api/test_scan.py`、`tests/test_storage/test_scan_through_seam.py` 单跑时 `scan_service.py` 196 句 0 缺 **100%**）：属性与那张字典读的是同一份模块级状态；扫描自己崩了不许把界面永久卡在「正在扫描」（收尾写在 `finally` 里）；扫描**开始之前**按下的停止被丢掉（不丢的话一次误按就把之后每一轮掐死）；中途按停止只收尾手上那一部、清单里剩下的一个也不碰，而 `files_found` 说的一定是"清单有几部"而不是"处理了几部"；内层扫描收尾不许抹平停止请求；一部片子写库写到一半坏了，它的半截行被自己那层 SAVEPOINT 带回、同一份清单里后面那部照常建档、那句「跳过」带着完整回溯进日志；被跳过的那一部下一轮修好了照常建档；核对丢失用的是整份清单——所以停掉的那一轮不会把没来得及扫的行刷成「已找不到」。
- **本单量出的洞一（新的待用户定夺）：半途停掉的一轮，在界面上和"扫完了"完全一样。** 循环 `break` 之后 `source.last_scan_at` 照写、通知照发「视频源 X 扫描完成，发现 N 个新视频」，而清单里剩下的文件一个都没打开过。人按了停止以后，没有任何一处读得出这一轮是残缺的；补得上补不上取决于自动扫描开关（#150 那条链路）和间隔。选项：**甲** 停掉的那一轮不写 `last_scan_at`（或另记"部分完成"），**乙** 照写但通知改口（「已按请求停止，还有 M 个文件没扫」），**丙** 只在 docstring 承认「扫描完成」这句是近似。`test_a_stop_mid_source_leaves_the_rest_of_the_listing_alone` 末尾那两行断言钉的是**现状**，不是认可；电池 **V12 就是甲的最小预备 fix**——它红的那一条恰好就是这一条，其余 40 条一动不动，改法的影响面已经量过。
- **本单量出的洞二（同一族，也待用户定夺）：兜底只护着新片那半圈。** 老片走 `known is not None` 那一条 `continue`，它同样调 `_register_subtitles`，但那一句在 `try` **外面**（`try` 从新片那一段才开始）。于是库里已有的一部片子字幕写不进去时，异常穿出 `scan_source`：这一轮 `last_scan_at` 不写、通知不发、剩下的文件一个没扫；而同一份清单里一部**新**片出同样的毛病只是跳过。手动按钮那一路因此是一个 500（`api/scan.py` 只把 `ValueError` 映射成 404），定时那一路由 `scheduler/tasks.py` 的 `scan_error` 通知兜着——同一颗雷的两个面。选项：**甲** 把老片那一圈也套进同一个 try（电池 **V13** 就是这一改法的最小版，恰好红一条），**乙** 保持不对称、把那句注释改成「只有新片那半圈有兜底」，**丙** 让整轮失败说清是哪一部片子带的。`test_a_known_videos_subtitle_failure_still_takes_the_round_down` 钉的同样是现状——今天真字幕注册只做 add/flush、炸不出来，所以这一条没有现成的坏输入，异常是假体喂进去的。
- **红在先（本单 `src/` 一行未改，红由电池给）**：V01–V14 十四格 → **13 红 + 1 实测等价**（其中 V12、V13 是预备翻转）。范围是 `tests/test_services/test_scan_service.py` 的 41 条；`src/services/scan_service.py` 在工作树里是 **CRLF**（442 CRLF / 0 lone LF，md5 `dd796a8f65a9a96364dbde447e10c4c7`），锚点按它自己的换行归一，每格先断言锚点命中恰好一次且字节真的变了，改完即按字节还原并 md5 复核（十四行 `restored_md5` 全 True，收尾 md5 与基线一致）。V05 那一格绿是**结构性**的，不是"忘了测"：`continue` 是循环体的最后一句，删掉它和留着它走到的是同一个循环末尾，所以这一格没有任何用例能红——承重的是它上面那句 `logger.warning`（V06 红 1）和那层 `begin_nested`（V07 红 2）。

| 格 | 改的那一处 | 结果 | 红几条 | 坏掉的话 |
|---|---|---|---|---|
| V01 | 文件那一圈的停止闸门改成永假 | 红 | 2 | 按了停止照样把整份清单扫完 |
| V02 | 只留那句 log、把 `break` 删掉 | 红 | 2 | 日志说停了，其实没停 |
| V03 | 保留停止行为、把那句 log 删掉 | 红 | 1 | 停了却没有任何一处说为什么 |
| V04 | 每个文件那圈 `except` 收窄成只接 `ValueError` | 红 | 2 | 一个坏文件让整轮 500 |
| V05 | 删掉 `except` 体末尾那句 `continue` | **绿** | 0 | 实测等价：它是循环体最后一句 |
| V06 | 跳过那句不带 `exc_info` | 红 | 1 | 运维只知道"跳过了"，不知道为什么 |
| V07 | 拆掉每个文件自己的 SAVEPOINT | 红 | 2 | 半截行留在库里，后面那部陪葬 |
| V08 | 最外层进场不再重置状态 | 红 | 1 | 一次误按把之后每一轮都掐死 |
| V09 | 收尾不再看 `outermost` | 红 | 1 | 内层扫描把停止请求抹平，只停了一半 |
| V10 | `is_scanning` 属性硬编码成 False | 红 | 1 | 属性与字典读的不是同一份状态 |
| V11 | 丢失核对不再看清单 | 红 | 8 | 按了停止的那一轮把没扫的行刷成「已找不到」 |
| V12 | 预备方案甲：停掉的一轮不再写 `last_scan_at` | 红 | 1 | 恰好是钉现状的那条用例 |
| V13 | 预备对称化：老片那一圈也套上同一个 try | 红 | 1 | 恰好是钉不对称的那条用例 |
| V14 | 收尾整块删掉 | 红 | 6 | 扫描崩了界面永远转圈，停止标记还留着 |

- **基线**：PG 全量 **923 passed，2 warnings，208.97s**，TOTAL **95.92%**（4613 句缺 188，上一轮 195——少的正是这一文件那 7 行）；SQLite 分支同轮 **922 passed + 1 skipped，83.31s**；两遍 RC 均 0。`ruff check tests src` 干净，`mypy src` 维持 34 条基线。

### 探针自己跑不起来时，接口说的是关于这部片子的假话——media_streams 的三路坏输出第一次各有签字（#175）

- **症状**：`src/utils/media_streams.py` 停在 **92%**（61 句缺 5 句：`57-58, 66, 176-177`），缺的三格有一个共同形状：**"探针跑不起来 / 输出不是预期那样"这一族，原先十条用例一条都没演过**——它们把 `subprocess.run` 换成替身，演的全是"一切顺利"那一路。`57-58` 是 ffprobe 回了一段坏 JSON（半截、被中途杀掉、磁盘写满）时"当作读不出来"的那道兜底，`66` 是一条**连 `tags` 都没有**的轨（裸 AAC、裸 srt 常见；`65` 那个判断本身早有分支经过，缺的是它的 `return`），`176-177` 是提取时 ffmpeg 那个子进程根本起不来 / 挂住 / 被拒绝。
- **替身是对的，但盲区留下了**：原先 10 条钉住了 argv（`-show_streams`、`-map 0:N`、末尾那个 `-`），代价和 #174 完全同形：**发出去的超时与解码约定（`timeout=30` / `timeout=60` / `encoding` / `errors`）在替身之下没有任何一格签字**，两处 `except (FileNotFoundError, subprocess.TimeoutExpired, OSError)` 里也只有 `FileNotFoundError` 一支被真的抛过。这次让替身把 kwargs 记下来，并把喂进去的异常实例当作"子进程那一步真的坏了"往上 `raise`。
- **回归用例 10 条**（本文件 10 → 20 条；单跑本文件时 `media_streams.py` 61 句 0 缺 **100%**）：半截 JSON 落成 `probed: False` 而不是 500；无 `tags` 的轨退回"轨道 N"且**不影响** `supported`（能不能转 WebVTT 只看编码器）；`""` 与 `"  "` 两种坏法走的是两个不同口子（前者在 `or` 那里就假了，只有空白能活到那个占位集合）；`und` / `xxx` 两个占位码各归一枚钉（`xxx` 此前全库没被喂过）；`language` / `LANGUAGE`、`title` / `TITLE` 四种拼法都认（大写字面此前摘掉任何半边都量不出红）；两次子调用的超时与编码约定；ffmpeg 起不来 / 挂住 / 被拒绝三种坏法各走一遍且原因带在句子里；探针挂住或共享被拒绝时详情页只是"探不到"。
- **本单量出的洞（新的待用户定夺）**：`extract_subtitle_webvtt` 在 ffprobe **自己**跑不起来（没装、不在服务账号的 PATH 上、30 秒没回）或**非零退出**（文件坏、share 掉线）时，`_run_ffprobe` 回 `{}`，于是 `wanted` 是空集，接口说的是「文件里没有编号为 N 的字幕轨」并回 404（`api/subtitles.py` 把 `StreamNotFoundError` 映射成 404）——**真原因（工具没跑成）被换成了一句关于这部片子的假话**，而它恰好是用户听得见、也修得了的那一句。对照 #142：外挂字幕那一路后来把 ffmpeg 的原因带上了，内嵌这一路今天仍然没有。三个选项：**甲**把"探测失败"和"没有这条轨"分开说话（回 404 还是 503/415 请用户定），**乙**只在 docstring 承认这一句是近似，**丙**让 `probe_streams` 的 `probed: False` 一并带上原因。两条钉住**现状**的用例把这句话原样锁住（`test_a_probe_that_could_not_run_is_blamed_on_the_file` / `test_a_probe_that_exits_non_zero_is_blamed_on_the_file_too`），不是认可；电池里的 **Y17 就是甲的最小预备 fix**——它红的那两条恰好就是这两条，其余 18 条一动不动，说明这一改法不会碰到别的行为。
- **另有一处测量结果，选择不钉**：ffprobe 理论上可能回一段**合法但不是对象**的 JSON（`[]` / `null`），那时 `probe_streams` 会把 `AttributeError` 送到接口外面。真 ffprobe 带 `-print_format json` 不会这样回，所以只记不钉——免得留一条永远红不了也永远绿不了的用例。
- **红在先（本单 `src/` 一行未改，红由电池给）**：Y1–Y17 十七格 → **14 红 + 3 实测等价**（其中 Y17 是预备翻转）。范围是 `tests/test_utils/test_media_streams.py` 的 20 条（`tests/test_api/test_subtitles.py` 那 20 条把 `probe_streams` / `extract_subtitle_webvtt` 整个换成替身，红不到这一文件的内部，所以不在范围内）；`src/utils/media_streams.py` 在工作树里是 **CRLF**（182 CRLF / 0 lone LF），锚点按它自己的换行归一，每格先断言锚点命中恰好一次且字节真的变了，改完即按字节还原并 md5 复核（`b7e76de876ad8a05db2351dfe4c4c462`，十七行 `restored_md5` 全 True，收尾 `git diff --ignore-cr-at-eol -- src/utils/media_streams.py` 为空）。三格绿各有道理，都不是"忘了测"：摘掉 `text=True` 是结构上红不了的等价参数（#174 的 Z4 同族），从两处元组里单独摘 `FileNotFoundError` 摘不出红是因为**它是 `OSError` 的子类**——真正承重的是 `OSError` 与 `TimeoutExpired` 那两支，这一条已写进用例 docstring，别把它读成"三个成员各有签字"。

| 格 | 改的那一处 | 结果 | 红几条 | 坏掉的话 |
|---|---|---|---|---|
| Y1 | `except ValueError` → `except KeyError` | 红 | 1 | 半截 JSON 不再是"读不出来"，片源详情页变 500 |
| Y2 | `if not code:` → `if False:` | 红 | 4 | 没有语言标签的轨在 `None.strip()` 上炸 |
| Y3 | 占位集合去掉 `""` | 红 | 1 | 一条 `"  "` 的轨把空串当语言发给前端 |
| Y4 | 占位集合去掉 `"und"` | 红 | 1 | `und` 原样进菜单 |
| Y5 | 占位集合去掉 `"xxx"` | 红 | 1 | 同上；`xxx` 此前全库零签字 |
| Y6 | 去掉探测的 `timeout=30` | 红 | 1 | ffprobe 挂住时那个请求跟着挂 |
| Y7 | 去掉提取的 `timeout=60` | 红 | 1 | 播放器等一条字幕可以等到无限 |
| Y8 | 去掉探测的 `text=True`（`encoding` 留着） | **绿** | 0 | 实测等价：`subprocess` 见 `encoding` 就进文本模式 |
| Y9 | 提取元组去掉 `TimeoutExpired` | 红 | 1 | ffmpeg 挂住时异常穿出接口 |
| Y10 | 提取元组去掉 `OSError` | 红 | 2 | 起不来 / 被拒绝两种坏法穿成 500 |
| Y11 | 提取元组去掉 `FileNotFoundError` | **绿** | 0 | 它是 `OSError` 的子类，父类照样接住 |
| Y12 | 探测元组去掉 `TimeoutExpired` | 红 | 1 | 探测那一头挂住时详情页 500 |
| Y13 | 探测元组去掉 `OSError` | 红 | 1 | 共享被拒绝时详情页 500 |
| Y14 | 探测元组去掉 `FileNotFoundError` | **绿** | 0 | 同 Y11 |
| Y15 | 去掉 `tags.get("LANGUAGE")` 那半边 | 红 | 1 | 打包器只写大写键时语言全丢、菜单变成"轨道 N" |
| Y16 | 去掉 `tags.get("TITLE")` 那半边 | 红 | 1 | 同上，轨名丢了 |
| Y17 | 预备 fix：探测空结果时改口说"读不出来" | 红 | 2 | 恰好是上面那两条钉现状的用例 |

- **基线**：PG 全量 **915 passed，2 warnings，192.76s**，TOTAL **95.77%**（4613 句缺 195，上一轮 200——少的正是这一文件那 5 行）；SQLite 分支同轮 **914 passed + 1 skipped，79.70s**；两遍 RC 均 0。`ruff check tests src` 干净，`mypy src` 维持 34 条基线。

### 备份那台子进程第一次真的起了进程，三道兜底分支第一次被走到（#174）

- **症状**：`src/backup.py` 停在 **95%**，缺的六行是四类各一，而且**没有一类是"某条分支忘了测"**：`124` 是 `_run` 里那句真的 `subprocess.run`——整个备份套把 `_run` 换成替身，这台子进程从 pytest 进来一次也没起过；`152` 是 `BACKUP_DIR` 为空那道闸门（今天没有调用方给过空串）；`217-218` 是轮转碰到 stat 不出的条目就跳过；`266-267` 是陈旧判断碰到 stat 不出的文件算陈旧。后两格要有"目录里列得出、`getmtime` 抛一次"的条目才走得到。
- **替身是对的，盲区还是留下来了**：换掉 `_run` 有理由——"口令有没有进 argv"只有在那一头才钉得住，真跑一次 pg_dump 反而看不出来，`tests/test_backup.py` 那 18 条断言的是真实 argv / env，这一层一律不动。代价是**发出去的 argv、环境变量、超时、还有那套解码参数本身一格签字都没有**。这一层落的是另一头，而且**不打库**（只用 `tmp_path` 摆文件），所以它能和任何事并行、也不需要测试库。
- **回归用例**：新增 `tests/test_backup_child_process.py` **9** 条。起真子进程用的是 `sys.executable`，不依赖机器上有没有 pg_dump；那三道兜底用**最小假体**走到真代码：只换 `os.listdir`（`getmtime` 保持是真的——它对不在盘上的名字真抛一次），以及只换 `latest_backup` 让它指回一个不存在的路径（`265` 那句 stat 真坏）。九条钉的是：子进程自己那两条流被当**文本**收回来、退出码忠实（3）；`encoding="utf-8"` 是实参不是装饰——子进程把中文按 UTF-8 字节写进 stderr，而这台机器的控制台代码页是 **cp936**，父进程按本地代码页解就会把 pg_dump 的中文诊断变成一串谁也读不懂的字节，那句正是失败通知里唯一的原因；`errors="replace"` 承的是另一个重——一个坏字节要是变成 `UnicodeDecodeError`，备份任务连原因都发不出去（实测两字节 → 两个 U+FFFD，不抛）；`timeout` 是真转发（1 秒就回 `TimeoutExpired`，`.timeout == 1`）；`_run` 用的是**交给它的那一份**环境而不是父进程那一份——这条比"值进得去"值钱得多，因为 `run_backup` 是 `env = {**os.environ}` 现抄一份再往上加 `PGPASSWORD`，一旦回落成父进程环境，**传一份"没有它"的环境也没用**，口令再也清不掉（子进程对两种偏差各回一个不同退出码 5 / 6 / 0，坏了能指出坏在哪半）；空目录在**建任何目录之前**就被拒（`calls == []` 且 `tmp_path` 空）；轮转碰到一个列得出、stat 不出的名字，旁边那份真过期的照清；"挑完最新那一份之后才消失"的文件算陈旧而不抛。
- **本单量出的那个洞（新的待用户定夺）**：`is_stale` 的 docstring 明写"stat 不出的条目按陈旧处理而不是抛异常，因为它跑在启动那一段，一个悬空条目不该把应用带下去"，而实测**只有晚一步消失的文件才走得到那句 `return True`**——如果它在 `latest_backup` 挑最新那一份**之前**就 stat 不出，`FileNotFoundError: [WinError 2]` 是从 `261` 那行外抛的（`max(key=os.path.getmtime)` 自己就 stat），`264-267` 那个 `try` 包不住。调用方 `scheduler/tasks.py:93` 那句 `if not backup.is_stale(...)` **没有任何 `try` 包着**（那句 `try` 在 `_dump_and_notify` 里面，要过了这一行才进得去），于是启动补跑在还没开始备份之前就死掉：库从此没有保险检查，也没有一条通知说得清为什么——和 #100 是同一个族。三个选项：**甲**把那两行一起纳入 `try`（两行，docstring 从此为真，推荐）／**乙**只改 docstring，承认它会把异常送上去／**丙**在 `tasks.py` 那一侧包一层。用例钉的是**现状**（`test_an_entry_that_was_already_gone_before_the_listing_gets_out_as_an_error` 断言 `FileNotFoundError`），不是认可；电池里的 **Z10 就是那句预备 fix**——它现在红的那一条正是这一条，选定甲之后翻绿的路径已经量过。
- **红在先（本单 `src/` 一行未改，红由电池给）**：Z1–Z10 十格 → **8 红 + 1 实测等价 + 1 预备翻转**。范围是 `test_backup_child_process.py` + `test_backup.py` 共 **27** 条；`src/backup.py` 在工作树里是 **CRLF**（273 CRLF / 0 lone LF），锚点按它自己的换行归一，每格改完即按字节还原并 md5 复核（`7451c02d4b8b092ccf62c7ddbdadf997`，十行 `restored_md5` 全 True，收尾 `git diff --ignore-cr-at-eol -- src/backup.py` 为空）。

| 格 | 改的那一处 | 结果 | 红几条 | 坏掉的话 |
|---|---|---|---|---|
| Z1 | 去掉 `encoding="utf-8"` | 红 | 1 | 子进程来的那句中文诊断按本地代码页解，变成乱码 |
| Z2 | 去掉 `errors="replace"` | 红 | 1 | 一个坏字节把失败通知本身炸成 `UnicodeDecodeError` |
| Z3 | 去掉 `capture_output=True` | 红 | 3 | `result.stdout` 是 None，什么都读不回来 |
| Z4 | 去掉 `text=True`（`encoding` 留着） | **绿** | 0 | 实测等价：`subprocess` 见 `encoding`/`errors` 本身就进文本模式 |
| Z5 | 去掉 `timeout=timeout` | 红 | 1 | pg_dump 挂住时任务永远挂着（这一格真的让子进程挂了 30 秒） |
| Z6 | `env=env` → `env=None` | 红 | 1 | 你没有传进去的 `PGPASSWORD` 照样到得了子进程 |
| Z7 | `if not backup_dir:` → `if False:` | 红 | 1 | 空目录不再是拒绝，而是更深一处的崩 |
| Z8 | 轮转 `except OSError` → `except ZeroDivisionError` | 红 | 1 | 一个悬空条目把整轮轮转带停，真过期的那份留在那儿 |
| Z9 | 陈旧判断 `except OSError: return True` → `return False` | 红 | 1 | 消失的 dump 被当成"还新鲜"，补跑任务从此不跑 |
| Z10 | 预备 fix：`try` 把 `latest_backup` 那一行也包进去 | 红 | 1 | 正是钉洞那一条——行为变更，等用户定夺 |

- **一格读错就危险的东西**：Z4 那条 `text=True` 和 #172 那两组**有默认值的 `response_model` 字段**是同一族——结构上就红不了（`encoding` 一个参数已经把文本模式定了）。别把这一格读成"`text=True` 有用例签着"；真要签它得换一条不带 `encoding` 的调用，而这一层今天没有那种调用。
- **基线**：PG 全量 **905 passed（2 warnings，135.04s）**，TOTAL **95.66%**（4613 stmts / 200 miss，上一单是 206 miss——正好是这一文件那六行）；SQLite 分支同轮 **904 passed + 1 skipped**（56.02s），两边退出码都是 0。`src/backup.py` 95% → **100%**（119 stmts / 0 miss）。`ruff check tests src` 干净，`mypy src` 仍是那 **34** 条基线（这一单复量过，不是新增）。前端一层没动：这一单只加后端用例，`openapi.json`、路由表和前端谁也没碰。
- **文档**：`backend/CLAUDE.md` 薄位置清单加一条 `src/backup.py`（含 Z4 那条等价、`_run` 那套参数的签名位置、以及上面那个洞）；讲备份机制那一节不动口径——它说"起 `pg_dump`、再用 `pg_restore -l` 读回来"，这一单补的正是那一句**真起进程**的签字，不是新行为。

### 影片↔标签有两条写路径，语义相反，而其中一条从 pytest 进来一次也没被走过（#173）

- **症状**：`src/api/videos.py` 在修正后的读数里是 **94%**，缺的八行是 `236-238` 和 `242-248` ——合起来不是边角，是 **`PUT /api/videos/{id}` 上 `tag_ids` 那一路的整个函数体**。接口层此前只被 `POST /api/tags/video/{id}` 那一头敲过（append 语义），而 PUT 这一头拿到 `tag_ids` 走的是 `video.tags = tags`——**整串换掉**。同一张 `video_tags`，两条路径语义相反，中间那条零钉子。
- **为什么界面上看不见它**：`VideoDetail.vue:234` 组装的 `VideoUpdate` 只有 `title` / `description` / `rating` 三个键，`frontend/src/types/video.ts:96` 里那个 `tag_ids?` 是**从来没被发出去的字段**（和 #151 那四个装饰配置项同一族）。所以这一路今天唯一的调用方是"任何别的客户端"，而它能把一个人挂好的标签整串清空。库是共享的（`update_video` 的 docstring 写明"anyone signed in edits the same row"，`user_id` 只用来带播放进度），所以这不是越权面，是语义面。
- **回归用例**：新增 `tests/test_api/test_video_tag_put_endpoint.py` **9** 条。钉的是：append 挂上 A 之后 PUT 只交 B → 只剩 B、链接表里 A 那行随之消失（那条分界线本身）；`tag_ids: []` 是一次真写而标签行还在；**请求里有一个不存在的 id 就把整串带走**（下面单列）；片子不存在时两半都 404 但**措辞不同**——`236-238` 那句不带 id、服务层那句带，用例钉"两句不一样 + 都 404"而不钉措辞（#153 正等着翻译这一族英文）；提交先于响应（`expunge_all` 之后重读还在，少了那句 commit 响应照样好看）；`{title, tag_ids}` 同请求两半都写进去；只改标签**不动 `videos.updated_at`** 而改标题动（详情页 `VideoDetail.vue:454` 显示的"更新于"因此认不出刚贴过标签）；`{"tag_ids": null}` 是 400 而不是"什么也不改"（`model_dump(exclude_unset=True)` 让"没带这个键"和"带了 null"落到同一个 `tag_ids is None`）；重复 id 只留一条链接且不回 500。
- **本单发现的那个洞（改不改属于产品决定，待用户定夺）**：`select(Tag).where(Tag.id.in_(tag_ids))` 只回查得到的那些，查不到的**不当成错误**，而后面那句是整串替换——两者叠起来，拿一个已经被人删掉的标签 id 发一次 PUT，这部片子原有的标签会一起没了，接口照样回 200，也没有任何一句说得出"哪个 id 不存在"。对照：append 那一头同样忽略未知 id，但它不动已有的关系（`tag_service.py:147` 的 `if tag and tag not in video.tags`）。用例今天钉的是**现状**，不是认可。
- **红在先（这一单没改 `src/` 一行行为，说清楚）**：新用例在旧代码上直接是绿的，能红的是变异电池——**10 格里 9 红 1 绿**，那 1 绿是实测出来的等价变异，不是漏钉。
- **变异**（一次一个变量；每轮**先断言锚点在文件里恰好命中一次、替换后字节确实变了**才允许把那一格算数；跑完按字节复位并核 md5 `d95de0ddf5ff8e0453ca227f8fd6b9be`，与快照一致。这一族还多一道前置：**`src/api/videos.py` 在工作树里是 CRLF**，而 `src/` 其余文件是 LF，所以锚点必须先按目标文件的换行归一，否则 `anchor_count` 恒为 0、每一格都会被"锚点没命中"挡下——第一轮就是这么拦住的）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 `video.tags = tags` 改成"原有不动、往上追加" | **红** 3 条（两条写路径从此变成同一件事） |
  | M2 换完标签不 `commit` | **红** 5 条（响应照样好看，库里没动） |
  | M3 提交后不再 `refresh(video)` | **绿**——等价变异，见下 |
  | M4 `if tag_ids is not None` 写成 `if tag_ids` | **红** 1 条（`[]` 和 `null` 从此不分） |
  | M5 去掉 `236-238` 那句 404 | **红** 1 条（`video` 是 `None`，撞上 500） |
  | M6 查标签时不带 `Tag.id.in_(tag_ids)` | **红** 3 条（库里的每个标签都挂上去） |
  | M7 `pop("tag_ids")` 换成 `get("tag_ids")` | **红** 2 条（键留在 `update_data` 里，于是走的不是同一句 404） |
  | M8 拆掉"什么都没带"那道闸门 | **红** 2 条（`{"tag_ids": null}` 从 400 变成静默 200） |
  | M9 未知 id 不再静默丢弃、改成 404 | **红** 1 条（今天这个"丢弃"是被选中的行为，不是巧合） |
  | M10 `if not update_data and tag_ids is None` 少掉半边 | **红** 7 条（只带标签的请求被整体拒掉，这一路今天就是这样被用的） |

- **M3 那一格绿的是会话不是用例**：`await session.refresh(video)` 摘掉之后 71 条照旧全绿——关系刚刚在同一个会话里被赋值过，对象就在 identity map 里，序列化读的是内存那份，不是数据库。所以这一句今天是**不承重**的，`test_the_replacement_is_committed_before_the_response_finishes` 钉住的是那句 `commit`，不是这句 `refresh`（别把它读成"重读过的值已经签了"）。
- **电池的读数这一版带两列 md5**：`mutated_md5=False` 是那轮磁盘上确实是**变异态**（与快照不同）的证据，`restored_md5=True` 才是复位成功的证据——十行全是 False/True，最后一行 `FINAL md5=… match=True` 再独立核一次，并用 `git diff --ignore-cr-at-eol` 确认这个文件对 HEAD 零差异。上一版只有一列 `restored_md5`，而它在 `finally` 复位**之前**就读文件，十行全报 False；那种列会被后人当成证据读，所以测量挪到了复位之后，整块电池也**对着最终字节重跑了一遍**（上一遍之后又改了 6 处 E501 换行，和一处写死的 `/api/videos/1` → 同一个 id 的 f-string），十格判定一字未变——上面这张表是第二遍的。
- **基线**：PG 全量 **896 passed（2 warnings，189.06s）**，TOTAL **95.53%**（4613 stmts / 206 miss，上一单是 214 miss）；SQLite 分支同轮 **895 passed + 1 skipped**。`src/api/videos.py` 94% → **100%**（142 stmts / 0 miss）。ruff `tests src` 干净，`mypy src` 仍是 34 项基线（`src/` 一行未改）。
- **文档**：`backend/CLAUDE.md` 的薄位置清单补了这一格与上面量出的性质。

### 转码那三条端点没人请求过，那条完成通知一直被替身演着：13 处 noop 之外第一次真写了一行（#172）

- **症状**：两份读数是同一件事的两头。`src/api/transcode.py` 在 PG 全量里 **89%**，缺 `87`（`GET /{video_id}/status` 的函数体）、`108-111`（`POST /{video_id}/cancel` 的 try 和它那两句 `except ValueError → 404`）、`119`（`GET /formats`）；`src/services/transcode_service.py` **89%**，缺 `155-158`（编码器抛异常时那句兜底）、`168-183`（`_notify` 整个本体）、`209-210`（`_record_output` 那个 `except`）、`286`（`cancel()` 末尾那句 `job.status = "cancelled"` 兜底）、`290`（`get_supported_formats()` 直通）。
- **为什么是盲区**：pytest 里对 `/api/transcode/*` 只发过两种请求——`POST /{video_id}`（成功那一路）和 `GET /{video_id}/outputs`（#154 那一单加的）。状态、取消、格式表三条地址一次也没被敲过，而前端进转码页就并发读状态与格式表（`Transcode.vue:217` 的 `loadAll`），之后每 1.5 秒轮一次状态。另一头是**替身把要测的东西演掉了**：`test_transcode_service.py` 里 **12** 条 + `test_transcode_products.py` 里 **1** 条，一共 13 处用例先把 `_notify` 换成 noop，注释给的理由是"别让后台任务写应用库"——那条顾虑从 #154 起就有了别的解法（同一个文件的 autouse fixture 把模块级 `async_session_maker` 指回测试库），于是那句理由今天站不住，而 `_notify` 的 16 行从此没有一次真跑过。它写的正是人能看见的那句话：`NotificationCenter.vue` 的 `isErrorType` 用 `type.endsWith('_error')` 认失败，真后端 e2e 第 15 条对着 `type` / `title` / `data` 三个键断言——这是一条跨语言的契约，中间那一层却是空的。
- **回归用例**：新增 `tests/test_api/test_transcode_read_endpoints.py` **8** 条 + `tests/test_services/test_transcode_notification.py` **7** 条。接口那一份钉的是形状：idle 那一路七个字段逐字相等（少一个字段在接口上不报错，只在页面上变成 `undefined`）、跑着时 `progress` 只留一位小数、状态那一条**不查库**（影片行已删掉也回 200 + idle，轮询代码只准备了这一个分支）、启动被拒时 400 带着原因、取消不存在的路时 404 且原因里点名是哪一部、活任务取消回 204 空体、一条手工摆出来的 `task=None` 记录（见下），格式表就是 `SUPPORTED_FORMATS` 的投影。通知那一份钉的是文案与两处吞异常的分界：成功只写一行且 `data` 带得到 `video_id`、ffmpeg 那句原话必须出现在失败通知末尾（#142 的症状在同一层的另一个现场）、没给原因时只能说"未知原因"而不是 Python 的 `None`、编码器整个抛异常时状态写 failed 而人那边照例有一行、通知写不进去时吞掉但不牵连任务状态与产物登记、产物登记写不进去时吞掉而通知照写、**取消那一路什么都不发**。`data` 里那个 `video_id` 今天没有前端读它（`grep` 全仓只有一处在写），用例钉它是因为 e2e 第 15 条钉了它——别把它读成"通知能点回那部片子"。
- **两处吞异常必须分开坏**：`_notify` 和 `_record_output` 用的是同一个模块级 maker，把整个 maker 换成一炸到底，两处 `except Exception` 会一起吞——两行都算"覆盖到了"，谁也没被钉住。所以用例给了一个**只坏 `session.scalar`** 的包装会话（`_record_output` 开头那次查重走它，`_notify` 的 add/commit/refresh 照常），另有一条把 `NotificationService.create` 换成抛异常，两个方向各钉一处。
- **红在先（这一单没改 `src/` 一行行为，说清楚）**：新用例在旧代码上直接是绿的，能红的是变异电池——**19 格里 18 红 1 绿**，那 1 绿是实测出来的等价变异，不是漏钉。
- **变异**（一次一个变量；每轮**先断言锚点在文件里恰好命中一次、替换后字节确实变了**才允许把那一格算数；跑完按字节复位并核 md5：`src/api/transcode.py` = `67227a9dd26d54ca39da44e356e8d0e6`、`src/services/transcode_service.py` = `4bd397b85cda7dbeeb4ebf268704272f`，两份都与快照一致）：

  | 变异 | 结果 |
  | --- | --- |
  | X1 状态响应里摘掉 `error` 那个键 | **绿**——等价变异，见下 |
  | X1b 摘掉 `video_id`（模型里没默认值） | **红** 5 条（`ResponseValidationError`） |
  | X1c 把 `is_transcoding` 改成 `isTranscoding` | **红** 5 条（同上，字段名从 snake 漂成 camel） |
  | X1d 把 `status` 翻转（idle ↔ running） | **红** 5 条 |
  | X2 取消不再捕获 `ValueError` | **红** 1 条（500 而不是 404 + 原因） |
  | X3 取消的 204 改成 200 | **红** 2 条 |
  | X4 `/formats` 回空表 | **红** 1 条 |
  | X5 启动那句 400 换成不含原因的固定英文 | **红** 1 条（`assert 'exe' in 'start failed'`） |
  | Y1 编码器抛异常时不写状态 | **红** 1 条（永远 running，通知还说完成） |
  | Y2 失败文案去掉 `or '未知原因'` | **红** 1 条（末尾出现字面量 `None`） |
  | Y3 失败文案不带 ffmpeg 那句 | **红** 3 条 |
  | Y4 `completed` 写死成 `True` | **红** 3 条 |
  | Y5 通知不带 `data` | **红** 2 条 |
  | Y6 `_notify` 的 `except` 改成往外抛 | **红** 1 条 |
  | Y7 `_record_output` 的 `except` 改成往外抛 | **红** 1 条 |
  | Y8 `cancel()` 末尾那句兜底改成永不成立 | **红** 1 条（手摆的那条防御用例） |
  | Y9 `CancelledError` 那一路不再 `raise` | **红** 1 条（每次取消多发一条失败通知） |
  | Y10 `progress` 不再四舍五入 | **红** 1 条 |

- **X1 那一格绿的是模型不是用例**：`TranscodeStatusResponse.error: str | None = None` 有默认值，FastAPI 用 `response_model` 构造时把缺掉的那个键补成 `None`，所以"服务层少给一个有默认值的字段"在 HTTP 这一层根本看不出来。形状是**声明**钉住的，不是这一条用例钉住的；红的是没默认值的那两格（X1b / X1c 直接 `ResponseValidationError`）。这一句写下来是因为它**钉不住**，不是记它已经钉住了。
- **`cancel()` 末尾那两行是构造性不可达**（与 #165 那两处同一处理）：`transcode()` 是先 `asyncio.create_task` 再登记进 `_jobs`，而 `_run` 成功/失败/取消每一路都写状态，所以"账上挂着 running 却已经没有任务对象"这一状态今天走不到。用例手工摆一条 `task=None` 的记录钉住它确实收敛成 `cancelled`，并在 docstring 里声明这是防御分支——别把它读成实测到的路径，也别"顺手加个 finally 补状态"。
- **基线**：PG 全量 **887 passed, 2 warnings**，TOTAL **95.36%**；SQLite 分支同轮 **886 passed + 1 skipped**。`src/api/transcode.py` 89% → **100%**，`src/services/transcode_service.py` 89% → **100%**。ruff `tests src` 干净，`mypy src` 仍是 34 项基线（`src/` 一行未改）。
- **文档**：`backend/CLAUDE.md` 的薄位置清单补了这两格，以及上面量出来的那五处性质（X1 那个等价变异、两处吞异常要分开坏、`cancel()` 末尾那两行为何不可达、状态那一路不查库、取消不许发通知）。

### 启动选路与会话收尾那十一行一次也没被执行过：`init_db()` 第一次真跑，连接还不还得问连接池（#171）

- **症状**：`src/database/session.py` 在 PG 全量读数里是 **88%**，缺 `205-210` 和 `278-282` 两段。前者是 `init_db()` 的选路本体（认库 → 老库补齐 + `stamp_head` / 否则 `upgrade_head`），后者是 `get_session()` 的 `yield` 加 `finally: await session.close()`。两段的共同点是**只有生产在用、测试从不进来**：启动那一份用例（`test_app_boot_lifespan.py:82-88`）和 `test_cli.py:318-321` 都把 `init_db` 换成只登记名字的替身，而所有走 HTTP 的用例经 `app.dependency_overrides[get_session]`（`conftest.py:190-193`）借的是测试自己的会话。于是"库来了到底走哪条路"和"一个请求的会话还不还回去"这两格零钉子——后者恰好是少一行 `close()` 也不报错、只在连接池被抽干的那天炸的那类东西。
- **补的是执行入口，不是断言密度**：`tests/test_migrations.py`（5 条）早就分别在同步连接上试过 `_is_unversioned_legacy` / `stamp_head` / `upgrade_head` / `business_tables`，零件全是活的，缺的是**把 `init_db()` 本身调用一次**——三条路线由谁选、选完库里到底留下什么，此前没有任何一条用例知道答案。
- **回归用例**：新增 `tests/test_database_boot_routes.py` **8** 条。这里不换替身：`init_db` 真跑，`get_session` 直接从生成器那一头消费。两个函数读的都是**模块级**的 `engine` / `async_session_maker`，而那两个默认指向 `settings.database_url`，所以每台引擎换成 `tmp_path` 上一个独立的 SQLite 文件库（夹具 `boot_engine` 顺带在第一次连接之前挂上 `enforce_sqlite_foreign_keys`）——留着默认值就是去动开发库。八条钉的是：空库由基线建出、落到 head、与模型声明零漂移；只有一张表又没有版本行的老库走补齐 + `stamp` 那一路而不是 `upgrade`，且**老库里那一行还在**；已版本化的库第二次启动一字不改；只跑到第一个修订的库下一次启动把剩下的补上（`transcode_outputs` 从无到有）；`get_session` 交出来的会话绑的就是当时那台引擎（`get_bind() is engine.sync_engine`，实测 `is engine` 为 **False**）、提交的那一行从另一条连接读得回来；正常结束、消费方抛异常（`athrow`）两种收尾之后 `engine.pool.checkedout()` 都回到 0；没提交的写不会跟着会话出去。
- **为什么"还不还连接"只能问池子**（探针实测，代码读不出来）：一个已 `close()` 的 `AsyncSession` 再执行语句**不报错**，也没有 `.closed` / `.is_closed` 属性可问——所以"会话被关掉了"这句话没有任何直接可断的观察量，能观察的只有连接池的 `checkedout()`（用前 0、语句后 1、收尾后 0）。
- **红在先（这一单没有可复的先红，说清楚）**：#171 没改 `src/` 一行行为，它补的是盲区，所以不存在"对着修改前的 HEAD 先跑红一次"——新用例在旧代码上直接是绿的。能红的是变异电池：**10 格里 6 红 4 绿**，那 4 绿是实测出来的**等价变异**，不是漏钉。
- **变异**（一次一个变量；每轮**先断言替换锚点在文件里恰好命中一次、替换后字节确实变了**，才允许把那一格算数；跑完按字节复位并核 md5 `1a4214e6ea70aaa06038b25f13c2868d`，与快照一致）：

  | 变异 | 结果 |
  | --- | --- |
  | W1 认库恒真（永远走补齐 + `stamp`） | **绿**——等价变异，见下 |
  | W2 认库恒假（永远 `upgrade_head`） | **红** 1 条（`OperationalError: table tags already exists`） |
  | W3 补齐那一路漏掉 `stamp_head` | **红** 1 条（版本行是空的） |
  | W4 补齐那一路漏掉 `apply_schema_fixes` | **红** 1 条（表只建了一半） |
  | W5 `stamp` 与补齐调换先后 | **绿**——等价变异 |
  | W6 `engine.begin()` 换成 `engine.connect()` | **红** 4 条 |
  | W7 摘掉 `finally: await session.close()` | **绿**——等价变异，见下 |
  | W8 `async with` 换成裸 maker（保留 `close()`） | **绿**——等价变异 |
  | W9 两者一起摘（裸 maker、不收尾） | **红** 2 条（两条 `checkedout()`） |
  | W10 `finally` 里补一句自动 commit | **红** 1 条（未提交写那条） |

- **四格绿的各记了一句为什么**（写进 `backend/CLAUDE.md`，别当"已经钉住了"读）：
  - **W1 永远走补齐**：`create_all` 建出的表今天和基线一模一样，`stamp` 登记完也查不出来——差别只在"没跑修订"这件事上，而 `0001` / `0002` 目前都是纯 DDL，`create_all` 恰好能演出同样的结果。**将来出现带数据的修订时这一格就是盲区**，别把补齐那条路当成 `upgrade` 的安全替代品。
  - **W5 `stamp` 与补齐调换先后**：也钉不住。文档里那句"顺序要紧"说的是 `apply_schema_fixes` **内部**"先清洗再建唯一索引"，不是这两步之间。
  - **W7 / W8 收尾那一半各自都不承重**：`AsyncSession.__aexit__` 本来就会 `close()`，所以摘掉 `finally` 或摘掉 `async with` 都测不出区别，只有两个一起没（W9）连接才会留在池里。这一句 `close()` 是双保险，别在它上面加"依赖它才成立"的逻辑。
- **W6 才是这单最值钱的一格**：`async with engine.begin()` 换成 `.connect()` 之后 `upgrade_head` 自己跑得一切正常，而 DDL 全在那条不提交的事务里——出块整体回滚，库里表没了、版本行没了，**一句错都不报**，红的是下一个读的人（实测红 4 条，正是那四条启动路线）。这一句不是装饰。
- **顺带量到第 8 条钉不住的东西**：W9（完全不收尾）下它照样绿——闲置的那条连接不会把未提交的写送给另一个读者，所以那条用例钉的是"没提交的写不会跟着会话出去"（W10 一加自动 commit 就红），钉不住"事务被回滚"。这一条写进文档，不假装钉住了。
- **基线**：后端 PG 全量 **872 passed**（+8）、**182.53s**、TOTAL **94.93%**（4613 句 / 234 缺）；`src/database/session.py` 从 **88%** 到 **100%**。SQLite 分支 **871 passed + 1 skipped**（75.16s）。两句计时别跟上单比：上一单同一条命令记到 663.41s / 86.54s，这一轮同时短了三倍和十几秒，波动原因没查实，别读成提速。`ruff check tests src` → All checks passed；`mypy src` 仍是那 **34** 条基线（复量过，不是新增）。前端一层没动：这一单只加后端用例，`openapi.json`、路由表和前端谁也没碰。
- **文档**：`backend/CLAUDE.md`「数据库迁移」那节三条路线后面新增一段，把上面几件实测性质写全（`begin()` 不是装饰 / 认错方向只有一头能红 / 会话收尾要拆两个变量看 / 第 8 条钉不住回滚），目录树里 `test_migrations.py` 的说明改成"Alembic 的零件……不经过 `init_db`"并补上新文件那一行；薄位置清单补上 `session.py` 这一格。
## 2026-10-08
### 导出接口表的那六行从前一次也没被执行过：写出去的那份文件必须能被同一份代码认回来（#170）

- **症状**：`src/export_openapi.py` 在 PG 全量读数里是 **77.78%**，缺 `39, 42-43, 71-76` 六行。缺的不是某条分支，是**这个模块自己干活的那一路**：`matches()` 里"读不出一个 schema"的三支（文件还没生成、那条路径是个目录、内容不是 JSON）和 `main()` 不带 `--check` 时写盘的那一整段，从 pytest 进来一次也没被执行过。这份文件是前端契约测试的对照表，而"写"和"核对"两头各自的判断是否同一份，此前零钉子——不一致时红的是快照，不是调用方，而调用方在前端另一种语言里。
- **三件实测事实**（都从代码读不出来，只能量）：
  - 导出确实离线：把 `DATABASE_URL` 指到 `127.0.0.1:1` 出的那份与提交的那份**逐字节相同**（md5 `e585d6dc4a5bc10c08c174dfd6f42f27`）。
  - `--out` 指到一个目录时 `exists()` 是真的，读它抛的要害在**两支方言不同名**：Windows 上是 `PermissionError`（errno 13），POSIX 上是 `IsADirectoryError`——同属 `OSError`，所以用例只断"算不一致"，不把 errno 写进断言。
  - 快照今天是 **66 条路径 / 85 个操作 / 5677 行**，而 `README.md:106` 和这个模块自己的 docstring 还写着"65 条路径"——同一份改动留下的两处腐烂文档，一并改齐（数字来自刚跑完的那份文件，不是我按着的）。
- **回归用例**：`tests/test_openapi_snapshot.py` **3 → 9** 条。新增的六条钉的是：文件还没生成时 `--check` 要说不一致（新克隆在第一次导出之前正是这个状态，把"读不到"演成"一致"是最省事的假绿）；路径是目录时也算不一致；内容不是 JSON 时也算不一致（半截写入、或被某个补丁工具换成冲突标记）；导出那一路写出的字节里**一个 `\r` 都没有**、解析后与 `render()` 逐字相等、写完立刻 `matches()` 为真（写的人和核对的人用的是同一份判断）；同一份 schema 换个缩进、换个键序写出去时 `--check` 必须闭嘴（比的是对象不是字节，反过来的话"谁顺手跑了个格式化"就变成一次假的不一致）；打印那句里的路径条数必须来自刚写出去的那份文件（数字不写死进断言——写死就等于又造一处会腐烂的文档）。
- **红在先（这一单没有可复的先红，说清楚）**：#170 没改 `src/` 一行行为（只有 docstring 里那两个数字），所以不存在"对着修改前的 HEAD 先跑红一次"——新用例在旧代码上直接是绿的。能红的是变异电池：**8 格里 7 红 1 绿**，那 1 绿是实测出来的等价变异，不是漏钉。
- **变异**（一次一个变量；每轮**先断言替换锚点在文件里恰好命中一次、替换后字节确实变了**，才允许把这一格叫绿——这一条是 #169 学来的，上一版那次假绿就是替换没落地；跑完按字节复位并核 md5 `1def3161e874719c00efe78c162030d4`，与快照一致）：

  | 变异 | 结果 |
  | --- | --- |
  | V1 摘掉 `if not output.exists(): return False` | **绿**——等价变异，见下 |
  | V2 `except` 收窄成只接 `OSError`（坏 JSON 从此炸回溯） | **红** 1 条 |
  | V3 `except` 收窄成只接 `JSONDecodeError`（目录那条路径从此炸回溯） | **红** 1 条 |
  | V4 `matches()` 直接返回 `True` | **红** 1 条 |
  | V5 写盘丢掉 `newline="\n"`（Windows 上落成 CRLF） | **红** 1 条 |
  | V6 改成拿原始字符串比而不是解析后比 | **红** 1 条 |
  | V7 打印的条数从"路径数"换成"操作数" | **红** 1 条 |
  | V8 `if args.check:` 反过来（`--check` 变成写盘） | **红** 4 条 |

- **V1 为什么是等价变异（实测，不是推理）**：摘掉前置闸门后，读一个不存在的文件抛的是 `FileNotFoundError`，而它本身就是 `OSError` 的子类，被同一个 `except` 接住、照样返回 `False`——**没有任何可观察行为差别**，所以任何单变量改动都照不红它。这一行只是把语义写明白，别把它当守卫信任，也别在它上面加"依赖它才成立"的逻辑；已经写进 `backend/CLAUDE.md`。
- **顺带重量了文档里那句"删一条路径会红几条"**（#122 时代写的是"3 条用例红 2 条"）：从提交文件里删掉 `/api/auth/sessions` 整条路径 → **2 failed, 7 passed**。红的还是那两条（逐键比对那条、`--check` 与快照同进同退那条），另外 7 条不看提交文件所以照绿——这条也更新进文档，用例数变了而红数没变，不是巧合：那 7 条钉的是这个模块自己的行为。
- **基线**：后端 PG 全量 **864 passed**（+6）、**663.41s**、TOTAL **94.73%**（4613 句 / 243 缺）；`src/export_openapi.py` 从 **77.78%** 到 **100%**。SQLite 分支 **863 passed + 1 skipped**（86.54s）。`ruff check tests src` → All checks passed；`mypy src` 仍是那 **34** 条基线（复量过，不是新增）。前端一层没动：Vitest 350、替身 e2e 100、`openapi.json` 66 条路径 / 85 个操作 / 5677 行都不变——这一单只加了后端用例，路由表和前端谁也没碰。
- **文档**：`backend/CLAUDE.md`「OpenAPI 快照」一节新增两条——"写的人和核对的人用的是同一份判断"（LF 写盘、只比解析后的对象、三种读不出都算不一致、打印条数来自文件本身）和"`exists()` 那一句不是守卫"（等价变异实测），并把"删一条路径红几条"从 3 条改成 9 条；薄位置清单补上 `export_openapi.py` 这一格。`README.md:106` 和 `src/export_openapi.py` 的 docstring 里那两个路径数改齐到 66 / 85。
### 转码那条命令从前在 pytest 里一次也没被执行过：ffmpeg 的配方、进度读法、失败原因和取消收尾第一次有钉子（#169）

- **症状**：`src/utils/ffmpeg.py` 在全量读数里是 **23%**（71 句缺 55 行：`26-30, 35-56, 72-141, 151`）。这一格不是"某条分支没测到"——是**整个 `transcode_video` 从 pytest 进来一次也没被调用过**：服务层用例把它整个换成替身，真 ffmpeg 又只在**另一个进程**里跑（`frontend/e2e/real/`），那份执行永远不进这份读数。于是四件事在 pytest 这一侧零钉子：发给 ffmpeg 的那条命令行长什么样、`-progress` 读回来的行怎么解释、失败时那句原因从哪儿来、取消时谁去收那个半截文件。
- **这一层签哪一头**：真产物那四行配方早由 **4** 条真后端 e2e 从**结果**那一头签过字（第 15 条真 FFmpeg 写真文件、`ffprobe` 核对产物里那两条流正是配方里那一对编码器；第 16 条让 ffmpeg 真失败一次；第 17 条杀的是真子进程；第 25 条把 mp4 那格的 `-c:a aac` 也签了）。这一层钉的是**发出请求**那一头：命令行的形状和读回来的解释。两层对着同一个约定，任何一头自己改了不通知对方都会红——只有其中一头的服务是不能签这一单的，因为真 ffmpeg 那份执行不进 pytest 的读数，而假子进程那一份又碰不到真磁盘上的容器。
- **回归用例**：新增 `tests/test_utils/test_ffmpeg_encode_recipe.py` **14** 条。假子进程是把 `asyncio.create_subprocess_exec` 换成"按脚本逐行喂 `stdout`"的替身，于是那一段真代码（读循环、解析、闸门、异常收尾）第一次被执行。覆盖的是：argv **逐字**对表（四个容器各配哪一对编码器、`-y`、`-progress pipe:1`，加上 `stdout=PIPE` / `stderr=STDOUT`——两处各一个缓冲时 ffmpeg 会在写满 stderr 上卡死）；`webm` 那格单独钉 `libopus`（`-c:a aac` 在 webm 里是 ffmpeg **直接拒绝**的配方，不是"效果差点"）；`out_time=` 变百分比并封顶（10 秒/100 秒 → 10.0，90 秒 → 90.0，5 分钟 → 100.0 而不是 300.0）；没有分母、没人听、两者都没有这三种情况下不许炸；认不出的时间戳只丢那一格而任务照常跑完；`out_time_ms` / `out_time_us` 那两个微秒键**不许驱动进度条**；失败那句给的是 ffmpeg 自己的诊断行，而机器可读的 `frame=` / `bitrate=` / `progress=` 一行都不许混进去；什么诊断都没给时只许说退出码（`ffmpeg exited with code 134`），不许编造原因；格式不认识时**一个进程都不许起**；`PATH` 上没有 ffmpeg 时说得出人话而不是回溯；管道中途断了要说得出原因且 kill 完必须 reap；取消那一路 kill + reap + 半截产物 `unlink`（文件压根不在盘上时也不能变成一次失败）+ `CancelledError` 原样抛上去。
- **`get_video_info`（`35-56`）故意留白**：全仓 `grep` 只有它自己的定义和一份 2026-07-27 的计划文档，**没有任何调用方**。给死代码写用例只会让它看起来是活的，所以这一文件停在 **89%** 而不是 100%；"删掉还是留着"记进待用户定夺。剩下那 8 行就是它——这一文件的百分比到不了顶，不是还漏了一条分支。
- **红在先（这一单没有可复的先红，说清楚）**：#169 没改 `src/` 一行，它补的是盲区，所以不存在"对着修改前的 HEAD 先跑红一次"这件事——新用例在旧代码上直接是绿的。能红的是变异电池：**10 格里 9 红 1 绿**，而那 1 绿是实测出来的**等价变异**，不是漏钉。
- **变异**（一次一个变量；每轮**先断言替换锚点在文件里恰好命中一次、替换后字节确实变了**，才允许跑测试——这一条是这单学到的：上一版 U3 那次"绿"其实是替换没落地；跑完按字节复位并核 md5 `b18c9b52ea37948c59c63a576ac1e7be`，与快照一致）：

  | 变异 | 结果 |
  | --- | --- |
  | U3a `if done is not None:` 摘掉（认不出的时间戳照样进回调） | **红** 1 条（`None / 60.0` 先把整趟变成一次失败，判据仍然在这条上） |
  | U3b `if total_duration and on_progress` 那道闸摘掉 | **红** 6 条 |
  | U3c 封顶那一步 `min(..., 100.0)` 摘掉 | **红** 1 条 |
  | U3d `startswith("out_time=")` 放宽成 `startswith("out_time")` | **绿**——等价变异，见下 |
  | U3e `_PROGRESS_KEY` 改成匹配每一行（诊断行全被当进度丢掉） | **红** 1 条 |
  | U3f 没有诊断行时那句退出码兜底删掉 | **红** 1 条 |
  | U3g 取消时不再 `unlink` 半截产物 | **红** 1 条 |
  | U3h 取消时不再 `kill` | **红** 1 条 |
  | U3i 管道异常时不再 kill、不再 reap | **红** 1 条 |
  | U3j 不认识格式那道闸摘掉（fallback 到 mp4 的配方） | **红** 1 条 |

- **U3d 为什么是等价变异（实测，不是推理）**：只放宽前缀时 `out_time_ms=10000000` 会被送去解析，而 `_parse_ffmpeg_time("10000000")` 按 `HH:MM:SS` 拆不出三段、返回 `None`，那一行于是被丢掉——和它原本落进 `elif not _PROGRESS_KEY.match(line)` 后因键名匹配同样被丢掉，**可观察行为完全一样**，所以任何单变量改动都照不红它。要红得同时动两处：实测把前缀放宽**和**给解析器加一支"裸数字按微秒算"一起上，进度那两条立刻**红 2 条**（`14 passed` → `2 failed, 12 passed`）。新加的那条「微秒键不许驱动进度条」钉的就是这个组合——今天它随解析器一起安全，将来谁单独动了哪一支都会先红在这里。
- **基线**：后端 PG 全量 **858 passed**（+14）、2 warnings（`test_db_transfer.py` 那两条既有的 `ResourceWarning`）、**684.04s**、TOTAL **94.56%**（4613 句 / 251 缺；上一格是 844 passed、93.54% / 298 缺）；`src/utils/ffmpeg.py` 现在是 **71 句 8 缺 = 89%**，缺的正是 `35-56` 那一段死代码。SQLite 分支 **857 passed + 1 skipped**（+14，89.62s；上一格 843 + 1 skip）。`ruff check tests src` → All checks passed（`Temp/` 里那两个一次性变异脚本自己带 4 条 ruff 报错，跑完就删，不进仓库）；`mypy src` 仍是那 **34** 条基线（`ffmpeg.py:125` / `:139` 两条本就在里面，不是新增）。前端一层没动：Vitest 350、替身 e2e 100、`openapi.json` 66 条路径 / 85 个操作都不变——这一单一行 `src/` 和一行 `frontend/` 都没改，那条路由表读不出新东西，真后端 e2e 那四条"结果那一头"的签收也就无从被我动坏。
- **文档**：`backend/CLAUDE.md` 薄位置清单里 `utils/ffmpeg.py` 那一格从「23%、桩不出真形状没有意义」改写成「23% → 89%：这一层签请求、那四条真 e2e 签结果」，并写清剩下那 8 行是 `get_video_info` 死代码、别把百分比顶不到 100% 当成还有分支没测。

### 产物从前只活在进程那本账上：转码落进独立目录，并第一次有了一张自己的表（#154）

- **症状**：转码成功后，产物写的是 `Path(input_path).with_suffix(".mkv")`——也就是**源的旁边**。而那个目录正是扫描范围（`file_scanner.scan_directory` 只看 `VideoSource.path`，`os.walk` 一路下潜、**没有排除机制**）。于是下一轮定时扫描把 `movie.mkv` 当成一部新片子登记进库，界面上同一部片子的两份并排出现，产物那份还能再转一遍。这一路**测试里一次也没红过**：`_jobs` 是进程内的字典，用例的会话就是服务的会话，"重启后什么都没人记得"和"产物会变成一部新片子"都不在旧用例的射程内。
- **修法（用户选的是甲 + 表里可逻辑删除）**：`TRANSCODE_OUTPUT_DIR`（默认 `./data/transcode`，和封面/备份一起进 `_anchor_under_backend` 那个名单——那串路径**会写进库**，换个工作目录启动就读不到自己昨天产的那一份了），新函数 `product_path()` 按 **`<输出目录>/<影片 id>/<源文件名去扩展>.<格式>`** 布局落盘，`output.parent.mkdir(parents=True, exist_ok=True)` 在 `transcode()` 里做而不是在 ffmpeg 里做（那一步失败会以"转码失败"的面目出现在界面上，而真实原因是没地方写）。按影片 id 分子目录挡的是平铺布局下两个片源的**同名片子互相覆盖**——ffmpeg 带 `-y`，覆盖是静默发生的。
- **闸门留着，理由换了一个**：同格式目标从前被拒是因为"会覆盖原文件"，输出目录独立之后不会覆盖了，但它让**产物和源同名**：库里的 `movie.mkv` 和产物表里的 `movie.mkv` 在人眼里是同一行，而这一单买的就是"产物看得见"。所以判据从"比两个路径"改成"比源扩展名"（`Path(input_path).suffix.lower().lstrip(".") == target_format`），错误文案同步改写成 `the product would have the same filename as the original`。
- **新表 `transcode_outputs`（迁移 `0002`）**：一行说的是"这一部的这一种容器产出过一份，文件在哪儿"。`UniqueConstraint(video_id, target_format)` + `(video_id, target_format)` 索引 + `ForeignKey(videos.id, ondelete="CASCADE")`；两张时间列用 `UTCDateTime`（#162 那个类型），迁移脚本写的是 `sa.DateTime(timezone=True)`——`impl` 就是它，两种方言 DDL 逐字节相同，形状由 `test_utc_datetime_columns.py` 的结构哨兵对着元数据核（**21 → 23 处声明**）。`_record_output()` **只在成功那一路调用**：失败的产物压根不存在，取消那一路 ffmpeg 已经把半截文件 unlink 掉了，写进表一条"存在过、其实没有"的行正是这一单要修掉的那种谎；重做同一种容器是这一行被更新，不是多出一行。
- **`deleted_at` 由读时那一次 stat 写（用户选的乙′）**：`list_outputs()` 是这一列**唯一的写的人**，而且**两个方向都核对**——文件没了就盖上时刻，被放回去（误删后恢复、换盘）就清掉，否则这一列从漏报变成误报，一样是谎；`if changed: commit()` 把发现落库，下一次读不用重新发现。`size_bytes` 是**当场** `stat()` 出来的、不写进表，因为库里那份会说谎。为什么只有这一处能写：产物目录在任何片源之外，扫描永远走不到它。
- **接口与前端**：新增 `GET /api/transcode/{video_id}/outputs` → `list[TranscodeProductResponse{id, target_format, output_path, size_bytes, created_at, deleted_at}]`；没转过的片子回 **200 + 空表**而不是 404（前端拿它渲染一行都没有的表格），片子被删了行也随级联走。`openapi.json` 重导：**66 条路径 / 85 个操作 / 5677 行**。`Transcode.vue` 多一张「转码产物」表（文件名、大小、去处、时间，`size_bytes === null` 显示 `—` 并标**已不在**、行不隐藏），轮询到 `completed` 那一刻**重读一次产物**（那一行是任务成功时才写进去的，不重读就得刷新页面才看得到），`fetchProducts` 失败要说清原因——"表里一行都不显示"和"这部片子没转过码"在界面上是同一个样子。
- **真后端 e2e 的接线**：`real/env.ts` 把 `TRANSCODE_OUTPUT_DIR` 指到 `backend/data/e2e/transcode`，`e2e_seed.prepare_media()` 只 rmtree 媒体目录**不动产物目录**，所以规格自己收尾（`transcode_support.ts` 新增 `productDir/productPath/readProducts`，`expectRealOutput` 现在断的是**精确路径**而不是"在源旁边"）。
- **回归用例**：后端 **+15** 条——新增 `tests/test_api/test_transcode_products.py` **7** 条（空表 200、字段集合逐字对、`size_bytes == 5` 是当场读的、只列这一部的、新做的在前、**盘上没了要报并且 `refresh` 证明那句写真的落库**、POST→后台任务→GET 全程走 HTTP 钉住"登记用模块级会话、读用请求会话，必须落在同一个库里"、未知影片 200 + 空表），`test_transcode_service.py` **+7** 条（产物不许变成库里的行、进程忘了之后产物仍已知、失败/取消都不登记、重做同容器只更新那一行、手工删掉要标回来且放回去要清掉），`test_config.py` **+1** 条（相对的 `TRANSCODE_OUTPUT_DIR` 按 `backend/` 展开——这一条是变异 M11 逼出来的：真改代码时只核了封面那条锚定用例，没核这一半）。前端 Vitest **+5** 条（345 → **350**）；替身 e2e 条数不变（100）但 `transcode.spec.ts` 加了 `.products-section` 那组断言，夹具补 `/transcode/{id}/outputs` 处理器；真后端 e2e 转码那一对 **4** 条改到新布局。
- **红在先**：写实现之前先把三个行为侧文件按 `git show HEAD:` 复位（`services/transcode_service.py`、`api/transcode.py`、`config.py`），跑这两个测试文件 → **7 failed + 17 errors**：API 那 7 条红的是 `{'detail': 'Not Found'}`（`GET …/outputs` 这条地址还不存在），服务层那 17 条在夹具 setup 就红（`module 'src.services.transcode_service' has no attribute 'settings'`——独立输出目录这个键还没有）。跑完按字节复位并核 md5（`4bd397b8…` / `67227a9d…` / `476d9733…` 三个全与快照一致），复位后同一条命令 → **32 passed**。**#154 的症状本身（产物被扫成库里的第二行）在这份复位上看不见**——复位把"往哪儿写"也一起复掉了；那一句是变异 M1 单独摆出来的：只把 `product_path` 退回 `with_suffix`、其余实现留着，后端红 3 条、真后端 e2e 红 4 条。前端那三条静态守卫同样是先看它们红才补的夹具处理器（见 F1/F2）。
- **变异**（一次一个变量；每轮从 `/tmp/mut154` 的快照**按字节**复位再改一处，跑完核 md5；六个被改文件复位后的 md5 全部与快照一致，`transcode_service.py 4bd397b8…`、`config.py 476d9733…`、`video_service.py a8bdf051…`、`models/transcode_output.py c67d2df2…`、`src/api/transcode.ts 98dfd55c…`、`e2e/fixtures.ts d875e17f…`）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 `product_path` 退回 `with_suffix`（产物写回源旁边） | **红** 3 条；真后端 e2e **4 条全红**（一条红在产物路径那一句，三条红在扫描计数那一句） |
  | M2 去掉 `output.parent.mkdir(...)` | **红** 5 条 |
  | M3 成功分支不再 `_record_output` | **红** 4 条 |
  | M4 读时核对整段删掉（`deleted_at` 从此没人写） | **红** 2 条 |
  | M5 只标"没了"、不往回翻 | **红** 1 条 |
  | M6 `size_bytes` 从表里的标记推出来，不当场 stat | **红** 5 条 |
  | M7 闸门退回"比路径"而不是"比源扩展名" | **红** 1 条（同格式那条拒绝没了） |
  | M8 布局平铺（去掉 `<video_id>/` 那一格） | **红** 2 条 |
  | M9 登记改成总是 INSERT（不 upsert） | **红** 1 条，且撞的就是那个唯一约束 |
  | M10 排序退成正序 | **红** 1 条 |
  | M11 `transcode_output_dir` 从锚定 validator 名单里摘掉 | **红** 1 条（新加的那条配置用例） |
  | M12 产物表没登记进 `VIDEO_CHILD_TABLES` | **红** 1 条（那条结构守卫） |
  | M13 两张时间列退回裸 `DateTime(timezone=True)` | **红** 1 条（#162 的结构哨兵 23 处） |
  | F1 前端地址段写错（`/outputs` → `/output`） | **红** 2 条：openapi 契约钉子 + 替身覆盖钉子 |
  | F2 替身夹具里那条处理器摘掉 | **红** 1 条 Vitest 守卫 + 3 条替身 e2e 断言 |

  **十五项全部能红，没有"拆不红"的格子。**M1 是唯一一条同时打到两层的：后端红 3 条，真后端 e2e 那 4 条全红——而且红的正是"#154 的签名"那两句（产物落在哪、扫描计数不许多出一行）。
- **基线**：**844 passed**（真库 PG；#162 是 829，差额正好是新增的 15 条）／TOTAL **93.54%**（4613 句、缺 298）／`src/services/transcode_service.py` **89%**（缺的那 14 行是 `_notify` 那一段和异常路径——通知写失败不该让转码本身失败，这一向是刻意留白）／**SQLite 分支 843 passed, 1 skipped in 89.95s**（跳过的那条是 PG 专属）／ruff 干净、`mypy src` 仍是那 **34** 项基线（这一单动了 `src/` 五个文件，没新增一项）／前端 `typecheck:test` 干净、Vitest **350**、替身 e2e **100**、`npm run build` 通过、真后端 e2e 转码那一对 **4 passed**（36.7s，跑的时候没有并行的 pytest）。
- **文档**：`backend/.env.example`、`README.md`、根 `CLAUDE.md`、`backend/CLAUDE.md`（新增「转码产物落盘（#154）」一节 8 条 + `VIDEO_CHILD_TABLES` 清单补上 `transcode_outputs`）、`frontend/CLAUDE.md`、`frontend/e2e/real/*`。
- **已知未修（下一单，#168）**：**删影片会带走产物行，但带不走产物文件**。级联（`ondelete="CASCADE"`）删的是行，磁盘上那份 `<输出目录>/<video_id>/x.mkv` 留在原地，而扫描永远走不到那儿去——所以它既不报错也没有任何人会再提起，是纯粹的字节泄漏。这一处 `backend/CLAUDE.md` 里也明写了「已知未修」，处置方案（删行时按 `output_path` 逐个 unlink、失败只记日志，照 #75 封面那一路的形状）等用户定夺。

### 那 21 处时间列从此只有一种形状：SQLite 分支上 10 条「我的设备」红第一次有人接住（#162）

- **症状**：只在测试分支上。`TEST_DATABASE_URL= pytest` 走的是内存 SQLite，本机自 10-04 起主线连的是 PG，这条路很久没人跑——#161 为了确认外键改动没弄坏什么跑了一趟，量到 `10 failed, 772 passed, 1 skipped`，全在「我的设备」和用户管理那一带，异常一律是 `TypeError: can't compare offset-naive and offset-aware datetimes`，回溯落在 `sqlalchemy/orm/evaluator.py:263`。**单独立刻能复现的最小一条**：`TEST_DATABASE_URL= .venv/Scripts/pytest.exe -q tests/test_api/test_auth.py` → **6 failed, 17 passed**。
- **病灶**：`auth_service.py:179-183` 那句 `delete(UserSession).where(..., UserSession.expires_at <= _utc_now())` 是 **ORM 启用的批量删除**——SQLAlchemy 执行完 SQL 还要**在 Python 里**按同一条 WHERE 重新评估 `identity_map` 里已加载的对象，好把被删的行从内存里摘掉。SQLite 的 `DATETIME` 不存偏移，读回来的 `expires_at` 是 naive，`naive <= aware` 当场抛；PG 的 `TIMESTAMP WITH TIME ZONE` 永远带偏移，所以主线一次也没红过。而 `list_sessions` 第一件事就是这句清理，于是**整页 500**，不是"结果差一点"。CLAUDE.md 从前只在**写入侧**防这件事（一律 `datetime.now(timezone.utc)`），读回侧没有闸门。
- **修法（用户选的是乙）**：新增 `src/database/types.py` 里的 `UTCDateTime`——一个 `TypeDecorator`，`impl = DateTime(timezone=True)`，`process_result_value` 就是现成的 `src/utils/time.as_utc()`；全部 **21 处**声明（13 个模型文件）换成它。选它而不是选"在调用点包一层"的两个理由：① 以后新建的列**默认就是对的形状**，不需要作者记得再包一次；② 调用点补丁只能钉住现在这一处病灶，下一句比较时间的批量 DML 照样炸。`impl` 保住 DDL，**两种方言编译出来逐字节不变**（第三条用例逐列对 PG 和 SQLite 各核一遍），所以**不需要 Alembic 迁移**，真库上的行一个也没动。
- **连带必须改的一处（差点变成静默失效）**：`TypeDecorator` 的实例**不是** `DateTime` 的实例（实测），所以 `isinstance(col.type, DateTime)` 从此一律为假。`db_audit.py` 有三处这样的判断（违规类型闸门、`canonical_value`、孤儿/范围扫描），不改的话审计会**悄悄地不再报时间列和字符串列的问题**——不红，只是什么都不说。三处统一走新的 `is_datetime_column()`（它剥 `.impl`）。这一条是 M4 钉住的。
- **回归用例**：新增 `tests/test_utc_datetime_columns.py`，**3 条**，自建内存 SQLite 引擎（不吃 `db_session`，本机主线是 PG，跟着方言走会绿得什么都没钉住）。① 存进去的时刻读回来必须带 `tzinfo`、且与写入同一时刻，NULL 仍是 `None`（不许变成零点）；② **真调用点**：两个会话摆出"从库里读回来"的形状后走 `AuthService.list_sessions`，过期那一行必须真的从库里没了；③ 结构钉子——`Base.metadata` 里每一列时间戳都必须是 `UTCDateTime`，且两种方言的 DDL 与 `DateTime(timezone=True)` 逐字相等，`len(columns) == 21` 是防"遍历本身是空的"那个哨兵。
- **三条测量出来的踩坑路（都记进了 CLAUDE.md §3，因为前两条是假绿）**：同一会话里 `add` 完就删 → **绿**（新对象带的是 Python 侧那个 aware 值）；只 `await s.scalars(...)` 不 `.all()` → **绿**（identity map 是空的，评估器没有对象可跑）；`expire_all()` 再读 → 红在 `MissingGreenlet`（本机的同步惰性加载，不是这一单的病灶）。只有**第二个会话 + `.all()` 把行消费掉**这一条会真的咬人。
- **变异**（一次一个变量；每轮跑 `TEST_DATABASE_URL= pytest -q` 于三个文件（新文件 + `test_api/test_auth.py` + `test_db_audit.py`），跑完按字节复位并核 md5，再对 `git diff HEAD --stat` 的 md5；绿基线 **43 passed**）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 删掉 `process_result_value`（`UTCDateTime` 退化成一个空标记） | **红** 7 条 |
  | M2 只把 `UserSession.expires_at` 一列摘回裸 `DateTime` | **红** 8 条（结构钉子也抓到） |
  | M3 去掉 `process_result_value` 里的 NULL 分支 | **红** 19 条（NULL 当场 `AttributeError`） |
  | M4 `is_datetime_column` 不剥 `.impl` | **红** 3 条：`test_detects_bad_datetime`、`test_bool_and_text_timestamps_canonicalise_alike`、结构钉子 |
  | M5 读侧原样返回方言给的值（不 `as_utc`） | **红** 7 条 |

  五项**全部能红**，没有"拆不红"的格子。M5 我原本预计会绿（SQLite 本来就给 naive，似乎无从分辨），实际红在①那条形状断言上——`assert tzinfo is not None` 钉的正是"方言给什么不重要"。
- **文档**：`backend/CLAUDE.md` 四处——§1 的建模型模板、PostgreSQL 那条要点（换成"用 `UTCDateTime()`，`impl` 保住 DDL 所以无需迁移"+"任何检查 `col.type` 的地方必须走 `is_datetime_column()`，因为 `TypeDecorator` 不是 `DateTime`"）、模型定义片段、§3 时区处理整段重写（含上面那三条踩坑路）。
- **基线**：**829 passed, 0 failed, 2 warnings**（真库 PG；上一单 826，差额正好是新增的 3 条）／TOTAL **93.49%**（#167 是 93.45%，miss 仍是 296，涨的一点来自 `src/database/types.py` 那 13 行**全覆盖**）／ruff 干净，`mypy src` 仍是那 **34** 项基线（这一单确实改了 `src/`：14 个文件，但没有新增一项，`types.py` 单独跑是 `Success: no issues found`）。**这一单真正的奖品在另一条跑法上**：`TEST_DATABASE_URL= pytest -q tests/` → **828 passed, 1 skipped in 90.22s**，也就是 #161 量到的那 10 条红全部消失——文档里写的回滚方言（SQLite）从此整套跑得通，不再是"名义上支持"。前端三种测试未涉及（这一单没动 `frontend/`）。

### 服务重启之后到底武装了什么：启动那 23 行第一次真的被执行过一次（#167）

- **症状**：表面上没有，而且这一格的"装错了"恰好是唯一一种**界面上看不出来**的错——少一行 `scheduler.start()`，网站照常能开、能登录、能手动扫描，只是从此再没有一次定时扫描，也没有每晚那份 `pg_dump`。量出来的是 `src/main.py` **81%**，缺的整段是 `22-44` 那个 `lifespan`：建库、按表里**现存的**片源挂扫描任务、备份只在 PostgreSQL 上挂载、真的 `start()`、退出时真的 `stop()`。相邻的两份用例都不从这一个入口进来（`test_scheduler_source_lifecycle.py` 走 Service 那三条同步边，`test_scheduler_backup.py` 钉的是任务函数本身），所以"启动"这一步全量跑里一次也没被执行过——全量 819 条里 `22-44` 十二行全是缺的，这就是这一单成立的全部依据。
- **回归用例**：新增 `tests/test_app_boot_lifespan.py`，**7 条**。三件接线是这一单的全部难度：① 调度器用**一个记录挂载顺序的子类**替身（`BootScheduler`）打在 `src.main.scheduler` 上——绝不动进程级那个单例，否则一条用例的挂载会漏进下一条；② 会话是**借来的**（`_BorrowedSession`），lifespan 那句 `async with async_session_maker()` 要是真关掉连接，测试会话当场废掉；③ 三个任务函数（`scan_source_task` / `backup_database_task` / `backup_catchup_task`）换成只登记不干事的替身，**替身必须打在 `src.scheduler.tasks` 模块上**，因为 `scan_scheduler` 是在挂载那一刻从模块里取函数的。不放替身的代价是真机行为：启动补跑那一条挂的是 `DateTrigger()`，`start()` 之后立刻执行，真跑一趟就是往真盘上写一次 `pg_dump`；定时扫描那个用的又是**全局**会话，会连到 `settings.database_url` 上头去——也就是真库。钉住的形状：`init_db` 必须排在任何挂载之前（整条事件序列逐字相等）；每条**启用着的**片源按**自己那一行的**间隔挂上（`interval[0:01:00]` 与 `interval[0:30:00]` 同时出现，所以不是写死一个默认值），关着的那条不挂；备份闸门的两半各归各看着（SQLite 一个都不挂、开关关了不挂但扫描照挂）；挂载时刻来自配置而不是代码（`cron[hour='7', minute='15']`）；`is_running` 在 `async with` 里面为真、出来为假。
- **变异**（一次一个变量；每轮先把 `src/main.py` **整文件从快照按字节复位**再改一处，跑完核对 md5，最后 `git diff --exit-code HEAD -- src/` 为空；**这一单没改过 `src/` 的一行**；跑的是新文件——老用例抓不住任何一条，因为那十二行本来就没被执行过）：

  | 变异 | 结果 |
  | --- | --- |
  | P1 拔掉 `await init_db()` | **红** 4 条（事件序列缺了头一格） |
  | P2 查询不再过滤 `is_active == True` | **红** 1 条：关着的那条片源也挂上了任务 |
  | P3 间隔写死 3600 | **红** 2 条：两条 `interval[...]` 和事件序列 |
  | P4 备份闸门丢掉方言那一半（只看开关） | **红** 1 条：SQLite 上也挂出两个备份任务 |
  | P5 备份闸门丢掉开关那一半（只看方言） | **红** 4 条：关掉备份的机器上照样挂 |
  | P6 拔掉 `add_backup_catchup_job()` | **红** 1 条：启动补跑再也不挂，"四天没备份"重新变成无人知晓 |
  | P7 挂载时刻写死 `"04:15"` | **红** 1 条：cron 那格的字符串对不上，配置里的时刻从此说了不算 |
  | P8 拔掉 `scheduler.start()` | **红** 5 条：任务挂上了但一轮也不跑 |
  | P9 拔掉 `scheduler.stop()` | **红** 5 条：退出时不关调度器 |

  九项**全部能红**，没有"拆不红"的格子。
- **一处接线上的坑，记下来免得下一单重踩**：夹具默认把 `settings.backup_enabled` 关成 `False`。第一版没关，三条钉片源的用例直接红——真环境的 `backend/.env` 里备份是开着的、库是 PostgreSQL，于是启动路径顺手就挂上两个备份任务，把"这一轮武装了什么"的事件序列污染了。备份那一半由后面三条用例**各自显式摆好**闸门的两半，所以关掉默认值不损失任何一格。
- **文档**：`backend/CLAUDE.md` §5 薄位置清单加一条 `src/main.py` **81% → 100%**，写清三件接线和那条"绝不用 `httpx.ASGITransport` 就等于不跑 lifespan"的成因。
- **基线**：**826 passed, 0 failed, 2 warnings**（10:05；上一单 819，差额正好是新增的 7 条）／TOTAL **93.45%**（#166 是 93.18%，miss 308 → **296**，减掉的十二行正是 lifespan 那一段）／`src/main.py` 64 行 **0 缺 → 100%**；ruff 干净，`mypy src` 仍是那 **34** 项基线（这一单没动 `src/`）；前端三种测试未涉及。那 2 条 `ResourceWarning: unclosed database` 还是 `test_db_audit` / `test_db_transfer` 那一双，和 #163、#164、#165、#166 记的是同一对。

### 五连败之后那十分钟到底会不会自己解开：限流器到期那三行补上签字（#166）

- **症状**：表面上没有。`test_auth.py` 早就有一条"五次失败之后账号被锁住"，界面上登录页也真的会说「尝试过于频繁，请 N 秒后再试」。量出来的是 `src/services/auth_service.py` **99%**，缺的三行 `409-410, 416` 全在锁定的**下半句**上：`:408-410` 是"窗口走完把这一条从表里抹掉并放行"，`:414-416` 是"比窗口还慢的失败不该把人攒成永久锁定"。换句话说——**"会锁"有人钉，"会解开"一份证据都没有**。这一格在真机上不是学术问题：`LoginRateLimiter` 是进程内的，重启才清得掉，一个人要是输错五次之后发现"过十分钟也没放开"，手上没有任何办法自查。
- **回归用例**：新增 `tests/test_api/test_login_lockout_expiry.py`，**6 条**。时钟是假的：整模块 monkeypatch `auth_service._utc_now`，一步跳满一个窗口（真等 600 秒既跑不动也不确定）。① 窗口最后一秒仍锁、正好走完就放行（钉 `<=` 那个等号）；② 放行之后旧账必须抹掉，下一次失败从第一格重数（钉 `:409` 那次 `pop`）；③ 隔**整整**一个窗口的失败照样累加到锁定（钉 `:415` 那个严格 `>`）；④ 比窗口还慢的失败永远攒不出锁定（钉 `:416` 的重置）；⑤ 从接口进来：五连败 → 429 → 走完窗口 → 正解 200，**且紧接着两次错口令还得是 401**（只断"放开这一次"不够，旧计数没忘的话第二条立刻又 429）；⑥ `Retry-After` 跟着剩余秒数递减（`601 → 301`，钉的是 `int(left) + 1` 那个算式，而不是"大于 0"）。阈值全部从 `login_rate_limiter()` 现读，没写死 5 和 600。
- **变异**（一次一个变量，每轮**先把整个文件从快照复位**再改一处，跑完逐字节核对 md5，最后 `git diff --exit-code HEAD -- src/` 为空；**这一单没改过 `src/` 的一行**；跑的是新文件 + 原有 `test_auth.py`，二十几条老用例在六轮里一条没红，所以这一族此前确实无人看着）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 `left <= 0` → `left < 0`（正好走完那天不放行） | **红** 3 条：到期用例、抹账用例、接口那一条 |
  | M2 删掉 `self._failures.pop(key, None)`（到期不放行也不抹账） | **红** 1 条：抹账用例——窗口走完之后再错一次就是第 6 格，等于锁从来不解开 |
  | M3 删掉那条 `return 0`（走到下面的 `int(left) + 1`） | **红** 3 条：`left` 在到期时是 `0`，`int(0)+1 == 1` 是真值，账号被永久锁死 |
  | M4 `return int(left) + 1` → 恒等于整个窗口 | **红** 1 条：`Retry-After` 那一条，横幅上的秒数再也不往下走 |
  | M5 删掉 `elapsed > lockout_seconds` 那整段重置 | **红** 1 条：慢猜测者用例——每 601 秒猜一次，第八次照样被锁 |
  | M6 重置条件 `>` → `>=` | **红** 1 条：整窗口间隔用例——隔整整一个窗口本该累加，翻成 `>=` 就永远清零，锁再也落不下去 |

- **一处今天拆不红，写在用例里而不是假装钉住**：接口那一层的"慢猜测者"（每 601 秒错一次）拆不红——**临时探针实测过**（两条接口层的用例挂在同一份变异上各跑一轮，M2、M5 下都是 `2 passed`，探针文件跑完即删）：路由每次都先问 `locked_for`，`:409` 的 pop 会先把旧账抹掉，就算删了 pop，`:416` 的重置还在。所以 `:416` 只能钉在计数器那一层（`record_failure` 之间不读锁），M5 就是那样红的；这两道守卫是刻意重叠的。
- **文档**：`backend/CLAUDE.md` §5 薄位置清单里 `auth_service.py` 那条从"99%，剩限流器"改写成"99% → **100%**"，并把三条改前值得知道的性质写进去（两道守卫重叠所以接口层拆不红、两处边界各差一个等号是有意选的、`return 0` 删不掉的原因）；上一单那句"另开一单"这一单收掉了。
- **基线**：**819 passed, 0 failed, 2 warnings**（10:12；上一单 813，差额正好是新增的 6 条）／TOTAL **93.18%**（#165 是 93.12%，miss 311 → **308**，减掉的三行正是 `409 / 410 / 416`）／`src/services/auth_service.py` 207 行 **0 缺 → 100%**；ruff 干净，`mypy src` 仍是那 **34** 项基线（这一单没动 `src/`）；前端三种测试未涉及。那 2 条 `ResourceWarning: unclosed database` 还是 `test_db_audit` / `test_db_transfer` 那一双，和 #163、#164、#165 记的是同一对。

### 用户管理那五道写闸门，有四道从来没被真请求敲过（#165）

- **症状**：表面上没有——界面上建号、改角色、停用、重置、踢下线五条写路径都有用例，真后端 e2e 第 26 条也在四个浏览器之间来回点过。量出来的是两处"做了但没人核对拒绝那一侧"：`src/api/users.py` **94%**，缺 `137, 155-156, 172-173`；`src/services/auth_service.py` **97%**，缺 `143, 234, 314, 409-410, 416`。翻译成人话：往角色框里填一个不存在的角色会得到什么、管理员把人家的口令重置成弱口令会得到什么、降级别人的时候那台浏览器到底还登不登得进来、以及"账号已停用"这件事在会话解析那一头到底有没有人把关——四件事一份证据都没有。
- **回归用例**：新增 `tests/test_api/test_admin_write_gates.py`，**8 条**。① 建号 `role="wizard"` → 400 且 detail **整句**等于「角色只能是 owner/member」，同时库里没有这个人；② 改角色同理，另加"被拒的那一次不留任何痕迹"（角色仍是 member、他那台浏览器的会话行还在、请求照旧 200）；③④ 管理员重置口令的两道强度闸门从**这一头**敲进去（`short` → 「密码至少 8 位」，25 个汉字 → 「密码过长（上限 72 字节）」），钉的是路由那两行 `except ValueError → 400`：#163 已经钉过建号与自助改密那两个调用方，管理员重置是第三个；⑤ 降级别人 → `signed_in_devices` 归零、他的 Cookie 当场 401；⑥ 降级自己 → 那一枚会话被留着（`signed_in_devices` 仍是 1，`/api/videos` 还 200，只有管理面对他关成 403——401 才是"被踢下线"）；⑦ 升级别人 → 他的浏览器一根毛都不动；⑧ **绕过接口**把 `is_active` 写假之后，那台仍活着的浏览器得到 401，且断言 sessions 那一行**还在**——否则这条 401 会被误读成"会话被删了"，`auth_service.py:143` 这一道闸门就白钉了。
- **`users.py:155-156` 按构造不可达，只记不拆**：那是 `update_status` 里的 `except ValueError → 400`，而 `set_active` 唯一会抛的分支是「除他之外没有别的可用管理员」。走路由时 actor 必然是一个可用的 owner（中间件按 `is_active` 把关，正是上面第⑧条），而 `user.id == actor.id` 的停用在更早一句就被「不能停用自己的账号」挡掉了——所以 actor 自己就是"除他之外的那个"，那句 raise 从接口进不来。它是给未来少一层前置检查时留的兜底。同理 `auth_service.py:143` 的前半句（`user is None`）也造不出来：`sessions.user_id` 声明的是 `ON DELETE CASCADE`。
- **变异**（一次一个变量；每轮**两个文件都先从快照复位**再改一处，跑完逐文件核对 md5，最后 `git diff --exit-code HEAD -- src/` 为空；**这一单没改过 `src/` 的一行**）：

  | 变异 | 结果 |
  | --- | --- |
  | N1 `auth_service.py:234` 建号角色闸门 `raise` → `pass` | **红** 1 条：`role="wizard"` 一路写到库里，撞 `ck_users_role`，`IntegrityError` 变成 500 |
  | N2 `:314` 改角色那道 `raise` → `pass` | **红** 1 条：同一个 CHECK 约束 |
  | N3 `users.py:172` 的 `except ValueError` 收窄成 `except KeyError` | **红** 2 条（两条重置用例）：`ValueError: 密码至少 8 位` / `密码过长（上限 72 字节）` 从路由穿出去，500 |
  | N4 `users.py:137` 的 `revoke_sessions` → `pass` | **红** 1 条（降级别人）：`signed_in_devices` 仍是 1，那台浏览器照样 200——"刚把你降成成员，你还在管理面里坐着" |
  | N5 `:134` 丢掉 `user.id != actor.id` 那一半 | **红** 1 条（降级自己）：把自己当场踢下线 |
  | N6 `:134` 丢掉 `user.role != ROLE_OWNER` 那一半 | **红** 1 条（升级别人）：刚升人当管理员，反倒把人踢下线 |
  | N7 `auth_service.py:142` 只看 `user is None` | **红** 1 条（停用状态）：一个已停用的账号凭旧 Cookie 继续读全站 |
  | N8 把 `create_user` 的角色闸门整块挪到重名检查之后 | **全绿**（实测）：八条照旧过。这一单钉的是"每道闸门给得出那句中文"，**钉不住两句检查的先后**。要钉它得再加一条"重名 + 坏角色"的用例，而先报哪一句本来就没有需求说过，所以记在这里不补 |

- **文档**：`backend/CLAUDE.md` §5 薄位置清单新增一条（94% / 97% 各自剩下哪几行、为什么 `155-156` 与 `user is None` 那两处是构造性不可达、以及"降级即踢会话"这条守卫的三个格子分别由哪一条用例看着）；新用例文件的模块 docstring 写了缺行出处、那条不可达性的推导和 N1–N8 的实测结果。
- **基线**：**813 passed, 0 failed, 2 warnings**（4:52；上一单 805，差额正好是新增的 8 条）／TOTAL **93.12%**（#164 是 92.98%，miss 317 → **311**，减掉的六行正是 `137 / 172-173 / 143 / 234 / 314`）／`src/api/users.py` 94% → **98%**（只剩 `155-156`）、`src/services/auth_service.py` 97% → **99%**（只剩限流器锁定期过期的 `409-410, 416`，另开一单）；ruff 干净，`mypy src` 仍是那 **34** 项基线（这一单没动 `src/`）；前端三种测试未涉及。那 2 条 `ResourceWarning: unclosed database` 还是 `test_db_audit` / `test_db_transfer` 那一双，和 #163、#164 记的是同一对。

### 播放页放的到底是哪一路：`api/stream.py` 那十七条没人走过的行补上签字（#164）

- **症状**：表面上完全没有——浏览器里片子能放、能拖进度条、封面也出图。量出来的是 `api/stream.py` **72%**，缺的十七行是 `37, 44-59, 90-100, 105-116`：也就是**整条路由从接口进来一次也没被执行过**。`tests/test_api/test_stream.py` 直接调 `_handle_range_request`，八条 RFC 边界语义都有真文件签字，那个函数看着很健康；而它上面的路由、`_get_content_type` 那张八行的表、封面的两条分支，pytest 这一套里一份证据都没有。判断"这不是 e2e 已经盖住了"的依据是同十七行**在只跑 16 条用例的子集和跑满 786 条的套件里读数一模一样**——真后端 e2e 里浏览器确实放片子，但那是另一个进程，不进这份读数。
- **回归用例**：新增 `tests/test_api/test_stream_endpoint.py`，**19 条**。本地整文件（交给 `FileResponse`，长度来自文件本身——用例特意把 `file_size` 那一格写成 1，钉的就是"表里的陈旧值不参与播放"）、本地 Range、content-type 那张表按**九行 + 兜底**逐格参数化（含大写 `.MKV` 那格，钉的是 `ext.lower()`）、不存在的影片 404、对象存储整文件（moto 真桶：正文、`Content-Length`、`Accept-Ranges`）、对象存储 Range、**桶答了但那把键没了**（和"没配凭证"走同一个占位；`test_storage_gates.py` 那条测的是够不着桶，这一条是另一半）、封面在盘上 / 封面被移走 / 封面那条的 404。对象那几条用 moto 在进程内接住 botocore：它证明**接线正确**（地址决定读法、区间原样交给存储层、读不到不等于空库），不证明真 MinIO 回一模一样的头——那一层仍是手工核对，同 `tests/test_storage/test_s3_storage.py` 的说明。
- **变异**（一次一个变量，每个跑完立刻还原并 md5 与快照逐字节核对，最后 `git diff --exit-code HEAD -- src/` 为空；**这一单没改过 `src/` 的任何一行**）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 整文件那一路的结束字节 `max(0, file_size - 1)` 写成 `file_size` | **全绿**（实测）：超出文件末尾的 end 被服务端收敛，正文一字节不差，而 `Content-Length` 来自 `str(file_size)` 不是那个参数。记这一条是因为它**钉不住**，见下面那条 0 字节的洞 |
  | M2 对象整文件的响应头里去掉 `Accept-Ranges` | **红** 1 条（对象整文件）；本地那条照绿——`FileResponse` 自己就带这个头 |
  | M3 把 `if storage.capabilities.local_path:` 写死成 `True` | **红** 1 条：`OSError: [WinError 123] 文件名、目录名或卷标语法不正确。: 's3://media/shows/01.mkv'`。能力闸门是播放路径上唯一挡住 `s3://` 的东西，真机上这就是一个 500 |
  | M4 `_get_content_type` 的兜底换成 `application/octet-stream` | **红** 1 条（`.mpeg` 那格） |
  | M5 封面那行去掉 `os.path.isfile` | **红** 1 条：`starlette` 的 `RuntimeError`，不是 404——行还在、文件不在，这一格只能回"没有封面" |
  | M6 路由里的 `if range_header:` 改成 `if False:` | **红 1 条，且只有对象那条红**：本地 Range 那两条照绿，因为 `FileResponse` 自己就懂 `Range`，206 的状态码、`Content-Range` 和正文一模一样。所以那条分支真正在服务的只有对象存储那一路 |
  | M7 表里 `.webm` 那一行改成 `video/mp4` | **红** 1 条：正是那格的参数化用例（逐行钉的效果） |
  | M8 `storage_for_locator` 的地址判断改成 `if False:` | **红** 2 条：对象整文件 + 对象 Range。这一条同时说明"Range 那一路的取字节是在响应里现挑存储的"确实有人在看 |

- **量出来一条洞，不改、等定夺**：一个 **0 字节的对象**从接口进来会坏。`size()` 回 `0`（不是 `None`），于是整文件那一路被走到，`max(0, file_size - 1)` 算出 `bytes=0-0`，moto 抛 `InvalidRange: The requested range is not satisfiable`；临时探针（跑完即删）打接口实测到的是这个 `ClientError` 直接抛出 ASGI 应用，而 `StreamingResponse` 的状态行和响应头在这之前已经发出——真机形状是"播放器拿到一个断流的 200 + 服务端一条异常"。同一份探针里 `iter_range(0, -1)`（也就是不加 `max` 的写法）在 moto 上安静回空，真机上不可信，所以**去掉 `max` 不是修法**。要改的是行为（0 字节该回空正文、还是该按"读不到"回占位），这是产品口径，留给用户定夺，也解释了 M1 为什么全绿。
- **文档**：`backend/CLAUDE.md` §5 薄位置清单里 `api/stream.py` 那条从"72%"改写成"72% → 100%"，并把上面三条能量住的方向写进去（本地那一路的 Range 分支是冗余的、能力闸门是唯一的 `s3://` 防线、0 字节那一格今天拆不红）；新用例文件的模块 docstring 写清十七行的出处和 moto 只证明接线不证明服务端行为这条边界。
- **基线**：**805 passed, 0 failed, 2 warnings**（4:46；上一单 786，差额正好是新增的 19 条）／TOTAL **92.98%**（#163 是 92.61%，miss 334 → **317**，减掉的 17 行正是 `stream.py` 那十七条）／`src/api/stream.py` **60 行 0 缺 → 100%**；ruff 干净，`mypy src` 仍是那 **34** 项基线（这一单没动 `src/`）；前端三种测试未涉及。那 2 条 `ResourceWarning: unclosed database` 还是 `test_db_audit` / `test_db_transfer` 那一双，和 #163 记的是同一对。

### 「密码过长（上限 72 字节）」这句从来没有说过（#163）：字节闸门和坏哈希那一路补上签字，顺带记下行覆盖率骗人的那个形状

- **症状**：表面上没有，而且这一单连"薄位置"都是读数骗出来的。`utils/password.py` 报 **85%**、缺 21-22 两行——那是 `verify_password` 的 `except ValueError: return False`；同一份全量读数里 `src/services/auth_service.py:369`（`raise ValueError("密码过长（上限 72 字节）")`）也是缺的。**但 `password.py:27` 那句 `return len(plain.encode("utf-8")) > 72` 是"覆盖到"的**：每一次建号、每一次改口令都会执行它，只是 783 条用例里从来没有一次算出过 True。一个永远返回 False 的布尔判断，在行覆盖率里和永远正确长得一模一样——这是 §5 那份薄位置清单一直警告的"别拿单文件百分比当证据"的一个具体形状，值得记的是它这次**反方向**骗了一次。
- **缺口是真的**：`grep -r -e 过长 tests/` 在写这一族用例之前是空的；没有任何用例喂过 `verify_password` 一个真坏掉的哈希。界面那一头也不是构造出来的：`frontend/src/views/Users.vue:231` 那个口令框**没有 `maxlength`**，25 个汉字的口令是真打得进来的字（同一份请求在 Pydantic 那一头只有 25 个字符，离 `max_length=200` 还远）。
- **为什么要按字节而不是按字符**（这一格的存在理由）：上面一层 Pydantic 数**字符**，下面 bcrypt 的限制是 **72 字节**，而且它超了是 `raise ValueError` 不是返回 False。UTF-8 下一个汉字占 3 字节，所以 24/25 个汉字正好落在闸门两侧——只测 ASCII 的话这一族永远绿，因为字符数和字节数在那个字母表里从来不分家。
- **回归用例**：新增 `tests/test_api/test_password_gates.py`，3 条。① API 那一路从建号口进来：18 与 24 个汉字（54 / 正好 72 字节）建成**并且真能登录**（光 201 不算，哈希是按那串字节算的才算），25 个（75 字节）回 400 且 detail **整句**等于那句中文，同时库里没有这个人；② 单元那一头钉边界本身：`password_too_long` 对 72 收、73 拒，ASCII 与汉字在字节上等价——`>` 写成 `>=` 只有这一条能红（第①条照样绿，因为 75 字节仍然越界）；③ 坏哈希：把 `users.password_hash` 写坏之后登录回 **401 + 那句"账号或密码错误"**而不是 500，两种坏法各走一遍（纯 ASCII 乱串撞到 bcrypt 的 `ValueError: Invalid salt`，带非 ASCII 的那一串在 `hashed.encode("ascii")` 处先抛 `UnicodeEncodeError`——它是 `ValueError` 的子类，所以那一句 `except` 恰好两种都接得住）。
- **变异**（一次一个变量，跑完 `cp` 还原并 md5 与快照逐字节核对，`git diff --numstat -- src/` 为空）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 拆掉 `validate_password_strength` 里那句字节闸门 | **红** 1 条：detail 变成 bcrypt 自己那句英文 `password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72])`（400 状态码不变——路由把所有 `ValueError` 都翻成 400，所以只断状态码的写法在这种变异下是绿的，这一条断的是整句文案） |
  | M2 `password.py:27` 的 `>` 改成 `>=` | **红** 2 条：单元边界那条，加上 API 那条（24 个汉字=正好 72 字节被误判成过长，建号 400） |
  | M3 `verify_password` 的 `except ValueError` 收窄成 `except TypeError` | **红** 1 条：`ValueError: Invalid salt` 一路穿出 ASGI，坏哈希那条拿到的是异常而不是 401 |
  | M4 `hashed.encode("ascii")` 换成 `.encode("utf-8")` | **全绿**（实测，不是推理）：两种编法得到的字节 bcrypt 都不认识，最后都归成同一句 Invalid salt。所以这一族钉的是"任何坏哈希都只能是 401"，钉不到"哪个异常从哪一行出来"——这一句写进用例 docstring，不假装钉住了 |

- **文档两处**：`backend/CLAUDE.md` §5 薄位置清单加一条（`utils/password.py` 85% → 100%，以及上面那个"永远返回 False 的判断在行覆盖率里看不出破绽"的形状 + M4 那条测不到的诚实记录）；新用例文件自己的模块 docstring 写清两格缺口的出处和为什么必须按字节。
- **基线**：786 passed, 0 failed（上一单 783，差额正好是新增的 3 条）／TOTAL **92.61%**（#161 是 92.54%，334 miss vs 337）／`src/utils/password.py` **100%**（此前 85%）／`src/services/auth_service.py` 97%，缺的 6 行 `143, 234, 314, 409-410, 416` 里 **369 已经不在了**；ruff 干净，`mypy src` 仍是那 34 项基线（这一单没动 `src/`）；前端三种测试未涉及（只读了 `Users.vue` 一行确认没有 `maxlength`）。那 2 条 ResourceWarning 还是 `tests/test_db_transfer.py::test_every_row_lands_with_its_own_id` 的，和 #161 记的是同一对。

### 模型里那 21 处 `ondelete="CASCADE"`，SQLite 一条也没执行过（#161）：开关补在连接事件上，两种方言从此一套规则

- **症状**：表面上没有。生产路径跑的是 PG，而 PG 一直在强制外键。量出来的是**同一棵树、同一份新用例，两种方言两个结论**：`TEST_DATABASE_URL=`（清空，走内存 SQLite）跑是 `2 failed, 4 passed`，裸跑（PG）是 `6 passed`。红的那两条，一条是「子行指向不存在的父行」——SQLite 照收，PG 当场 `IntegrityError`；另一条是 `delete(Watchlist)` 这种绕过 ORM 的批量删除——PG 顺着外键子句连带清掉 `watchlist_items`，SQLite 只删父表，`assert 2 == 0` 里那 2 就是留在库里的两条孤儿。
- **根因不在 schema**：`create_all` 和 `0001` 基线写的 DDL 都带 `ON DELETE CASCADE`（`alembic/versions/0001_baseline.py` 里 21 条外键全带），缺的是 SQLite 那个**出厂关着的** `PRAGMA foreign_keys`——官网 foreign_keys.html 写明这是为老应用留的向后兼容，也就是说不显式打开，模型里那 21 处声明在 SQLite 上就只是注释。
- **这一单原来不是这个方案**（记下来，因为它红过一次就变了）：原来那张票写的是「删单级联收成一条：`passive_deletes`」。量了一把才发现这个选项是空的——`passive_deletes=True` 只阻止 ORM **去加载**子行，而 `Watchlist.items` 挂着 `lazy="selectin"`、`get_watchlist()` 又 `selectinload` 了一遍，子行永远已经在内存里，ORM 照旧一条一条发 `DELETE FROM watchlist_items WHERE id = ?`；真能跳过删除的是 `passive_deletes="all"`，而它和 `cascade="all, delete-orphan"` 是互斥的，映射器配置阶段直接 `ArgumentError: can't set passive_deletes='all' in conjunction with 'delete' or 'delete-orphan' cascade`。也就是说选了它什么也不会发生。回到用户面前重给了选项，定的是「开 PRAGMA + 用例钉平两边」。
- **修法**：`src/database/session.py` 加 `enforce_sqlite_foreign_keys(engine)`，一个 `connect` 事件补那一句 PRAGMA，DDL 一个字节不动；启动那个模块级引擎在建完之后立刻挂，PG 那边按方言早退（挂上去那句 PRAGMA 是 PG 的语法错误，会在每个连接上炸）。
- **范围是两处，不是全仓**：挂了开关的只有启动那个 `engine` 和 `tests/conftest.py` 里用例那个。`db_audit` 只读、读的就是脏库；`db_transfer` 搬的老库里可能真有孤儿行，强制了搬迁会中止；`test_migrations.py` / `test_db_transfer.py` 那些自建引擎同理。这几处保持 SQLite 出厂默认是有意的，理由写在 `backend/CLAUDE.md` 那条方言规则末尾——不然下一个读代码的人会把"怎么没挂全"当成漏。
- **挂载位置是个坑，而且是踩出来的**：`tests/conftest.py` 第一版把这个调用放在 `db_session` 里 `if/else` 之后——也就是建完表才挂。用例照旧红。原因是内存 SQLite 用 `StaticPool`，建表那条连接一路用到底，事件是**新连接**才发的，晚挂对它根本不生效。现在两个分支各挂一次，在第一次连接之前；这一条同时写进了函数 docstring，因为它下次还会绊人。
- **开强制之前先跑只读孤儿审计**（`mode=ro`，不碰任何库）：`data/` 下那五个老文件——`videos.db`（回滚目标）、`videos.db.bak-2026-09-22`、三个 `walkthrough_m*.db`——`PRAGMA foreign_key_check` 全部**零违规**（声明外键的表 9~12 张）。所以打开开关不会让任何一个老库的现有行变成写入失败；`home_sites` 那个真 PG 库不需要查，它能被写进去就说明一直是在强制下写的。
- **回归用例**：新增 `tests/test_sqlite_foreign_keys.py`，6 条。两条打 `db_session` 那条真连接（孤儿子行被拒、批量删父表两边子行都没了——顺带钉住「级联只管自己那一单，别人的队列一条不少」），跑在哪种方言上由 `TEST_DATABASE_URL` 决定，头部会打印，所以这两条两边各跑一次就是两份证据。另外四条打 `enforce_sqlite_foreign_keys` 本身：挂上的引擎 PRAGMA 真是 1 且孤儿插入被拒；**不挂的引擎同一个插入照旧成功**（这条把修前的行为永久写进用例，比一次红-绿更长寿）；非 SQLite 的引擎不挂事件（只建引擎不连库，地址是 `127.0.0.1:1` 那种不可能有服务的，也不带任何口令）；以及启动那个模块级引擎挂没挂——它按方言断言 `registered == is_sqlite`，所以本机（PG）上它只断"没挂错东西"，真的在钉事情要等 `DATABASE_URL` 指回 SQLite 那天，见下面 M1。**红在修前**：`2 failed, 4 passed`（SQLite）对 `6 passed`（PG）。
- **两次变异**（一次一个变量，跑完还原并与 HEAD 逐行核对 diff）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 删掉模块级那句 `enforce_sqlite_foreign_keys(engine)` | **红** 1 条：`the_engine_the_app_boots_on_is_armed`（`assert False == True`）——这条只在把 `DATABASE_URL` 指到一个临时 SQLite 文件时才红，所以那一次跑法是 `DATABASE_URL=sqlite+aiosqlite:///Temp/mut_engine.db TEST_DATABASE_URL= pytest tests/test_sqlite_foreign_keys.py`；PG 基线下它是绿的，这一点写进了用例 docstring，不假装它在本机能拦东西 |
  | M2 事件不挂了（`event.listen` 那句换成 `pass`） | **红** 3 条：孤儿那两条 + 「挂上的引擎 PRAGMA 真是 1」那条（`assert 0 == 1`）；`without_the_switch…` 那条照绿——它断的就是不挂时的行为 |

- **顺手量出来一个更大的洞（另开票 #162）**：为了确认这次改动没弄坏什么，把全套跑在内存 SQLite 上是头一回——`10 failed, 772 passed, 1 skipped`。那 10 条全在「我的设备」和用户管理那一带（`test_api/test_auth.py` 6 条、`test_api/test_users.py` 3 条、`test_middleware/test_roles.py[/api/users]` 1 条），异常一律是 `TypeError: can't compare offset-naive and offset-aware datetimes`（`sqlalchemy/orm/evaluator.py:263`），跟外键一个字的关系：把本次的 PRAGMA 挂载摘掉、同样三个文件重跑，还是 `10 failed, 78 passed`。SQLite 把 `DateTime(timezone=True)` 读回来永远是 naive 这件事 CLAUDE.md 记过，但只在写入侧防了。真正的事实是：**这条测试分支很久没人跑过**——本机自 10-04 起裸 `pytest` 连的就是 PG。
- **文档四处**：`backend/CLAUDE.md` 的「PG 真的执行外键」那条改写成「两种方言现在都真的执行外键」（连挂载位置一起写进去）、`VIDEO_CHILD_TABLES` 那段"两个方言朝相反方向失效"改口——那个理由的一半被这次补平了，显式清单剩下的理由换成「由这一处决定删除带走什么」+「schema 不知道哪张表存着封面路径」；`db_audit` 那段里"SQLite 不执行外键"改成"新的孤儿进不去了，那一类查的是开关之前的历史遗留"；目录树里 `support.py` 那行注释；以及 `tests/support.py` 的模块 docstring——它原文教的正是这次要堵的那条宽松路（「可以直接写 `source_id=1` 而不建那条视频源」），留着它就是在教一件不再成立的事。顺带在 `backend/CLAUDE.md` 覆盖率那一节记了一条本机踩了两次的坑：`--cov` 后面写模块名（`--cov=src.database.session`）会让解释器在 `asyncpg` 建连接那一刻直接段错误（退出码 139，栈顶 `connect_utils._create_ssl_connection`），看着像用例把进程弄坏了；同一批文件写 `--cov=src` 立刻正常。
- **基线**：783 passed, 0 failed（真库 PostgreSQL；上一单是 777，差额正好是这单新增的 6 条）／TOTAL 92.54%（#157 那一次 92.52%）／`src/database/session.py` 87.67%，缺的 9 行是 `init_db` 205-210 和 `get_session` 278-282，都由别的用例覆盖，本单新加的 147-184 那几行全被走到。ruff、mypy 干净。SQLite 分支那一趟是 `10 failed, 772 passed, 1 skipped`——那 10 条与外键无关，见上面 #162。这一趟还多出两条 `ResourceWarning: unclosed database in <sqlite3.Connection>`，都落在 `tests/test_db_transfer.py::test_every_row_lands_with_its_own_id`，是搬迁那套自己造的 SQLite 连接；本单在这条跑法上对它们是惰性的（PG 上 `enforce_sqlite_foreign_keys` 在 `event.listen` 之前就按方言早退，而那几台引擎本来就有意不挂），所以没跟着改。前端三种测试未涉及（这一单没动 `frontend/`）。

### 没有 `.env` 的检出会静默建出一个空库（#157）：默认连接串从 SQLite 换成 PostgreSQL，`asyncpg` 因此搬进核心依赖


- **症状**：`src/config.py:26` 的默认值还是 `sqlite+aiosqlite:///./data/videos.db`，而真机从 10-04 起跑的是 PostgreSQL。任何一份没有 `backend/.env` 的检出（新机器、别人 clone、CI）都会安静地建出一个空 SQLite 文件、一个空库：服务起得来，首页是空的，看起来像"装好了"。配套的 README 装依赖段还写着「`uv sync` 只跑 SQLite 用这个（asyncpg 不在核心依赖里）」——默认方言和默认依赖是错开的两条。
- **修法**：默认值换成 `postgresql+asyncpg://home_sites_app@127.0.0.1:5432/home_sites`，**故意不带口令**：口令只有一个去处，就是没进版本库的 `.env`（模板 `.env.example`，建库 `deploy/pg-provision.example.sql`）。于是没有 `.env` 的检出的第一次启动会报连不上库——这就是那条"闸门"想要的效果，只是不用新写启动检查代码：`lifespan` 的第一句就是 `init_db()`，里面是 `async with engine.begin()`，真连；而备份任务的挂载在 `main.py:34`、排在 `init_db` 之后，所以也不会对着一个连不上的库每晚发失败通知。SQLite 这条路没被删，只是从此必须显式指。
- **依赖跟着方言走**（用户定的是"默认值改成 PG"，这条是它的推论）：`asyncpg>=0.29` 从 `[project.optional-dependencies] postgres` 搬进 `dependencies`，`postgres` 这个 extra 删掉（否则同一件事两处声明）。`uv lock` 的 diff 是 3 增 5 删，全在 `provides-extras` 和 `requires-dist` 那两处，**没有任何版本漂移**——这一点值得专门看一眼，重跑 lock 顺手升别的包是最容易混进提交里的东西。
- **四条文档**：`backend/.env.example`（DB 段：PG 那行带 `<口令>` 占位，SQLite 改成注释掉的回滚备选）、README 装依赖三条、README「🗄️ 数据库」首句、`backend/CLAUDE.md` 的 PostgreSQL 小节。根 `CLAUDE.md` 的环境变量段本来就写的是 PG，没改。
- **谁真的在读这个默认值**（改之前全仓扫过一遍，`grep -n database_url`）：`database/session.py:147` 建引擎（lazy，import 时不连，所以 `python -m src.export_openapi` 离线导出照样出得来）、`main.py:34` 的备份挂载条件、`db_transfer.py:324` 的 `--to` 默认值、`e2e_seed.py:181` 的可弃库闸门。**真后端 e2e 不受影响**——它自己把 `DATABASE_URL` 显式设成 `_test` 库（`frontend/e2e/real/env.ts:90`），那份 `assert_disposable` 要的正是库名后缀。
- **回归用例**：`tests/test_config.py::test_load_default_settings` 里那句 `assert "sqlite" in settings.database_url` 换成两条——`urlsplit(...).scheme == "postgresql+asyncpg"`，和 `urlsplit(...).password is None`。第二条是这一单里我更想留下的那句：**有人为了让默认值"能连上"把真口令填进来并提交**，是这个位置唯一的凭据泄漏形状，而它不会让任何现有用例变红。**红在修前**：`1 failed, 6 passed`，红的正是 scheme 那条（`assert 'sqlite+aiosqlite' == 'postgresql+asyncpg'`）。
- **这一单里我自己的操作失误（记在这里，因为判据是可复用的）**：为了确认后台那套全量跑的是哪种方言，我执行了一句 `python -c "print(settings.database_url)"`——读的是**生效值**，也就是 `.env` 里那条带着真 PG 口令的串，于是口令进了控制台输出、进了会话日志。仓库从头到尾没有它，但这个动作的错处在于"看方言"这件事本来只需要 `urlsplit(...).scheme`，或者 `Settings(_env_file=None)`。已向用户报告并建议轮换口令；这条与上面那条 `password is None` 是同一件事的两面：**默认值不许带口令，生效值不许被打印**。
- **基线**：777 passed, 0 skipped（真库 PostgreSQL）／TOTAL 92.52%／`src/config.py` 100%；ruff、mypy 干净；前端三种测试未涉及（这一单没动 `frontend/`）。

## 2026-10-07
### 片源删掉之后调度器不知道（#152）：三条同步边第一次有人读，代价是这一族从此红得起来

- **症状**：没有。生产代码是对的——`SourceService` 的 create / update / delete 每一处都在动 `scan_source_{id}` 那个任务。这一单补的还是**层**：全仓 `grep -n "scheduler\." backend/tests` 只命中备份任务那三条断言，**没有任何一条用例读过调度器**；`/api/scheduler` 那四个端点从来没被请求过（`api/scheduler.py` 75%，缺 40、50-58、64、70），`scan_scheduler.py` 81%（缺 `start()` / `stop()` / `get_jobs()` / `is_running` 那四段），`source_service.py` 98% 缺的那一行正是 87（关启用时拆任务）。
- **为什么这一族值得钉**：少掉的每一行都不改变任何测试结果，改的却是进程内会不会多一个**永远扫不到东西的任务**。以 delete 为例：行没了，被删的片源仍按原间隔醒来，`ScanService.scan_source` 当场 `ValueError`，`scan_source_task` 那句 `except` 把它变成一条「定时扫描失败」通知——每小时一条，直到下次重启。#85 拆的"只会自己长大的通知"就是同一个形状，只是那次长在扫描成功那一侧。
- **写法**：新增 `tests/test_scheduler_source_lifecycle.py`，12 条用例。每条把 `src.services.source_service` 和 `src.api.scheduler` 里那个全局 `scheduler` 换成新建的 `ScanScheduler()`：真任务、真 APScheduler 作业表，但绝不往那个跨用例存活的全局实例上挂东西（片源接口的每一次 `create` 都在往上挂）。生命周期那七条读的是作业表里的原始 job，**不走** `ScanScheduler.get_jobs()`——未启动的调度器上挂着的任务连 `next_run_time` 这个属性都还没有，那个包装只在启动之后可用；端点那五条先把实例 `start()` 起来，顺带把 `start()` / `get_jobs()` / `is_running` 三段从没被走过的代码走了。
- **十二条用例 + 五次变异**（一次改一个变量，每次跑完按字节还原并核 md5：`src/services/source_service.py` 还原后与 HEAD 逐字节一致，`git status` 认它没被改过；绿基线 12 passed in 7.18s）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 `delete` 不拆任务了 | **红** 1 条：`deleting_a_source_disarms_its_job`——就是上面那条通知链的起点 |
  | M2 `update` 关掉那一支不拆任务 | **红** 1 条：`deactivating_a_source_disarms_its_job`；`reactivating…` 照绿——它后来会把任务重新挂上，那条边盖不住这一支 |
  | M3 `create` 不分启用与否，一律挂上 | **红** 1 条：`an_inactive_source_is_not_armed` |
  | M4 `update` 末尾整段同步删掉 | **红** 2 条：`deactivating…` + `changing_the_interval…`——比 M2 宽一层，说明那两段不是重复断言 |
  | M5 `create` 挂的是写死的 3600，不是片源自己的 `scan_interval` | **红** 3 条：`creating…own_interval` + `renaming…leaves_the_job_alone` + `the_jobs_endpoint_lists…`；`changing_the_interval…` 照绿——那条走的是 `update` 那一支，它用的是对的变量 |

- **M5 是这一单里唯一事先没算准的一条**：第一次跑它红了 4 条，多出来的是 `an_inactive_source_is_not_armed`——因为我那个变异顺手把 `if source.is_active:` 一起写没了，一次改了两个变量。把锚点收窄回"只换实参"之后它红 3 条，`battery ok`。这张表的意义恰恰在这：预期写错会被自己的电池打回来，而不是被"全绿"糊过去。
- **顺带记下但没改的一处**：`ScanScheduler.get_jobs()` 那句 `job.next_run_time.isoformat() if job.next_run_time else None` 在**未启动**的调度器上会 `AttributeError`（挂上去的任务那时还没有这个属性）。生产够不着——uvicorn 只在 lifespan 起完之后就绪，而 `main.py` 是先挂任务再 `start()`，`start()` 会把挂着的任务挨个排上时间轴。所以这一句不加兜底；但它解释了为什么这一份用例分两种读法（生命周期读作业表，端点先启动）。
- **基线**：修前 PostgreSQL 全量 765 passed、TOTAL 92.01%，修后 **777 passed**（正是新增那 12 条）、TOTAL **93%**（92.52%，9:33 跑完，`--cov=src`）。三处薄位置各自归零：`api/scheduler.py` 75%→**100%**、`scan_scheduler.py` 81%→**100%**、`source_service.py` 98%（缺的就是 87 那一行）→**100%**。`ruff check src tests` 全绿，`mypy src` 34 条与基线持平。前端零改动（`git status --short` 只有那一份新用例和三处文档），三层静态闸门因此没重跑。
### 设置页那个「自动扫描」开关按下去什么都关不掉（#150）：`settings` 表第一次有了写入方之外的读者

- **症状**：owner 在系统配置页把「自动扫描」拨到关、保存、刷新回来仍是关——然后片源照样按各自的间隔一轮一轮被扫。证据只有一条 grep：`auto_scan_enabled` 除了 `/api/settings` 自己（写它、再把它读回来回显），全仓没有任何代码读过它；`scheduler/tasks.py` 那两个扫描任务和 `main.py` 的挂载只看 `video_sources.is_active` 与 `scan_interval`。页面上那句「启用后将按照设定的间隔自动扫描视频源」里，"自动扫描"一直在发生，跟开关没关系。
- **为什么一层测试都没抓到**：`test_api/test_preferences.py` 把这一面盖得很实——键名白名单、值的可解析性、整份 PUT 的写→读往返，全绿。**往返恰好是装饰件最像正常工作的形状**：断言的是"写进去的能读回来"，从来没有人问"读回来之后是谁在用"。根 `CLAUDE.md` 因此多了一条规则（配置表的键要有读者），这条规则本身也是这一单的产物。
- **修法**：新增 `src/services/setting_service.py`——`SettingService.is_auto_scan_enabled` 每轮现读，两个扫描任务在真正动手之前问一次，关了就整轮不走，也**不写任何通知**（一轮被开关拦下的扫描不是事件，给它播一条就变回 #85 刚删掉的那种每晚心跳）。解析规则只留 `parse_auto_scan_enabled` 一份：没写过这一行算**开**（新库那张表本来就是空的，一个字没写过的人不该被静默停扫），`GET /api/settings` 改走同一份，否则同一个字符串在后有两个真值。
- **闸门的位置是这一单唯一不显然的地方**：落在 `scheduler/tasks.py`，不落在 `ScanService.scan_source`。设置页说的是"自动"扫描，人按「立即扫描」那一路不该归它管。而"挪进 service"是完全同一行代码、四条用例照绿——只有第五条会红。M3 就是专门跑这一挪的。
- **五条用例 + 四次变异**（一次改一个变量，每次跑完按字节还原并核 md5：`src/scheduler/tasks.py` `c062b2c1…` / `src/services/setting_service.py` `ad520b05…` / `src/services/scan_service.py` `dd796a8f…`；绿基线 5 passed）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 删掉 `scan_source_task` 那道闸门 | **红** 2 条：`a_disabled_switch_skips_the_scheduled_round` + `flipping_the_switch_back_on_resumes_scanning`；`full_scan_round…` 照绿——两个任务各问各的，少一处不会一起红 |
  | M2 没写过这一行时的默认改成"关" | **红** 1 条：`no_row_written_yet_means_auto_scan_is_on`——空表是每一台新机器的常态，这一条挡的是"修好开关顺手把默认扫成关" |
  | M3 闸门挪进 `ScanService.scan_source`（任务里那道同时删掉） | **红** 1 条：只有 `manual_scan_is_not_governed_by_the_switch`；前三条照绿——**位置错而用例全绿**这一族，第一次被自己人挡住 |
  | M4 删掉 `scan_all_active_task` 那道闸门 | **红** 1 条：`full_scan_round_honours_the_switch_too` |

- **红在修前**：闸门还不存在时跑这一份用例是 `3 failed, 2 passed in 8.59s`（红的是 M1/M4 各自要抓的那三条：`disabled…` / `flipping…` / `full_scan…`），而 `no_row…` 与 `manual…` 当时就绿——它们钉的是"改完之后也别变坏"的那两侧。
- **仍然没接的**：`auto_scan_interval`、`default_transcode_format`、`thumbnail_width`、`thumbnail_height` 四项仍是只写不读。第一项最刺眼：它和源级别的 `scan_interval` 撞名，而 `SourceForm.vue` 那个秒数输入框才是真的在管事。要么让它广播给所有启用的源（那源级就退化成会被设置页覆盖的默认值），要么从页面上摘掉——这是产品决定，留给用户，见 #151。
- **另一处顺手记下的事实**：`scan_all_active_task` 在真机上**没有挂载点**（`main.py` 只按源挂 `scan_source_{id}`，`/api/scheduler/jobs` 那条 POST 也只挂按源的），全仓 grep 只有它自己的定义命中过一次。闸门照加，理由写在这份用例的 docstring 里：将来它被挂上去的时候，这个开关不能再是第二次装饰。
- **基线**：修前 PostgreSQL 全量 760 passed，修后同一套 **765 passed**（正是新增那 5 条），`--cov=src` TOTAL **92%**（92.01%，17:06 跑完）。`scheduler/tasks.py` 从 62% 到 **93%**——剩下的 44-45、69-70 是"失败通知自己也写不进去"那两层兜底，要有真机才红得起来；新文件 `setting_service.py` **100%**。`ruff check .` 全绿，`mypy src` 34 条与基线持平（新增的两个文件一条没贡献）。前端这次没动：`git status --short` 只有 backend 的 4 个源文件、1 份用例和 4 处文档，所以前端的三层闸门没有重跑的必要。

### 第五个构造器曾能一声不响地走进来（#149）：哨兵表现在必须和遍历器记到的那一批一一对应

- **症状**：没有。和 #148 同一类——这一单补的还是层，不是修复。`tests/api/builder-urls.spec.ts` 那张管「哪个实参落在哪一段」的哨兵表原先**只按名字手写四条**，所以它的失效方式不是地址写错，而是清单不全。
- **先量盲区**（一次性变异，跑完即还原）：往 `src/api/videos.ts` 加一个只返回字符串的 `tempSubtitleUrl`，故意复用一条**已声明**的路由模板 `/api/videos/{video_id}/subtitles/{subtitle_id}/stream`。结果 `tests/api/` 那 11 份文件 50 条**全绿**：遍历器记到它、路由表那层对上它、形状与替身两层照绿——「实参落在哪一段」这一层根本不知道它存在。
- **修法**：表**仍然是人写的**（每条 `{key, actual: fn(11, 22), expected: 人算的那句}`），外面加一条 `pins exactly the builders the walker records`：表上的键集必须**等于**遍历器 `viaClient === false` 补记的那一批，两个方向都拆——新构造器没人钉红、构造器被删掉而表没跟着改也红。再加一条 `has builders to pin` 下限（「空匹配集不报错，它只是绿」这一族第五次：#122 glob 深度 / #128 遍历空跑 / #131 切片偏移 / #148 探测 / #149 表——表要是被清空，下面每条都会空跑）。
- **为什么不把整张表自动生成**：这一层要的就是「有人为它算一句期望地址」那一步。让遍历器把自己的记录回灌成期望值，断言就变成 `x === x`，第五个构造器照样走进来，只是这次连该红的人都没有。
- **四次变异**（每次改单点、跑完按字节还原并核 md5：`src/api/videos.ts` `f413e168…` / `tests/api/emitted-calls.ts` `3ab11800…` / `tests/api/builder-urls.spec.ts` `b93f7c30…`；绿基线两份守卫共 15 passed）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 加第 5 个构造器，复用已声明的字幕轨模板 | **红** 1 条：`pins exactly the builders the walker records`；`openapi-contract.spec.ts` 那 9 条照绿——路由表看不出槽位归属 |
  | M2 表里删掉一条钉（构造器还在） | **红** 2 条：`has builders to pin`（表少到 3 条）+ 集合相等（unpinned 方向） |
  | M3 把某条期望地址里的两个哨兵实参写反 | **红** 1 条：只有它自己那条 `puts the sentinels where … says they belong`，集合相等照绿——「槽位归属」和「清单完整」是两个问题，得分开定位 |
  | M4 遍历器不再补记构造器（那半静默归零） | **红** 3 条跨两份文件：本单的集合相等（stale 四条一起）+ `openapi-contract.spec.ts` 的两条下限 |

  M1 那一行同时就是「红在修前」：同一句变异在手写四条表的旧守卫下全绿（上面那条实测），在本单之后恰好红一条。
- **踩到的一个脚手架错**：电池第一版按「`tests/api/*.ts` 是 LF」的假设写多行锚点，而工作区里 `src/api/videos.ts` 是 **CRLF**，M1 的 needle 数不出 1 次、脚本停在断言上；改成按目标文件的行尾对齐 needle 与 replacement 才跑通（#148 那批锚点全是单行，因此没撞上这一条）。
- **没做的**：遍历器补记的条件仍是 `typeof returned === 'string' && returned.startsWith('/')`，所以一个返回字符串却**不带前导斜杠**的构造器仍然记不到，也就仍然钉不到——要补得先让遍历器接受非 `/` 开头的返回值，那是形状层（`paths.spec.ts` 那三条规则）的下游；哨兵实参仍写死 11 / 22，三个以上参数的构造器要用哪几个值仍归人决定。
- **基线**：Vitest 343 → **345 passed / 36 files**（本单 +2）、`typecheck:test` 无输出、`npm run build` ✓ 795ms、桩 e2e **100 passed（39.2s）**。真后端 e2e（26 条）与后端套件（760 条）没重跑，证据：`git status --short` 只有 `frontend/tests/api/builder-urls.spec.ts` 一份，电池碰过的两份文件全部按字节还原并核过 md5。文档同步：`CLAUDE.md`（构造器那一层多的一句）、`frontend/CLAUDE.md`（#149 一段）、`CHANGELOG.md` 本条。

### 钉住前端会发出的每一个查询参数名（#148）：`?searsh=abc` 回的是 200 和**没筛过的**第一页

- **症状**：没有。这一单补的是一层，不是修复——今天这份应用一个拼错的查询名都没有，守卫的**自然红条数是 0**。写在这儿是为了别把它读成"修好了什么"。
- **盲区在哪**：`frontend/tests/api/emitted-calls.ts` 给每个参数位塞的是 `[1,2,3]`，而 `client.getUri` 对非对象 `params` 会抛 `TypeError`，遍历因此把它丢掉——于是 `listVideos(params)` 这种「第一个参数就是查询对象、原样交给 axios」的函数，在三份静态守卫里发出的**查询串是空的**。它的查询名不写在 `src/api/` 里（`Home.vue:160-232` 三处调用按筛选状态拼 `{page, page_size, source_id, tag_id, search}`），而是声明在参数类型接口 `VideoQueryParams` 上：TS 管的是调用方↔接口那一段，**接口↔后端那一段此前没有任何东西在看**。
- **先量失效的形状**（一次性探针，跑完即删）：`GET /api/videos?searsh=abc&page=1` 回 **200**，返回的是**没筛过**的第一页（`['items','page','page_size','total']`）。FastAPI 只把声明过的查询参数绑进函数签名，`backend/src` 全仓 grep 无一处读 `request.query_params`（零命中）。所以这一族的失效方式不是报错，是**筛选无声停掉**——界面上搜了等于没搜。
- **认「谁是查询转发函数」用的是哨兵探测，不是读代码形状**：把一个只含 `__qprobe__` 的对象逐位塞进参数位，真发出去的地址里出现这个键，才算它是查询转发函数。`{ params }` 简写、`{ params: xxx }`、`{ ...extra }` 摊平——形状全都不重要，这是问函数本身而不是猜它怎么写（同一理由见 #128「守卫 import 它检查的东西，强过抄一份匹配器」）。位数拿不到（`listVideos(params = {})` 的 `.length` 是 0，所以按 `function.length` 循环会一位也不探），于是固定探样本参数那三位。命中之后键集取自那个参数**声明的类型接口**（`firstParamType` + `interfaceFields`，两份 `import.meta.glob('?raw')` 读源码），再把整套键回喂一次，记下浏览器真会发出的那一句和里面真落线的键。
- **断言的是子集，不是集合相等**：接口里有个后端没声明的键 = 真缺陷；后端声明了而前端不用的键 ≠ 缺陷。四条新用例（`openapi-contract.spec.ts` 从 5 条到 9 条）：认得出转发函数（下限 `>= 1` **并且**点名 `videos.ts#listVideos`）、每个查询面都读得出键集（读不到判红而不是放过）、发出去的键后端全都声明、接口声明的键全都真落到线上（外加 `expect.arrayContaining` 把那五个已知键钉住）。
- **「空匹配集不报错，它只是绿」这一族第四次**：#122 glob 深度、#128 遍历空跑、#131 切片偏移，这次轮到探测本身——所以"认得出转发函数"那条同时设下限和点模块名。
- **六次变异**（每次改单点、跑完按字节还原并核 md5：`src/types/video.ts` `3d28606b…` / `src/api/videos.ts` `f413e168…` / `tests/api/emitted-calls.ts` `3ab11800…` / `backend/openapi.json` `253253cd…`；绿基线该文件 9 passed）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 接口里把 `search` 拼成 `searsh`（前端这一半） | **红** 2 条：`sends only the query names the backend declares` + `sends every query name the parameter interface declares` |
  | M2 只把 `openapi.json` 里声明的 `search` 改成 `q`，前端一个字没动（后端那一半） | **红** 1 条：`sends only the query names the backend declares` |
  | M3 模块不再转发调用方给的对象（`{ params })` → `{})`） | **红** 2 条：`finds the query-forwarding functions by probe` + `sends every query name…`——这一族整个静默消失 |
  | M4 模块只转发 `search` 与 `page` 两个键 | **红** 2 条，判决与 M3 **完全相同** |
  | M5 守卫自己读键那一步锚错（`export  interface` 双空格） | **红** 2 条：`reads a key set off the parameter type of every surface` + `sends every query name…` |
  | M6 仍转发对象、却把 `page` 按死成 `undefined` | **红** 1 条：`sends every query name the parameter interface declares`——"少发"那条规则全绿，只有反向这条抓得到 |

  M4 那条如实记下来：对「我给的对象有没有原样落到查询串上」这一问，"完全不转发"和"只转发两个键"是**同一个答案**——两者都意味着这一族的查询串由模块自己决定。探测答不出"落了几个"，要区分得换问法，那是另一单的活。
- **跨层量的那一半**（另一次单点字节变异，跑完还原）：把 `backend/src/api/videos.py` 路由签名里的 `search` 改名，红的是 `backend/tests/test_openapi_snapshot.py` 两条（`test_committed_openapi_matches_the_route_table`、`test_check_mode_agrees_with_the_snapshot`），而前端那层照绿——因为它读的 JSON 还没变；只改 JSON 则红的是前端那层。也就是说这条契约是**两节各红各的**（代码↔文件、文件↔接口），接起来才钉住「路由代码 ↔ 前端接口」，没有哪一层单独钉得住。已写进 `backend/CLAUDE.md` 与 `README.md` 的快照命令注释。
- **自己踩到、并且改掉的三个错**：一是变异电池第一版只在 `finally` 里还原，于是 M4 的锚点已被 M3 吃掉、脚本死在「锚点出现 0 次」——**变异必须单变量**，改成每轮循环开头回写原始字节；二是 M5 那一版的替换字节和 needle 一模一样，是个空变异（跑了等于没跑），重锚到双空格才真的把读取器打断；三是本机控制台 cp936 在打印 vitest 的 `×` 行时抛 `UnicodeEncodeError`，电池炸在 M1 之后——`finally` 把四份文件都按字节还原并核了 md5，没漏，加 `sys.stdout.reconfigure(encoding='utf-8')` 和 ANSI 剥离之后重跑。另有两处是跑之前重读代码抓到的：`interfaceFields` 用 `(\S*?)` 永远匹配不上接口体（接口体里全是换行和缩进 → 改 `([\s\S]*?)`），以及第二次回喂时假定命中的是 0 号位（探测可能命中 1/2 位 → 改成按 `slot` 回写）。
- **没做的**：`tests/api/builder-urls.spec.ts` 那份「构造器清单」仍是手写的四条，第五个只返回字符串的构造器可以走进来而不受任何钉子——下一单 #149 让它从遍历器 `viaClient === false` 的记录推导；`src/api/` 之外不许拼 URL 那条由 `inline-requests.spec.ts` 守，与本单无交集。
- **基线**：Vitest 339 → **343 passed / 36 files**（+4）、`typecheck:test` 无输出、`npm run build` ✓ 805ms、桩 e2e **100 passed（37.6s）**。真后端 e2e（26 条）与后端套件（760 条）**没有重跑**，证据写清楚：`git status --short` 只有 `frontend/tests/api/` 那两份文件，Playwright 只收 `./e2e` 与 `./e2e/real`，而变异电池碰过的后端文件全部按字节还原（`api/videos.py` `d95de0dd…`、`openapi.json` `253253cd…`）。文档同步：`CLAUDE.md`（契约链那句 + 三层守卫那句）、`frontend/CLAUDE.md`（`getUri` 丢 `params` 那句 + 新增 #148 一段）、`backend/CLAUDE.md`（下游消费者那句 + 新增"没声明的查询参数会被静默忽略"）、`README.md` 快照命令注释、`CHANGELOG.md` 本条。

### 扫描只登记字幕、从不核对（#147）：文件移走之后那条轨道永远挂在菜单上

- **症状**：字幕文件被移走、改名或删掉之后，`GET /api/videos/{id}/subtitles` 照旧列出那一条，CC 菜单照旧给着那个名字，点下去才是 #146 那句「字幕「英文」没能加载」。这一格是 #146 收尾时点名留给下一单的「没做的」：那一单只让界面**说实话**，没替谁把行收拾干净。
- **缝在哪**：`scan_service._register_subtitles` 只会**加**（`SubtitleService.register` 撞到已知路径返回 `False`），而影片行在 `scan_service.py:341-350` 有 `is_missing` 那一路核对，字幕从来没有对照的一半。形状上也不对称：影片行留着改标记，`Subtitle` 那一行除了"这条轨存在"什么都不表达，所以这里做的是**删行**（新增 `SubtitleService.prune_missing`），删除的正是 #14 那单一直在防的"孤儿行"那一类。
- **这一单的承重墙是问法**：问**「文件还在吗」**（`os.path.isfile(row.filepath)`）而不是**「这轮扫描认得它吗」**。后者看着更对称、也更快（清单已经在手上了），但它每次扫描都会抹掉所有手工挂上来的轨道——`find_subtitle_files` 只认由影片主干名推出来的那几种后缀，而 `SubtitleService.add` 收下的名字可以完全不在那个模式里（`movie.zh.srt` 之外还有 `另一组字幕.srt` 这一类）。这一格由 `test_scan_keeps_hand_registered_subtitle_the_scanner_never_matches` 钉着，#134 那条"手工挂的标签扛过一次真扫描"是同一族。
- **两道闸门各自挡掉一种"整库被读空"**：`storage.reachable(source.path)`——挂载盘没就绪那一轮清单是空的，据此核对会把每条登记都删掉；`storage.capabilities.sidecar_subtitles`——源类型可以由 `PUT /api/sources/{id}` 从本地改成对象存储，而那些 `s3://` 地址在本地 `isfile` 看来永远"不存在"。两道都能红（M4、M5），不是装饰。
- **契约只动了一处**：`subtitles_gone` 只走服务层的返回 dict 和通知的 JSON 列，**没进** `ScanResultResponse`（和 `foreign_paths` 同一待遇：那个响应模型是固定的，多余的键被 Pydantic 丢掉），所以 `backend/openapi.json` 不必重导。通知 `data` 那一列则是前端 `toEqual` 在断的契约，所以 `frontend/e2e/real/library.real.spec.ts` 那三处载荷同步加上 `subtitles_gone: 0`。文案是第五句方向话「N 条字幕文件已不存在」，闸门加的是第四项。
- **用例**：`tests/test_services/test_scan_service.py` 五条新的（删掉的必须是被移走的那一条 / 两句词都不许动 / 手工挂的那条扛得住 / 只播一次且下一轮安静 / 没这个能力的源整批不动），`tests/test_storage/test_scan_through_seam.py` 一条新的（够不着的共享盘不核对）——六条对着修前的 HEAD **全红**（`6 failed, 42 passed`）。真后端 e2e **第 22 条原地加宽第 8 步**，没新开第 27 条（编号就是执行顺序）：删掉走过的那条 `.eng.srt` 之后点一次扫描，清单只剩 `zh`/`ja`、`files_found=2`、通知多那句「1 条字幕文件已不存在」，而**播放页在这一刻什么也不说**（菜单回到 `['关闭','中文','日文']`、零条 toast），切到 `.chi.ass` 那一条仍是两句真 cue。第 22 条头部那段"扫描没有字幕丢了这一说"的说明跟着翻成了这一格现状。
- **六次变异**（每次改单点、跑完按字节还原并核 md5：`scan_service.py` `dd796a8f…` / `subtitle_service.py` `e114ec36…`）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 摘掉 svc 调用（等于回到修前） | **红** 2 条（移走那一条 + 通知那一条）；真后端 e2e 第 22 条同红在 :488 那句 |
  | M2 通知闸门不含 `subtitles_gone` | **红** 1 条（只播一次那一条） |
  | M3 不看文件在不在、整源删光 | **红** 8 条（连登记那三条一起——被删掉的是下一轮还要重新认出来的那两行） |
  | M4 核对不看 `reachable` | **红** 2 条（够不着的共享盘 + 能力那一条） |
  | M5 核对不看能力闸门 | **红** 1 条（`s3://` 那一批历史行） |
  | M6 数的是"翻了几行"而不是"删了几行" | **红** 4 条（对照用例的 `0` 最先撑不住） |

  M1 特别在真后端 e2e 上单跑了一遍：同一处摘掉，浏览器那一头红在第 8 步那句 `not.toContain(srtId)`，而第 23 条照绿——这一层的签字只咬它该咬的那一格。
- **自己踩到、并且改掉的两个错**：一是把 `prune_missing` 的第一版写成"数行数"那一族同构错误（`gone` 直接从 `result.scalars()` 推，没有中间量），变异电池的两条锚点因此无处落，先把它改成 `rows`/`gone` 两步再跑；二是**全量后端套件我同时跑了两趟**（前一趟丢在后台、后一趟前台再起），两条链共用 `home_sites_test` 那一个库，于是前台那趟红在 `tests/test_api/test_auth.py` 那 16 条 + 4 条 ERROR——和本单毫无关系，是把"不许同时跑两套 DB 用例"这条自己记过的规矩破了。复位后单独重跑一遍：**760 passed**（9:21，绿）。这条写在这儿是因为它差点变成一次假诊断：红的全是 auth，而我改的是 scan。
- **没做的**：真库里那两条字幕行的 `label` 还是 `en` / `zh`（#143 记的那件），仍然等你点头；内嵌字幕（`media_streams`）那一路没有"行"可核对，本来每次播放都现探，不受这一单影响；扫描不会**重新发现**被移走后又改名的字幕以外的修复动作，改名后的旧行就是删掉、由下一轮 `find_subtitle_files` 重新登记。
- **基线**：后端 754 → **760 passed**（真库 PostgreSQL，单跑 9:21）、`ruff` All checks passed、`mypy` 仍是文档里那 **34** 条且我改的两个源文件零条；Vitest **339 passed / 36 files**（一条没动）、桩 e2e **100 passed**、真后端 e2e **26 passed（2.6 分钟）**，第 22 条整跑 4.1 秒、`typecheck:test` 无输出、`npm run build` ✓ 746ms。文档同步：`README.md` 外挂字幕那一节多出第 5 步、`CLAUDE.md` 能力表"字幕支持"那一行、`backend/CLAUDE.md` 通知段四项 + 新增一段"字幕那一半是核对"、`frontend/CLAUDE.md` 第 22 条那段现状翻过来、`CHANGELOG.md` 本条。

### 字幕轨取不到时播放器一声不响（#146）：失败只有浏览器知道，那就让它说

- **症状**：外挂字幕那个文件被移走之后，菜单里那条轨照旧在、照旧可点、点了照旧什么都没有。`VideoPlayer.vue` 只给 `<track>` 挂 `load`，不挂 `error`，于是那句 404 走到浏览器就蒸发了——这是 #142、#143 连着记了两次的同一格「没做的」。
- **先量机制，再定形状**（第一版断言按"轨插进 DOM 就去拉"写，红了以后没有猜：喂真 mp4、让真服务器回真 404 起了一次探针）：
  - `<track>` 上没有 `default` 时 Chromium 起步给的是 **`disabled`**，那种轨**一个请求也不发**——实测重载后三条轨的 `readyState` 全停在 0，服务器那边一条 `/stream` 也没收到。`applyTrackMode` 选中一条时会把三条一起拨到 `showing`/`hidden`，**那一次拨动才是第一个请求的来处**（所以第 22 条里两条从没被选中的 `hidden` 轨也是 `readyState` 2、cue 齐全）。
  - 失败和 `load` 一样**只发在 `<track>` 元素上**，`TextTrack` 上那个事件 Chromium 从来不发；而 `readyState` 一旦是 3 就**不再拉第二次**，所以标记必须是留下来的那一份——toast 三秒自己走。
  - 由此定了三件不做的事：不主动汇报没被点过的轨（结构上做不到，它连请求都没发出去）、失败时不自动取消选中（"你选了它、它坏了"比"它悄悄没了"诚实）、不动 `.subtitle-menu-note`（那是内嵌那一路报图像字幕的格子）。
- **修法**：`failedTrackKeys` 一份清单 + `markTrackFailed(key, label)` 一个入口 + 菜单条目后缀 `failedSuffix(key)`。只有那个 `error` 事件能进这个入口——"这一行还在清单里"永远不是失败的来处。话只说一句、不带原因：接口那句 404 的原话（#142 特意留在响应体里）到浏览器这一头一个字都不剩，原因在不在磁盘上都问不出来，所以不写"文件不存在"这种话；文案纯中文，走 #131 那条语言守卫。
- **用例**：`tests/components/VideoPlayer.spec.ts` 五条新的（说得出是哪一条 / 只标浏览器报的那一条、而且要它报了才标——标记得出现在**已经开着**的菜单里才算接上响应式 / 同一条不重复弹 toast / 内嵌那条用探针给的名字 / 换文件把标记清掉），五条对着修前的 HEAD 全红（`5 failed | 46 passed`）。真后端 e2e **第 22 条原地加宽**，没新开第 27 条：这套用例的编号就是执行顺序，新开一条必须排在最后，而这次要钉的两副样子都在第 22 条的现场。翻过来的是"重载之后点下去 → toast +「英文（加载失败）」"这一格；新加的反面是"文件确实已经没了、但那条轨的旧 cue 还在浏览器内存里时，界面上一个字都不许报"（`errorToasts` 0 + 菜单四条干净），以及 `.subtitle-menu-note` 仍然不多一个字。
- **七次变异**（每次改单点、跑完按字节还原并核 md5：`VideoPlayer.vue` `0fa83df9…`）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 摘掉 `error` 监听（等于回到修前） | **红** 在 :445 那句 toast |
  | M2 只 toast、不记进 `failedTrackKeys` | **红** 在 :461 那个标记 |
  | M3 只记标记、不发 toast | **红** 在 :445 |
  | M4 一条失败就把每条都标死 | **红** 在 :461（红的是"只标浏览器报的那一条"） |
  | M5 换文件时不清空标记 | **红** 在单测 :506（菜单回到 `['关闭','英文']` 那一句） |
  | M6 去掉监听器上的 `{ once: true }` | **两层全绿**，见下 |
  | M7 toast 报的是内部 key（`sidecar-3`）而不是菜单上那个名字 | **红** 在 :445 |

  M6 记在这儿而不是删掉：挡住重复 toast 的是 `markTrackFailed` 开头那句按 key 去重，`once` 只是第二道闸——它不是已签的护栏，别把它当回归测试的保护对象。
- **自己踩到、并且改掉的两个错**：一是第一版把 toast 断在 `page.goto` 之后、点击之前，靠的是"插入即拉取"这个没验过的假设，实测红在 :436；机制量清楚之后那一段顺序整个换了。二是那份一次性探针喂的 `movie.mp4` 是 `content-length: 0`，影片自己就没加载成功，于是得出"`hidden` 的轨不发请求"这个**部分正确**的结论（真正不发的是 `disabled`；`hidden` 是会被拨出来、也会发请求的）。两处都写进了注释和文档，探针跑完即删。
- **没做的**：扫描那一头仍然没有"字幕丢了"这一说——文件没了行还在、清单照旧列着它（第 22 条钉的现状）；这一单只让界面**说实话**，没有替谁去把行收拾干净。真库里那两条字幕行的 `label` 还是 `en` / `zh`（#143 记的那件），仍然等你点头。（前一件 **2026-10-07 由 #147 关掉**：扫描现在核对「文件还在吗」并把那一行删掉，上面引的那句现状和第 22 条那段说明都已翻过来；界面这一头没再动过。）
- **基线**：Vitest 334 → **339 passed / 36 files**；真后端 e2e **26 passed（2.3 分钟）**，第 22 条整跑 3.4 秒、solo（`-g sidecar` 命中同文件两条）11.4 秒；桩 e2e **100 passed**、`npm run build` ✓ 762ms、`npm run typecheck:test` 无输出。后端一行没动（这一单改的全在 `frontend/`），`git status` 里后端目录干净，所以那 754 条后端用例、`ruff`、`mypy` 都没重跑。文档同步：`README.md` 外挂字幕那一节多出第 4 步、`CLAUDE.md` 能力表"字幕支持"那一行、`frontend/CLAUDE.md` 第 22 条那段现状翻过来 + 单测约定里多一条"两层的分工是量出来的"、`CHANGELOG.md` 本条。

### 加宽真后端 e2e（#145）：片单那三条写路径打真库——那句 409 和那一次备注赋值，pytest 里一次也没执行过

- **缝在哪（先量的，不是猜的）**：拿现有那份 `.coverage` 跑 `coverage report`，两行显示**从未执行**：`backend/src/api/watchlists.py:125`（PUT 路由那句 `raise HTTPException(409)`）和 `backend/src/services/watchlist_service.py:129`（`watchlist.description = description`）。原因各自的：409 只在 POST 那一路被撞过（`tests/test_api/test_isolation.py:61`），而没有任何一条用例往一条**已存在**的片单上 PUT 过备注——`test_watchlist_service.py:126` 断的那个 `description is None` 属于一条压根没写过备注的单。真后端 e2e 这一头，第 5 条只签过"从详情页新建一条也进库"，替身夹具那三个处理器（`frontend/e2e/fixtures.ts:1043` PUT、`:1096` 移出、`:1103` 删单）既不查名字撞不撞、也不按账号过滤，404 文案还是它自己编的那句「片单不存在」。
- **只有真跑答得出的三件事**：
  - 名字那条索引是 `UniqueConstraint("owner_id", "name")` 而不是全局的，于是"该挡"和"不该挡"分居两步：owner 把自己的片单改成**成员**那条的名字必须放行（第 8 步，200），改成**本人**另一条的名字必须 409（第 6 步）；中间还夹着一道"同名的自己不算撞"的闸门 `if name != watchlist.name`——只改备注那一次 PUT 是带着原名字进来的，去掉闸门它就跟自己撞死。
  - **回声不算证据**：`Watchlists.vue:85` 和 `:97` 把 PUT / DELETE 的响应直接写进 `lists.value`，所以界面在"库里一个字没变"的那个世界里也照样显示新状态。于是每一步 UI 之后都另发一次 `GET` 读回来比，409 那一步只有真读回可看（名字、备注、`created_at`、队列逐列未动——`created_at` 那一列挡的是"改名走成删了重建"）。
  - 三条写路由的 404 全是服务层那句**带 id** 的原话 `Watchlist with id N not found`（`update` / `delete` / `remove_video` 三处 raise，路由只把 `str(e)` 塞进 detail），而 `GET /api/watchlists/{id}` 走的是路由自己那句**不带 id** 的 `Watchlist not found`：「这条存在但不归你」和「压根没这条」在读那一路是同一个字节串。这一句是拿 999999 和一条真存在的别人的单各读一次、比 `text` 逐字相等钉下来的，顺带才说明归属过滤没把别人的行存在性漏出去。
- **移出签的是范围**：同一部片子在另一条片单里那一行必须还在（M4 把删除写成按 `video_id` 全库删，红在这一句），而影片行自己仍 200——删的是 `watchlist_items` 那一行，不是 `videos`；跨页面那一头是详情页的「片单」弹窗，勾的状态和 `1 部` 计数跟着片单页一起改口。
- **删单那一路量出一个双机制盲区，而预判被推翻**：`Watchlist.items` 上的 `cascade="all, delete-orphan"`（ORM 侧）和 `watchlist_items.watchlist_id` 上的 `ondelete="CASCADE"`（PG 侧）是同一个保证后面的两台机器，原以为去掉任何一条都不会红。实测 M7 去掉 ORM 那一条之后本条**照样红**，只是红在更早的「移出」那一步：关系上没有 `delete-orphan` 时 `items.remove(item)` 走的是把外键置 null，PG 的 NOT NULL 当场 `NotNullViolationError`、路由 500、界面那句移出的成功 toast 不出现（那串 asyncpg 栈直接打在 uvicorn 的输出里）。所以"两条机制挡一件事"这个盲区今天只剩**删单**那一路没被拆开，而 M7 红得比那一步早、压根没走到它——记在这里，只记不拆。
- **七次变异**（每条改完单跑 `-g 三条写路径`，跑完整份原字节写回并核对 md5：`watchlist_service.py` `e0d4e44d…` / `models/watchlist.py` `07246594…` / `Watchlists.vue` `650561e4…`）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 去掉 `update` 里 `await self._require_free_name(user_id, name)` | **红** 在 :248 那句 409 toast，也就是那句从没执行过的 `api/watchlists.py:125` |
  | M2 去掉 `if description is not None` | **红** 在 :233——只带名字的 PUT 把备注擦成 null |
  | M3 放松 `get_watchlist` 的 `owner_id` 谓词 | **红** 在 :304，成员改得动 owner 那一条（200 而不是 404） |
  | M4 `remove_video` 改成按 `video_id` 删 | **红** 在 :337"另一条里那一行还在" |
  | M5 去掉 `if name != watchlist.name` 那道自我闸门 | **红** 在 :221，只改备注那次 PUT 撞死在自己身上 |
  | M6 `Watchlists.vue` 的 `erase` 去掉 `await deleteWatchlist(list.id)` | **红** 在 :366 那次真读回（200 而不是 404），而界面那句「片单已删除」照弹 |
  | M7 去掉 `Watchlist.items` 的 `cascade="all, delete-orphan"` | **红** 在 :334 的移出 toast（原预判是绿，见上一条） |

- **两句现状，记在这里而不是修掉**：界面那个前缀是中文、后半句是服务端英文原话（`保存失败：Watchlist 'E2E 乙号队列' already exists`），因为 `client.ts` 把 `detail` 摊平之后直接拼进那句 toast——第 18 条签的是同一条通路，只是这一路的英文此前没人读过；`PUT {description: ""}` 落进库里的是空串而不是 null，界面上 `.list-desc` 少一个元素，两种"没有备注"在库里分得开。
- **编号 26 是字母序白送的**：`watchlists` 排在 `video-transcode-mp4` 之后（`w` > `v`），前面 25 条的编号一个都没动。它对现场的约束只有两条：不扫源（所以第 16、17、19、21~24 条那批"自己造的文件自己收走"的规矩与它无关，`files_found` 那串数也不涨），以及它留下的片单行全部由自己的 `finally` 按身份删干净。整跑时 owner 已经有第 5 条和第 18 条留下的片单、solo 时一条都没有，所以断言一律取差值或"含不含我那几条的 id"；片单名字刻意取成互不为子串，因为 `panel()` 用的是 `hasText`。
- **收尾按 #120 的规矩**：`finally` 的 body 里不写断言，只做删除（先成员身份删掉成员那条，再换回 owner 删掉那两条），**在 `finally` 之后**用真读回核对 owner 的片单名集合、`GET /api/watchlists?video_id=1` 那份持有人清单回到起点、影片 200、通知数未变。
- **验证**：新用例单独跑（Windows 控制台是 cp936，`-g 三条写路径` 走不稳，所以按文件路径 solo）**13.5 秒绿**；全套真后端 e2e **26 条 2.3 分钟绿**，报告里第 26 行就是它（13.2 秒）；`npx vitest run` **334 passed / 36 files**（一条没动）；桩 e2e **100 passed**——第一次跑有两条播放器用例在负载下抖红（`player.spec.ts:92` 进度条拖动、`:189` 音量记忆），重跑全绿，这两条是已知的定时器/播放抖动，本单没碰播放器；`npm run typecheck:test` 无输出，`npm run build` ✓ built in 786ms。`backend/src/` 在变异跑完之后按 md5 逐字复位（`watchlist_service.py` `e0d4e44d…` / `models/watchlist.py` `07246594…` / `Watchlists.vue` `650561e4…`），所以后端那 754 条、`ruff`、`mypy` 都没重跑——这一单在代码里只多了一个 `frontend/e2e/real/` 文件。文档同步：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 的计数 25 → 26（含替身覆盖段那句"语义只有 `e2e/real/` 那 26 条签"）、`frontend/CLAUDE.md` 的顺序段添第 26 条的位置与 `-g 三条写路径`（十八条 → 十九条）、`backend/CLAUDE.md` 的薄位置清单里记下那两行现在的签字处在浏览器那一头。

### 转码表里 mp4 那一行从来没有一个真产物签过（#144）：换掉**源**而不是换掉目标

- **这一格为什么一直漏着**：`utils/ffmpeg.py` 那张四行配方里 `mp4` 那一行是 `{libx264, aac, .mp4}`，检查的是**输出**。播种那部本来就是 `.mp4`，而 `transcode_service.py:83` 的 `output_path` 拿源文件 `with_suffix` 拼，所以"目标 mp4"在第 15 条第 3 步只能换来那句同格式的 400——ffmpeg 从没为那一行起过一个进程。另一半是它不出口：`get_supported_formats` 只回 `codec` 和 `extension`，那两个编码器字面值从不进任何 API 响应。两件事叠起来，改错 `SUPPORTED_FORMATS['mp4']['acodec']` 在当时那 24 条真后端用例和 754 条后端用例里**一格都不红**（#115 量的正是这一格，#117 补的那条音轨只让另外三行红得动）。
- **做法**：换**源**，不换目标。现场 `ffmpeg -c copy`（不重编码，半秒）把播种那部 remux 成一部真 `.mkv` 放进媒体目录，扫进来得到库里的第二行，从那一行点 mp4——那道闸门比的是拼出来的路径和源文件是不是同一个，不比扩展名，于是放行，四行配方里最后一行第一次真跑起来。核对的还是只有真进程给得出的三样：产物文件头那几个字节是 `ftyp`（不看文件名）、`ffprobe` 报出的两条流正是 h264 + aac、通知 `data.video_id` 认的是这一行而不是播种那部的 1；`progress` 钉 100 钉的是"`_run` 成功就写 100"，不是编码器报到第几秒。夹具自己带一道钉子：remux 出来的 `.mkv` 必须真带着那条音频流——无声的源让 ffmpeg 把 `-c:a` 整个跳过，那半张配方就又查不到了（#115/#117 那一枪的延续）。
- **为什么单开一支文件**：这套用例的**编号就是执行顺序**（#136、#139 都为此改过文件名），而这一条要排在最后。写进 `transcode.real.spec.ts` 它会物理上落到第 18 位，那要么推动后面七条的编号（那些数字在 CHANGELOG 的历史条目里也出现，历史不改写），要么让文档里的"第 25 条"和报告里的第 25 行不是同一条用例。`video-transcode-mp4` 排在 `video-tags` 后面是 `tags` < `transcode` 的字母序给的。代价是它要的配方表（`CONTAINER` / `STREAMS`）和读产物的几句断言得从 `transcode.real.spec.ts` 里搬出来——现在两个 spec 共用 `e2e/real/transcode_support.ts` 一份（抄第二份就变成两张表各自红，正是 #143 记下的那个病根）。
- **六次变异**（每次改单点、跑完立刻按字节还原并核 md5：`src/utils/ffmpeg.py` `b18c9b52…` / 新 spec `fda9804c…` / `transcode_support.ts` `8a57ce29…`，六次全部回到原值）：
  - M1 `mp4` 那行的 `acodec` 改成 `libmp3lame` → **整套只红第 25 条那一条**（1 failed / 24 passed）。这一条就是本单的全部理由：这一格从前改了没人红。
  - M2 `mp4` 那行的 `codec` 改成 `libvpx-vp9` → 红在产物的两条流对不上配方。
  - M3 remux 时加 `-an` 丢掉音频流 → 红在夹具自己那道钉子上（无声的源确实查不到那半张配方）。
  - M4 通知改成按播种那部的 id 断 → 红在 `toMatchObject`（`data.video_id` 认的是这一行）。
  - M5 期望的容器魔数换成文件里绝不存在的串 → 红，`Received` 里露出 `ftypisom…` 那段真字节。
  - M6 把 `STREAMS.mp4` 的期望改成 opus → **红在第 73 行那道钉子，不是产物断言**。这是一条要记下的边界：`STREAMS.mp4` 这一个常量同时钉着"源有两条流"和"产物有这两条流"，改它能红，但只证明有人读它。产物那半的独立签字是 M1/M2——那两次改的是 ffmpeg.py 里的配方，也就是产品自己。
- **没做的（新量出来的一件，等你点头）**：转码产物写进的就是**被扫描的那个媒体目录**（`transcode_service.py:83` 的 `output_path` 是源文件 `with_suffix`），而扫描只按扩展名收（`file_scanner.py:27` 那一句 `if ext in VIDEO_EXTENSIONS`），没有任何"这是产物"的标记——所以下一轮定时扫描会把它当成一部新片子登记进库。e2e 这一套看不出来，是因为每一条都把自己的产物删干净了（第 15/16/17/25 条都是）。这一单没动它，也没顺手修：修法要么给产物另设目录、要么给 `output_path` 那一路立一个"扫描不认"的约定，两条都是产品决定。
- **基线**：真后端 e2e 24 → **25 passed**（整套 2.2 分钟，新那条 solo 5.1 秒 / 整跑 4.9 秒，`-g mp4` 只命中它，且报告里的第 25 行就是它）；后端 **754 passed** 不变（这一单只有测试与文档，产品代码一行没动）；Vitest **334**、替身 e2e **100**、`npm run build`、`typecheck:test` 全绿。

### 外挂字幕在菜单里叫 `chi`、`zh`，内嵌那一条叫「中文」（#143）：两条来源现在共用一张名字表和一次文件名切分

- **症状**：同一个字幕下拉框里两种命名——内嵌那一路把 ffprobe 的语言标签翻成中文，外挂那一路存的是文件名后缀的原文，而真库上读一眼就知道这不只是测试里的事（那两行的 `label` 是 `en` 和 `zh`）。往下量出四处，根子是**两条写路径各自从文件名里切一次**：`movie.chi.srt` 扫描归一成 `zh`、手工 POST 存成 `chi`（那一列还要当 `srclang` 用）；`movie.mp4.zh.srt` 手工切出来的是 `mp4.zh`，两个字段都是；`movie.zh-CN.srt` 的显示名丢了地区；而 `language` 在真库是 `VARCHAR(10)`，手工那条路把整个后缀塞进去，一部 `movie.这条是导演评论加长版说明.srt` 直接换来一次 `value too long` → 界面 500（客户端传的值有 `Field(max_length=10)` 挡成 422，服务端自己派生的那一路没人挡）。
- **修法**：`utils/subtitles.sidecar_identity(video, subtitle) -> (language, label)` 成为两条写路径唯一的出处，文件名切分也收进 `_sidecar_suffix`（`None` 表示不是这部片子的字幕；扫描据此跳过 `movie.mkv.zh.srt` 这类兄弟文件的字幕，手工那条路保持“允许挂隔壁的文件”的现状）。`media_streams` 那张私有名字表上移成 `subtitles.LANGUAGE_NAMES`，两边都通过 `language_display_name` 取名。两条政策写进函数而不是注释：认不出的代码原样返回（`nor` 还是 `nor`），地区保留（`zh-CN` → `中文（CN）`）——名字表只认到语族，折掉地区就让简中繁中两条在菜单里同名、点不开。非语言后缀的 `language` 一律 `None`，说明性文字只进 `label`，那一列再不会因为名字长而炸。
- **用例**：`tests/test_utils/test_subtitles.py` 四条新的（外挂名字走同一张表、未知代码原样、地区保留、无后缀时用影片主干名兜底）加三处从现状翻过来的 `label` 钉子；`tests/test_api/test_subtitles.py` 两条新的（手工和扫描必须给出同一对字段；后缀不是语言代码时 `language` 留空——这条就是那个 500 的回归位置）；`tests/test_services/test_subtitle_service.py` 一处翻转。翻转的钉子对着修前的 HEAD 全是红的（`'chi' != '中文'`、`'mp4.zh' != '中文'`、`value too long`），那条兜底现状钉子改前改后都绿，留着是因为它是兜底那一步唯一的护栏。真后端 e2e 第 22、23 条里把“一边中文一边裸码”钉成现状的断言这次一并翻成 `['关闭','中文','英文','日文','韩文']`。基线 753 → **754** passed（真库 PostgreSQL，5:42），ruff/mypy 干净（mypy 仍是文档里那 34 条），前端 334/36 + 替身 100 + 真后端 24 全绿。
- **九次变异**（每次改单点、跑完立刻按字节还原并核 md5：`src/utils/subtitles.py` `ba84f173…` / `src/utils/media_streams.py` `b7e76de8…` / `src/services/subtitle_service.py` `199cab81…`）：外挂 `label` 退回后缀原文 → 后端红 7 条，且真后端 e2e 第 22、23 条**一起红**（浏览器那一头的名字钉子是真能红的）；显示名丢掉地区 → 2 红；未知代码编出一个「未知语言」→ 1 红；`_sidecar_suffix` 不再剥掉影片自己的扩展名 → 2 红（扫描和手工各一，证明这一处现在两头都在用）；兜底那一步不给名字 → 1 红；手工那条路不再派生 → 4 红；内嵌那一路退回裸码 → 2 红；内嵌改回**自己的一份同名表**（M8）→ **全绿**，记在这儿：这一层的共享只是 DRY，内嵌的行为一个字没变；扫描不再跳过兄弟文件的字幕（M9）→ 1 红。
- **没做的**：真库里那两行老 `label`（`en` / `zh`）不会被这次修复改名——扫描只往里加、不重列已有的行，在扫描里顺手改写别人手工编辑过的字段是一条新的写路径，这一单不背着人加；要么重新挂一次那两条字幕，要么自己跑一句 `UPDATE subtitles SET label = …`（等你点头）。播放器对“这条轨加载失败”仍然没有任何可见提示（`VideoPlayer.vue` 只挂 `load` 不挂 `error`），这是 #142 就记下的同一格产品决定。

## 2026-10-06
### 外挂字幕转换失败那句把 ffmpeg 的原因丢了（#142）：两条转换路径共用同一句"最后一行"

- **症状**：sidecar 那条路（`utils/subtitles._ffmpeg_to_webvtt`）失败时抛的是写死的「字幕转换失败」，ffmpeg 自己那两行 stderr 一个字都没进消息；而内嵌轨那条路（`utils/media_streams.extract_subtitle_webvtt`）一直把最后一行放进去。两个路由都是 `detail=str(e)` 翻成 415，于是同一件事在浏览器这边一边能诊断、一边只有四个字——那个人点了菜单里那条轨，手上只有一部手机。
- **修法**：把「取 stderr 最后一条非空行」抽成 `subtitles.ffmpeg_stderr_reason(stderr, fallback)`，两条路各自只留下自己的前缀和"子进程什么也没说"时的那句兜底。顺带把 sidecar 那条 415 的路由用例从"只看状态码"升级成"再看那句话有没有原样走出来"，和内嵌那条对齐。实测真 ffmpeg 8.x：后缀写着 `.ass`、内容不是字幕 → 退出码 183、stderr 两行，最后一行 `Error opening input files: Invalid data found when processing input`；拿不到子进程真消息时那句 `字幕转换失败：…` 只剩兜底。
- **用例**：`tests/test_utils/test_subtitles.py` 两条新的（前者钉 ffmpeg 那句话在消息里，后者钉 rc=0 而 stdout 空时兜底那句话仍然说完整），`tests/test_api/test_subtitles.py` 那条 415 多一个断言。两条新用例先对着修前的 HEAD 红过：`assert '字幕转换失败' == '字幕转换失败：这个文件没有转出任何字幕'`。基线 746 → **748** passed（真库 PostgreSQL，3:07）。
- **六次变异**：每次改单点、跑完立刻按字节还原并核 md5。M1 回到写死那句 → 新两条一起红；M2 改成取第一行 → 侧车那条 + 内嵌那条 `test_extract_reports_an_unconvertible_track` 一起红（这条规则两头都有人钉着）；M3 兜底写成空串 → 1 红；M4 把 `or not (result.stdout or "").strip()` 那一支删掉 → 1 红（只看返回码就漏掉"转出一个字节也没有"）；M5 把内嵌那一路改回它自己的内联写法 → **全绿**，记在这儿：共享只是 DRY，内嵌的行为一个字没变；M6 把路由改成写死的 415 消息 → 只有那条路由用例红。
- **没做的**：播放器对"这条轨加载失败"仍然没有任何可见提示——`VideoPlayer.vue` 的 `bindTrackTiming` 只给 `<track>` 挂 `load`，不挂 `error`，所以这句话到不了界面；这是产品决定，等你点头。真 e2e 第 22 条也没加第四份字幕文件（它钉的是那三轨的 `toEqual`）。
### 用户管理那一格把已经死掉的会话也算成一台设备（#141）：读之前先把过期那几行删掉

- **症状**：`sessions` 里过期的那一行，只有被**它自己的**那枚 Cookie 再带回来一次才会被删（`resolve_session` 一边拒绝它一边删它）。可两处按列表读的路径永远等不到那一次——`/api/auth/sessions`（「我的设备」）把它列成一台还登着的浏览器，`/api/users` 的 `signed_in_devices` 把它数进「登录设备」那一格。一台关掉一个月的手机因此会永远挂在那里，旁边那句"30 天前"只会让人以为是自己记错了。`list_sessions` 的 docstring 早就写着"行会随过期自己消失"，这一句在修复前是假的。
- **修法**：`AuthService.purge_expired_sessions(user_id)` 一个方法，`list_sessions` 与 `api/users.py::_payload` 各调一次（后者在那一格的 count 之前）。选择删掉而不是加一道过滤，是因为第三处口径在写路径上：停用、重置密码、踢下线那句「已退出 N 台」回的是 `revoke_sessions` 删掉的行数，只改读的一侧就会变成"那一格说 0、那句话报 3"，仍然不同温；行真没了，四处自然一致，这张表也不再只涨不消。
- **用例**：两条都是先看红的。`tests/test_api/test_users.py` 在夹具那一行活的旁边播一行已过期的，`signed_in_devices` 回来的是 2；`tests/test_api/test_auth.py` 那台"手机"真登录之后把它的 `expires_at` 搬到一小时之前，「我的设备」仍然列两行。两条各带一句**先回滚再读表**：一条没提交的 DELETE 在同一个会话里同样"看不见"，只有回滚会把它原样还回来（M4 就是被这一句抓到的）。过期时刻写死成"现在减一小时"，不从"记住我"那 30 天里减几天——那个数字一改，这一条就会静默地变成在测一个还活着的会话，而它看上去仍然像在测过期。
- **五次变异**（每次改完单跑那两只文件、跑完还原并核对 md5）：`list_sessions` 不再清 → 红在设备列表那一条；`_payload` 不再清 → 红在 `signed_in_devices` 那一条；判据 `<=` 换成 `>=` → 9 条红（凡是"列出自己的设备"的用例全红，因为被删的是活的那一行）；删了但不提交 → 这一单新加的两条都红；不分过期、把这个人全删 → 同样 9 条红。前两次各只红一条，是这一单最干净的两根签名线。
- **没做的**：这一格仍然只跟着**这一台浏览器自己的写**重读（#135 记下的边界），本单没加轮询也没加刷新按钮；前端一行没改，两个数字都是服务器算出来的。基线：后端 744 → **746** passed（真库 PostgreSQL），ruff/mypy 干净。
### 修掉字幕转换里那一个空 cue（#140）：ASS 的 `\N` 被 WebVTT 当成"这条 cue 到此为止"，第 22 条钉成的那三格现状这次真翻了

- **症状**：第 22 条（#138）当初把一句现状钉在断言里——那条外挂 ASS 的响应体里词都在，浏览器解析出的却是 `[CUE_ASS_ONE, '']`：菜单里点得动、一句也不显示。根因在 ffmpeg 的 WebVTT muxer：它把 ASS 的 `\N` 写成**一次真的换行**，于是一条以 `\N` 开头的 Dialogue 出来是"时间戳行 + 空行 + 那句词"，而 WebVTT 里时间戳后面紧跟空行的意思就是"这条 cue 到此结束"，那句词因此落在所有 cue 之外。本机真 ffmpeg 8.x 两条出口都量过字节：sidecar 那条（`subtitles._ffmpeg_to_webvtt`）吐出 `00:10.000 --> 00:12.000\n\n外挂 ASS·第二句…`，内嵌那条（`media_streams.extract_subtitle_webvtt`）在同一部 mkv 上吐出的是 `00:05.000 --> 00:08.000\n\n内嵌ASS第一句…`——**空行出现在第一条 cue 上而不是第二条**，所以按"第几条"写规则是错的，得按"紧跟时间戳"写。
- **修法**：`subtitles.fold_blank_lines_inside_cues()` 一个函数，三条**转换**支路各套一次（`.srt`、`.ass/.ssa`、内嵌提取），不是套在两个 ffmpeg 出口上——纯 Python 的 `srt_to_webvtt` 也给得出同一个形状（SRT 里那段空行本来就是合法写法），汇合处只有一处。两道闸门各有自己的用例：**只有下一行非空且不是时间戳行才折**，真·空 cue 的分隔符因此保住，否则下一条 cue 的时间戳会被吞进上一条的文本里；**第一条时间戳之前的区域一个字不碰**，那是 `WEBVTT` 头和可选的 cue 标识，它的空行是语法要求。第二道闸门是真后端 e2e 教出来的：第一版没有它，第 23 条红在 `:569`——那份没有 BOM 的 UTF-16 转回来的文本里**没有任何一行认得出时间戳**，于是整份文件的头部空行被当成 cue 内空行折掉了，`text.startsWith('WEBVTT\n\n')` 当场失效。
- **边界**：`.vtt` 依旧原样透传，**正好是同一个形状也不动**。这一单改的是**应用自己写出来的** WebVTT，不是别人写好的文件；`test_convert_vtt_stays_byte_faithful_even_with_the_same_shape` 就是划这条线的，它用 `open(..., newline="")` 按 LF 落盘，因为这一句比的是"一个字节都不许动"，换行法不能由写入模式决定。
- **用例**：`tests/test_utils/test_subtitles.py` 五条新的、`tests/test_utils/test_media_streams.py` 一条新的，夹具是上面量回来的真字节。`_touch` 走文本模式，本机落到磁盘就是 CRLF，所以那两条比字节形状的用例刻意绕开它按 LF 写——这里要的是"时间戳行后面紧跟一个空行"那**一个**形状，不是两种换行法叠出来的形状。
- **第 22 条那三格**：响应体翻成 `'00:10.000 --> 00:12.000\n' + CUE_ASS_TWO`，并加一句反向的 `not.toContain('00:12.000\n\n')`（不许顺手把所有空行都删掉），浏览器那两处从 `[CUE_ASS_ONE, '']` 翻成 `[CUE_ASS_ONE, CUE_ASS_TWO]`（第 6 步那条 `toContainEqual` 和三轨 `toEqual` 里第一条）。第 21 条不受影响：那个容器里两条轨是 `mov_text` + `ttml`，没有以换行开头的 Dialogue。
- **七次变异**（每条改完单跑一次，跑完按字节还原并核对 md5：`src/utils/subtitles.py` `1f2876fe…` / `src/utils/media_streams.py` `90f23b07…`，七次全 `restored=True`）：
  - fold 整个变成 no-op → 红 3 条（sidecar、srt、内嵌提取各一），真后端 e2e 第 22 条一起红在响应体那一句；
  - 折掉"下一条是时间戳就不许折"那道闸门 → 红在「真·空 cue 的分隔符还在」和内嵌那条（第二条 cue 前的 `\n\n` 没了）；
  - 折掉"头部之前不许动"那道闸门 → 红在「什么都解析不出来时头部空行还在」，就是第 23 条踩过的那一枪；
  - sidecar 支路不套 fold → 红在 ass 那条 + 第 22 条 e2e；
  - `.srt` 支路不套 → 红在 srt 那条；
  - 内嵌提取不套 → 红在内嵌那条；
  - `.vtt` 支路**套上** fold → 红在字节忠实那条。这一枪是给边界上的，不是给修复上的——它证明那条断言不是摆设。
- **基线**：后端全量 **744 passed**（原 738，+6 全在这单的两份测试文件里），`tests/test_utils/test_subtitles.py` + `test_media_streams.py` **27 passed**（原 22），真后端 e2e **24 条全绿**，桩 e2e **100 passed**，Vitest **334 passed**，`typecheck:test` 干净，`ruff` 全绿、`mypy` 对这两份源文件干净。

### 加宽真后端 e2e（#139）：外挂字幕的编码那一路——GBK / UTF-16 / BOM 四种真字节走到浏览器，少了 BOM 那一份安静地什么都没有

- **缝在哪**：`backend/src/utils/subtitles.py::read_subtitle_text` 那两个编码分支。服务层那 12 条只有一条碰过编码（`test_read_subtitle_text_falls_back_to_gb18030`），而 `utf-16`（BOM 判据）和 `utf-8-sig`（剥 UTF-8 BOM）两支**全仓库零用例**——实测把 `if raw.startswith((b"\xff\xfe", b"\xfe\xff")): return raw.decode("utf-16")` 那两行整个删掉，`tests/test_utils/test_subtitles.py` 与 `tests/test_api/test_subtitles.py` 那 30 条一条都不红。桩用例这一头更直接：`fixtures.ts` 那个 stream 处理器无论问哪一条都回同一段 UTF-8 的 `SAMPLE_VTT`，"这份文件是什么编码"在桩面上结构上不存在。
- **夹具**：同一部复制的 `.mp4` 旁边四个文件，**同一个句子的四种编码**——GBK 的 `.chi.srt`、UTF-16LE 带 BOM 的 `.eng.srt`、UTF-8 带 BOM 的 `.jpn.vtt`、以及把带 BOM 那一份的前两个字节砍掉的 `.kor.srt`。Node 的 `Buffer` 编不出 GBK，所以那 136 个字节是 base64 抄进 spec 的；它的含义不由注释签，由「响应体逐字等于那两句词」和 `writeEncodingFixtures()` 自己的三道夹具钉子签（GBK 与 UTF-16 那两份里**不许**出现这句话的 UTF-8 字节、必须出现 `0xB1 0xE0`（「编」的 GBK 写法）、带 BOM 与不带 BOM 那两份只差前两字节、`.vtt` 去掉前三字节必须逐字等于写进去的那段）。
- **这一条量出的现状（只有一句）**：没有 BOM 的 UTF-16LE 会被当成 UTF-8 **成功**解码，回来的是夹着 NUL 的一串，于是 `_TIMESTAMP_RANGE` 和 `isdigit()` 那道过滤双双落空——路由仍然 200、仍然以 `WEBVTT` 开头，浏览器把那条轨标成 loaded（`elementState` 2）而 `cues.length === 0`：菜单里照旧可点，点了照旧一个字节也没有，连 `.subtitle-menu-note` 都不出现。和第 22 条第 5 步那个"200 而零条 cue"是同一个形状。所以这条同时钉两头：认得出编码的三份必须逐字对上服务器交出的那一段，认不出的那一份必须**安静地什么都没有**（断的是 200 + 体里有 `\u0000` + 体里没有那句话 + 磁盘上那份文件本身用 `utf16le` 读仍然带着那句话）。
- **两件"断言本身的前提"是实测出来的**：① `fetchInPage` 用 `new TextDecoder()` 读 body，它会吃掉前导 U+FEFF，所以 **BOM 在文本断言里是隐形的**——第一次把 `utf-8-sig` 换成 `utf-8` 跑，两支用例全绿，只有 `bytes`（`body.byteLength`）分得开；② **Starlette 对任何 `text/*` 的 media_type 自动补 `; charset=utf-8`**，所以 `api/subtitles.py` 里那句显式 charset 删掉也不 observable（变异 M4 因此全绿——那不是用例写松了，是断言的对象压根不存在，故只记不修）。顺带还量到 Chromium 对**带 BOM 的 WebVTT 响应照收不误**（轨是 loaded、cue 全在），所以服务器剥没剥 BOM 在浏览器那头永远分不出来。
- **七次变异**（每条改完单跑 `npm run test:e2e:real -- e2e/real/video-sidecar-subtitles.real.spec.ts`，跑完按字节还原并核对 md5：`utils/subtitles.py` `47ee9bcc…` / `api/subtitles.py` `0eee6f49…` / `src/api/subtitles.ts` `2976fd27…`）：
  - 删掉 UTF-16 BOM 那一支 → 只有第 23 条红，红在 `:547`（UTF-16 那份的响应体整段变乱码）；
  - `utf-8-sig` → `utf-8`（不再剥 BOM）→ **第一次全绿**，补上字节钉子后红在 `:560`（那句 message 写的就是「BOM 没剥掉的话这里是 +3」）；
  - `gb18030` → `big5` → 红在 `:530`（GBK 那两句词逐字比对）；
  - 删掉响应那句 `; charset=utf-8` → **全绿**（原因见上，只记不修）；
  - media_type 换成 `application/vnd.vtt` → 两支用例一起红（这一枪才是给 `contentType` 那句 `toBe` 上的）；
  - `.vtt` 改走 `srt_to_webvtt`（不再原样透传）→ 红在 `:554`（CRLF 被折成 LF、索引行跟着被滤掉）；
  - 把前端 `subtitleTrackUrl` 里的 `/stream` 写成 `/Stream` → **两支用例全红**：第 22 条红在 `:348`「那条外挂 ASS 没有被浏览器拉下来并解析成 cue」，第 23 条红在 `:590`「四种编码的字幕没有都变成浏览器里的 cue」。这是唯一一处从 `<track>` 的地址倒着同时咬住两个文件的变异，也是这条地址第一次被真浏览器签字（`builder-urls.spec.ts` 那把哨兵尺子只保证它拼得出来）。
- **编号推动**：新这条住在 `video-sidecar-subtitles.real.spec.ts` 里、写在第 22 条后面（同一支文件第二条），所以只有 `video-tags` 那一条从第 23 条变成第 24 条——连带它自己那行头注、`users.real.spec.ts:134` 与 `video-edit.real.spec.ts:23` 两处交叉引用，以及 README / 根 CLAUDE / frontend CLAUDE 的计数和「逐条」段落。顺手修掉一处早就存在的错位：`users.real.spec.ts` 那两处「后面的第 18、19、20 条」是 #136 插入取消那条时留下的（它自己就是第 18 条），现在换成不依赖条数的说法。
- **基线**：真后端 **24 条全绿**（两次整跑一次 3.3 分钟、一次 2.5 分钟，本机背景负载不同；新这条 solo 3.7 秒、整跑 2.7~3.6 秒，默认 30 秒超时够用；同文件的第 22 条整跑 4.3~5.5 秒），桩 e2e **100 passed**（58 秒），Vitest **334 passed**，`typecheck:test` 干净，`tests/test_utils/test_subtitles.py` + `tests/test_api/test_subtitles.py` **30 passed**——这一单**一行的 `backend/src/` 都没有改**，所以后端全量 738 没有重跑；那两个字幕文件跑的是变异全部按 md5 还原之后的代码。

### 加宽真后端 e2e（#138）：sidecar 字幕那一路——真 ffmpeg 真转一个 .ass，而"文件没了"在浏览器里有两副样子

- **缝在哪**：`backend/src/utils/subtitles.py`——`_LANGUAGE_ALIASES` 那张别名表、`find_subtitle_files` 的「同名 + 语言后缀」认文件、`srt_to_webvtt`（纯 Python）和 `_ffmpeg_to_webvtt`（真子进程）。服务层有 12 条用例（`tests/test_utils/test_subtitles.py`），认文件那一半是真 tmp_path，**转换那一半只有一条碰 ffmpeg**：`test_convert_ass_uses_ffmpeg` 把 `subprocess.run` 换成一份写死的 `CompletedProcess(stdout="WEBVTT\n\n")`——真 ffmpeg 遇到真 ASS 会吐出什么，从没被问过真进程。桩用例这一头更直接：`fixtures.ts` 的 `/videos/{id}/subtitles` 回的是手抄的两行，那个 stream 处理器无论问哪一条都回同一段 `SAMPLE_VTT`（#128 那道守卫只保证地址接得住，语义仍是零）。页面这一头第 9 条（`library.real.spec.ts`）早就签过播种那部的 `.zh.srt`，缺的是「三种语言一次认全」和「`.ass` 走的是一条子进程而不是那半条 Python」。
- **夹具为什么长这样**：把播种那部的字节 `copyFileSync` 成第二部（这一路要验的是认文件和转换，与画面无关），旁边写三个 sidecar：`e2e_sidecar.chi.ass`（带完整 `[Script Info]` + `[V4+ Styles]` 头）、`e2e_sidecar.eng.srt`（按字节写 CRLF，文本模式在 Windows 上会翻成 `\r\r\n`）、`e2e_sidecar.jpn.ass`（**只有 `[Events]` 段、没有头**）。那个头不是讲究出来的——本机实测：去掉 `[Script Info]` 的 ASS，ffprobe 报的是 `lrc`（「detected only with low score of 5, misdetection possible!」），ffmpeg 用 `text` 解码器读完，stdout 只有一句 `WEBVTT`、退出码 0，应用就此**回 200 而零条 cue**。所以 `writeSidecarFixtures()` 自己先把头钉一遍，写夹具的人（包括写它的我）把它丢了要红在夹具上而不是红在结论上。
- **六条变异全红**（每条改完单独 `npm run test:e2e:real -- e2e/real/video-sidecar-subtitles.real.spec.ts` 跑一次，跑完按字节还原并核对 md5：`utils/subtitles.py` `47ee9bcc…` / `api/subtitles.py` `0eee6f49…` / `services/subtitle_service.py` `21ab398d…` / `components/VideoPlayer.vue` `51ec498d…`）：
  - `_LANGUAGE_ALIASES` 删掉 `"chi": "zh"` → 红在 `:202`（`language` 那一栏从 `zh` 变回裸后缀 `chi`）；
  - `.ass` 改走 `srt_to_webvtt`（不碰 ffmpeg）→ 红在 `:238`：`{\an8}` 原样进了 WebVTT；
  - `_ffmpeg_to_webvtt` 的 `-f webvtt` 换成 `-f srt` → 红在 `:238`（ffmpeg 的 srt muxer 连覆写标记都不剥，出来的整段还是 SRT 形状）；
  - `api/subtitles.py` 那条 `except FileNotFoundError` 换成一个永不发生的异常 → 红在 `:327`：404 变 500，那句「字幕文件不存在」跟着没了；
  - `VideoPlayer.vue` 的 `subtitleLabel` 从 `label || language` 翻成 `language || label` → 红在 `:279`：菜单三项从 `关闭 / chi / eng / jpn` 变成 `关闭 / zh / en / ja`（这一枪签的是"界面上那个名字来自哪一列"，而它和内嵌那一路的「中文」本来就不对称）；
  - `SubtitleService.register` 里 `if path in known: return False` 改成 `return True`（不重复插行、但把它数成新增）→ 红在 `:179`：`subtitles_found` 从 3 变 4。第 3 步那次重扫断的是 `new_videos: 0 / subtitles_found: 0`，这两次是同一个去重集合跨两次 HTTP 事务——`known_paths` 每轮只查一次库，靠的是前面那条用例已经把行落进去了。
- **本单第一次红在哪（记下来省后人半天）**：第 7 步点 'eng' 那条 `.click()` 一直挂到用例超时，报出来的却是 `finally` 里那句 `fetchInPage`「Target page, context or browser has been closed」。真正的凶手是 `selectTrack` 收尾把 `showSubtitleMenu` 设回 false——菜单在第 6 步点完 'chi' 之后就不存在了，而 Playwright 等一个永远不出现的元素时不会替你分辨"没有"和"不可见"。修法是第 7 步自己重新点一次 `.subtitle-btn`。**顺带我原本写死的 `elementState: 3` 是猜的**：不重载时那条轨压根不再发请求，它放的是浏览器早就解析完存在内存里的旧 cue（`readyState` 仍是 2、那两句词照旧在），接口那句 404 谁也没听见；只有重载之后 `<track>` 才真的去拉一次并停在 3。两头都钉进去了——这比"文件没了就报错"那半句我想当然的写法有意思得多。
- **只有真文件给得出的东西才值得钉**：`language` 三格是别名表归一的 `zh`/`en`/`ja`，`label` 三格是**没归一**的原始后缀 `chi`/`eng`/`jpn`（界面读后者）；同一次转换里两种时间轴方言——Python 那条留小时（`00:00:03.000 -->`）、ffmpeg 那条省掉（`00:05.000 -->`），谁把两边统一成一种写法就说明其中一路没走真进程；`{\an8}`、`Dialogue:`、`ScriptType` 三个都不许在 WebVTT 里出现；SRT 那一路还有一正一反两条（序号行被 `line.strip().isdigit()` 剥掉、逗号时间戳归成点，而反面的「不许出现只含数字的一行」也在）；反面是那个"200 而零条 cue"——`broken.text.trim()` 必须**恰好**是 `WEBVTT`，那句词仍在文件里、却不在响应里。播放页那一头签的还是 `video.textTracks` 里浏览器自己解析出的 cue，三条轨一次看全（第三条就是那个安静洞在浏览器那一头的形状：`readyState` 2、cue 空清单、模式照常可切）。
- **两句钉成现状、不是愿望**：① ASS 那句以 `\N` 开头的词，ffmpeg 写成一次换行，而 WebVTT 里时间戳后紧跟空行的意思是"这条 cue 到此为止"——于是那句话**在响应体里**、到浏览器却是一条空串（`:246` 钉响应原文、`:292`/`:304` 钉浏览器读到的「第一句在、第二句是空字符串」）。修它的下一单要把这三处一起翻绿，spec 里已写明翻绿后该长什么样。② 扫描没有"字幕丢了"这一说：文件从磁盘上没了，行仍在清单里、条目仍在菜单里、没有任何一处提示。
- **顺序与编号**：新文件 `video-sidecar-subtitles.real.spec.ts` 落在 `video-embedded-subtitles` 与 `video-tags` 之间（字母序的结果），所以只有 `video-tags` 挪号：22→23（含 `video-edit` 与 `users` 两处头部引用）。它必须排在第 9 条（通知）之后——自己那趟扫描会往 `notifications` 真写一行；它在**被扫描的那个媒体目录里**写四个文件，起点断的是 `files_found=2 / new_videos=1 / subtitles_found=3`，所以那四个和那一行影片必须由自己的 `finally` 收干净，否则第 23 条那次扫描的 `files_found` 就不是 2。总数 22 → 23：`README.md:391`、`CLAUDE.md:205`、`frontend/CLAUDE.md`（648 那句「那 22 条签」→ 23；671 的逐条段插入本单整段；678 的顺序链与 `-g` 清单各加一条、「第 15~22 条」→ 15~23、「第 15 条排在倒数第八条」→ 第九条并补上外挂字幕、「第 20 条排在倒数第三条」→ 第四条、内嵌那条末尾的「留在磁盘上第 22 条那次扫描」改成 22、23 两条；顺带还清两笔旧账——748 那句从 #125 起就欠的「16 条打真后端」改成 23，`-g` 清单那句数错的「十四条命令」（实列十六条）改成十六条）。
- **基线**：真后端 **23 条 2.4m 全绿**（新这条 solo 4.6 秒、整跑也是 4.6 秒，默认 30 秒超时够用），桩 e2e **100 passed**（第一次整跑红过一条、后两次 100 全绿——本单一个字没动 `fixtures.ts` 和那 100 条，症状是 #126 记过的计时类 flake）、Vitest **334 passed**、后端**全量 738 passed**（这一单动过 `backend/src/` 的三个文件，所以全量重跑过，跑的是 md5 核对还原之后的代码）、`typecheck:test` 干净。跑完 `data/e2e/media/` 实测回到 `e2e_sample.mp4` 与 `e2e_sample.zh.srt` 两个文件，`git status` 只剩这一份新 spec。

### 加宽真后端 e2e（#137）：内嵌字幕那一路——真 ffprobe 报出那两条轨、真 ffmpeg 抠出那两句、浏览器把它们渲染出来

- **缝在哪**：`backend/src/utils/media_streams.py` 那两个函数——`probe_streams`（问 ffprobe 这个文件里有哪几条字幕轨、哪条转得了）和 `extract_subtitle_webvtt`（问 ffmpeg 把其中一条抠成 WebVTT，写 stdout、不落盘）。服务层有 9 条用例（`tests/test_utils/test_media_streams.py`），**其中 8 条把 `subprocess.run` 换成一份手写的 ffprobe JSON**、第九条连子进程都不碰（它在「文件不存在」那一步就抛），于是「真容器会被 ffprobe 报成什么样」从没被问过真进程：`WEBVTT_CODECS` 那道 `supported` 闸门、`_LANGUAGE_NAMES` 里 `chi → 中文` 那一格、`stream_index` 与 `position` 的区别（前端拿前者拼提取地址）、`_label_of` 的三级兜底、ffmpeg 自己那句失败原因——全是对着我自己造的字典测出来的。桩用例这一头更直接：`fixtures.ts` 那份 `/subtitles/streams` 处理器永远回 `subtitles: []`，`/subtitles/embedded/{n}/stream` 无论问哪一条都回同一段写死的 `SAMPLE_VTT`（#128 那道守卫只保证地址接得住，语义仍是零）。
- **夹具为什么长这样**：一部 `ffmpeg` 当场编出来的 mp4，h264 + aac + 两条字幕轨（`mov_text` 挂 `language=chi`、`ttml` 挂 `language=eng`）。**不是 PGS/DVD 那种图像字幕**：本机 ffmpeg 只允许「文字转文字、图像转图像」的字幕编码（`-c:s dvbsub` 直接回 `Subtitle encoding currently only possible from text to text or bitmap to bitmap`），手边没有 bitmap 源，而 `ttml` 是 `WEBVTT_CODECS` 清单外唯一还能由文本编出来的那一格——`supported: false` 因此照样有真容器可对，且它反过来**送出一个真 415**（ffmpeg 没有 ttml 解码器，`-c:s webvtt` 在那条轨上真的失败一次，那句原因是它自己的 stderr 尾巴）。`ttml` 只肯装进 mp4，matroska/webm 回 `-40 Function not implemented`。SRT 写在系统临时目录而不是媒体目录：扫描是递归的，落在媒体目录就会被认成 sidecar 字幕，`subtitles_found` 不再是 0。
- **七条变异全红，这一单没有拆不红的护栏**（每条改完单独 `-g 内嵌字幕` 跑一次，跑完按字节还原并核对 md5：`utils/media_streams.py` `0537e890…` / `api/subtitles.py` `0eee6f49…` / `components/VideoPlayer.vue` `51ec498d…`）：
  - `WEBVTT_CODECS` 里加 `ttml` → 红在 `:181`（`supported` 那一栏 false 变 true）；
  - `_LANGUAGE_NAMES` 删掉 `chi` → 红在 `:181`（label 退回裸码 `chi`）；
  - `extract_subtitle_webvtt` 去掉那个 subtitle-only 过滤 → 红在 `:241`：视频轨（0）和音频轨（1）从 404「文件里没有编号为 N 的字幕轨」变成 415（`Encoder not found`），这一枪签的是「提取的候选不是用全部流建的」；
  - `api/subtitles.py` 去掉 `except SubtitleConversionError` → 红在 `:230`：415 变 500，那句 ffmpeg 原话也跟着没了；
  - `probe_streams` 的 `stream_index` 换成 `position` → 红在 `:181`（2/3 变 0/1）；
  - `VideoPlayer.vue:446` 去掉 `.filter(track => track.supported)` → 红在 `:260`：菜单里三项 `关闭 / 中文 / 英文`，而「英文」那条点下去只会拿到一个 415；
  - `_label_of` 的兜底从 `轨道 {position + 1}` 改成 `轨道 {position}` → 红在 `:201`（音频那条 label 变「轨道 0」）。
- **本单第一次红在哪**：`.subtitle-btn` 等 20 秒等不到。播放器挂在 `VideoDetail.vue` 的 `v-if="isPlaying"` 下面，不点那张海报它压根不存在——快照里前四步全对、页面停在详情页，这一句写进了用例头部。
- **只有真文件给得出的东西才值得钉**：`stream_index` 必须是 2 和 3 而不是 0 和 1（前端拿它拼提取地址，差一位就问视频轨要字幕）、`container` 是 ffprobe 自己那串 `mov,mp4,m4a,…`、`label` 一栏走的是 `chi → 中文` 和音频那条的三级兜底 `轨道 1`、`supported` 一真一假，反面是同一次请求里播种那部的 `subtitles: []`；提取那一路是 `embedded/2/stream` 200 + `text/vtt` + 现场编进容器的那两句（替身那段和 sidecar 那句都不是这两句）、`embedded/3/stream` 415、`embedded/0` 与 `embedded/1` 404。播放页那一头签的是**浏览器自己解析出来的 cue**：`video.textTracks` 里那条轨的 cue 文本必须等于现场写进容器的那两句——这是整套里唯一「真进程 + 真容器 + 真浏览器」三方都在场的断言。
- **顺序与编号**：新文件 `video-embedded-subtitles.real.spec.ts` 落在 `video-edit` 与 `video-tags` 之间（字母序的结果），所以只有 `video-tags` 挪号：21→22（含 `video-edit` 与 `users` 两处头部引用）。它必须排在第 9 条（通知）之后——自己那趟扫描会往 `notifications` 真写一行；它起点断的 `files_found=2` 也要求它把现编那个 `.mp4` 由自己的 `finally` 收干净，否则第 22 条那次扫描就不是 2 了。总数 21 → 22：`README.md:391`、`CLAUDE.md:205`、`frontend/CLAUDE.md`（648 那句「那 20 条签」是从 #135 起就欠的账，一并改成 22；671 的逐条段插入本单整段；678 的顺序段与 `-g` 清单各加一条、「第 15~20 条」→ 15~22、「第 15 条排在倒数第七条」→ 第八条并补上内嵌字幕、「第 20 条排在倒数第二条」→ 第三条）。
- **基线**：真后端 **22 条 2.4m 全绿**（新这条 solo 8.6 秒、整跑 3.4 秒），桩 e2e **100 passed**（第一次整跑就绿）、Vitest **334 / 36 文件**、`typecheck:test` 干净。被变异过的三个文件字节级回到基线（md5 逐个核对），故全量 pytest / `ruff` / `mypy` 未重跑，只把 `test_media_streams.py` 与 `test_subtitles.py` 在还原后的代码上重测一遍（27 passed）。跑完 `data/e2e/media/` 实测回到 `e2e_sample.mp4` 与 `e2e_sample.zh.srt` 两个文件，临时目录里没留下 `e2e-sub-*`。

### 加宽真后端 e2e（#136）：转码取消那一路——被杀掉的是一个真子进程，半截产物真的从磁盘上没了

- **缝在哪**：`backend/src/utils/ffmpeg.py:126-132` 那段 `except asyncio.CancelledError`（kill → wait → `unlink` 输出 → 再 raise）**在全仓库一处也没有被执行过**。服务层唯一那条 cancel 用例（`tests/test_services/test_transcode_service.py` 的 `test_cancel_stops_the_job_and_records_it`）把 `transcode_video` 整个换成一个挂在 `asyncio.Event().wait()` 上的假函数，于是它签的是"作业状态机记得住 cancelled"，而真进程有没有被杀、半截文件归谁管，两句都不在它的路径上；100 条桩用例那份 cancel 处理器更是只把一个字符串改成 `'cancelled'`，顺带回 200 `{ok:true}`，而真路由回的是 **204 空体**。
- **怎么让一个真任务追得上**：现场是一部现编的 15 秒 720p 真片子（`writeSlowClip`），同一份字节两种速度——vp9 编它要好几分钟，末尾重编成 mkv（libx264）只要几秒。播种那部 5 KB 黑屏编成 webm 只要 0.06 秒，点不到「取消」就已经跑完，追一个已经结束的任务得到的会是第 15 条已经签过的那个 404。
- **五个变异，四红一绿**（每个改完单独 `-g 转码取消` 跑，跑完原字节写回并核对 md5：`utils/ffmpeg.py` `b18c9b52…` / `services/transcode_service.py` `9ffd03fe…` / `views/Transcode.vue` `cf01ce17…`）：
  - 删掉 `Path(output_path).unlink(...)` → 红在 `transcode.real.spec.ts:580`（`existsSync(partial)` 应为 false），4.2 秒；
  - 删掉 `_run` 里那句 `raise`（于是取消也会写一条 `transcode_error` 通知）→ 红在 `:587`，通知总数 3 比 2；
  - 把 `Transcode.vue` 里那句 `await cancelTranscode()` 打桩掉 → 红在 `:567`：**toast「转码已取消」照样弹**，而 `.status-section` 停在「转码中」——那句成功提示是前端自己写的，所以这一条不许只认 toast，这一句写进了用例头部；
  - 删掉 `proc.kill()` → 红在 `:566`：那个 POST 压根不返回（服务层在 `await` 一个没人杀的编码器），连 toast 都弹不出来。这一枪顺带签掉了比预期更强的一句：**204 是等到子进程真没了才发的**；
  - **绿的那一个是有预期的**：删掉 `cancel()` 末尾那句兜底（`if job.status == "running": job.status = "cancelled"`），本条和服务层 11 条全绿——`_run` 在 re-raise 之前已经写过 `cancelled`，那是个**死分支**。这里只记不删：删代码是行为变更，不是一条测试用例的份内事。
- **两句量出来的实话，不是一开始写出来的**：「取消之前磁盘上先有那个半截文件」这一句只能核**存在**、不能核字节——ffmpeg 的 muxer 带缓冲（32 KB 才落一次盘），而正被写的文件在 Windows 上不一定读得动，实测第一版拿 `size > 0` 轮询 30 秒读到 0。这是本仓库第三次撞到"要断的是那条路径真的跑过的副作用"。
- **`finally` 里的清理不许抛**（本条立的一条通用规矩）：Windows 上刚被真 ffmpeg 读过的那个输入文件，紧接着 unlink 会得到 `EBUSY`（重试 10 次也穿得过），而 **`finally` 抛出的异常会顶掉 try 块里那个真正的断言失败**——M4 第一次跑报出来的就是一句 unlink 错误，用例红了哪一步完全看不见。现在那句清理带 `maxRetries` 并 catch 掉，下一轮 `e2e_seed.prepare_media()` 的 rmtree 兜底。
- **顺序与编号**：本条落在 `transcode.real.spec.ts` 的第三个 `test`，没有新起 `transcode-cancel.real.spec.ts`——文件名里 `-`（45）排在 `.`（46）之前，那份新文件会插到 `transcode` 前面，推动的是六条而不是四条。于是 `users` 17→18、`video-delete` 18→19、`video-edit` 19→20（含头部引用 `video-tags` 那一处）、`video-tags` 20→21；总数 20 → 21，`README.md:391`、`CLAUDE.md:205`、`frontend/CLAUDE.md`（671 的逐条段、678 的顺序段与 `-g` 清单）跟着改口。顺带纠正 678 里四处从 #134 起就在欠账的数字：「第 15 条排在倒数第六条」→第七条并补上取消、「丢失标记排在后面那七条之前」→八条、「第 15~19 条要用它登录」→15~20、「会改变库里影片数的两条之一」→三条（并写清第 17 条为什么可以插在中间：它那一行在正文末尾就删掉了）。
- **基线**：真后端 **21 条 2.3m 全绿**（新这条 solo 7.1 秒、整跑 7.4 秒），桩 e2e **100 passed**（第三次整跑才绿：前两次各抖一条计时类播放器用例，`player.spec.ts:189` 与 `:92`，单跑都绿——#115/#117/#118/#119/#120 记过的那一族，本单没碰播放器与替身一行代码）、Vitest **334 / 36 文件**、`typecheck:test` 干净；`backend/src/` 三个文件字节级回到基线（md5 逐个核对），故全量 pytest / `ruff` / `mypy` 未重跑，只把 `test_transcode_service.py` 在还原后的代码上重测一遍（11 passed）。跑完 `data/e2e/media/` 实测回到 `e2e_sample.mp4` 与 `e2e_sample.zh.srt` 两个文件。

### 加宽真后端 e2e（#135）：用户管理页那五条写路径打真库真中间件——一套里第一次同时开四台浏览器

- **缝在哪**：`frontend/src/views/Users.vue` 那五个写接口（`POST /api/users`、`PUT .../role`、`PUT .../status`、`POST .../password`、`DELETE .../sessions`）在浏览器这一层一次也没被点过。第 7 条只让这个页面**列出**账号、读那一格设备数；替身那侧（`e2e/roles.spec.ts`）有建号、改角色、重置密码、踢下线四条，可它们签的是 `fixtures.ts` 里手写的响应表——那句 400 是前端自己编的，永远不会和后端那句不一样。
- **为什么接口层那份不算**：`backend/tests/test_api/test_users.py` 把语义签得很死（建完能登录、重名 400、弱密码 400、停用切断会话、重置后旧口令失效、踢下线报数），但它那个假客户端**只有一个 cookie jar**。三段它量不出：① 服务端那句原因要一路走到人眼前——`username` 短了撞的是 pydantic 的 422（`detail` 是数组），账号名不合法、重名、弱密码撞的是服务层的 400（`detail` 是字符串），两路到界面上都只剩 `.el-message--error` 一句话，而这句话是 `client.ts` 摊平再拼前缀出来的；② 一台浏览器的 Cookie 被**另一台**的动作作废；③ 角色是每次请求现查的，不是登录时冻在 Cookie 里的。
- **`user.id != actor.id` 那半句是全仓库唯一的签字处**：`api/users.py:126` 只在「降级别人」时撤那人的会话，降级自己留着——留着才看得见"我刚把自己降级了"而不是被突然踢下线。接口层那五条只测过「最后一个管理员降不得」，没测过「两个管理员时降级自己不踢自己」；这一条把自己降成成员之后断 `meStatus` 仍是 200、`GET /api/users` 当场 403，再由刚被提拔的那个成员把自己升回去。
- **支点句是页面顶部那句谁都当装饰看的说明**：「停用的账号会立即在所有浏览器退出，历史与收藏都会保留」。前半句接口层签了，后半句**一层都没有**——少了这一句，把「停用」写成「删号」也能让前面所有断言全绿。所以停用之前先让那台浏览器真收藏一部片子，启用回来之后那张卡片还在原地。
- **六个变异，五红一绿**（每个改完单独 `-g 用户管理` 跑，跑完整份原字节写回并核对 md5：`client.ts` `bcec5c41…` / `api/users.py` `60c59075…` / `auth_service.py` `e69763b7…` / `middleware/auth.py` `e5d7e4f7…`）：
  - 拆掉 `flattenDetail` 对数组的摊平 → 红在 `:274`，界面那句退成 `创建失败: Request failed with status code 422`（正是 #74 与 #126 那一族的失效形状）；
  - 去掉 `user.id != actor.id` → 红在 `:316`，把自己降级的人被自己的动作踢下线；
  - 降级不撤那人的会话 → 红在 `:329`，那台浏览器拿着成员身份继续跑；
  - 重置密码不撤会话 → 红在 `:402`，旧口令失效而旧 Cookie 还活着；
  - 停用不撤会话 → 红在 `:371`，钉住的是那一格设备数（`signed_in_devices` 先断，那句 401 在它后面）；
  - **绿的那一个是有预期的**：把 `get_current_user` 里的 `not user.is_active` 单独拆掉，整条照绿。停用这一刀实际由「会话行被一起删掉」把关，两道 `is_active` 闸在这一路各挡各的，谁单拆都有另一道兜着——这句写进用例头部，免得后来人以为那半句被签过。
- **写用例时踩出来的一个界面事实**：「登录设备」那一格只跟着**这一台浏览器自己的写**重读（`Users.vue` 只在四个动作的 `finally` 和 `onMounted` 里调 `loadUsers`）。别的浏览器刚登进来时它停在旧数，而「踢下线」的灰不灰正是按这一个数算出来的（`:disabled="!row.signed_in_devices"`），第一次跑就挂在那颗钮上等 `enabled` 等到超时。用例里用一次 `page.reload()` 跟上，并把这个边界写进头部**而不去钉它新不新鲜**——钉住就等于挡掉将来加的刷新按钮或轮询。
- **一条超时账**：`playwright.real.config.ts` 没有 `testTimeout`，默认 30 秒，而这条本机绿的那一遍是 17 秒（四次真浏览器登录，每一次都要过一遍 bcrypt）。所以文件里 `test.setTimeout(90_000)`。顺带量到：Playwright 1.63 的 `TestDetails` 没有 `timeout` 字段，`test(title, { timeout }, body)` 那个写法在 `typecheck:test` 下报 TS2353，只能走 `test.setTimeout`。
- **顺序与编号**：`users` 落在 `transcode` 和 `video-delete` 之间是字母序给的，所以它是执行顺序里的**第 17 条**，后面三条各退一位（`video-delete` 17→18、`video-edit` 18→19、`video-tags` 19→20，含 `video-edit` 头部引用 `video-tags` 的那一处）；总数 19 → 20，`README.md:391`、`CLAUDE.md:205`、`frontend/CLAUDE.md`（648 的替身层那句、671 的逐条段、678 的顺序段与 `-g` 清单）三处跟着改口。顺带纠正 678 里两处陈账：「第 15 条（转码）排在倒数第四条（它后面是转码失败、删除影片、编辑影片）」从 #134 起就少算一条，改成倒数第五条并补齐；「丢失标记排在后面那**五**条之前」同理改成七条。671 里那句「前 18 条一次也没走到那一行」去掉旧数字，改成「在它之前的那十九条」。
- **基线**：真后端 20 条 1.8m 全绿、桩 e2e 100 全绿、Vitest 334 全绿、`typecheck:test` 干净；后端四个文件字节级回到基线（md5 逐个核对），故 pytest 未重跑。`library.real.spec.ts` 那 13 条和 `playwright.real.config.ts` 一个字没改。

### 加宽真后端 e2e（#134）：手工挂的那枚标签扛得过一次真扫描——那句 docstring 的后半句以前根本没被执行过

- **缝在哪**：`backend/src/services/scan_service.py:157` 的 docstring 写的是「a title **or tag set** someone curated by hand is left alone」，第 18 条（#127）只签了前半句。后半句那一行是 171 行的 `video.tags = [*video.tags, *[tag for tag in auto if tag not in video.tags]]`，而它在此前 **18 条真后端用例里一次也没被执行过**：那函数开头两道闸门——`if video.series is not None: return`（162–163）、`if parsed.series is None: return`（165–166）——而播种那部 `e2e_sample.mp4` 解析不出 series，第二趟扫描在 166 行就返回了。覆盖率报告上那一行是绿的，绿的是服务层那条用例，浏览器这一层从来没进去过。
- **为什么服务层那条不算**：`test_rescan_backfills_coordinates_into_old_rows` 挂那枚手工标签用的是**同一个 session 里 ORM 直接 append**，而真实世界是两趟事务：浏览器 `POST /api/tags/video/{id}` 提交完，`POST /api/sources/1/scan` 在**另一个请求、另一个 session** 里把同一条影片行重新捞出来。`Video.tags` 是 `lazy="selectin"`，捞出来那一份里有没有别的 session 刚提交的那一枚，只有真 HTTP + 真 PG 说得了谎。
- **现场怎么安排的，以及哪一句是 SQL 给的**：媒体目录里把播种那部的字节复制成 `morning.squad.s02e03.mp4`（名字必须解析得出 series，否则闸门在第二句就返回），扫一遍得到那一行和它的自动标签 `morning squad`，再从详情页那个「编辑标签」对话框手工挂第二枚——这条写流程 #132 只在替身夹具里走过，真库这一头当时还没人签。然后把三个坐标列**清空**，让它长成 `db_transfer.py` 搬进来的那批行的形状。这一步只能走 SQL：库里没有任何接口能把 `series` 写回 null（`VideoUpdate` 只有 title / description / rating / tag_ids，手工建档的接口压根不存在），所以那是一次性的 `UPDATE` 经 venv 的 python 从 stdin 执行，并断言 `rowcount == 1`——清空的要是别行，后面全部断言就在替空谈话。连接串只进子进程的环境变量，不进 argv、不打印。**被验的因此是"扫描怎么处理标签"，不是"这一列怎么变空的"**。
- **支点句是坐标，不是标签**：扫描之后三个坐标必须被填回 `morning squad / 2 / 3`。少了这一句，"两枚标签都还在"在「`_backfill_coordinates` 压根没走到那条 append」这个错误世界里同样成立，整条用例就退化成"它没动标签，因为它什么也没做"——和第 18 条那句"改名之前先把旧片名钉住"是同一个办法；用例里那句注释（`:200`）就写着"支点"。
- **三个变异，两个红一个绿**（每个改完单独 `-g 手工挂` 跑，跑完整份原字节写回并核对 md5：`scan_service.py` `02dbc917…` / `VideoDetail.vue` `1c746268…`）：

  | 变异 | 结果 |
  | --- | --- |
  | M1 `video.tags = list(auto)`（重列，而不是只往里加） | **红** 在 `video-tags.real.spec.ts:203` |
  | M2 摘掉 `if tag not in video.tags` 那道去重 | **绿**（见下一条） |
  | M3 `handleSaveTags` 保存后不再重读影片 | **红** 在 :182 那句 `expectAttached` |

- **M2 绿不是台子坏了，是那句护栏在这个缝上拆不红**：`secondary` 关系上 SQLAlchemy 默认带 `AppendsUniqueBehavior`，同一个实例重复 append 本来就被吃掉，所以 `[*video.tags, *auto]` 和带 `if` 的那一份在真库上写出同一个结果。用例里那句 `expect(scanned.tags.length).toBe(2)` 钉的是"这一趟扫描没把关联表写成两条"（那是所有写路径共同的账），不是那句 `if` 的账，注释也跟着改成了这句实话。这是 #115 那把尺子的继续（当时量出 mp4 那行的 `acodec` 谁都拆不红）：**一句断言只有先被拆红过，才有资格说自己签了什么**。
- **浏览器层的一个坑**：`page.goto()` 只等文档加载完，Vue 那一路的 `getVideo` 还在飞，直接读 `.tags-list .el-tag` 拿回来的是空数组。第一次报红时快照里那一页停在**首页**、顶上写着「影片加载失败：Video not found」，看着像那一行被谁删了——其实是 `VideoDetail.vue:113` 加载失败之后 `router.push({ name: 'home' })`，那句 `Video not found` 出自 `api/videos.py:208`，和服务层那句 `Video with id N not found`（第 18 条签的）不是同一条。这类"要先等界面读回来才能比"的断言一律走 `expect.poll`，用例里收成一处 `expectAttached`，三处调用共用。
- **收尾按 #120 的规矩**：`finally` 的 body 里不写断言，只做删除（`tryDelete` 连状态码都不核）——影片 → 手工标签 → 自动标签 → 磁盘上那个文件；**在 `finally` 之后**再用真读回核对影片 id 集合与标签名清单回到起点、那个文件确实不在。跑完整套的磁盘现场是 `data/e2e/media/` 只剩播种那部加它的 `.srt`、`thumbnails/` 只剩播种那一张（它自己那一行的封面由删影片那一路带走，那一路是第 17 条签的）。
- **顺序**：`video-tags` 落在 `video-edit` 后面是字母序，但它现在确实是最后一条，所以两处"第 18 条是这一套的最后一条"的活说法跟着作废（`frontend/CLAUDE.md` 的顺序段和 `video-edit.real.spec.ts` 自己的头部，都改了；CHANGELOG 里当初那几条记录不动，那是历史）。它对起点的断言全是先读后比，起点那次扫描断 `files_found=2 / new_videos=1`，所以第 16、17 条"自己造的文件自己收走"在它这里是前提；它给源 1 连盖三次 `last_scan_at`、留一行通知（后两次 `new_videos=0` 按 #85 那条不发），所以第 9 条那种"整张通知表只有播种那一行"必须在它前面跑完。
- **验证**：新用例单独 `-g 手工挂` 4.3 秒绿；全套真后端 e2e **19 条 1.5 分钟绿**；`npx vitest run` **334 passed / 36 files**（一条没动）；桩 e2e **100 passed**（同样一条没动）；`npm run typecheck:test` 无输出。`backend/src/` 在变异跑完之后按 md5 复位，所以后端 738 条、`ruff`、`mypy` 都没重跑——这一单在代码里只多了一个 `e2e/real/` 文件。文档同步：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 的计数 18 → 19，`frontend/CLAUDE.md` 那条顺序段添上第 19 条的位置和 `-g 手工挂`。

### 全站 17 处英文提示扫平成中文（#131），并补上那条谁都看不见的语言闸门

- **缝在哪**：界面文案是中文的，唯独 `ElMessage` 有 **17 处整句英文开头**（`Failed to load tags: …`、`Operation failed: …`、`Delete failed: …`、`Failed: …`），夹在同一张卡片上的「标签已创建」和「删除标签失败」之间。**当初记的 12 处是窄口径**——#129 只数了 `Tags.vue` 和它的邻居，这次按 `ElMessage` 六个方法全站扫，实际分布是 6 个视图 17 处。
- **这一族为什么一直没被拦住**：把这 17 条改回英文，**改动前那 431 条浏览器/单元用例里一条都不会红**（331 单元 + 100 桩 e2e）。单元层断的是 `toHaveBeenCalledWith(expect.stringContaining('服务端那句原因'))`，e2e 断的是 `.el-message--error` 里那句原因——两层都在核"服务端原话有没有被吞掉"（#74 那一族），没有一层核"那句话外面套的是哪种语言"。所以这一单的主要产出不是那 17 条串，是补上的那一条静态闸门。
- **17 处的落点**：动词短语跟着邻近那句 success 取名词，不另发明口径。

  | 视图 | 处数 | 新文案 |
  | --- | --- | --- |
  | `Favorites.vue` | 2 | 收藏加载失败：／移除收藏失败： |
  | `History.vue` | 2 | 播放历史加载失败：／删除播放记录失败： |
  | `Home.vue` | 1 | 视频加载失败： |
  | `Sources.vue` | 3 | 视频源加载失败：／操作失败：／删除视频源失败： |
  | `Tags.vue` | 3 | 标签加载失败：／操作失败：／删除标签失败： |
  | `VideoDetail.vue` | 6 | 影片加载失败：／标签保存失败：／片单保存失败：／收藏操作失败：／视频信息更新失败：／删除影片失败： |

- **新闸门 `tests/views/toast-language.spec.ts`**：遍历 `src/` 下每个 `.vue`/`.ts`（先刮掉块注释、HTML 注释和行注释，同 #123 的规矩，且**刮的时候保留换行**，否则清单里的行号会往回跳、指不到人脸上），用一条正则同时抓住调用和它的第一个字面量实参（跨行的 `ElMessageBox.confirm(` 因此也进得来），断那句话里含汉字。**它检查的是这一族，不是那 17 条串**——新写一个英文 catch 同样红。
- **覆盖率是量出来的，不是"大概都覆盖了"**：全站 `ElMessage*` 调用 **100 处**，其中 **96 处**第一个实参是字面量、进了检查清单；剩下 **4 处**是表达式（`ElMessage.error(transcodeStatus.value.error ?? '转码失败')` 三处、`ElMessage.success(isActive ? '…' : '…')` 一处），静态一层结构上读不到，逐条肉眼核过是中文，记在这里免得下一个人以为 100 处全被护住了。顺带一句：**那三处 `?? '转码失败'` 不是文案问题**，正是 #74/#126 量过的"兜底常量吃掉服务端原因"的形状，别把它当文案改。
- **红是怎么来的**：这条不需要人造红——守卫先写、对着没改的文案跑， offender 清单正好 17 行（`views\Tags.vue:36 ElMessage.error(\`Failed to load tags: …`），改完转绿。再补一次变异确认它抓得住未来的回归：把 `Tags.vue` 那一句单独改回英文 → **1 处红**，跑完按 md5 复位（`26088225`）。
- **两处自己踩到的**：(1) 第一版正则的切片偏移写错（锚到了 `(` 上），`examined.length` 直接变成 **0**——是那条"下限"把它抓出来的，和 #122 那次一模一样；没有下限，这就是一份看着全绿的空守卫，所以现在有两条下限各自钉住"扫到了文件"和"扫到了文案"。(2) 六份视图里 `Favorites.vue`/`History.vue` 是纯 LF、另四份是纯 CRLF，而 `VideoDetail.vue` 有三处 `Failed: ` **同名同形**，Edit 的多行锚在 CRLF 上匹配不了——所以走字节级按 `(文件, 行号)` 替换，每一处先 assert needle 在该行出现恰好一次，六份文件改完 `\r\n` 计数一字未变。
- **验证**：`npx vitest run` **334 passed / 36 files**（原 331 / 35，新增 3 条全在守卫里）；桩 e2e **100 passed**（原 100，一条没动——这本身就是"两层都看不见前缀"的证据）；`npm run typecheck:test` 无输出；`backend/` 一行没动，所以后端 738 与真后端 e2e 18 没重跑。文档同步：`frontend/CLAUDE.md` 新增「提示文案语言」一节。

### 标签名两头那圈空格收口在服务层（#130）：`_clean_name` 一处尺子，六个变异里三条只红后端

- **缺陷长什么样**：`tags.name` 的唯一约束算的是**整串**，所以 `动作片` 和 `动作片␣` 是两行，而界面上是两张分不出来的卡片；`Field(..., min_length=1)` 数的是字符数，`"   "` 照样过校验。两句都不是推的——真库上实测建出过 `{"id": 1, "name": "  ", "video_count": 0}`，一枚看不见的标签，页面上只剩一个颜色点。两头都不裁是这个单开进来的原因：`Tags.vue` 只在**空值闸门**上 `.trim()` 了一次，发出去的 body 用的仍是原始那份。
- **收口在哪一头**：`TagService._clean_name`——建（`create`）和改（`update`）两条写路径都先过它，裁完是空串抛 `BlankTagNameError`（`ValueError` 的子类），路由把它翻成带中文原话的 4xx。放在服务层而不是只改前端：只修界面的话任何客户端仍能往库里塞带空格的重复标签，"进来的名字都是裁过的"这一句在 API 面上根本不存在。扫描那条自动标签不用跟着改，`name_parser._find_group` 早就 `.strip(" -_")` 了。
- **422 改口成 400，这一处是我和当初选项不一致的地方**：选项里写的是"裁完是空串就按 422 拒"，实现落成了 **400 + 原话**。理由是 422 只可能由 pydantic 在进 handler 之前发出，而这条规则必须待在服务层（上一条的理由），于是它能变成状态码的唯一位置就是路由那个 `except`——那一族在这个文件里是 409「重名」、400「没有字段可改」，都是带着原话的 4xx。两个码因此都活着且分得清：`{"name": ""}` 撞 `min_length` 回 422，`{"name": "   "}` 撞服务层回 400。前端不需要新接线：`client.ts` 的 `flattenDetail` 对**字符串** detail 是原样透传的，这句中文以 `err.message` 到达界面（后端压根没有 422 处理分支，归一化全在那一层）。
- **两处顺序是承重的**：`api/tags.py` 的 `update_tag` 里 `except BlankTagNameError` 必须排在 `except ValueError`（那条翻成 404「标签不存在」）**之前**——它本身就是 `ValueError`，晚一步那个 400 会悄悄降级成 404；`service.update` 里必须**先验名字再动任何 `setattr`**，否则一次带着 `{name, color}` 的失败改名会把颜色留下，那条用例就是连颜色一起 PUT 再断言颜色没变。
- **零迁移，是量出来的**：真库现有 3 枚标签，没有一枚带首尾空格，裁剪后也没有新撞出双胞胎（`动作片␣` 那种根本不存在），所以这次不需要任何清洗脚本。
- **六个变异，每个单独跑、跑完按 md5 还原**（`tag_service.py` `50aaea31…` / `api/tags.py` `30e3225a…` / `Tags.vue` `ed109d55…`）：

  | 变异 | 后端 pytest | 单测 | 桩 e2e |
  | --- | --- | --- | --- |
  | M1 `_clean_name` 原样返回（等于回到本次改动之前） | **红 6** | 绿 | 绿 |
  | M2 不再拒绝纯空格名 | **红 2** | 绿 | 绿 |
  | M3 `update_tag` 漏掉那条 400 分支 | **红 1** | 绿 | 绿 |
  | M4 前端建/改名不再 `trim()` | 绿 | **红 4** | **红 2** |
  | M5 改名比较拿没裁的那一份去比 | 绿 | **红 1** | **红 1** |
  | M6 那句空名提示退回英文 | 绿 | **红 1** | **红 1** |

  M1~M3 一层前端都碰不到、M4~M6 一次后端都不红，这两半是同一件事的两面：**界面先裁，所以浏览器永远发不出带空格的名字**。
- **由这张表定下来的决定：替身夹具故意不补裁剪**。给 `POST/PUT /api/tags` 加一段 `trim()` 是一行任何变异都拆不红的死写（#132 量出那次多余的 `links.set` 用的是同一把尺子）。后端那一半的签字人是这 6 条 pytest，界面对那一半是 3 条单测 + 2 条桩 e2e。
- **顺带替 #131 收掉 12 处英文里的 1 处**：`Tags.vue` 那句 `Please enter a tag name` 就在同一条闸门上，改文案比留着再改一遍省事，所以 #131 剩 **11 处**（Favorites 1、History 1、Home 1、Sources 2、Tags 2、VideoDetail 4）。
- **验证**：6 条新后端用例先对着没修的代码红过一遍再转绿；`tests/test_api/test_tags.py` 33 passed，全量后端 **738 passed**（原 732）；`npx vitest run` **331 passed / 35 files**（原 328）；桩 e2e **100 passed 36.8 秒**（原 98）；真后端 e2e **18 passed**（这单动了 `backend/src/`，所以重跑了）；`npm run typecheck:test` 无输出；`ruff` 全绿，`mypy src` 仍是文档记录的那 **34** 项基线，一条没多。

### 加宽替身 e2e（#132）：影片↔标签的关系变成有状态的——详情页「编辑标签」两层共 7 条

- **缝在哪**：`frontend/src/views/VideoDetail.vue` 那条「编辑标签」的写流程，两层一条用例都没有。它偏偏是标签唯一"往一部影片上挂"的入口，而替身夹具的 `POST/DELETE /api/tags/video/...` 只回一句 204、谁也没落库（#128 那次静态遍历问的是"这条地址有没有人答"，语义不在那一层的账上）。后果是"保存后重新读这部影片"永远拿回安装前那几枚标签——用例只能红，而红的是替身不是界面。这和 #133 刚修掉的「`PUT /api/settings` 只回显不落库」是同一类不忠实。
- **改法**：关系存进每次安装重建的 `videoTagLinks`（`Map<videoId, tagId[]>`，后端 `video_tags` 那张关联表的替身），读路径一律按 id 现取；`videos[].tags` 那份模块级种子从此降级成"初始关系的声明"，全夹具只剩这一处真相。按 id 现取顺带白送两件事：标签改名跟着走、删掉的标签自动从影片卡片上消失（和真库那次 join 同一个理由）。另外三处还直接引用种子的读路径（`/history/continue`、`/favorites`、`/videos/series` 的 `next`）也改成现取——它们今天不渲染标签，改的是"别让关系有第二份真相"。
- **两层共 7 条（`tests/views/VideoDetail.spec.ts` 4 + `e2e/video-tags.spec.ts` 3），边界是量出来的**：

  | 变异 | 单测 | e2e |
  | --- | --- | --- |
  | M1 夹具的 POST 不落库（等于回到本次改动之前） | 绿 | **红** |
  | M2 夹具的 DELETE 不落库（同上） | 绿 | **红** |
  | M8 视图把勾选的全发（丢掉新增差分） | **红** | 绿 |
  | M9 视图把当前项全摘（丢掉摘除差分） | **红** | 绿 |
  | M10 对话框预勾"全库标签"而不是本片已有的 | **红** | **红** |
  | M11 保存失败时吞掉服务端原因（#74 那一族） | **红** | 绿 |
  | M12 保存后不重新读影片 | 绿 | **红** |

  M8/M9 为什么只有单测红：替身对"多挂一次""摘一枚本来没挂的"都照常回 204（和后端一致），发多了在浏览器里看不出任何区别。M1/M2/M12 为什么只有 e2e 红：单测把 `@/api/tags` 整个 mock 掉，替身根本不在场，"存下来没有"这一问它答不出。
- **两层都量不到的两处**：夹具那两条防御分支（已挂的不挂第二遍、认不出的标签 id 静默跳过）在 M3/M4 两个变异下**两层全绿**——界面上根本发不出这两种请求（`VideoDetail.vue` 发的是差集，而复选框清单来自 `listTags`，选不到不存在的 id）。它们照的是后端 `tag_service.py` 里那两个 `if`，签过字的是服务层用例，记在这里免得下一个人以为桩用例护得住。
- **验证**：`npx vitest run` 328 条全绿（原 324）、`npx playwright test` 98 条全绿（原 95）、`npm run typecheck:test` 无输出。真后端 e2e 那 18 条没重跑：`e2e/real/` 那三份只在注释里提到 `fixtures.ts`，一条 `page.route` 都没有，而这次改的正是那份替身。`src/views/VideoDetail.vue` 一个字没进提交——变异只是临时改、每次跑完按 md5 还原（`d0dd4575`）。

### 加宽替身 e2e（#133）：系统配置页两层从零补齐——七个变异里三个只红单层，两层的边界是量出来的

- **缝在哪**：`frontend/src/views/Settings.vue` 是 14 个视图里最后一个两层都没有用例的。它不是没人管的地方——真后端 e2e 第 11 条（#112）早就把这一页的**语义**签过了（整份 PUT 回的是请求体本身，改完必须换一路读才算数；被拒的写入不落地），缺的是**桩面两层**：替身夹具在 #128 之后已经接得住 `GET/PUT /api/settings`，可这页界面在 95 条桩用例里一次也没被打开过。
- **两层的分法这次是量出来的**（七个变异，每个单独跑、跑完按 md5 还原，`Settings.vue` `84db8e11…` / `fixtures.ts` `c2ab7966…`）：M1 把 `settings.value = await getSettings()` 的赋值摘掉 → 单测 4 红 + e2e 1 红；M2 把保存换成差量式 PUT（只发间隔那一项）→ 单测 2 红 + e2e 3 红；M3 把「保存失败」那句换成兜底常量（#74 那一族）→ **只有单测红**，因为替身那份整份 PUT 根本不会失败；M4 `:min="100"` → `:min="0"` → **只有 e2e 红**（要真打字才走到钳位）；M5 `:max="1080"` → `:max="99999"` → 只有 e2e 红；M6 摘掉按钮上的 `:loading="saving"` → 只有单测红（替身答得太快，e2e 那条请求态压根悬不起来）；M7 把替身的整份 PUT 改回"只回显不落库" → 只有 e2e 红。三个只红单层、方向还相反，这才是"哪一层能改坏它"的实测版。
- **由 M2 牵出的那条契约**：`PUT /api/settings` 的请求模型就是 `AllSettingsResponse`，五个字段**全带默认值**，所以少发一项不是"那一项不动"，是**被写回代码默认值**（`AllSettingsResponse(**{"thumbnail_width": 640})` 实测把另外四项填成 `True / 3600 / 'mp4' / 180`）。服务端那一半早有 `test_a_bulk_put_that_omits_a_key_resets_it` 钉着，界面这一半"每次都发全五项"此前一句没签——现在单测拿「一个控件也没动」那次保存钉、e2e 拿真 PUT 的 body 钉同一次形状。
- **单测独占的是「能指定服务器回什么」**：库里完全可能存着一个界面选项列表没有的值（`PUT /api/settings/{key}` 对 `auto_scan_interval` 只要求是整数，`default_transcode_format` 后端连值都不校验）。实测 Element Plus 的 `el-select` 在没有匹配选项时**把 model 原样显示出来**（`600` / `divx`），既不悄悄换成列表里的一项、也不清空——所以现在有一条用例就钉这个"不悄悄换"，另一条钉"读失败时页面停在初始值上"（防止有人把 catch 写成清空重来）。这两问真库那 18 条都问不了：它读到的就是库里那份。
- **替身修掉一处不忠实**：`PUT /api/settings` 原先只回显、不落库，于是"保存后刷新还在"这一类用例在桩面上必然红，而红的是替身不是界面（后端 `update_settings` 是写完五个键才 `return data`）。现在它和后端一样 `Object.assign(systemSettings, body)`。两条**单键** PUT 仍只回显——它们没有界面调用者（#128 量的），要接住得连后端那道整数闸门一起补，那是另一单的活。
- **顺带记一句别顺手删的东西**：`Settings.vue` 上那两道 `:min` / `:max` 是这三个数字键**全系统唯一的范围闸门**（#112 立的口径是"只校验是不是整数、不校验范围"），把它换掉不会有任何一层替用户拦住 0 宽的封面。
- 验证：`npx vitest run` **324 passed / 35 files**（原 317 / 34）；stub e2e **95 passed 32.7 秒**（原 90）；`npm run typecheck:test` 干净（一处 `let settle: (() => void) | null` 被 TS2349 拦下——回调里赋值不改变量收窄，改成初值为 no-op 的 `let settle: () => void`）；后端、真后端 e2e、`ruff` / `mypy` 未重跑——`backend/src/` 一行没动。

### 加宽替身 e2e（#129）：标签管理页两层用例从零补齐——补上前 14 个视图里只剩它和 `Settings.vue` 一条用例都没有

- **缝在哪**：`frontend/src/views/Tags.vue` 是一条 346 行的视图，此前**一条用例也没有**（单测和 e2e 两层都没有）。它是 #128 那次补的 17 条缺分支里最集中的一面——标签的建、改名、删、挂卸四条写路径当时第一次在替身里跑得起来，但跑起来不等于被走过：那天补的是"地址有人接"，界面这一侧仍然一次也没点过。
- **两层各问一件另一问答不出的事**：`e2e/tags.spec.ts` 8 条管"真点得动"——卡片真的多一张、409 之后对话框真的还开着、确认后卡片真的消失、取消时真的一个请求都没发；`tests/views/Tags.spec.ts` 10 条管"请求的形状"——PUT body 只带改动的那个字段、什么都没改就一次 PUT 都不发、写失败时不许回读（那句 `await loadTags()` 在 try 里，跑过去就会把人刚填的名字抹掉，而对话框还开着）。中间有一处是**只有单测够得着**的：替身夹具的 `tagBody()` 永远带上 `video_count`，所以"后端没带这个字段时界面写什么"（`{{ tag.video_count ?? 0 }}` 那句兜底）在浏览器那一路结构上量不到。
- **那条"不可能是常量"的断言照旧是这条缝的核心**：#108 立的规矩（每个"界面显示的是 API 说的"都要配一条它不可能是常数的断言）在标签页的落点是——新建一条**故意不挂任何影片**的标签，两张卡片必须一个写 `1 个视频`、一个写 `0 个视频`。写死常数、或者把全库影片数抄过来，在这里都会露出来；只有播种那一张卡片时"1 个视频"两种写法都给得出。
- **八个变异，每个红一处以上，全部按 md5 还原**（`Tags.vue` md5 `9a56c6f3…`、`fixtures.ts` md5 `952d6675…`）：M1 把空名闸门改成只看原始串（`.trim()` 摘掉）→ 单测 1 红 + e2e 1 红；M2 让颜色无条件进 PUT body → 单测 1 红 + e2e **2 红**（改名那条和"什么都没改"那条，后者现在会发一次 PUT）；M3 去掉 `Object.keys(updateData).length > 0` 那道闸 → 两层各 1 红；M4 把 `Operation failed: ${err.message}` 换成固定文案（#74 那一族）→ 两层各 1 红；M5 摘掉 `?? 0` → **只有单测红**，就是上面说的那半盲区；M6 关掉替身的重名判断 → **只有 e2e 红**（单测 mock 掉了 API）；M7 把替身的 `video_count` 写死成 1 → 只有 e2e 红；M8 让替身的删除只回 204、行留在表里 → 只有 e2e 红。M5/M6/M7/M8 这四条"单层红"是这份用例最值钱的部分：它们把两层的边界量出来了。
- **顺带量到两处，都没动**：① `Tags.vue` 和后端 `TagCreate` / `TagUpdate` **两边都不裁剪首尾空格**，于是 `动作片` 与 `动作片 ` 是两行，而 `tags.name` 那条唯一列——以及为它写的 409（#98）——正好拦不住这一对；同一份代码库里 `Users.vue` 是 `小明␣␣` → `小明` 才发的请求，两边口径不一致。② 这条视图的提示文案是中英夹着的：`Operation failed: 标签「动作片」已存在`、`Failed to load tags: …`、`Please enter a tag name`，界面其余部分全中文。**两条都是产品文案/校验口径的决定，不是守卫决定，所以只记不改**，各立一单。
- **一处结构性的"这单做不到"**：`VideoDetail.vue` 的 `handleSaveTags` 存完标签会 `getVideo()` 重读一次来拿新的 `tags`，而替身夹具里 `POST /tags/video/{id}` 与 `DELETE /tags/video/{v}/{t}` 是**无状态 ACK**（只回 204，不动 `videos[].tags`）。所以"在详情页给影片挂一个标签，卡片跟着多一个"这类用例现在还点不红也点不绿——补它得先让夹具里的影片↔标签关系变成每次安装重建的一张表，而 `videos[].tags` 同时被搜索分面（`matchesSearch`）读着，那是另一单的活。
- 验证：`npx vitest run` **317 passed / 34 files**（原 307 / 33）；stub e2e **90 passed 48.5 秒**（原 82；本轮没有踩到 #126 记过的那条计时类 flake）；`npm run typecheck:test` 干净（那份 tsconfig 的 `include` 覆盖 `e2e/**/*.ts` 与 `tests/`，两份新文件里两处 `VueNode` 上的 `.value`、一处 `mock.calls` 都在这一步被拦下改写过）；后端、真后端 e2e、`ruff` / `mypy` 未重跑——`backend/src/` 一行没动，新增的只有 `frontend/e2e/tags.spec.ts` 与 `frontend/tests/views/Tags.spec.ts` 两份测试文件。

## 2026-10-05

### 加宽守卫（#128）：替身夹具必须接得住前端会发出的每一条地址——上线当天量出 17 条缺分支

- **缝在哪**：#120 写「我的设备」那条用例时才发现 `frontend/e2e/fixtures.ts` 里根本没有 `/api/auth/sessions` 的分支，而此前 82 条替身 e2e 全绿——因为**没有任何一条界面用例请求过那个地址**，兜底那句 `未预置的接口` 一次也没被执行到。缺分支不会红，只会静默把替身编的一句假 500 交给界面；哪天有视图开始请求它，红的是界面而不是测试。本单把这次偶然变成一份常驻守卫。
- **守卫怎么搭**：`frontend/tests/api/stub-coverage.spec.ts` 不复制匹配器，直接 `import { mockApi } from '../../e2e/fixtures'`——用一份假 `page` 接住它注册的那个 `page.route` 处理函数，用假 `route` 逐条驱动，答出来的状态码就是桩用例真会看到的那个。复制一份匹配器只能保证"我抄的这份"和夹具一致，而真实的失效方式是夹具改了、守卫没跟着改。地址集合也不再各抄遍历器：#121/#122 那两份自己抄的遍历抽成 `frontend/tests/api/emitted-calls.ts` 一份，一次遍历同时记下完整地址（`client.getUri(config)`）、**没拼前缀的原文**（`config.url`，给形状规则用）和那几个只返回字符串的浏览器构造器。三份守卫（形状 / 路由表 / 替身）从此不可能"一边加了地址、另一边静默少几条"——"少了几条"在测试里从来不报错，只是绿。
- **规则五条**：每条地址都有人答（分支走到了却一次 `fulfill` 都没调，在真浏览器里是永久挂起）；没有一条落到 `未预置的接口`；非 `/auth/*` 的一条都不许被替身的默认拒绝拦成 401/403；模块清单与地址数下限（防 glob 走错目录变成零条空测试）；样本实参登记表不许成陈账（`revokeSession` 那 64 位十六进制令牌、`getSetting` 的白名单键名——函数改名后那份样本对应的就不再是界面会发的地址）。
- **自己踩到的两个坑，都是"看起来全绿的空守卫"**：① 夹具是**有状态**的（`signedIn`、`removedVideos`、`readNotifications`、转码状态机），而 `POST /auth/logout` 会把 `signedIn` 翻回 false，遍历又按模块名排序、`auth` 排第一——共用一份夹具时实测后面六十条地址被整批拦成 401，兜底那句一次也执行不到，"没有缺分支"那条规则演成一份全绿的空守卫。改成每条地址各自 `installStub()` 一次（一趟 1 毫秒），并把"这批地址是以登录着的 owner 身份走的"单独钉成一条规则。② `.filter((_, i) => …).map((call, i) => answers[i])` 里第二个 `i` 是**筛过之后**的新数组下标，不是 `calls` 的下标——真缺一条分支时点名点对了、配的响应体却是另一条地址的。改成先配对再筛。
- **量出来的 17 条**：标签的 `POST /tags`、`PUT /tags/{id}`、`DELETE /tags/{id}`、`POST /tags/video/{id}`、`DELETE /tags/video/{v}/{t}`、`GET /tags/{id}`、`GET /tags/{id}/videos`，源的 `POST /sources`、`PUT /sources/{id}`、`GET /sources/{id}`，`GET /videos/{id}/mediaStreams`，内嵌字幕那条流与字幕的增删，`GET/PUT /settings/{key}` 与整表读。其中 `createTag` / `updateTag` / `deleteTag` / `addTagsToVideo` / `removeTagFromVideo` / `createSource` / `updateSource` 是界面上真点的写路径——也就是说这些流程此前在桩用例里根本跑不起来（点下去替身回一句 500，而用例断言的是别的东西）。补进夹具的这几条是有状态的：`tagRows` / `sourceRows` / `subtitleRows` / `systemSettings` 四张小表每次安装重建，重名建标签照后端那条唯一列回 409（#98），`GET /settings/{key}` 与整表读写共用同一份，所以"建完刷新还在"这类桩用例从此有东西可签。
- **一处刻意没跟着改**：新加的 `/videos/{id}/subtitles/streams` 分支第一版给每条视频都编出一条内嵌字幕，红了三条播放器用例（`播放页为每个字幕渲染一条 WebVTT 轨道` / `播放器菜单…` / `没有字幕的视频不显示字幕按钮`）。替身不能为了让守卫绿而编造后端给不出的数据——现在那条分支如实报"内嵌轨为空"（这份 mp4 夹具确实只有视频流），注释里点名那三条期望。
- **红过没有**（Red before green：两个变异各自单跑 `npx vitest run tests/api/stub-coverage.spec.ts`，跑完按 md5 `952d6675…` 校验还原字节）：删掉 `GET /tags/{id}/videos` 那一段（11 行）→ 红 1 条，报 `tags.ts#getTagVideos  GET /api/tags/1/videos → {"detail":"未预置的接口: /tags/1/videos"}`；删掉 `POST /tags` 那一段（14 行）→ 红 1 条，报 `tags.ts#createTag  POST /api/tags`。修下标 bug 之前跑的第一个变异是"半对"的红：地址点对了，响应体却是登录那一条的——红是能红，读的人被指错地方。
- **顺带量到的死导出**（记下来免得下次重新发现一遍）：`getTag` / `getSource` / `markVideoViewed` / `getNewVideos` / `addSubtitle` / `removeSubtitle` / `getSetting` / `updateSetting` 八个导出今天第一次被静态遍历点到，其中六条界面没在用。**没有删**——是不是死代码是产品决定，不是守卫决定。
- 验证：`npx vitest run` **307 passed / 33 files**（原 302 / 32；新增的 5 条就是本单那份守卫）；`tests/api` 三条守卫同跑 14 条绿；`npm run typecheck:test` 干净（那份 tsconfig 的 `include` 覆盖 `e2e/**/*.ts`，夹具的改动在里面被检查过——它当场拦下一处 `any` 写进 `as const` 键并集的 `TS2322`）；stub e2e **82 条全绿**（`player.spec.ts` 那条 A-B 段重放在并行负载下红过一次、单独跑 2.5 秒绿，是 #126 记过的计时类用例老毛病，不是本单引入）；被钉住的地址 76 条（72 次 `client` 调用 + 4 条构造器）。后端与真后端 e2e 未重跑：`backend/src/` 一行没动，`fixtures.ts` 只活在前端测试面里。

### 加宽真后端 e2e（#127）：编辑影片那一路打通真库——顺带修掉一个 `rating: null` 炸成 500 的形状

- **缝在哪**：`PUT /api/videos/{video_id}` 是库面最后一个从没在真后端签过字的写接口。服务层 `update_video` 有单测，但那 82 条桩用例里"改完刷新还在"是 `frontend/e2e/fixtures.ts` 自己那份手写响应表说了算；另一半是 `backend/src/services/scan_service.py:157` 那句 docstring——"a title or tag set someone curated by hand is left alone"——从写下那天起没有任何一条用例在 HTTP 之上核过它。
- **量出来一个真缺陷**：`VideoUpdate.rating` 标的是 `int | None`（意思是"不填就不改"），而 `videos.rating` 那一列是 NOT NULL。于是 `{"rating": null}` 是一条一路好走的请求：Pydantic 放行、服务层 `setattr(video, "rating", None)` 照写、asyncpg 在 `UPDATE videos SET rating=NULL` 上顶回来 → **500**；而 `VideoResponse.rating: int` 从来发不出 null，那一半契约根本不成立。按老规矩先对着修复前的 HEAD 红一次（实测 `sqlalchemy.exc.IntegrityError: null value in column "rating" of relation "videos" violates not-null constraint`），再收闸口。
- **修在表示层，不收在服务层**：`VideoUpdate` 上加一个 `@field_validator("rating")`，把显式 null 变成 422 一句原话「评分不能留空：要清空请填 0」。这是 #112 那条"写进去的值必须能被读回来的那条路径解析"的另一半：列不接受的值不该进请求模型，而界面上"清空评分"本来就是点回 0 星、不是一个缺值状态。Pydantic v2 的口径顺带量清楚了：`field_validator` **不跑**在"根本没提供"的字段上（`VideoUpdate().model_dump(exclude_unset=True)` 实测 `{}`），所以"不填不改"和"填 null"天然分得开，闸口不必自己判 `model_fields_set`。
- **反面那一半也钉住了**：`title` / `description` 那两列**可以**为空，同样的 null 照旧 200（`test_an_explicit_null_title_is_still_allowed`），页面上片名退回文件名。没有这一条，"所有 null 都不许进"也算修好了。
- **第 18 条用例签的三件事**：① 三个控件真点击写进真库，`GET /api/videos/1`、列表查询里那一行、页面本身三路读回同一个答案，`updated_at` 由列上的 `onupdate` 推新（替身夹具压根没有这一列），`thumbnail_path` 不许动；② 紧接着对**同一个源**再扫一遍，片名、简介、评分一个字都不许被文件名解析覆盖（`files_found=1 / new_videos=0`），那句 docstring 从此有了真身；③ 片名的**下游**：`backend/src/api/history.py:91` 那个 `video_title` 是读时联表现算的、不是历史行里的快照，改名之后 `/api/history/continue`、首页那条轨的 `.rail-caption`、`/history` 的 `.continue-title` 和搜索必须一起改口，而改名**之前**先把基线钉成旧名字——否则这一整段拿"处处都是 null"也能过。外加三条 422 各自的 Pydantic `type`、空 body 的 400、`99999` 的 404，和 member 两头（界面上数不出「编辑」那颗按钮、硬发 PUT 撞的是真中间件那句 403）。
- **五个变异，五个红**（每个单独跑、跑完按 md5 还原）：M1 把 `update_video` 里的 `setattr` 换成 `pass` → 红在页面那句新片名（spec:107）；M2 把 validator 的 `if value is None` 换成 `if value is False` → 红成 500，现场就是修复前那个 `NotNullViolationError`；M3 去掉 `updated_at` 列上的 `onupdate=` → 红在时间戳那句（spec:122）；M4 把 `video_title=record.video.title if record.video else None` 换成 `video_title=None` → 红在改名**之前**那条基线（spec:92），这一条最能证明用例核的是联表而不是常量；M5 往 `MEMBER_WRITE_PATHS` 里加一条 `/api/videos/{id}` → 红在 member 那一步的 403（spec:215）。
- **顺带纠正 #126 留下的编号陈账**：`frontend/CLAUDE.md` 那条顺序说明里的「第 15 条（转码）排在倒数第二条」「第 16 条（删除影片）…也就是整跑的最后」「第 15、16 条要用它登录」「后两个由第 13 条和第 16 条共用」四处按新编号全部改口；另外「删除影片是这一轮里唯一会改变库里影片数的一条」从 #126 起就不再成立——第 16 条那个非法容器同样会建出一行，只是它自己在 `finally` 里收干净了。
- 验证：新用例单独 `-g 编辑影片` 7.3 秒绿；全套真后端 e2e **18 条 1.4 分钟绿**；后端全量 **732 passed**（3:01，PG）；`npm run typecheck:test` 干净；`ruff check` 干净；`mypy src` 仍是那条 34 项基线，没有新增；`backend/openapi.json` **不用重生成**——`field_validator` 不动 JSON Schema，`tests/test_openapi_snapshot.py` 原样绿。

### 加宽真后端 e2e（#126）：让 ffmpeg 真失败一次——那句原因原先只有 monkeypatch 的假字符串签过字

- **缝在哪**：失败那一路不是全空，是**半层假**。`backend/tests/test_services/test_transcode_service.py` 那条 `test_failed_job_keeps_the_error_message` 把 `transcode_video` 换成一个返回 `(False, "boom")` 的假函数，所以"错误字段跟着作业走"这一句是证的；但 `transcode_video` 里那个 20 行的 stderr 尾巴（`other_output`）到底从真子进程捞回了什么、闸门放行之后一个失败的任务在界面上长成什么样、后台任务发出去的到底是 `transcode_complete` 还是 `transcode_error`——三处没有一个字签过，而 82 条桩用例那份 `POST /api/transcode/{id}` 处理器永远不会失败。
- **现场**：往媒体目录写一个 `e2e_broken.mp4`——后缀在扫描器白名单里，内容是一行文本。扫描只认后缀（`extract_video_info` 探针失败回的是默认值），所以库里确实建得起一行，而那一行的 `duration` 和 `thumbnail_path` 都是 null。然后从界面上选 `webm` → 开始转码 → 不刷新，轮询到「失败」。
- **`progress` 钉 0 靠的是那个 null 时长**：`_run` 拿到 `duration=None`，`on_progress` 一次都不会被调用。这和第 15 条里"avi 那一路容器最后报到 28 秒"是两回事，注释里把两句分开了。
- **三层各一个变异，实测三个红**（每趟跑完按 md5 还原）：M1 把失败分支那句 `" ".join(other_output) or f"ffmpeg exited..."` 换成常量 → 红在 `toContain('moov atom not found')`；M2 把 `type="transcode_complete" if completed else "transcode_error"` 改成永远 complete → 红在通知那条 `toMatchObject`；M3 把页面 `{{ transcodeStatus.error }}` 换成常量「转码失败」→ 红在"页面那一段与接口字段逐字相等"那一句，也就是 #74 那一族的形状。
- **量到一件一直没核实的事**：`transcode_video` 只在 cancel 分支 `unlink` 输出文件，失败分支不删。这一趟磁盘上之所以干净，是因为 ffmpeg **连输入都没打开**（实测 `rc=183`，`e2e_broken.webm` 压根不存在），不是"失败不留产物"的通用保证。用例里那句注释只说这一种失败模式；**没有顺手把删除补上**——那是行为变更，等用户点头。
- **自己踩到的一个数**：通知基线原先取在用例开头，于是多数出一条——那一趟扫描自己也发一条（库真变了才发，第 9 条钉的就是它）。改成扫描**之后**取基线。
- **编号跟着挪**：本文件那条新用例是执行顺序里的**第 16 条**，`video-delete.real.spec.ts` 从"第 16 条"改口为"第 17 条"；`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 16 → 17；`frontend/CLAUDE.md` 那份 `-g` 名单加一条，并把 `-g 转码` 换成 `-g 三种拒绝`（前者从本单起会同时命中成功和失败两条）。`backend/CLAUDE.md` 里那条 coverage 注记写的"第 14 用例"是旧编号，一并改成"那两条：第 15 条 / 第 16 条"。
- 验证：新用例单独跑 5.0 秒绿；全套真后端 e2e **17 条 1.3 分钟绿**（删除影片那条排在最后仍然数得出 `files_found=2 / new_videos=1`，说明这一条把自己造的现场收干净了）；`npm run typecheck:test` 干净；Vitest **302 / 32 文件**绿（本单没动 `src/`，那一遍是防回归）。
### 加宽真后端 e2e（#125）：转码表里 mkv 那一行也补一次真产物——顺带纠正 #117 说过头的一句

- **起点是 #117 留在 spec 注释里的一句话**：「四行配方只有这两行有产物可查：`mp4` 造不出产物（源文件本身就是 mp4，同格式覆盖被闸门拒绝），这条用例也不产 mkv」。后半句不是事实，是我自己给自己设的限制——同格式那道闸门是 `Path(input_path).with_suffix(f".{fmt}") == Path(input_path)`，四种格式里只有 `mp4` 那一行真被挡住，`mkv` 从 #115 起就可以转。于是 `mkv` 那半张配方（`-c:v libx264 -c:a aac`）到 #125 之前都没有一个真进程签过字。
- **补的是第 6 步**：界面上选 `mkv (.mkv)` → 开始转码 → 不刷新，轮询到自己的终态，再按 webm / avi 那两次的规格核对产物——文件头那几个字节自报 `matroska`（读 EBML 的 DocType，不看文件名），`ffprobe` 报出来的两条流是 `h264 + aac`，后台任务写进真库那条通知的 `data.format` 是 `mkv`。这一步刻意不钉 `progress`：avi 那一步已经说明"容器最后报到第几秒"是编码器的细节，不是这条用例要签的东西。产物照旧由 `test.afterEach` 收走，绿跑完媒体目录还是只有播种那两个文件。
- **两个变异证明这一条真的能红**（改 `backend/src/utils/ffmpeg.py` 的 mkv 那行，每趟跑完按 md5 `b18c9b52…` 还原）：`codec` → `libvpx-vp9` 红在流清单——vp9 塞得进 matroska，容器那一句挡不住它，只有 `ffprobe` 认得出来；`acodec` → `libopus` 同样红在流清单。**第三个变异反过来做**：把 `mp4` 那行的 `acodec` 也改成 `libopus`，整条用例仍然绿（实测 exit 0），因为 mp4→mp4 在闸门就得到 400，ffmpeg 从没为它起过一次进程——这是这套用例现在诚实留下的最后一个配方空白。
- 顺带 `CONTAINER` 加 `mkv: 'matroska'`、`STREAMS` 加 mkv 那一对，取消那一步的"拒绝不许改记录"基线从 avi 记录换成 mkv 记录（步骤号 6/7/8 跟着挪）。
- 验证：全套真后端 e2e **16 条 2.1 分钟绿**（单独跑这一条 28.9 秒），`npm run typecheck:test`（`vue-tsc -p tsconfig.vitest.json --noEmit`，那份 tsconfig 把 `e2e/**/*.ts` 算在内）干净。
### FastAPI 升级评估（#111）：工单的前提在仓库里找不到出处，顺手把全量套件里最后一个告警消掉

- **动因**：#111 写着"编辑器反复告警 `fastapi==0.112.0` 已过时，当前 `pyproject` 是 `>=0.109.0`、锁到 0.112.0"。先量再动：拿 `.venv/Scripts/python.exe` 用 `importlib.metadata` 逐包读已装版本，对着 `backend/uv.lock` 比，10 个关键包**零漂移**——fastapi 0.140.0 / starlette 1.3.1 / pydantic 2.13.4 / pydantic-core 2.46.4 / uvicorn 0.51.0 / anyio 4.14.2 / python-multipart 0.0.32 / alembic 1.20.0 / sqlalchemy 2.0.51 / httpx 0.28.1，Python 3.13.5；`uv lock --check` 退出码 0（锁与 `pyproject` 也同步）。
- **0.112.0 不属于这个仓库**：`git log --diff-filter=A -- backend/uv.lock` 显示这份锁是 2026-07-27 的 `1d77281` 才加进来的，从第一天起就写 0.140.0，此后四次改动一次没动过 fastapi；`git grep "0\.112"` 在所有被跟踪文件里零命中，也没有任何 `requirements*.txt`。那条告警来自仓库之外的解释器。**工单的前提是过时的，按它改依赖会改错东西。**
- **我自己在这条上量错过一次**：那张对照表第一版是拿**系统 python** 跑的，读出 fastapi 0.115.6 / starlette 0.41.3 / pydantic 2.10.3，看着像"环境与锁严重漂移"；换成 `.venv/Scripts/python.exe` 后差异全部消失。凡是核对版本，先钉死解释器。
- **真要升的话面有多小**（实测 `uv pip install --dry-run fastapi==0.142.2 --python .venv/Scripts/python.exe`）：只动两个 wheel——fastapi 本身，外加新拖进来的 `opentelemetry-api==1.45.0`（来自 0.142.0 的"原生 OpenTelemetry 支持"）；starlette 留 1.3.1、pydantic 不动，所以不是框架换代。0.141.0 / 0.142.0 的 release notes 各只有一条 feature（`app.frontend(check_dir="auto")`、OpenTelemetry），无 breaking 条目；0.142.1 修的恰好是 "included routers 重复包装端点"，就在 `_IncludedRouter` 那条我们依赖的路上，但改的是路由内部结构，而两处全路由扫面读的是 `app.openapi()["paths"]`、不是 `app.routes`，够不着断言的输入。
- **工单点名要复核的那条警告到今天仍然成立**：`app.routes` 顶层实测 21 条（16 `_IncludedRouter` + 4 `Route` + 1 `APIRoute`），`_IncludedRouter` 依旧没有 `.path`——所以"别改走 `app.routes`"那句不是历史包袱，是当前行为。复核清单（三处）与上面这些数字都落在 `backend/CLAUDE.md`「依赖管理」新增的两节里。
- **决定：不换，也没动任何依赖版本**。这是依赖变更、要用户点头；而且没有紧迫理由——当前 0.140.0 栈上全量后端 **730 passed**（2026-10-05 实测 3:21 与 9:14 各一次，两次都绿；后者与别的进程同跑，耗时不作为基线引用）。
- **顺手消掉的一条**：那次全量唯一的告警是 `from fastapi.testclient import TestClient` 在 starlette 1.3.1 上**导入即告警**（`StarletteDeprecationWarning: ... install httpx2 instead`），而 `TestClient` 只剩脚手架期的 `tests/test_main.py` 在用它测 `/health`、`/docs`、`/redoc`。改成与其余用例同一条 `httpx.ASGITransport` 路：这三条都落在中间件"非 `/api` 直接放行"的分支上、不碰库，所以在本文件自建一个不带会话替身的 `public_client`，而不是复用 `anon_client`（后者会 monkeypatch session factory 并拖进 `db_session`）。改完 `tests/test_main.py` 5 条 0.06s 绿、全量**零告警**；`ruff check` 干净；`mypy` 口径仍是 `mypy src`（`tests/` 不在里面，且原文件同样报 5 条缺注解，改成 6 条是新增那个 fixture 的），没有新增债务。

### 把浏览器自己取的那四类地址也钉到路由表上（#124，接着 #123 的遗留）

- **动因**：#123 交出时把「三个返回字符串的 URL 构造器」记成遗留，但没实测过它们到底瞎到什么程度。这次先量：6 个变异跑全套，`subtitles/embedded/` → `embed`、详情页流地址 → `/videostream`、详情页流地址 → `/thumbnail` 三个**全绿**；另外三个（`thumbnail` 的两个变体、字幕 `/stream` → `/vtt`）会红，可红的原因是 `tests/api/videos.spec.ts:33` / `tests/components/VideoCard.spec.ts:22` / `tests/views/History.spec.ts` / `tests/components/VideoPlayer.spec.ts` 里各抄了一份字面量——那是"源码和抄本一起改"才会响的铃，不是契约。另外发现 #123 那句"这一类关掉了"说过头了：`VideoDetail.vue:74` 的 `/api/videos/${video.value.id}/stream` 还在视图里，而那份守卫只盯默认导入 axios 实例的文件，看不见裸字面量。
- **改了什么**：那条流地址搬进 `src/api/videos.ts` 成为 `streamUrl(id)`，模板改读 `streamUrl(video.id)`——原来 `if (!video.value) return ''` 是死分支，播放器整块就挂在 `v-if="video"` 里面。`openapi-contract.spec.ts` 的遍历器现在除了适配器记录的 axios 请求，还把**只返回字符串**的构造器按 GET 补记一条（浏览器取封面、取流、取 `.vtt` 走的正是 GET），并用 `viaClient` 把两类分开各设下限，防止哪一类静默归零还被总数蒙过去。新增 `tests/api/builder-urls.spec.ts` 4 条用互不相等的哨兵值（11 / 22）钉住"哪个实参落在哪一段"。守卫 `inline-requests.spec.ts` 加第二条规则：`src/api/` 之外不许出现 `/api/` 字面量，比对前先刮掉 `/* */`、`<!-- -->`、`//`，不然 `src/types/auth.ts` 里那句文档注释会被当成请求。
- **为什么必须是两层，一层不够**（这两条都是实测出来的，不是推的）：
  - **路由表管不了落点**。字幕那条模板声明成 `/api/videos/{video_id}/subtitles/{subtitle_id}/stream`，两个参数都是 integer，把实参写反照样命中；把 `streamUrl` 改成返回封面地址也仍是一条已声明的路由。这两个变异对表全绿，只有哨兵断言抓到（字幕那个还顺带红了 `VideoPlayer.spec.ts`）。
  - **手抄管不了两边一起错**。把 `backend/openapi.json` 里的封面路由临时改名为 `/poster`（模拟后端改名，前端一行没动），红的只有 `openapi-contract.spec.ts` 那一条，三处手抄期望全绿——手抄能响"构造器改了"，永远响不了"构造器和它的抄本一起对着一个已经不存在的接口"。
- **红过没有**（Red before green，六个变异全部跑 `npx vitest run` 全套，跑完按 md5 校验还原字节）：搬之前 3 绿 3 红（如上）；搬之后六个各红 1~2 份文件——`embedded`→`embed` 与字幕落点写反各红 2 份，详情页地址重新内联红守卫那 1 份，`streamUrl` 改回封面地址红 `builder-urls` 1 份，路由表改名红 `openapi-contract` 1 份，把补记那段关掉红新下限 1 份。
- **验证**：`npx vitest run` **302 passed / 32 files**（原 296 / 31）；`tests/api` **41 条 / 10 份**（原 35 / 9）；被钉住的地址从 72 次 `client` 调用扩到 **76** 条（+4 构造器）；`vue-tsc --noEmit` 干净；`npm run build` ✓ 786ms；stub e2e 82 条 30.8s、真后端 e2e 16 条 1.2m 全绿（`VideoDetail.vue` 是真改了的界面文件，播放器的 `src` 换了来源）。后端没重跑：`backend/src/` 一行没碰，`backend/openapi.json` 只在那个改名变异里临时动过，还原后 md5 `253253cd…` 与提交版本一致。
- **遗留**：静态层只剩一条——调用方自己传进来的 `params` 键名仍在遍历器之外（模块里写死的那部分已经钉住）。真后端 e2e 那 16 条仍然只在被点到时才覆盖这些地址。

### 把 Sources / Transcode 两视图里就地拼的 7 条 URL 搬进 `src/api/`（#123，账是从 #122 的遗留里翻出来的）

- **动因**：#122 的路由表钉子只看得见经过 `client` 的调用，而 `Sources.vue` / `Transcode.vue` 里有 7 条 URL 是在视图函数体里用字符串拼出来的，`tests/api/` 两份规格对它们完全瞎。这不是推测：搬之前把 7 条逐条改坏（改单复数、改路径段、改方法）再跑 `npx vitest run tests/api`，**33 条用例全绿**；视图规格里断言的 URL 又是手抄的第二份字面量，源码写错它照着抄错，照样绿。等于这 7 条是仓库里唯一一批"改错了没人报警"的请求。
- **改了什么**：新增 `src/api/scan.ts`（`scanAll` / `scanSource`）和 `src/api/transcode.ts`（`listTranscodeFormats` / `getTranscodeStatus` / `startTranscode` / `cancelTranscode`）。模块边界跟着后端 router 走，不跟页面直觉走：两条 scan 路由都定义在 `backend/src/api/scan.py`，所以放进 `scan.ts` 而不是看着像源列表就塞进 `sources.ts`。`Transcode.vue` 里三份手抄的 `interface`（`FormatInfo` / `Video` / `TranscodeStatus`）删掉，换成新增的 `src/types/transcode.ts`、`src/types/scan.ts` 和已有的 `getVideo`；两个点击处理器改名 `handleStartTranscode` / `handleCancelTranscode`，免得和导入的同名函数互相遮蔽。
- **顺带把这一类关掉**：新增 `tests/api/inline-requests.spec.ts`，静态扫 `src/` 下 `api/` 之外的每个 `.ts`/`.vue`，只要默认导入了 axios 实例就算违规——默认导入才是"拿到实例、可以就地拼 URL"的形状，`router` 那种具名导入不发请求。同文件里还有一条"至少扫到 25 个源文件"的下限：扫描器自己的路径写错时会扫到空目录，然后以"零违规"的名义通过，这条下限就是防这个的。
- **视图规格一行没动**：`tests/views/*.spec.ts` 继续 `vi.mock('@/api/client')`。因为 `src/api/*.ts` 只是 `client` 的薄包装，mock 掉 `client` 同时就在喂数据和记录 URL，搬之前搬之后 mock 看到的 URL 集合一模一样——这本身就是"包装层没有引入第二处真相"的证据。
- **红过没有**（Red before green：逐条改坏就跑，跑完按 md5 校验还原字节）：搬完之后同样的变异，6 条 URL 变异 + 4 条方法变异各让 `openapi-contract.spec.ts` 红 1 条，其中 `/transcode/formats` 改成 `/transcode/format` 报的是这批里最有信息量的一句——`形状相符的模板有 /api/transcode/{video_id}，但方法或路径参数类型不成立`；改坏 `videos.ts` 红 2 条；改坏 guard 自己的正则让它漏检，红 1 条。搬之前这些全绿。
- **验证**：`npx vitest run` 296 passed / 31 files（原 294 / 30）；`tests/api` 35 条 / 9 份文件（原 33 / 8）；被钉子记录下来的 client 调用从 66 次涨到 72 次（临时翻转下限断言实测出来的，不是估的）；`vue-tsc --noEmit` 干净；`npm run build` ✓ 810ms；stub e2e 82 条 33.8s、真后端 e2e 16 条 1.2m 全绿。后端没重跑：`backend/src/` 一行没碰。
- **我自己踩的两个坑**：变异脚本第一版用 `read_text()` + `write_text(newline='')`，把 `Sources.vue` 的 173 行 CRLF 全写成了 LF，`git status` 还显示干净（autocrlf 归一化把差异吃掉了）——是靠脚本 `finally` 里那句 md5 断言才发现的，此后凡是动仓库文件的脚本一律走字节。第二个：cp936 控制台上打印 vitest 的 `❯` 直接 `UnicodeEncodeError`，得给**父进程**也带 `PYTHONIOENCODING=utf-8`（或只打 ASCII），只给子进程设没用。
- **遗留**：`thumbnailUrl` / `subtitleTrackUrl` / `embeddedSubtitleTrackUrl` 这三个返回字符串的 URL 构造器现在确实住在 `src/api/` 里了，但它们不经过 `client`，两份 api 规格还是看不见；要钉住得换一条路（直接拿模板对 `openapi.json` 校验），另开一张。另外调用方自己传进来的 `params` 对象的键名也仍然在钉子外面。

### 新增：路由表提交进仓库（`backend/openapi.json`），前端每份请求模块的 URL 从此对着真接口核对（补 #121 自己交代的那条"钉不住段名"）

- **动因**：#121 收尾时列的未覆盖面就是本单的立身之本——形状规则（不带 `/api`、以 `/` 开头、没有 `//` 也没有尾斜杠）**看不出段名拼错**：`/videos/duplicates` 少一个 `s`、`/auth/sessions` 写成单数，在 12 份模块的任何一层钉子下都是全绿，只有界面真点到那条路由才撞出 404。要签它得有一份可比对的路由表。顺带推翻 #121 当时写的那句"生成它要先起着后端"：`app.openapi()` 是离线构建的（实测把 `DATABASE_URL` 指到一个没人监听的端口照样出 65 条路径 / 84 个操作），没有任何服务、没有网络。
- **加了什么**：① `backend/src/export_openapi.py`——`python -m src.export_openapi` 写快照，`--out` 换目标、`--check` 只比不写（不一致退出码 1）。输出是 `json.dumps(..., indent=2, sort_keys=True)` 加尾换行，键排序和固定缩进是为了让 diff 只反映接口本身的变化；连跑两次字节完全相同（md5 `253253cd…`），这条本身就是"确定性"的验证。② `backend/openapi.json`：65 路径 / 84 操作 / 5575 行 / 144322 字节，其中 6 行描述是中文（所以是 UTF-8，不是 ASCII）。③ `backend/tests/test_openapi_snapshot.py` 3 条：提交的文件必须与 `app.openapi()` **逐键比对象**（不是比文本，注释和格式漂移不会造成假红）、`--check` 与它口径一致、`--check` 对着陈旧文件必须红。④ `frontend/tests/api/openapi-contract.spec.ts` 4 条：模块清单自己数出来、遍历后至少 60 次调用且**全部落在 `/api/` 下**、每条 URL 命中 schema 里声明过的**路径 + 方法**且路径参数类型对得上、每个 query 键名都在 schema 里声明过。
- **红在先**（四个变异，每个只改一份 `src/api/*.ts`，`npx vitest run tests/api/`，跑完还原并核对 md5：`auth.ts fddf9ae8…`、`preferences.ts ad53d65e…`、`favorites.ts 77457a91…`、`videos.ts ed089e1e…`；前两个与 #121 记录的同一份值，说明两次变异都还原到了同一字节）：① `'/auth/sessions/${tokenHash}'` 改成 `'/auth/session/…'` → 红在契约那条；② `preferences.ts` 的 `client.put('/preferences', patch)` 换成 `client.post` → 红（路径对、方法没声明）；③ `favorites.ts` 的 `page_size: pageSize` 写成 `size: pageSize` → 红在 query 键名那条；④ `videos.ts` 的 `'/videos/duplicates'` 改成 `'/videos/duplicate'` → 红。另有一处**证明防腐钉子有牙**的：从提交的 `openapi.json` 里删掉 `/api/auth/sessions` 那一段，`test_openapi_snapshot.py` **3 条里红 2 条**，重跑导出即复绿。
- **两个变异一开始是绿的，各自逼出一条新规则**（这才是本单最值钱的部分，光加"能不能匹配上路径"是不够的）：③ 最初把带 `%5B` 的键（遍历夹具传的 `params` 对象编码出来的 `dummy[dummy]`）整个过滤掉，`page_size → size` 跟着被放过——改成按 `=` 切、剥掉 `%5B` 之后那段再比；④ 纯形状匹配（段数相同 + 字面段相同 + `{x}` 吃任意一段）下 `/videos/duplicate` 撞上 `/api/videos/{video_id}`，"看起来合法"，而运行时拿到的是 422 不是 404——加了**路径参数类型**规则：schema 声明 `integer`/`number` 的那一段必须是 `-?\d+`，`boolean` 只能是 true/false。这两条规则都不是先想出来再加的，是被假绿逼出来的。
- **一次差点留在工作树的变异**：变异脚本在 `finally` **之前**打印结果，Windows 控制台默认 cp936，撞上 vitest 输出里的 `❯` 抛 `UnicodeEncodeError`，脚本死在半路，`src/api/auth.ts` 带着改动留了下来——是 `git status` 抓到的，不是脚本。规矩改成：`finally` 里只还原、打印挪到最后，并且脚本自带 `PYTHONIOENCODING=utf-8`。
- **一条死路，原因是没先查文档**：本来想再加一条"schema 里声明的每条路径确实注册在 `app` 上"的完整性用例，结果 `app.routes` 只能列出顶层 21 条——这版 FastAPI 把 include 进来的路由存成 `_IncludedRouter`，没有 `.path`，于是 83 个操作全被判成"未注册"。而 `backend/CLAUDE.md:462` 早就写着这句警告，是本单没读它就动手。删掉这条，快照钉子改成直接与 `app.openapi()` 比对象。
- **三处说过头的文档被改口**：① `CHANGELOG.md:698` 那条 2026-09-21 的"自动遍历全部 api 模块"（#121 已记，历史条目不改写，引用它的人要知道）；② `frontend/CLAUDE.md:637` 那句"改用 `client.defaults.adapter` 拦截，能顺带验证 `baseURL + url` 拼出的完整地址"——实测 **adapter 里 `config.url` 还是原始相对路径**（`/videos/new`），`baseURL` 是另一个字段，拼接发生在 axios 自己的 adapter 内部，能看到真实地址的公开方法是 `client.getUri(config)`（顺带量到它对非对象 `params` 抛 `TypeError: target must be an object`）；③ #121 本单里"生成 schema 要起着后端"那句。另补 `README.md` 测试一节一句方言判据（`.env` 里带着 `TEST_DATABASE_URL` 时裸 `pytest` 跑的就是 PG，报通过数前先确认）——那是 #103 的结论，README 一直没跟上。
- **覆盖面的位移**：`frontend/CLAUDE.md:636` 里"新增一份 `src/api/*.ts` 要同时加进 `MODULES`"这条手工登记从此作废——两份 api 用例（`paths.spec.ts` / `openapi-contract.spec.ts`）共用同一个 `import.meta.glob('../../src/api/*.ts')` 自己数清单，下限断言 `>= 12` 只为了防"glob 什么都没匹配到 → 整份用例空跑还全绿"（这个红在本单里是**真出现过**的：glob 深度写错时它立刻红了，等于误打误撞验了这条兜底）。
- **仍然钉不住的**：① 在 `src/api/*` 之外拼出来的 URL 不在这份遍历里——`<img>`/`<video>` 的 `src`、字幕 `.vtt` 的地址都是字符串拼装，没有 `client` 经过；② 遍历夹具只传位置参数，`listVideos` 那种由**调用方**传入的 `params` 对象键名，只有模块自己写死的那部分被钉住（`getUri` 对非对象 `params` 会抛，那一支是丢掉的）。这两条留给"82 条桩 e2e 仍在 mock `/api`"那一单一起收。
- **验证**：`npx vitest run tests/api/` **8 files / 33 tests passed**；前端单测 **294 passed / 30 files**（290 → 294，新增正是这 4 条契约用例）、`typecheck:test` 绿、`npm run build` 绿（1.21 秒）；`backend/tests/test_openapi_snapshot.py` **3 passed**（以及上面那次删路径的 2 failed）；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数）；后端 PostgreSQL 全量 **730 passed**（471 秒，PG；727 → 730，多的正是那 3 条快照用例。慢一倍是这一轮同时有 ShadowBot 和两个 uvicorn 在跑。另外交代一句：这个下午同一条命令曾报出 **54 failed / 660 passed**，那是它和另一套 pytest 撞在同一个 `home_sites_test` 上，失败全是文档里记过的 TRUNCATE 互等，不是回归——**要信数就只信单独跑出来的那一个**）。桩 e2e 与真后端 e2e 本单未跑：`src/` 一行没改，四个变异全部还原并核对过 md5，`git status --short src/api` 干净。

### 测试：请求路径的静态钉子从此覆盖全部 12 份请求模块，并且按模块归账（#121）

- **动因**：#119 顺带量到的那句——`frontend/tests/api/paths.spec.ts` 只遍历 `src/api/` 的 8 份，而 auth / preferences / users / watchlists 四份连「别把 `baseURL` 已经带的 `/api` 再写一遍」（#10 那一类双前缀缺陷的回归护栏）都没有钉子。本单补全到 **12** 份（`client.ts` 不在遍历范围内——它就是被替身换掉的那个 axios 实例本身）。
- **加了什么**：① `MODULES` 补上那四份；② **按模块归账**——`invokeModule()` 返回该模块新增的那几次调用，哪一份一次 `client` 都没打到就算红；③ 第三条形状规则「一次拼接一个分隔符」：路径里既不许出现 `//`，也不许以 `/` 结尾（尾斜杠在 FastAPI 那边是另一条路由，而多写一个 `/` 拼出来的地址会打到前缀中间去）。
- **红在先**（四个变异，每个只改一份 `src/api/*.ts`，跑 `npx vitest run tests/api/paths.spec.ts`，跑完 `cp` 还原并核对 md5：`auth.ts fddf9ae8…`、`watchlists.ts 7a20707c…`、`preferences.ts ad53d65e…`、`users.ts b45ed6d8…`）：① `'/auth/sessions'` 前面补上 `/api` → 红在双前缀那条（`expected [ '/api/auth/sessions' ] to deeply equal []`）——**这一句在改之前不会红**，因为旧的 `MODULES` 里没有 auth，那正是本单的立身之本；② `'/watchlists'` 去掉前导斜杠 → 红在「必须绝对路径」；③ `preferences.ts` 两个函数都不再请求（直接 `Promise.resolve`）→ 红在按模块归账那句（`expected [ '@/api/preferences' ] …`），而**总调用数只从 66 掉到 64**，旧那句 `toBeGreaterThan(20)` 照样绿——这就是归账断言的存在理由；④ `/users/${userId}/role` 写成 `/users//${userId}/role` → 红在新加的 `//` 那条。
- **文档同步**：`frontend/CLAUDE.md` 约定清单里那句「`paths.spec.ts` 会自动遍历所有 api 模块」改成了实际形状（12 份、三条规则、按模块归账、新增一份 `src/api/*.ts` 必须同时加进 `MODULES`，漏了不会红）。顺带记一句：**`CHANGELOG.md:698` 那条 2026-09-21 的旧条目写的是「自动遍历全部 api 模块」，从来不是真的**——历史条目按惯例不改写，但引用它的人要知道它说过头了（这正是本仓库反复踩的"文档比代码多说"那一类，只不过这次多说的是我们自己的 changelog）。
- **仍然钉不住的**：路径的**段名**写错（`/auth/session` 少一个 `s` 这种）在任何一层都看不见——这份测试只管形状，真后端 e2e 只有被界面点到的端点才会撞上去。要真签，得把 12 份模块的 URL 对着 OpenAPI（#119 实测 65 路径 / 84 操作）核一遍，而那需要先有一份**提交进仓库的 `openapi.json`**（现在没有；生成它要起着后端跑一次），这一条列进待办，本单不假装覆盖。
- **验证**：`npx vitest run tests/api/paths.spec.ts` **4 passed**；前端单测 **290 passed / 29 files**（289 → 290，新加的那条是 `//` 与尾斜杠规则）、`typecheck:test` 绿。本单没动 `src/`、没动后端、没动 e2e，故未重跑 build / pytest / ruff / mypy / playwright。

### 新增：真后端 e2e 加到 16 条——个人设置页的「退掉那一台」和「主题按人存」第一次打到真库

- **动因**：`Profile.vue` 是除 `NotFound.vue` 外唯一从没在真库上签过字的视图。三件事在别处都没有签名：设备列表（`frontend/e2e/fixtures.ts` **根本没有 `/api/auth/sessions` 处理器**，那 82 条桩用例从没真的请求过它）、单台退出，以及改密码后那句写在卡片上的「其他浏览器会被退出，这台仍然保持登录」——服务层只覆盖 CLI 那条**不带** `keep_token_hash` 的路，也就是说"这台留着"那一半从来没被任何一层测过。
- **第 14 条（个人设置页）**：`frontend/e2e/real/profile.real.spec.ts`，八段、四台真浏览器（owner 两台 + member + 改密码前签进来的第三台）。核对的全是"至少两个各自握着 cookie 的 context 才证得出"的事：同一张会话表在两台里**行集合与顺序一致、而 `current` 各指各的那一行**；界面上点掉「退出」后按「刷新」逼服务端重答一次，清单**只少被点的那一枚摘要**（`handleRevoke` 只在本地筛一遍就收工，不刷新等于没验），被退那台从此 401 而这台仍 200；member 拿 owner 的摘要去删得到 404「设备不存在或已退出」而 owner 那一行原样还在（`revoke_session` 的谓词是 `(user_id, token_hash)`）；主题点「深色」之后**换一路**读回 `dark`（PUT 回显的就是刚写进去的那份，拿它当证据等于自证），member 全程留在 `light`，一台**全新浏览器**（没有 localStorage 可依赖）登录同一账号仍是深色；`{theme:'neon'}` 出不了 `Literal`，422 之后库里仍是 `dark`；改完口令这一台还活着、改密码前签进来的那两台 401、member 那台不受影响（批量撤销只动这个账号）。
- **八个变异，八个都红**（每个单独 `-g 个人设置` 跑，跑完 `cp` 还原并核对 md5：`api/auth.py 23fe94a6…`、`services/auth_service.py e69763b7…`、`api/preferences.py 343b897d…`、`services/preference_service.py 90be60cb…`、`views/Profile.vue 388ed694…`）：① `auth.py:153` 的 `current` 写死成 `True` → 红在 `:88`（第二台读到的"当前"不止它自己那一行）；② `revoke_session` 的谓词摘掉 `UserSession.user_id == user_id` → 红在 `:120`（member 删 owner 那一行得到 204 而不是 404）；③ 改成摘掉 `token_hash` 那半 → 红在 `:109`（紧接着那一次读直接 401：整个账号的会话都被删了，包括点按钮这台自己的）；④ `Profile.vue:217` 的 `v-if="!device.current"` 反相 → 红在 `:97`（当前那行的「管这一台」提示连着它的 `v-else` 一起消失）；⑤ `preference_service.py:27` 的 `get(UserPreference, user_id)` 写死成 `1` → 红在 `:145`（member 看见的是 owner 的 `dark`）；⑥ `preferences.py:20` 的 `Literal` 放宽成 `str` → 红在 `:153`（`{"theme":"neon"}` 回 200）；⑦ `auth.py` 的 `keep_token_hash=hash_token(token)` 换成 `None` → 红在 `:174`；⑧ `auth.py:158` 的 `Path(pattern=TOKEN_HASH_PATTERN)` 摘掉 → 红在 `:134`（形状不对的摘要一路走到服务层，回的是 404 而不是 422）。
- **最值钱的发现不是断言，是 `finally`**：变异⑦第一次跑，报出来的唯一错误是我自己 `finally` 里那句"口令换回去"的断言（`Expected: 204 / Received: 401`，旧 `:187`），第 8 步真正的失败被整条盖掉——**`finally` 里抛出的错误会顶掉 try 块的失败原因**。改法是 `finally` 里一律不断言：另开一台 context 用轮换后的口令登录，登得上才换回原值；"到底换没换回去"交给 `finally` 之后那一次真登录去证（`revived` + `.user-name`）。
- **顺带抓到一条假绿**：还是变异⑦，`:172` 那句 `await expect(rows).toHaveCount(1)` **是绿的**——`Profile.vue` 的 `loadDevices` 在 catch 里保留上一份数组，重读 401 时界面恰好停在"只剩一台"的正确样子。那一步真正签得住的是 `:174` 那份对服务端摘要数组的相等断言；DOM 计数在这里不能单独当证据。
- **单跑和整跑的红位置不一样**：变异①在单独 `-g 个人设置`（TRUNCATE 后库里只有这一条自己的那次登录）下**不会**红在 `:77` 的 `expect(mine).toHaveLength(1)`，而是红在 `:88`；整跑跑到第 14 条时 owner 名下已有十几行活会话，它会更早红。以后写"这条能红"要说清是在哪种跑法下量的。
- **明确不声称的三件事**（写在文件头，不假装覆盖）：① 主题那颗单选钮刷新后的**选中态是不确定的**（`Profile.vue:18` 在 setup 里快照 `getTheme()`，而 `useAuth.ts:47` 的 `loadAccountTheme()` 是 fire-and-forget），所以只断言 `html[data-theme]`，不碰 radio；② 原始 token 从不进任何响应（`auth_service.py:428` 只回摘要），"摘要推不回原值"这一层在浏览器接缝上测不到；③ 退掉**自己当前**这一台在后端是合法的（204、行照删），但界面把按钮藏了（`Profile.vue:217`），浏览器走不到那条路，只能由第 5 段那个跨账号 404 侧证闸门在位。
- **编号与文档同步**：`README.md:384`、`CLAUDE.md:201`、`frontend/CLAUDE.md:655/662/732` 三处计数 15 → 16；`frontend/CLAUDE.md` 逐条段补第 14 条签什么、顺序段链尾改成 `… → 丢失标记 → 个人设置 → 转码 → 删除影片`、`-g` 命令清单八条改九条、转码与删除两条的编号各退一位（`transcode.real.spec.ts:2`「第 14 条」→15、`video-delete.real.spec.ts:2`「第 15 条」→16），接线规矩里"后两个由第 13 条和第 15 条共用"改成第 16 条。`library.real.spec.ts` 那 13 条和 `playwright.real.config.ts` **一个字没改**——新文件靠字母序自己插进 `library` 与 `transcode` 之间，配置里的 `testMatch` 早就覆盖 `*.real.spec.ts`。
- **这次差点改坏的一处**：这些文档在 Windows 工作树里换行是**混着的**（实测 `transcode.real.spec.ts` 300 行全 CRLF，而 `video-delete.real.spec.ts`、`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 全是 LF），所以 `sed -i` 会把命中的那几行改写成 LF，一个文件里出现两种换行。走的是字节路径：先校验每个锚点在文件里**恰好出现一次**，再整体替换、按原字节写回，写完复核行数与 CRLF 计数不变。顺序段里另外两句在 #117/#118 之后就已经过时（「第 12 条排在倒数第二」「第 13 条排在最后」），这次一并按实际约束改成「排在第 8 条之后」「排在第 12 条之后、最后三条之前」。
- **验证**：`-g 个人设置` 单独 **1 passed**（10.6 秒）；真后端 e2e 整跑 **16 passed**（1.4 分钟，本条 8.8 秒）；前端单测 **289 passed / 29 files**（`src/` 一行没改）、`typecheck:test` 绿、`npm run build` 绿；桩 e2e **82 passed**（整跑第一次红一条 `e2e/player.spec.ts:85`，单跑那一个文件 12 passed——和 #115/#117/#118/#119 记过的那一族靠计时器走的用例同源，这一族至今已量到 `:85`/`:92`/`:119`/`:189` 四处）。本单**没动后端一行代码**（八个变异全部还原并核对 md5），故未重跑 pytest / ruff / mypy。
- **覆盖面现状**：浏览器用例总数 **98** 条（真库 **16** + 替身 **82**），`Profile.vue` 从此有真库签字。仍然零真库签字的四样照旧列出、不假装补齐：`storage.reachable()` 那道闸门、转码跑到一半被取消（夹具那段编码只要 0.04–0.06 秒，抢不到中间态）、`mp4`/`mkv` 两行 `acodec`、以及"级联清单在 PG 上改错了不会红"。

### 修复 + 新增：收藏页和历史页移掉最后一页仅剩的那条后不再谎报「暂无」——#113 那条分页教训的另外两处漏口（前端单测 281 → 289）

- **动因**：#113 学到的那句是"界面上那一页可能已经不成立了，重读之前先核对服务器信封"，当时只在 `Home.vue` 补了钳位，触发方式是地址栏里那个越界的 `?page=`（分享链接、浏览器前进后退）。这一单把同一个教训换个触发条件再查一遍：**页面上自己那颗删除按钮**。范围是 `grep 'total > pageSize'` 圈定的——整个前端只有三个视图分页：`Home.vue`、`Favorites.vue`、`History.vue`，后两个都只删行不钳位，于是这一单把同一件事的另外两处一起关掉；从此这一类在仓库里没有第四处。
- **原症状**（两个视图各自复现，形状一样）：在第 2 页把只剩 1 条的那一页移掉，`total` 从 21 变 20 而 `currentPage` 还停在 2，后端照实回 `items: []`、`total: 20`（越界那页不是 404，服务端也不偷偷把页码改成还存在的那一页——见下面的真库断言），前端于是渲染 `el-empty` 那句「暂无收藏视频。」/「暂无观看历史。」。而分页条自己的渲染条件是 `v-if="total > pageSize"`，`total` 正好落到 `pageSize` 那一刻它**整个消失**，`el-pagination` 里那句「共 20 条记录」跟着没了——用户对着一个谎，库里明明还有 20 行，而**回第 1 页的入口恰好在需要它的时候不在**，唯一出路是刷新。历史页更热闹一点：`el-table` 没有 `v-if`，所以同屏摆着两句"什么都没有"（`el-empty` 的「暂无观看历史。」和表格自己的「暂无历史记录」）。
- **红在先**：`frontend/tests/views/Favorites.spec.ts:110` 和 `frontend/tests/views/History.spec.ts:169`，两处都是 `expect(...mock.calls.map(([page]) => page)).toEqual([1, 2, 2, 1])`，对着未修复的 HEAD 实测 `AssertionError: expected [ 1, 2, 2 ] to deeply equal [ 1, 2, 2, 1 ]`——缺的正是"读了越界的空页之后再读一次"那第四脚。`Favorites.vue` 这个视图此前**一个测试都没有**，那 6 条是它的第一个夹具。
- **修复**：两个视图各 +9 行，用的是 `Home.vue` 里那句现成的 `Math.max(1, Math.ceil(result.total / pageSize.value))`，**不抽新抽象**——三处各读自己的 API，共享的只有这一句算术；抽成 composable 反而把"该信哪个信封"从视图里挪走了。`frontend/CLAUDE.md` 的约定清单补了一条，含"别顺手改成删完回第 1 页"。
- **两条反向用例挡的是同一种错误改法**：`keeps the user on the same page when that page still has items left`（45 条排到第 3 页，删一条后断言 `[1, 3, 3]`、卡片区剩 4 张）——用户的阅读位置不是 bug。变异实测：真把"移除成功后回第 1 页"那种改法装上去，**四条**分页用例一起红（`Tests 4 failed | 12 passed (16)`）。反过来，只改钳位的目标值（`lastPage` → `1`）**测不到**，因为钳位那一支只在空页上执行——记这一句是免得下次误以为钳位目标已被钉住。
- **夹具的牙口**（两个视图同一套，值得单记）：`listFavorites` / `removeFavorite` 必须接到**同一份可变的行数组**上（`library()` + `wire()`）。分家写实测过——只 mock 列表、不 mock 删除时，"移除"只成功在提示框里，库里行数一动没动，`[1, 2, 2, 1]` 那类断言会永远绿。另：每页 20 条是这两个视图自己的默认值，所以**夹具至少要 21 条才碰得到第 2 页**；换页唯一入口是点 `.el-pager li` 上那个数字，这条路径本身也在被测范围内。
- **真库那半边**（`frontend/e2e/real/library.real.spec.ts` 第 3 条收藏用例内 +15 行，条数不变）：`GET /api/favorites?page=2&page_size=20` 在真 PostgreSQL 上必须回 **200 + 空 `items` + 诚实的 `total: 1` + 原样回显的 `page: 2` / `page_size: 20`**。前端那句钳位是拿 `total` 算最后一页的，`total` 说假话钳位就空转；这个信封在替身夹具里翻不出来——`fixtures.ts` 那份 `/api/favorites` 处理器**根本不读 `page`**。
- **验证**：前端单测 **289 passed / 29 files**（281 → 289：`Favorites.spec.ts` 新增 6 条、`History.spec.ts` 新增 2 条）、`typecheck:test` 绿、`npm run build` 绿；真后端 e2e 整跑 **15 passed**（1.1 分钟）；浏览器用例总数仍是 **97** 条（真库 15 + 替身 82），本单加宽的是第 3 条的断言厚度而不是条数。桩 e2e **第三次整跑才 82 passed**：前两次各红一条靠计时器走的播放器用例（第一次 `e2e/player.spec.ts:119`、第二次 `:189`），单跑都绿，本单没碰播放器那一侧任何代码——和 #115/#117/#118 记过的那一族是同一件事，这里照记不藏。本单**没动后端一行代码**，故未重跑 pytest / ruff / mypy。
- **顺带量到的**（记下来免得下次猜）：`app.openapi()` 是 **65 个路径 / 84 个操作**；`src/api/` 有 **13** 个请求模块，而 `frontend/tests/api/paths.spec.ts`（早于本单，不是这单写的）只遍历其中 **8** 个，断言也只有"请求路径不带第二个 `/api` 前缀"加 `calls.length > 20`——auth / users / preferences / watchlists 那几份的请求路径没有静态钉子。

### 新增：真后端 e2e 加到 15 条——从界面上删一部影片，磁盘上那张封面必须跟着没（#75 的清理从此有浏览器级签字）

- **动因**：#75 补上的封面清理，当时签它的是两条服务层用例——它们把封面路径喂成临时目录里的一个字符串，验的是"那个函数调用到了"。而从 `.action-buttons` 里那枚「删除」到盘上少一个 `.jpg`，中间还隔着 axios 全局带的 `X-Requested-With`、中间件的 CSRF 与角色两道闸、`DELETE` 的 204、Vue 里那句 `router.push`，以及扫描真写进库里的那列绝对封面路径。这一整串原先没有一处签过字：那 82 条桩用例里的"删除"只是把一份手写响应表里的行抹掉，磁盘从来不在场。
- **红在先**（这条没有对应的修复——行为早就对了，所以红只能**跑出来**）：`backend/src/services/video_service.py:543` 摘掉 `delete_cover_files(covers)`，单独 `-g 删掉一部影片` 红在 `frontend/e2e/real/video-delete.real.spec.ts:158`，报的是那个真路径：`expect(received).toBe(expected) // Received: true`，`D:\…\backend\data\e2e\thumbnails\1\e2e_extra-5edbf2b28314.jpg`。
- **用例 15（删除影片与它名下那张封面）**：`frontend/e2e/real/video-delete.real.spec.ts`，六段。① 在媒体目录里用 ffmpeg **现编**第二条 15 秒的片子（时长和字节数都刻意和播种那部 30 秒的不一样，扫描才会把它认成第二部），扫完核对 `files_found=2 / new_videos=1 / subtitles_found=0`；② 库里那一行是靠"删除前后的 id 集合之差"找出来的（不是 `id=2`），标题解析成 `e2e extra`，它的 `thumbnail_path` 必须落在 `data/e2e/thumbnails/1/` 之下且文件真在——只核对"文件在"挡不住 #63 那个相对路径 bug；③ 给它加一行收藏，好让级联真有一张子表可带，而这一脚故意先**不带** CSRF 头发 `POST /api/favorites/{id}`，403 才算撞过真中间件；④ 从界面上删：按钮 → 确认框里那颗文字是「删除」而不是「确定」的按钮 → 提示「视频已删除」→ 跳回首页；⑤ 库里那行 `GET` 404、`GET /api/videos/{id}/thumbnail` 也 404（`Video not found` 而不是"没有封面"）、**再删一次**得到 404 原话 `Video with id N not found` 而不是一片 500、收藏里那一行跟着没了；⑥ 磁盘上它那张封面没了，而**整个 `thumbnails/` 目录回到删除前那份「相对路径 + 内容 sha1」清单**（这一句才是这条用例最值钱的：删除走的是"先把路径取出来、提交之后再删文件"，一步写错就是把别人的图一起端走），同时用户的 `.mp4` **必须还在**——行是应用建的，片子是用户放的，只有前者归应用管；首页的卡片跟着少一张。
- **三个变异，三个都红**（每个单独 `-g 删掉一部影片` 跑，跑完还原并核对 md5：`video_service.py 5fc720f5…`、`api/videos.py 2a1595ff…`、`VideoDetail.vue 7c04fc0b…`）：① 封面清理整步摘掉 → 红在 `:158`（上面那句）；② `api/videos.py` 的 delete 路由摘掉 `except ValueError` → 红在 `:145`（第二脚删除期望 404，收到 500，webServer 日志里就是那句裸 `ValueError: Video with id 2 not found`）；③ `VideoDetail.vue` 的 `handleDelete` 摘掉 `await deleteVideo(video.value.id)` → 红在 `:138`：提示仍然照说「视频已删除」、URL 仍然回首页，而 `GET /api/videos/2` 回 **200** 把整行原样吐回来。**③ 是这条用例的立身之本**——它证明"删除确实是那枚按钮发出的"，而不是用例自己 fetch 出来的。
- **顺手共用的接线**：`coverFingerprints()` 和 `scanSource()` 从 `library.real.spec.ts` 提进 `e2e/real/support.ts`。第 13 条说的是"扫描不该动别人的封面"，第 15 条说的是"删除只该动自己那一张"，读的是同一个目录、同一份算法，两份各抄一遍就等于约好其中一份会过时。根级登录钩子照旧**每个 spec 自己写一行**（`support.ts` 文件头那条规矩没变）。
- **起点读差值、不写死数**：它是整跑的最后一条，前面 14 条在库里留了收藏、片单、标签、几行非默认 `settings` 和几行通知，所以它开头先 `GET /api/videos` 读一份基线，用 id 集合的差找出新那一行，通知数和收藏数一律按"之前 + 之后"比。
- **实测到的形状**（记下来免得下次猜）：现编那条 15 秒片子扫出来是 `duration=15`、`file_size=4867`、`resolution=64x36`、`title='e2e extra'`、封面 `thumbnails/1/e2e_extra-5edbf2b28314.jpg`（绝对路径）；`GET /api/videos/{id}` 的 404 原话是 `Video not found`，而 delete 那条路的原话是 `Video with id N not found`——两句不一样，用例各钉一处。
- **仍然钉不住的**：级联清单里那几张子表**在 PG 上没法用变异证明**——schema 声明的是 `ondelete="CASCADE"`，真库自己会补刀，所以从 `VIDEO_CHILD_TABLES` 里摘掉 `Favorite` 这一条用例照样绿。这正是 #84 那句"两种方言朝相反方向失败"的另一半，服务层那条清单核对用例（`test_the_explicit_cascade_list_is_every_child_of_videos`）才是挡它的地方；这条用例真正独有的是磁盘那半边。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 14 → 15；`frontend/CLAUDE.md` 逐条那段补第 15 条要签的东西、顺序段"十四条"改"十五条"（链尾加 `→ 删除影片`、`-g` 命令从七条列成八条、并写明它为什么压轴：它是这一轮里唯一会改变库里影片数的一条，且自己的 `.mp4` 由自己的 `finally` 收走）、那条接线规矩里补上新共用的两个函数；`backend/CLAUDE.md` 封面清理那一段写明这一步现在有两层签字，服务层那层验"调用到了"、浏览器这层验"盘上少的正是这一张"。
- **验证**：`-g 删掉一部影片` 单独 **1 passed**（8.6 秒）；真后端 e2e 整跑 **15 passed**（1.0 分钟，单 worker 串行，本条 2.6 秒）；后端 PostgreSQL 全量 **727 passed**（3:20，本单没动后端测试）；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数）；前端单测 **281 passed**、`typecheck:test` 绿、`npm run build` 绿、桩 e2e **82 passed**（34.9 秒；**第一次整跑曾红一条**——`e2e/player.spec.ts:92` 那一条按住拖动的用例，单独跑 1 passed、再整跑 82 passed。它和 #115/#117 记过的那几条靠计时器走的用例是同一族，本单没有碰播放器那一侧的任何代码）。跑完 `data/e2e/` 实测：`media/` 只剩 `e2e_sample.mp4` 与 `e2e_sample.zh.srt`，`thumbnails/1/` 只剩播种那张 `e2e_sample-e21b1144913f.jpg`——现编的片子和它的封面都被自己收走了。
- **覆盖面现状**：浏览器用例总数 **97** 条（真库 **15** + 替身 **82**）。仍然零真库签字的：`storage.reachable()` 那道闸门、转码跑到一半被取消、`mp4`/`mkv` 两行 acodec，以及上面那条"级联清单在 PG 上改错了不会红"。

### 新增：真后端 e2e 的夹具带上音轨，转码配方的音频半边从此能红（#115 的变异⑧翻红）

- **动因**：#115 那八个变异里唯一绿的一个（⑧：把 webm 的 acodec `libopus` 改成容器明确拒收的 `aac`）不是断言写歪了，是**夹具的问题**——播种那部片子只有一条视频轨。源里没有音频流时 ffmpeg 把 `-c:a` 整个跳过（实测：无声夹具 + `-c:v libvpx-vp9 -c:a aac` 回 **rc=0**、写出一个 1332 字节只含 vp9 的 webm），于是 `SUPPORTED_FORMATS` 里音频那一列在**整套测试**中没有一处被执行过；而 `acodec` 又不进任何 API 响应（`get_supported_formats` 只回 `codec` 和 `extension`），接口那侧也拦不住写错的值。
- **红在先**：先把断言写进 `expectRealOutput`（新增的 `probeStreams` 去问 `ffprobe`：产物必须是配方那一对编码器），再拿**旧夹具**单独跑一次 `-g 转码` —— 红在 `frontend/e2e/real/transcode.real.spec.ts:151`，`Expected [['audio','opus'],['video','vp9']] / Received [['video','vp9']]`。这一步先跑，是为了证明这条断言确实有牙，而不是和夹具一起改完直接绿。
- **夹具**：`backend/src/e2e_seed.py` 的 `SAMPLE_MP4_B64` 换成 64x36 黑帧、1 fps、30 秒，外加一条 1 秒的 44100 Hz 单声道正弦（AAC），5008 字节（原 1882）。时长仍是 `30.000000`、封面仍是 320×180，所以扫描、播放、`Range`、继续观看那几条用例的断言**一个字都没改**，整跑仍是 14 条。
- **用例**：`transcode.real.spec.ts` 现在对两个产物各核一份流清单（webm → `vp9` + `opus`，avi → `h264` + `aac`），不再只看文件头那几个字节。`STREAMS` 里写的是 ffprobe 那一侧的编码器名，不是配方字面值（`libvpx-vp9` → `vp9`、`libopus` → `opus`、`libx264` → `h264`），这层映射是手抄的。
- **三个变异**（每个单独 `-g 转码` 跑，跑完 `cp` 还原并核对 md5 `b18c9b52…`）：① webm 的 acodec → `aac`，也就是 #115 那个绿的⑧，**现在红了**——红在 `.status-section` 那句「已完成」（现 :206），页面上直接摆着容器自己那句话：`Only VP8 or VP9 or AV1 video and Vorbis or Opus audio and WebVTT subtitles are supported for WebM.`（顺带又一次实测了 #74 那条"失败原因必须露出来"：这句话是 `transcode_error` 的 `error` 原样进界面）；② avi 的 acodec → `libopus` 红在 avi 状态四元组那一句（现 :266；AVI 同样不收 opus，任务落 `failed`）；③ webm 的 vcodec → `libx264` 红在格式清单那一句（现 :184，接口那侧先把它挡住），新增的 `['video','vp9']` 是同一件事的第二道闸门——只有"清单和命令行各自读一份表"这种改法才轮到它红。
- **仍然没钉住的**：四行配方里 `mp4` 与 `mkv` 两行的 acodec 还是零真进程签字。mp4 造不出产物（源文件本身是 mp4，同格式覆盖被闸门拒绝），mkv 的 `aac` 虽然和 avi 的 `aac` 是同一个字面值，但**只改 mkv 那一行不会红**，因为用例不产 mkv。这条写进用例注释，不假装覆盖。
- **播种侧的闸门**：`backend/tests/test_e2e_seed.py` 现在除了尺寸还钉 `blob.count(b"trak") == 2` 和 `b"mp4a" in blob`——音轨被无声地换回"只有一条视频流"时，红在 `pytest` 的半秒里，而不是等到真 PG 加真 FFmpeg 都起来的那条 e2e 才看得见。
- **顺带看到的**：变异①那一趟失败后，媒体目录里留下一个 262 字节的坏 `e2e_sample.webm`，而用例的 `produced` 只在断言通过后才把路径交出去。不用管它——下一次起跑 `prepare_media` 整目录重建。记这一句是为了别把"跑完目录是干净的"误当成用例自己负责的证据。
- **文档同步**：`frontend/e2e/real/library.real.spec.ts` 文件头的夹具描述（1882 字节 → 5008 字节 + 一条 AAC 音轨）、`transcode.real.spec.ts` 文件头补上"问 ffprobe 的那两条流"和"夹具必须带音轨"这条前提、`frontend/CLAUDE.md` 两处（第 14 条要签的东西 + 播种那一行的夹具形状）、`backend/CLAUDE.md` 薄位置清单里 `utils/ffmpeg.py` 那条（现在也核对产物里的流）。
- **验证**：`-g 转码` 单独 **1 passed**（6.1 秒，三个变异还原之后）；真后端 e2e 整跑 **14 passed**（1.0 分钟，单 worker 串行）；后端 PostgreSQL 全量 **727 passed**（3:31，和 #115 同数——本单没加服务层用例，只改了播种闸门那一条的断言）；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数）；前端单测 **281 passed**、`typecheck:test` 绿、`npm run build` 绿、桩 e2e **82 passed**（35.8 秒）。跑完 `data/e2e/media/` 只剩 `e2e_sample.mp4` 与 `e2e_sample.zh.srt`。
- **覆盖面现状**：浏览器用例总数仍是 **96** 条（真库 14 + 替身 82），本单加宽的是第 14 条的**断言厚度**而不是条数。#115 那份"仍然零真库签字"的清单里，**音频那半张配方已经划掉**（webm、avi 两行已签，mp4、mkv 两行见上），剩下的是 `storage.reachable()` 那道闸门（要一个"列不出来"的源，服务层那份假存储带这个开关）和转码跑到一半被取消（30 秒的片子实测 0.04–0.06 秒转完，没有可靠的"中途"窗口）。

### 修复 + 新增：转码格式名的大小写会先回 200 再在后台失败；真后端 e2e 加到 14 条（转码长流程）

- **动因**：转码是这一套里最后一条"从没在真库、真进程上签过字"的长流程，而它被**两层假**夹着：82 条桩用例把 `/api/transcode*` 四个端点全写在 `frontend/e2e/fixtures.ts` 自己的处理器里（那份处理器**不做任何校验、也永远不会失败**，`output_path` 写死成 `/tmp/out.<格式>`），后端 11 条服务用例里凡是走到编码那一步的 5 条又把 `transcode_video` 整个换掉、剩下 6 条只测拒绝。于是"真起一个 FFmpeg、真往磁盘写一个文件、真由后台任务写一行通知"这一段，整套测试没有一处跑过——大小写那个 bug 正是从这条缝里掉下去的。
- **原症状**（走出来的，不是推测）：闸门 `check_format_support` 大小写不敏感，而编码器查表 `SUPPORTED_FORMATS.get(...)` 敏感，输出文件的扩展名用的也是原串。发 `target_format: "AVI"` 时 HTTP 那侧先回 **200 `{"status": "started", "target_format": "AVI"}`**（界面据此弹「转码任务已启动」），任务再在后台失败成「不支持的格式：AVI」——同一个请求先说"开始跑了"、再说"我根本不认识这个格式"。
- **红在先**：`backend/tests/test_services/test_transcode_service.py:133`（新用例 `test_target_format_is_normalized_before_the_encoder_sees_it`）先跑红，实测 `AssertionError: {'video_id': 1, 'status': 'started', 'target_format': 'MKV', 'output_path': '…\movie.MKV'} / assert 'MKV' == 'mkv'`。这条用例把**真正递给编码器的那个字符串**钉住（spy 记下 `(output_path, target_format)`），其余用例都把 `transcode_video` 换掉了，参数是什么从来没人看。
- **修复**：`TranscodeService.transcode` 在**进闸门之前**做 `target_format = target_format.lower()`，并写明为什么不放在闸门里——只归一其中一处，被放行的那个原串还是会在下一张查表上落空，那时 200 已经发出去了。归一之后闸门、`with_suffix` 拼的扩展名、编码器查表和通知里那个 `data.format` 拿到的是同一个值。
- **用例 14（转码长流程）**：`frontend/e2e/real/transcode.real.spec.ts`，七段。① 格式清单四项各带编码器和**带点的**扩展名（替身那份是没点的 `'mkv'`）；② 界面上选 webm → 确认 → 不刷新也轮询到「已完成 / WEBM」，状态四元组 `['completed', false, 100, null]`，`expectRealOutput` 核对服务器报回来的那个**绝对路径**落在 `data/e2e/media/` 里、`existsSync`、非空，并读文件头 64 字节里的容器自报家门（EBML 的 DocType / RIFF 的 FormType，**不看文件名**），通知总数 +1 且 `data` 是 `{video_id: 1, format: 'webm'}`；③ 同格式（mp4→mp4）必须被拦住并且说的是原话 `overwrite the original file`，被拒之后状态对象原样、通知不多发、**源文件的 sha1 一个字节没变**；④ 不认识的格式 400 `Unsupported format: exe`，不进任务表也不发通知；⑤ 大写 `'AVI'` 走 API——`['started', 'avi']`、`waitSettled` 后 `['completed', null, 'avi', 100]`、产物是真 avi、第二条通知的 `data.format` 用的是归一后的写法（这一段就是本单那个 bug 的回归位置）；⑥ 对已结束的任务 `POST /cancel` 得到 404 `No active transcoding`，且拒绝不许顺手把记录改掉；⑦ 转码不往库里加片子（`GET /api/videos` 的 `total` 仍是 1）。产物由 `test.afterEach` 自己删——它们就在被扫描的目录里，留着下一轮就成了一部新片子。
- **八个变异，七个红一个绿**（每个改完单独 `-g 转码` 跑，跑完 `cp` 还原并核对 md5）：① 摘掉 `.lower()`（= 提交前行为）→ 红在 `transcode.real.spec.ts:225`（期望 `['started','avi']`，收到 `['started','AVI']`），同一处服务层用例红在 `:133`；② webm 的 vcodec `libvpx-vp9` → `libx264` → 红在 `:146`（格式清单里那一行的 codec）；③ 给 ffmpeg 命令加一个 `-f mp4`（容器与扩展名不一致）→ 红在 `:111`，正是 `expectRealOutput` 读文件头那一句——**这一条专门证明"不看文件名、看字节"有牙**；④ 通知的 `data` 里去掉 `format` 键 → 红在 `:189`（`toMatchObject` 那个 `data.format`）；⑤ 摘掉成功时的 `job.progress = 100.0` → 红在 `:230`（avi 那一路最后一条 `out_time` 是 28 秒 / 30 秒的片子，照它算只有 93.3；webm 那趟容器自己补到了 30 秒，所以它证不到这件事）；⑥ 同格式闸门改成 `if False:` → 红在 `:200`（`.el-message--error` 等不到那句话）；⑦ `cancel()` 的 `if not job or job.status != "running"` 改成只判 `if not job` → 红在 `:251`（期望 404 收到 200）。⑧ **绿的那个**：webm 的 acodec `libopus` → `aac`（`ffmpeg.py` 注释里"WebM rejects aac"对应的正是这个错值）整跑下来照样绿。原因实测：夹具这部片子**只有视频轨**（`ffprobe` 一条 stream，h264），`-c:a` 从没被用上，而 `FormatInfo` 也不把 acodec 报给界面——**音频那半张配方现在仍然没有任何一层测得到**，这条已写进用例注释，不假装它被覆盖了。
- **没有写的那条断言**：「跑到一半取消」。夹具那部 30 秒的片子实测 0.04–0.06 秒就转完，"中途"这个窗口靠计时器赌运气，而本项目已经把靠计时器走的用例归进抖动的一类（`player.spec.ts` 那几条）。能被真进程钉住的取消语义是"只认还在跑的那一个"，它由第⑥段那条 404 钉住。
- **踩到的**：`signIn` / `fetchInPage` / `requestJson` / `CSRF` 抽到共用的 `e2e/real/support.ts` 之后，把根级 `test.beforeEach(signIn)` 也一并放在那里——结果是**单独 `-g` 跑每个文件都绿、整跑时第 14 条红在 `Failed to execute 'fetch' on 'Window': Failed to parse URL from /api/transcode/formats`**（页面停在 `about:blank`，相对地址拼不出来，其余 13 条全过）。Playwright 的根级钩子只绑在"第一个 import 到该模块的文件"上（模块被缓存，第二个文件的 import 不再执行一次），所以这一行必须每个 spec 自己写。
- **文档同步**：`README.md`、`CLAUDE.md`、`frontend/CLAUDE.md` 三处计数 13 → 14；`frontend/CLAUDE.md` 逐条那段补第 14 条要签的东西（含"两层假"那两句和 acodec 证不到这件事），顺序段从"十三条"改"十四条"（链尾加 `→ 转码`、`-g` 命令从六条列成七条，并写明第 14 条为什么必须压轴：它往 `notifications` 留两行，而第 9 条把整张通知表当成"只有播种那一行"；它末尾还要核对 `GET /api/videos` 的 `total` 仍是 1）以及那条接线规矩（钩子各自注册）；`backend/CLAUDE.md` 的薄位置清单里 `utils/ffmpeg.py` 那条补上"真跑那一趟现在有了，但它活在另一个进程里、不进这份读数"。
- **验证**：真后端 e2e **14 passed**（单 worker 串行，1.0 分钟；第 14 条 5.4 秒；八个变异全部还原之后整跑）；`-g 转码` 单独跑 **1 passed**（11.1 秒）；后端 PostgreSQL 全量 **727 passed**（3:35，726 → 727 是本单新增那条服务层用例），`--cov=src` TOTAL **92%**，其中 `services/transcode_service.py` 87%、`api/transcode.py` 85%；`ruff check .` **0 项**、`mypy src` **34 项**（基线同数）；前端单测 **281 passed**、`typecheck:test` 绿、`npm run build` 绿、桩 e2e **82 passed**（35.1 秒）。跑完 `data/e2e/media/` 实测只剩 `e2e_sample.mp4` 与 `e2e_sample.zh.srt` 两个文件，产物都被 `afterEach` 收走了。
- **覆盖面现状**：浏览器用例总数实测 **96** 条——打真库 **14** 条，其余 **82** 条继续对着 `e2e/fixtures.ts` 的替身。真后端 e2e 那份共享接线现在收在 `e2e/real/support.ts`（登录、带 cookie 的 fetch、JSON 请求、CSRF 头），两份 spec 各自注册登录钩子。仍然零真库签字的：转码命令里**音频那半张配方**（见变异⑧）、`storage.reachable()` 那道闸门（它要的是一个"列不出来"的源，服务层那份假存储带这个开关）。

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
