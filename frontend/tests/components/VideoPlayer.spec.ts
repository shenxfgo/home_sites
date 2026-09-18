import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import VideoPlayer from '@/components/VideoPlayer.vue'
import { makeSubtitle } from '../factories'

const listSubtitles = vi.hoisted(() => vi.fn())
const recordPlay = vi.hoisted(() => vi.fn())
const updateProgress = vi.hoisted(() => vi.fn())

vi.mock('@/api/subtitles', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/subtitles')>()),
  listSubtitles,
}))

vi.mock('@/api/videos', () => ({
  recordPlay,
  updateProgress: (...args: unknown[]) => updateProgress(...args) as unknown,
}))

function mountPlayer(videoId = 1) {
  return mount(VideoPlayer, {
    props: { videoId, videoUrl: '/api/videos/1/stream' },
  })
}

describe('VideoPlayer subtitles', () => {
  beforeEach(() => {
    vi.useRealTimers()
    listSubtitles.mockReset()
    recordPlay.mockReset()
    recordPlay.mockResolvedValue(undefined)
    updateProgress.mockReset()
    updateProgress.mockResolvedValue(undefined)
    listSubtitles.mockResolvedValue([])
  })

  it('loads the tracks of the played video once', async () => {
    mountPlayer(7)
    await flushPromises()

    expect(listSubtitles).toHaveBeenCalledTimes(1)
    expect(listSubtitles).toHaveBeenCalledWith(7)
  })

  it('renders a WebVTT track per subtitle', async () => {
    listSubtitles.mockResolvedValue([
      makeSubtitle({ id: 3, language: 'zh', label: '中文' }),
      makeSubtitle({ id: 4, language: 'en', label: null }),
    ])

    const wrapper = mountPlayer()
    await flushPromises()

    const tracks = wrapper.findAll('track')
    expect(tracks).toHaveLength(2)
    expect(tracks[0].attributes('src')).toBe('/api/videos/1/subtitles/3/stream')
    expect(tracks[0].attributes('srclang')).toBe('zh')
    expect(tracks[0].attributes('label')).toBe('中文')
    expect(tracks[1].attributes('srclang')).toBe('en')
    expect(tracks[1].attributes('label')).toBe('en')
  })

  it('falls back to an undetermined language so the browser keeps the track', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ language: null, label: '评论音轨' })])

    const wrapper = mountPlayer()
    await flushPromises()

    expect(wrapper.find('track').attributes('srclang')).toBe('und')
    expect(wrapper.find('track').attributes('label')).toBe('评论音轨')
  })

  it('hides the subtitle button when the video has no tracks', async () => {
    const wrapper = mountPlayer()
    await flushPromises()

    expect(wrapper.find('.subtitle-btn').exists()).toBe(false)
  })

  it('lists 关闭 plus every track in the subtitle menu', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3, label: '中文' })])
    const wrapper = mountPlayer()
    await flushPromises()

    await wrapper.find('.subtitle-btn').trigger('click')

    const items = wrapper.findAll('.subtitle-menu-item')
    expect(items.map((item) => item.text())).toEqual(['关闭', '中文'])
    expect(items[0].classes()).toContain('is-active')
  })

  it('marks the chosen track active', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3, label: '中文' })])
    const wrapper = mountPlayer()
    await flushPromises()

    await wrapper.find('.subtitle-btn').trigger('click')
    await wrapper.findAll('.subtitle-menu-item')[1].trigger('click')

    expect(wrapper.find('.subtitle-btn').classes()).toContain('is-active')
  })

  it('closes the menu after a choice', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle()])
    const wrapper = mountPlayer()
    await flushPromises()

    await wrapper.find('.subtitle-btn').trigger('click')
    await wrapper.findAll('.subtitle-menu-item')[1].trigger('click')

    expect(wrapper.find('.subtitle-menu').exists()).toBe(false)
  })

  it('loads the tracks again when the video changes', async () => {
    const wrapper = mountPlayer(1)
    await flushPromises()

    await wrapper.setProps({ videoId: 2 })
    await flushPromises()

    expect(listSubtitles).toHaveBeenLastCalledWith(2)
    expect(wrapper.findAll('track')).toHaveLength(0)
  })

  it('keeps playing when the subtitle request fails', async () => {
    listSubtitles.mockRejectedValue(new Error('network down'))

    const wrapper = mountPlayer()
    await flushPromises()

    expect(wrapper.find('video').exists()).toBe(true)
    expect(wrapper.findAll('track')).toHaveLength(0)
    expect(wrapper.find('.subtitle-btn').exists()).toBe(false)
  })
})
