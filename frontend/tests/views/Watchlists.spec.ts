import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import Watchlists from '@/views/Watchlists.vue'
import {
  createWatchlist,
  deleteWatchlist,
  listWatchlists,
  removeVideoFromWatchlist,
  updateWatchlist,
} from '@/api/watchlists'
import type { Watchlist } from '@/api/watchlists'
import { makeVideo } from '../factories'
import { CONFIRMED } from '../helpers'

const push = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/api/watchlists', () => ({
  listWatchlists: vi.fn(),
  createWatchlist: vi.fn(),
  updateWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  addVideoToWatchlist: vi.fn(),
  removeVideoFromWatchlist: vi.fn(),
}))

function watchlist(overrides: Partial<Watchlist> = {}): Watchlist {
  return {
    id: 1,
    name: '今晚看这些',
    description: null,
    created_at: '2026-09-18T08:00:00',
    items: [
      makeVideo({ id: 21, title: '午夜列车', duration: 1500, progress: null }),
      makeVideo({ id: 22, title: '极地科考', duration: 3000, progress: null }),
    ],
    ...overrides,
  }
}

async function mountPage(lists: Watchlist[]) {
  vi.mocked(listWatchlists).mockResolvedValue(lists)
  // The form dialog teleports to body, which only works once the page is attached.
  const wrapper = mount(Watchlists, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

/** The teleported dialog holds the form; the wrapper cannot see it. */
function dialog(): Element | null {
  return document.body.querySelector('.el-dialog')
}

function nameField(): HTMLInputElement {
  const field = dialog()?.querySelector('input')
  if (!field) throw new Error('片单表单没有渲染出来')
  return field as HTMLInputElement
}

async function typeInName(value: string) {
  const field = nameField()
  field.value = value
  field.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}

function dialogButton(label: string): HTMLButtonElement {
  const found = Array.from(dialog()?.querySelectorAll('button') ?? []).find((node) =>
    node.textContent?.includes(label),
  )
  if (!found) throw new Error(`弹窗里没有文案包含 "${label}" 的按钮`)
  return found as HTMLButtonElement
}

async function pageButton(wrapper: Awaited<ReturnType<typeof mountPage>>, label: string) {
  const found = wrapper.findAll('button').find((node) => node.text().includes(label))
  if (!found) throw new Error(`页面里没有文案包含 "${label}" 的按钮`)
  await found.trigger('click')
  await flushPromises()
}

describe('Watchlists view', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(deleteWatchlist).mockResolvedValue(undefined)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
  })

  it('queues titles in the order the backend sent them', async () => {
    const wrapper = await mountPage([watchlist()])

    expect(wrapper.findAll('.queue-title').map((node) => node.text())).toEqual([
      '午夜列车',
      '极地科考',
    ])
    expect(wrapper.findAll('.queue-index').map((node) => node.text())).toEqual(['1', '2'])
    expect(wrapper.text()).toContain('1 个片单 · 2 条排队')
    wrapper.unmount()
  })

  it('adds up the length of a queue', async () => {
    const wrapper = await mountPage([watchlist()])

    // 1500 + 3000 秒
    expect(wrapper.find('.list-meta').text()).toContain('2 部 · 共 1:15:00')
    wrapper.unmount()
  })

  it('marks how far a queued title has been watched', async () => {
    const wrapper = await mountPage([
      watchlist({ items: [makeVideo({ id: 21, title: '午夜列车', duration: 1500, progress: 600 })] }),
    ])

    expect(wrapper.find('.queue-meta').text()).toContain('25:00')
    expect(wrapper.find('.queue-meta').text()).toContain('已看 10:00')
    wrapper.unmount()
  })

  it('opens the title page from a queue row', async () => {
    const wrapper = await mountPage([watchlist()])

    await wrapper.findAll('.queue-main')[1].trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'video-detail', params: { id: 22 } })
    wrapper.unmount()
  })

  it('takes a title out of the queue without dropping it from the library', async () => {
    const wrapper = await mountPage([watchlist()])
    vi.mocked(removeVideoFromWatchlist).mockResolvedValue(
      watchlist({ items: [makeVideo({ id: 21, title: '午夜列车', duration: 1500 })] }),
    )

    await pageButton(wrapper, '移出')

    expect(removeVideoFromWatchlist).toHaveBeenCalledWith(1, 21)
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('影片仍在库里'))
    expect(wrapper.findAll('.queue-item')).toHaveLength(1)
    expect(wrapper.text()).toContain('1 个片单 · 1 条排队')
    wrapper.unmount()
  })

  it('points an empty queue at the video detail page', async () => {
    const wrapper = await mountPage([watchlist({ items: [] })])

    expect(wrapper.find('.queue-empty').text()).toContain('去影片详情页点「加入片单」')
    wrapper.unmount()
  })

  it('keeps the list when the delete is cancelled', async () => {
    const wrapper = await mountPage([watchlist()])
    vi.mocked(ElMessageBox.confirm).mockRejectedValue(new Error('cancel'))

    await pageButton(wrapper, '删除片单')

    expect(deleteWatchlist).not.toHaveBeenCalled()
    expect(wrapper.findAll('.list-panel')).toHaveLength(1)
    wrapper.unmount()
  })

  it('deletes only the queue, and says so before asking', async () => {
    const wrapper = await mountPage([watchlist()])

    await pageButton(wrapper, '删除片单')

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('影片本身不会被动'),
      '确认删除',
      expect.anything(),
    )
    expect(deleteWatchlist).toHaveBeenCalledWith(1)
    expect(wrapper.findAll('.list-panel')).toHaveLength(0)
    wrapper.unmount()
  })

  it('creates a list from the dialog', async () => {
    const wrapper = await mountPage([])
    vi.mocked(createWatchlist).mockResolvedValue(watchlist({ name: '周末电影', items: [] }))

    await pageButton(wrapper, '新建片单')
    expect(dialog()?.textContent).toContain('新建片单')
    await typeInName('周末电影')
    dialogButton('保存').click()
    await flushPromises()

    expect(createWatchlist).toHaveBeenCalledWith('周末电影', '')
    expect(wrapper.text()).toContain('周末电影')
    wrapper.unmount()
  })

  it('refuses a nameless list', async () => {
    const wrapper = await mountPage([])

    await pageButton(wrapper, '新建片单')
    dialogButton('保存').click()
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledWith('片单要有个名字')
    expect(createWatchlist).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('renames a list and keeps its note', async () => {
    const wrapper = await mountPage([watchlist({ description: '留到周日' })])
    vi.mocked(updateWatchlist).mockResolvedValue(
      watchlist({ name: '周末电影', description: '留到周日' }),
    )

    await pageButton(wrapper, '重命名')
    expect(nameField().value).toBe('今晚看这些')
    await typeInName('周末电影')
    dialogButton('保存').click()
    await flushPromises()

    expect(updateWatchlist).toHaveBeenCalledWith(1, {
      name: '周末电影',
      description: '留到周日',
    })
    expect(wrapper.find('.list-name').text()).toBe('周末电影')
    expect(wrapper.find('.list-desc').text()).toBe('留到周日')
    wrapper.unmount()
  })

  it('shows the empty state when no list exists yet', async () => {
    const wrapper = await mountPage([])

    expect(wrapper.text()).toContain('还没有片单')
    wrapper.unmount()
  })

  it('reports a failed load', async () => {
    vi.mocked(listWatchlists).mockRejectedValue(new Error('服务未就绪'))
    const wrapper = mount(Watchlists)
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('加载片单失败：服务未就绪')
    wrapper.unmount()
  })
})
