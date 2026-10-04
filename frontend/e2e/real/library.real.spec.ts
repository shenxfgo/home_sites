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

/** 和 `Home.vue` 里那份 `formatDuration` 同形：不足一小时写 `M:SS`。 */
function mmss(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

/** 后端抄在影片上的那一列，两个页面各自把它格式化成人看得懂的东西。 */
interface ProgressRow {
  id: number
  title: string
  duration: number
  progress: number | null
}

test('继续观看那条轨读的是真历史行：剩的秒数和进度条都由库里那一行算出来', async ({ page }) => {
  // 期望值先问后端要，不往用例里抄第二个 18——播种改了这个数，这条用例跟着动，
  // 而不是变成一个"页面对、常量错"的假红。
  const rail = await fetchInPage(page, '/api/history/continue')
  expect(rail.status).toBe(200)
  const [row] = JSON.parse(rail.text) as ProgressRow[]
  expect(row).toBeDefined()
  expect(row.title).toBe('e2e sample')
  expect(row.progress).not.toBeNull()
  // 没看完才会进这条轨：completed 那一列是 is_completed() 算的，这里只核对它的结果
  expect(row.progress!).toBeGreaterThan(0)
  expect(row.progress!).toBeLessThan(row.duration)

  await page.goto('/')
  const resume = page.locator('.resume-rail')
  await expect(resume).toBeVisible()
  await expect(resume.locator('.rail-count')).toHaveText('1 部没看完')
  const item = resume.locator('.rail-item')
  await expect(item).toHaveCount(1)
  await expect(item.locator('.rail-caption')).toHaveText(row.title)
  await expect(item.locator('.rail-remaining')).toHaveText(
    `剩 ${mmss(row.duration - row.progress!)}`,
  )

  // 进度条是内联样式，宽度按百分比给；浏览器算成 px 之后还要跟着容器变，所以读样式
  // 串里的数字，而不是拿 px 去比。
  const fill = item.locator('.rail-bar-fill')
  const width = await fill.evaluate((el) => (el as HTMLElement).style.width)
  expect(Math.round(Number.parseFloat(width))).toBe(
    Math.round((row.progress! / row.duration) * 100),
  )

  await item.click()
  await expect(page).toHaveURL(/\/videos\/1$/)

  // 同一行在 /history 上也要读得出来：两处吃的是同一个端点，替身夹具里那份形状就是在
  // 这里和真后端对账的。
  await page.goto('/history')
  const card = page.locator('.continue-card')
  await expect(card).toHaveCount(1)
  await expect(card.locator('.continue-title')).toHaveText(row.title)
  await expect(card.locator('.continue-meta')).toContainText(mmss(row.duration))
})

test('片单页把播种的队列连"已看"一起渲染，从详情页新建的那条也进库', async ({ page }) => {
  // 契约里最容易漏的一条：片单的条目也带着**这个账号**的观看位置，页面才有话可写。
  // 替身夹具给不给这一列，前端都不会红；真后端不给才会。
  const queue = await fetchInPage(page, '/api/watchlists/1')
  expect(queue.status).toBe(200)
  const list = JSON.parse(queue.text) as {
    name: string
    description: string | null
    items: ProgressRow[]
  }
  expect(list.items).toHaveLength(1)
  expect(list.items[0].progress).not.toBeNull()

  await page.goto('/watchlists')
  await expect(page.locator('.page-meta')).toHaveText('1 个片单 · 1 条排队')
  const panel = page.locator('.list-panel')
  await expect(panel).toHaveCount(1)
  await expect(panel.locator('.list-name')).toHaveText(list.name)
  // 说明是从库里那一行读出来的：播种只写了后端，页面能显示它就说明这一列真的在接口里。
  expect(list.description).toBe('真后端 e2e 播的那一条')
  await expect(panel.locator('.list-desc')).toHaveText(list.description!)
  await expect(panel.locator('.queue-title')).toHaveText(list.items[0].title)
  await expect(panel.locator('.queue-meta')).toContainText(`已看 ${mmss(list.items[0].progress!)}`)

  // 真写一次：从详情页的「片单」弹窗里新建一条并直接把这部片子放进去，写的是真库。
  await page.goto('/videos/1')
  await page.locator('.action-buttons').getByRole('button', { name: '片单', exact: true }).click()
  const dialog = page.locator('.el-dialog', { hasText: '加入片单' })
  await expect(dialog).toBeVisible()
  await dialog.locator('.watchlist-new input').fill('周末再看')
  await dialog.getByRole('button', { name: '保存' }).click()
  await expect(page.locator('.el-message--success')).toBeVisible()

  await page.goto('/watchlists')
  await expect(page.locator('.page-meta')).toHaveText('2 个片单 · 2 条排队')
  const created = page.locator('.list-panel', { hasText: '周末再看' })
  await expect(created.locator('.queue-title')).toHaveText('e2e sample')

  // 页面说的两个数，库里确实是两个数——不是前端把刚点的那一下乐观地留在了内存里
  const after = await fetchInPage(page, '/api/watchlists')
  const all = JSON.parse(after.text) as { id: number; items: unknown[] }[]
  expect(all).toHaveLength(2)
  expect(all.reduce((sum, entry) => sum + entry.items.length, 0)).toBe(2)
})
