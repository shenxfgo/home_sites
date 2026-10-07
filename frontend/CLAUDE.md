# CLAUDE.md - 前端开发规范

## 技术栈

- Vue 3.4+
- TypeScript 5.0+
- Vite 5.0+
- Element Plus 2.5+
- Vue Router 4
- Axios
- npm（包管理器）

## 代码规范

### Vue 组件风格

```vue
<template>
  <!-- 使用 Element Plus 组件 -->
  <el-button type="primary" @click="handleClick">
    {{ buttonText }}
  </el-button>
</template>

<script setup lang="ts">
// 使用 Composition API + <script setup>
import { ref } from 'vue'

// 定义 props
interface Props {
  buttonText?: string
}

const props = withDefaults(defineProps<Props>(), {
  buttonText: '点击',
})

// 定义 emits
const emit = defineEmits<{
  (e: 'click'): void
}>()

// 响应式数据
const count = ref(0)

// 方法
function handleClick() {
  count.value++
  emit('click')
}
</script>

<style scoped>
/* 组件样式 */
.button {
  margin: 16px;
}
</style>
```

### TypeScript 规范

```typescript
// 使用接口定义类型
interface Video {
  id: number
  title: string
  duration: number | null
}

// 使用类型别名
type VideoList = Video[]

// 函数类型提示
function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// 泛型使用
async function fetchData<T>(url: string): Promise<T> {
  const response = await apiClient.get(url)
  return response.data
}
```

### 命名规范

- 文件名：PascalCase（组件）或 camelCase（工具）
  - `VideoCard.vue`
  - `videoUtils.ts`
- 组件名：PascalCase（`VideoCard`）
- 函数名：camelCase（`getVideoList`）
- 常量：UPPER_CASE（`API_BASE_URL`）
- CSS 类名：kebab-case（`video-card`）

### 提示文案语言

- **`ElMessage` / `ElMessageBox` 的文案一律中文开头**（#131）。这一条有静态闸门：`tests/views/toast-language.spec.ts` 遍历 `src/` 里每一个第一实参是字面量的提示调用（实测 100 处里的 96 处），断言那句话里含汉字。为什么单开一层静态的：这 17 处从前改回英文**不会有任何一条用例红**——单元层断的是 `stringContaining('服务端那句原因')`（前缀不在断言里），e2e 断的也是那句原因，两层都在核"服务端原话有没有被吞"（#74 那一族），没有一层核"外面套的是哪种语言"。
- 剩下 4 处第一实参是表达式（`ElMessage.error(x ?? '转码失败')`、`ElMessage.success(a ? '…' : '…')`）静态读不到，肉眼核过是中文。**别把兜底常量当文案改**：那种 `?? '转码失败'` 正是 #74/#126 量过的"吞掉服务端原因"的形状，要动的是让原因进来。

## 目录结构

```
frontend/
├── src/
│   ├── api/                # API 调用模块
│   │   ├── client.ts      # Axios 实例（默认带 X-Requested-With，401 统一跳登录）
│   │   ├── auth.ts        # 认证 API（登录/登出/me/status/改密/我的设备 listSessions + revokeSession）
│   │   ├── videos.ts      # 视频 API
│   │   ├── subtitles.ts   # 字幕 API（列表/登记/删除 + WebVTT 地址）
│   │   ├── sources.ts     # 视频源 API
│   │   ├── scan.ts        # 扫描 API（扫一个源 / 扫全部；两条路由共用 `ScanResultResponse`，所以只有一份返回类型，聚合字段按路由各填一半）
│   │   ├── transcode.ts   # 转码 API（格式清单 / 状态轮询 / 启动 / 取消）
│   │   ├── settings.ts    # 系统配置 API（owner 才看得见这一页）
│   │   ├── users.ts       # 账号管理 API（仅 owner 调用）
│   │   ├── preferences.ts # 个人偏好 API（主题按人存）
│   │   ├── watchlists.ts  # 片单 API（队列读写 + 进出队列）
│   │   └── ...
│   ├── components/         # 可复用组件
│   │   ├── VideoCard.vue
│   │   ├── VideoPlayer.vue
│   │   ├── SourceCard.vue
│   │   ├── SourceForm.vue  # 添加/编辑视频源对话框；类型选 `S3 / MinIO` 时路径提示改成 s3:// 写法并说明能力限制
│   │   ├── DuplicateChecker.vue # 重复文件检测（按需调 /videos/duplicates）
│   │   └── ...
│   ├── composables/        # 组合式函数
│   │   ├── useTheme.ts    # 主题切换（本机立即生效 + 同步到账号，登录后按人拉回）
│   │   └── useAuth.ts     # 当前用户（模块级 ref 共享，未引 Pinia）
│   ├── views/              # 页面组件
│   │   ├── Home.vue       # 首页/视频列表
│   │   ├── Login.vue      # 登录页（裸页，不套 MainLayout）
│   │   ├── Sources.vue    # 视频源管理（owner）
│   │   ├── Stats.vue      # 观影统计（数字卡 + 纯 CSS 柱状图 + 标签分布）
│   │   ├── Watchlists.vue # 片单（一份份手排队列，移出/删除只动队列行）
│   │   ├── Tags.vue       # 标签管理（owner）
│   │   ├── Users.vue      # 账号管理（owner）：建号/改角色/停用/重置密码/踢下线
│   │   ├── Profile.vue    # 个人设置：主题按人存 + 改自己的密码 + 登录设备（列出/退出单台），成员也能进
│   │   ├── Settings.vue   # 系统配置（只剩 owner 看得见的三项）
│   │   └── ...
│   ├── layouts/            # 布局组件
│   │   └── MainLayout.vue
│   ├── router/             # 路由配置
│   │   └── index.ts
│   ├── types/              # TypeScript 类型
│   │   ├── video.ts
│   │   ├── auth.ts         # UserRole / AuthUser / AuthStatus / AuthDevice（我的设备的一行）
│   │   ├── subtitle.ts
│   │   ├── scan.ts        # ScanResult（两条扫描路由共用一份，四个聚合字段只有 scan-all 填）
│   │   ├── transcode.ts   # TranscodeFormat / TranscodeStatus / TranscodeResult
│   │   └── source.ts
│   ├── styles/             # 全局样式
│   │   ├── global.css
│   │   └── theme.css      # 影院风主题基座（浅色 + 深色两套令牌）
│   ├── main.ts             # 应用入口
│   └── App.vue             # 根组件
├── public/                 # 静态资源
├── index.html              # HTML 模板
├── vite.config.ts          # Vite 配置
├── tsconfig.json           # TypeScript 配置
└── package.json            # 项目配置
```

## 开发流程

### 1. 创建 API 模块

```typescript
// src/api/examples.ts
import apiClient from './client'

export interface Example {
  id: number
  name: string
}

export interface ExampleCreate {
  name: string
}

export const examplesApi = {
  async list(): Promise<Example[]> {
    const response = await apiClient.get('/examples')
    return response.data
  },

  async create(data: ExampleCreate): Promise<Example> {
    const response = await apiClient.post('/examples', data)
    return response.data
  },

  async get(id: number): Promise<Example> {
    const response = await apiClient.get(`/examples/${id}`)
    return response.data
  },
}
```

### 2. 创建组件

```vue
<!-- src/components/ExampleCard.vue -->
<template>
  <el-card class="example-card">
    <template #header>
      <div class="card-header">
        <span>{{ example.name }}</span>
        <el-button link @click="handleEdit">编辑</el-button>
      </div>
    </template>
    <div class="card-content">
      <!-- 内容 -->
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { Example } from '@/types/example'

interface Props {
  example: Example
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'edit', example: Example): void
}>()

function handleEdit() {
  emit('edit', props.example)
}
</script>

<style scoped>
.example-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
```

### 3. 创建页面

```vue
<!-- src/views/Examples.vue -->
<template>
  <div class="examples-page">
    <div class="page-header">
      <h2>示例管理</h2>
      <el-button type="primary" @click="showAddDialog">
        <el-icon><Plus /></el-icon>
        添加示例
      </el-button>
    </div>

    <div v-if="loading" class="loading">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="examples.length === 0" class="empty">
      <el-empty description="暂无数据" />
    </div>

    <div v-else class="examples-grid">
      <ExampleCard
        v-for="example in examples"
        :key="example.id"
        :example="example"
        @edit="handleEdit"
      />
    </div>

    <ExampleForm
      v-model:visible="formVisible"
      :example="currentExample"
      @submit="handleFormSubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import ExampleCard from '@/components/ExampleCard.vue'
import ExampleForm from '@/components/ExampleForm.vue'
import { examplesApi } from '@/api/examples'
import type { Example } from '@/types/example'

const examples = ref<Example[]>([])
const loading = ref(false)
const formVisible = ref(false)
const currentExample = ref<Example | null>(null)

onMounted(() => {
  fetchExamples()
})

async function fetchExamples() {
  loading.value = true
  try {
    examples.value = await examplesApi.list()
  } catch (error) {
    ElMessage.error('获取数据失败')
  } finally {
    loading.value = false
  }
}

function showAddDialog() {
  currentExample.value = null
  formVisible.value = true
}

function handleEdit(example: Example) {
  currentExample.value = example
  formVisible.value = true
}

async function handleFormSubmit(data: any) {
  try {
    if (currentExample.value) {
      await examplesApi.update(currentExample.value.id, data)
      ElMessage.success('更新成功')
    } else {
      await examplesApi.create(data)
      ElMessage.success('添加成功')
    }
    formVisible.value = false
    fetchExamples()
  } catch (error) {
    ElMessage.error('操作失败')
  }
}
</script>

<style scoped>
.examples-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.examples-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
</style>
```

### 4. 更新路由

```typescript
// src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      {
        path: 'examples',
        name: 'Examples',
        component: () => import('@/views/Examples.vue'),
        meta: { title: '示例管理' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
```

## 组件规范

### Props 定义

```typescript
// 使用接口定义 Props
interface Props {
  title: string
  count?: number
  items: Item[]
}

const props = withDefaults(defineProps<Props>(), {
  count: 0,
})
```

### Emits 定义

```typescript
// 使用类型定义 Emits
const emit = defineEmits<{
  (e: 'update', value: string): void
  (e: 'delete', id: number): void
}>()
```

### 响应式数据

```typescript
import { ref, reactive, computed } from 'vue'

// ref - 基本类型
const count = ref(0)

// reactive - 对象
const form = reactive({
  name: '',
  email: '',
})

// computed - 计算属性
const fullName = computed(() => `${form.name} - ${form.email}`)
```

## 样式规范

### 使用 Scoped 样式

```vue
<style scoped>
/* 组件样式不会影响其他组件 */
.container {
  padding: 16px;
}
</style>
```

### 使用 CSS 变量

组件只消费 `styles/theme.css` 里的令牌，不写死颜色与圆角：

```css
.panel {
  background: var(--glass-bg);            /* 面板底色 */
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-panel);
  color: var(--text-glass);
  box-shadow: var(--glass-shadow);
}

.panel__hint {
  color: var(--text-glass-secondary);
}
```

强调色分两档，不能互换：`--accent` 是写在表面上的文字/图标色，`--accent-fill` 是垫白字的实底色；
同一个紫色做不到既让白字达到 4.5:1、又让它在深底上达到 4.5:1。语义色同理，实底档是
`--success-solid` / `--danger-solid` / `--warning-solid`。

### 深色模式

影院风双主题（浅色纸白分层 / 深色近黑）共用一套令牌，通过 `data-theme="light"|"dark"` 切换：

```typescript
// 使用 useTheme composable
import { useTheme, setTheme } from '@/composables/useTheme'

const { theme } = useTheme()

// 切换主题
setTheme('dark')    // 深色模式
setTheme('light')   // 浅色模式
setTheme('auto')    // 跟随系统
```

`styles/theme.css` 的令牌分三组：

```css
:root {                          /* 两套主题共用：实底强调色、语义实底、圆角 */
  --accent-fill: #6a58f5;
  --success-solid: #1e7a45;
  --radius-panel: 12px;
}

:root {                          /* 浅色 */
  --accent: #5b48e0;
  --surface-bg: #ffffff;
  --tile-bg: #eef0f4;
  --text-glass: #17191f;
  --text-glass-secondary: #5f6673;
}

:root[data-theme="dark"] {       /* 深色：同一批令牌换值 */
  --accent: #a99dff;
  --surface-bg: #14171e;
  --tile-bg: #1e222b;
  --text-glass: #e9ebef;
  --text-glass-secondary: #98a0ad;
}
```

**注意：**
- `--glass-*` 与 `.glass-panel` 是玻璃拟态时代留下的名字，现在只是主题钩子，不要再加 `backdrop-filter`。
- 深色必须整组重申 Element Plus 变量：`html.dark` 的优先级高于 `:root`，只改个别变量会让主色退回它默认的蓝色。
- 深色下 Element Plus 的语义基色（`--el-color-success` 等）是给文字用的，偏亮，垫白字只有 2~3:1，实底按钮要换成 `--*-solid` 档。
- 布局组件（MainLayout）的主题样式需要全局（非 scoped），否则选择器无法生效。
- 改完两套主题都要在跑起来的应用里实测文字对比度（AA 4.5:1），不要只看类型检查。

### 响应式设计

```css
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

@media (max-width: 768px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
```

## API 调用规范

### Axios 实例

`src/api/client.ts` 已经在做两件事，新增模块直接用它就行：

```typescript
// src/api/client.ts
const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
    // 后端对非 GET 的 Cookie 请求强制要这个头（跨站表单发不出来），写在这里最省事
    'X-Requested-With': 'fetch',
  },
})

// 身份与跳转都在 router 里注册，client 只负责通知，避免反向依赖
export function setUnauthorizedHandler(handler: () => void) { ... }

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const url: string = error.config?.url ?? ''
    // /auth/* 自己的 401 是"密码错了"，不是"会话没了"，不能触发跳转
    if (error.response?.status === 401 && !url.startsWith('/auth/') && onUnauthorized) {
      onUnauthorized()
    }
    const message = flattenDetail(error.response?.data?.detail) ?? error.message ?? 'Unknown error'
    return Promise.reject(new Error(message))
  }
)
```

所以调用侧拿到的一直是 `Error(后端 detail)`，`catch` 里直接 `e.message` 就是给人看的那句话。

- `flattenDetail` 是为 422 存在的：pydantic 的校验错误在 `detail` 里是**对象数组**（`type` / `loc` / `msg` / `ctx`），原样当消息用浏览器就渲染成 `[object Object],[object Object]`。摊出来的格式是「字段 原因；字段 原因」，字段名取 `loc` 除第 0 项（`body`/`query`/`path` 这些 scope）之后最后一个字符串，所以 `['body','tags',0]` 报成 `tags`。原因按 `type` 查表翻译成中文，表里没有的类型退回 `msg` 原文——**宁可留一句英文，也不要再出现 `[object Object]`**。后端普遍用 `min_length=1` 表达必填，这类单独说成「不能为空」
- 表单页仍然要自己做**空值前置校验**（见 `views/Login.vue` 的 `submit()`）：客户端拦得住的错不必绕一圈服务端。拦截器的摊平是兜底，管的是拦不住的那些（长度、范围、格式）
- **`catch` 里只能读 `error.message`**：拦截器 reject 的是现场 `new Error(...)`，`error.response` 已经不在上面了——`error.response?.data?.detail` 恒为 undefined，最后露出来的永远是写死的那句兜底文案。`views/Transcode.vue` 的六个 catch 原先全这么写，服务端说「源文件已不在原路径」、页面回「转码失败」。现在统一走一个 `errorReason(error)`（取 `message`，非 Error 的 reject 回 null；`ElMessageBox` 取消时 reject 的正是字符串 `'cancel'`，要先挡掉）
- 轮询里的失败**不要每轮弹一次 toast**：转码状态 1.5 秒问一次，服务端一挂就是刷屏。做法是把原因留在状态卡片上（`.status-fetch-error`，告警色，和转码本身失败的 `.status-error` 红色区分），toast 只在用户主动进页那一次给（`pollTimer` 还没起来时）。同时卡片要清掉这一行 once 恢复响应，否则用户会一直以为还在报错

## 认证与路由守卫

- 状态在 `composables/useAuth.ts`：模块级 `ref`（`user` / `needsSetup` / `loaded`）+ `load()` / `signIn()` / `signOut()` / `forget()`，全站共享一份，**没有引 Pinia**。
- 会话是后端发的 `HttpOnly` Cookie，前端读不到也不需要读；`load()` 打 `/auth/status` 判断登录态，`/auth/me` 取身份。
- `router.beforeEach` 对非 `meta.public` 的路由先 `load()` 再放行，未登录跳 `/login?redirect=<原地址>`。跳回原地址时只认 `/` 开头的站内路径，`//host` 会被浏览器按协议相对地址解析，必须挡掉。
- 登录页要脱离布局：`App.vue` 用 `route.meta.public === true` 决定套不套 `MainLayout`，因此新增公开页时记得打 `meta: { public: true }`，否则会被顶栏包进去。
- 后端重启或被 `revoke-sessions` 踢掉之后，任何一次请求都会回 401，`setUnauthorizedHandler` 里清本地身份并跳登录，页面不会停在"看着有数据、点什么都没反应"的状态。
- 收藏、历史、片单、统计、`is_new` 角标与通知 `read` 回的都是**当前账号**的那份，接口路径与响应结构没变，前端不按账号写分支；换号一定要走退出登录（`signOut()` + 重新 `load()`），否则页面里还是上一个账号已经加载好的列表。
- 角色只看 `useAuth().isOwner`（`user.role === 'owner'`）。管理页在路由表上写 `meta: { roles: ['owner'] }`，守卫里未登录先跳登录、已登录但角色不够则回首页——不是进去再吃一串 403。顶栏的导航项与用户菜单按同一判断显隐。
- 同一个判断要一路带到按钮：成员打得开的页面上也摆着库级操作——首页横幅的「清理丢失记录」、影片详情的「转码 / 编辑 / 删除」和标签行那个加号，它们走的是 `DELETE /api/videos/{id}`、`PUT /api/videos/{id}` 与标签写接口，全在成员禁写名单里，所以这些一律 `v-if="isOwner"`，`/videos/:id/transcode` 整页也标了 `roles: ['owner']`。标准只有一条：**中间件会拒绝的操作，界面上就不该留入口**。
- 这条标准也管顶栏自己：`NotificationCenter` 在 `isAuthenticated` 为真之前不打 `/api/notifications*`（`watch` 而不是 `onMounted`——顶栏会比会话探测先挂上来，首帧那一下没有会话）。不守着就每次进登录页都在控制台留一对 401，而真机走查看的就是控制台。
- 藏入口只是体验，**中间件才是真拦**：后端已经把成员的管理面写请求挡成 403，前端少给一个入口只是少一次"点了没反应"。新加一个管理页时，先确认后端口已经收口，再考虑要不要给成员露出来。
- 主题是账号的属性：`useTheme.setTheme()` 本机立即生效并写 `localStorage`，再尽力 `PUT /api/preferences`；`load()` / `signIn()` 之后 `syncThemeFromAccount()` 拉回那一份。这个拉取是 fire-and-forget——服务端慢或不可达时主题晚一帧到位可以接受，卡在登录页不行，所以**不要**去 `await` 它。
- 「登录设备」是 `/profile` 最后一张卡：`listSessions()` 回的每一行里 `token_hash` 是摘要而不是 Cookie 值，前端只拿它当"退哪一台"的地址。**这里从不出现已过期的那一行**：服务器在列表之前先把它们删掉（`AuthService.purge_expired_sessions`），所以这一张卡的行数和 `/users` 那格的「登录设备」是同一个口径，前端不需要自己按 `expires_at` 再筛一遍。User-Agent 由 `deviceLabel()` 翻成 `Chrome · Windows` 这类文案，认不出来就原样截 40 字符——**那句话是客户端自己写的，只决定这一行显示什么，任何判断都不看它**。当前这台不给「退出」按钮（退它就是退出本页，走顶栏的「退出登录」）；`handleRevoke` 成功时本地删行，失败时弹后端原话并重读，别把列表留在假数据上；改密码会顺手退掉别的浏览器，所以成功后同样 `loadDevices()`。四张卡各自带语义 class（`card-account` / `card-theme` / `card-password` / `card-devices`），单测与 e2e 按它定位——**别用 `.profile-card` 的第几张来选**，加一张卡就会错位。
- 播放器偏好（倍速、音量、字幕字号与延迟）仍留在 `localStorage`，跟浏览器不跟人，与主题不是一回事，见设计文档的偏差说明。

### API 模块

```typescript
// src/api/videos.ts
import apiClient from './client'
import type { Video, VideoListResponse } from '@/types/video'

export const videosApi = {
  async list(params?: Record<string, any>): Promise<VideoListResponse> {
    const response = await apiClient.get('/videos', { params })
    return response.data
  },

  async get(id: number): Promise<Video> {
    const response = await apiClient.get(`/videos/${id}`)
    return response.data
  },
}
```

### 视频源类型

- 类型只有 `local` / `nas` / `minio` 三个值，文案集中在 `src/types/source.ts` 的 `SOURCE_TYPE_LABELS`（`SourceCard` 的角标与 `SourceForm` 的下拉都读它）。`minio` 显示成 `S3 / MinIO`：后端那份实现讲通用 S3 协议，MinIO/RustFS 只是端点不同，不用为它单开类型。加一种类型要连后端 `src/storage/__init__.py` 的分发表一起改
- 表单只在 `type === 'minio'` 时把占位符换成 `s3://…` 写法并显示 `.path-hint` 那段能力说明。路径与类型是否匹配由后端判（不匹配回 400），前端只负责提前说清楚，别在这里再写一份判定
- 这类影片请求转码或字幕时后端返回中文 400，`client.ts` 的拦截器会把那句话原样弹成提示，因此不需要为对象存储单独加前端分支

## 测试规范

### 单元测试（Vitest）

测试代码统一放在 `frontend/tests/`，文件名 `*.spec.ts`，**不要放进 `src/`**（`src/**` 由 `tsconfig.app.json` 纳入生产构建的类型检查）。

```
tests/
├── setup.ts            # 全局注册 Element Plus 与图标、ResizeObserver / matchMedia 兜底、用例间状态清理
├── factories.ts        # makeVideo / makeSource / makeTag 等数据工厂
├── helpers.ts          # buttonByText / CONFIRMED 等断言辅助
├── api/                # axios 实例与请求路径
├── components/         # 组件级用例
├── composables/        # 组合式函数
├── views/              # 页面级用例
└── router.spec.ts      # 路由表与 404 兜底
```

约定：

- 页面/组件依赖 `useRouter`、`useRoute` 时按文件 `vi.mock('vue-router', ...)`，不要安装真实路由。
- 测路由守卫要 `vi.mock('@/api/auth')` 控制登录态，并在每个用例前 `useAuth().forget()`——`useAuth` 的状态是模块级 ref，不清就会跨用例串味。
- **视图里不写请求**：一份 `src/api/*.ts` 都没有的 URL 在三层 api 钉子（`paths.spec.ts` 形状 / `openapi-contract.spec.ts` 路由表 / `stub-coverage.spec.ts` 替身夹具）眼里是不存在的，`tests/api/inline-requests.spec.ts` 因此扫一遍 `src/`，凡是 `src/api/` 之外默认导入 axios 实例（`import api from '@/api/client'`）的文件都算违规；`src/api/` 之外出现 `/api/` 字面量同样违规（先刮掉注释再比，免得把文档句当成请求），这一条是 #124 补的：`<img>` / `<video>` / `<track>` 的 `src` 一次 axios 都不走，`VideoDetail.vue` 里那条流地址改坏之后 31 份测试全绿过。#123 之前 `Sources.vue` 与 `Transcode.vue` 就是这么各写各的，7 条 URL 全在钉子外面——实测把其中任何一条改成不存在的路径（`/scan/everything`、`/transcode/format`），`tests/api/` 那 33 条照样全绿。视图用例仍然 `vi.mock('@/api/client')` 记录 `url`：请求模块只是把 `client` 转手一层，替身换掉 `client` 就同时喂了数据并记了账，所以搬运之后 `tests/views/Sources.spec.ts` / `Transcode.spec.ts` 一条断言都不用改（`env.get` 记录的还是 `/transcode/7/status` 这种完整相对路径）。`tests/api/paths.spec.ts` 做三条形状校验：不带 `/api`、以 `/` 开头、既没有 `//` 也没有尾斜杠，并且**按模块归账**——某一份一次 `client` 都没打到就算红（实测 14 份共 72 次 `client` 调用，另有 4 条只返回字符串的构造器由 `openapi-contract.spec.ts` 按 GET 补记，合计 76 次；整份停掉只会少掉那一份的那几次，只数总数看不出来）。三份 api 守卫（`paths.spec.ts` / `openapi-contract.spec.ts` / `stub-coverage.spec.ts`）**共用同一份遍历器** `tests/api/emitted-calls.ts`（`import.meta.glob('../../src/api/*.ts')` 自己数出模块清单，新增一份 `src/api/*.ts` 不需要登记），它一次遍历同时记下三样：`client.getUri(config)` 拼出的完整地址、`config.url` 那段没拼前缀的原文（给形状规则）、以及那几个只返回字符串的构造器；清单本身只设 `>= 12` 的下限，用来防"glob 什么都没匹配到 → 整份用例空跑还全绿"。**为什么不各抄一份遍历器**：抄了就只能保证"我抄的这份"和别的一致，而真实的失效方式是某一份加了地址、另一份静默少几条——"少了几条"在测试里从来不报错，只是绿（#121/#122 的教训）。#121 之前这里是手写数组，它的失效方式是**漏一份不会红**（auth / preferences / users / watchlists 四份连"别把 `baseURL` 已经带的 `/api` 再写一遍"都没翻出来过），所以干脆不让这种清单存在。
- 只测 api 模块本身时改用 `client.defaults.adapter` 拦截。注意 **adapter 里 `config.url` 还是原始相对路径**（实测 `/videos/new`，`baseURL` 是另一个字段，拼接发生在 axios 自己的 adapter 里），要拿到真实请求地址得调公开方法 `client.getUri(config)`；别信"adapter 能顺带看到完整地址"这种说法。请求体到这里已被 axios 序列化过，要 `JSON.parse(String(config.data))` 再断言字段名。`getUri` 对 `params` 是非对象会抛 `TypeError: target must be an object`，遍历时要丢掉。
- `tests/api/openapi-contract.spec.ts` 是**第四层钉子**：它读 `backend/openapi.json`（真路由表，见 `backend/CLAUDE.md`「OpenAPI 快照」），把 `client.getUri` 拼出的完整地址逐条核对到 schema 的 `path + method` 上，还校验路径参数**类型对得上**（`{video_id}` 声明 `integer`，就得是纯数字）和 query 键名**在 schema 里声明过**。这两条不是锦上添花，是实测出来的：少了类型规则，把 `/videos/duplicates` 写成 `/videos/duplicate` 会撞上 `/api/videos/{video_id}` 而"看起来合法"；少了 query 规则，`page_size` 写成 `size` 会被过滤 `%5B` 的那步一起放过。跑这条用例不需要后端进程，但**需要 `backend/openapi.json` 是最新的**——改完后端接口要重跑导出，否则这里红的是快照而不是你。遍历器另外会把 `src/api/` 里那几个**只返回字符串**的构造器（`thumbnailUrl` / `streamUrl` / `subtitleTrackUrl` / `embeddedSubtitleTrackUrl`）按 GET 记一条一起对表——它们在浏览器里确实是被 GET 取的。但**路由表管不了实参落在哪一段**：`/api/videos/{video_id}/subtitles/{subtitle_id}/stream` 两个参数都声明成 integer，写反照样命中同一个模板；把流地址换成封面地址也仍是一条已声明的路由（实测：对表全绿，只有哨兵断言抓得到）。所以 `tests/api/builder-urls.spec.ts` 用互不相等的哨兵值（11 / 22）把这四条钉成具体地址。
- `tests/api/stub-coverage.spec.ts` 是**第三层**：前两层问的是"后端有没有这条路由""形状对不对"，这一层问"那 100 条桩用例的替身**接不接得住**这条地址"。它 `import { mockApi } from '../../e2e/fixtures'`（不复制匹配器——复制就只能保证"我抄的这份"和夹具一致，而真实的失效方式是夹具改了、守卫没跟着改），用一份假 `page` 接住它注册的那个 `page.route` 处理函数，再用假 `route` 逐条驱动遍历器交出的 76 条地址，断言三条：每条都有人答（一次 `fulfill` 都没调的分支在真浏览器里是永久挂起）、没有一条落到 `未预置的接口: METHOD /path` 那句兜底上、非 `/auth/*` 的一条都不该被替身的默认拒绝拦成 401/403。**每条地址各自重装一份夹具**，这不是洁癖：夹具是有状态的（`signedIn`、`removedVideos`、`readNotifications`、转码状态机），而 `POST /auth/logout` 会把 `signedIn` 翻回 false、遍历又按模块名排序（`auth` 排第一）——共用一份时实测后面六十条全被拦成 401，兜底那句一次也执行不到，"没有缺分支"那条规则演成一份看着全绿的空守卫。`postData()` 一律回 `{}`：这一层问的是地址，不是请求体，而夹具里所有按 body 行事的分支都带默认值或 `typeof` 闸门，空对象走得通。**它上线当天量出 17 条缺分支**（标签的增删改与挂卸、源的建改、`/mediaStreams`、内嵌字幕流、单键设置的读写），其中一半是界面上真有的写路径——也就是说这些流程此前在桩用例里根本跑不起来。补进夹具的这几条是有状态的（`tagRows` / `sourceRows` / `subtitleRows` / `systemSettings` 四张每次安装重建的小表（#132 又添了第五张 `videoTagLinks`，存的是影片↔标签的关系）），"建完刷新还在"从此不需要现编假数据。**这一层管地址不管语义**：替身答得出的那一串仍是前端自己写的假设，语义只有 `e2e/real/` 那 26 条签。**有一处逻辑是故意不补进替身的，别顺手加上**：标签名首尾空格的裁剪（#130）只写在两处——`TagService._clean_name` 是唯一的闸，`Tags.vue` 的 `handleSubmit` 在发请求前先 `trim()`。正因为界面先裁，夹具那两条 `POST/PUT /api/tags` 结构上永远收不到带空格的名字，给它加一段 `trim()` 是一行任何变异都拆不红的死写（量出这一类死写的同一把尺子见 #132 那次多余的 `set`）；后端那一半由 `backend/tests/test_api/test_tags.py` 那 6 条签，界面对那一半由 `tests/views/Tags.spec.ts` 与 `e2e/tags.spec.ts` 共 5 条签。
- **#129 给 `views/Tags.vue` 一次补了两层**（`tests/views/Tags.spec.ts` 10 条 + `e2e/tags.spec.ts` 8 条），这两层的分法只有一条：**这一问是不是只有这一层答得出**。把视图里那句 `{{ tag.video_count ?? 0 }}` 的兜底摘掉，**只有单测红**——替身夹具的 `tagBody()` 永远带上 `video_count`，「后端没带这个字段时长什么样」在浏览器那一路结构上量不到；反过来把夹具里建标签那条重名判断关掉，**只有 e2e 红**——单测 `vi.mock('@/api/tags')`，替身根本不在场。落法因此是：形状类断言（PUT body 只含改动那个字段、无改动一次 PUT 都不发、写失败时不许回读把人刚填的名字抹掉）放单测，「点得动、卡片真的少一张」放 e2e。**往一个视图补用例时先问哪一层量不到，别把同一串断言抄两遍。**
- **#133 给 `views/Settings.vue` 又补了两层**（`tests/views/Settings.spec.ts` 7 条 + `e2e/settings.spec.ts` 5 条），它是 14 个视图里最后一个两层都没有用例的那一个。这一次两层的边界是**量出来的**，不是排出来的：把保存失败那句换成兜底常量（#74 那一族）→ **只有单测红**，因为替身那份整份 PUT 永远不会失败；把 `:min="100"` 换成 `:min="0"`、把替身的整份 PUT 改成只回显不落库 → **只有 e2e 红**，前者要真打字才走到钳位，后者要真刷新才看得出没落库。七个变异里三个只红单层——**一条断言该写在哪一层，就看它能不能在那一层被改坏**。
- **`PUT /api/settings` 那五项请求字段全带默认值**，所以差量式保存不是「漏的那项不动」，而是**被写回代码默认值**（后端 `test_a_bulk_put_that_omits_a_key_resets_it` 早就钉了服务端那一半）。界面这一半是「每次都发全五项」，`tests/views/Settings.spec.ts` 用「一个控件也没动」那次保存钉住它，`e2e/settings.spec.ts` 从真 PUT 的 body 上钉同一个形状。另外 `Settings.vue` 上那两道 `:min` / `:max`是这三个数字键**全系统唯一的范围闸门**（后端只认「是不是整数」，#112 的口径），别顺手删。
- **顺带修掉替身一处不忠实**：`PUT /api/settings` 原先只回显、不落库，于是「保存后刷新还在」这类用例在桩面上必然红，而红的是替身不是界面（后端的 `update_settings` 是写完五个键才 `return data`）。现在它照后端`Object.assign(systemSettings, body)`。两条**单键** PUT 仍只回显：它们没有界面调用者（#128 静态遍历量的），要接住得连后端那道整数闸门一起补，那是另一单的活。这一层的语义仍由真后端 e2e 第 11 条签。
- **#132 把替身夹具的影片↔标签关系改成有状态的**，为的是 `VideoDetail.vue` 那条「编辑标签」的写流程（`tests/views/VideoDetail.spec.ts` 4 条 + `e2e/video-tags.spec.ts` 3 条）。在此之前 `POST/DELETE /api/tags/video/...` 只回一句 204、谁也没落库，于是「保存后重新读这部影片」在桩面上永远拿回安装前那几枚标签——和 #133 那句「只回显不落库」是同一类不忠实，红的是替身不是界面。现在关系存在每次安装重建的 `videoTagLinks`（`Map<videoId, tagId[]>`，后端 `video_tags` 那张关联表的替身）里，读路径一律按 id 现取，`videos[].tags` 那份模块级种子从此只是「初始关系的声明」；按 id 现取顺带白送两件事：标签改名跟着 `tagRows` 走、删掉的标签自动从影片卡片上消失（和真库那次 join 同一个理由）。**两层的边界同样是量出来的**：「挂上/摘掉到底存没存下来」只有 e2e 红（把夹具的 POST 改回不落库，单测全绿——它 `vi.mock('@/api/tags')`，替身不在场）；「只发差集、不许把勾选的全发」只有单测红（把视图那两句 `filter(id => !current…)` 换成全集，e2e 全绿——替身对「多挂一次」照常回 204，和后端一致）；预勾选写成「全库勾上」则两层一起红。**反过来记一件**：夹具那两条防御分支（已挂的不挂第二遍、认不出的标签 id 静默跳过）在两个变异下**两层全绿**——界面上根本发不出这两种请求（复选框清单来自 `listTags`，选不到不存在的 id），签过字的是后端 `tag_service.py` 那两个 `if` 的服务层用例，别以为桩用例护得住。
- **#146 给 `VideoPlayer.vue` 补上「这条字幕没能加载」那句人话，两层的分工是量出来的**：失败只以 `<track>` **元素**上那个 `error` 事件到场（`TextTrack` 上那个事件 Chromium 从来不发），所以监听器绑在元素上、且必须绑在 `bindTrackEvents` 里 `if (!track) return` **之前**——`video.textTracks` 那一层还没有时元素已经在了，jsdom 里 `mountPlayer()` 给的恰恰是空 `textTracks`。菜单条目上那个「（加载失败）」和 toast 的分工不是审美：toast 三秒自己走，而 `readyState` 已经是 3 的那条轨浏览器**再也不拉第二次**，少了 durable 的那一半，事后就没法问出是哪一条。反面也钉住：没被点过的轨在 Chromium 是 `disabled`、一个请求都不发（见上一节第 22 条），"主动汇报一条没被选中的字幕坏了"在这一路是结构上做不到，不是漏做。七次变异六次红：摘掉监听 / 只 toast 不记 / 只记不 toast / 一条失败标死全部 / toast 报内部 key → 全红在真后端 e2e 第 22 条，换文件时不清空标记 → 红在单测；**去掉 `{ once: true }` 两层全绿**——挡住重复 toast 的是 `markTrackFailed` 开头那句按 key 去重，`once` 只是第二道闸，记在这儿免得下一个人把它当成已签的护栏。
- 弹层分两种查法：popover / dropdown 会 teleport 到 `document.body`（用 `popper-class` 查），**`el-dialog` 默认 `append-to-body: false`，是就地渲染的**，得在 `wrapper` 里查 `.el-dialog`；挂载时仍传 `attachTo: document.body`，否则弹层里的焦点与事件走不通。
- **模板里新用一个 `el-*` 组件，必须同时加进 `src/main.ts` 的按需注册清单**。漏注册不会报错，只会把标签当未知元素渲染（单测照样全绿，因为 `tests/setup.ts` 装的是完整 `ElementPlus` 插件），实际界面里就只剩一串纯文字——`<el-radio>` 曾经就是这样在浏览器里消失的。所以组件注册这类问题只能靠 e2e 或真机发现。
- 主题选「跟随系统」时要读 `window.matchMedia`，jsdom 没有这个 API，`tests/setup.ts` 里给了一份假实现；用例里别再各自 `stub`。
- 弹层一定要给 `popper-class`（如 `notification-popper` / `user-popper`）：页面上同时有两个弹层时，`.el-popover` 这种选择器在 Playwright 严格模式下会因命中两处直接报错。
- 定时器轮询用 `vi.useFakeTimers()` + `vi.advanceTimersByTimeAsync()`，用例结束前 `vi.useRealTimers()`。
- **带分页、又能就地删行的视图，重读之前要把越界的那一页钳回去**：`Home.vue` / `Favorites.vue` / `History.vue` 三处同一句 `Math.max(1, Math.ceil(total / pageSize))`（分页条的渲染条件是 `total > pageSize`，所以越界那一页会连着"空的一页"和"整条分页消失"一起出现，只剩刷新一条出路）。别顺手改成"删完回第 1 页"：用户的阅读位置不是 bug，而"最后一页只剩一条"那种情形下两种写法给出同一个界面，只有第 3 页还剩 4 条能分开它们——`tests/views/Favorites.spec.ts` 与 `tests/views/History.spec.ts` 各钉一边，把钳位换成"一律回第 1 页"会两处一起红。这类夹具至少要 21 条才碰得到第 2 页（`page-sizes` 里能选到的最小值是 10，而默认每页 20）；换页只能点分页条上那个数字，视图没有别的公开入口，所以那个点击本身也是被测的一环。

### 端到端测试（Playwright）

`frontend/e2e/`，由 `playwright.config.ts` 自动拉起 `localhost:4173` 的 dev server。`e2e/fixtures.ts` 里的 `mockApi(page, { signedIn, needsSetup, role, themes })` 用带状态的假接口替换整个 `/api` 面，因此 **E2E 不需要启动后端**；注意路由要按 `url.pathname.startsWith('/api/')` 匹配，用 `**/api/**` 通配会把 Vite 的 `/src/api/*.ts` 模块请求一起拦掉导致白屏。这份替身覆盖面由 `tests/api/stub-coverage.spec.ts` 钉着（见上一节末条）：新增一份 `src/api/*.ts` 或新加一条地址，夹具里没有对应分支时红的是这条守卫，而不是某天界面拿到一句假 500。

默认 `signedIn: true`：所有非 `/auth/*` 请求正常回数据。传 `signedIn: false` 时替身一律回 `401 {detail:'未认证'}`，登录流程、守卫跳转、401 拦截这些用例就是这么打的。

角色面在这份替身里是照抄中间件的：`role: 'member'` 之后，`/users`、`/settings` 连读都 403；写接口反过来按 `MEMBER_WRITE` 这条正则放行，它是 `backend/src/middleware/auth.py` 里 `MEMBER_WRITE_PATHS` 的一比一抄写，名单之外的写请求一律 403。账号表（owner / member / 一个停用号）与 `themes`（按账号存的主题）是跨请求的可变状态，所以"退出后换账号登录、主题跟着人走"这种用例能真跑。后端放行或新收一条写接口时，**`MEMBER_WRITE`、后端名单和 `e2e/roles.spec.ts` 的期望要一起改**，否则浏览器测的是替身，不是后端。

### 打真后端的端到端测试（`e2e/real/`）

上面那句"浏览器测的是替身"就是这套用例存在的理由：替身把响应该长什么样写在前端测试里，前后端各自对着自己那份理解测试，中间没有签字的人。`npm run test:e2e:real` 跑 26 条，一条 `page.route` 都没有，请求走完 Vite 代理 → uvicorn → PostgreSQL：真表单登录换来真 cookie、首页渲染的是真扫描写出来的那一行、字幕轨是 sidecar 真转成 WebVTT 的、`Range` 分段回的是 `206 + Content-Range`、点下去的收藏在刷新后还在库里（那一条还顺手把收藏列表**越界那一页**的形状钉死：`page=2` 也是 200、`items` 是空的、`total` 说真话、`page` 原样回显——替身夹具那份 `/api/favorites` 处理器根本不读 `page`，而 `Favorites.vue` 那句钳位全靠 `total` 是诚实的才能算出最后一页）、继续观看那条轨的"剩 0:12"和进度条宽度算自真历史行、片单页连条目的"已看"秒数和片单说明一起从库里读回来，第 6 条把 `MEMBER_WRITE` 那份手抄本交回真中间件核对（成员读管理面 403、名单外的写 403、名单内的写真的落库，换回 owner 看到的仍是自己那两份数据），第 7 条签的是管理面两页的**算法**——`/api/history/stats` 真按 `days` 返回零填充的整窗（替身可以不理这个参数，前端自己也数不出"30 格"这件事），`/api/users` 那格的 `signed_in_devices` 是中间件每次登录真写下的会话行数。第 8 条签标签：两个标签各数各的 `video_count`（挂上片子的那个才涨，没挂过的留在 0，所以那个数不可能是"全局有几部片子"），而 `GET /api/tags/{id}/videos` 必须带着每部片子自己的 `tags` 集合回来——这正是 #101 那个 500 的回归位置，它只在真库的关系加载上出现：序列化是同步的，那一查没预取第二层就是 greenlet 之外的一次 IO，替身夹具永远测不到。第 9 条签通知流：那一行是播种那趟真扫描留下的，句末"发现 1 个新视频、1 条字幕"和 `data` 里那三个计数都是扫描器的计数器（替身给的是手抄文案，给不出一份 JSON 列在真库上的往返），同批文件再扫一遍时计数全 0、通知数也**必须还是 1**（#85 的回归位置：库没变就不发），而 owner 点掉已读并刷新之后成员看到的仍是未读——feed 是广播的、`read` 是按人的，这两半只有在真库的 `notification_reads` 复合主键上才分得开。第 10 条签"同一个目录挂两个源"：`videos.filepath` 是全库唯一的，所以这件事只有真库能回答——第二条扫描必须报 `files_found=1 / new_videos=0`（文件确实被看到了，不是扫了个空目录），库里仍然只有一部片子、归属还在源 1，而时间戳只盖在被扫的那一个源上；把第二个源删掉之后那部片子和它的封面都必须原样还在（`source_service.delete` 的谓词是 `Video.source_id == source_id`，写反了就会删掉别人的片子）。第 11 条签系统配置那一页，关键是 **`PUT /api/settings` 回的是请求体本身**——"保存成功"和"库里到底有没有那一行"在替身夹具里是同一件事，所以改完必须换一路读才算数；起始那五项是播种从不写 `settings` 表时**代码默认值经一次 Text→int/bool 强制转换**读回来的样子，而 `GET /api/settings/{key}` 给的是那一列的原文（`"7200"`），界面上那个 7200 是 `int()` 之后的数。这一条同时钉住本单的修复：单键 PUT 原先只认键名不认值，写一个读不回来的字符串进去，`GET /api/settings` 从此 500，直到有人手工去改那一行。第 12 条签搜索与筛选的分面，这里有两个替身永远答不出来的问题：一是 `frontend/e2e/fixtures.ts` 里的 `matchesSearch` 是拿 TypeScript 把 `backend/src/utils/video_search.py` **又实现了一遍**，两份实现各自测自己那一侧，谁改了对方都不知道；二是替身的 `/videos` 处理器**根本不读 `page` / `page_size`**，永远回 `page: 1, page_size: 20`，所以那 100 条桩用例里的翻页全是虚构的。这一条把浏览器打出去的一串字符（URL 编码 → FastAPI 参数解析 → 一次真 ILIKE）的结果核到三处一致：卡片数、服务器对**同一个字符串**报的 total、地址栏里那个词；顺带钉住只有真库才给得出的三件事——ILIKE 不区分大小写（替身是 `toLowerCase` + `includes`）、`标签:` / `源:` 这两个算子真被解析器认下、观看状态读的是**这个账号**的播放历史（换成员登录，同一个 `未看完` 对他必须是 0 条，而 `没看过` 是 1 条；同库同一片子两个人报的数不一样，只有真中间件加真库给得出）。它顺手量出一个真缺陷并修在 `views/Home.vue`：`?page=` 是首页自己写进地址栏的，分享一条链接或浏览器后退能带回来一个已经不存在的页——那一页确实是空的而库里不空，界面于是同屏说「共 1 个视频」和「添加视频源并扫描即可开始使用」；现在越界的一页会钳回最后一页再读一次，地址栏跟着改（`watch([selectedSourceId, selectedTagId, currentPage, pageSize], pushQuery)` 本来就管这个）。**这条能单独 `-g 搜索框` 跑**：它自己建那两个标签，不借第 8 条留下的。第 13 条签"文件从磁盘上消失再挂回来"这一整条往返，它要的真库证据是三样：`videos.is_missing` 那一列（替身夹具只照抄 `fixtures.ts` 里那份 `is_missing: false`，翻不翻都由它自己说了算）、`GET /api/videos?search=丢失` 背后那条真谓词，以及通知里那两句话的**方向**。做法是把 `data/e2e/media/e2e_sample.mp4` 搬去同级的 `hidden/`，扫一遍，再搬回来扫一遍——搬出源目录是硬要求：本地扫描是递归的，任何仍留在里面、名字以 `.mp4` 结尾的东西都会被登记成一部新片子，那一验的就不是"把标记翻回去"而是"多出一行"。核对的是那一次扫描报 `files_found=0` 而库里那一行**还在**（`total` 仍是 1、`id` 仍是 1，只有 `is_missing` 翻成 true）、首页那条横幅和卡片角上的「丢失」标读的是同一个 `丢失` 探针、「查看」把算子填进搜索框；搬回来之后同一行影片 `id`、同一批封面文件（按 `thumbnails/` 下每个 `.jpg` 的相对路径 + 内容 sha1 逐项比）、同一条观看历史行的 `id` 都不许变——三样合起来才挡得住"删了重扫"这种写法：封面路径是按 `<root>/<source_id>/<片名>-<locator 摘要>.jpg` 拼的，行重建就会换一个目录名，而光看影片行会漏掉 `play_history` 那张表。第 14 条签个人设置页那两条写路径，也是除 NotFound 外唯一从没在真库上签过字的视图：`e2e/fixtures.ts` **根本没有 `/api/auth/sessions` 处理器**（当时那批桩用例因此从没真的请求过设备列表；#128 已经把这条分支补进夹具，桩用例现在接得住它，而设备列表那页的界面语义由 #120 那条真后端用例签），服务层那边只有 CLI 那条**不带** `keep_token_hash` 的路有测试——也就是说界面上那句「其他浏览器会被退出，这台仍然保持登录」此前没有任何一层签过字。核对的全是要有**两个以上各自握着 cookie 的 context** 才证得出的事：同一张会话表在两台浏览器里行集合与顺序完全一致、而 `current` 各指各的那一行（把 `current` 存成一列、或拿创建时间当"当前"都会红）；从界面上点掉「退出」、再按「刷新」逼服务端重答一次，清单**只少被点的那一枚摘要**，被退那台从此 401 而这台仍 200（`handleRevoke` 只在本地筛一遍就收工，不刷新等于没验）；成员拿 owner 的摘要去删得到 404「设备不存在或已退出」而 owner 那一行原样还在（`revoke_session` 的谓词是 `(user_id, token_hash)`）；形状不对的摘要（`…/sessions/zZZ`）在路由那个 `Path(pattern=...)` 上就 422，跟 404 分得很清；主题点「深色」之后换一路读回 `dark`（PUT 的响应回显的就是刚写进去的那份，拿它当证据等于自证），member 全程留在 `light`，而一台**全新浏览器**（没有 localStorage 可依赖）登录同一账号仍是深色——存的是账号而不是这台机器；`{theme:"neon"}` 出不了 `Literal`，422 之后库里仍是 `dark`；改完口令这一台还活着、改密码前签进来的那两台 401、member 那台不受影响（批量撤销只动这个账号）。第 15 条签转码那条长流程，它是这一套里唯一"应用真起了一个 FFmpeg 子进程、真往磁盘写了一个文件"的用例：`backend/tests/test_services/test_transcode_service.py` 那 11 条服务用例里，凡是跑到编码那一步的（5 条）都把 `transcode_video` 整个换掉，剩下 6 条只测拒绝，而 100 条桩用例的 `POST /api/transcode/{id}` 处理器**不做任何校验、永远不会失败**，`output_path` 写死成 `/tmp/out.<格式>`——两层假各测自己那份理解，中间没人签过字。核对的因此全是只有真进程给得出的东西：格式清单那四项各带编码器和**带点的**扩展名（替身那份是没点的 `'mkv'`）、界面不刷新也能轮询到自己的终态、服务器报回来的**绝对输出路径**落在 `data/e2e/media/` 里且文件头那几个字节自报所请求的那种容器（读 EBML 的 DocType / RIFF 的 FormType，不看文件名）、产物里那两条流正是配方里那一对编码器（webm 是 vp9 + opus、avi 与 mkv 是 h264 + aac；问 `ffprobe` 而不是问接口——`acodec` 从不进任何响应，而这一句能成立的前提是播种那部片子**带一条音轨**：无声的源让 ffmpeg 把 `-c:a` 整个跳过，于是把 webm 的 acodec 写成容器拒收的 `aac` 也能一路绿（#115 的变异⑧就是这么绿的，#117 补上音轨后它红了）、mkv 那一行也有真产物（#125 补上第三次转码：把它的 `codec` 改成 `libvpx-vp9`、`acodec` 改成 `libopus` 各红一次）、mp4 那一行现在也有（#144 第 25 条把**源**换成一个现场 `-c copy` 出来的.mkv——同格式那道闸门比的是 `with_suffix` 拼出来的路径和源文件是不是同一个，不比扩展名，所以换个容器的源就能把目标指向 mp4，ffmpeg 这才第一次为表里 mp4 那一行起过进程：把它的 `acodec` 改成 `libmp3lame` 只红第 25 条那一条用例，改成 `libvpx-vp9` 连产物的流清单都不对）。四行配方四行都有真产物签过字了，而那四种格式界面现在也真能编出四种（从前只有三种，缺的就是 mp4——播种那部的后缀替它挡着闸门）。承载这两句的 `CONTAINER` / `STREAMS` 两张表和读产物的那几句断言从 #144 起住在 `e2e/real/transcode_support.ts`，`transcode.real.spec.ts`（第 15~17 条）和 `video-transcode-mp4.real.spec.ts`（第 25 条）共用同一份——把表抄进第二个文件就变成两张表各自红、后台任务用 `async_session_maker()`（不是请求那个 session）写进真库的那条 `transcode_complete` 带着自己的 `video_id` 与 `format`，以及三种拒绝各有原话（同格式那句 `overwrite the original file`、`Unsupported format: exe`、对已经结束的任务 cancel 得到 404 `No active transcoding`）。它还钉住本单的修复：`target_format` 必须在**进闸门之前**归一大小写——闸门 `check_format_support` 本来就不区分，只有归一在闸门里做，被放行的 `'AVI'` 才会先回一个 HTTP 200「已启动」、再在后台失败成「不支持的格式：AVI」。这条**能单独 `-g 三种拒绝` 跑。第 16 条签的是转码**失败**那一路，它的覆盖原先只有半层：`backend/tests/test_services/test_transcode_service.py` 那条 `test_failed_job_keeps_the_error_message` 把 `transcode_video` 换成一个返回 `(False, "boom")` 的假函数，于是"错误字段跟着作业走"这一句是证的，而 `transcode_video` 里那个 20 行的 stderr 尾巴到底从真子进程捞回了什么、闸门放行之后一个失败的任务在界面上长成什么样、后台任务发出去的到底是 `transcode_complete` 还是 `transcode_error`——三处都没有一个字签过字，而 100 条桩用例那份 POST 处理器永远不会失败。现场是"后缀合法、内容不是任何一种容器"的一个文件：扫描只认后缀（`extract_video_info` 探针失败回的是默认值），所以库里确实建得起一行，而那一行的 `duration` 和 `thumbnail_path` 都是 null——`progress` 钉在 0 靠的是前者（`_run` 拿到 `duration=None`，`on_progress` 一次都不会被调用），不是"编码器最后报到第几秒"那个细节。断言落在三层各一处：接口那句原因里有 ffmpeg 自己的两个措辞（`moov atom not found` / `Invalid data found when processing input`，方括号里那个地址每次运行都随机，所以不钉它）；页面 `.status-error` 那一段和接口字段**逐字相等**（#74 那一族的回归位置，`?? '转码失败'` 那种兜底常量会把原因吃掉，把 `{{ transcodeStatus.error }}` 换成常量就是这么红的）；真库那条通知是 `transcode_error`、标题「转码失败」、`data` 带着这一行的 id 和 `webm`。它还量了一件一直没核实的事：`transcode_video` 只在 cancel 分支 `unlink` 输出、失败分支不删——这一趟磁盘上之所以干净，是因为 ffmpeg **连输入都没打开**，什么都没写出来；这不等于"失败不留产物"的通用保证，用例里那句注释也只说这一种失败模式。两个细节记一下：通知的基线取在扫描**之后**（那一趟扫描自己也发一条，库真变了才发——第 9 条钉的就是它），而那个垃圾文件和可能的产物都由这一条自己在 finally 里收走，因为排在它后面的删除影片那条按 `files_found=2 / new_videos=1` 数媒体目录。**这条能单独 `-g 转码失败` 跑。** 第 17 条签的是转码**取消**那一路，被杀掉的是一个真子进程。`backend/src/utils/ffmpeg.py` 里那段 `except asyncio.CancelledError`（kill → wait → 删输出 → 再抛）在全仓库一处也没有被执行过：服务层那条 `test_cancel_stops_the_job_and_records_it` 把 `transcode_video` 整个换成一个挂在 `asyncio.Event().wait()` 上的假函数，于是它证的是"作业状态机记得住 cancelled"，而真进程有没有被杀、半截文件归谁管，两句都不在它的路径上；100 条桩用例那份 cancel 处理器更是只把一个字符串改成 `'cancelled'`，顺带回 200 `{ok:true}`，而真路由回的是 204 空体——这一处不忠实是**记下来的**，本单没有东西被它挡住，所以不去顺手修。现场是一部现编的 15 秒 720p 真片子（`writeSlowClip`）：vp9 编它要好几分钟，而末尾把它重编成 mkv（libx264）只要几秒——同一份字节两种速度，"追得上一个活任务"和"取消之后这活儿真还能起来"这两步就都不用等第二次分钟级（播种那部 5 KB 黑屏编成 webm 只要 0.06 秒，点不到「取消」就已经跑完，得到的会是第 15 条已经签过的那个 404）。核对的四件事各有各的变异：`cancelTranscode` 回 204 的那一刻半截 `.webm` 已经从磁盘上没了——`cancel()` 是 `task.cancel()` 之后 `await` 那个任务，而 kill / wait / unlink 全在 re-raise 之前，所以这一句不需要轮询；把 `proc.kill()` 删掉，那个 POST 压根不返回（服务层在等一个没人杀的编码器），界面上那句「转码已取消」永远弹不出来（实测红在 toast 那一句，204 是等到子进程真没了才发的）；把 `Path(output_path).unlink(...)` 删掉，红在"文件没了"那一句（实测红在 `existsSync(partial)`）；`_run` 在 CancelledError 里 re-raise **走在 `_notify` 之前**，所以取消一条通知也不写——把那句 `raise` 删掉就红在通知数上（实测 3 比 2），而末尾那次真跑完的 mkv 写了一条 `transcode_complete`，两句合起来才说明那份安静是取消特有的，不是这一路压根不写通知表。它还量出 `cancel()` 末尾那句兜底（`if job.status == "running"`）是**死分支**：删掉它，本条和服务层那 11 条全绿（`_run` 在 re-raise 之前已经写过 `cancelled`），所以这里只记不删。另外"被取消的任务 `progress` 永远小于 100、`error` 是 null 而不是那句人话"也在断言里，`output_path` 那句绝对路径和 `sha1(输入文件)` 不变一头一尾钉着输入输出各自不许动。**这条能单独 `-g 转码取消` 跑**（本机绿的那一遍 7.1 秒），它慢在两次真编码，`test.setTimeout(180_000)` 放宽的是墙不是断言。 第 18 条签的是用户管理页那五条写路径（建号、改角色、停用启用、重置密码、踢下线）打真库真中间件。后端接口层（`backend/tests/test_api/test_users.py`）已经把语义签得很死——建完能登录、重名 400、弱密码 400、停用切断会话、重置后旧口令失效、踢下线报数——所以这条不复述那份表，它签的是三段只有浏览器接缝才有的东西：一是**服务端那句原因要一路走到人眼前**，`username` 短了走 pydantic 的 422（`detail` 是个数组），账号名不合法、重名、弱密码走服务层的 400（`detail` 是字符串），两路在界面上都只剩 `.el-message--error` 一句话，而这句话是 `client.ts` 把 `detail` 摊平再拼上前缀出来的——#74 与 #126 那一族断的就是这一环，把摊平那一步拆掉，界面退成 `创建失败: Request failed with status code 422`（实测红）；二是**一台浏览器的 Cookie 被另一台的动作当场作废**，四种动作的落点都是「那一台从此 401、这一台照常干活」，而接口层那个假客户端只有一个 cookie jar，量不出「别人被踢、我没被踢」；三是**角色是每次请求现查的**，把管理员自己降级之后会话一行没少、管理面却立刻 403，那半句 `api/users.py` 里的 `user.id != actor.id` 是全仓库唯一的签字处。支点句是页面顶部那句「停用的账号会立即在所有浏览器退出，历史与收藏都会保留」的后半句——少了这一句，把「停用」写成「删号」也能让前面所有断言全绿，所以停用之前先让那台浏览器真收藏一部片子，启用回来之后卡片还在原地。**这条能单独 `-g 用户管理` 跑**，它慢在真 bcrypt：建号要摘要一次，每一次真登录都要验一遍，本机绿的那一遍 17 秒，所以这条自己 `test.setTimeout(90_000)`。 第 19 条签的是「从界面上删掉一部影片」这一路从按钮到磁盘的整串接线，也是这一套里唯一**由界面发起删除**的一条。#75 补上的封面清理当时只由两条服务层用例签字，那两条把封面路径喂成临时目录里的一个字符串，验的是「那个函数调用到了」；而从 `.action-buttons` 里那枚「删除」到盘上少一个 `.jpg`，中间还隔着 axios 全局带的 `X-Requested-With`、中间件的 CSRF 与角色两道闸、`DELETE` 的 204、Vue 里那句 `router.push`，以及扫描真写进库里的那列绝对封面路径——这一整串替身夹具一条都没有（那 100 条里的「删除」只是把一份手写响应表里的行抹掉，磁盘从来不在场）。做法是在媒体目录里用 ffmpeg **现编**第二条 15 秒的片子（真库实测 `duration=15`、4867 字节、标题解析成 `e2e extra`），时长和字节数都刻意和播种那部 30 秒的不一样，扫描才会把它认成第二部片子。扫完先核对 `files_found=2 / new_videos=1`、库里那一行的 `thumbnail_path` 落在 `data/e2e/thumbnails/1/` 下面且文件真在（#63 那个相对路径 bug 的回归位置：只核对「文件在」挡不住它指到别处去），再顺手给它加一行收藏——级联清单少一张表在界面上完全看不出来，只有删除时才看得出来，而那一脚故意先不带 CSRF 头发 `POST /api/favorites/{id}`，403 才算签过真中间件（前端 axios 全局带那个头，所以正常点击走的是放行那条路）。然后从界面上删：按钮、确认框里那颗文字是「删除」而不是「确定」的按钮、提示那句「视频已删除」、跳回首页。核对两头：库里那行 `GET` 404、`GET /api/videos/{id}/thumbnail` 也 404（说的是「Video not found」而不是「没有封面」）、**再删一次**得到的是 404 原话 `Video with id N not found` 而不是一片 500（路由那句 `except ValueError` 的回归位置）、收藏里那一行跟着没了、首页的卡片少一张；磁盘上它那张封面没了，而**整个 `thumbnails/` 目录回到删除前那份「相对路径 + 内容 sha1」清单**——这一句才是这条用例最值钱的：删除走的是「先把路径取出来、提交之后再删文件」，一步写错就是把别人的图一起端走。同时用户的 `.mp4` **必须还在**：行是应用建的，片子是用户放的，只有前者归应用管。**这条能单独 `-g 删掉一部影片` 跑**。第 20 条签的是「编辑影片信息」这一路，它是库面最后一个从没在真后端签过字的写接口：`PUT /api/videos/{id}` 在服务层有单测，但那 100 条桩用例里"改完刷新还在"是 `fixtures.ts` 自己那份手写响应表说了算，而 `backend/src/services/scan_service.py:157` 那句 docstring——"a title or tag set someone curated by hand is left alone"——在 HTTP 之上一层都没有核过。做法是从界面上点「编辑」、填新片名和新简介、点第 4 颗星、保存，然后**换三路**读回同一个答案（`GET /api/videos/1`、列表查询里那一行、页面本身），并核对 `updated_at` 被列上的 `onupdate` 推新（替身夹具压根没有这一列，相等就说明那句 UPDATE 没走到）、`thumbnail_path` 一个字没动。第二脚是对**同一个源**再扫一遍：片名、简介、评分必须原样还在，`files_found=1 / new_videos=0`——这就是那句 docstring 的真身，已存在的行走的是 `_backfill_coordinates`，它只在 `series` 为空时才动手，从不碰标题。第三条主线是片名的**下游**：`backend/src/api/history.py:91` 那个 `video_title` 是读时联表现算的、不是历史行里的快照，所以改名之后 `/api/history/continue` 的返回、首页那条轨的 `.rail-caption`、`/history` 的 `.continue-title` 和卡片上的 `.video-link span` 必须一起改口（新名字搜得到、旧名字 0 条、`共 0 个视频`），而改名**之前**先把基线钉成旧名字——否则这一整段拿"处处都是 null"也能过。四类拒绝各有原话：`rating: 6` → `less_than_equal`、`title: ""` → `string_too_short`、`rating: null` → `value_error`（本单修的就是这一条：`VideoUpdate.rating` 原先标 `int | None` 而那一列是 NOT NULL，一路放行到 asyncpg 顶上才炸成 500）、空 body → 400「No fields to update」、`99999` → 404「Video with id 99999 not found」。member 那一步两头都钉：界面上根本数不出「编辑」那颗按钮，硬发 PUT 撞的是真中间件那句 403「需要管理员权限」，而库里那一行仍是 owner 刚改过的新名字；换回 owner 发 `{"title": null}` 得到 200，页面上退回文件名 `e2e_sample.mp4`——那一列可以为空，这半句是防止修复被做成"所有 null 都不许进"。末尾把片名/简介/评分恢复成播种那一份再读一次。**这条能单独 `-g 编辑影片` 跑**。第 21 条签的是「字幕装在容器里面」那一路，缝在 `backend/src/utils/media_streams.py` 那两个函数上——`probe_streams`（问 ffprobe 这个文件里有哪几条字幕轨、哪条转得了）和 `extract_subtitle_webvtt`（问 ffmpeg 把其中一条抠成 WebVTT，写 stdout、不落盘）。服务层那边有 9 条用例，其中 8 条把 `subprocess.run` 换成一份手写的 ffprobe JSON、第九条连子进程都不碰（它在「文件不存在」那一步就抛），所以「真容器会被报成什么样」从没被问过真进程；桩用例这一头更直接：`fixtures.ts` 那份 `/subtitles/streams` 处理器永远回 `subtitles: []`，`/subtitles/embedded/{n}/stream` 无论问哪条都回同一段写死的 `SAMPLE_VTT`（#128 那道守卫只保证地址接得住，语义仍是零）。现场是一部 `ffmpeg` 当场编出来的 mp4：h264 + aac + 两条字幕轨，一条 `mov_text`（`language=chi`）、一条 `ttml`（`language=eng`）。**为什么是 `ttml` 而不是 PGS/DVD 那种图像字幕**：本机 ffmpeg 只允许「文字转文字、图像转图像」的字幕编码（`-c:s dvbsub` 直接回 `Subtitle encoding currently only possible from text to text or bitmap to bitmap`），手边没有 bitmap 源，而 `ttml` 是 `WEBVTT_CODECS` 清单外唯一还能由文本编出来的那一格——`supported: false` 因此照样有真容器可对；它反过来还送出一个**真 415**：ffmpeg 没有 ttml 解码器，`-c:s webvtt` 在那条轨上真的失败一次，那句原因是它自己的 stderr 尾巴。`ttml` 只肯装进 mp4，matroska/webm 回 `-40 Function not implemented`；SRT 写在系统临时目录而不是媒体目录，因为扫描是递归的，落在媒体目录就会被认成 sidecar 字幕，`subtitles_found` 不再是 0。核对的全是只有真文件给得出的东西：`stream_index` 必须是 2 和 3 而不是 0 和 1（前端拿前者拼提取地址，差一位就问视频轨要字幕）、`container` 是 ffprobe 自己那串 `mov,mp4,m4a,…`、`label` 走 `subtitles.LANGUAGE_NAMES` 的 `chi → 中文`（#143 起这张表由内嵌和外挂两条来源共用） 和音频那条的三级兜底 `轨道 1`、`supported` 一真一假，反面是同一次请求里播种那部的 `subtitles: []`。提取那一路：`embedded/2/stream` 200 + `text/vtt` + 现场编进容器的那两句（替身那段和 sidecar 那句都不是这两句），`embedded/3/stream` 415，`embedded/0` 和 `embedded/1` 404——`extract_subtitle_webvtt` 先把候选限制在 `codec_type == "subtitle"`，这一句挡的是「清单用全部流建」那种写法。**播放页那一头签的是浏览器自己解析出来的 cue**：先点 `.preview-area` 把播放器挂上（`VideoDetail.vue` 的 `v-if="isPlaying"`，本单第一次红就停在等 `.subtitle-btn` 那 20 秒上），菜单里只有「中文」，「英文」以「1 条图像字幕浏览器放不出来」出现——那是 `VideoPlayer.vue:446` 那句 `.filter(track => track.supported)` 的签名，它读的是服务器给的字段而不是自己按 codec 名猜；点下去之后 `video.textTracks` 里那条轨的 cue 文本必须等于现场写进容器的那两句，这是整条用例里唯一「真进程 + 真容器 + 真浏览器」三方都在场的断言。**七条变异全红**（每条改完单跑一次、跑完还原并核对 md5）：`WEBVTT_CODECS` 里加 `ttml` → 第 2 步那份 `toEqual` 红；`_LANGUAGE_NAMES` 删掉 `chi` → 标签红；`extract_subtitle_webvtt` 去掉那个 subtitle-only 过滤 → 0/1 从 404 变成 415；`api/subtitles.py` 去掉 `except SubtitleConversionError` → 415 变 500；`stream_index` 换成 `position` → 那份 `toEqual` 红；`VideoPlayer.vue` 去掉 `.filter` → 菜单里多出「英文」；`_label_of` 的兜底改成「轨道 + position」 → 音频那条红。这一单**没有拆不红的护栏**。末尾 `finally` 用真 HTTP 删掉那一行（字幕与封面跟着级联走）、把那个 mp4 和临时目录收走（Windows 上 ffmpeg 读过的文件在子进程没退出前删不掉，所以 `rmSync` 带 `maxRetries`；就算没删干净也不影响下一轮——播种起跑就 rmtree），`finally` **之后**再核对影片 id 集合、`existsSync` 和整份封面清单回到起点（#120 的规矩）。**这条能单独 `-g 内嵌字幕` 跑**（solo 8.6 秒、整跑 3.4 秒，默认 30 秒超时够用）。第 22 条签的是「字幕装在影片**旁边**」那一路，缝在 `backend/src/utils/subtitles.py`——`_LANGUAGE_ALIASES` 那张别名表、`find_subtitle_files` 的 sidecar 认文件、`srt_to_webvtt`（纯 Python）和 `_ffmpeg_to_webvtt`（真子进程）。服务层那 12 条里转换这一半只有一条 `test_convert_ass_uses_ffmpeg`，而它把 `subprocess.run` 换成一份写死的 `CompletedProcess(stdout="WEBVTT\n\n")`——真 ffmpeg 遇到真 ASS 会吐出什么从没被问过真进程；桩用例那一头 `fixtures.ts` 的 `/videos/{id}/subtitles` 回的是手抄两行、stream 处理器无论问哪条都回同一段 `SAMPLE_VTT`。现场是把播种那部的字节复制成第二部，旁边写三个 sidecar（`.chi.ass` / `.eng.srt` / `.jpn.ass`）。核对的全是只有真文件给得出的东西：`language` 是别名表归一的 `zh`/`en`/`ja` 而界面上的名字和内嵌那一路**同一张表**（#143 起 `chi`/`eng`/`jpn` 在这一路给出的也是「中文」「英文」「日文」；这一条此前把“一边中文、一边裸码”钉成现状，把 `label` 退回原始后缀就是这里的红）；同一次转换里两种时间轴方言（Python 那条留小时 `00:00:03.000 -->`、ffmpeg 那条省掉 `00:05.000 -->`，谁把两边统一了就说明其中一路没走真进程）；`{\an8}` 被真解码器吃掉而 `Dialogue:`/`ScriptType` 整个不见（原样吐回一个 `.ass` 是这一路最像"成功"的失败）。**一句已修、一句现状**：ASS 那句以 `\N` 开头时 ffmpeg 把一次真换行写进 cue 里，而 WebVTT 里时间戳后紧跟空行就是"这条 cue 到此为止"，于是那句词落在所有 cue 之外、界面上一条也不显示——#140 修的就是它（`subtitles.fold_blank_lines_inside_cues()` 把紧跟时间戳的那一段空行折回文本，`.srt`、`.ass/.ssa` 和内嵌提取三条**转换**支路各套一次，而 `.vtt` 原样透传一个字节都不动，这条边界由 `test_convert_vtt_stays_byte_faithful_even_with_the_same_shape` 签着；那道"第一条时间戳之前不许动"的闸门则是第 23 条教出来的），现在第 22 条第 6 步解析出的是两句真 cue。仍然在的是另一半：一个只有 `[Events]` 段的 ASS 会被 ffprobe 认成 `lrc`（本机实测），ffmpeg 用 `text` 解码器读完只回一句 `WEBVTT`、一个 cue 都没有、退出码仍是 0，**应用就此回 200 而零条 cue**，界面上那条轨照旧可选、点了照旧什么都没有。字幕文件被删掉那一半有两副样子：不重载时那条轨放的是浏览器早就解析完存在内存里的旧 cue（接口那句 404 谁也没听见），重载之后要等那一条被点下去、`mode` 从 `disabled` 拨走，`<track>` 才真的去拉这一次、`readyState` 变 3——从这一刻起界面上有一句话说得出是哪一条取不到（#146：toast「字幕「英文」没能加载」加上菜单条目上那个「（加载失败）」，toast 三秒就走、标记留着），而**没被点过的那一条仍然一声不响**：`<track>` 上没有 `default` 时 Chromium 起步给的是 `disabled`，那种轨它一个请求也不发，浏览器还不知道，界面就没有东西该说（实测：重载后菜单四条干净、零条 toast、三条轨的 `mode` 全是 `disabled`、`readyState` 停在 0）。这里有一个机制上的坑记在这儿：`applyTrackMode` 选中一条时把三条一起拨到 `showing`/`hidden`，而**那一次拨动就是第一个请求的来处**，所以两条从没被选中的 `hidden` 轨也是 `readyState` 2、cue 齐全——别把"插进 DOM 就去拉"当成前提。扫描没有"字幕丢了"这一说，行仍留在清单里。**这条能单独 `-g sidecar 字幕` 跑**（solo 4.6 秒、整跑 4.6 秒，默认 30 秒超时够用）。踩过的坑：`selectTrack` 收尾会把 `showSubtitleMenu` 关掉，所以连着点两个字幕条目必须在中间重新点开菜单——不重开的症状不是断言失败，是那条 `.click()` 一直等到用例超时（Playwright 等一个永远不出现的元素时不分辨"没有"和"不可见"）。第 23 条和第 22 条同一支文件、同一个缝，签的是那份字幕文件**不是 UTF-8** 的时候这一路都发生些什么。缝在 `read_subtitle_text` 那两个从没有用例走到的编码分支上：服务层那 12 条里只有 `test_read_subtitle_text_falls_back_to_gb18030` 碰过编码，而 `utf-16` 那一支**全仓库零用例**（实测：删掉 UTF-16 那两个分支，`tests/test_utils/test_subtitles.py` + `tests/test_api/test_subtitles.py` 那 30 条一条都不红）；桩用例那一头 `fixtures.ts` 的 stream 处理器永远回同一段 UTF-8 的 `SAMPLE_VTT`，"编码"这件事在桩面上结构上不存在。现场是同一部复制的 `.mp4` 旁边四个文件——**同一个句子的四种编码**：GBK 的 `.chi.srt`、UTF-16LE 带 BOM 的 `.eng.srt`、UTF-8 带 BOM 的 `.jpn.vtt`、以及把前一份的 BOM 删掉的那一支 `.kor.srt`（后两份只差那几个字节头，用例自己断言 `subarray(2)` 相等）。Node 的 `Buffer` 编不出 GBK，所以那 136 字节是 base64 抄进来的，它的含义由「响应体逐字等于那两句词」签，不由注释签。**这一条量出的现状只有一句**：没有 BOM 的 UTF-16LE 会被当成 UTF-8 **成功**解码，回来的是夹着 NUL 的一串，于是时间戳正则和 `isdigit()` 那道过滤双双落空，路由仍然 200、仍然以 `WEBVTT` 开头，浏览器把那条轨标成 loaded（`elementState` 2）而 `cues.length === 0`——菜单里照旧可点，点了照旧一个字节也没有（`.subtitle-menu-note` 也不出现，和第 22 条第 5 步那个"200 而零条 cue"同一个形状）。所以这一条同时钉两头：认得出编码的三份必须逐字对上服务器交出的那一段，认不出的那一份必须**安静地什么都没有**。它另外钉了两件"断言本身的前提"，都是实测出来的：`fetchInPage` 用 `new TextDecoder()` 读 body，而它会吃掉前导 U+FEFF，所以**BOM 在文本断言里是隐形的**，只有 `bytes`（`body.byteLength`）分得开（第一次把 `utf-8-sig` 换成 `utf-8` 跑，两条用例全绿，症状就是这条）；以及 **Starlette 对任何 `text/*` 的 media_type 自动补 `; charset=utf-8`**，所以 `api/subtitles.py` 那句显式 charset 删掉也不 observable（变异 M4 因此全绿，那不是用例写松了，是断言的对象压根不存在）——要红得换掉整个 media type（M4b：`application/vnd.vtt`，两条一起红）。顺带还量到 Chromium 对**带 BOM 的 WebVTT 响应照收不误**（轨是 loaded 的、cue 全在），所以"服务器剥没剥 BOM"这件事在浏览器那头根本分不出来，分得开的只有 `bytes` 那一句。七次变异（每条改完单跑、跑完还原并核对 md5）：删 UTF-16 分支 → 红在响应体那一句；`utf-8-sig`→`utf-8` → 补上字节钉子后红在 `bytes`；`gb18030`→`big5` → 红在 GBK 那两句词；删 charset → 全绿（原因见上，只记不修）；换 media type → 两条全红；`.vtt` 改走 `srt_to_webvtt` → 红在 CRLF 那一句（`.vtt` 是原样透传的，折一次就说明这一路没走透传）；**把前端 `subtitleTrackUrl` 的 `/stream` 写成 `/Stream` → 两支用例全红**（第 22 条红在 ASS 那条轨没解析出来，第 23 条红在那四种编码没有都变成 cue——这是唯一一处从 `<track>` 的地址倒着同时咬住两个文件的变异，也是 `subtitleTrackUrl` 第一次被真浏览器签字）。**这条能单独 `-g 四种编码` 跑**（solo 3.7 秒、整跑 2.7~3.6 秒，默认 30 秒超时够用），那五个文件和那一行影片由自己的 `finally` 收走（Windows 上刚被 ffmpeg 读过的文件要 `maxRetries`），`finally` **之后**再核对影片 id 集合、那五个文件没了、整份封面清单回到起点，而**播种那部自己那条 `lang=zh` 的字幕一个字节没动**（这一句挡的是"注册 sidecar 时把别人的行一起改了一遍"那种写法）。第 24 条签的是「手工挂上去的那枚标签扛不扛得过一轮真扫描」，也就是第 20 条引用过的那句 docstring 的**后半句**（「a title **or tag set** someone curated by hand is left alone」）。在它之前的二十三条一次也没走到那一行：`backend/src/services/scan_service.py` 的 `_backfill_coordinates` 上有两道闸门（`if video.series is not None: return`、`if parsed.series is None: return`），而播种那部 `e2e_sample.mp4` 解析不出 series，所以函数第二趟扫描就在 166 行返回了，第 171 行那条"只往里加、不重列"的 append 在整套里从没被**执行**过。服务层确实有一条覆盖它的（`test_rescan_backfills_coordinates_into_old_rows`），但那一行的手工标签是**同一个 session 里用 ORM 直接挂上去的**，而真实世界是两趟事务：浏览器 `POST /api/tags/video/{id}` 提交完，`POST /api/sources/1/scan` 在另一个请求、另一个 session 里把同一条影片行重新捞出来（`Video.tags` 是 `lazy="selectin"`，捞出来那份里有没有别的 session 刚提交的那一枚，只有真 HTTP + 真 PG 才说得了谎）。做法是在媒体目录里复制一份播种那部的字节、换一个解析得出 series 的文件名，扫一遍得到那一行和它的自动标签，再从详情页那个「编辑标签」对话框手工挂上第二枚（#132 只在替身里走过这条写流程，真库这一头当时还没签过）。**"这行是解析器出现之前写进去的"这一种形状只能靠 SQL 安排**：库里没有任何接口能把 `series` 写回 null（`VideoUpdate` 只有 title / description / rating / tag_ids，手工建档的接口压根不存在），所以用例用一段一次性脚本走 `UPDATE`，并且断言 `rowcount == 1`——清空的要是别行，后面全部断言就在替空谈话；连接串只进子进程的环境变量，不进 argv、不打印。反面那一半靠**坐标当支点**：扫描后三个坐标列必须被填回来，少了这一句，整条用例在"函数压根没走到第 171 行"这个错误世界里也能全绿（和第 20 条"改名之前先把旧片名钉住"是同一个办法）。第三趟扫描核对幂等：标签表不涨、那张卡片仍是「1 个视频」（#85 那一族搬到关联行上的同一件事）。**这一次量出一条拆不红的护栏**：把 `if tag not in video.tags` 整段去掉（`video.tags = [*video.tags, *auto]`）后本用例**照样全绿**——`secondary` 关系上 SQLAlchemy 默认带 `AppendsUniqueBehavior`，同一个实例的重复 append 本来就被吃掉。所以那句 `expect(scanned.tags.length).toBe(2)` 钉的是"这一趟没把关联表写成两条"（所有写路径共同的账），不是那句护栏的账，用例里的注释也跟着改成了这句实话；和 #115 那次"mp4 那行的 `acodec` 签不到"是同一类发现：**能被拆红才有资格说签名**。另记一个浏览器层的坑：`page.goto()` 只等文档加载完，Vue 那一路的 `getVideo` 还在飞，直接读 `.tags-list .el-tag` 拿回来的是空数组，而快照里那一页还停在被 `VideoDetail.vue` 弹回首页之后的样子（看着像"那行没了"）——标签条这类"读回来才能比"的断言一律走 `expect.poll`。**这条能单独 `-g 手工挂` 跑**。 第 25 条签的是转码表里 **mp4** 那一行——那张四行配方从前只有三行有真产物，缺的这一行不是漏了，是被**源文件的后缀**挡着的：`transcode_service.py:83` 的 `output_path` 拿源文件 `with_suffix` 拼，播种那部本来就是 .mp4，所以"目标 mp4"在第 15 条第 3 步只能换来那句同格式的 400，ffmpeg 从没为那一行起过进程；而 `SUPPORTED_FORMATS['mp4']` 那两个编码器字面值（`-c:v libx264`、`-c:a aac`）又不进任何 API 响应（`get_supported_formats` 只回 `codec` 和 `extension`），于是改错它在当时那二十四条真用例和 754 条后端用例里一格都不红。做法是把**源**换掉而不是把目标换掉：现场 `-c copy`（不重编码、半秒）出一部.mkv 放进媒体目录，扫进来得到库里的第二行，从那一行点 mp4——闸门比的是拼出来的路径和源文件是不是同一个，不比扩展名，于是放行，那一行第一次真跑起来。核对的还是只有真进程给得出的三样：产物文件头那几个字节是 `ftyp`（不看文件名）、`ffprobe` 报出的两条流是 h264 + aac（配方表 `STREAMS` 里 mp4 那一行）、通知 `data.video_id` 认的是这一行而不是播种那部的 1；`progress` 钉 100 钉的是"`_run` 成功就写 100"，不是编码器最后报到第几秒（avi 那一路在第 15 条已经量过那两者不是一回事）。夹具自己有一道钉子：remux 出来的.mkv 必须真带着那条音频流——无声的源让 ffmpeg 把 `-c:a` 整个跳过，那半张配方就又查不到了（#115/#117 那一枪的延续）。**这条能单独 `-g mp4` 跑**（solo 与整跑都 5 秒上下）。它为什么住在 `video-transcode-mp4.real.spec.ts` 而不是第 15 条那支文件里：这套用例的**编号就是执行顺序**（#136、#139 都为此改过文件名），而这一条当时要排在最后（第 26 条那支 `watchlists` 由字母序自然排到了它后面，它的编号没动）——写进 `transcode.real.spec.ts` 它会物理上落到第 18 位，那要么推动后面七条的编号（那些数字在 CHANGELOG 的历史条目里也出现，历史不改写），要么让文档里的"第 25 条"和报告里的第 25 行不是同一条用例；`video-transcode-mp4` 排在 `video-tags` 后面是 `tags` < `transcode` 的字母序给的。代价是它要的那张配方表和读产物的几句断言得从 `transcode.real.spec.ts` 里搬出来——现在住在 `e2e/real/transcode_support.ts`，两个 spec 共用一份（抄第二份就变成两张表各自红，正是 #143 记下的那个病根）。它的顺序约束和第 16/17/19 条同款：起点那趟扫描断 `files_found: 2 / new_videos: 1`，所以那个 .mkv 和它的 mp4 产物由自己的 `finally` 收走（`maxRetries` 那半句同 #136），并在 `finally` **之后**用 `existsSync` 核对两个文件真没了（#120 的规矩）。第 26 条签的是片单那三条从没在真后端签过字的写路径：`PUT /api/watchlists/{id}`（改名与改备注）、`DELETE /api/watchlists/{id}`（删单）、`DELETE /api/watchlists/{id}/videos/{video_id}`（移出）。补上的理由是先量出来的，不是猜的：拿现有那份 `.coverage` 跑 `coverage report`，`src/api/watchlists.py:125`（PUT 路由那句 `raise HTTPException(409)`）和 `src/services/watchlist_service.py:129`（`watchlist.description = description`）在全套后端用例里**一次也没执行过**——409 只在 POST 那一路被撞过（`tests/test_api/test_isolation.py:61`），而没有一条用例往一条已存在的片单上 PUT 过备注（`test_watchlist_service.py:126` 断的那个 `description is None` 属于一条压根没写过备注的单）。第 5 条签过"从详情页新建一条也进库"那一路，而替身夹具那三个处理器（`fixtures.ts:1043` PUT、`:1096` 移出、`:1103` 删单）既不查名字撞不撞、也不按账号过滤，404 文案还是它自己编的那句「片单不存在」。只有真跑答得出的有三件事。**一是名字那条索引是 `(owner_id, name)` 而不是全局的**：owner 把自己的片单改成**成员**那条的名字必须放行（第 8 步），改成**本人**另一条的名字必须 409（第 6 步），中间还夹着一道"同名的自己不算撞"的闸门 `if name != watchlist.name`——只改备注那一次 PUT 是带着原名字进来的，去掉那道闸门它就跟自己撞死（M5 红在第 3 步那句成功 toast：`element(s) not found`）。**二是回声不算证据**：`Watchlists.vue:85` 和 `:97` 把 PUT 与 DELETE 的响应直接写进 `lists.value`，所以界面在"库里一个字没变"的那个世界里也照样显示新状态；于是每一步 UI 之后都另发一次 `GET` 读回来比，409 那一步只有真读回可看（名字、备注、`created_at` 和队列逐列未动——`created_at` 那一列挡的是"改名走成删了重建"）。**三是三条写路由的 404 全是服务层那句带 id 的原话** `Watchlist with id N not found`（`update`/`delete`/`remove_video` 三处 raise，路由只把 `str(e)` 塞进 detail），而 `GET /api/watchlists/{id}` 走的是路由自己那句**不带 id** 的 `Watchlist not found`：「这条存在但不归你」和「压根没这条」在读那一路是同一个字节串，这一句是拿一个 999999 和一条真存在的别人的单各读一次、比 `text` 逐字相等钉下来的，顺带才说明归属过滤没把别人的行存在性漏出去。移出那一步签的是**范围**：同一部片子在另一条里那一行必须还在（M4 把删除写成按 `video_id` 全库删，红在这一句），而影片行自己仍 200——删的是 `watchlist_items` 那一行，不是 `videos`；详情页那个「片单」弹窗读的是同一批行，勾上的状态和那条 `1 部` 计数跟着片单页一起改口。删单那一路顺带量出一个**双机制盲区，并且推翻了对它的预判**：`Watchlist.items` 上 `cascade="all, delete-orphan"`（ORM 侧）和 `watchlist_items.watchlist_id` 上 `ondelete="CASCADE"`（PG 侧）是同一个保证后面的两台机器，原以为拿掉任何一条都不会红——实测 M7 去掉 ORM 那条 cascade 之后本条**照样红**，只是红在更早的「移出」那一步：关系上没有 `delete-orphan` 时 `items.remove(item)` 走的是把外键置 null，PG 的 NOT NULL 当场 `NotNullViolationError`、路由 500、界面那句移出成功 toast 不出现（uvicorn 那一侧报出来的是 `asyncpg.exceptions.NotNullViolationError`，栈顶在 `remove_video` 的 commit 上）。所以"两条机制挡一件事"这个盲区今天只剩删单那一路没被拆开，而 M7 红得比那一步早、压根没走到它——记在这里，不当成已签。七次变异（每条改完单跑、跑完还原并核对 md5）：M1 去掉 `update` 里 `await self._require_free_name(user_id, name)` 那一句 → 红在第 6 步那句 409 toast，也就是那句从没执行过的 `api/watchlists.py:125`；M2 去掉 `if description is not None` → 只带名字的 PUT 把备注擦成 null，红在第 4 步；M3 放松 `get_watchlist` 的 `owner_id` 谓词 → 成员改得动 owner 那一条，红在第 7 步三格拒绝的第一格（200 而不是 404）；M4 移出改成按 `video_id` 删 → 红在第 9 步"另一条里那一行还在"；M5 见上；M6 `Watchlists.vue` 的 `erase` 去掉 `await deleteWatchlist(list.id)`（只在本地把那条筛掉）→ 红在删完之后那次真读回（200 而不是 404，而界面那句「片单已删除」照弹，确认框里那两句"及其 N 条排队记录 / 影片本身不会被动"也照说）；M7 见上。**两句现状记在这里而不是修掉**：界面那个前缀是中文的、后半句是服务端英文原话（`保存失败：Watchlist 'E2E 乙号队列' already exists`），因为 `client.ts` 把 `detail` 摊平之后直接拼进那句 toast——和第 18 条签的是同一条通路，只是这一路的英文没人读过；`PUT {description: ""}` 落进库里的是空串而不是 null，界面上 `.list-desc` 少一个元素，"两种没有备注"在库里分得开。编号 26 是字母序白送的：`watchlists` 排在 `video-transcode-mp4` 之后（`w` > `v`），前面 25 条的编号一个都没动。**这条能单独 `-g 三条写路径` 跑**（solo 13.5 秒、整跑 13.2 秒，默认 30 秒超时够用）：它自己建 owner 那两条和成员那一条，不借第 5 条那条队列也不借第 18 条成员那条同名片单，所以整跑时的断言一律取差值或"含不含我那几条的 id"，单独跑时那些名字还不存在也能绿；片单名字刻意取成互不为子串，因为 `panel()` 用的是 `hasText`。它不动播种那部的任何一列、不扫源、不留影片行，`finally` 按身份各自删掉自己那三条，并在 `finally` **之后**用真读回核对 owner 的片单名集合、`GET /api/watchlists?video_id=1` 那份持有人清单回到起点，影片 200、通知数未变（#120 的规矩）。

接线方式（`playwright.real.config.ts`）：

- 两条 `webServer` 串成一条 `&&`：`python -m src.e2e_seed` 成功后才起 uvicorn（8099），再另起一个 Vite（4174，`E2E_API_TARGET` 指向 8099）。端口和 8000/4173 都隔开，且 `reuseExistingServer: false`——绝不复用开发者手动起着的那个后端，否则测试数据写进真库。
- **配置文件里的顶层代码会被执行好几遍**（主进程一次、每个 worker 一次，本机实测三个进程），所以这里只允许只读的 `testDatabaseUrl()`。媒体夹具的准备全部由 `backend/src/e2e_seed.py` 自己做；把它放在配置里写文件的后果是播种之后目录又被清一次，库里的封面路径指向一个已经不存在的文件，表现为 `naturalWidth=0`。
- 一次性库只认 PostgreSQL，且库名必须以 `_test` 结尾：`env.ts` 和 `e2e_seed.py` 各有一道同样的闸门，前者让它在起服务器之前就失败，后者让它在下任何 TRUNCATE 语句之前就失败。口令走环境变量（`E2E_PASSWORD`），不进 argv、不进任何输出。
- 用例共用一次播种、`workers: 1` 顺序跑，所以二十六条的顺序就是约定：登录页 → 详情页/流式 → 收藏 → 继续观看 → 片单 → 角色网关 → 管理面两页 → 标签 → 通知 → 同目录双源 → 系统配置 → 搜索与筛选 → 丢失标记 → 个人设置 → 转码 → 转码失败 → 转码取消 → 用户管理 → 删除影片 → 编辑影片 → 内嵌字幕 → 外挂字幕 → 外挂字幕的编码 → 手工挂标签 → 转码表里 mp4 那一行 → 片单那三条写路径（片单那条会从详情页新建一条片单，所以它必须排在只核对"1 个片单"的那一段之后；角色网关那条末尾要核对 owner 那两条片单，所以它必须紧跟在片单那条后面——**用 `-g` 挑着跑会把这条和它前面那条一起弄红**，那不是回归；管理面两页只依赖播种和它自己那次登录，可以单独跑。标签那条把 `/api/tags` 整张表当成"只有我自己建的那两个"来断言，而播种一个标签都不建；通知那条则把 `notifications` 整张表当成"只有播种那趟扫描留下的那一行"，并且它自己会再扫一遍、给 owner 写下已读、往 source 上盖一个新的 `last_scan_at`，所以这两条都排在后面。第 10 条排在后段：它在页面上新建一个源、扫一遍、再把它删掉，末尾是把 `GET /api/sources` 整张表当成"只剩播种那一个源"来断言的——它自己会留下 `last_scan_at`，也会真的动源表，放在任何一条前面都可能把别人数源的断言弄红；它调扫描接口用的是 `POST /api/sources/{id}/scan`，注意 `backend/src/api/scan.py` 的 router 前缀本身就是 `/api`（前端 axios 的 baseURL 也是 `/api`，所以组件里写的是 `/sources/${id}/scan`，两边拼出来的最终路径一样，但在浏览器里手工拼错前缀只会得到一个 404）。除角色网关那条之外其余都能单独跑（`-g 标签挂在真影片`、`-g 通知是广播`、`-g 同一个目录`、`-g 系统配置`、`-g 搜索框`、`-g 消失`、`-g 个人设置`、`-g 三种拒绝`、`-g 转码失败`、`-g 用户管理`、`-g 删掉一部影片`、`-g 编辑影片`、`-g 内嵌字幕`、`-g sidecar 字幕`、`-g 四种编码`、`-g 手工挂`、`-g 转码取消`、`-g mp4`、`-g 三条写路径` 是证明能红时用的十九条命令，各自只命中一条（`-g 转码` 从 #126 起会同时命中成功和失败那两条，从 #136 起再命中取消那一条，从 #144 起还命中「转码表里 mp4 那一行」那一条——所以点这一条要用 `-g 转码取消`，点第 25 条要用 `-g mp4`（第 15~17 条的标题里没有 `mp4` 这四个字母）；`-g sidecar 字幕` 从 #139 起仍然只命中第 22 条那一条，因为同文件新那支的标题里一个 `sidecar` 也没有））。第 11 条（系统配置）紧跟在第 10 条后面：它开头断的是 `settings` 表**空着**时那五项走代码默认值，末尾又留下四行非默认的键值——顺序在它这里不是硬约束（播种那趟 `TRUNCATE` 走的是 `business_tables()`，整库连 `settings` 一起清，所以每次起跑都是空表），但任何后来想在别处读系统配置的用例都会踩到它留下的那几行，所以谁再往中间插一条读 `settings` 的用例，就得自己改成先把值定下来再断言。第 12 条（搜索与筛选）排在第 8 条之后：它往 `tags` 里留两个标签，其中一个**挂在播种那部片子上**，而第 8 条把 `/api/tags` 整张表当成"只有我自己建的那两个"来断言、并且要求那个没挂过片子的标签 `video_count` 留在 0——所以它必须在第 8 条之后。它还教会一件事：界面现在会把越界的 `?page=` 从地址栏里擦掉，将来任何用例落到"第 N 页"上再断言地址栏，都得先等这一次钳位跑完。第 13 条（丢失标记）排在第 12 条之后、后面那八条之前：它在磁盘上把播种那个文件搬走又搬回来，所以**任何还要扫到那一个文件的用例都不能排在它后面**（断言中途失败时 `finally` 只保证文件回位，库里那一行会停在 `is_missing=true`，而它自己两次扫描会给源 1 再盖两次 `last_scan_at`、把 `notifications` 留成三行——第 9 条把整张通知表当成"只有播种那一行"来断言，同理必须在它之前）。**这条能单独 `-g 消失` 跑**：它起点是播种后的 1 行通知和 1 部片子，中间那两次扫描是它自己发的。第 14 条（个人设置）排在第 13 条之后、转码之前：它按服务端数组的下标点行、不写死条数，所以前面那些用例各自登录留下的活会话它照单全收；它往后面只留三样——owner 的 `theme=dark`、owner 名下两三行活会话、以及**已经换回 `E2E_PASSWORD` 的口令**（第 15~26 条要用它登录），而转码那三条（长流程、失败、取消）、用户管理和删除影片都不读主题，读会话行数的只有用户管理那一条——它数的只有自己现建那个账号名下的几台。反过来它不清理自己的会话，所以谁再往它后面插一条把 `/api/auth/sessions` 整张表当成"只有我自己这几台"来断言的用例，得先自己读一遍摘要再比差值。**这条能单独 `-g 个人设置` 跑**：它三台 context 全在自己手里，不借前面任何一条留下的行。第 15 条（转码）排在倒数第十二条（它后面是转码失败、转码取消、用户管理、删除影片、编辑影片、内嵌字幕、外挂字幕、外挂字幕的编码、手工挂标签、转码表里 mp4 那一行、片单那三条写路径），理由和第 13 条同类：它在**被扫描的那个媒体目录里**造文件（`output_path` 是源文件的 `with_suffix`，所以产物就是 `data/e2e/media/e2e_sample.<格式>`），因此它自己用 `test.afterEach` 把每一个产物删掉——留在磁盘上，下一轮扫描就把它当成一部新片子，"共 1 个视频"那一类断言全得跟着重写；它也给 `notifications` 留两行（webm、avi 各一条完成通知），而第 9 条把整张通知表当成"只有播种那一行"，所以它必须在第 9 条之后。反过来它末尾核对 `GET /api/videos` 的 `total` 仍是 1，所以任何会多留下一行影片的用例都不能排在它后面。第 17 条（转码取消）就排在同文件的第 15、16 条后面，本单没有新起一份 `transcode-cancel.real.spec.ts`，因为文件名里 `-`（45）排在 `.`（46）之前，那份新文件会插到 `transcode` 前面，把后面六条的编号一起推动。它对现场的规矩和第 16 条同款：`e2e_slow.mp4` 与那半截 `.webm` 由它自己在 `finally` 里收走，末尾那次真跑完的 mkv 产物走文件级的 `afterEach`，库里那一行在正文末尾就 `DELETE` 掉并当场核对 `GET` 404、`total` 回到起点（封面那份清单也核对，靠的是第 19 条签过的"删行连带删封面"），所以它既不给第 9 条那句"整张通知表只有播种那一行"留行（它排在第 9 条之后），也不给后面的用例留第二部片子。它另外留下一条 `transcode_complete`（末尾那次 mkv）和源 1 的一次 `last_scan_at`，这两样排在它后面的四条都不读。**这一条立了一条通用规矩**：`finally` 里的清理**删不掉也不许抛**——Windows 上刚被真 ffmpeg 读过的那个输入文件紧接着 unlink 会得到 EBUSY（带 `maxRetries` 也要留一手），而 `finally` 抛出的异常会顶掉 try 块里那个真正的断言失败（实测：把取消那次 API 调用打桩掉之后，报出来的是一句 unlink 错误而不是它究竟红在哪一步）。**这条能单独 `-g 转码取消` 跑**。第 18 条（用户管理）排在第 17 条（转码取消）之后、删除影片之前，位置是 `users` 落在 `transcode` 和 `video-delete` 之间的字母序给的。它对库的扰动都自己收回去：新建的那一个账号留在库里（`users` 这张表整跑下来只有它自己动，所以它对账号表敢断绝对的名字集合而不是差值）、给那部片子挂的一行收藏在末尾删掉、管理员的角色在 `finally` 里补回来。最后这一处是这条唯一真正的顺序风险：中段要把管理员降成成员，那一刻全库能把他升回来的只有刚被它提拔的那个成员，那三步（降级自己 → 由它升回自己 → 把它降回成员）之间任何一步崩掉，后面三条就对着一个没有管理员的库满屏 403。所以收尾的 `keepAnOwner` 不带断言地补这个不变量（先试本人自己的口令，绿的那一路一次登录失败都不产生，也就踩不到那个「5 次锁 10 分钟」的限流器），跑绿之后再真读一遍角色列核对复原真的生效了。它读会话行数只读自己现建那个账号名下的，前面用例留在 owner 名下的活会话它一眼都不看，所以第 14 条那句「不读主题和会话」对它同样成立。**这条能单独 `-g 用户管理` 跑**。 第 19 条（删除影片）排在第 16 条（转码失败）之后：它是这一轮里会**改变库里影片数**的三条之一（中途真多出一行、末尾删掉；第 16 条那个"后缀合法、内容不是容器"的文件也建得起一行，但它自己在 `finally` 里把文件收走，下一轮扫描不会再登记它），所以任何还要按「只有一部片子」断言的用例都不能插在它们三条中间（第 17 条插在中间是允许的：它自己造那一行、也在正文末尾删掉那一行，后面那句"删除只该动自己那一张封面"数的仍是差值；第 18 条也允许：它一部影片都不数，只借播种那一行挂一枚收藏）；它自己造的那个 `.mp4` 由自己的 `finally` 收走——留在媒体目录里，下一轮扫描就会把它当成一部新片子，「共 1 个视频」那一族断言全得跟着重写。它对起点一律「先读一遍再比差值」，不写死收藏数、通知数或影片 id，所以前面那些用例留在库里的行不会弄红它。第 20 条（编辑影片）排在倒数第七条，这个位置有一半是文件名字母序给的顺带结果（`video-edit` 落在 `video-delete` 后面），真正的硬约束是它**改的是播种那部片子的名字**：第 1~13 条里有一批按 `e2e sample`、"继续观看只有 1 部"和"共 1 个视频"断言的用例，它必须排在它们全部之后。它对源 1 的那次扫描报 `files_found=1 / new_videos=0`，这也要求前面的用例把自己造在媒体目录里的文件收干净（第 16、17、19 条正是这么做的）。它末尾把片名/简介/评分恢复成播种那一份再读一次，所以将来往它后面插一条不必猜上一轮留下了什么。第 21 条（内嵌字幕）排在 `video-edit` 和 `video-tags` 之间，这个位置是文件名字母序给的（`video-embedded-subtitles` 落在两者中间），硬约束只有一条：它必须排在第 9 条（通知）之后——它自己那趟扫描会往 `notifications` 真写一行，而第 9 条把整张通知表当成「只有播种那一行」来断言。它起点那次扫描断的是 `files_found=2 / new_videos=1`（媒体目录里此刻只有播种那部和它自己刚编出来那一部），所以它造的那个 `.mp4` 必须由自己的 `finally` 收干净——留在磁盘上，第 22、23、24、25 条那四次扫描的 `files_found` 就不是 2，「共 N 个视频」那一族断言全得跟着重写。它不改播种那部的任何一列，也不按片名找别人那一行。第 22 条（外挂字幕）排在 `video-embedded-subtitles` 和 `video-tags` 之间，这个位置同样是文件名字母序给的，硬约束和第 21 条同族：它必须排在第 9 条（通知）之后（自己那趟扫描往 `notifications` 真写一行），而且它在**被扫描的那个媒体目录里**写四个文件（一部复制的 `.mp4` 加三条 sidecar），起点那次扫描断的是 `files_found=2 / new_videos=1 / subtitles_found=3`，所以那四个必须由自己的 `finally` 收干净——留在磁盘上，同一支文件里第 23 条（编码那一支）起点那趟扫描的 `files_found` 就不是 2。第 23 条（外挂字幕的编码）和第 22 条住在**同一支文件**里，这是 #136 那条规矩的第二回应用：两条用例共用一个缝、一套夹具和一份收尾，而另起一份 `video-sidecar-subtitles-encoding.real.spec.ts` 的话，`-`（45）排在 `.`（46）之前，它会插到 `video-sidecar-subtitles` **前面**，把那条的编号一起推动。它的顺序约束就是那条文件的（排在第 9 条之后），另外自己写五个文件（一部复制的 `.mp4` 加四份编码各异的字幕），起点断 `files_found=2 / new_videos=1 / subtitles_found=4`，那五个同样必须自己收干净——留在磁盘上，第 24 条起点那趟扫描的 `files_found` 就不是 2。第 24 条（手工挂的标签扛过一次真扫描）排在倒数第三条：`video-tags` 落在 `video-edit` 后面也是字母序的顺带结果，但它这个位置有几条自己的硬约束——它在**被扫描的那个媒体目录里**复制出第二个 `.mp4`（字节就是播种那部的，只有名字换成一个解析得出 series 的），起点那次扫描断的是 `files_found=2 / new_videos=1`，所以第 16、17、19 条那种"自己造的文件自己收走"的规矩在它这里是前提而不是选项；它给源 1 连盖三次 `last_scan_at`、留下一行通知（第一次扫描真多了一行才发，后两次 `new_videos=0` 按 #85 那条不发），所以第 9 条那种"整张通知表只有播种那一行"的断言必须在它前面跑完。它自己造的那一行、那两枚标签和磁盘上那个文件由 `finally` 收走（删影片那一路连带把它的封面也带走，这条由第 19 条签过），并且它在 `finally` **之后**用真读回核对影片 id 集合和标签名清单回到起点（#120 那条规矩：收尾的 body 里不写断言，否则真正的失败会被自己的还原断言盖住）。它不改播种那部的任何一列，也不按片名找自己那一行——它按解析出来的 `morning squad S02E03` 找，和第 20 条末尾那次恢复互不相干。**这条能单独 `-g 手工挂` 跑**：那一行、那两枚标签、那个文件全在它自己手里。第 26 条（片单那三条写路径）排在最后，位置是 `watchlists` 落在 `video-transcode-mp4` 之后的字母序给的，它对现场的约束只有两条：不扫源（所以前面那批「自己造的文件自己收走」的规矩与它无关，那四次扫描的 `files_found` 也不用跟着涨），以及它留下的片单行全部由自己的 `finally` 按身份删干净——第 5 条那句「1 个片单」和第 6 条末尾 owner 那两条片单的核对都排在它前面，所以它可以在整跑里用差值断言，也可以在 solo 时用绝对名字断言。它中途把 owner 的一条改成了成员那条的名字（第 8 步「本人范围外不挡」那一句），所以收尾若漏删任何一条，下一轮整跑里「同名片单只在本人范围内冲突」那一格就会撞——这就是它为什么非但要在 `finally` 之后核对 owner 的名字集合，还要核对 `GET /api/watchlists?video_id=1` 那份持有人清单。**这份用例还立了一条接线规矩**：真后端 spec 共用的 `signIn` / `fetchInPage` / `requestJson` / `CSRF` / `scanSource` / `coverFingerprints` 现在住在 `e2e/real/support.ts`（后两个由第 13 条和第 19 条共用：一个说「扫描不该动别人的封面」，一个说「删除只该动自己那一张」，读的是同一个目录、同一份算法），但 `test.beforeEach(signIn)` **必须在每个 spec 文件里各自写一行**——Playwright 的根级钩子只绑到"第一个 import 到该模块的文件"上（模块被缓存，第二个文件的 import 不再执行一次），实测症状是单独 `-g` 跑每个文件都绿、整跑时后面那个文件的页面停在 `about:blank`、连相对 fetch 的地址都拼不出来（报错长这样：`Failed to execute 'fetch' on 'Window': Failed to parse URL from /api/transcode/formats`）。`signIn()` 换身份的前提也写在同一条里：一进 `/login` 就先清 cookie——已登录的人撞 `/login` 会被守卫直接送回首页，表单根本不渲染，这条真库实测过一次 30 秒超时。真库实测的行是 `id=1`、片名 `e2e sample`、30 秒、5008 字节、一条视频流加一条 1 秒的 AAC 音轨（音轨是给第 15 条那种音频编码器准备的）、320×180 封面、一条 `lang=zh` 字幕，视频源那一行是 `id=1`、名字 `E2E local`、`last_scan_at` 已经被播种那趟扫描盖上了时间戳；播种另外用**服务层本身**写出一次观看进度（18 秒，`completed` 归 `is_completed()` 算）和一条带说明的片单，继续观看和片单那两条读的就是这两行，`watch_events` 里那一行则是统计页那 30 格的唯一来源。播种建**两个**账号（owner `e2e_owner` + member `e2e_member`），member 那一份什么都不写，所以"成员从 0 开始加收藏""同名片单只在本人范围内冲突"这两个断言才有东西可对；角色网关那条断言的全是 403，而"member 那行其实没建成"同样会一路 403，因此播种的核对闸门查的是 `role` 这一列而不是行数。

## 常见问题

### 1. 路径别名

```typescript
// vite.config.ts
import { resolve } from 'path'

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
```

### 2. TypeScript 配置

```json
// tsconfig.app.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

### 3. Element Plus 按需导入

```typescript
// main.ts：只 app.use() 模板里真正用到的组件，图标由各组件局部导入
import { ElButton, ElCard, /* ... */ ElLoading } from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

for (const component of [ElButton, ElCard /* ... */]) {
  app.use(component)
}
// v-loading 指令随 ElLoading 插件注册，不在组件列表里
app.use(ElLoading)
```

`app.use(ElementPlus)` 会引用全部组件、`import * as Icons` 会注册 293 个图标组件，两者都会让 tree-shaking 失效、入口 chunk 从 276 kB 涨回 769 kB。**新增页面若用到列表外的组件，必须一并加入注册列表**：漏掉的组件不会报错，只会渲染成未知标签（单测装了完整插件，因此全绿；浏览器里那块 UI 直接不见了）。

## 构建和部署

```bash
# 开发
npm run dev

# 构建
npm run build

# 预览构建结果
npm run preview

# 单元测试（Vitest + jsdom + @vue/test-utils）
npm run test
npm run test:watch
npm run test:coverage

# 端到端测试（Playwright，自动启动 4173 端口的 dev server）
npm run test:e2e

# 端到端测试（26 条打真后端：自己起 8099 的一次性后端，需要一个 _test 结尾的 PG 库）
npm run test:e2e:real

# 类型检查（含测试代码）
npm run build
npm run typecheck:test
```
