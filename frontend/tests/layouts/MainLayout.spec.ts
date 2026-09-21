import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Router } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { notificationsApi } from '@/api/notifications'
import { getAuthStatus, getMe, logout } from '@/api/auth'
import { useAuth } from '@/composables/useAuth'
import { domButtonByText } from '../helpers'

vi.mock('@/api/auth', () => ({
  getAuthStatus: vi.fn(),
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
}))

vi.mock('@/api/notifications', () => ({
  notificationsApi: {
    list: vi.fn(),
    getUnreadCount: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    remove: vi.fn(),
    clearAll: vi.fn(),
  },
}))

// 有会话时 useAuth 会去拉这个人的主题；别让真实请求混进用例。
vi.mock('@/api/preferences', () => ({
  getPreferences: vi.fn().mockResolvedValue({ theme: 'light' }),
  updatePreferences: vi.fn().mockResolvedValue({ theme: 'light' }),
}))

const stub = { template: '<div />' }

const OWNER = { id: 1, username: 'tester', role: 'owner' as const, display_name: 'Tester' }
const MEMBER = { id: 2, username: 'kid', role: 'member' as const, display_name: '小明' }

let router: Router

/** Labels of the nav entries actually rendered for the current role. */
function navLabels(wrapper: VueWrapper): string[] {
  return wrapper.findAll('.nav-item').map((node) => node.text())
}

/** The nav button showing that label; which buttons exist at all depends on the role. */
function navItem(wrapper: VueWrapper, label: string) {
  const found = navLabels(wrapper).findIndex((text) => text.includes(label))
  if (found < 0) throw new Error(`顶栏没有 "${label}" 这一项，只有：${navLabels(wrapper).join('、')}`)
  return wrapper.findAll('.nav-item')[found]
}

async function mountLayout() {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: stub },
      { path: '/history', name: 'history', component: stub },
      { path: '/settings', name: 'settings', component: stub },
      { path: '/users', name: 'users', component: stub },
      { path: '/profile', name: 'profile', component: stub },
      { path: '/login', name: 'login', component: stub },
    ],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(MainLayout, {
    global: { plugins: [router] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

/** Text of the teleported dialog, or null while it is closed. */
function dialogText(): string | null {
  const dialog = document.body.querySelector('.el-dialog')
  return dialog ? (dialog.textContent ?? '') : null
}

async function press(key: string, target: Element | Document = document.body) {
  target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
  await flushPromises()
}

describe('MainLayout shortcut help', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(notificationsApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
    vi.mocked(notificationsApi.getUnreadCount).mockResolvedValue(0)
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('opens the list on the question mark key', async () => {
    const wrapper = await mountLayout()
    expect(dialogText()).toBeNull()

    await press('?')

    expect(dialogText()).toContain('快捷键')
    expect(dialogText()).toContain('跳到首页搜索框')
    expect(dialogText()).toContain('播放 / 暂停')
    wrapper.unmount()
  })

  it('opens the same list from the nav button', async () => {
    const wrapper = await mountLayout()

    await wrapper.find('.shortcut-help-btn').trigger('click')

    expect(dialogText()).toContain('后退 / 前进 5 秒')
    wrapper.unmount()
  })

  it('leaves the question mark to the field being typed in', async () => {
    const wrapper = await mountLayout()
    const field = document.createElement('input')
    document.body.appendChild(field)

    field.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true }))
    await flushPromises()

    expect(dialogText()).toBeNull()
    field.remove()
    wrapper.unmount()
  })

  it('highlights the nav entry that owns the current route', async () => {
    const wrapper = await mountLayout()

    await router.push('/')
    await flushPromises()
    expect(navItem(wrapper, '首页').classes()).toContain('active')

    await router.push('/history')
    await flushPromises()
    expect(navItem(wrapper, '播放历史').classes()).toContain('active')
    expect(navItem(wrapper, '首页').classes()).not.toContain('active')
    wrapper.unmount()
  })
})

describe('MainLayout account menu', () => {
  beforeEach(async () => {
    document.body.innerHTML = ''
    vi.mocked(notificationsApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
    vi.mocked(notificationsApi.getUnreadCount).mockResolvedValue(0)
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: true, needs_setup: false })
    vi.mocked(getMe).mockResolvedValue(OWNER)
    vi.mocked(logout).mockResolvedValue(undefined)
    await useAuth().load(true)
  })

  afterEach(() => {
    document.body.innerHTML = ''
    useAuth().forget()
  })

  it('shows who is signed in', async () => {
    const wrapper = await mountLayout()

    expect(wrapper.get('.user-name').text()).toBe('Tester')
    expect(wrapper.get('.user-avatar').text()).toBe('T')
    wrapper.unmount()
  })

  it('ends the session and hands over to the login page', async () => {
    const wrapper = await mountLayout()
    await wrapper.get('.user-chip').trigger('click')
    await flushPromises()

    domButtonByText(document.body, '退出登录')?.click()
    await flushPromises()

    expect(logout).toHaveBeenCalledTimes(1)
    // 退出是一段 async 链（请求 -> 清态 -> 导航），等它自己走完而不是猜帧数。
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    wrapper.unmount()
  })

  it('opens 个人设置 from the account menu', async () => {
    const wrapper = await mountLayout()
    await wrapper.get('.user-chip').trigger('click')
    await flushPromises()

    domButtonByText(document.body, '个人设置')?.click()
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('profile'))

    wrapper.unmount()
  })

  it('shows 用户管理 to an owner and hides it from a member', async () => {
    const wrapper = await mountLayout()
    await wrapper.get('.user-chip').trigger('click')
    await flushPromises()
    expect(domButtonByText(document.body, '用户管理')).toBeDefined()
    wrapper.unmount()
    document.body.innerHTML = '' // 上一个人的弹层可能还挂在 body 上

    vi.mocked(getMe).mockResolvedValue(MEMBER)
    await useAuth().load(true)
    const memberView = await mountLayout()
    await memberView.get('.user-chip').trigger('click')
    await flushPromises()
    expect(domButtonByText(document.body, '用户管理')).toBeUndefined()
    expect(domButtonByText(document.body, '个人设置')).toBeDefined()
    memberView.unmount()
  })
})

describe('MainLayout nav entries', () => {
  beforeEach(async () => {
    document.body.innerHTML = ''
    vi.mocked(notificationsApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
    vi.mocked(notificationsApi.getUnreadCount).mockResolvedValue(0)
    vi.mocked(getAuthStatus).mockResolvedValue({ authenticated: true, needs_setup: false })
    vi.mocked(logout).mockResolvedValue(undefined)
  })

  afterEach(() => {
    document.body.innerHTML = ''
    useAuth().forget()
  })

  it('gives an owner the management entries', async () => {
    vi.mocked(getMe).mockResolvedValue(OWNER)
    await useAuth().load(true)

    const wrapper = await mountLayout()

    expect(navLabels(wrapper)).toEqual(
      expect.arrayContaining(['首页', '视频源', '标签管理', '设置', '片单']),
    )
    wrapper.unmount()
  })

  it('keeps 视频源, 标签管理 and 设置 out of a member\'s top bar', async () => {
    vi.mocked(getMe).mockResolvedValue(MEMBER)
    await useAuth().load(true)

    const wrapper = await mountLayout()
    const labels = navLabels(wrapper)

    expect(labels).toEqual(expect.arrayContaining(['首页', '播放历史', '收藏', '片单']))
    expect(labels).not.toContain('视频源')
    expect(labels).not.toContain('标签管理')
    expect(labels).not.toContain('设置')
    wrapper.unmount()
  })
})
