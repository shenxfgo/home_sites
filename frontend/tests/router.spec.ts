import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getAuthStatus, getMe } from '@/api/auth'
import { useAuth } from '@/composables/useAuth'
import router from '@/router'

vi.mock('@/api/auth', () => ({
  getAuthStatus: vi.fn(),
  getMe: vi.fn(),
}))

const OWNER = { id: 1, username: 'tester', role: 'owner' as const, display_name: 'Tester' }

/** 每次导航都重新探测：模块级登录态会跨用例留着。 */
async function signIn(user: typeof OWNER | null) {
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
