import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import History from '@/views/History.vue'
import { deleteHistory, getContinueList, listHistory } from '@/api/history'
import type { HistoryItem } from '@/api/history'
import { makeVideo } from '../factories'
import { buttonByText, CONFIRMED } from '../helpers'

const push = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push, back: vi.fn() }),
}))

vi.mock('@/api/history', () => ({
  listHistory: vi.fn(),
  getContinueList: vi.fn(),
  deleteHistory: vi.fn(),
}))

function item(overrides: Partial<HistoryItem> = {}): HistoryItem {
  return {
    id: 1,
    video_id: 4,
    played_at: '2026-09-18T08:00:00',
    progress: 12,
    completed: false,
    video_title: '深夜测试',
    ...overrides,
  }
}

/** 每页 20 条是这两个视图自己的默认值，夹具按它排，不去动页大小选项。 */
const PAGE_SIZE = 20

async function mountHistory(items: HistoryItem[], continueVideos: ReturnType<typeof makeVideo>[] = []) {
  vi.mocked(listHistory).mockResolvedValue({ items, total: items.length, page: 1, page_size: 20 })
  vi.mocked(getContinueList).mockResolvedValue(continueVideos)
  const wrapper = mount(History)
  await flushPromises()
  return wrapper
}

describe('History view', () => {
  beforeEach(() => {
    vi.mocked(deleteHistory).mockResolvedValue(undefined)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('shows the video title returned by the backend', async () => {
    const wrapper = await mountHistory([item()])

    expect(wrapper.text()).toContain('深夜测试')
    expect(wrapper.text()).not.toContain('视频 #4')
    wrapper.unmount()
  })

  it('falls back to the video id when the record has no title', async () => {
    const wrapper = await mountHistory([item({ video_id: 9, video_title: null })])

    expect(wrapper.text()).toContain('视频 #9')
    wrapper.unmount()
  })

  it('marks finished records separately from ones still playing', async () => {
    const wrapper = await mountHistory([item({ id: 1, completed: true }), item({ id: 2, completed: false })])

    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('未看完')
    wrapper.unmount()
  })

  it('hides the continue watching section when there is nothing to resume', async () => {
    const wrapper = await mountHistory([item()], [])

    expect(wrapper.text()).not.toContain('继续观看')
    wrapper.unmount()
  })

  it('lists resumable videos with their thumbnails', async () => {
    const wrapper = await mountHistory([item()], [makeVideo({ id: 21, title: '未看完的片子' })])

    expect(wrapper.text()).toContain('继续观看')
    expect(wrapper.text()).toContain('未看完的片子')
    expect(wrapper.find('.continue-card img').attributes('src')).toBe('/api/videos/21/thumbnail')
    wrapper.unmount()
  })

  it('opens the video page when a history row is clicked', async () => {
    const wrapper = await mountHistory([item({ video_id: 4 })])

    await wrapper.find('.video-link').trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'video-detail', params: { id: 4 } })
    wrapper.unmount()
  })

  it('deletes a record after confirmation and reloads the list', async () => {
    const wrapper = await mountHistory([item({ id: 7 })])

    const deleteButton = wrapper.findAll('button').find((node) => node.text().includes('删除'))
    expect(deleteButton).toBeDefined()
    await deleteButton?.trigger('click')
    await flushPromises()

    expect(deleteHistory).toHaveBeenCalledWith(7)
    expect(listHistory).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('shows the empty state when nothing has been watched', async () => {
    const wrapper = await mountHistory([])

    expect(wrapper.text()).toContain('暂无观看历史')
    wrapper.unmount()
  })

  /**
   * 一页一页可服务的历史：`serve` 按 page/page_size 切片，`remove` 真的删掉那一行。
   * 默认的 `mountHistory` 把 `total` 写死成 `items.length`，那种夹具翻不出"页码越界"
   * 这件事——它永远只有第 1 页。
   */
  async function mountPaged(count: number) {
    const rows = Array.from({ length: count }, (_, i) => item({ id: i + 1, video_id: i + 1 }))
    vi.mocked(listHistory).mockImplementation((page = 1, pageSize = PAGE_SIZE) => {
      const start = (page - 1) * pageSize
      return Promise.resolve({
        items: rows.slice(start, start + pageSize),
        total: rows.length,
        page,
        page_size: pageSize,
      })
    })
    vi.mocked(deleteHistory).mockImplementation(async (id: number) => {
      rows.splice(rows.findIndex((row) => row.id === id), 1)
    })
    vi.mocked(getContinueList).mockResolvedValue([])
    const wrapper = mount(History)
    await flushPromises()
    return wrapper
  }

  /** 分页条上那个数字是唯一的换页入口，所以它本身也是被测的一环。 */
  async function gotoPage(wrapper: ReturnType<typeof mount>, page: number) {
    const pager = wrapper.findAll('.el-pager li').find((node) => node.text() === String(page))
    if (!pager) throw new Error(`分页条上没有第 ${page} 页可以点`)
    await pager.trigger('click')
    await flushPromises()
    expect(vi.mocked(listHistory)).toHaveBeenLastCalledWith(page, PAGE_SIZE)
  }

  /**
   * 删掉最后一页仅剩的那一条：`total` 正好落到 `pageSize`，页码却还停在第 2 页。后端
   * 照实回空的一页，前端于是同屏渲染「暂无观看历史。」和分页条上那句「共 20 条记录」，
   * 而分页条自己的条件 `total > pageSize` 此刻不成立、整个消失——只剩刷新一条出路。
   * 和 #113 在 `Home.vue` 上踩过的是同一件事，触发方式换成页面上那颗「删除」。
   */
  it('clamps back to a page that still exists when the last record on the last page is deleted', async () => {
    const wrapper = await mountPaged(21)

    await gotoPage(wrapper, 2)
    await buttonByText(wrapper, '删除').trigger('click')
    await flushPromises()

    // 第 1 页、第 2 页、删完又读第 2 页（那页此刻是空的），然后钳回第 1 页。
    expect(vi.mocked(listHistory).mock.calls.map(([page]) => page)).toEqual([1, 2, 2, 1])
    expect(wrapper.text()).not.toContain('暂无观看历史')
    wrapper.unmount()
  })

  it('keeps the user on the same page when that page still has records left', async () => {
    const wrapper = await mountPaged(45)

    await gotoPage(wrapper, 3) // 第 3 页只有 5 条
    await buttonByText(wrapper, '删除').trigger('click')
    await flushPromises()

    // 这一条挡的是"顺手回第 1 页"那种改法：用户的阅读位置不是 bug。
    expect(vi.mocked(listHistory).mock.calls.map(([page]) => page)).toEqual([1, 3, 3])
    wrapper.unmount()
  })
})
