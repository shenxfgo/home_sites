import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import VideoDetail from '@/views/VideoDetail.vue'
import { getVideo } from '@/api/videos'
import { addTagsToVideo, listTags, removeTagFromVideo } from '@/api/tags'
import { checkFavorite } from '@/api/favorites'
import {
  addVideoToWatchlist,
  createWatchlist,
  listWatchlists,
  removeVideoFromWatchlist,
} from '@/api/watchlists'
import type { Watchlist } from '@/api/watchlists'
import type { Tag } from '@/types/video'
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

// 详情页上有一排只有管理员能按的按钮，所以用例也要能换人。
const signedInAs = vi.hoisted(() => ({ role: 'owner' as 'owner' | 'member' }))
vi.mock('@/composables/useAuth', async () => {
  const { computed } = await import('vue')
  return {
    useAuth: () => ({ isOwner: computed(() => signedInAs.role === 'owner') }),
  }
})

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

async function mountDetail(
  role: 'owner' | 'member' = 'owner',
  seed: { tags?: Tag[]; catalog?: Tag[] } = {},
) {
  signedInAs.role = role
  vi.mocked(getVideo).mockResolvedValue(
    makeVideo({ id: 21, title: '午夜列车', tags: seed.tags ?? [] }),
  )
  vi.mocked(checkFavorite).mockResolvedValue(false)
  vi.mocked(listTags).mockResolvedValue(seed.catalog ?? [])
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

/** 库里两条可选标签，这部片只挂了第一条——预勾选和差分都要能看出差别。 */
const ACTION: Tag = { id: 1, name: '动作片', color: '#7c6cff' }
const DOC: Tag = { id: 2, name: '纪录片', color: '#f56c6c' }

function tagDialog(): Element | null {
  return Array.from(document.body.querySelectorAll('.el-dialog')).find((node) =>
    node.textContent?.includes('编辑标签'),
  ) ?? null
}

/**
 * 对话框此刻是否开着。`el-dialog` 关掉后 Element Plus 只是把外层 overlay 设成
 * `display: none`，节点还留在 body 里，所以只查 `tagDialog()` 存在与否会永远为真。
 */
function tagDialogOpen(): boolean {
  const overlay = Array.from(document.body.querySelectorAll('.el-overlay')).find((node) =>
    node.textContent?.includes('编辑标签'),
  )
  return Boolean(overlay && (overlay as HTMLElement).style.display !== 'none')
}

function tagCheckboxFor(name: string) {
  const row = Array.from(tagDialog()?.querySelectorAll('.tag-checkbox-item') ?? []).find((node) =>
    node.textContent?.includes(name),
  )
  return row?.querySelector('.el-checkbox') ?? null
}

async function openTagDialog(wrapper: Awaited<ReturnType<typeof mountDetail>>) {
  const trigger = wrapper.find('.tags-list button')
  if (!trigger.exists()) throw new Error('详情页没有挂标签的加号按钮')
  await trigger.trigger('click')
  await flushPromises()
}

/** 一次点一项：同步连点两项会让复选框组读到过期的 model。 */
async function toggleTag(name: string) {
  const box = tagCheckboxFor(name)?.querySelector('input')
  if (!box) throw new Error(`标签弹窗里没有 "${name}" 这一项`)
  box.click()
  await flushPromises()
}

async function clickInTagDialog(label: string) {
  const found = Array.from(tagDialog()?.querySelectorAll('button') ?? []).find((node) =>
    node.textContent?.includes(label),
  )
  if (!found) throw new Error(`编辑标签弹窗里没有 "${label}" 按钮`)
  found.click()
  await flushPromises()
}

/**
 * 标签对话框这一节只管**请求内容**：多挂一次、摘一次本来没挂的，替身夹具都照常回 204
 * （#132 补的那份状态就是这样设计的，和后端一致），所以浏览器层看不出「发多了」——
 * 只有把 api 模块 mock 掉的这一层能量到。反过来，「存下来没有」只有 e2e 能证，
 * 见 `e2e/video-tags.spec.ts`。
 */
describe('VideoDetail tag dialog', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.mocked(addTagsToVideo).mockReset().mockResolvedValue(undefined)
    vi.mocked(removeTagFromVideo).mockReset().mockResolvedValue(undefined)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('opens with the title’s own tag ticked and the other clear', async () => {
    const wrapper = await mountDetail('owner', { tags: [ACTION], catalog: [ACTION, DOC] })

    await openTagDialog(wrapper)

    expect(tagCheckboxFor('动作片')?.classList.contains('is-checked')).toBe(true)
    expect(tagCheckboxFor('纪录片')?.classList.contains('is-checked')).toBe(false)
    wrapper.unmount()
  })

  it('posts only the newly ticked id and deletes only the unticked one', async () => {
    const wrapper = await mountDetail('owner', { tags: [ACTION], catalog: [ACTION, DOC] })
    await openTagDialog(wrapper)

    await toggleTag('纪录片')
    await toggleTag('动作片')
    await clickInTagDialog('保存')

    // 勾选项是 {纪录片}，当前项是 {动作片}：发出去的必须是差集，不是勾选的全集。
    expect(addTagsToVideo).toHaveBeenCalledTimes(1)
    expect(addTagsToVideo).toHaveBeenCalledWith(21, [2])
    expect(removeTagFromVideo).toHaveBeenCalledTimes(1)
    expect(removeTagFromVideo).toHaveBeenCalledWith(21, 1)
    wrapper.unmount()
  })

  it('sends no write at all when the ticks were not touched', async () => {
    const wrapper = await mountDetail('owner', { tags: [ACTION], catalog: [ACTION, DOC] })
    await openTagDialog(wrapper)

    await clickInTagDialog('保存')

    expect(addTagsToVideo).not.toHaveBeenCalled()
    expect(removeTagFromVideo).not.toHaveBeenCalled()
    expect(tagDialogOpen()).toBe(false)
    wrapper.unmount()
  })

  it('quotes the server when the write fails and leaves the dialog open', async () => {
    vi.mocked(addTagsToVideo).mockRejectedValue(new Error('标签不存在'))
    const wrapper = await mountDetail('owner', { tags: [], catalog: [ACTION, DOC] })
    await openTagDialog(wrapper)

    await toggleTag('动作片')
    await clickInTagDialog('保存')

    // 和 #74/#75、#129 那一类同一个理由：服务端的原因不能被一句「Failed」盖掉。
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('标签不存在'))
    // 写没成，人还得回去改，所以对话框不能自己关掉。
    expect(tagDialogOpen()).toBe(true)
    wrapper.unmount()
  })
})

/** Labels on the action row: which buttons one particular role is handed. */
function actionLabels(wrapper: Awaited<ReturnType<typeof mountDetail>>) {
  return wrapper.findAll('.action-buttons button').map((node) => node.text().trim())
}

describe('VideoDetail role gate', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('gives the owner the whole library surface', async () => {
    const wrapper = await mountDetail()

    expect(actionLabels(wrapper)).toEqual(
      expect.arrayContaining(['播放', '收藏', '片单', '转码', '编辑', '删除']),
    )
    expect(wrapper.findAll('.tags-list button')).toHaveLength(1)
    wrapper.unmount()
  })

  it('leaves a member only the row they can actually use', async () => {
    const wrapper = await mountDetail('member')

    // 改信息、删片、转码都在中间件的成员禁写名单里，点了只会拿 403，这里就不摆出来
    expect(actionLabels(wrapper)).toEqual(['播放', '收藏', '片单'])
    expect(wrapper.find('.tags-list button').exists()).toBe(false)
    wrapper.unmount()
  })
})
