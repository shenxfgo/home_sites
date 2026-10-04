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
- 视图里的请求走 `@/api/client`，用 `vi.hoisted` + `vi.mock('@/api/client')` 记录 `url`，再断言路径**不带 `/api` 前缀**（`baseURL` 已经是 `/api`）；`tests/api/paths.spec.ts` 会自动遍历所有 api 模块做同样校验。
- 只测 api 模块本身时，可以改用 `client.defaults.adapter` 拦截，能顺带验证 `baseURL + url` 拼出的完整地址。注意请求体到这里已被 axios 序列化过，要 `JSON.parse(String(config.data))` 再断言字段名。
- 弹层分两种查法：popover / dropdown 会 teleport 到 `document.body`（用 `popper-class` 查），**`el-dialog` 默认 `append-to-body: false`，是就地渲染的**，得在 `wrapper` 里查 `.el-dialog`；挂载时仍传 `attachTo: document.body`，否则弹层里的焦点与事件走不通。
- **模板里新用一个 `el-*` 组件，必须同时加进 `src/main.ts` 的按需注册清单**。漏注册不会报错，只会把标签当未知元素渲染（单测照样全绿，因为 `tests/setup.ts` 装的是完整 `ElementPlus` 插件），实际界面里就只剩一串纯文字——`<el-radio>` 曾经就是这样在浏览器里消失的。所以组件注册这类问题只能靠 e2e 或真机发现。
- 主题选「跟随系统」时要读 `window.matchMedia`，jsdom 没有这个 API，`tests/setup.ts` 里给了一份假实现；用例里别再各自 `stub`。
- 弹层一定要给 `popper-class`（如 `notification-popper` / `user-popper`）：页面上同时有两个弹层时，`.el-popover` 这种选择器在 Playwright 严格模式下会因命中两处直接报错。
- 定时器轮询用 `vi.useFakeTimers()` + `vi.advanceTimersByTimeAsync()`，用例结束前 `vi.useRealTimers()`。

### 端到端测试（Playwright）

`frontend/e2e/`，由 `playwright.config.ts` 自动拉起 `localhost:4173` 的 dev server。`e2e/fixtures.ts` 里的 `mockApi(page, { signedIn, needsSetup, role, themes })` 用带状态的假接口替换整个 `/api` 面，因此 **E2E 不需要启动后端**；注意路由要按 `url.pathname.startsWith('/api/')` 匹配，用 `**/api/**` 通配会把 Vite 的 `/src/api/*.ts` 模块请求一起拦掉导致白屏。

默认 `signedIn: true`：所有非 `/auth/*` 请求正常回数据。传 `signedIn: false` 时替身一律回 `401 {detail:'未认证'}`，登录流程、守卫跳转、401 拦截这些用例就是这么打的。

角色面在这份替身里是照抄中间件的：`role: 'member'` 之后，`/users`、`/settings` 连读都 403；写接口反过来按 `MEMBER_WRITE` 这条正则放行，它是 `backend/src/middleware/auth.py` 里 `MEMBER_WRITE_PATHS` 的一比一抄写，名单之外的写请求一律 403。账号表（owner / member / 一个停用号）与 `themes`（按账号存的主题）是跨请求的可变状态，所以"退出后换账号登录、主题跟着人走"这种用例能真跑。后端放行或新收一条写接口时，**`MEMBER_WRITE`、后端名单和 `e2e/roles.spec.ts` 的期望要一起改**，否则浏览器测的是替身，不是后端。

### 打真后端的端到端测试（`e2e/real/`）

上面那句"浏览器测的是替身"就是这套用例存在的理由：替身把响应该长什么样写在前端测试里，前后端各自对着自己那份理解测试，中间没有签字的人。`npm run test:e2e:real` 跑 9 条，一条 `page.route` 都没有，请求走完 Vite 代理 → uvicorn → PostgreSQL：真表单登录换来真 cookie、首页渲染的是真扫描写出来的那一行、字幕轨是 sidecar 真转成 WebVTT 的、`Range` 分段回的是 `206 + Content-Range`、点下去的收藏在刷新后还在库里、继续观看那条轨的"剩 0:12"和进度条宽度算自真历史行、片单页连条目的"已看"秒数和片单说明一起从库里读回来，第 6 条把 `MEMBER_WRITE` 那份手抄本交回真中间件核对（成员读管理面 403、名单外的写 403、名单内的写真的落库，换回 owner 看到的仍是自己那两份数据），第 7 条签的是管理面两页的**算法**——`/api/history/stats` 真按 `days` 返回零填充的整窗（替身可以不理这个参数，前端自己也数不出"30 格"这件事），`/api/users` 那格的 `signed_in_devices` 是中间件每次登录真写下的会话行数。第 8 条签标签：两个标签各数各的 `video_count`（挂上片子的那个才涨，没挂过的留在 0，所以那个数不可能是"全局有几部片子"），而 `GET /api/tags/{id}/videos` 必须带着每部片子自己的 `tags` 集合回来——这正是 #101 那个 500 的回归位置，它只在真库的关系加载上出现：序列化是同步的，那一查没预取第二层就是 greenlet 之外的一次 IO，替身夹具永远测不到。第 9 条签通知流：那一行是播种那趟真扫描留下的，句末"发现 1 个新视频、1 条字幕"和 `data` 里那三个计数都是扫描器的计数器（替身给的是手抄文案，给不出一份 JSON 列在真库上的往返），同批文件再扫一遍时计数全 0、通知数也**必须还是 1**（#85 的回归位置：库没变就不发），而 owner 点掉已读并刷新之后成员看到的仍是未读——feed 是广播的、`read` 是按人的，这两半只有在真库的 `notification_reads` 复合主键上才分得开。

接线方式（`playwright.real.config.ts`）：

- 两条 `webServer` 串成一条 `&&`：`python -m src.e2e_seed` 成功后才起 uvicorn（8099），再另起一个 Vite（4174，`E2E_API_TARGET` 指向 8099）。端口和 8000/4173 都隔开，且 `reuseExistingServer: false`——绝不复用开发者手动起着的那个后端，否则测试数据写进真库。
- **配置文件里的顶层代码会被执行好几遍**（主进程一次、每个 worker 一次，本机实测三个进程），所以这里只允许只读的 `testDatabaseUrl()`。媒体夹具的准备全部由 `backend/src/e2e_seed.py` 自己做；把它放在配置里写文件的后果是播种之后目录又被清一次，库里的封面路径指向一个已经不存在的文件，表现为 `naturalWidth=0`。
- 一次性库只认 PostgreSQL，且库名必须以 `_test` 结尾：`env.ts` 和 `e2e_seed.py` 各有一道同样的闸门，前者让它在起服务器之前就失败，后者让它在下任何 TRUNCATE 语句之前就失败。口令走环境变量（`E2E_PASSWORD`），不进 argv、不进任何输出。
- 用例共用一次播种、`workers: 1` 顺序跑，所以九条的顺序就是约定：登录页 → 详情页/流式 → 收藏 → 继续观看 → 片单 → 角色网关 → 管理面两页 → 标签 → 通知（片单那条会从详情页新建一条片单，所以它必须排在只核对"1 个片单"的那一段之后；角色网关那条末尾要核对 owner 那两条片单，所以它必须紧跟在片单那条后面——**用 `-g` 挑着跑会把这条和它前面那条一起弄红**，那不是回归；管理面两页只依赖播种和它自己那次登录，可以单独跑。标签那条把 `/api/tags` 整张表当成"只有我自己建的那两个"来断言，而播种一个标签都不建；通知那条则把 `notifications` 整张表当成"只有播种那趟扫描留下的那一行"，并且它自己会再扫一遍、给 owner 写下已读、往 source 上盖一个新的 `last_scan_at`，所以这两条都排在后面、通知排最后。除角色网关那条之外其余都能单独跑（`-g 标签挂在真影片`、`-g 通知是广播` 是证明能红时用的两条命令，各自只命中一条））。`signIn()` 换身份的前提也写在同一条里：一进 `/login` 就先清 cookie——已登录的人撞 `/login` 会被守卫直接送回首页，表单根本不渲染，这条真库实测过一次 30 秒超时。真库实测的行是 `id=1`、片名 `e2e sample`、30 秒、320×180 封面、一条 `lang=zh` 字幕，视频源那一行是 `id=1`、名字 `E2E local`、`last_scan_at` 已经被播种那趟扫描盖上了时间戳；播种另外用**服务层本身**写出一次观看进度（18 秒，`completed` 归 `is_completed()` 算）和一条带说明的片单，继续观看和片单那两条读的就是这两行，`watch_events` 里那一行则是统计页那 30 格的唯一来源。播种建**两个**账号（owner `e2e_owner` + member `e2e_member`），member 那一份什么都不写，所以"成员从 0 开始加收藏""同名片单只在本人范围内冲突"这两个断言才有东西可对；角色网关那条断言的全是 403，而"member 那行其实没建成"同样会一路 403，因此播种的核对闸门查的是 `role` 这一列而不是行数。

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

# 端到端测试（9 条打真后端：自己起 8099 的一次性后端，需要一个 _test 结尾的 PG 库）
npm run test:e2e:real

# 类型检查（含测试代码）
npm run build
npm run typecheck:test
```
