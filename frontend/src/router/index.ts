import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { setUnauthorizedHandler } from '@/api/client'
import { useAuth } from '@/composables/useAuth'
import type { UserRole } from '@/types/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** 登录页这类裸页：不套顶栏，也不需要会话。 */
    public?: boolean
    /** 谁能进这一页；省略表示所有登录用户。 */
    roles?: UserRole[]
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true },
  },
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
    meta: { title: '视频源', roles: ['owner'] },
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/History.vue'),
    meta: { title: '播放历史' },
  },
  {
    path: '/stats',
    name: 'stats',
    component: () => import('@/views/Stats.vue'),
    meta: { title: '观影统计' },
  },
  {
    path: '/favorites',
    name: 'favorites',
    component: () => import('@/views/Favorites.vue'),
    meta: { title: '收藏' },
  },
  {
    path: '/watchlists',
    name: 'watchlists',
    component: () => import('@/views/Watchlists.vue'),
    meta: { title: '片单' },
  },
  {
    path: '/tags',
    name: 'tags',
    component: () => import('@/views/Tags.vue'),
    meta: { title: '标签管理', roles: ['owner'] },
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
    meta: { title: '视频转码', roles: ['owner'] },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/Settings.vue'),
    meta: { title: '设置', roles: ['owner'] },
  },
  {
    path: '/users',
    name: 'users',
    component: () => import('@/views/Users.vue'),
    meta: { title: '用户管理', roles: ['owner'] },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/Profile.vue'),
    meta: { title: '个人设置' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFound.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const { load, forget, isAuthenticated, user } = useAuth()

// 会话过期只在这一处处理：业务代码收到的仍然是普通报错，不需要各自判断 401。
setUnauthorizedHandler(() => {
  forget()
  const from = router.currentRoute.value
  if (!from.meta.public) {
    void router.replace({ name: 'login', query: { redirect: from.fullPath } })
  }
})

// 除登录页外一律要求会话；/api 那边默认拒绝，这里只是让人先看登录页而不是满屏报错。
router.beforeEach(async (to) => {
  if (to.meta.public) {
    const signedIn = await load().catch(() => null)
    return to.name === 'login' && signedIn ? { path: '/' } : true
  }
  if (!isAuthenticated.value) await load().catch(() => null)
  if (!isAuthenticated.value) return { name: 'login', query: { redirect: to.fullPath } }
  // 管理页对成员直接送回首页：顶栏本来就不给他显示这些入口，撞上的都是手敲地址。
  // 真正的拒绝在服务端（同一请求会拿 403），这里只是不让人看见一个空壳页面。
  const allowed = to.meta.roles
  if (allowed && !allowed.includes(user.value!.role)) return { path: '/' }
  return true
})

// Update document title on navigation.
router.afterEach((to) => {
  document.title = `${to.meta.title ?? '首页'} - Home Sites`
})

export default router
