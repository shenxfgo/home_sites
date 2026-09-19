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
    remove: vi.fn(),
    clearAll: vi.fn(),
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

  it('deletes one notification without touching the others', async () => {
    vi.mocked(notificationsApi.remove).mockResolvedValue(undefined)
    const wrapper = await mountOpened(
      [notification({ id: 1, title: '扫描完成' }), notification({ id: 2, title: '转码完成' })],
      2,
    )
    const unreadBefore = vi.mocked(notificationsApi.getUnreadCount).mock.calls.length

    popper()
      ?.querySelector<HTMLElement>('.notification-item .notification-remove')
      ?.click()
    await flushPromises()

    expect(notificationsApi.remove).toHaveBeenCalledWith(1)
    const items = popper()?.querySelectorAll('.notification-item') ?? []
    expect(items).toHaveLength(1)
    expect(items[0]?.textContent).toContain('转码完成')
    expect(vi.mocked(notificationsApi.getUnreadCount).mock.calls.length).toBe(unreadBefore + 1)
    wrapper.unmount()
  })

  it('clears the list only after a second click on 清空', async () => {
    vi.mocked(notificationsApi.clearAll).mockResolvedValue(undefined)
    const wrapper = await mountOpened([notification({ id: 1 })], 1)

    const clear = () =>
      Array.from(popper()?.querySelectorAll('button') ?? []).find((node) =>
        node.textContent?.includes('清空') || node.textContent?.includes('确认清空'),
      )

    clear()?.click()
    await flushPromises()
    expect(notificationsApi.clearAll).not.toHaveBeenCalled()
    expect(clear()?.textContent).toContain('确认清空')

    clear()?.click()
    await flushPromises()
    expect(notificationsApi.clearAll).toHaveBeenCalledTimes(1)
    expect(popper()?.textContent).toContain('暂无通知')
    expect(wrapper.find('.el-badge__content').exists()).toBe(false)
    wrapper.unmount()
  })

  it('lets the 清空 confirmation lapse', async () => {
    vi.useFakeTimers()
    vi.mocked(notificationsApi.clearAll).mockResolvedValue(undefined)
    await mountOpened([notification({ id: 1 })], 1)

    const clear = () =>
      Array.from(popper()?.querySelectorAll('button') ?? []).find((node) =>
        node.textContent?.includes('清空'),
      )

    clear()?.click()
    await vi.advanceTimersByTimeAsync(4100)

    expect(clear()?.textContent).toBe('清空')
    expect(notificationsApi.clearAll).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('keeps 清空 out of the header when there is nothing to clear', async () => {
    const wrapper = await mountOpened([], 0)

    const labels = Array.from(popper()?.querySelectorAll('button') ?? []).map((node) =>
      node.textContent?.trim(),
    )
    expect(labels).not.toContain('清空')
    wrapper.unmount()
  })
})
