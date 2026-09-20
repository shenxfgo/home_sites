# 多用户认证与权限设计文档

**创建日期：** 2026-09-20
**状态：** M1 认证骨架已实施（2026-09-20），M2–M4 待做
**版本：** 1.1
**适用范围：** 局域网自托管；公网部署需要的额外项见 [§12](#分期实施)

---

## 目录

1. [背景与目标](#背景与目标)
2. [三条决定性约束](#三条决定性约束)
3. [角色与权限矩阵](#角色与权限矩阵)
4. [数据模型](#数据模型)
5. [认证流程](#认证流程)
6. [鉴权实施](#鉴权实施)
7. [会话安全与 CSRF](#会话安全与-csrf)
8. [数据迁移](#数据迁移)
9. [前端设计](#前端设计)
10. [登录页设计](#登录页设计)
11. [测试策略](#测试策略)
12. [分期实施](#分期实施)
13. [被否决的方案](#被否决的方案)
14. [待确认项](#待确认项)

---

## 背景与目标

现状：`backend/src` 全仓没有任何认证或授权代码，11 张表没有一列指向"人"，55 个端点全部匿名可访问。原设计文档（`2026-07-26-video-platform-design.md` §安全考虑）只写了"支持配置访问白名单""路径遍历防护"，没有落到实现。

目标：

1. 未登录不能读写任何业务数据。
2. 每个家庭成员有独立账号，收藏 / 播放进度 / 稍后看 / 观看统计互不可见、互不覆盖。
3. 区分"管理者"与"普通成员"：删库、扫描、转码、改设置这类破坏性操作收敛到管理员。
4. 不引入外部认证服务，不改变现有部署方式（`uv run uvicorn` + 前端静态托管）。

非目标：公网开放注册、第三方登录（OIDC/OAuth）、2FA、细粒度 RBAC、按视频源做 ACL。

---

## 三条决定性约束

写代码前先记住这三条，它们决定了下面几乎所有选择：

**1. 播放器走的是浏览器原生资源请求。** `<video src="/api/videos/{id}/stream">`、`<img src=".../thumbnail">`、`<track src=".../subtitles/{id}/stream">` 都发不出 `Authorization` 头。所以 **localStorage + JWT 方案在这里不成立**（把 token 拼进 query 会泄漏到访问日志与浏览器历史）。结论：用 **HttpOnly Cookie 会话**。

**2. 项目没有 Alembic。** Schema 演进的唯一途径是 `src/database/session.py::init_db()` 里 `create_all` 之后的幂等 SQL 常量（`ADDED_COLUMNS` + `PRAGMA table_info`，加唯一索引前先 `DEDUPE_*`）。`user_id` 列和索引替换必须走这套，见 §8。

**3. 测试用的内存库 fixture 不跑 `init_db()`**（`tests/conftest.py:17-38` 只有 `create_all`）。所以任何新约束必须**同时**声明在模型上，否则"测试全绿、真库缺索引"。

---

## 角色与权限矩阵

只有两个角色，不做权限表。

| 能力 | member | owner |
|---|---|---|
| 浏览 / 搜索 / 播放 / 字幕 | ✅ | ✅ |
| 收藏、播放历史、稍后看、观看统计 | ✅（仅自己的） | ✅（仅自己的） |
| 修改自己的偏好（主题、播放器设置）与密码 | ✅ | ✅ |
| 视频源增删改、扫描、停止扫描 | ❌ | ✅ |
| 转码（发起/取消）、删除视频、编辑视频元数据、标签管理 | ❌ | ✅ |
| 系统设置（扫描间隔、缩略图尺寸、默认格式） | ❌ | ✅ |
| 用户管理（建号、禁用、改角色、重置密码、踢下线） | ❌ | ✅ |

判定规则：**读接口只看"是否登录"，写接口按矩阵看角色**。视频库本身对所有登录用户可见（不做源级 ACL）。

---

## 数据模型

### 新增：`users`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | PK | |
| `username` | String(64) unique not null | 登录名，小写归一后存储 |
| `password_hash` | String(128) not null | bcrypt(cost 12) |
| `role` | String(20) not null default `member` | `member` / `owner`，CHECK 约束 |
| `display_name` | String(64) null | 界面显示名 |
| `is_active` | Boolean not null default True | 禁用而非删除，保留其历史数据 |
| `created_at` / `last_login_at` | DateTime(tz) | 一律 `lambda: datetime.now(timezone.utc)` |

### 新增：`sessions`

| 列 | 类型 | 说明 |
|---|---|---|
| `token_hash` | String(64) PK | `sha256(随机 32B url-safe token)`，明文只出现在 Cookie 里 |
| `user_id` | FK→users.id CASCADE, indexed | |
| `created_at` / `expires_at` | DateTime(tz) not null | "记住我" 30 天，否则 12 小时滑动 |
| `last_seen_at` | DateTime(tz) | 滑动过期用，写入节流到 5 分钟一次 |
| `user_agent` | String(256) null | 仅用于"我的设备"列表展示 |

服务端可撤销是选 DB 会话而非签名 Cookie 的唯一理由，家庭场景值这点复杂度。

### 新增：`user_preferences`

`(user_id PK/FK, prefs JSON)`。把现在 `settings` 表里的**界面偏好**（主题、播放器偏好）搬进来；`settings` 退化为纯系统配置（扫描间隔、缩略图尺寸、默认转码格式），仅 owner 可写。

### 新增：两张"已读"关联表

`new_videos`（扫描发现日志）和 `notifications`（扫描/转码产生的系统通知）本质是**广播内容**，不该按人复制行。做法是保留全局行 + 记录每人已读：

- `new_video_reads(new_video_id FK PK, user_id FK PK)`
- `notification_reads(notification_id FK PK, user_id FK PK)`

`mark_read` 从"UPDATE 那一行"变成"INSERT 一条已读"；`mark_all_read` 变成批量 INSERT；`unread_count` 变成 `LEFT JOIN ... WHERE r.user_id IS NULL`。删除通知/新视频时随 FK CASCADE 清理。

### 改造：加 `user_id` 的既有表

| 表 | 改动 | 备注 |
|---|---|---|
| `favorites` | +`user_id` FK CASCADE indexed；唯一约束改 `(user_id, video_id)` | 现在是裸 `(video_id)` |
| `play_history` | +`user_id`；**必须删掉 `video_id` 上的全局唯一索引**，换 `(user_id, video_id)` 唯一 | 见 §8，这是唯一有破坏性的迁移 |
| `watch_events` | +`user_id` indexed | 观看统计按人聚合 |
| `watchlists` | +`owner_id` FK→users.id CASCADE indexed；唯一约束 `(owner_id, name)` | 清单是个人资产 |
| `watchlist_items` | 不加列 | 归属随 `watchlists` |
| `videos` | **不加列** | `view_count` / `rating` / `last_played_at` 保留为全站共享的"热度"，个人进度一律以 `play_history` 为准 |
| `video_sources` / `tags` / `subtitles` | 不加列 | 库级共享资源 |

### 越权面（改造时必须一并修掉）

现在这些接口按裸 id 操作，登录后 A 能改/删 B 的数据，加列后必须改成"按 (id, user_id) 定位"：

- `history_service.py:146` 删除历史记录
- `notification_service.py:63/87` 标记已读、删除通知
- `watchlist_service.py:51/71/84/93/119` 清单的读改写、加删条目
- `video_service.py:440` `mark_video_viewed`

---

## 认证流程

```
POST /api/auth/login   {username, password, remember?}
  → 200 {id, username, role, display_name}
  → Set-Cookie: sid=<token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=...
  → 401 {"detail":"账号或密码错误"}      （账号不存在与密码错误同一响应，防枚举）
  → 429 {"detail":"尝试过于频繁，请稍后再试"}

GET  /api/auth/status   公开 → {authenticated: bool, needs_setup: bool}
GET  /api/auth/me       → 当前用户；未登录 401
POST /api/auth/logout   删 sessions 行 + Max-Age=0 清 Cookie
POST /api/auth/password {old_password, new_password} → 成功后撤销其它所有会话
```

**建号只走 CLI，不开注册接口：**

```bash
cd backend && uv run python -m src.cli create-user --username admin --role owner
# 交互式读密码，不回显；已存在则报错退出
uv run python -m src.cli list-users
uv run python -m src.cli set-role --username admin --role member
uv run python -m src.cli revoke-sessions --username admin
```

`needs_setup`（users 表为空）用于首启引导：登录页此时显示"还没有账号，去后端执行 create-user"的提示，而不是让人对着一个永远登不进去的表单猜。

---

## 鉴权实施

**双层，各管一件事：**

1. **`AuthMiddleware` 默认拒绝** —— 只管"登录了吗"。非 `/api/` 前缀直接放行（静态资源、SPA 路由）；`/api/auth/login`、`/api/auth/status`、`/health` 白名单；其余 `/api/*` 无有效会话 → `401` JSON。命中后把 `user`/`session` 挂到 `request.state`，供下游依赖复用，避免二次查库。

   > 为什么不用逐路由 `Depends`：现在 55 个端点，将来还会加。**漏挂一个就等于整个方案失效**，而且新加接口的人不知道要挂。默认拒绝把"忘记保护"变成"忘记放行"，后者会立刻炸在手上，是能被发现的 bug。

2. **`require_role("owner")` 依赖** —— 只管"够格吗"，挂在写接口上，不满足 → `403`。角色检查的接口数量少且语义明确，适合显式声明。

中间件内取 DB：直接 `async with sessionmaker()()`，不走 `get_session` 依赖（中间件拿不到它）。注意别在每个请求上多开一次连接池等待——SQLite 单文件，家庭并发下可接受。

会话校验顺带做惰性清理：`expires_at < now` 的行删掉，不引入后台任务。

---

## 会话安全与 CSRF

- **Cookie**：名字 `sid`，`HttpOnly` + `SameSite=Lax` + `Path=/`；`Secure` 由配置项 `auth_cookie_secure` 控制，默认 `False`（局域网 http），公网 https 部署时打开。
- **CSRF**：`SameSite=Lax` 已挡住跨站 POST；再补一道——所有写接口只接受 `Content-Type: application/json`（跨站表单发不出这个类型），且 `AuthMiddleware` 对非 GET 请求校验 `X-Requested-With: fetch`（跨域脚本无法设置自定义头）。前端 axios 实例统一加这一个头即可。
- **CORS**：现有配置已经是 `allow_credentials=True` + 显式 origin 列表（`main.py:49-55`），符合带 Cookie 的要求。生产同域托管 dist 时 CORS 根本不参与。
- **登录限流**：进程内字典记 `(ip, username)` 连续失败次数，5 次锁 10 分钟，重启清零。家庭局域网下够用，不值得引入 Redis。
- **密码哈希**：直接用 `bcrypt` 包（`bcrypt.hashpw` + `checkpw`，cost 12）。
  **同时删掉 `pyproject.toml` 里的 `passlib[bcrypt]` 和 `python-jose`** —— 全仓零引用，且 passlib 自 2020 年停更、与 bcrypt≥4 有兼容告警。留着它们只会让人以为认证已经存在。
- **备份即含凭据**：`data/videos.db` 现在是密码哈希 + 会话表所在，`README` 的备份说明要加一句"等同备份登录凭据"。

---

## 数据迁移

无 Alembic，全部走 `init_db()` 的幂等 SQL。**执行前提醒用户复制一份 `data/videos.db`。**

顺序（每一步都可重复执行）：

1. `create_all` 建新表（`users` / `sessions` / `user_preferences` / 两张 `_reads`）。
2. `ADDED_COLUMNS` 元组给 5 张表加可空 `user_id` / `owner_id` 列。
3. **回填**：若 users 为空，不自动建号；把既有 `favorites` / `play_history` / `watch_events` / `watchlists` 行留给"第一个 owner 账号"——做法是记录一个 `legacy_owner_id = NULL`，在 `create-user --role owner` 首次执行时把 `user_id IS NULL` 的行 UPDATE 给它。
   > 不做这一步的话，升级后所有历史进度和收藏在界面上消失，用户会以为数据丢了。
4. **`play_history` 唯一约束替换**（唯一有破坏性的一步）：
   - 模型侧删掉 `src/models/history.py:23` 的 `unique=True`，否则内存库测试仍按"一视频一行"建表（§约束 3）。
   - `DROP INDEX IF EXISTS ix_play_history_video_id`（`session.py:22-25` 建的那个）。
   - 先按 `(user_id, video_id)` 去重（同键保留 `played_at` 最新一条，参照既有 `DEDUPE_PLAY_HISTORY` 的写法），再 `CREATE UNIQUE INDEX IF NOT EXISTS ux_play_history_user_video ON play_history(user_id, video_id)`。
   > 不删旧索引的话，第二个用户播放同一视频直接 INSERT 冲突。
5. **`favorites` 新增 `(user_id, video_id)` 唯一索引前先去重**：该表今天**没有任何唯一约束**（`src/models/favorite.py` 只有 `id` PK），同一视频可能已有多行，直接建唯一索引会失败。
6. 新索引：`sessions.user_id`、`favorites.user_id`、`watch_events.user_id`、`watchlists.owner_id`、两张 `_reads` 的外键列。
7. **同步声明在模型上**（约束 3），保证内存库测试与真库一致。

---

## 前端设计

- **`src/composables/useAuth.ts`**（项目没有 Pinia，沿用 `useTheme` 的模块级 ref 风格）：`user` / `status` / `login()` / `logout()` / `fetchMe()`，导出 `isAdmin` computed。
- **`src/api/auth.ts`**：`login` / `logout` / `getMe` / `getAuthStatus` / `changePassword`。
- **路由**：`/login` 用**独立布局，不套 `MainLayout`**（顶栏本身会泄露"有哪些功能、有没有数据"），`meta: { public: true }`；`beforeEach` 里非 public 且未登录 → `/login?redirect=<fullPath>`。启动时 `fetchMe()` 一次，结果缓存在 composable。
- **axios 拦截器**（`src/api/client.ts:13` 现有位置）：加一条"401 → 清空 auth 状态 + 跳登录并带 redirect"。注意 `<img>` / `<track>` 的 401 不经过拦截器，靠路由守卫兜底 + 图片 `onerror` 占位。
- **`MainLayout`** 右侧用户菜单：显示名 + 角色标记，菜单项"修改密码 / 退出登录"，owner 额外看到"用户管理"。管理入口用 `v-if="isAdmin"` 隐藏 —— 只是体验，**后端必须再判一次**。
- **`views/Users.vue`**（owner）：列用户、建号、改角色、禁用、踢下线。
- **`views/Profile.vue`**：改密码 + 个人偏好（把现在 `Settings.vue` 里的"界面设置/主题"迁过来，`Settings.vue` 只留系统配置并加 owner 守卫）。

---

## 登录页设计

对齐现有深色影院风（`styles/theme.css` 令牌），不引入 `backdrop-filter` 和渐变光斑。

**布局**：全屏影院黑 + 轻微暗角，中央 420px 面板（`--radius-panel: 12px`）。面板内自上而下：字标 "Home Sites"（`--accent`）→ 一行说明"家庭视频库"→ 用户名 → 密码 → 记住我 + 登录按钮。

**令牌用法**：主按钮底色用 `--accent-fill` 垫白字，**不能**用 `--accent`（主题文档明确：同一紫色做不到既让白字达 4.5:1、又在深底上达 4.5:1）。

**控件**：`el-input` + `prefix-icon`（`User` / `Lock`），密码框 `show-password`；`autocomplete="username"` / `"current-password"`；用户名 autofocus；回车提交；提交中按钮 `loading` 且禁用整个表单。

**反馈**：
- 失败 → 面板内 `el-alert` "账号或密码错误"，不区分账号不存在/密码错，不显示剩余尝试次数。
- 429 → "尝试过于频繁，请稍后再试"，按钮禁用到倒计时结束。
- `needs_setup` → 表单替换为引导卡片，给出 `create-user` 命令。
- 登录成功后跳 `redirect` 参数指向的原页面，默认首页。

**不做**：注册入口、忘记密码、第三方登录、验证码（局域网无必要）。

---

## 测试策略

**后端**

- 现有 `client` fixture 在 4 个测试文件里各抄了一份（`test_history.py:31-48` 等）→ **提到根 `tests/conftest.py`**，并加 `as_role` 参数：默认覆盖 `get_current_user` 为 owner，避免 278 个既有用例集体改。
- 新增 `tests/test_api/test_auth.py`：登录成功/失败/枚举同响应、限流、me、logout、改密后其它会话失效、`needs_setup`。
- 新增 `tests/test_middleware/test_auth.py`：未登录访问每个 `/api/*` 前缀都 401（参数化列全部路由，防"漏挂"回归）、白名单可匿名、member 打 owner 接口 403。
- 新增 `tests/test_services/test_isolation.py`：**A 的收藏/历史/清单/统计不出现在 B 的列表里；A 按 id 删 B 的行返回 404**。这是多用户改造真正的价值点，越权清单（§数据模型末尾）逐条要有用例。
- 迁移用例：给一个带旧数据的库跑 `init_db()` 两次，断言幂等且回填正确（含 `play_history` 索引替换）。

**前端**

- `tests/composables/useAuth.spec.ts`、`tests/views/Login.spec.ts`（失败提示、回车提交、redirect）、`tests/router.spec.ts` 补守卫用例（未登录跳 `/login?redirect=`、public 路由放行）。
- `e2e/fixtures.ts` 的接口替身加 `/api/auth/*` 分支（未登录 → 401），新增 `e2e/login.spec.ts` 走一遍"被拦到登录页 → 登录 → 回到原页面"。
- 验收：`uv run pytest`、`npm run test`、`npm run test:e2e`、`npm run build` 全绿。

---

## 分期实施

四期，每期结束都是一个可用状态，可独立验收。

| 期 | 内容 | 验收 |
|---|---|---|
| **M1 认证骨架** ✅ | `users`/`sessions` 模型、bcrypt、`cli.py create-user`、`/api/auth/*`、`AuthMiddleware` 默认拒绝、登录页 + `useAuth` + 路由守卫 + 401 拦截。限流与 `X-Requested-With` 校验一并提前做完 | 未登录访问任何 `/api/*` 都 401（`tests/test_middleware` 逐端点扫面 71 例）；能登录、能退出、刷新保持 |
| **M2 数据归属** | 5 张表加 `user_id`/`owner_id` + 两张 `_reads`、§8 迁移、service 层全部过滤、越权清单修复 | 两个账号数据互不可见；老数据回填到第一个 owner；越权用例通过 |
| **M3 角色与管理** | `require_role`、`user_preferences` 与 `settings` 拆分、`views/Users.vue`、`views/Profile.vue`、顶栏用户菜单 | member 看不到也调不动管理接口；主题偏好按人保存 |
| **M4 收尾** | "我的设备"会话列表、README/CLAUDE.md/CHANGELOG 更新、公网部署注意事项（`auth_cookie_secure`、反代 https） | 全量测试 + 浏览器真机走查 |

**公网路线（本期不做，只保留口子）**：角色矩阵与 Cookie 的 `Secure` 开关已为此准备好；真要暴露公网，优先在反代加 mTLS 或 IP 白名单，其次才考虑接 Authentik/Authelia。

---

## 被否决的方案

| 方案 | 否决理由 |
|---|---|
| JWT in localStorage + `Authorization` 头 | `<video>` / `<img>` / `<track>` 发不出该头，播放器与缩略图会整片 401（§约束 1） |
| JWT 放签名 Cookie | 服务端无法撤销，且要管 `SECRET_KEY` 轮换；家庭场景"能踢下线"比"无状态"值钱 |
| 反代 basic auth / Authelia | 运维成本高于收益，且应用内角色矩阵、按人数据归属它都做不到 |
| RBAC 权限表 + 角色多对多 | 两个角色的固定矩阵，权限表是纯过度设计 |
| 每人开一个浏览器 profile 隔离 | 零成本但无真正隔离，且移动端/电视端体验很差 |
| 通知/新片按用户复制行 | 扫描一次要为 N 个用户插 N 行、加用户还要回填；已读关联表更省 |

---

## 待确认项

1. **`videos.view_count` / `rating` 保持全站共享**（本设计的默认）—— 若希望"我打过的分"独立，需要再加一张 `user_ratings` 表。
2. **视频库对所有登录用户可见** —— 若某些源只想自己看得到，需要 `source_acl(source_id, user_id)`，M2 之后单独排期。
3. **老数据回填给"第一个 owner 账号"** —— 若希望按人重新分配，需要 `cli.py reassign --from-legacy --to <username>`。
4. **是否现在就删 `passlib` / `python-jose` 依赖**（推荐删，避免误导）。
