import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Router } from 'vue-router'
import Login from '@/views/Login.vue'
import { getAuthStatus, login } from '@/api/auth'
import { useAuth } from '@/composables/useAuth'

vi.mock('@/api/auth', () => ({
  getAuthStatus: vi.fn(),
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}))

// 登录成功后会去拉这个人的主题；别让真实请求留在用例里。
vi.mock('@/api/preferences', () => ({
  getPreferences: vi.fn().mockResolvedValue({ theme: 'light' }),
  updatePreferences: vi.fn().mockResolvedValue({ theme: 'light' }),
}))

const OWNER = { id: 1, username: 'tester', role: 'owner' as const, display_name: 'Tester' }
const stub = { template: '<div />' }

async function makeRouter(initial: string): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: Login, meta: { public: true } },
      { path: '/', name: 'home', component: stub },
      { path: '/sources', name: 'sources', component: stub },
    ],
  })
  await router.push(initial)
  await router.isReady()
  return router
}

async function mountLogin(initial = '/login') {
  const router = await makeRouter(initial)
  const wrapper = mount(Login, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('Login view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuth().forget()
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: false, needs_setup: false })
    vi.mocked(login).mockResolvedValue(OWNER)
  })

  it('sends the trimmed account name and lands on the page the visitor asked for', async () => {
    const { wrapper, router } = await mountLogin('/login?redirect=/sources')

    await wrapper.get('#login-username').setValue('  Tester ')
    await wrapper.get('#login-password').setValue('secret-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(login).toHaveBeenCalledWith('Tester', 'secret-pass', false)
    expect(router.currentRoute.value.path).toBe('/sources')
  })

  it('passes 记住我 through to the session length', async () => {
    const { wrapper } = await mountLogin()

    await wrapper.get('#login-username').setValue('tester')
    await wrapper.get('#login-password').setValue('secret-pass')
    await wrapper.get('.remember input').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(login).toHaveBeenCalledWith('tester', 'secret-pass', true)
  })

  it('shows the backend reason and clears the password on a bad attempt', async () => {
    vi.mocked(login).mockRejectedValue(new Error('账号或密码错误'))

    const { wrapper, router } = await mountLogin()
    await wrapper.get('#login-username').setValue('tester')
    await wrapper.get('#login-password').setValue('wrong-one')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('.error').text()).toBe('账号或密码错误')
    expect((wrapper.get('#login-password').element as HTMLInputElement).value).toBe('')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('tells an empty library how to make its first account', async () => {
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: false, needs_setup: true })

    const { wrapper } = await mountLogin()

    expect(wrapper.get('.notice').text()).toContain('create-user')
  })

  it('ignores a redirect that points at another host', async () => {
    const { wrapper, router } = await mountLogin('/login?redirect=//evil.example.com')

    await wrapper.get('#login-username').setValue('tester')
    await wrapper.get('#login-password').setValue('secret-pass')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/')
  })
})
