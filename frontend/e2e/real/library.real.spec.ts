/**
 * 打真后端的 e2e：没有一条 `page.route`，请求全部走完 Vite 代理 → uvicorn → PostgreSQL。
 *
 * 这套用例存在的理由是替身夹具补不上的一环：替身把响应形状写在了前端测试里，前端和后端
 * 各自对着自己那份理解测试，中间没人签字。这里验的正是中间那层——真扫描产出的行、真
 * FFmpeg 封面、真 SRT→WebVTT 转换、真 Range 分段、真写进库的收藏。
 *
 * 数据来自 `backend/src/e2e_seed.py` 的一次性播种，长这样（真库实测）：id=1、片名
 * `e2e sample`、时长 30 秒、1882 字节的 H.264 片段、一条 lang=zh 的 sidecar 字幕。
 * 一轮只 TRUNCATE 一次，所以三条用例是接力而不是各自重启——顺序即约定。
 */
import { expect, test, type Page } from '@playwright/test'

import { E2E_PASSWORD, E2E_USERNAME } from './env'

async function signIn(page: Page): Promise<void> {
  await page.goto('/login')
  await page.locator('#login-username').fill(E2E_USERNAME)
  await page.locator('#login-password').fill(E2E_PASSWORD)
  await page.locator('.submit').click()
  await expect(page).toHaveURL(/\/$/)
}

test.beforeEach(async ({ page }) => {
  await signIn(page)
})

/** 在页面里发请求，凭的是浏览器刚从真登录接口拿到的那张 cookie。 */
async function fetchInPage(
  page: Page,
  path: string,
  headers: Record<string, string> = {},
): Promise<{ status: number; contentType: string; contentRange: string | null; bytes: number; text: string }> {
  return page.evaluate(
    async ({ path, headers }) => {
      const response = await fetch(path, { headers })
      const body = await response.arrayBuffer()
      return {
        status: response.status,
        contentType: response.headers.get('content-type') ?? '',
        contentRange: response.headers.get('content-range'),
        bytes: body.byteLength,
        text: new TextDecoder().decode(body),
      }
    },
    { path, headers },
  )
}

test('真表单登录后，首页渲染出扫描出来的那一行', async ({ page }) => {
  await expect(page.locator('.top-nav')).toBeVisible()
  // 顶栏写的是真库里的 display_name，不是替身里的 Tester
  await expect(page.locator('.user-name')).toHaveText('E2E')

  await expect(page.locator('.hero-sub')).toHaveText('共 1 个视频，挑一部开始今天的观影吧')

  const card = page.locator('.video-card')
  await expect(card).toHaveCount(1)
  await expect(card.first()).toContainText('e2e sample')
  await expect(card.locator('.duration-badge')).toHaveText('0:30')

  // 封面是真 FFmpeg 抽帧出来的图，不是 1x1 的替身像素
  const thumb = card.locator('img.thumbnail-img')
  await expect(thumb).toHaveAttribute('src', '/api/videos/1/thumbnail')
  await expect(thumb).toHaveJSProperty('naturalWidth', 320)

  await card.first().click()
  await expect(page).toHaveURL(/\/videos\/1$/)
})

test('详情页的字幕轨来自真转换，媒体接口按 Range 分段返回', async ({ page }) => {
  await page.goto('/videos/1')
  await page.locator('.preview-area').click()
  await expect(page.locator('.video-player')).toBeVisible()

  const track = page.locator('video track')
  await expect(track).toHaveCount(1)
  await expect(track).toHaveAttribute('src', '/api/videos/1/subtitles/1/stream')
  await expect(track).toHaveAttribute('srclang', 'zh')
  await expect(page.locator('.subtitle-btn')).toBeVisible()

  // 浏览器只会请求 <track> 的 src，拿到的必须是转换后的 WebVTT，而不是原始 SRT
  const vtt = await fetchInPage(page, '/api/videos/1/subtitles/1/stream')
  expect(vtt.status).toBe(200)
  expect(vtt.contentType).toContain('text/vtt')
  expect(vtt.text).toContain('WEBVTT')
  expect(vtt.text).toContain('E2E subtitle line')
  expect(vtt.text).not.toContain(',500 -->')

  // 整段取回：后端报得出总长，才谈得上分段
  const full = await fetchInPage(page, '/api/videos/1/stream')
  expect(full.status).toBe(200)
  expect(full.contentType).toContain('video/mp4')

  const head = await fetchInPage(page, '/api/videos/1/stream', { Range: 'bytes=0-99' })
  expect(head.status).toBe(206)
  expect(head.bytes).toBe(100)
  expect(head.contentRange).toBe(`bytes 0-99/${full.bytes}`)

  // 贴着片尾的一小段：起止都对得上，长度不是凑出来的
  const tail = await fetchInPage(page, '/api/videos/1/stream', {
    Range: `bytes=${full.bytes - 8}-${full.bytes - 1}`,
  })
  expect(tail.status).toBe(206)
  expect(tail.bytes).toBe(8)
  expect(tail.contentRange).toBe(`bytes ${full.bytes - 8}-${full.bytes - 1}/${full.bytes}`)
})

test('收藏写进真库，刷新后仍在，收藏页读得到同一行', async ({ page }) => {
  await page.goto('/videos/1')

  // 顶栏那枚导航按钮也叫「收藏」，所以按钮一律从详情页的操作区里取
  const favButton = page.locator('.action-buttons').getByRole('button', { name: '收藏', exact: true })
  // 库是刚清空的，所以第一次进来一定是「收藏」
  await expect(favButton).toBeVisible()
  await favButton.click()
  await expect(page.locator('.el-message--success')).toContainText('已添加到收藏')

  await page.reload()
  await expect(
    page.locator('.action-buttons').getByRole('button', { name: '已收藏', exact: true }),
  ).toBeVisible()

  await page.goto('/favorites')
  const cards = page.locator('.favorite-card')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('e2e sample')

  // 后端那侧的计数和页面看到的是同一个数，说明页面读的就是库里那一行
  const list = await fetchInPage(page, '/api/favorites')
  expect(JSON.parse(list.text).total).toBe(1)
})
