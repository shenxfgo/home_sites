import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: { title: '首页' },
  },
  {
    path: '/sources',
    name: 'sources',
    component: () => import('@/views/Sources.vue'),
    meta: { title: '视频源' },
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/History.vue'),
    meta: { title: '播放历史' },
  },
  {
    path: '/favorites',
    name: 'favorites',
    component: () => import('@/views/Favorites.vue'),
    meta: { title: '收藏' },
  },
  {
    path: '/tags',
    name: 'tags',
    component: () => import('@/views/Tags.vue'),
    meta: { title: '标签管理' },
  },
  {
    path: '/videos/:id',
    name: 'video-detail',
    component: () => import('@/views/VideoDetail.vue'),
    meta: { title: '视频详情' },
  },
  {
    path: '/videos/:id/transcode',
    name: 'transcode',
    component: () => import('@/views/Transcode.vue'),
    meta: { title: '视频转码' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/Settings.vue'),
    meta: { title: '设置' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Update document title on navigation.
router.afterEach((to) => {
  document.title = `${to.meta.title ?? '首页'} - Home Sites`
})

export default router
