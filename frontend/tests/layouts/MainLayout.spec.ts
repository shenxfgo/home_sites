import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Router } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { notificationsApi } from '@/api/notifications'

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

const stub = { template: '<div />' }

let router: Router

async function mountLayout() {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: stub },
      { path: '/history', name: 'history', component: stub },
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
    expect(wrapper.findAll('.nav-item')[0].classes()).toContain('active')

    await router.push('/history')
    await flushPromises()
    expect(wrapper.findAll('.nav-item')[2].classes()).toContain('active')
    wrapper.unmount()
  })
})
