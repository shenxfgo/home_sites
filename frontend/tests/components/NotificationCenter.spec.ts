import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import NotificationCenter from '@/components/NotificationCenter.vue'
import { notificationsApi } from '@/api/notifications'
import type { Notification } from '@/api/notifications'

vi.mock('@/api/notifications', () => ({
  notificationsApi: {
    list: vi.fn(),
    getUnreadCount: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}))

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 1,
    type: 'scan_complete',
    title: '扫描完成',
    message: '发现 3 个新视频',
    data: null,
    read: false,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

async function mountOpened(items: Notification[], unread: number) {
  vi.mocked(notificationsApi.list).mockResolvedValue({ items, total: items.length, page: 1, page_size: 50 })
  vi.mocked(notificationsApi.getUnreadCount).mockResolvedValue(unread)
  const wrapper = mount(NotificationCenter, { attachTo: document.body })
  await flushPromises()
  await wrapper.find('.notification-badge button').trigger('click')
  await flushPromises()
  return wrapper
}

function popper(): HTMLElement | null {
  return document.body.querySelector('.el-popover')
}

describe('NotificationCenter', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(notificationsApi.markRead).mockResolvedValue(undefined)
    vi.mocked(notificationsApi.markAllRead).mockResolvedValue(undefined)
  })

  it('shows how many notifications are still unread', async () => {
    const wrapper = await mountOpened([notification()], 4)

    expect(wrapper.find('.el-badge__content').text()).toBe('4')
    wrapper.unmount()
  })

  it('hides the badge once everything is read', async () => {
    const wrapper = await mountOpened([], 0)

    expect(wrapper.find('.el-badge__content').exists()).toBe(false)
    wrapper.unmount()
  })

  it('lists notifications in the popover', async () => {
    await mountOpened([notification({ title: '转码完成' })], 1)

    expect(popper()?.textContent).toContain('转码完成')
    expect(popper()?.textContent).toContain('发现 3 个新视频')
  })

  it('marks a single notification as read when clicked', async () => {
    await mountOpened([notification({ id: 12 })], 2)

    const item = popper()?.querySelector<HTMLElement>('.notification-item')
    item?.click()
    await flushPromises()

    expect(notificationsApi.markRead).toHaveBeenCalledWith(12)
    expect(popper()?.querySelector('.el-badge__content')).toBeNull()
  })

  it('decrements the badge after reading one notification', async () => {
    const wrapper = await mountOpened([notification({ id: 12 })], 2)

    popper()?.querySelector<HTMLElement>('.notification-item')?.click()
    await flushPromises()

    expect(wrapper.find('.el-badge__content').text()).toBe('1')
    wrapper.unmount()
  })

  it('marks every notification read in one call', async () => {
    const wrapper = await mountOpened([notification({ id: 1 }), notification({ id: 2 })], 2)

    const markAll = Array.from(popper()?.querySelectorAll('button') ?? []).find((node) =>
      node.textContent?.includes('全部已读'),
    )
    markAll?.click()
    await flushPromises()

    expect(notificationsApi.markAllRead).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.el-badge__content').exists()).toBe(false)
    wrapper.unmount()
  })

  it('says so when there are no notifications yet', async () => {
    await mountOpened([], 3)

    expect(popper()?.textContent).toContain('暂无通知')
  })
})
