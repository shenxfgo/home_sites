import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getAuthStatus, getMe } from '@/api/auth'
import { useAuth } from '@/composables/useAuth'
import router from '@/router'
import type { AuthUser } from '@/types/auth'

vi.mock('@/api/auth', () => ({
  getAuthStatus: vi.fn(),
  getMe: vi.fn(),
}))

// 会话一旦确立就会去拉主题，这里挡掉真实请求。
vi.mock('@/api/preferences', () => ({
  getPreferences: vi.fn().mockResolvedValue({ theme: 'light' }),
  updatePreferences: vi.fn().mockResolvedValue({ theme: 'light' }),
}))

const OWNER = { id: 1, username: 'tester', role: 'owner' as const, display_name: 'Tester' }
const MEMBER = { id: 2, username: 'kid', role: 'member' as const, display_name: '小明' }

/** 每次导航都重新探测：模块级登录态会跨用例留着。 */
async function signIn(user: AuthUser | null) {
  vi.mocked(getAuthStatus).mockResolvedValue({
    authenticated: user !== null,
    needs_setup: user === null,
  })
  vi.mocked(getMe).mockResolvedValue(user ?? OWNER)
  useAuth().forget()
}

describe('router', () => {
  beforeEach(async () => {
    await signIn(OWNER)
    await router.replace('/')
  })

  it('exposes the main navigation routes', () => {
    const names = router.getRoutes().map((route) => route.name).filter(Boolean)

    expect(names).toEqual(
      expect.arrayContaining([
        'login',
        'home',
        'sources',
        'history',
        'stats',
        'favorites',
        'watchlists',
        'tags',
        'settings',
        'users',
        'profile',
      ]),
    )
  })

  it('sends unknown paths to the 404 page instead of rendering nothing', async () => {
    await router.push('/definitely/not/a/page')

    expect(router.currentRoute.value.name).toBe('not-found')
    expect(router.currentRoute.value.params.pathMatch).toEqual(['definitely', 'not', 'a', 'page'])
  })

  it('keeps the video detail and transcode routes addressable by id', () => {
    expect(router.resolve('/videos/12').name).toBe('video-detail')
    expect(router.resolve('/videos/12/transcode').name).toBe('transcode')
    expect(router.resolve('/videos/12/transcode').params.id).toBe('12')
  })

  it('writes the route title into the document title', async () => {
    await router.push('/history')

    expect(document.title).toBe('播放历史 - Home Sites')
  })

  it('brings an anonymous visitor to the login page with a way back', async () => {
    await signIn(null)

    await router.push('/sources?tab=all')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/sources?tab=all')
  })

  it('lets a signed-in user straight through', async () => {
    await router.push('/settings')

    expect(router.currentRoute.value.name).toBe('settings')
    expect(getAuthStatus).toHaveBeenCalledTimes(1) // 探测过一次就缓存了
  })

  it('does not offer the login page to someone already signed in', async () => {
    await router.push('/login')

    expect(router.currentRoute.value.name).toBe('home')
  })
})

describe('router role gate', () => {
  beforeEach(async () => {
    useAuth().forget()
    await router.replace('/')
  })

  it('walks a member back out of every management page', async () => {
    await signIn(MEMBER)

    for (const path of ['/sources', '/tags', '/settings', '/users', '/videos/12/transcode']) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe('home')
      await router.push('/')
    }
  })

  it('leaves the watching pages and 个人设置 open to a member', async () => {
    await signIn(MEMBER)

    for (const [path, name] of [
      ['/history', 'history'],
      ['/favorites', 'favorites'],
      ['/watchlists', 'watchlists'],
      ['/profile', 'profile'],
      ['/videos/21', 'video-detail'],
    ]) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe(name)
      await router.push('/')
    }
  })

  it('lets the owner into 用户管理', async () => {
    await signIn(OWNER)

    await router.push('/users')

    expect(router.currentRoute.value.name).toBe('users')
  })
})
