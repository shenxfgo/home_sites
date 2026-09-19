<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled,
  VideoCamera,
  Clock,
  TrendCharts,
  Star,
  CollectionTag,
  Setting,
} from '@element-plus/icons-vue'
import NotificationCenter from '@/components/NotificationCenter.vue'
import { isTypingTarget } from '@/composables/typingGuard'

const router = useRouter()
const route = useRoute()

const navItems = [
  { path: '/', label: '首页', icon: HomeFilled },
  { path: '/sources', label: '视频源', icon: VideoCamera },
  { path: '/history', label: '播放历史', icon: Clock },
  { path: '/stats', label: '观影统计', icon: TrendCharts },
  { path: '/favorites', label: '收藏', icon: Star },
  { path: '/tags', label: '标签管理', icon: CollectionTag },
  { path: '/settings', label: '设置', icon: Setting },
]

const shortcutsVisible = ref(false)

const shortcutGroups = [
  {
    title: '全站',
    items: [
      { keys: ['/'], desc: '跳到首页搜索框' },
      { keys: ['?'], desc: '打开这份快捷键清单' },
      { keys: ['Esc'], desc: '关闭对话框与菜单' },
    ],
  },
  {
    title: '播放器',
    items: [
      { keys: ['空格', 'K'], desc: '播放 / 暂停' },
      { keys: ['←', '→'], desc: '后退 / 前进 5 秒' },
      { keys: ['↑', '↓'], desc: '音量，之后会记住' },
      { keys: ['M'], desc: '静音' },
      { keys: ['F'], desc: '全屏' },
    ],
  },
]

const activeMenu = computed(() => {
  const match = navItems.find((item) => {
    if (item.path === '/') return route.path === '/'
    return route.path.startsWith(item.path)
  })
  return match?.path ?? '/'
})

function navigate(path: string) {
  router.push(path)
}

// "?" lists the shortcuts; typing it into a field must not steal the key.
function handleGlobalKeydown(e: KeyboardEvent) {
  if (e.key !== '?' || e.metaKey || e.ctrlKey || e.altKey) return
  if (isTypingTarget(e.target)) return
  e.preventDefault()
  shortcutsVisible.value = !shortcutsVisible.value
}

onMounted(() => document.addEventListener('keydown', handleGlobalKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleGlobalKeydown))
</script>

<template>
  <div class="layout-root">
    <!-- 顶部导航栏 -->
    <header class="top-nav">
      <div class="logo-area accent-text" @click="navigate('/')">Home Sites</div>

      <nav class="nav-menu">
        <button
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: activeMenu === item.path }"
          @click="navigate(item.path)"
        >
          <el-icon :size="15"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="nav-right">
        <el-button text class="shortcut-help-btn" title="快捷键（按 ? 也可打开）" @click="shortcutsVisible = true">
          快捷键
        </el-button>
        <NotificationCenter />
      </div>
    </header>

    <!-- 快捷键清单 -->
    <el-dialog v-model="shortcutsVisible" title="快捷键" width="420px">
      <section v-for="group in shortcutGroups" :key="group.title" class="shortcut-group">
        <h3 class="shortcut-group-title">{{ group.title }}</h3>
        <div v-for="item in group.items" :key="item.desc" class="shortcut-row">
          <span class="shortcut-keys">
            <kbd v-for="key in item.keys" :key="key">{{ key }}</kbd>
          </span>
          <span class="shortcut-desc">{{ item.desc }}</span>
        </div>
      </section>
    </el-dialog>

    <!-- 内容区 -->
    <main class="layout-main">
      <router-view v-slot="{ Component }">
        <transition name="pop" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.layout-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.top-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 24px;
  height: 56px;
  background: var(--surface-bg);
  border-bottom: 1px solid var(--glass-border);
}

.logo-area {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.2px;
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
}

.nav-menu {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  overflow-x: auto;
  scrollbar-width: none;
}

.nav-menu::-webkit-scrollbar {
  display: none;
}

.nav-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: none;
  border-radius: var(--radius-tile);
  background: transparent;
  color: var(--text-glass-secondary);
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.nav-item:hover {
  background: var(--tile-bg);
  color: var(--text-glass);
}

.nav-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.shortcut-help-btn {
  color: var(--text-glass-secondary);
}

.shortcut-help-btn:hover {
  color: var(--accent);
}

.shortcut-group + .shortcut-group {
  margin-top: 16px;
}

.shortcut-group-title {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: var(--text-glass-secondary);
}

.shortcut-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
  font-size: 13px;
  color: var(--text-glass);
}

.shortcut-keys {
  display: flex;
  gap: 4px;
  min-width: 78px;
}

.shortcut-keys kbd {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--glass-border);
  background: var(--tile-bg);
  color: var(--text-glass);
}

.layout-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
