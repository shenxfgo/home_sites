import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getAuthStatus, getMe, login, logout } from '@/api/auth'
import { getPreferences } from '@/api/preferences'
import { getTheme } from '@/composables/useTheme'
import { useAuth } from '@/composables/useAuth'

vi.mock('@/api/auth', () => ({
  getAuthStatus: vi.fn(),
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}))

// 登录后会顺带拉这个人的主题；挡住请求，只关心"有没有拉、拉不到时登不登得上"。
vi.mock('@/api/preferences', () => ({
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
}))

const OWNER = { id: 1, username: 'tester', role: 'owner' as const, display_name: 'Tester' }

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth().forget()
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: true, needs_setup: false })
    vi.mocked(getMe).mockResolvedValue(OWNER)
    vi.mocked(login).mockResolvedValue(OWNER)
    vi.mocked(logout).mockResolvedValue(undefined)
    vi.mocked(getPreferences).mockResolvedValue({ theme: 'light' })
  })

  it('restores the signed-in user once and caches it', async () => {
    const auth = useAuth()

    expect(await auth.load()).toEqual(OWNER)
    expect(await auth.load()).toEqual(OWNER)

    expect(getAuthStatus).toHaveBeenCalledTimes(1)
    expect(auth.isAuthenticated.value).toBe(true)
    expect(auth.isOwner.value).toBe(true)
  })

  it('re-probes when asked to, which is how a refresh picks up a new session', async () => {
    const auth = useAuth()
    await auth.load()

    await auth.load(true)

    expect(getAuthStatus).toHaveBeenCalledTimes(2)
  })

  it('leaves the user empty but reads the setup flag when there is no session', async () => {
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: false, needs_setup: true })
    const auth = useAuth()

    expect(await auth.load()).toBeNull()

    expect(getMe).not.toHaveBeenCalled()
    expect(auth.needsSetup.value).toBe(true)
    expect(auth.isAuthenticated.value).toBe(false)
  })

  it('keeps the user it just signed in without probing again', async () => {
    const auth = useAuth()

    expect(await auth.signIn('tester', 'secret-pass', true)).toEqual(OWNER)

    expect(login).toHaveBeenCalledWith('tester', 'secret-pass', true)
    expect(getAuthStatus).not.toHaveBeenCalled()
    expect(auth.isAuthenticated.value).toBe(true)
  })

  it('forgets the session on sign-out and drops the cached state', async () => {
    const auth = useAuth()
    await auth.load()

    await auth.signOut()

    expect(logout).toHaveBeenCalledTimes(1)
    expect(auth.user.value).toBeNull()
    await auth.load()
    expect(getAuthStatus).toHaveBeenCalledTimes(2)
  })

  it('treats a 401 as no session at all, so the next guard re-probes', async () => {
    const auth = useAuth()
    await auth.load()

    auth.forget()

    expect(auth.user.value).toBeNull()
    expect(auth.loaded.value).toBe(false)
  })

  it('pulls the account theme in once a session is known', async () => {
    vi.mocked(getPreferences).mockResolvedValue({ theme: 'dark' })

    await useAuth().load(true)

    await vi.waitFor(() => expect(getTheme()).toBe('dark'))
  })

  it('does not ask for preferences without a session', async () => {
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: false, needs_setup: false })

    await useAuth().load(true)

    expect(getPreferences).not.toHaveBeenCalled()
  })

  it('signs in even when the theme cannot be fetched', async () => {
    vi.mocked(getPreferences).mockRejectedValue(new Error('网络不可用'))
    const auth = useAuth()

    expect(await auth.signIn('tester', 'secret-pass')).toEqual(OWNER)
    // 主题那条支路失败就失败，不该把登录一起拖倒
    await vi.waitFor(() => expect(getPreferences).toHaveBeenCalledTimes(1))
    expect(auth.isAuthenticated.value).toBe(true)
  })
})
