<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled,
  VideoCamera,
  Clock,
  Star,
  CollectionTag,
  Setting,
} from '@element-plus/icons-vue'
import NotificationCenter from '@/components/NotificationCenter.vue'

const router = useRouter()
const route = useRoute()

const navItems = [
  { path: '/', label: '首页', icon: HomeFilled },
  { path: '/sources', label: '视频源', icon: VideoCamera },
  { path: '/history', label: '播放历史', icon: Clock },
  { path: '/favorites', label: '收藏', icon: Star },
  { path: '/tags', label: '标签管理', icon: CollectionTag },
  { path: '/settings', label: '设置', icon: Setting },
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
        <NotificationCenter />
      </div>
    </header>

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
}

.layout-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
