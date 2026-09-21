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
  /** Series coordinates the scan parsed out of the file name. */
  series: string | null
  season: number | null
  episode: number | null
  /** The last scan could not find the file on disk. */
  is_missing: boolean
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
    series: '深夜客车',
    season: 1,
    episode: 2,
    is_missing: false,
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
    series: null,
    season: null,
    episode: null,
    // The NAS share was not mounted at the last scan, so the row is still in
    // the library but its file could not be found.
    is_missing: true,
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

/** Rows for GET /videos/series: the next unfinished episode is the one to open. */
export const seriesProgress = [
  { series: '深夜客车', total: 3, finished: 1, watched: 2, next: videos[0] },
]

/**
 * A byte-identical second copy of 深夜测试. It never reaches the grid, because
 * the duplicate report is the only route that serves it.
 */
const duplicateCopies: StubVideo[] = [
  {
    ...videos[0],
    id: 41,
    title: '深夜测试 备份',
    filepath: 'D:\\videos\\重复\\深夜测试.mp4',
    view_count: 0,
    progress: null,
    is_new: false,
    last_played_at: null,
    created_at: hoursAgo(20),
    updated_at: hoursAgo(20),
  },
]

/** Body for GET /videos/duplicates: the same bytes filed in two places. */
function duplicateGroupsFor(alive: StubVideo[], copies: StubVideo[]) {
  const items = alive.filter((video) => video.id === 1).concat(copies)
  if (items.length < 2) return []
  const size = items[0].file_size ?? 0
  return [
    {
      file_size: size,
      duration: items[0].duration,
      count: items.length,
      wasted_bytes: size * (items.length - 1),
      keep_id: items[0].id,
      items,
    },
  ]
}

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

/** 替身认识的账号，以及登录用的密码。 */
export const STUB_PASSWORD = 'secret-pass'
export const STUB_USER = { id: 1, username: 'tester', role: 'owner' as const, display_name: 'Tester' }
export const STUB_MEMBER = { id: 2, username: 'kid', role: 'member' as const, display_name: '小明' }
const ACCOUNTS = { owner: STUB_USER, member: STUB_MEMBER }

export type StubRole = keyof typeof ACCOUNTS

/**
 * 成员可写的接口，一比一照抄后端 `src/middleware/auth.py` 的 `MEMBER_WRITE_PATHS`：
 * 只有自己的收藏、历史、片单、已读和偏好。后端放行一条新的写接口，这里要跟着加，
 * 否则替身会替界面挡掉一次本该成功的请求。
 *
 * `/auth/*` 那几条（登录、退出、我的设备）在替身里由 auth 分支自己处理，两种角色
 * 都放行，所以不进这张表。
 */
const MEMBER_WRITE =
  /^(\/preferences|\/favorites\/\d+|\/history\/\d+|\/notifications\/(\d+\/read|read-all)|\/videos\/new\/\d+\/viewed|\/videos\/\d+\/(play|progress)|\/watchlists(\/\d+(\/videos(\/\d+)?)?)?)$/

/** "我的设备"的两行：这一台是跑用例的浏览器，另一台造出来好让列表不只一行。 */
const HERE_HASH = 'e'.repeat(64)
const PHONE_HASH = 'b'.repeat(64)
const PHONE_USER_AGENT =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

/** Rows for GET /users: what the 用户管理 table shows per account. */
interface StubAccountRow {
  id: number
  username: string
  role: 'owner' | 'member'
  display_name: string | null
  is_active: boolean
  created_at: string
  last_login_at: string | null
  signed_in_devices: number
}

const userRowsSeed: StubAccountRow[] = [
  {
    id: 1,
    username: 'tester',
    role: 'owner',
    display_name: 'Tester',
    is_active: true,
    created_at: hoursAgo(300),
    last_login_at: hoursAgo(1),
    signed_in_devices: 2,
  },
  {
    id: 2,
    username: 'kid',
    role: 'member',
    display_name: '小明',
    is_active: true,
    created_at: hoursAgo(200),
    last_login_at: hoursAgo(6),
    signed_in_devices: 1,
  },
  {
    id: 3,
    username: 'guest',
    role: 'member',
    display_name: null,
    is_active: false,
    created_at: hoursAgo(90),
    last_login_at: null,
    signed_in_devices: 0,
  },
]

/** A hand-picked queue of video ids, in the order they were added. */
interface StubWatchlist {
  id: number
  name: string
  description: string | null
  created_at: string
  video_ids: number[]
}

const watchlistSeed: StubWatchlist[] = [
  {
    id: 1,
    name: '今晚看这些',
    description: null,
    created_at: hoursAgo(5),
    video_ids: [1, 2],
  },
  {
    id: 2,
    name: '还没排片',
    description: '先占个位置',
    created_at: hoursAgo(4),
    video_ids: [],
  },
]

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

      if (text === '丢失' || text === 'missing') {
        if (!video.is_missing) return false
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
 *
 * `signedIn` mirrors the backend's default-deny middleware: while false, every
 * non-auth route answers 401, so the login flow can be tested end to end.
 * `role` picks which account holds that session, and a member gets the same 403
 * the role gateway hands out for the management surface.
 */
export async function mockApi(
  page: Page,
  options: {
    signedIn?: boolean
    needsSetup?: boolean
    role?: StubRole
    themes?: Partial<Record<StubRole, string>>
  } = {},
): Promise<void> {
  let signedIn = options.signedIn ?? true
  /** 当前会话是谁：登录成功后会换人，角色网关和偏好都按这个人来判。 */
  let account = ACCOUNTS[options.role ?? 'owner']
  const byUsername = (username: unknown) =>
    Object.values(ACCOUNTS).find((item) => item.username === username) ?? null
  /** 主题按人存：换账号登录就该看到那个人自己的选择。 */
  const themeStore: Record<number, string> = {
    [STUB_USER.id]: options.themes?.owner ?? 'light',
    [STUB_MEMBER.id]: options.themes?.member ?? 'light',
  }
  const userRows = userRowsSeed.map((row) => ({ ...row }))
  let nextUserId = 100
  let transcode: TranscodeState = 'idle'
  let transcodeProgress = 0
  let transcodeFormat: string | null = null
  const readNotifications = new Set<number>()
  const removedNotifications = new Set<number>()
  /** 退出过的设备：真后端删掉那一行 sessions，替身就从这份名单里划掉它。 */
  const revokedDevices = new Set<string>()
  /** Rows the app deleted through DELETE /videos/{id} during a test. */
  const removedVideos = new Set<number>()
  /** Queues the page mutates through /watchlists, seeded per test. */
  const queues: StubWatchlist[] = watchlistSeed.map((list) => ({
    ...list,
    video_ids: [...list.video_ids],
  }))
  let nextQueueId = 100
  const aliveVideos = () => videos.filter((video) => !removedVideos.has(video.id))
  const aliveCopies = () => duplicateCopies.filter((video) => !removedVideos.has(video.id))

  const queueBody = (list: StubWatchlist) => ({
    id: list.id,
    name: list.name,
    description: list.description,
    created_at: list.created_at,
    items: list.video_ids
      .map((id) => aliveVideos().find((video) => video.id === id))
      .filter((video): video is StubVideo => Boolean(video)),
  })

  const findQueue = (id: number) => queues.find((list) => list.id === id)

  /** 这个账号此刻开着的会话。当前这台报进去的 User-Agent，另一台是造好的手机。 */
  const deviceRows = (userAgent: string | null) =>
    [
      {
        token_hash: HERE_HASH,
        current: true,
        user_agent: userAgent,
        created_at: hoursAgo(2),
        last_seen_at: hoursAgo(0),
        expires_at: new Date(Date.now() + 12 * 3600_000).toISOString(),
      },
      {
        token_hash: PHONE_HASH,
        current: false,
        user_agent: PHONE_USER_AGENT,
        created_at: hoursAgo(300),
        last_seen_at: hoursAgo(3),
        expires_at: new Date(Date.now() + 30 * 86_400_000).toISOString(),
      },
    ].filter((row) => !revokedDevices.has(row.token_hash))

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

    if (path.startsWith('/auth/')) {
      if (method === 'GET' && path === '/auth/status') {
        return respond(route, {
          authenticated: signedIn,
          needs_setup: options.needsSetup ?? false,
        })
      }
      if (method === 'GET' && path === '/auth/me') {
        return signedIn ? respond(route, account) : respond(route, { detail: '未认证' }, 401)
      }
      if (method === 'POST' && path === '/auth/login') {
        const body = JSON.parse(request.postData() ?? '{}')
        const found = byUsername(body.username)
        if (!found || body.password !== STUB_PASSWORD) {
          return respond(route, { detail: '账号或密码错误' }, 401)
        }
        signedIn = true
        account = found
        return respond(route, account)
      }
      if (method === 'POST' && path === '/auth/logout') {
        signedIn = false
        return route.fulfill({ status: 204, body: '' })
      }
      if (method === 'POST' && path === '/auth/password') {
        const body = JSON.parse(request.postData() ?? '{}')
        // 替身账号共用同一个密码，所以"原密码对不对"这件事能照真后端判。
        if (body.old_password !== STUB_PASSWORD) {
          return respond(route, { detail: '原密码不正确' }, 400)
        }
        // 真后端改完密码会顺手退了别的浏览器，只留发起的这一台。
        revokedDevices.add(PHONE_HASH)
        return route.fulfill({ status: 204, body: '' })
      }
      if (path.startsWith('/auth/sessions')) {
        // 和 /auth/logout 同一档：两种角色都管得动自己的会话，这里不该有 403。
        if (!signedIn) return respond(route, { detail: '未认证' }, 401)
        if (method === 'GET' && path === '/auth/sessions') {
          return respond(route, deviceRows(request.headers()['user-agent'] ?? null))
        }
        const deviceOut = /^\/auth\/sessions\/([0-9a-f]{64})$/.exec(path)
        if (method === 'DELETE' && deviceOut) {
          if (revokedDevices.has(deviceOut[1])) {
            return respond(route, { detail: '设备不存在或已退出' }, 404)
          }
          revokedDevices.add(deviceOut[1])
          return route.fulfill({ status: 204, body: '' })
        }
      }
      return respond(route, { detail: `未预置的接口: ${method} ${path}` }, 500)
    }
    // 后端的默认拒绝：没有会话时业务接口一律 401，登录流程才测得真。
    if (!signedIn) return respond(route, { detail: '未认证' }, 401)
    if (account.role !== 'owner') {
      // 管理面连读都不给成员，界面上也就该没有这些入口。
      if (/^\/(users|settings)(\/|$)/.test(path)) {
        return respond(route, { detail: '需要管理员权限' }, 403)
      }
      // 写接口反过来按白名单放行，和中间件一样：不在名单里的都是库级操作。
      if (method !== 'GET' && !MEMBER_WRITE.test(path)) {
        return respond(route, { detail: '需要管理员权限' }, 403)
      }
    }

    if (method === 'GET' && path === '/preferences') {
      return respond(route, { theme: themeStore[account.id] ?? 'light' })
    }
    if (method === 'PUT' && path === '/preferences') {
      const body = JSON.parse(request.postData() ?? '{}')
      if (typeof body.theme === 'string') themeStore[account.id] = body.theme
      return respond(route, { theme: themeStore[account.id] ?? 'light' })
    }

    if (path.startsWith('/users')) {
      const rowBody = (row: StubAccountRow) => ({ ...row })
      if (method === 'GET' && path === '/users') {
        return respond(route, userRows.map(rowBody))
      }
      if (method === 'POST' && path === '/users') {
        const body = JSON.parse(request.postData() ?? '{}')
        const created: StubAccountRow = {
          id: nextUserId++,
          username: body.username,
          role: body.role ?? 'member',
          display_name: body.display_name ?? null,
          is_active: true,
          created_at: new Date().toISOString(),
          last_login_at: null,
          signed_in_devices: 0,
        }
        userRows.push(created)
        return respond(route, rowBody(created), 201)
      }
      const managed = /^\/users\/(\d+)(?:\/(\w+))?$/.exec(path)
      if (managed) {
        const found = userRows.find((row) => row.id === Number(managed[1]))
        if (!found) return respond(route, { detail: '账号不存在' }, 404)
        const body = JSON.parse(request.postData() ?? '{}')
        if (method === 'PUT' && managed[2] === 'role') {
          // 和后端一样：不能把最后一个可用管理员降级。
          const owners = userRows.filter((row) => row.role === 'owner' && row.is_active)
          if (found.role === 'owner' && body.role !== 'owner' && owners.length < 2) {
            return respond(route, { detail: '至少要保留一个可用的管理员，不能降级最后一个' }, 400)
          }
          found.role = body.role
          return respond(route, rowBody(found))
        }
        if (method === 'PUT' && managed[2] === 'status') {
          if (found.id === account.id && body.is_active === false) {
            return respond(route, { detail: '不能停用自己的账号' }, 400)
          }
          found.is_active = body.is_active
          if (!found.is_active) found.signed_in_devices = 0
          return respond(route, rowBody(found))
        }
        if (method === 'POST' && managed[2] === 'password') {
          return route.fulfill({ status: 204, body: '' })
        }
        if (method === 'DELETE' && managed[2] === 'sessions') {
          const revoked = found.signed_in_devices
          found.signed_in_devices = 0
          return respond(route, { revoked })
        }
      }
      return respond(route, { detail: `未预置的接口: ${method} ${path}` }, 500)
    }

    if (method === 'GET') {
      if (path === '/videos') {
        const search = (url.searchParams.get('search') ?? '').trim()
        const sourceId = url.searchParams.get('source_id')
        const tagId = url.searchParams.get('tag_id')
        const items = aliveVideos().filter(
          (video) =>
            (!search || matchesSearch(video, search)) &&
            (!sourceId || video.source_id === Number(sourceId)) &&
            (!tagId || video.tags.some((tag) => tag.id === Number(tagId))),
        )
        return respond(route, { items, total: items.length, page: 1, page_size: 20 })
      }
      if (path === '/videos/new') return respond(route, [])
      if (path === '/videos/series') return respond(route, seriesProgress)
      if (path === '/videos/duplicates') {
        return respond(route, duplicateGroupsFor(aliveVideos(), aliveCopies()))
      }
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
        const found = aliveVideos().find((item) => item.id === Number(video[1]))
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
      if (path === '/history/stats') {
        const days = Number(url.searchParams.get('days') ?? 30)
        const daily = Array.from({ length: days }, (_, index) => ({
          date: new Date(Date.now() - (days - 1 - index) * 86_400_000)
            .toISOString()
            .slice(0, 10),
          seconds: index === days - 1 ? 5400 : index === days - 2 ? 1800 : 0,
          videos: index >= days - 2 ? 1 : 0,
        }))
        return respond(route, {
          days,
          window_seconds: 7200,
          month_seconds: 5400,
          videos_watched: 1,
          active_days: 2,
          longest_streak_days: 2,
          daily,
          tags: [{ name: '动作片', color: '#7c6cff', seconds: 7200 }],
        })
      }
      if (path === '/favorites') return respond(route, { items: [videos[1]], total: 1, page: 1, page_size: 20 })
      if (path === '/tags') return respond(route, [{ id: 1, name: '动作片', color: '#7c6cff', video_count: 1 }])
      if (path === '/watchlists') {
        const videoId = url.searchParams.get('video_id')
        const held = videoId ? queues.filter((list) => list.video_ids.includes(Number(videoId))) : queues
        return respond(route, held.map(queueBody))
      }
      const queueRow = /^\/watchlists\/(\d+)$/.exec(path)
      if (queueRow) {
        const found = findQueue(Number(queueRow[1]))
        return found ? respond(route, queueBody(found)) : respond(route, { detail: '片单不存在' }, 404)
      }
      if (path === '/settings') {
        return respond(route, {
          auto_scan_enabled: true,
          auto_scan_interval: 3600,
          default_transcode_format: 'mp4',
          thumbnail_width: 320,
          thumbnail_height: 180,
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
      if (path === '/watchlists') {
        const body = JSON.parse(request.postData() ?? '{}')
        const created: StubWatchlist = {
          id: nextQueueId++,
          name: body.name ?? '未命名片单',
          description: body.description ?? null,
          created_at: new Date().toISOString(),
          video_ids: [],
        }
        queues.push(created)
        return respond(route, queueBody(created), 201)
      }
      const queueAdd = /^\/watchlists\/(\d+)\/videos$/.exec(path)
      if (queueAdd) {
        const found = findQueue(Number(queueAdd[1]))
        if (!found) return respond(route, { detail: '片单不存在' }, 404)
        const videoId = Number(JSON.parse(request.postData() ?? '{}').video_id)
        if (!found.video_ids.includes(videoId)) found.video_ids.push(videoId)
        return respond(route, queueBody(found))
      }
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
      const queueEdit = /^\/watchlists\/(\d+)$/.exec(path)
      if (queueEdit) {
        const found = findQueue(Number(queueEdit[1]))
        if (!found) return respond(route, { detail: '片单不存在' }, 404)
        const body = JSON.parse(request.postData() ?? '{}')
        if (body.name !== undefined) found.name = body.name
        if (body.description !== undefined) found.description = body.description
        return respond(route, queueBody(found))
      }
      if (path === '/settings' || /^\/videos\/\d+$/.test(path)) {
        return respond(route, JSON.parse(request.postData() ?? '{}'))
      }
    }

    if (method === 'DELETE') {
      const queueTakeOut = /^\/watchlists\/(\d+)\/videos\/(\d+)$/.exec(path)
      if (queueTakeOut) {
        const found = findQueue(Number(queueTakeOut[1]))
        if (!found) return respond(route, { detail: '片单不存在' }, 404)
        found.video_ids = found.video_ids.filter((id) => id !== Number(queueTakeOut[2]))
        return respond(route, queueBody(found))
      }
      const queueErase = /^\/watchlists\/(\d+)$/.exec(path)
      if (queueErase) {
        const index = queues.findIndex((list) => list.id === Number(queueErase[1]))
        if (index === -1) return respond(route, { detail: '片单不存在' }, 404)
        queues.splice(index, 1)
        return route.fulfill({ status: 204, body: '' })
      }
      const videoRow = /^\/videos\/(\d+)$/.exec(path)
      if (videoRow) {
        const id = Number(videoRow[1])
        const known = [...aliveVideos(), ...aliveCopies()].some((video) => video.id === id)
        if (!known) {
          return respond(route, { detail: '视频不存在' }, 404)
        }
        removedVideos.add(id)
        return route.fulfill({ status: 204, body: '' })
      }
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
