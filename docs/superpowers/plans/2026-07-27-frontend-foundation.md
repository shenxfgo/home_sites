# 前端基础框架与视频源管理页面实现计划

> **致 agentic 工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐步实施此计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 搭建前端基础框架，实现视频源管理页面，验证后端 Source API。

**架构：** Vue 3 单页应用，使用 Element Plus 组件库，Vue Router 路由管理，Axios HTTP 客户端。

**技术栈：** Vue 3 + TypeScript + Vite + Element Plus + Vue Router + Axios

## 全局约束

- Node.js 版本：18+
- 使用 npm 或 pnpm 进行依赖管理
- 遵循 Vue 3 Composition API 风格
- 所有组件使用 `<script setup>` 语法
- TypeScript 严格模式
- 响应式设计，支持桌面端和平板端
- API 请求使用 Axios，基础 URL 可配置
- 代码风格遵循 ESLint + Prettier

---

## 阶段一：项目初始化与基础配置

### 任务 1：创建 Vue 3 项目

**文件：**
- 创建：`frontend/` 目录及所有项目文件

**接口：**
- 依赖：Node.js 18+、npm/pnpm
- 产出：Vue 3 + TypeScript + Vite 项目结构

- [ ] **步骤 1：使用 Vite 创建 Vue 3 + TypeScript 项目**

```bash
cd /d/git_opensource_project/diy/home_sites
npm create vite@latest frontend -- --template vue-ts
```

- [ ] **步骤 2：安装核心依赖**

```bash
cd frontend
npm install vue-router@4 axios element-plus @element-plus/icons-vue
npm install -D @types/node
```

- [ ] **步骤 3：配置 vite.config.ts**

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **步骤 4：配置 tsconfig.json**

```json
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.vue"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **步骤 5：提交**

```bash
cd frontend
git add .
git commit -m "feat: initialize Vue 3 + TypeScript + Vite project"
```

---

## 阶段二：基础框架配置

### 任务 2：配置 Element Plus 和路由

**文件：**
- 创建：`frontend/src/main.ts`
- 创建：`frontend/src/App.vue`
- 创建：`frontend/src/router/index.ts`
- 创建：`frontend/src/layouts/MainLayout.vue`

**接口：**
- 依赖：Vue 3、Element Plus、Vue Router
- 产出：应用入口、路由配置、主布局

- [ ] **步骤 1：配置 main.ts**

```typescript
// frontend/src/main.ts
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import './styles/global.css'

const app = createApp(App)

// Register all Element Plus icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(ElementPlus)
app.use(router)
app.mount('#app')
```

- [ ] **步骤 2：创建全局样式**

```css
/* frontend/src/styles/global.css */
:root {
  --primary-color: #409eff;
  --success-color: #67c23a;
  --warning-color: #e6a23c;
  --danger-color: #f56c6c;
  --info-color: #909399;
}

body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background-color: #f5f7fa;
}

#app {
  height: 100vh;
}
```

- [ ] **步骤 3：创建路由配置**

```typescript
// frontend/src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'sources',
        name: 'Sources',
        component: () => import('@/views/Sources.vue'),
        meta: { title: '视频源管理' },
      },
      {
        path: 'videos/:id',
        name: 'VideoDetail',
        component: () => import('@/views/VideoDetail.vue'),
        meta: { title: '视频详情' },
      },
      {
        path: 'tags',
        name: 'Tags',
        component: () => import('@/views/Tags.vue'),
        meta: { title: '标签管理' },
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/History.vue'),
        meta: { title: '播放历史' },
      },
      {
        path: 'favorites',
        name: 'Favorites',
        component: () => import('@/views/Favorites.vue'),
        meta: { title: '收藏列表' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings.vue'),
        meta: { title: '设置' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || '视频管理平台'} - Video Platform`
  next()
})

export default router
```

- [ ] **步骤 4：创建主布局组件**

```vue
<!-- frontend/src/layouts/MainLayout.vue -->
<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <el-icon size="24"><VideoCamera /></el-icon>
        <span>视频管理平台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/sources">
          <el-icon><FolderOpened /></el-icon>
          <span>视频源管理</span>
        </el-menu-item>
        <el-menu-item index="/tags">
          <el-icon><PriceTag /></el-icon>
          <span>标签管理</span>
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><Clock /></el-icon>
          <span>播放历史</span>
        </el-menu-item>
        <el-menu-item index="/favorites">
          <el-icon><Star /></el-icon>
          <span>收藏列表</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentRoute.meta.title">
              {{ currentRoute.meta.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-badge :value="notificationCount" :hidden="notificationCount === 0" class="notification-badge">
            <el-button :icon="Bell" circle />
          </el-badge>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  VideoCamera,
  HomeFilled,
  FolderOpened,
  PriceTag,
  Clock,
  Star,
  Setting,
  Bell,
} from '@element-plus/icons-vue'

const route = useRoute()
const currentRoute = computed(() => route)
const activeMenu = computed(() => route.path)
const notificationCount = ref(0)
</script>

<style scoped>
.main-layout {
  height: 100vh;
}

.sidebar {
  background-color: #304156;
  color: #bfcbd9;
  overflow-y: auto;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 18px;
  font-weight: bold;
  color: #fff;
  border-bottom: 1px solid #3a4a5c;
}

.sidebar-menu {
  border-right: none;
  background-color: transparent;
}

.sidebar-menu .el-menu-item {
  color: #bfcbd9;
}

.sidebar-menu .el-menu-item:hover,
.sidebar-menu .el-menu-item.is-active {
  background-color: #263445;
  color: #409eff;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.header-left {
  display: flex;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.main-content {
  background-color: #f5f7fa;
  padding: 20px;
}
</style>
```

- [ ] **步骤 5：创建占位页面组件**

```vue
<!-- frontend/src/views/Home.vue -->
<template>
  <div class="home">
    <h1>欢迎使用视频管理平台</h1>
    <p>请先配置视频源，然后扫描视频。</p>
  </div>
</template>

<script setup lang="ts">
</script>
```

```vue
<!-- frontend/src/views/VideoDetail.vue -->
<template>
  <div>视频详情页面（待实现）</div>
</template>
```

```vue
<!-- frontend/src/views/Tags.vue -->
<template>
  <div>标签管理页面（待实现）</div>
</template>
```

```vue
<!-- frontend/src/views/History.vue -->
<template>
  <div>播放历史页面（待实现）</div>
</template>
```

```vue
<!-- frontend/src/views/Favorites.vue -->
<template>
  <div>收藏列表页面（待实现）</div>
</template>
```

```vue
<!-- frontend/src/views/Settings.vue -->
<template>
  <div>设置页面（待实现）</div>
</template>
```

- [ ] **步骤 6：提交**

```bash
cd frontend
git add src/main.ts src/App.vue src/router/ src/layouts/ src/views/ src/styles/
git commit -m "feat: configure Element Plus, router, and main layout"
```

---

## 阶段三：API 客户端配置

### 任务 3：创建 Axios 实例和 API 模块

**文件：**
- 创建：`frontend/src/api/client.ts`
- 创建：`frontend/src/api/sources.ts`
- 创建：`frontend/src/types/source.ts`

**接口：**
- 依赖：Axios
- 产出：API 客户端、视频源 API 模块、TypeScript 类型定义

- [ ] **步骤 1：创建 Axios 客户端**

```typescript
// frontend/src/api/client.ts
import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    // You can add auth tokens here if needed
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
apiClient.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    // Handle common errors
    if (error.response) {
      const { status, data } = error.response
      switch (status) {
        case 400:
          console.error('Bad Request:', data.detail)
          break
        case 404:
          console.error('Not Found:', data.detail)
          break
        case 422:
          console.error('Validation Error:', data.detail)
          break
        case 500:
          console.error('Server Error')
          break
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

- [ ] **步骤 2：创建 TypeScript 类型定义**

```typescript
// frontend/src/types/source.ts
export interface VideoSource {
  id: number
  name: string
  path: string
  type: 'local' | 'nas' | 'minio'
  scan_interval: number
  last_scan_at: string | null
  is_active: boolean
  created_at: string
}

export interface SourceCreateData {
  name: string
  path: string
  type: 'local' | 'nas' | 'minio'
  scan_interval?: number
  is_active?: boolean
}

export interface SourceUpdateData {
  name?: string
  path?: string
  type?: 'local' | 'nas' | 'minio'
  scan_interval?: number
  is_active?: boolean
}
```

- [ ] **步骤 3：创建视频源 API 模块**

```typescript
// frontend/src/api/sources.ts
import apiClient from './client'
import type { VideoSource, SourceCreateData, SourceUpdateData } from '@/types/source'

export const sourcesApi = {
  /**
   * 获取所有视频源
   */
  list(activeOnly: boolean = false): Promise<VideoSource[]> {
    return apiClient.get('/sources', { params: { active_only: activeOnly } }).then(res => res.data)
  },

  /**
   * 获取单个视频源
   */
  get(id: number): Promise<VideoSource> {
    return apiClient.get(`/sources/${id}`).then(res => res.data)
  },

  /**
   * 创建视频源
   */
  create(data: SourceCreateData): Promise<VideoSource> {
    return apiClient.post('/sources', data).then(res => res.data)
  },

  /**
   * 更新视频源
   */
  update(id: number, data: SourceUpdateData): Promise<VideoSource> {
    return apiClient.put(`/sources/${id}`, data).then(res => res.data)
  },

  /**
   * 删除视频源
   */
  delete(id: number): Promise<void> {
    return apiClient.delete(`/sources/${id}`)
  },
}
```

- [ ] **步骤 4：提交**

```bash
cd frontend
git add src/api/ src/types/
git commit -m "feat: add Axios client and sources API module"
```

---

## 阶段四：视频源管理页面

### 任务 4：实现视频源管理页面

**文件：**
- 创建：`frontend/src/views/Sources.vue`
- 创建：`frontend/src/components/SourceForm.vue`
- 创建：`frontend/src/components/SourceCard.vue`

**接口：**
- 依赖：Element Plus、sourcesApi
- 产出：视频源管理页面，包含列表、添加、编辑、删除功能

- [ ] **步骤 1：创建视频源表单组件**

```vue
<!-- frontend/src/components/SourceForm.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? '编辑视频源' : '添加视频源'"
    width="500px"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
    >
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入视频源名称" />
      </el-form-item>
      <el-form-item label="路径" prop="path">
        <el-input v-model="form.path" placeholder="请输入视频目录路径" />
      </el-form-item>
      <el-form-item label="类型" prop="type">
        <el-select v-model="form.type" placeholder="请选择类型">
          <el-option label="本地目录" value="local" />
          <el-option label="NAS" value="nas" />
          <el-option label="MinIO" value="minio" />
        </el-select>
      </el-form-item>
      <el-form-item label="扫描间隔" prop="scan_interval">
        <el-input-number
          v-model="form.scan_interval"
          :min="60"
          :max="86400"
          :step="60"
        />
        <span class="form-hint">秒（默认 3600）</span>
      </el-form-item>
      <el-form-item label="启用" prop="is_active">
        <el-switch v-model="form.is_active" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="loading">
        {{ isEdit ? '保存' : '添加' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { VideoSource, SourceCreateData } from '@/types/source'

interface Props {
  visible: boolean
  source?: VideoSource | null
}

const props = withDefaults(defineProps<Props>(), {
  source: null,
})

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'submit', data: SourceCreateData): void
}>()

const formRef = ref<FormInstance>()
const loading = ref(false)
const isEdit = ref(false)

const form = reactive<SourceCreateData>({
  name: '',
  path: '',
  type: 'local',
  scan_interval: 3600,
  is_active: true,
})

const rules: FormRules = {
  name: [
    { required: true, message: '请输入视频源名称', trigger: 'blur' },
    { min: 1, max: 255, message: '长度在 1 到 255 个字符', trigger: 'blur' },
  ],
  path: [
    { required: true, message: '请输入视频目录路径', trigger: 'blur' },
    { min: 1, max: 1024, message: '长度在 1 到 1024 个字符', trigger: 'blur' },
  ],
  type: [
    { required: true, message: '请选择类型', trigger: 'change' },
  ],
}

watch(
  () => props.source,
  (newSource) => {
    if (newSource) {
      isEdit.value = true
      form.name = newSource.name
      form.path = newSource.path
      form.type = newSource.type
      form.scan_interval = newSource.scan_interval
      form.is_active = newSource.is_active
    } else {
      isEdit.value = false
      resetForm()
    }
  },
  { immediate: true }
)

function resetForm() {
  form.name = ''
  form.path = ''
  form.type = 'local'
  form.scan_interval = 3600
  form.is_active = true
}

function handleClose() {
  emit('update:visible', false)
  resetForm()
}

async function handleSubmit() {
  if (!formRef.value) return

  await formRef.value.validate((valid) => {
    if (valid) {
      emit('submit', { ...form })
    }
  })
}
</script>

<style scoped>
.form-hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
</style>
```

- [ ] **步骤 2：创建视频源卡片组件**

```vue
<!-- frontend/src/components/SourceCard.vue -->
<template>
  <el-card class="source-card" :class="{ 'is-inactive': !source.is_active }">
    <template #header>
      <div class="card-header">
        <div class="card-title">
          <el-icon size="20">
            <FolderOpened v-if="source.type === 'local'" />
            <Platform v-else-if="source.type === 'nas'" />
            <Cloudy v-else />
          </el-icon>
          <span>{{ source.name }}</span>
        </div>
        <div class="card-actions">
          <el-switch
            v-model="source.is_active"
            @change="handleToggleActive"
            size="small"
          />
          <el-dropdown @command="handleCommand">
            <el-button :icon="MoreFilled" circle size="small" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">
                  <el-icon><Edit /></el-icon>
                  编辑
                </el-dropdown-item>
                <el-dropdown-item command="scan" :disabled="!source.is_active">
                  <el-icon><Refresh /></el-icon>
                  扫描
                </el-dropdown-item>
                <el-dropdown-item command="delete" divided>
                  <el-icon><Delete /></el-icon>
                  <span style="color: #f56c6c">删除</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </template>
    <div class="card-content">
      <div class="info-item">
        <span class="label">路径：</span>
        <el-tooltip :content="source.path" placement="top">
          <span class="value path">{{ source.path }}</span>
        </el-tooltip>
      </div>
      <div class="info-item">
        <span class="label">类型：</span>
        <el-tag size="small" :type="getTypeTag(source.type)">
          {{ getTypeLabel(source.type) }}
        </el-tag>
      </div>
      <div class="info-item">
        <span class="label">扫描间隔：</span>
        <span class="value">{{ formatInterval(source.scan_interval) }}</span>
      </div>
      <div class="info-item">
        <span class="label">上次扫描：</span>
        <span class="value">{{ source.last_scan_at ? formatDate(source.last_scan_at) : '从未' }}</span>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { FolderOpened, Platform, Cloudy, MoreFilled, Edit, Refresh, Delete } from '@element-plus/icons-vue'
import type { VideoSource } from '@/types/source'

interface Props {
  source: VideoSource
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'edit', source: VideoSource): void
  (e: 'delete', source: VideoSource): void
  (e: 'scan', source: VideoSource): void
  (e: 'toggle-active', source: VideoSource, active: boolean): void
}>()

function getTypeTag(type: string): '' | 'success' | 'warning' {
  const map: Record<string, '' | 'success' | 'warning'> = {
    local: '',
    nas: 'success',
    minio: 'warning',
  }
  return map[type] || ''
}

function getTypeLabel(type: string): string {
  const map: Record<string, string> = {
    local: '本地',
    nas: 'NAS',
    minio: 'MinIO',
  }
  return map[type] || type
}

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`
  return `${Math.floor(seconds / 3600)}小时`
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function handleCommand(command: string) {
  switch (command) {
    case 'edit':
      emit('edit', props.source)
      break
    case 'scan':
      emit('scan', props.source)
      break
    case 'delete':
      emit('delete', props.source)
      break
  }
}

function handleToggleActive(val: boolean) {
  emit('toggle-active', props.source, val)
}
</script>

<style scoped>
.source-card {
  margin-bottom: 16px;
}

.source-card.is-inactive {
  opacity: 0.7;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  align-items: center;
}

.label {
  color: #909399;
  font-size: 14px;
  min-width: 80px;
}

.value {
  font-size: 14px;
}

.value.path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 250px;
}
</style>
```

- [ ] **步骤 3：创建视频源管理页面**

```vue
<!-- frontend/src/views/Sources.vue -->
<template>
  <div class="sources-page">
    <div class="page-header">
      <h2>视频源管理</h2>
      <el-button type="primary" @click="showAddDialog">
        <el-icon><Plus /></el-icon>
        添加视频源
      </el-button>
    </div>

    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="sources.length === 0" class="empty-container">
      <el-empty description="暂无视频源">
        <el-button type="primary" @click="showAddDialog">添加视频源</el-button>
      </el-empty>
    </div>

    <div v-else class="sources-grid">
      <SourceCard
        v-for="source in sources"
        :key="source.id"
        :source="source"
        @edit="handleEdit"
        @delete="handleDelete"
        @scan="handleScan"
        @toggle-active="handleToggleActive"
      />
    </div>

    <SourceForm
      v-model:visible="formVisible"
      :source="currentSource"
      @submit="handleFormSubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import SourceCard from '@/components/SourceCard.vue'
import SourceForm from '@/components/SourceForm.vue'
import { sourcesApi } from '@/api/sources'
import type { VideoSource, SourceCreateData } from '@/types/source'

const sources = ref<VideoSource[]>([])
const loading = ref(false)
const formVisible = ref(false)
const currentSource = ref<VideoSource | null>(null)

onMounted(() => {
  fetchSources()
})

async function fetchSources() {
  loading.value = true
  try {
    sources.value = await sourcesApi.list()
  } catch (error) {
    ElMessage.error('获取视频源列表失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

function showAddDialog() {
  currentSource.value = null
  formVisible.value = true
}

function handleEdit(source: VideoSource) {
  currentSource.value = source
  formVisible.value = true
}

async function handleDelete(source: VideoSource) {
  try {
    await ElMessageBox.confirm(
      `确定要删除视频源 "${source.name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    await sourcesApi.delete(source.id)
    ElMessage.success('删除成功')
    fetchSources()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
      console.error(error)
    }
  }
}

async function handleScan(source: VideoSource) {
  try {
    // TODO: Implement scan API call
    ElMessage.info(`开始扫描 "${source.name}"...`)
  } catch (error) {
    ElMessage.error('扫描失败')
    console.error(error)
  }
}

async function handleToggleActive(source: VideoSource, active: boolean) {
  try {
    await sourcesApi.update(source.id, { is_active: active })
    ElMessage.success(active ? '已启用' : '已禁用')
  } catch (error) {
    ElMessage.error('更新失败')
    console.error(error)
    // Revert the change
    source.is_active = !active
  }
}

async function handleFormSubmit(data: SourceCreateData) {
  try {
    if (currentSource.value) {
      await sourcesApi.update(currentSource.value.id, data)
      ElMessage.success('更新成功')
    } else {
      await sourcesApi.create(data)
      ElMessage.success('添加成功')
    }
    formVisible.value = false
    fetchSources()
  } catch (error) {
    ElMessage.error(currentSource.value ? '更新失败' : '添加失败')
    console.error(error)
  }
}
</script>

<style scoped>
.sources-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #303133;
}

.loading-container {
  padding: 40px;
  background: #fff;
  border-radius: 8px;
}

.empty-container {
  padding: 60px 0;
  background: #fff;
  border-radius: 8px;
}

.sources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 16px;
}
</style>
```

- [ ] **步骤 4：提交**

```bash
cd frontend
git add src/components/ src/views/Sources.vue
git commit -m "feat: implement sources management page with CRUD"
```

---

## 阶段五：完善与测试

### 任务 5：完善应用入口和测试

**文件：**
- 修改：`frontend/src/App.vue`
- 创建：`frontend/.env.development`

**接口：**
- 依赖：所有前置任务
- 产出：完整可运行的前端应用

- [ ] **步骤 1：更新 App.vue**

```vue
<!-- frontend/src/App.vue -->
<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
/* Global styles are imported in main.ts */
</style>
```

- [ ] **步骤 2：创建环境配置**

```env
# frontend/.env.development
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_TITLE=视频管理平台 - 开发环境
```

- [ ] **步骤 3：更新 API 客户端使用环境变量**

```typescript
// frontend/src/api/client.ts
import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ... rest of the file remains the same
```

- [ ] **步骤 4：运行开发服务器测试**

```bash
cd frontend
npm run dev
```

- [ ] **步骤 5：提交**

```bash
cd frontend
git add .
git commit -m "feat: complete frontend foundation with sources management"
```

---

## 完成标准

1. ✅ Vue 3 + TypeScript + Vite 项目创建成功
2. ✅ Element Plus 集成并可使用
3. ✅ 路由配置完成，支持页面导航
4. ✅ 主布局组件完成，包含侧边栏和头部
5. ✅ Axios 客户端配置完成，支持 API 代理
6. ✅ 视频源管理页面完成，支持：
   - 列表展示
   - 添加视频源
   - 编辑视频源
   - 删除视频源
   - 启用/禁用视频源
7. ✅ 所有代码提交到 Git

---

## 后续任务

完成本计划后，可以继续实现：
1. 视频列表页面（需要 VideoService API）
2. 视频播放器（需要视频流 API）
3. 标签管理页面
4. 播放历史页面
5. 收藏列表页面
6. 通知中心组件
