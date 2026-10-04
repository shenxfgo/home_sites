/**
 * 真后端 e2e 各文件共用的那几行接线：登录、带 cookie 发请求、非 GET 的那个头、扫描一个源、
 * 以及把封面目录拍成一张可比对的清单。
 *
 * 单独成一个文件而不是在几份 spec 里各抄一遍：这套用例的"顺序即约定"本来就要求它们
 * 共用同一次播种，登录怎么走、响应怎么读如果两边各有一份实现，改页面时只会红一处。
 *
 * `beforeEach(signIn)` **不在这里注册**：根级钩子只挂在"第一个 import 到本模块的那个文件"
 * 上（模块会被缓存，第二个文件的 import 不会再执行一次），实测结果是单独 `-g` 跑每个文件
 * 都绿、整跑时后面那个文件的页面停在 about:blank 上、连 fetch 的相对地址都拼不出来。
 * 所以每个 spec 自己写那一行。
 */
import { expect, type Page } from '@playwright/test'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { join, sep } from 'node:path'

import { E2E_PASSWORD, E2E_USERNAME, THUMBNAIL_DIR } from './env'

/** 非 GET 都要带这个头，中间件先查它再查角色（顺序写在 `middleware/auth.py`）。 */
export const CSRF = { 'x-requested-with': 'fetch' }

/** 起步就是"已登录的 owner"；要换身份的用例自己再 signIn 一次。钩子写在每个 spec 文件
 * 自己身上（理由见文件头），这里只给函数。 */
export async function signIn(page: Page, username: string = E2E_USERNAME): Promise<void> {
  // 先交出手里那张 cookie：/login 对已登录的人是直接送回首页的，表单压根不渲染（真库实测
  // 过一次 30 秒超时）。一轮里要换两次身份，所以这一步写在函数里而不是每个调用点抄一遍。
  await page.context().clearCookies()
  await page.goto('/login')
  await page.locator('#login-username').fill(username)
  await page.locator('#login-password').fill(E2E_PASSWORD)
  await page.locator('.submit').click()
  await expect(page).toHaveURL(/\/$/)
}

export interface InPageResponse {
  status: number
  contentType: string
  contentRange: string | null
  bytes: number
  text: string
}

/** 在页面里发请求，凭的是浏览器刚从真登录接口拿到的那张 cookie。 */
export async function fetchInPage(
  page: Page,
  path: string,
  init: {
    headers?: Record<string, string>
    method?: string
    body?: string
  } = {},
): Promise<InPageResponse> {
  return page.evaluate(
    async ({ path, init }) => {
      const response = await fetch(path, init)
      const body = await response.arrayBuffer()
      return {
        status: response.status,
        contentType: response.headers.get('content-type') ?? '',
        contentRange: response.headers.get('content-range'),
        bytes: body.byteLength,
        text: new TextDecoder().decode(body),
      }
    },
    { path, init },
  )
}

/** 发一个 JSON 请求并把响应里的 JSON 读回来（状态码先核对，非 2xx 一律当场失败）。 */
export async function requestJson<T>(
  page: Page,
  path: string,
  options: { method?: string; body?: unknown; expectStatus?: number } = {},
): Promise<T> {
  const expectStatus = options.expectStatus ?? 200
  const response = await fetchInPage(page, path, {
    method: options.method ?? 'GET',
    headers:
      options.body === undefined
        ? CSRF
        : { ...CSRF, 'content-type': 'application/json' },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  expect(response.status, `${path} -> ${response.text.slice(0, 300)}`).toBe(expectStatus)
  return (response.status === 204 ? null : (JSON.parse(response.text) as T)) as T
}

/**
 * 缩略图目录下每个 `.jpg` 的「相对路径 + 内容 sha1」，排序后逐项可比。
 *
 * 名字集合挡住"文件被删掉了"，也挡住"文件写到了别处"：封面路径是
 * `<root>/<source_id>/<stem>-<locator 摘要>.jpg`，行如果被删掉重扫，新的那行拿到的是
 * 另一个 id，于是目录名跟着变，这一份列表就多出（或少掉）一项。内容哈希只多一道保险，
 * 承担不起"证明没重编码"这种说法——同一份输入重编码出来的字节本来就可能一致。
 *
 * 两个 spec 都要它，所以住在这里：一个是"扫描不该动别人的封面"，一个是"删除只该动自己
 * 那一张"，两边读的是同一个目录、同一份算法。
 */
export function coverFingerprints(): string[] {
  if (!existsSync(THUMBNAIL_DIR)) return []
  return readdirSync(THUMBNAIL_DIR, { recursive: true })
    .map((entry) => String(entry).split(sep).join('/'))
    .filter((name) => name.toLowerCase().endsWith('.jpg'))
    .map(
      (name) =>
        `${name} ${createHash('sha1').update(readFileSync(join(THUMBNAIL_DIR, name))).digest('hex')}`,
    )
    .sort()
}

/**
 * 扫一个源，只取它报的四个计数。
 *
 * 挑字段而不是 `toEqual` 整个对象：单个源的扫描和 `/api/sources/scan`（全部源）共用同一份
 * 响应模型，那一侧才有的 `sources_scanned` / `total_*` 在这里全是 null。照整个对象写死，断言
 * 就成了「响应模型今天有哪几个键」，多一个键就红，而那和这条用例要验的事无关。
 *
 * `foreign_paths` 也不在这里：服务层那个 dict 里有，`ScanResult` 没把它带过 HTTP 边界，
 * 所以浏览器永远读不到它（第一版照抄服务层的形状，红在这里）。
 */
export type ScanCounters = {
  files_found: number
  new_videos: number
  subtitles_found: number
}

export async function scanSource(page: Page, sourceId: number): Promise<ScanCounters> {
  const body = await requestJson<ScanCounters & { source_id: number }>(
    page,
    `/api/sources/${sourceId}/scan`,
    { method: 'POST' },
  )
  expect(body.source_id).toBe(sourceId)
  return {
    files_found: body.files_found,
    new_videos: body.new_videos,
    subtitles_found: body.subtitles_found,
  }
}
