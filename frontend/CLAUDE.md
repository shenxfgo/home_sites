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
- 「登录设备」是 `/profile` 最后一张卡：`listSessions()` 回的每一行里 `token_hash` 是摘要而不是 Cookie 值，前端只拿它当"退哪一台"的地址。User-Agent 由 `deviceLabel()` 翻成 `Chrome · Windows` 这类文案，认不出来就原样截 40 字符——**那句话是客户端自己写的，只决定这一行显示什么，任何判断都不看它**。当前这台不给「退出」按钮（退它就是退出本页，走顶栏的「退出登录」）；`handleRevoke` 成功时本地删行，失败时弹后端原话并重读，别把列表留在假数据上；改密码会顺手退掉别的浏览器，所以成功后同样 `loadDevices()`。四张卡各自带语义 class（`card-account` / `card-theme` / `card-password` / `card-devices`），单测与 e2e 按它定位——**别用 `.profile-card` 的第几张来选**，加一张卡就会错位。
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
- `tests/api/stub-coverage.spec.ts` 是**第三层**：前两层问的是"后端有没有这条路由""形状对不对"，这一层问"那 90 条桩用例的替身**接不接得住**这条地址"。它 `import { mockApi } from '../../e2e/fixtures'`（不复制匹配器——复制就只能保证"我抄的这份"和夹具一致，而真实的失效方式是夹具改了、守卫没跟着改），用一份假 `page` 接住它注册的那个 `page.route` 处理函数，再用假 `route` 逐条驱动遍历器交出的 76 条地址，断言三条：每条都有人答（一次 `fulfill` 都没调的分支在真浏览器里是永久挂起）、没有一条落到 `未预置的接口: METHOD /path` 那句兜底上、非 `/auth/*` 的一条都不该被替身的默认拒绝拦成 401/403。**每条地址各自重装一份夹具**，这不是洁癖：夹具是有状态的（`signedIn`、`removedVideos`、`readNotifications`、转码状态机），而 `POST /auth/logout` 会把 `signedIn` 翻回 false、遍历又按模块名排序（`auth` 排第一）——共用一份时实测后面六十条全被拦成 401，兜底那句一次也执行不到，"没有缺分支"那条规则演成一份看着全绿的空守卫。`postData()` 一律回 `{}`：这一层问的是地址，不是请求体，而夹具里所有按 body 行事的分支都带默认值或 `typeof` 闸门，空对象走得通。**它上线当天量出 17 条缺分支**（标签的增删改与挂卸、源的建改、`/mediaStreams`、内嵌字幕流、单键设置的读写），其中一半是界面上真有的写路径——也就是说这些流程此前在桩用例里根本跑不起来。补进夹具的这几条是有状态的（`tagRows` / `sourceRows` / `subtitleRows` / `systemSettings` 四张每次安装重建的小表），"建完刷新还在"从此不需要现编假数据。**这一层管地址不管语义**：替身答得出的那一串仍是前端自己写的假设，语义只有 `e2e/real/` 那 18 条签。
- **#129 给 `views/Tags.vue` 一次补了两层**（`tests/views/Tags.spec.ts` 10 条 + `e2e/tags.spec.ts` 8 条），这两层的分法只有一条：**这一问是不是只有这一层答得出**。把视图里那句 `{{ tag.video_count ?? 0 }}` 的兜底摘掉，**只有单测红**——替身夹具的 `tagBody()` 永远带上 `video_count`，「后端没带这个字段时长什么样」在浏览器那一路结构上量不到；反过来把夹具里建标签那条重名判断关掉，**只有 e2e 红**——单测 `vi.mock('@/api/tags')`，替身根本不在场。落法因此是：形状类断言（PUT body 只含改动那个字段、无改动一次 PUT 都不发、写失败时不许回读把人刚填的名字抹掉）放单测，「点得动、卡片真的少一张」放 e2e。**往一个视图补用例时先问哪一层量不到，别把同一串断言抄两遍。**
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

上面那句"浏览器测的是替身"就是这套用例存在的理由：替身把响应该长什么样写在前端测试里，前后端各自对着自己那份理解测试，中间没有签字的人。`npm run test:e2e:real` 跑 18 条，一条 `page.route` 都没有，请求走完 Vite 代理 → uvicorn → PostgreSQL：真表单登录换来真 cookie、首页渲染的是真扫描写出来的那一行、字幕轨是 sidecar 真转成 WebVTT 的、`Range` 分段回的是 `206 + Content-Range`、点下去的收藏在刷新后还在库里（那一条还顺手把收藏列表**越界那一页**的形状钉死：`page=2` 也是 200、`items` 是空的、`total` 说真话、`page` 原样回显——替身夹具那份 `/api/favorites` 处理器根本不读 `page`，而 `Favorites.vue` 那句钳位全靠 `total` 是诚实的才能算出最后一页）、继续观看那条轨的"剩 0:12"和进度条宽度算自真历史行、片单页连条目的"已看"秒数和片单说明一起从库里读回来，第 6 条把 `MEMBER_WRITE` 那份手抄本交回真中间件核对（成员读管理面 403、名单外的写 403、名单内的写真的落库，换回 owner 看到的仍是自己那两份数据），第 7 条签的是管理面两页的**算法**——`/api/history/stats` 真按 `days` 返回零填充的整窗（替身可以不理这个参数，前端自己也数不出"30 格"这件事），`/api/users` 那格的 `signed_in_devices` 是中间件每次登录真写下的会话行数。第 8 条签标签：两个标签各数各的 `video_count`（挂上片子的那个才涨，没挂过的留在 0，所以那个数不可能是"全局有几部片子"），而 `GET /api/tags/{id}/videos` 必须带着每部片子自己的 `tags` 集合回来——这正是 #101 那个 500 的回归位置，它只在真库的关系加载上出现：序列化是同步的，那一查没预取第二层就是 greenlet 之外的一次 IO，替身夹具永远测不到。第 9 条签通知流：那一行是播种那趟真扫描留下的，句末"发现 1 个新视频、1 条字幕"和 `data` 里那三个计数都是扫描器的计数器（替身给的是手抄文案，给不出一份 JSON 列在真库上的往返），同批文件再扫一遍时计数全 0、通知数也**必须还是 1**（#85 的回归位置：库没变就不发），而 owner 点掉已读并刷新之后成员看到的仍是未读——feed 是广播的、`read` 是按人的，这两半只有在真库的 `notification_reads` 复合主键上才分得开。第 10 条签"同一个目录挂两个源"：`videos.filepath` 是全库唯一的，所以这件事只有真库能回答——第二条扫描必须报 `files_found=1 / new_videos=0`（文件确实被看到了，不是扫了个空目录），库里仍然只有一部片子、归属还在源 1，而时间戳只盖在被扫的那一个源上；把第二个源删掉之后那部片子和它的封面都必须原样还在（`source_service.delete` 的谓词是 `Video.source_id == source_id`，写反了就会删掉别人的片子）。第 11 条签系统配置那一页，关键是 **`PUT /api/settings` 回的是请求体本身**——"保存成功"和"库里到底有没有那一行"在替身夹具里是同一件事，所以改完必须换一路读才算数；起始那五项是播种从不写 `settings` 表时**代码默认值经一次 Text→int/bool 强制转换**读回来的样子，而 `GET /api/settings/{key}` 给的是那一列的原文（`"7200"`），界面上那个 7200 是 `int()` 之后的数。这一条同时钉住本单的修复：单键 PUT 原先只认键名不认值，写一个读不回来的字符串进去，`GET /api/settings` 从此 500，直到有人手工去改那一行。第 12 条签搜索与筛选的分面，这里有两个替身永远答不出来的问题：一是 `frontend/e2e/fixtures.ts` 里的 `matchesSearch` 是拿 TypeScript 把 `backend/src/utils/video_search.py` **又实现了一遍**，两份实现各自测自己那一侧，谁改了对方都不知道；二是替身的 `/videos` 处理器**根本不读 `page` / `page_size`**，永远回 `page: 1, page_size: 20`，所以那 90 条桩用例里的翻页全是虚构的。这一条把浏览器打出去的一串字符（URL 编码 → FastAPI 参数解析 → 一次真 ILIKE）的结果核到三处一致：卡片数、服务器对**同一个字符串**报的 total、地址栏里那个词；顺带钉住只有真库才给得出的三件事——ILIKE 不区分大小写（替身是 `toLowerCase` + `includes`）、`标签:` / `源:` 这两个算子真被解析器认下、观看状态读的是**这个账号**的播放历史（换成员登录，同一个 `未看完` 对他必须是 0 条，而 `没看过` 是 1 条；同库同一片子两个人报的数不一样，只有真中间件加真库给得出）。它顺手量出一个真缺陷并修在 `views/Home.vue`：`?page=` 是首页自己写进地址栏的，分享一条链接或浏览器后退能带回来一个已经不存在的页——那一页确实是空的而库里不空，界面于是同屏说「共 1 个视频」和「添加视频源并扫描即可开始使用」；现在越界的一页会钳回最后一页再读一次，地址栏跟着改（`watch([selectedSourceId, selectedTagId, currentPage, pageSize], pushQuery)` 本来就管这个）。**这条能单独 `-g 搜索框` 跑**：它自己建那两个标签，不借第 8 条留下的。第 13 条签"文件从磁盘上消失再挂回来"这一整条往返，它要的真库证据是三样：`videos.is_missing` 那一列（替身夹具只照抄 `fixtures.ts` 里那份 `is_missing: false`，翻不翻都由它自己说了算）、`GET /api/videos?search=丢失` 背后那条真谓词，以及通知里那两句话的**方向**。做法是把 `data/e2e/media/e2e_sample.mp4` 搬去同级的 `hidden/`，扫一遍，再搬回来扫一遍——搬出源目录是硬要求：本地扫描是递归的，任何仍留在里面、名字以 `.mp4` 结尾的东西都会被登记成一部新片子，那一验的就不是"把标记翻回去"而是"多出一行"。核对的是那一次扫描报 `files_found=0` 而库里那一行**还在**（`total` 仍是 1、`id` 仍是 1，只有 `is_missing` 翻成 true）、首页那条横幅和卡片角上的「丢失」标读的是同一个 `丢失` 探针、「查看」把算子填进搜索框；搬回来之后同一行影片 `id`、同一批封面文件（按 `thumbnails/` 下每个 `.jpg` 的相对路径 + 内容 sha1 逐项比）、同一条观看历史行的 `id` 都不许变——三样合起来才挡得住"删了重扫"这种写法：封面路径是按 `<root>/<source_id>/<片名>-<locator 摘要>.jpg` 拼的，行重建就会换一个目录名，而光看影片行会漏掉 `play_history` 那张表。第 14 条签个人设置页那两条写路径，也是除 NotFound 外唯一从没在真库上签过字的视图：`e2e/fixtures.ts` **根本没有 `/api/auth/sessions` 处理器**（当时那批桩用例因此从没真的请求过设备列表；#128 已经把这条分支补进夹具，桩用例现在接得住它，而设备列表那页的界面语义由 #120 那条真后端用例签），服务层那边只有 CLI 那条**不带** `keep_token_hash` 的路有测试——也就是说界面上那句「其他浏览器会被退出，这台仍然保持登录」此前没有任何一层签过字。核对的全是要有**两个以上各自握着 cookie 的 context** 才证得出的事：同一张会话表在两台浏览器里行集合与顺序完全一致、而 `current` 各指各的那一行（把 `current` 存成一列、或拿创建时间当"当前"都会红）；从界面上点掉「退出」、再按「刷新」逼服务端重答一次，清单**只少被点的那一枚摘要**，被退那台从此 401 而这台仍 200（`handleRevoke` 只在本地筛一遍就收工，不刷新等于没验）；成员拿 owner 的摘要去删得到 404「设备不存在或已退出」而 owner 那一行原样还在（`revoke_session` 的谓词是 `(user_id, token_hash)`）；形状不对的摘要（`…/sessions/zZZ`）在路由那个 `Path(pattern=...)` 上就 422，跟 404 分得很清；主题点「深色」之后换一路读回 `dark`（PUT 的响应回显的就是刚写进去的那份，拿它当证据等于自证），member 全程留在 `light`，而一台**全新浏览器**（没有 localStorage 可依赖）登录同一账号仍是深色——存的是账号而不是这台机器；`{theme:"neon"}` 出不了 `Literal`，422 之后库里仍是 `dark`；改完口令这一台还活着、改密码前签进来的那两台 401、member 那台不受影响（批量撤销只动这个账号）。第 15 条签转码那条长流程，它是这一套里唯一"应用真起了一个 FFmpeg 子进程、真往磁盘写了一个文件"的用例：`backend/tests/test_services/test_transcode_service.py` 那 11 条服务用例里，凡是跑到编码那一步的（5 条）都把 `transcode_video` 整个换掉，剩下 6 条只测拒绝，而 90 条桩用例的 `POST /api/transcode/{id}` 处理器**不做任何校验、永远不会失败**，`output_path` 写死成 `/tmp/out.<格式>`——两层假各测自己那份理解，中间没人签过字。核对的因此全是只有真进程给得出的东西：格式清单那四项各带编码器和**带点的**扩展名（替身那份是没点的 `'mkv'`）、界面不刷新也能轮询到自己的终态、服务器报回来的**绝对输出路径**落在 `data/e2e/media/` 里且文件头那几个字节自报所请求的那种容器（读 EBML 的 DocType / RIFF 的 FormType，不看文件名）、产物里那两条流正是配方里那一对编码器（webm 是 vp9 + opus、avi 与 mkv 是 h264 + aac；那四种格式里界面真能编出三种，同格式那道闸门只挡得住源文件自己那一个 `mp4`，问 `ffprobe` 而不是问接口——`acodec` 从不进任何响应，而这一句能成立的前提是播种那部片子**带一条音轨**：无声的源让 ffmpeg 把 `-c:a` 整个跳过，于是把 webm 的 acodec 写成容器拒收的 `aac` 也能一路绿（#115 的变异⑧就是这么绿的，#117 补上音轨后它红了）、mkv 那一行也有真产物（#125 补上第三次转码：把它的 `codec` 改成 `libvpx-vp9`、`acodec` 改成 `libopus` 各红一次，所以四行配方里三行的那半张 `-c:v`/`-c:a` 都由真进程签过字了；没签过的是 `mp4` 那一行的 `acodec`——把它改成 `libopus` 这一套仍然全绿，因为 mp4→mp4 在闸门就得到 400，ffmpeg 从没为它起过进程）、后台任务用 `async_session_maker()`（不是请求那个 session）写进真库的那条 `transcode_complete` 带着自己的 `video_id` 与 `format`，以及三种拒绝各有原话（同格式那句 `overwrite the original file`、`Unsupported format: exe`、对已经结束的任务 cancel 得到 404 `No active transcoding`）。它还钉住本单的修复：`target_format` 必须在**进闸门之前**归一大小写——闸门 `check_format_support` 本来就不区分，只有归一在闸门里做，被放行的 `'AVI'` 才会先回一个 HTTP 200「已启动」、再在后台失败成「不支持的格式：AVI」。这条**能单独 `-g 三种拒绝` 跑。第 16 条签的是转码**失败**那一路，它的覆盖原先只有半层：`backend/tests/test_services/test_transcode_service.py` 那条 `test_failed_job_keeps_the_error_message` 把 `transcode_video` 换成一个返回 `(False, "boom")` 的假函数，于是"错误字段跟着作业走"这一句是证的，而 `transcode_video` 里那个 20 行的 stderr 尾巴到底从真子进程捞回了什么、闸门放行之后一个失败的任务在界面上长成什么样、后台任务发出去的到底是 `transcode_complete` 还是 `transcode_error`——三处都没有一个字签过字，而 90 条桩用例那份 POST 处理器永远不会失败。现场是"后缀合法、内容不是任何一种容器"的一个文件：扫描只认后缀（`extract_video_info` 探针失败回的是默认值），所以库里确实建得起一行，而那一行的 `duration` 和 `thumbnail_path` 都是 null——`progress` 钉在 0 靠的是前者（`_run` 拿到 `duration=None`，`on_progress` 一次都不会被调用），不是"编码器最后报到第几秒"那个细节。断言落在三层各一处：接口那句原因里有 ffmpeg 自己的两个措辞（`moov atom not found` / `Invalid data found when processing input`，方括号里那个地址每次运行都随机，所以不钉它）；页面 `.status-error` 那一段和接口字段**逐字相等**（#74 那一族的回归位置，`?? '转码失败'` 那种兜底常量会把原因吃掉，把 `{{ transcodeStatus.error }}` 换成常量就是这么红的）；真库那条通知是 `transcode_error`、标题「转码失败」、`data` 带着这一行的 id 和 `webm`。它还量了一件一直没核实的事：`transcode_video` 只在 cancel 分支 `unlink` 输出、失败分支不删——这一趟磁盘上之所以干净，是因为 ffmpeg **连输入都没打开**，什么都没写出来；这不等于"失败不留产物"的通用保证，用例里那句注释也只说这一种失败模式。两个细节记一下：通知的基线取在扫描**之后**（那一趟扫描自己也发一条，库真变了才发——第 9 条钉的就是它），而那个垃圾文件和可能的产物都由这一条自己在 finally 里收走，因为排在它后面的删除影片那条按 `files_found=2 / new_videos=1` 数媒体目录。**这条能单独 `-g 转码失败` 跑。** 第 17 条签的是「从界面上删掉一部影片」这一路从按钮到磁盘的整串接线，也是这一套里唯一**由界面发起删除**的一条。#75 补上的封面清理当时只由两条服务层用例签字，那两条把封面路径喂成临时目录里的一个字符串，验的是「那个函数调用到了」；而从 `.action-buttons` 里那枚「删除」到盘上少一个 `.jpg`，中间还隔着 axios 全局带的 `X-Requested-With`、中间件的 CSRF 与角色两道闸、`DELETE` 的 204、Vue 里那句 `router.push`，以及扫描真写进库里的那列绝对封面路径——这一整串替身夹具一条都没有（那 90 条里的「删除」只是把一份手写响应表里的行抹掉，磁盘从来不在场）。做法是在媒体目录里用 ffmpeg **现编**第二条 15 秒的片子（真库实测 `duration=15`、4867 字节、标题解析成 `e2e extra`），时长和字节数都刻意和播种那部 30 秒的不一样，扫描才会把它认成第二部片子。扫完先核对 `files_found=2 / new_videos=1`、库里那一行的 `thumbnail_path` 落在 `data/e2e/thumbnails/1/` 下面且文件真在（#63 那个相对路径 bug 的回归位置：只核对「文件在」挡不住它指到别处去），再顺手给它加一行收藏——级联清单少一张表在界面上完全看不出来，只有删除时才看得出来，而那一脚故意先不带 CSRF 头发 `POST /api/favorites/{id}`，403 才算签过真中间件（前端 axios 全局带那个头，所以正常点击走的是放行那条路）。然后从界面上删：按钮、确认框里那颗文字是「删除」而不是「确定」的按钮、提示那句「视频已删除」、跳回首页。核对两头：库里那行 `GET` 404、`GET /api/videos/{id}/thumbnail` 也 404（说的是「Video not found」而不是「没有封面」）、**再删一次**得到的是 404 原话 `Video with id N not found` 而不是一片 500（路由那句 `except ValueError` 的回归位置）、收藏里那一行跟着没了、首页的卡片少一张；磁盘上它那张封面没了，而**整个 `thumbnails/` 目录回到删除前那份「相对路径 + 内容 sha1」清单**——这一句才是这条用例最值钱的：删除走的是「先把路径取出来、提交之后再删文件」，一步写错就是把别人的图一起端走。同时用户的 `.mp4` **必须还在**：行是应用建的，片子是用户放的，只有前者归应用管。**这条能单独 `-g 删掉一部影片` 跑**。第 18 条签的是「编辑影片信息」这一路，它是库面最后一个从没在真后端签过字的写接口：`PUT /api/videos/{id}` 在服务层有单测，但那 90 条桩用例里"改完刷新还在"是 `fixtures.ts` 自己那份手写响应表说了算，而 `backend/src/services/scan_service.py:157` 那句 docstring——"a title or tag set someone curated by hand is left alone"——在 HTTP 之上一层都没有核过。做法是从界面上点「编辑」、填新片名和新简介、点第 4 颗星、保存，然后**换三路**读回同一个答案（`GET /api/videos/1`、列表查询里那一行、页面本身），并核对 `updated_at` 被列上的 `onupdate` 推新（替身夹具压根没有这一列，相等就说明那句 UPDATE 没走到）、`thumbnail_path` 一个字没动。第二脚是对**同一个源**再扫一遍：片名、简介、评分必须原样还在，`files_found=1 / new_videos=0`——这就是那句 docstring 的真身，已存在的行走的是 `_backfill_coordinates`，它只在 `series` 为空时才动手，从不碰标题。第三条主线是片名的**下游**：`backend/src/api/history.py:91` 那个 `video_title` 是读时联表现算的、不是历史行里的快照，所以改名之后 `/api/history/continue` 的返回、首页那条轨的 `.rail-caption`、`/history` 的 `.continue-title` 和卡片上的 `.video-link span` 必须一起改口（新名字搜得到、旧名字 0 条、`共 0 个视频`），而改名**之前**先把基线钉成旧名字——否则这一整段拿"处处都是 null"也能过。四类拒绝各有原话：`rating: 6` → `less_than_equal`、`title: ""` → `string_too_short`、`rating: null` → `value_error`（本单修的就是这一条：`VideoUpdate.rating` 原先标 `int | None` 而那一列是 NOT NULL，一路放行到 asyncpg 顶上才炸成 500）、空 body → 400「No fields to update」、`99999` → 404「Video with id 99999 not found」。member 那一步两头都钉：界面上根本数不出「编辑」那颗按钮，硬发 PUT 撞的是真中间件那句 403「需要管理员权限」，而库里那一行仍是 owner 刚改过的新名字；换回 owner 发 `{"title": null}` 得到 200，页面上退回文件名 `e2e_sample.mp4`——那一列可以为空，这半句是防止修复被做成"所有 null 都不许进"。末尾把片名/简介/评分恢复成播种那一份再读一次。**这条能单独 `-g 编辑影片` 跑**。

接线方式（`playwright.real.config.ts`）：

- 两条 `webServer` 串成一条 `&&`：`python -m src.e2e_seed` 成功后才起 uvicorn（8099），再另起一个 Vite（4174，`E2E_API_TARGET` 指向 8099）。端口和 8000/4173 都隔开，且 `reuseExistingServer: false`——绝不复用开发者手动起着的那个后端，否则测试数据写进真库。
- **配置文件里的顶层代码会被执行好几遍**（主进程一次、每个 worker 一次，本机实测三个进程），所以这里只允许只读的 `testDatabaseUrl()`。媒体夹具的准备全部由 `backend/src/e2e_seed.py` 自己做；把它放在配置里写文件的后果是播种之后目录又被清一次，库里的封面路径指向一个已经不存在的文件，表现为 `naturalWidth=0`。
- 一次性库只认 PostgreSQL，且库名必须以 `_test` 结尾：`env.ts` 和 `e2e_seed.py` 各有一道同样的闸门，前者让它在起服务器之前就失败，后者让它在下任何 TRUNCATE 语句之前就失败。口令走环境变量（`E2E_PASSWORD`），不进 argv、不进任何输出。
- 用例共用一次播种、`workers: 1` 顺序跑，所以十八条的顺序就是约定：登录页 → 详情页/流式 → 收藏 → 继续观看 → 片单 → 角色网关 → 管理面两页 → 标签 → 通知 → 同目录双源 → 系统配置 → 搜索与筛选 → 丢失标记 → 个人设置 → 转码 → 转码失败 → 删除影片 → 编辑影片（片单那条会从详情页新建一条片单，所以它必须排在只核对"1 个片单"的那一段之后；角色网关那条末尾要核对 owner 那两条片单，所以它必须紧跟在片单那条后面——**用 `-g` 挑着跑会把这条和它前面那条一起弄红**，那不是回归；管理面两页只依赖播种和它自己那次登录，可以单独跑。标签那条把 `/api/tags` 整张表当成"只有我自己建的那两个"来断言，而播种一个标签都不建；通知那条则把 `notifications` 整张表当成"只有播种那趟扫描留下的那一行"，并且它自己会再扫一遍、给 owner 写下已读、往 source 上盖一个新的 `last_scan_at`，所以这两条都排在后面。第 10 条排在后段：它在页面上新建一个源、扫一遍、再把它删掉，末尾是把 `GET /api/sources` 整张表当成"只剩播种那一个源"来断言的——它自己会留下 `last_scan_at`，也会真的动源表，放在任何一条前面都可能把别人数源的断言弄红；它调扫描接口用的是 `POST /api/sources/{id}/scan`，注意 `backend/src/api/scan.py` 的 router 前缀本身就是 `/api`（前端 axios 的 baseURL 也是 `/api`，所以组件里写的是 `/sources/${id}/scan`，两边拼出来的最终路径一样，但在浏览器里手工拼错前缀只会得到一个 404）。除角色网关那条之外其余都能单独跑（`-g 标签挂在真影片`、`-g 通知是广播`、`-g 同一个目录`、`-g 系统配置`、`-g 搜索框`、`-g 消失`、`-g 个人设置`、`-g 三种拒绝`、`-g 转码失败`、`-g 删掉一部影片`、`-g 编辑影片` 是证明能红时用的十一条命令，各自只命中一条（`-g 转码` 从 #126 起会同时命中成功和失败那两条））。第 11 条（系统配置）紧跟在第 10 条后面：它开头断的是 `settings` 表**空着**时那五项走代码默认值，末尾又留下四行非默认的键值——顺序在它这里不是硬约束（播种那趟 `TRUNCATE` 走的是 `business_tables()`，整库连 `settings` 一起清，所以每次起跑都是空表），但任何后来想在别处读系统配置的用例都会踩到它留下的那几行，所以谁再往中间插一条读 `settings` 的用例，就得自己改成先把值定下来再断言。第 12 条（搜索与筛选）排在第 8 条之后：它往 `tags` 里留两个标签，其中一个**挂在播种那部片子上**，而第 8 条把 `/api/tags` 整张表当成"只有我自己建的那两个"来断言、并且要求那个没挂过片子的标签 `video_count` 留在 0——所以它必须在第 8 条之后。它还教会一件事：界面现在会把越界的 `?page=` 从地址栏里擦掉，将来任何用例落到"第 N 页"上再断言地址栏，都得先等这一次钳位跑完。第 13 条（丢失标记）排在第 12 条之后、后面那五条之前：它在磁盘上把播种那个文件搬走又搬回来，所以**任何还要扫到那一个文件的用例都不能排在它后面**（断言中途失败时 `finally` 只保证文件回位，库里那一行会停在 `is_missing=true`，而它自己两次扫描会给源 1 再盖两次 `last_scan_at`、把 `notifications` 留成三行——第 9 条把整张通知表当成"只有播种那一行"来断言，同理必须在它之前）。**这条能单独 `-g 消失` 跑**：它起点是播种后的 1 行通知和 1 部片子，中间那两次扫描是它自己发的。第 14 条（个人设置）排在第 13 条之后、转码之前：它按服务端数组的下标点行、不写死条数，所以前面那些用例各自登录留下的活会话它照单全收；它往后面只留三样——owner 的 `theme=dark`、owner 名下两三行活会话、以及**已经换回 `E2E_PASSWORD` 的口令**（第 15~18 条要用它登录），而转码和删除影片两条都不读主题和会话。反过来它不清理自己的会话，所以谁再往它后面插一条把 `/api/auth/sessions` 整张表当成"只有我自己这几台"来断言的用例，得先自己读一遍摘要再比差值。**这条能单独 `-g 个人设置` 跑**：它三台 context 全在自己手里，不借前面任何一条留下的行。第 15 条（转码）排在倒数第四条（它后面是转码失败、删除影片、编辑影片），理由和第 13 条同类：它在**被扫描的那个媒体目录里**造文件（`output_path` 是源文件的 `with_suffix`，所以产物就是 `data/e2e/media/e2e_sample.<格式>`），因此它自己用 `test.afterEach` 把每一个产物删掉——留在磁盘上，下一轮扫描就把它当成一部新片子，"共 1 个视频"那一类断言全得跟着重写；它也给 `notifications` 留两行（webm、avi 各一条完成通知），而第 9 条把整张通知表当成"只有播种那一行"，所以它必须在第 9 条之后。反过来它末尾核对 `GET /api/videos` 的 `total` 仍是 1，所以任何会多留下一行影片的用例都不能排在它后面。第 17 条（删除影片）排在第 16 条（转码失败）之后：它是这一轮里会**改变库里影片数**的两条之一（中途真多出一行、末尾删掉；第 16 条那个"后缀合法、内容不是容器"的文件也建得起一行，但它自己在 `finally` 里把文件收走，下一轮扫描不会再登记它），所以任何还要按「只有一部片子」断言的用例都不能插在它们两条中间；它自己造的那个 `.mp4` 由自己的 `finally` 收走——留在媒体目录里，下一轮扫描就会把它当成一部新片子，「共 1 个视频」那一族断言全得跟着重写。它对起点一律「先读一遍再比差值」，不写死收藏数、通知数或影片 id，所以前面那些用例留在库里的行不会弄红它。第 18 条（编辑影片）排在整跑的最后，这个位置有一半是文件名字母序给的顺带结果（`video-edit` 落在 `video-delete` 后面），真正的硬约束是它**改的是播种那部片子的名字**：第 1~13 条里有一批按 `e2e sample`、"继续观看只有 1 部"和"共 1 个视频"断言的用例，它必须排在它们全部之后。它对源 1 的那次扫描报 `files_found=1 / new_videos=0`，这也要求前面的用例把自己造在媒体目录里的文件收干净（第 16、17 条正是这么做的）。它末尾把片名/简介/评分恢复成播种那一份再读一次，所以将来往它后面插一条不必猜上一轮留下了什么。**这份用例还立了一条接线规矩**：真后端 spec 共用的 `signIn` / `fetchInPage` / `requestJson` / `CSRF` / `scanSource` / `coverFingerprints` 现在住在 `e2e/real/support.ts`（后两个由第 13 条和第 17 条共用：一个说「扫描不该动别人的封面」，一个说「删除只该动自己那一张」，读的是同一个目录、同一份算法），但 `test.beforeEach(signIn)` **必须在每个 spec 文件里各自写一行**——Playwright 的根级钩子只绑到"第一个 import 到该模块的文件"上（模块被缓存，第二个文件的 import 不再执行一次），实测症状是单独 `-g` 跑每个文件都绿、整跑时后面那个文件的页面停在 `about:blank`、连相对 fetch 的地址都拼不出来（报错长这样：`Failed to execute 'fetch' on 'Window': Failed to parse URL from /api/transcode/formats`）。`signIn()` 换身份的前提也写在同一条里：一进 `/login` 就先清 cookie——已登录的人撞 `/login` 会被守卫直接送回首页，表单根本不渲染，这条真库实测过一次 30 秒超时。真库实测的行是 `id=1`、片名 `e2e sample`、30 秒、5008 字节、一条视频流加一条 1 秒的 AAC 音轨（音轨是给第 15 条那种音频编码器准备的）、320×180 封面、一条 `lang=zh` 字幕，视频源那一行是 `id=1`、名字 `E2E local`、`last_scan_at` 已经被播种那趟扫描盖上了时间戳；播种另外用**服务层本身**写出一次观看进度（18 秒，`completed` 归 `is_completed()` 算）和一条带说明的片单，继续观看和片单那两条读的就是这两行，`watch_events` 里那一行则是统计页那 30 格的唯一来源。播种建**两个**账号（owner `e2e_owner` + member `e2e_member`），member 那一份什么都不写，所以"成员从 0 开始加收藏""同名片单只在本人范围内冲突"这两个断言才有东西可对；角色网关那条断言的全是 403，而"member 那行其实没建成"同样会一路 403，因此播种的核对闸门查的是 `role` 这一列而不是行数。

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

# 端到端测试（16 条打真后端：自己起 8099 的一次性后端，需要一个 _test 结尾的 PG 库）
npm run test:e2e:real

# 类型检查（含测试代码）
npm run build
npm run typecheck:test
```
