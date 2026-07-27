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
│   │   ├── client.ts      # Axios 实例
│   │   ├── videos.ts      # 视频 API
│   │   ├── sources.ts     # 视频源 API
│   │   ├── settings.ts    # 设置 API
│   │   └── ...
│   ├── components/         # 可复用组件
│   │   ├── VideoCard.vue
│   │   ├── VideoPlayer.vue
│   │   ├── SourceCard.vue
│   │   └── ...
│   ├── composables/        # 组合式函数
│   │   └── useTheme.ts    # 主题切换
│   ├── views/              # 页面组件
│   │   ├── Home.vue       # 首页/视频列表
│   │   ├── Sources.vue    # 视频源管理
│   │   ├── Tags.vue       # 标签管理
│   │   ├── Settings.vue   # 应用设置
│   │   └── ...
│   ├── layouts/            # 布局组件
│   │   └── MainLayout.vue
│   ├── router/             # 路由配置
│   │   └── index.ts
│   ├── types/              # TypeScript 类型
│   │   ├── video.ts
│   │   └── source.ts
│   ├── styles/             # 全局样式
│   │   ├── global.css
│   │   └── theme.css      # 深色模式样式
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

```css
:root {
  --primary-color: #409eff;
  --success-color: #67c23a;
  --warning-color: #e6a23c;
  --danger-color: #f56c6c;
}

.button {
  background-color: var(--primary-color);
}
```

### 深色模式

项目支持深色模式，通过 `data-theme="dark"` 属性切换：

```typescript
// 使用 useTheme composable
import { useTheme, setTheme } from '@/composables/useTheme'

const { theme } = useTheme()

// 切换主题
setTheme('dark')    // 深色模式
setTheme('light')   // 浅色模式
setTheme('auto')    // 跟随系统
```

深色模式样式定义在 `styles/theme.css` 中：

```css
/* 深色模式变量 */
:root[data-theme="dark"] {
  --bg-color: #1d1e1f;
  --bg-color-page: #0a0a0a;
  --text-color-primary: #e5eaf3;
  --text-color-regular: #cfd3dc;
  --border-color-lighter: #303133;
}

/* 深色模式下的组件样式 */
:root[data-theme="dark"] .el-card {
  background-color: var(--bg-color);
  border-color: var(--border-color-lighter);
}
```

**注意：** 布局组件（MainLayout）的深色模式需要使用全局样式（非 scoped），否则选择器无法生效。

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

```typescript
// src/api/client.ts
import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    // 添加 token 等
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 统一错误处理
    if (error.response?.status === 401) {
      // 处理未授权
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

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

### 组件测试

```typescript
// src/components/__tests__/VideoCard.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import VideoCard from '../VideoCard.vue'

describe('VideoCard', () => {
  it('renders video title', () => {
    const wrapper = mount(VideoCard, {
      props: {
        video: { id: 1, title: '测试视频' },
      },
    })
    expect(wrapper.text()).toContain('测试视频')
  })
})
```

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
// main.ts
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

app.use(ElementPlus)
```

## 构建和部署

```bash
# 开发
npm run dev

# 构建
npm run build

# 预览构建结果
npm run preview

# 代码检查
npm run lint

# 类型检查
npm run type-check
```
