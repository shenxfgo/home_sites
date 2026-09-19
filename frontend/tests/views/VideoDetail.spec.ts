import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import VideoDetail from '@/views/VideoDetail.vue'
import { getVideo } from '@/api/videos'
import { listTags } from '@/api/tags'
import { checkFavorite } from '@/api/favorites'
import {
  addVideoToWatchlist,
  createWatchlist,
  listWatchlists,
  removeVideoFromWatchlist,
} from '@/api/watchlists'
import type { Watchlist } from '@/api/watchlists'
import { makeVideo } from '../factories'

const push = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '21' } }),
  useRouter: () => ({ push }),
}))

vi.mock('@/api/videos', () => ({
  getVideo: vi.fn(),
  updateVideo: vi.fn(),
  deleteVideo: vi.fn(),
  thumbnailUrl: vi.fn(() => '/api/videos/21/thumbnail'),
}))

vi.mock('@/api/favorites', () => ({
  checkFavorite: vi.fn(),
  addFavorite: vi.fn(),
  removeFavorite: vi.fn(),
}))

vi.mock('@/api/tags', () => ({
  listTags: vi.fn(),
  addTagsToVideo: vi.fn(),
  removeTagFromVideo: vi.fn(),
}))

vi.mock('@/api/watchlists', () => ({
  listWatchlists: vi.fn(),
  createWatchlist: vi.fn(),
  addVideoToWatchlist: vi.fn(),
  removeVideoFromWatchlist: vi.fn(),
}))

function watchlist(overrides: Partial<Watchlist> = {}): Watchlist {
  return {
    id: 1,
    name: '今晚看这些',
    description: null,
    created_at: '2026-09-18T08:00:00',
    items: [makeVideo({ id: 21, title: '午夜列车' })],
    ...overrides,
  }
}

async function mountDetail() {
  vi.mocked(getVideo).mockResolvedValue(makeVideo({ id: 21, title: '午夜列车', tags: [] }))
  vi.mocked(checkFavorite).mockResolvedValue(false)
  vi.mocked(listTags).mockResolvedValue([])
  const wrapper = mount(VideoDetail, {
    attachTo: document.body,
    global: { stubs: { VideoPlayer: true } },
  })
  await flushPromises()
  return wrapper
}

function dialog(): Element | null {
  return Array.from(document.body.querySelectorAll('.el-dialog')).find((node) =>
    node.textContent?.includes('加入片单'),
  ) ?? null
}

async function clickInDialog(label: string) {
  const found = Array.from(dialog()?.querySelectorAll('button') ?? []).find((node) =>
    node.textContent?.includes(label),
  )
  if (!found) throw new Error(`加入片单弹窗里没有 "${label}" 按钮`)
  found.click()
  await flushPromises()
}

async function openWatchlistDialog(wrapper: Awaited<ReturnType<typeof mountDetail>>) {
  const trigger = wrapper.findAll('button').find((node) => node.text().includes('片单'))
  if (!trigger) throw new Error('详情页没有片单按钮')
  await trigger.trigger('click')
  await flushPromises()
}

/** The checkbox for one queue, and whether it is ticked. */
function checkboxFor(listName: string) {
  const row = Array.from(dialog()?.querySelectorAll('.watchlist-checkbox-item') ?? []).find(
    (node) => node.textContent?.includes(listName),
  )
  return row?.querySelector('.el-checkbox') ?? null
}

/** One toggle per tick: two synchronous clicks share a stale group model. */
async function toggle(listName: string) {
  const box = checkboxFor(listName)?.querySelector('input')
  if (!box) throw new Error(`弹窗里没有 "${listName}" 这一项`)
  box.click()
  await flushPromises()
}

describe('VideoDetail watchlist dialog', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(addVideoToWatchlist).mockResolvedValue(watchlist())
    vi.mocked(removeVideoFromWatchlist).mockResolvedValue(watchlist({ items: [] }))
    vi.mocked(createWatchlist).mockResolvedValue(watchlist({ id: 9, name: '周末电影', items: [] }))
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('opens with the queues already holding this title ticked', async () => {
    vi.mocked(listWatchlists).mockResolvedValue([
      watchlist(),
      watchlist({ id: 2, name: '空着的', items: [] }),
    ])
    const wrapper = await mountDetail()

    await openWatchlistDialog(wrapper)

    expect(dialog()?.textContent).toContain('今晚看这些')
    expect(dialog()?.textContent).toContain('1 部')
    expect(checkboxFor('今晚看这些')?.classList.contains('is-checked')).toBe(true)
    expect(checkboxFor('空着的')?.classList.contains('is-checked')).toBe(false)
    wrapper.unmount()
  })

  it('adds and removes only the queues the ticks changed in', async () => {
    vi.mocked(listWatchlists).mockResolvedValue([
      watchlist(),
      watchlist({ id: 2, name: '空着的', items: [] }),
    ])
    const wrapper = await mountDetail()
    await openWatchlistDialog(wrapper)

    await toggle('今晚看这些')
    await toggle('空着的')
    await clickInDialog('保存')

    expect(addVideoToWatchlist).toHaveBeenCalledWith(2, 21)
    expect(removeVideoFromWatchlist).toHaveBeenCalledWith(1, 21)
    expect(ElMessage.success).toHaveBeenCalledWith('片单已更新')
    wrapper.unmount()
  })

  it('starts a new queue from the dialog and puts this title in it', async () => {
    vi.mocked(listWatchlists).mockResolvedValue([])
    const wrapper = await mountDetail()
    await openWatchlistDialog(wrapper)

    expect(dialog()?.textContent).toContain('还没有片单')
    const field = dialog()?.querySelector('.watchlist-new input') as HTMLInputElement | null
    if (!field) throw new Error('弹窗里没有新建片单的输入框')
    field.value = '周末电影'
    field.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    await clickInDialog('保存')

    expect(createWatchlist).toHaveBeenCalledWith('周末电影')
    expect(addVideoToWatchlist).toHaveBeenCalledWith(9, 21)
    wrapper.unmount()
  })

  it('reports a failed load without opening the dialog', async () => {
    vi.mocked(listWatchlists).mockRejectedValue(new Error('服务未就绪'))
    const wrapper = await mountDetail()

    await openWatchlistDialog(wrapper)

    expect(ElMessage.error).toHaveBeenCalledWith('片单加载失败：服务未就绪')
    expect(dialog()).toBeNull()
    wrapper.unmount()
  })
})
