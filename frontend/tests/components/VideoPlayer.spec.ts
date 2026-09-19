import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

/** Wrappers attached to the document, torn down after each seeking test. */
const mounted: ReturnType<typeof mount>[] = []

/** A rect jsdom would never produce on its own (it returns all zeros). */
function rect(left: number, width: number) {
  return {
    left,
    right: left + width,
    top: 0,
    bottom: 0,
    width,
    height: 0,
    x: left,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect
}

/** Mount, give the media element a duration, and place the seek bar on screen. */
async function mountSeekablePlayer(duration = 100) {
  // 必须挂进 document，拖拽时进度条依赖 window 上的冒泡
  const wrapper = mount(VideoPlayer, {
    props: { videoId: 1, videoUrl: '/api/videos/1/stream' },
    attachTo: document.body,
  })
  mounted.push(wrapper)

  const video = wrapper.find('video').element as HTMLVideoElement
  Object.defineProperty(video, 'duration', { value: duration, configurable: true })
  await wrapper.find('video').trigger('loadedmetadata')

  // 播放器 1200px 宽，进度条只是其中左侧偏移 200px、宽 400px 的一段
  const player = wrapper.find('.video-player').element as HTMLElement
  player.getBoundingClientRect = () => rect(0, 1200)
  const bar = wrapper.find('.progress-bar').element as HTMLElement
  bar.getBoundingClientRect = () => rect(200, 400)
  return { wrapper, video, bar }
}

describe('VideoPlayer seeking', () => {
  beforeEach(() => {
    listSubtitles.mockReset()
    listSubtitles.mockResolvedValue([])
    recordPlay.mockReset()
    recordPlay.mockResolvedValue(undefined)
    updateProgress.mockReset()
    updateProgress.mockResolvedValue(undefined)
  })

  afterEach(() => {
    // 松开指针并卸载，避免未结束的拖拽把 window 监听带进下一个用例
    window.dispatchEvent(new MouseEvent('pointerup'))
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  it('seeks to the clicked point of the bar, not of the whole player', async () => {
    const { video, bar } = await mountSeekablePlayer(100)

    // 进度条正中 = 屏幕 x=400；按整台播放器算会得到 33%，按进度条算是 50%
    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 400, bubbles: true }))

    expect(video.currentTime).toBe(50)
  })

  it('maps the ends of the bar to 0 and the full duration', async () => {
    const { video, bar } = await mountSeekablePlayer(100)

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 200, bubbles: true }))
    expect(video.currentTime).toBe(0)

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 600, bubbles: true }))
    expect(video.currentTime).toBe(100)

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 999, bubbles: true }))
    expect(video.currentTime).toBe(100)
  })

  it('follows the pointer while dragging', async () => {
    const { video, bar } = await mountSeekablePlayer(100)

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 200, bubbles: true }))
    bar.dispatchEvent(new MouseEvent('pointermove', { clientX: 500, bubbles: true }))
    expect(video.currentTime).toBe(75)

    bar.dispatchEvent(new MouseEvent('pointermove', { clientX: 300, bubbles: true }))
    expect(video.currentTime).toBe(25)

    bar.dispatchEvent(new MouseEvent('pointerup', { clientX: 300, bubbles: true }))
  })

  it('ignores plain pointer movement until the bar is pressed', async () => {
    const { video, bar } = await mountSeekablePlayer(100)

    bar.dispatchEvent(new MouseEvent('pointermove', { clientX: 500, bubbles: true }))

    expect(video.currentTime).toBe(0)
  })

  it('shows the pointer position on the bar while dragging', async () => {
    const { wrapper, bar } = await mountSeekablePlayer(100)

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 500, bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.progress-fill').attributes('style')).toContain('width: 75%')

    bar.dispatchEvent(new MouseEvent('pointerup', { clientX: 500, bubbles: true }))
    bar.dispatchEvent(new MouseEvent('pointermove', { clientX: 200, bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.progress-fill').attributes('style')).not.toContain('width: 75%')
  })

  it('keeps following the pointer after it leaves the bar', async () => {
    const { video, bar } = await mountSeekablePlayer(100)

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 300, bubbles: true }))
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 560 }))
    expect(video.currentTime).toBe(90)

    window.dispatchEvent(new MouseEvent('pointerup', { clientX: 560 }))
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 200 }))
    expect(video.currentTime).toBe(90)
  })

  it('does not seek before the duration is known', async () => {
    const wrapper = mountPlayer()
    await flushPromises()

    const video = wrapper.find('video').element as HTMLVideoElement
    const bar = wrapper.find('.progress-bar').element as HTMLElement
    bar.getBoundingClientRect = () => rect(200, 400)
    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 400, bubbles: true }))

    expect(video.currentTime).toBe(0)
  })
})

describe('VideoPlayer A-B loop', () => {
  beforeEach(() => {
    vi.useRealTimers()
    listSubtitles.mockReset()
    listSubtitles.mockResolvedValue([])
    recordPlay.mockReset()
    recordPlay.mockResolvedValue(undefined)
    updateProgress.mockReset()
    updateProgress.mockResolvedValue(undefined)
  })

  afterEach(() => {
    window.dispatchEvent(new MouseEvent('pointerup'))
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  /** Move the playhead and let the component observe it, like the browser would. */
  async function moveTo(video: HTMLVideoElement, seconds: number) {
    video.currentTime = seconds
    video.dispatchEvent(new Event('timeupdate'))
    await new Promise((resolve) => setTimeout(resolve, 0))
  }

  function loopButtons(wrapper: ReturnType<typeof mount>) {
    return wrapper.findAll('.loop-btn')
  }

  it('keeps B disabled until the playhead is past a marked start', async () => {
    const { wrapper, video } = await mountSeekablePlayer(100)
    await moveTo(video, 20)

    expect(loopButtons(wrapper)[1].attributes('disabled')).toBeDefined()

    await loopButtons(wrapper)[0].trigger('click')
    expect(loopButtons(wrapper)[1].attributes('disabled')).toBeDefined()

    await moveTo(video, 21)
    expect(loopButtons(wrapper)[1].attributes('disabled')).toBeUndefined()
  })

  it('rejects an end point at or before the start point', async () => {
    const { wrapper, video } = await mountSeekablePlayer(100)

    await moveTo(video, 30)
    await loopButtons(wrapper)[0].trigger('click')
    await moveTo(video, 30)
    expect(loopButtons(wrapper)[1].attributes('disabled')).toBeDefined()

    await moveTo(video, 10)
    expect(loopButtons(wrapper)[1].attributes('disabled')).toBeDefined()
    expect(wrapper.find('.progress-loop').exists()).toBe(false)
  })

  it('rewinds to A when the playhead passes B', async () => {
    const { wrapper, video } = await mountSeekablePlayer(100)

    await moveTo(video, 20)
    await loopButtons(wrapper)[0].trigger('click')
    await moveTo(video, 35)
    await loopButtons(wrapper)[1].trigger('click')

    await moveTo(video, 34)
    expect(video.currentTime).toBe(34)

    await moveTo(video, 36)
    expect(video.currentTime).toBe(20)
    expect(wrapper.find('.loop-control').classes()).toContain('is-looping')
  })

  it('draws the marked range on the seek bar and clears it again', async () => {
    const { wrapper, video } = await mountSeekablePlayer(100)

    await moveTo(video, 20)
    await loopButtons(wrapper)[0].trigger('click')
    await moveTo(video, 45)
    await loopButtons(wrapper)[1].trigger('click')

    const band = wrapper.find('.progress-loop')
    expect(band.exists()).toBe(true)
    expect(band.attributes('style')).toContain('left: 20%')
    expect(band.attributes('style')).toContain('width: 25%')

    await wrapper.find('.loop-clear').trigger('click')
    expect(wrapper.find('.progress-loop').exists()).toBe(false)
    expect(video.currentTime).toBe(45)
  })

  it('snaps a seek past B back to A, and stops after clearing', async () => {
    const { wrapper, video, bar } = await mountSeekablePlayer(100)

    await moveTo(video, 20)
    await loopButtons(wrapper)[0].trigger('click')
    await moveTo(video, 40)
    await loopButtons(wrapper)[1].trigger('click')

    // 拖到 70 后，下一次 timeupdate 会把播放位置拉回 A
    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 480, bubbles: true }))
    window.dispatchEvent(new MouseEvent('pointerup', { clientX: 480 }))
    expect(video.currentTime).toBe(70)
    video.dispatchEvent(new Event('timeupdate'))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(video.currentTime).toBe(20)

    await wrapper.find('.loop-clear').trigger('click')
    await moveTo(video, 80)
    expect(video.currentTime).toBe(80)
  })
})

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
