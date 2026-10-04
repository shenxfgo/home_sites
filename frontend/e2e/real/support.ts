/**
 * 真后端 e2e 各文件共用的那几行接线：登录、带 cookie 发请求、非 GET 的那个头。
 *
 * 单独成一个文件而不是在两份 spec 里各抄一遍：这套用例的"顺序即约定"本来就要求它们
 * 共用同一次播种，登录怎么走、响应怎么读如果两边各有一份实现，改页面时只会红一处。
 *
 * `beforeEach(signIn)` **不在这里注册**：根级钩子只挂在"第一个 import 到本模块的那个文件"
 * 上（模块会被缓存，第二个文件的 import 不会再执行一次），实测结果是单独 `-g` 跑每个文件
 * 都绿、整跑时后面那个文件的页面停在 about:blank 上、连 fetch 的相对地址都拼不出来。
 * 所以每个 spec 自己写那一行。
 */
import { expect, type Page } from '@playwright/test'

import { E2E_PASSWORD, E2E_USERNAME } from './env'

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
