import type { Page, Route } from '@playwright/test'

/** 1x1 transparent PNG, used to answer thumbnail requests. */
export const TINY_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
)

/**
 * 一段真实的 H.264 片段（64x36 黑帧、1 fps、30 秒、1.8 kB），让浏览器报出真实的
 * 时长与可拖动区间，播放器用例才能验证跳转与像素级布局。宽高比必须是 16:9，
 * 否则 <video> 会按固有尺寸把控制条顶出视口。
 */
export const SAMPLE_MP4 = Buffer.from(
  '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',
  'base64',
)

export interface StubVideo {
  id: number
  source_id: number
  filepath: string
  title: string | null
  description: string | null
  duration: number | null
  file_size: number | null
  format: string | null
  resolution: string | null
  thumbnail_path: string | null
  rating: number
  view_count: number
  is_new: boolean
  last_played_at: string | null
  /** Stored playback position in seconds, attached by the watch-progress query. */
  progress: number | null
  created_at: string
  updated_at: string
  tags: { id: number; name: string; color: string }[]
}

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString()

export const videos: StubVideo[] = [
  {
    id: 1,
    source_id: 1,
    filepath: 'D:\\videos\\深夜测试.mp4',
    title: '深夜测试',
    description: null,
    duration: 65,
    file_size: 2048,
    format: 'mp4',
    resolution: '640x480',
    thumbnail_path: 'D:\\thumbs\\1.jpg',
    rating: 4,
    view_count: 3,
    is_new: true,
    last_played_at: hoursAgo(2),
    progress: 42,
    created_at: hoursAgo(1),
    updated_at: hoursAgo(1),
    tags: [{ id: 1, name: '动作片', color: '#7c6cff' }],
  },
  {
    id: 2,
    source_id: 2,
    filepath: '\\\\nas\\media\\周末纪录片.mkv',
    title: '周末纪录片',
    description: '关于极地科考的长纪录片',
    duration: 3600,
    file_size: 4096,
    format: 'mkv',
    resolution: '1280x720',
    thumbnail_path: 'D:\\thumbs\\2.jpg',
    rating: 0,
    view_count: 0,
    is_new: false,
    last_played_at: null,
    progress: null,
    created_at: hoursAgo(50),
    updated_at: hoursAgo(50),
    tags: [],
  },
]

export const sources = [
  {
    id: 1,
    name: '本地视频库',
    path: 'D:\\videos',
    type: 'local',
    scan_interval: 3600,
    last_scan_at: hoursAgo(3),
    is_active: true,
    created_at: hoursAgo(200),
  },
  {
    id: 2,
    name: 'NAS 片库',
    path: '\\\\nas\\media',
    type: 'nas',
    scan_interval: 7200,
    last_scan_at: null,
    is_active: true,
    created_at: hoursAgo(190),
  },
]

const formats = [
  { format: 'mp4', codec: 'libx264', extension: 'mp4' },
  { format: 'webm', codec: 'libvpx-vp9', extension: 'webm' },
]

type TranscodeState = 'idle' | 'running' | 'completed' | 'cancelled'

export const subtitles = [
  {
    id: 1,
    video_id: 1,
    language: 'zh',
    filepath: 'D:\\videos\\深夜测试.zh.srt',
    label: '中文',
    created_at: hoursAgo(1),
  },
  {
    id: 2,
    video_id: 1,
    language: 'en',
    filepath: 'D:\\videos\\深夜测试.en.srt',
    label: 'English',
    created_at: hoursAgo(1),
  },
]

/** WebVTT body the subtitle stream route answers with. */
export const SAMPLE_VTT = 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n中文测试\n'

/** Seed rows the notification routes serve; `read` is filled in per request. */
const NOTIFICATION_SEEDS = [
  {
    id: 1,
    type: 'scan_complete',
    title: '扫描完成',
    message: '发现 2 个新视频',
    data: null,
    created_at: hoursAgo(1),
  },
  {
    id: 2,
    type: 'new_video',
    title: '新视频',
    message: '深夜测试.mp4 已入库',
    data: null,
    created_at: hoursAgo(2),
  },
]

/** Which stub videos the fake playback history marks as started. */
const WATCH_STATE: Record<number, 'never' | 'unfinished' | 'finished'> = { 1: 'unfinished' }

const WATCH_STATE_LABELS: Record<string, string> = {
  没看过: 'never',
  未看完: 'unfinished',
  已看完: 'finished',
}

const DURATION_UNITS: Record<string, number> = {
  小时: 3600,
  分钟: 60,
  秒: 1,
  h: 3600,
  min: 60,
  m: 60,
  s: 1,
}

const NAMED_FILTER = /^(源|视频源|标签)[:：](.+)$/
const COMPARISON = /^(评分|时长)?\s*(>=|<=|≥|≤|>|<|=)\s*(\S+)$/

function secondsOf(value: string): number | null {
  const match = /^(\d+(?:\.\d+)?)(小时|分钟|秒|h|min|m|s)?$/i.exec(value)
  if (!match) return null
  const unit = match[2] ? DURATION_UNITS[match[2].toLowerCase()] : 60
  return Math.round(Number(match[1]) * unit)
}

function satisfies(actual: number | null, op: string, expected: number): boolean {
  if (actual == null) return false
  const normalized = op === '≥' ? '>=' : op === '≤' ? '<=' : op
  if (normalized === '>=') return actual >= expected
  if (normalized === '<=') return actual <= expected
  if (normalized === '>') return actual > expected
  if (normalized === '<') return actual < expected
  return actual === expected
}

/**
 * 搜索框的替身语义，与后端 `src/utils/video_search.py` 同义：关键词同时匹配片名、
 * 简介和标签名，多个词之间是且的关系。浏览器用例只覆盖"界面把整串发出去并按返回
 * 渲染"，所以这里不做空格容错，只保证同一种写法两边得到同一批视频。
 */
function matchesSearch(video: StubVideo, raw: string): boolean {
  const haystack = [
    video.title ?? video.filepath,
    video.description ?? '',
    ...video.tags.map((tag) => tag.name),
  ].map((field) => field.toLowerCase())

  for (const token of raw.match(/"[^"]+"|\S+/g) ?? []) {
    const quoted = token.startsWith('"')
    const text = quoted ? token.slice(1, -1) : token
    const lower = text.toLowerCase()

    if (!quoted) {
      const named = NAMED_FILTER.exec(text)
      if (named) {
        const [, key, value] = named
        const pool =
          key === '标签'
            ? video.tags.map((tag) => tag.name)
            : [sources.find((source) => source.id === video.source_id)?.name ?? '']
        if (!pool.some((field) => field.includes(value))) return false
        continue
      }

      const comparison = COMPARISON.exec(text)
      if (comparison) {
        const [, key, op, value] = comparison
        const seconds = secondsOf(value)
        if (key === '时长' || (!key && seconds !== null)) {
          if (!satisfies(video.duration, op, seconds ?? 0)) return false
          continue
        }
        if (key === '评分' && /^\d+$/.test(value)) {
          if (!satisfies(video.rating, op, Number(value))) return false
          continue
        }
      }

      if (text in WATCH_STATE_LABELS) {
        if ((WATCH_STATE[video.id] ?? 'never') !== WATCH_STATE_LABELS[text]) return false
        continue
      }
    }

    if (!haystack.some((field) => field.includes(lower))) return false
  }
  return true
}

/**
 * Stub the whole `/api` surface with a small stateful fake so the browser tests
 * exercise the real app (routing, components, axios layer) without a backend.
 */
export async function mockApi(page: Page): Promise<void> {
  let transcode: TranscodeState = 'idle'
  let transcodeProgress = 0
  let transcodeFormat: string | null = null
  const readNotifications = new Set<number>()
  const removedNotifications = new Set<number>()

  const statusBody = (videoId: number) => ({
    video_id: videoId,
    is_transcoding: transcode === 'running',
    status: transcode,
    progress: transcodeProgress,
    target_format: transcodeFormat,
    output_path: transcodeFormat ? `/tmp/out.${transcodeFormat}` : null,
    error: null,
  })

  const respond = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  /**
   * 响应不带字节区间信息时，Chromium 的 `video.seekable` 会是空的 [[0, 0]]，
   * 即使缓冲完整、readyState 到 4，赋值 currentTime 也会被静默丢弃。所以替身必须
   * 像真实流接口一样处理 Range，否则播放器用例全部失效。
   */
  const respondMedia = (route: Route, body: Buffer, contentType: string) => {
    const total = body.length
    const headers = { 'Accept-Ranges': 'bytes', 'Content-Length': String(total) }
    const range = /^bytes=(\d*)-(\d*)$/.exec(route.request().headers()['range'] ?? '')
    if (range && (range[1] || range[2])) {
      const start = range[1] ? Number(range[1]) : Math.max(0, total - Number(range[2]))
      const end = Math.min(total - 1, range[1] && range[2] ? Number(range[2]) : total - 1)
      if (start > end) {
        return route.fulfill({
          status: 416,
          headers: { ...headers, 'Content-Range': `bytes */${total}` },
          body: Buffer.alloc(0),
        })
      }
      return route.fulfill({
        status: 206,
        headers: {
          ...headers,
          'Content-Length': String(end - start + 1),
          'Content-Range': `bytes ${start}-${end}/${total}`,
        },
        body: body.subarray(start, end + 1),
      })
    }
    return route.fulfill({ status: 200, headers: { ...headers, 'Content-Type': contentType }, body })
  }

  await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = request.method()

    if (method === 'GET') {
      if (path === '/videos') {
        const search = (url.searchParams.get('search') ?? '').trim()
        const sourceId = url.searchParams.get('source_id')
        const tagId = url.searchParams.get('tag_id')
        const items = videos.filter(
          (video) =>
            (!search || matchesSearch(video, search)) &&
            (!sourceId || video.source_id === Number(sourceId)) &&
            (!tagId || video.tags.some((tag) => tag.id === Number(tagId))),
        )
        return respond(route, { items, total: items.length, page: 1, page_size: 20 })
      }
      if (path === '/videos/new') return respond(route, [])
      const subtitleStream = /^\/videos\/(\d+)\/subtitles\/(\d+)\/stream$/.exec(path)
      if (subtitleStream) {
        return route.fulfill({ status: 200, contentType: 'text/vtt', body: SAMPLE_VTT })
      }
      const subtitleList = /^\/videos\/(\d+)\/subtitles$/.exec(path)
      if (subtitleList) {
        return respond(
          route,
          subtitles.filter((item) => item.video_id === Number(subtitleList[1])),
        )
      }
      if (/^\/videos\/\d+\/stream$/.test(path)) {
        return respondMedia(route, SAMPLE_MP4, 'video/mp4')
      }
      const favoriteStatus = /^\/favorites\/(\d+)\/status$/.exec(path)
      if (favoriteStatus) return respond(route, { is_favorite: false })
      const video = /^\/videos\/(\d+)$/.exec(path)
      if (video) {
        const found = videos.find((item) => item.id === Number(video[1]))
        return found ? respond(route, found) : respond(route, { detail: '视频不存在' }, 404)
      }
      if (/^\/videos\/\d+\/thumbnail$/.test(path)) {
        return route.fulfill({ status: 200, contentType: 'image/png', body: TINY_PNG })
      }
      if (path === '/sources') {
        const activeOnly = url.searchParams.get('active_only') === 'true'
        return respond(route, activeOnly ? sources.filter((source) => source.is_active) : sources)
      }
      if (path === '/history') {
        return respond(route, {
          items: [
            {
              id: 1,
              video_id: 1,
              played_at: hoursAgo(2),
              progress: 42,
              completed: false,
              video_title: '深夜测试',
            },
            {
              id: 2,
              video_id: 999,
              played_at: hoursAgo(20),
              progress: 900,
              completed: true,
              video_title: null,
            },
          ],
          total: 2,
          page: 1,
          page_size: 20,
        })
      }
      if (path === '/history/continue') return respond(route, [videos[0]])
      if (path === '/favorites') return respond(route, { items: [videos[1]], total: 1, page: 1, page_size: 20 })
      if (path === '/tags') return respond(route, [{ id: 1, name: '动作片', color: '#7c6cff', video_count: 1 }])
      if (path === '/settings') {
        return respond(route, {
          auto_scan_enabled: true,
          auto_scan_interval: 3600,
          default_transcode_format: 'mp4',
          thumbnail_width: 320,
          thumbnail_height: 180,
          theme: 'light',
        })
      }
      if (path === '/notifications') {
        const items = NOTIFICATION_SEEDS.filter((item) => !removedNotifications.has(item.id)).map(
          (item) => ({ ...item, read: readNotifications.has(item.id) }),
        )
        return respond(route, { items, total: items.length, page: 1, page_size: 50 })
      }
      if (path === '/notifications/unread') {
        const alive = NOTIFICATION_SEEDS.filter((item) => !removedNotifications.has(item.id))
        return respond(route, {
          count: alive.filter((item) => !readNotifications.has(item.id)).length,
        })
      }
      if (path === '/transcode/formats') return respond(route, formats)
      const status = /^\/transcode\/(\d+)\/status$/.exec(path)
      if (status) {
        if (transcode === 'running') {
          transcodeProgress = Math.min(100, transcodeProgress + 45)
          if (transcodeProgress === 100) transcode = 'completed'
        }
        return respond(route, statusBody(Number(status[1])))
      }
      return respond(route, { detail: `未预置的接口: ${path}` }, 500)
    }

    if (method === 'POST') {
      if (/^\/videos\/\d+\/(play|progress)$/.test(path)) return respond(route, { ok: true })
      if (/^\/favorites\/\d+$/.test(path)) return respond(route, { ok: true })
      if (path === '/scan/all') {
        return respond(route, { sources_scanned: 2, total_files: 12, total_new_videos: 3 })
      }
      const scan = /^\/sources\/(\d+)\/scan$/.exec(path)
      if (scan) return respond(route, { source_id: Number(scan[1]), files_found: 2, new_videos: 1 })
      const read = /^\/notifications\/(\d+)\/read$/.exec(path)
      if (read) {
        readNotifications.add(Number(read[1]))
        return respond(route, { ok: true })
      }
      if (path === '/notifications/read-all') {
        readNotifications.add(1)
        readNotifications.add(2)
        return respond(route, { ok: true })
      }
      const start = /^\/transcode\/(\d+)$/.exec(path)
      if (start) {
        transcode = 'running'
        transcodeProgress = 0
        transcodeFormat = JSON.parse(request.postData() ?? '{}').target_format ?? null
        return respond(route, statusBody(Number(start[1])))
      }
      if (/^\/transcode\/\d+\/cancel$/.test(path)) {
        transcode = 'cancelled'
        return respond(route, { ok: true })
      }
      return respond(route, { detail: `未预置的接口: ${path}` }, 500)
    }

    if (method === 'PUT') {
      if (path === '/settings' || /^\/videos\/\d+$/.test(path)) {
        return respond(route, JSON.parse(request.postData() ?? '{}'))
      }
    }

    if (method === 'DELETE') {
      if (/^\/sources\/\d+$/.test(path)) return route.fulfill({ status: 204, body: '' })
      if (/^\/history\/\d+$/.test(path)) return respond(route, { ok: true })
      if (/^\/favorites\/\d+$/.test(path)) return respond(route, { ok: true })
      const notification = /^\/notifications\/(\d+)$/.exec(path)
      if (notification) {
        const id = Number(notification[1])
        if (!NOTIFICATION_SEEDS.some((item) => item.id === id) || removedNotifications.has(id)) {
          return respond(route, { detail: '通知不存在' }, 404)
        }
        removedNotifications.add(id)
        return route.fulfill({ status: 204, body: '' })
      }
      if (path === '/notifications') {
        for (const item of NOTIFICATION_SEEDS) removedNotifications.add(item.id)
        return route.fulfill({ status: 204, body: '' })
      }
    }

    return respond(route, { detail: `未预置的接口: ${method} ${path}` }, 500)
  })
}
