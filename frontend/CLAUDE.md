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
│   │   ├── auth.ts        # 认证 API（登录/登出/me/status/改密）
│   │   ├── videos.ts      # 视频 API
│   │   ├── subtitles.ts   # 字幕 API（列表/登记/删除 + WebVTT 地址）
│   │   ├── sources.ts     # 视频源 API
│   │   ├── settings.ts    # 设置 API
│   │   ├── watchlists.ts  # 片单 API（队列读写 + 进出队列）
│   │   └── ...
│   ├── components/         # 可复用组件
│   │   ├── VideoCard.vue
│   │   ├── VideoPlayer.vue
│   │   ├── SourceCard.vue
│   │   ├── DuplicateChecker.vue # 重复文件检测（按需调 /videos/duplicates）
│   │   └── ...
│   ├── composables/        # 组合式函数
│   │   ├── useTheme.ts    # 主题切换
│   │   └── useAuth.ts     # 当前用户（模块级 ref 共享，未引 Pinia）
│   ├── views/              # 页面组件
│   │   ├── Home.vue       # 首页/视频列表
│   │   ├── Login.vue      # 登录页（裸页，不套 MainLayout）
│   │   ├── Sources.vue    # 视频源管理
│   │   ├── Stats.vue      # 观影统计（数字卡 + 纯 CSS 柱状图 + 标签分布）
│   │   ├── Watchlists.vue # 片单（一份份手排队列，移出/删除只动队列行）
│   │   ├── Tags.vue       # 标签管理
│   │   ├── Settings.vue   # 应用设置
│   │   └── ...
│   ├── layouts/            # 布局组件
│   │   └── MainLayout.vue
│   ├── router/             # 路由配置
│   │   └── index.ts
│   ├── types/              # TypeScript 类型
│   │   ├── video.ts
│   │   ├── auth.ts         # UserRole / AuthUser / AuthStatus
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
  timeout: 10000,
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
    const message = error.response?.data?.detail ?? error.message ?? 'Unknown error'
    return Promise.reject(new Error(message))
  }
)
```

所以调用侧拿到的一直是 `Error(后端 detail)`，`catch` 里直接 `e.message` 就是给人看的那句话。

## 认证与路由守卫

- 状态在 `composables/useAuth.ts`：模块级 `ref`（`user` / `needsSetup` / `loaded`）+ `load()` / `signIn()` / `signOut()` / `forget()`，全站共享一份，**没有引 Pinia**。
- 会话是后端发的 `HttpOnly` Cookie，前端读不到也不需要读；`load()` 打 `/auth/status` 判断登录态，`/auth/me` 取身份。
- `router.beforeEach` 对非 `meta.public` 的路由先 `load()` 再放行，未登录跳 `/login?redirect=<原地址>`。跳回原地址时只认 `/` 开头的站内路径，`//host` 会被浏览器按协议相对地址解析，必须挡掉。
- 登录页要脱离布局：`App.vue` 用 `route.meta.public === true` 决定套不套 `MainLayout`，因此新增公开页时记得打 `meta: { public: true }`，否则会被顶栏包进去。
- 后端重启或被 `revoke-sessions` 踢掉之后，任何一次请求都会回 401，`setUnauthorizedHandler` 里清本地身份并跳登录，页面不会停在"看着有数据、点什么都没反应"的状态。
- 收藏、历史、片单、统计、`is_new` 角标与通知 `read` 回的都是**当前账号**的那份，接口路径与响应结构没变，前端不按账号写分支；换号一定要走退出登录（`signOut()` + 重新 `load()`），否则页面里还是上一个账号已经加载好的列表。

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

## 测试规范

### 单元测试（Vitest）

测试代码统一放在 `frontend/tests/`，文件名 `*.spec.ts`，**不要放进 `src/`**（`src/**` 由 `tsconfig.app.json` 纳入生产构建的类型检查）。

```
tests/
├── setup.ts            # 全局注册 Element Plus 与图标、ResizeObserver 兜底、用例间状态清理
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
- Element Plus 的弹层（popover / dialog）会 teleport 到 `document.body`，挂载时传 `attachTo: document.body` 并用 `document.body.querySelector` 查询。
- 弹层一定要给 `popper-class`（如 `notification-popper` / `user-popper`）：页面上同时有两个弹层时，`.el-popover` 这种选择器在 Playwright 严格模式下会因命中两处直接报错。
- 定时器轮询用 `vi.useFakeTimers()` + `vi.advanceTimersByTimeAsync()`，用例结束前 `vi.useRealTimers()`。

### 端到端测试（Playwright）

`frontend/e2e/`，由 `playwright.config.ts` 自动拉起 `localhost:4173` 的 dev server。`e2e/fixtures.ts` 里的 `mockApi(page, { signedIn, needsSetup })` 用带状态的假接口替换整个 `/api` 面，因此 **E2E 不需要启动后端**；注意路由要按 `url.pathname.startsWith('/api/')` 匹配，用 `**/api/**` 通配会把 Vite 的 `/src/api/*.ts` 模块请求一起拦掉导致白屏。

默认 `signedIn: true`：所有非 `/auth/*` 请求正常回数据。传 `signedIn: false` 时替身一律回 `401 {detail:'未认证'}`，登录流程、守卫跳转、401 拦截这些用例就是这么打的。

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

`app.use(ElementPlus)` 会引用全部组件、`import * as Icons` 会注册 293 个图标组件，两者都会让 tree-shaking 失效、入口 chunk 从 276 kB 涨回 769 kB。新增页面若用到列表外的组件，需要一并加入注册列表。

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

# 类型检查（含测试代码）
npm run build
npm run typecheck:test
```
