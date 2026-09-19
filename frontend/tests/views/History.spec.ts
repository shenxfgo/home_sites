import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import History from '@/views/History.vue'
import { deleteHistory, getContinueList, listHistory } from '@/api/history'
import type { HistoryItem } from '@/api/history'
import { makeVideo } from '../factories'
import { CONFIRMED } from '../helpers'

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
})
