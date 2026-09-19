import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import Stats from '@/views/Stats.vue'
import { getWatchStats } from '@/api/history'
import type { WatchStats } from '@/api/history'

vi.mock('@/api/history', () => ({
  getWatchStats: vi.fn(),
}))

function stats(overrides: Partial<WatchStats> = {}): WatchStats {
  return {
    days: 30,
    window_seconds: 9000,
    month_seconds: 5400,
    videos_watched: 6,
    active_days: 3,
    longest_streak_days: 2,
    daily: [
      { date: '2026-09-16', seconds: 0, videos: 0 },
      { date: '2026-09-17', seconds: 4500, videos: 2 },
      { date: '2026-09-18', seconds: 4500, videos: 4 },
    ],
    tags: [
      { name: '悬疑', color: '#7c6cff', seconds: 6000 },
      { name: '剧集', color: '#f5a623', seconds: 1500 },
    ],
    ...overrides,
  }
}

async function mountStats(payload: WatchStats) {
  vi.mocked(getWatchStats).mockResolvedValue(payload)
  const wrapper = mount(Stats)
  await flushPromises()
  return wrapper
}

describe('Stats view', () => {
  beforeEach(() => {
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('shows the hours the user came for', async () => {
    const wrapper = await mountStats(stats())

    expect(wrapper.find('.stat-card').text()).toContain('1.5 小时')
    expect(wrapper.text()).toContain('本月观看')
    expect(wrapper.text()).toContain('6 部')
    expect(wrapper.text()).toContain('2 天')
    expect(getWatchStats).toHaveBeenCalledWith(30)
    wrapper.unmount()
  })

  it('keeps a day under an hour readable in minutes', async () => {
    const wrapper = await mountStats(
      stats({ month_seconds: 90, window_seconds: 90 }),
    )

    expect(wrapper.find('.stat-card').text()).toContain('2 分钟')
    wrapper.unmount()
  })

  it('draws one bar per day with the busiest day at full height', async () => {
    const wrapper = await mountStats(stats())
    const bars = wrapper.findAll('.bar')

    expect(bars).toHaveLength(3)
    expect(bars[0].attributes('style')).toContain('height: 2%')
    expect(bars[1].attributes('style')).toContain('height: 100%')
    expect(bars[2].attributes('style')).toContain('height: 100%')
    wrapper.unmount()
  })

  it('labels the chart with the first and last day of the window', async () => {
    const wrapper = await mountStats(stats())

    expect(wrapper.find('.chart-axis').text()).toBe('9月16日9月18日')
    wrapper.unmount()
  })

  it('scales each tag against the biggest one and paints it in its colour', async () => {
    const wrapper = await mountStats(stats())
    const rows = wrapper.findAll('.tag-row')

    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('悬疑')
    expect(rows[0].find('.tag-fill').attributes('style')).toContain('width: 100%')
    expect(rows[0].find('.tag-fill').attributes('style')).toContain('rgb(124, 108, 255)')
    expect(rows[1].find('.tag-fill').attributes('style')).toContain('width: 25%')
    expect(rows[1].text()).toContain('25 分钟')
    wrapper.unmount()
  })

  it('asks for a new window when the picker changes', async () => {
    const wrapper = await mountStats(stats())
    vi.mocked(getWatchStats).mockResolvedValue(stats({ days: 7 }))

    const seven = wrapper.findAll('.window-btn')[0]
    expect(seven.text()).toContain('近 7 天')
    await seven.trigger('click')
    await flushPromises()

    expect(getWatchStats).toHaveBeenLastCalledWith(7)
    expect(wrapper.findAll('.window-btn')[1].classes()).not.toContain('active')
    expect(seven.classes()).toContain('active')
    wrapper.unmount()
  })

  it('says so when the log is still empty', async () => {
    const wrapper = await mountStats(
      stats({
        window_seconds: 0,
        month_seconds: 0,
        videos_watched: 0,
        active_days: 0,
        longest_streak_days: 0,
        daily: [{ date: '2026-09-18', seconds: 0, videos: 0 }],
        tags: [],
      }),
    )

    expect(wrapper.findAll('.bar')).toHaveLength(0)
    expect(wrapper.findAll('.panel-empty')[0].text()).toContain('还没有观看记录')
    expect(wrapper.findAll('.panel-empty')[1].text()).toContain('还没有标签')
    wrapper.unmount()
  })

  it('reports a failed load instead of showing zeros', async () => {
    vi.mocked(getWatchStats).mockRejectedValue(new Error('服务未就绪'))
    const wrapper = mount(Stats)
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('加载统计失败：服务未就绪')
    wrapper.unmount()
  })
})
