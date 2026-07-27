import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: { title: 'Home' },
  },
  {
    path: '/sources',
    name: 'sources',
    component: () => import('@/views/Sources.vue'),
    meta: { title: 'Video Sources' },
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/History.vue'),
    meta: { title: 'History' },
  },
  {
    path: '/favorites',
    name: 'favorites',
    component: () => import('@/views/Favorites.vue'),
    meta: { title: 'Favorites' },
  },
  {
    path: '/videos/:id',
    name: 'video-detail',
    component: () => import('@/views/VideoDetail.vue'),
    meta: { title: 'Video Details' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/Settings.vue'),
    meta: { title: 'Settings' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Update document title on navigation.
router.afterEach((to) => {
  document.title = `${to.meta.title ?? 'Home'} - Home Sites`
})

export default router
