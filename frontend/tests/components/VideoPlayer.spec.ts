import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import VideoPlayer from '@/components/VideoPlayer.vue'
import { playerPrefs } from '@/composables/playerPrefs'
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
  const wrapper = mount(VideoPlayer, {
    props: { videoId, videoUrl: '/api/videos/1/stream' },
  })
  // The keyboard listeners live on `document`, so an unmounted wrapper keeps
  // answering keys for the rest of the file unless it is torn down.
  mounted.push(wrapper)
  return wrapper
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

describe('VideoPlayer playback tracking', () => {
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

  /** Mount a player that already knows its duration, and press play on it. */
  async function watchPlayer(duration = 120) {
    const { wrapper, video } = await mountSeekablePlayer(duration)
    await wrapper.find('video').trigger('play')
    return { wrapper, video }
  }

  it('records the play once, however often playback pauses', async () => {
    const { wrapper } = await watchPlayer()

    await wrapper.find('video').trigger('pause')
    await wrapper.find('video').trigger('play')

    expect(recordPlay).toHaveBeenCalledTimes(1)
    expect(recordPlay).toHaveBeenCalledWith(1)
  })

  it('reports the position the moment playback pauses', async () => {
    const { wrapper, video } = await watchPlayer()
    updateProgress.mockClear()

    video.currentTime = 33
    await wrapper.find('video').trigger('pause')

    expect(updateProgress).toHaveBeenCalledWith(1, 33)
  })

  it('reports the whole duration when the video ends', async () => {
    const { wrapper } = await watchPlayer(120)
    updateProgress.mockClear()

    await wrapper.find('video').trigger('ended')

    expect(updateProgress).toHaveBeenCalledWith(1, 120)
  })

  it('keeps tracking a replay instead of starting a second record', async () => {
    const { wrapper, video } = await watchPlayer(120)
    await wrapper.find('video').trigger('ended')
    updateProgress.mockClear()

    await wrapper.find('video').trigger('play')
    video.currentTime = 12
    await wrapper.find('video').trigger('pause')

    expect(recordPlay).toHaveBeenCalledTimes(1)
    expect(updateProgress).toHaveBeenCalledWith(1, 12)
  })

  it('reports the position when the seek bar is released', async () => {
    const { wrapper, video, bar } = await mountSeekablePlayer(100)
    await wrapper.find('video').trigger('play')
    updateProgress.mockClear()

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 400, bubbles: true }))
    window.dispatchEvent(new MouseEvent('pointerup', { clientX: 400 }))

    expect(video.currentTime).toBe(50)
    expect(updateProgress).toHaveBeenCalledWith(1, 50)
  })

  it('stores nothing for a video the viewer never played', async () => {
    const { wrapper, bar } = await mountSeekablePlayer(100)

    bar.dispatchEvent(new MouseEvent('pointerdown', { clientX: 400, bubbles: true }))
    window.dispatchEvent(new MouseEvent('pointerup', { clientX: 400 }))
    await wrapper.unmount()

    expect(recordPlay).not.toHaveBeenCalled()
    expect(updateProgress).not.toHaveBeenCalled()
  })
})

/** One WebVTT track holding the given cues; jsdom would never parse them. */
interface FakeCue {
  startTime: number
  endTime: number
}

interface FakeTrack {
  kind: string
  mode: string
  cues?: FakeCue[]
}

function fakeTracks(cues: FakeCue[]): FakeTrack[] {
  return [{ kind: 'subtitles', mode: 'hidden', cues }]
}

/**
 * Mount a player whose file is already measurable.
 *
 * The track list has to exist before the subtitle request resolves, because
 * that is when the player binds its cue timing.
 */
async function mountReady(
  extraProps: Record<string, unknown> = {},
  options: { duration?: number; tracks?: FakeTrack[] } = {},
) {
  const duration = options.duration ?? 100
  const wrapper = mount(VideoPlayer, {
    props: { videoId: 1, videoUrl: '/api/videos/1/stream', ...extraProps },
    attachTo: document.body,
  })
  mounted.push(wrapper)

  const video = wrapper.find('video').element as HTMLVideoElement
  Object.defineProperty(video, 'duration', { value: duration, configurable: true })
  if (options.tracks) {
    Object.defineProperty(video, 'textTracks', { value: options.tracks, configurable: true })
  }
  await flushPromises()
  await wrapper.find('video').trigger('loadedmetadata')
  return { wrapper, video }
}

/** Reset the shared prefs singleton so one test cannot leak into the next. */
function resetPrefs() {
  Object.assign(playerPrefs, {
    volume: 1,
    muted: false,
    rate: 1,
    subtitleSize: 0,
    subtitleDelay: 0,
  })
}

describe('VideoPlayer remembered choices', () => {
  beforeEach(() => {
    vi.useRealTimers()
    listSubtitles.mockReset()
    listSubtitles.mockResolvedValue([])
    recordPlay.mockReset()
    recordPlay.mockResolvedValue(undefined)
    updateProgress.mockReset()
    updateProgress.mockResolvedValue(undefined)
    resetPrefs()
  })

  afterEach(() => {
    window.dispatchEvent(new MouseEvent('pointerup'))
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  async function openCueMenu(wrapper: ReturnType<typeof mount>) {
    await wrapper.find('.subtitle-btn').trigger('click')
    return wrapper
  }

  function stepButton(wrapper: ReturnType<typeof mount>, group: number, which: 'down' | 'up') {
    const steppers = wrapper.findAll('.cue-stepper')
    const steps = steppers[group]?.findAll('.cue-step') ?? []
    return which === 'down' ? steps[0] : steps[1]
  }

  /** The 延迟 readout, which is the second stepper group in the menu. */
  function delayValue(wrapper: ReturnType<typeof mount>) {
    return wrapper.findAll('.cue-value')[1]?.text()
  }

  it('puts the remembered volume and speed on the element', async () => {
    Object.assign(playerPrefs, { volume: 0.4, rate: 1.5 })

    const { video } = await mountReady()

    expect(video.volume).toBe(0.4)
    expect(video.playbackRate).toBe(1.5)
  })

  it('offers the stored speed on the rate button', async () => {
    Object.assign(playerPrefs, { rate: 1.25 })

    const { wrapper } = await mountReady()

    expect(wrapper.find('.rate-btn').text()).toBe('1.25x')
    expect(wrapper.find('.rate-btn').classes()).toContain('is-active')
  })

  it('switches speed from the menu and remembers the choice', async () => {
    const { wrapper, video } = await mountReady()

    await wrapper.find('.rate-btn').trigger('click')
    const items = wrapper.findAll('.rate-menu .subtitle-menu-item')
    expect(items.map((item) => item.text())).toEqual(['0.5x', '0.75x', '1x', '1.25x', '1.5x', '2x'])

    await items[5].trigger('click')

    expect(video.playbackRate).toBe(2)
    expect(playerPrefs.rate).toBe(2)
    expect(wrapper.find('.rate-btn').text()).toBe('2x')
    expect(wrapper.find('.rate-menu').exists()).toBe(false)
  })

  it('keeps the speed after a new file loads', async () => {
    Object.assign(playerPrefs, { rate: 1.5 })

    const { wrapper, video } = await mountReady()
    await wrapper.find('video').trigger('loadstart')
    await wrapper.find('video').trigger('loadedmetadata')

    expect(video.playbackRate).toBe(1.5)
  })

  it('remembers muting as surely as it remembers volume', async () => {
    const { wrapper, video } = await mountReady()

    await wrapper.find('.volume-control .control-btn').trigger('click')
    expect(video.muted).toBe(true)
    expect(playerPrefs.muted).toBe(true)

    await wrapper.find('.volume-control .control-btn').trigger('click')
    expect(video.muted).toBe(false)
    expect(playerPrefs.muted).toBe(false)
  })

  it('starts at the stored position once the file is measurable', async () => {
    const { wrapper, video } = await mountReady({ startAt: 40 })

    expect(video.currentTime).toBe(40)
    expect(wrapper.find('.progress-fill').attributes('style')).toContain('width: 40%')
    expect(wrapper.emitted('resumed')).toEqual([[40]])
  })

  it('leaves the playhead alone for a head or a tail resume', async () => {
    const head = await mountReady({ startAt: 2 })
    expect(head.video.currentTime).toBe(0)
    expect(head.wrapper.emitted('resumed')).toBeUndefined()
    head.wrapper.unmount()
    mounted.pop()

    const tail = await mountReady({ startAt: 98 })
    expect(tail.video.currentTime).toBe(0)
    expect(tail.wrapper.emitted('resumed')).toBeUndefined()
  })

  it('skips the resume when there is nothing stored', async () => {
    const { wrapper, video } = await mountReady({ startAt: null })

    expect(video.currentTime).toBe(0)
    expect(wrapper.emitted('resumed')).toBeUndefined()
  })

  it('resumes once per load, and again when the file reloads', async () => {
    const { wrapper, video } = await mountReady({ startAt: 40 })

    video.currentTime = 61
    await wrapper.find('video').trigger('loadedmetadata')
    expect(video.currentTime).toBe(61)
    expect(wrapper.emitted('resumed')).toHaveLength(1)

    await wrapper.find('video').trigger('loadstart')
    await wrapper.find('video').trigger('loadedmetadata')
    expect(video.currentTime).toBe(40)
    expect(wrapper.emitted('resumed')).toHaveLength(2)
  })

  it('scales the cues through the video element', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3, label: '中文' })])

    const { wrapper, video } = await mountReady()
    await openCueMenu(wrapper)

    expect(wrapper.find('.cue-value').text()).toBe('自动')
    expect(video.style.fontSize).toBe('')

    await stepButton(wrapper, 0, 'up').trigger('click')
    expect(playerPrefs.subtitleSize).toBe(14)
    expect(video.style.fontSize).toBe('14px')

    await stepButton(wrapper, 0, 'up').trigger('click')
    expect(wrapper.find('.cue-value').text()).toBe('16')

    await stepButton(wrapper, 0, 'up').trigger('click')
    await stepButton(wrapper, 0, 'up').trigger('click')
    expect(playerPrefs.subtitleSize).toBe(20)
    await stepButton(wrapper, 0, 'down').trigger('click')
    expect(playerPrefs.subtitleSize).toBe(18)

    await wrapper.get('.cue-reset').trigger('click')
    expect(playerPrefs.subtitleSize).toBe(0)
    expect(video.style.fontSize).toBe('')
  })

  it('never lets the cue size leave the readable band', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3 })])
    const { wrapper, video } = await mountReady()
    await openCueMenu(wrapper)

    for (let i = 0; i < 20; i++) await stepButton(wrapper, 0, 'up').trigger('click')
    expect(playerPrefs.subtitleSize).toBe(40)

    for (let i = 0; i < 40; i++) await stepButton(wrapper, 0, 'down').trigger('click')
    expect(playerPrefs.subtitleSize).toBe(14)
    expect(video.style.fontSize).toBe('14px')
  })

  it('shifts every cue by the stored delay and back again', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3 })])
    const cues = [
      { startTime: 10, endTime: 12 },
      { startTime: 20, endTime: 21 },
    ]
    const { wrapper } = await mountReady({}, { tracks: fakeTracks(cues) })
    await openCueMenu(wrapper)

    await stepButton(wrapper, 1, 'up').trigger('click')
    expect(playerPrefs.subtitleDelay).toBe(0.5)
    expect(cues[0]).toMatchObject({ startTime: 10.5, endTime: 12.5 })
    expect(cues[1]).toMatchObject({ startTime: 20.5, endTime: 21.5 })

    await stepButton(wrapper, 1, 'up').trigger('click')
    expect(cues[0]).toMatchObject({ startTime: 11, endTime: 13 })

    await stepButton(wrapper, 1, 'down').trigger('click')
    await stepButton(wrapper, 1, 'down').trigger('click')
    expect(cues[0]).toMatchObject({ startTime: 10, endTime: 12 })
    expect(cues[1]).toMatchObject({ startTime: 20, endTime: 21 })
    expect(playerPrefs.subtitleDelay).toBe(0)
  })

  it('binds the delay to cues the browser parses later', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3 })])
    const cues = [{ startTime: 4, endTime: 6 }]
    // 轨道刚挂上时浏览器还没解析出 cues，<track> 元素 load 之后才有
    const track = Object.assign(new EventTarget(), {
      kind: 'subtitles',
      mode: 'hidden',
      cues: undefined as typeof cues | undefined,
    })

    playerPrefs.subtitleDelay = 1
    const { wrapper } = await mountReady({}, { tracks: [track] })
    expect(cues[0]).toMatchObject({ startTime: 4, endTime: 6 })

    track.cues = cues
    await wrapper.findAll('track')[0].trigger('load')
    await flushPromises()

    expect(cues[0]).toMatchObject({ startTime: 5, endTime: 7 })
    await openCueMenu(wrapper)
    expect(delayValue(wrapper)).toBe('1.0s')
  })

  it('retries when the browser hands over an empty cue list first', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3 })])
    const cues = [{ startTime: 4, endTime: 6 }]
    // Chromium 在解析完成前给的是空列表而不是 undefined，此时不能算已经记下时间轴
    const track = Object.assign(new EventTarget(), {
      kind: 'subtitles',
      mode: 'hidden',
      cues: [] as typeof cues,
    })

    playerPrefs.subtitleDelay = 1
    const { wrapper } = await mountReady({}, { tracks: [track] })

    track.cues = cues
    await wrapper.findAll('track')[0].trigger('load')
    await flushPromises()

    expect(cues[0]).toMatchObject({ startTime: 5, endTime: 7 })
    wrapper.unmount()
  })

  it('keeps a cue from running backwards at the very start', async () => {
    listSubtitles.mockResolvedValue([makeSubtitle({ id: 3 })])
    const cues = [{ startTime: 0.2, endTime: 2 }]
    const { wrapper } = await mountReady({}, { tracks: fakeTracks(cues) })
    await openCueMenu(wrapper)

    await stepButton(wrapper, 1, 'down').trigger('click')
    expect(cues[0]).toMatchObject({ startTime: 0, endTime: 1.5 })
  })
})

describe('VideoPlayer keyboard shortcuts', () => {
  beforeEach(() => {
    vi.useRealTimers()
    listSubtitles.mockReset()
    listSubtitles.mockResolvedValue([])
    recordPlay.mockReset()
    recordPlay.mockResolvedValue(undefined)
    updateProgress.mockReset()
    updateProgress.mockResolvedValue(undefined)
    resetPrefs()
  })

  afterEach(() => {
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  /** Fire a document-level key as if it had been typed into `field`. */
  async function press(key: string, field: Element | Document) {
    field.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  }

  it('rewinds with the arrow keys', async () => {
    const { wrapper, video } = await mountReady()
    video.currentTime = 30

    await press('ArrowLeft', document.body)

    expect(video.currentTime).toBe(25)
    wrapper.unmount()
  })

  it('plays and pauses on the space key', async () => {
    const { wrapper, video } = await mountReady()
    const play = vi.spyOn(video, 'play').mockResolvedValue(undefined)

    await press(' ', document.body)

    expect(play).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('stands down while the viewer is typing in a field', async () => {
    const { wrapper, video } = await mountReady()
    video.currentTime = 30
    const play = vi.spyOn(video, 'play').mockResolvedValue(undefined)
    const field = document.createElement('input')
    document.body.appendChild(field)

    await press('ArrowLeft', field)
    await press(' ', field)

    expect(video.currentTime).toBe(30)
    expect(play).not.toHaveBeenCalled()
    field.remove()
    wrapper.unmount()
  })

  it('stands down while the viewer is typing in a textarea', async () => {
    const { wrapper, video } = await mountReady()
    video.currentTime = 30
    const play = vi.spyOn(video, 'play').mockResolvedValue(undefined)
    const box = document.createElement('textarea')
    document.body.appendChild(box)

    await press('ArrowLeft', box)
    await press(' ', box)

    expect(video.currentTime).toBe(30)
    expect(play).not.toHaveBeenCalled()
    box.remove()
    wrapper.unmount()
  })
})
