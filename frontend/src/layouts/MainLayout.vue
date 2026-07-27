<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled,
  VideoCamera,
  Clock,
  Star,
  CollectionTag,
  Setting,
  Menu,
} from '@element-plus/icons-vue'
import NotificationCenter from '@/components/NotificationCenter.vue'

const router = useRouter()
const route = useRoute()
const isCollapse = ref(false)

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
  <el-container class="layout-container">
    <!-- Sidebar -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="layout-aside">
      <div class="logo-area">
        <span v-if="!isCollapse" class="logo-text">Home Sites</span>
        <span v-else class="logo-text-short">HS</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        class="layout-menu"
        @select="navigate"
      >
        <el-menu-item
          v-for="item in navItems"
          :key="item.path"
          :index="item.path"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- Main area -->
    <el-container class="layout-main-container">
      <el-header class="layout-header">
        <el-button
          :icon="Menu"
          text
          @click="isCollapse = !isCollapse"
        />
        <span class="header-title">{{ route.meta.title }}</span>
        <div class="header-spacer" />
        <NotificationCenter />
      </el-header>

      <el-main class="layout-main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style>
/* 使用全局样式以支持深色模式 */
.layout-container {
  height: 100vh;
}

.layout-aside {
  background-color: var(--aside-bg, var(--el-menu-bg-color));
  border-right: 1px solid var(--el-border-color-lighter);
  transition: width 0.3s;
  overflow: hidden;
}

.logo-area {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
  white-space: nowrap;
}

.logo-text-short {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.layout-menu {
  border-right: none;
}

.layout-main-container {
  display: flex;
  flex-direction: column;
}

.layout-header {
  display: flex;
  align-items: center;
  height: 60px;
  padding: 0 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background-color: var(--header-bg, var(--el-bg-color));
}

.header-title {
  font-size: 16px;
  font-weight: 500;
  margin-left: 8px;
  color: var(--el-text-color-primary);
}

.header-spacer {
  flex: 1;
}

.layout-main {
  flex: 1;
  background-color: var(--main-bg, var(--el-bg-color-page));
  overflow-y: auto;
}

/* 深色模式 */
:root[data-theme="dark"] .layout-aside {
  --aside-bg: #1d1e1f;
}

:root[data-theme="dark"] .layout-header {
  --header-bg: #1d1e1f;
}

:root[data-theme="dark"] .layout-main {
  --main-bg: #0a0a0a;
}
</style>
