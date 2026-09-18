import type { Page, Route } from '@playwright/test'

/** 1x1 transparent PNG, used to answer thumbnail requests. */
export const TINY_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
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
  last_played_at: string | null
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
    last_played_at: hoursAgo(2),
    created_at: hoursAgo(1),
    updated_at: hoursAgo(1),
    tags: [{ id: 1, name: '动作片', color: '#7c6cff' }],
  },
  {
    id: 2,
    source_id: 2,
    filepath: '\\\\nas\\media\\周末纪录片.mkv',
    title: '周末纪录片',
    description: null,
    duration: 3600,
    file_size: 4096,
    format: 'mkv',
    resolution: '1280x720',
    thumbnail_path: 'D:\\thumbs\\2.jpg',
    rating: 0,
    view_count: 0,
    last_played_at: null,
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

/**
 * Stub the whole `/api` surface with a small stateful fake so the browser tests
 * exercise the real app (routing, components, axios layer) without a backend.
 */
export async function mockApi(page: Page): Promise<void> {
  let transcode: TranscodeState = 'idle'
  let transcodeProgress = 0
  let transcodeFormat: string | null = null
  const readNotifications = new Set<number>()

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

  await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/^\/api/, '')
    const method = request.method()

    if (method === 'GET') {
      if (path === '/videos') {
        const search = (url.searchParams.get('search') ?? '').trim()
        const sourceId = url.searchParams.get('source_id')
        const items = videos.filter(
          (video) =>
            (!search || (video.title ?? video.filepath).includes(search)) &&
            (!sourceId || video.source_id === Number(sourceId)),
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
        return route.fulfill({ status: 200, contentType: 'video/mp4', body: '' })
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
        const items = [
          {
            id: 1,
            type: 'scan_complete',
            title: '扫描完成',
            message: '发现 2 个新视频',
            data: null,
            read: readNotifications.has(1),
            created_at: hoursAgo(1),
          },
          {
            id: 2,
            type: 'new_video',
            title: '新视频',
            message: '深夜测试.mp4 已入库',
            data: null,
            read: readNotifications.has(2),
            created_at: hoursAgo(2),
          },
        ]
        return respond(route, { items, total: items.length, page: 1, page_size: 50 })
      }
      if (path === '/notifications/unread') {
        return respond(route, { count: 2 - [...readNotifications].filter((id) => id <= 2).length })
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
    }

    return respond(route, { detail: `未预置的接口: ${method} ${path}` }, 500)
  })
}
