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
    <!-- 顶部玻璃导航栏 -->
    <header class="top-nav glass-panel">
      <div class="logo-area gradient-text" @click="navigate('/')">Home Sites</div>

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
  top: 12px;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 24px;
  margin: 12px 16px 0;
  padding: 0 20px;
  height: 58px;
  border-radius: 999px;
}

.logo-area {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 0.5px;
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
  padding: 8px 16px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-glass);
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.22s ease;
}

.nav-item:hover {
  background: rgba(124, 108, 255, 0.12);
  transform: translateY(-1px);
}

.nav-item.active {
  background: var(--grad-primary);
  color: #fff;
  box-shadow: 0 4px 14px rgba(124, 108, 255, 0.4);
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
