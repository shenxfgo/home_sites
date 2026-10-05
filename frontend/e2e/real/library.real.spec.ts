/**
 * 打真后端的 e2e：没有一条 `page.route`，请求全部走完 Vite 代理 → uvicorn → PostgreSQL。
 *
 * 这套用例存在的理由是替身夹具补不上的一环：替身把响应形状写在了前端测试里，前端和后端
 * 各自对着自己那份理解测试，中间没人签字。这里验的正是中间那层——真扫描产出的行、真
 * FFmpeg 封面、真 SRT→WebVTT 转换、真 Range 分段、真写进库的收藏，真角色闸门
 * （替身夹具那份 `MEMBER_WRITE` 名单是从后端抄来的，抄错也不会红，只有真中间件会），
 * 以及只在真库上才出现的**关系加载**：标签下那批影片要带着自己的 `tags` 集合回来，
 * 序列化是同步的，少预取一层就是一次 greenlet 之外的 IO（500），而替身给的是一份 JSON，
 * 没有关系可加载，永远测不到这件事。
 *
 * 数据来自 `backend/src/e2e_seed.py` 的一次性播种，长这样（真库实测）：两个账号
 * （owner `e2e_owner` + member `e2e_member`）、影片 id=1、片名 `e2e sample`、时长 30 秒、
 * 5008 字节、一条视频流外加一条 1 秒的 AAC 音轨（音轨是给转码配方的音频半边准备的，见
 * `transcode.real.spec.ts`）、一条 lang=zh 的 sidecar 字幕，外加服务层写进库的 18 秒观看
 * 进度和一条排好队的片单（member 那个账号什么都没写）。
 * 一轮只 TRUNCATE 一次，所以用例之间是接力而不是各自重启——顺序即约定。
 */
import { expect, test, type Page } from '@playwright/test'
import { existsSync, mkdirSync, renameSync } from 'node:fs'
import { join, sep } from 'node:path'

import { E2E_DIR, E2E_MEMBER_USERNAME, E2E_USERNAME, MEDIA_DIR } from './env'
// 登录、带 cookie 发请求这两件事现在住在 `support.ts`，因为打真后端的 spec 已经有两份了：
// 一个页面改了，两处都该跟着红，而不是只红一份。但钩子必须各自注册（理由见 `support.ts` 文件头）。
import { CSRF, coverFingerprints, fetchInPage, requestJson, scanSource, signIn } from './support'

test.beforeEach(async ({ page }) => {
  await signIn(page)
})

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

  const head = await fetchInPage(page, '/api/videos/1/stream', {
    headers: { Range: 'bytes=0-99' },
  })
  expect(head.status).toBe(206)
  expect(head.bytes).toBe(100)
  expect(head.contentRange).toBe(`bytes 0-99/${full.bytes}`)

  // 贴着片尾的一小段：起止都对得上，长度不是凑出来的
  const tail = await fetchInPage(page, '/api/videos/1/stream', {
    headers: { Range: `bytes=${full.bytes - 8}-${full.bytes - 1}` },
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

  // 越界那一页的形状：200、空的一页、诚实的 total、原样回显的页码。不是 404，也不是
  // 服务端偷偷把页码改成还存在的那一页。收藏页那句「移掉最后一页的最后一个收藏就把
  // 页码钳回去」全靠这个形状才成立——`total` 说真话前端才算得出最后一页，`page` 回显
  // 才看得出它确实按请求的那一页答了。这一页在替身夹具里翻不出来：`fixtures.ts` 那份
  // `/api/favorites` 处理器根本不读 `page`。
  const beyond = await requestJson<{
    items: unknown[]
    total: number
    page: number
    page_size: number
  }>(page, '/api/favorites?page=2&page_size=20')
  expect([beyond.items.length, beyond.total, beyond.page, beyond.page_size]).toEqual([0, 1, 2, 20])
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

  // 页面说的那两个数，库里确实是那两个数——不是前端把刚点的那一下乐观地留在了内存里
  const after = await fetchInPage(page, '/api/watchlists')
  const all = JSON.parse(after.text) as { id: number; items: unknown[] }[]
  expect(all).toHaveLength(2)
  expect(all.reduce((sum, entry) => sum + entry.items.length, 0)).toBe(2)
})

test('成员账号撞的是真中间件：管理面连读都 403，库级写 403，改自己那份才通', async ({ page }) => {
  // 替身夹具里那份 MEMBER_WRITE 是后端名单的手抄本，抄歪了前端不会红（它甚至不知道自己
  // 抄的是谁的规则）。这条用例赌的就是"手抄本和原件一致"这件事。
  await signIn(page, E2E_MEMBER_USERNAME)
  await expect(page.locator('.user-name')).toHaveText('E2E 成员')

  // 界面那一层先按顺序少给入口：owner 专属的三个不在，用户菜单里也没有「用户管理」
  const labels = (await page.locator('.nav-item').allTextContents()).map((text) => text.trim())
  expect(labels).toEqual(['首页', '播放历史', '观影统计', '收藏', '片单'])
  await page.locator('.user-chip').click()
  await expect(page.locator('.user-popper button', { hasText: '用户管理' })).toHaveCount(0)

  // 手敲管理页地址只会被守卫送回首页——真正的拒绝在下面那两次请求里
  await page.goto('/settings')
  await expect(page).toHaveURL(/\/$/)

  for (const path of ['/api/users', '/api/settings']) {
    const blocked = await fetchInPage(page, path)
    expect(blocked.status, path).toBe(403)
    expect(JSON.parse(blocked.text).detail, path).toBe('需要管理员权限')
  }

  // 库级写不在名单里。刻意带上 CSRF 头：中间件是**先查那个头、再查角色**，不带头的话
  // 两条 403 长得一模一样，就分不清到底是哪一层挡的。
  const forbidden = await fetchInPage(page, '/api/videos/1', { method: 'DELETE', headers: CSRF })
  expect(forbidden.status).toBe(403)
  expect(JSON.parse(forbidden.text).detail).toBe('需要管理员权限')
  // 那一行确实没动：拒绝发生在服务层之前，不是删完了再报错
  expect((await fetchInPage(page, '/api/videos/1')).status).toBe(200)

  // 反向的一半同样要成立：名单内的写必须真通，成员这边一份收藏都没播种过，所以从 0 起
  expect(JSON.parse((await fetchInPage(page, '/api/favorites')).text).total).toBe(0)
  const added = await fetchInPage(page, '/api/favorites/1', { method: 'POST', headers: CSRF })
  expect(added.status).toBe(201)
  await page.goto('/favorites')
  await expect(page.locator('.favorite-card')).toHaveCount(1)

  // 片单名只在**本人**范围内唯一：这条和 owner 那份播种的同名片单撞不上。归属过滤要是漏了，
  // 这里回来的是 409 而不是 201，而界面照样能建——只有打真库才看得见。
  const named = await fetchInPage(page, '/api/watchlists', {
    method: 'POST',
    headers: { ...CSRF, 'content-type': 'application/json' },
    body: JSON.stringify({ name: '今晚看这些' }),
  })
  expect(named.status).toBe(201)
  const mine = JSON.parse((await fetchInPage(page, '/api/watchlists')).text) as {
    name: string
  }[]
  expect(mine.map((entry) => entry.name)).toEqual(['今晚看这些'])

  // 换回 owner：两条片单（一条播种、一条用例 5 建的）一行没多也没少，列表按 id 从旧到新；
  // 收藏那句的 1 是用例 3 点下去的那一条——成员加的那条没混进来才算隔离。
  await signIn(page, E2E_USERNAME)
  const ownerLists = JSON.parse((await fetchInPage(page, '/api/watchlists')).text) as {
    name: string
  }[]
  expect(ownerLists.map((entry) => entry.name)).toEqual(['今晚看这些', '周末再看'])
  expect(JSON.parse((await fetchInPage(page, '/api/favorites')).text).total).toBe(1)
})

/** `/api/history/stats` 的响应里这条用例真正在用的那几项。 */
type WatchStats = {
  days: number
  window_seconds: number
  videos_watched: number
  daily: { date: string; seconds: number; videos: number }[]
}

type AdminUser = { username: string; role: string; signed_in_devices: number }

test('管理面那两页的数是后台算出来的：窗口按 days 零填充，设备数来自真登录', async ({ page }) => {
  // 替身夹具里 `daily` 是前端抄的几天，`days` 这个查询参数它甚至可以不理；用户管理那格的
  // `signed_in_devices` 在替身里是个常数。这两句只有打真库才签得到。
  const month = JSON.parse((await fetchInPage(page, '/api/history/stats?days=30')).text) as WatchStats
  expect(month.days).toBe(30)
  // 零填充是真后台的承诺：窗口里每一天都得有一格，哪怕那天什么都没看（播种只写了今天）
  expect(month.daily).toHaveLength(30)
  expect(new Set(month.daily.map((entry) => entry.date)).size).toBe(30)
  expect(month.daily.filter((entry) => entry.seconds > 0).length).toBeGreaterThan(0)

  await page.goto('/stats')
  await expect(page.locator('.bar-cell')).toHaveCount(30)
  await expect(
    page.locator('.stat-card', { hasText: '看过影片' }).locator('.stat-value'),
  ).toHaveText(`${month.videos_watched} 部`)

  // 换窗口要后端真的重算：7 天窗口是 30 天窗口的子集，总时长只会更小或相等。前端自己
  // 数那 30 格永远发现不了"days 被忽略"这件事。
  await page.locator('.window-btn', { hasText: '近 7 天' }).click()
  await expect(page.locator('.bar-cell')).toHaveCount(7)
  const week = JSON.parse((await fetchInPage(page, '/api/history/stats?days=7')).text) as WatchStats
  expect(week.days).toBe(7)
  expect(week.daily).toHaveLength(7)
  expect(week.window_seconds).toBeLessThanOrEqual(month.window_seconds)

  await page.goto('/users')
  const rows = page.locator('.users-table .el-table__row')
  await expect(rows).toHaveCount(2)
  const accounts = JSON.parse((await fetchInPage(page, '/api/users')).text) as AdminUser[]
  expect(accounts.map((entry) => entry.username).sort()).toEqual(['e2e_member', 'e2e_owner'])
  // owner 此刻就登录在这台浏览器上，所以那一格至少是 1：它是中间件每次登录写下的会话行，
  // 不是接口里的默认值（`signed_in_devices: int = 0` 那个 0 就是给"没人登录"准备的）
  const owner = accounts.find((entry) => entry.username === 'e2e_owner')
  expect(owner?.signed_in_devices).toBeGreaterThanOrEqual(1)
  // 表格里「登录设备」那一列（第四格）就是接口那一个数
  for (const entry of accounts) {
    await expect(
      rows.filter({ hasText: entry.username }).first().locator('td').nth(3),
    ).toHaveText(String(entry.signed_in_devices))
  }
})

/** `GET /api/tags` 里这条用例真正在用的那几项。 */
type TagRow = { id: number; name: string; video_count: number }

test('标签挂在真影片上：两个标签各数各的视频，标签下那部片子读得到自己的标签', async ({ page }) => {
  // 播种一个标签都没建，所以建标签这一下走的是真接口；而 #101 修的那个 500（响应模型要读
  // `video.tags`，那一查却没预取第二层）只会在真库的关系加载上出现，替身夹具永远测不到。
  await page.goto('/tags')
  await page.locator('.page-header button', { hasText: '添加标签' }).click()
  const dialog = page.locator('.el-dialog')
  await dialog.locator('input[placeholder="请输入标签名称"]').fill('真库标签')
  await dialog.getByRole('button', { name: '创建' }).click()
  const firstCard = page.locator('.tag-card', { hasText: '真库标签' })
  await expect(firstCard).toHaveCount(1)
  await expect(firstCard.locator('.tag-meta')).toContainText('0 个视频')

  // 挂到扫描出来的那部影片上（界面上这个动作在详情页，这里走接口把两步分开）
  const created = JSON.parse((await fetchInPage(page, '/api/tags')).text) as TagRow[]
  const attachedId = created.find((entry) => entry.name === '真库标签')?.id
  expect(attachedId).toBeTruthy()
  const linked = await fetchInPage(page, '/api/tags/video/1', {
    method: 'POST',
    headers: { ...CSRF, 'content-type': 'application/json' },
    body: JSON.stringify({ tag_ids: [attachedId] }),
  })
  expect(linked.status).toBe(204)

  await page.reload()
  await expect(firstCard.locator('.tag-meta')).toContainText('1 个视频')

  // 第二个标签只建不挂：`video_count` 要是算成了全局的数，这里就会跟着变成"1 个视频"。
  // （期望写成映射而不是数组：`GET /api/tags` 按名字排，而中文在 PG 与 SQLite 上的排序
  // 规则不保证一致，这条两边都要能过。）
  const second = await fetchInPage(page, '/api/tags', {
    method: 'POST',
    headers: { ...CSRF, 'content-type': 'application/json' },
    body: JSON.stringify({ name: '没挂过片子的标签' }),
  })
  expect(second.status).toBe(201)
  await page.reload()
  await expect(
    page.locator('.tag-card', { hasText: '没挂过片子的标签' }).locator('.tag-meta'),
  ).toContainText('0 个视频')

  const rows = JSON.parse((await fetchInPage(page, '/api/tags')).text) as TagRow[]
  expect(Object.fromEntries(rows.map((entry) => [entry.name, entry.video_count]))).toEqual({
    真库标签: 1,
    没挂过片子的标签: 0,
  })

  // 这一句是那单的回归位置：状态码必须还是 200，而那部片子带着自己的标签集合回来
  const videos = await fetchInPage(page, `/api/tags/${attachedId}/videos`)
  expect(videos.status).toBe(200)
  const listed = JSON.parse(videos.text) as { id: number; title: string; tags: { id: number }[] }[]
  expect(listed.map((entry) => [entry.id, entry.title])).toEqual([[1, 'e2e sample']])
  expect(listed[0]?.tags.map((entry) => entry.id)).toEqual([attachedId])
})

/** `GET /api/notifications` 里这条用例真正在用的那几项。 */
type NotificationRow = {
  id: number
  type: string
  title: string
  message: string
  read: boolean
  data: { source_id: number; new_count: number; subtitles_found: number; missing_changed: number }
}
type NotificationList = { items: NotificationRow[]; total: number }

async function readNotifications(page: Page): Promise<NotificationList> {
  return JSON.parse((await fetchInPage(page, '/api/notifications')).text) as NotificationList
}

test('通知是广播的、已读是按人的：同批文件再扫一遍零新增就一句都不发', async ({ page }) => {
  // 起点是播种那趟**真扫描**留下的那一行，不是夹具里手抄的文案：句末那两个数是
  // `scan_source` 的计数器（`new_videos` / `subtitles_found`），而 `data` 那一列是
  // JSON 列在真库上的往返——替身夹具两样都给不了。
  const seeded = await readNotifications(page)
  expect(seeded.total).toBe(1)
  const only = seeded.items[0]
  expect(only?.type).toBe('scan_complete')
  expect(only?.read).toBe(false)
  expect(only?.message).toContain('发现 1 个新视频')
  expect(only?.message).toContain('1 条字幕')
  expect(only?.data).toEqual({ source_id: 1, new_count: 1, subtitles_found: 1, missing_changed: 0 })

  // 铃铛：角标是未读数，弹层里那一行就是库里那一行
  await expect(page.locator('.notification-badge .el-badge__content')).toHaveText('1')
  await page.locator('.notification-badge button').click()
  const popper = page.locator('.notification-popper')
  await expect(popper.locator('.notification-item')).toHaveCount(1)
  await expect(popper.locator('.notification-item')).toHaveClass(/unread/)
  await expect(popper.locator('.notification-title')).toHaveText('扫描完成')
  await expect(popper.locator('.notification-message')).toContainText('发现 1 个新视频')

  // #85 的回归位置：文件一个没变，再扫一遍的计数全为 0，于是一条通知都不许多出来。
  // 这一句只有打真库才成立——替身那侧"扫不扫都回同一份列表"本来就是自洽的。
  const rescan = await fetchInPage(page, '/api/sources/1/scan', { method: 'POST', headers: CSRF })
  expect(rescan.status).toBe(200)
  const counted = JSON.parse(rescan.text) as { files_found: number; new_videos: number; subtitles_found: number }
  // 文件确实被扫到了（不是"扫了个空目录所以当然没新增"），但库没变
  expect(counted.files_found).toBe(1)
  expect(counted.new_videos).toBe(0)
  expect(counted.subtitles_found).toBe(0)
  expect((await readNotifications(page)).total).toBe(1)

  // 已读写成真库的一行：点「全部已读」之后**刷新**再读，界面和接口都得到同一个 read=true
  // （不刷新就只证明了前端那句乐观更新）。
  await popper.getByRole('button', { name: '全部已读' }).click()
  await page.reload()
  expect((await readNotifications(page)).items[0]?.read).toBe(true)
  expect(
    JSON.parse((await fetchInPage(page, '/api/notifications/unread')).text) as { count: number },
  ).toEqual({ count: 0 })

  // 反向的一半才说明这不是全局开关：换成员登录，**同一条**通知还在（feed 是广播的），
  // 但那一行对他仍是未读——`notification_reads` 的主键是 (notification_id, user_id)。
  await signIn(page, E2E_MEMBER_USERNAME)
  const memberView = await readNotifications(page)
  expect(memberView.total).toBe(1)
  expect(memberView.items[0]?.id).toBe(only?.id)
  expect(memberView.items[0]?.read).toBe(false)
  expect(
    JSON.parse((await fetchInPage(page, '/api/notifications/unread')).text) as { count: number },
  ).toEqual({ count: 1 })

  // 成员能改自己的已读状态，但清空整条流是库级动作，不在中间件那份名单里
  const denied = await fetchInPage(page, '/api/notifications', { method: 'DELETE', headers: CSRF })
  expect(denied.status).toBe(403)
  expect((await readNotifications(page)).total).toBe(1)
})

/** `GET /api/sources` 里这条用例真正在用的那几项。 */
type SourceRow = {
  id: number
  name: string
  path: string
  type: string
  is_active: boolean
  scan_interval: number
  last_scan_at: string | null
}

async function readSources(page: Page): Promise<SourceRow[]> {
  return JSON.parse((await fetchInPage(page, '/api/sources')).text) as SourceRow[]
}

test('同一个目录挂两个源：扫它不出重复片，删它不伤第一个源那部片子', async ({ page }) => {
  // `videos.filepath` 是全库唯一的，所以"两个源指向同一个目录"这件事只有真库能回答：
  // 替身给不出一次唯一约束冲突，也给不出一个"服务端刚写上去"的扫描时刻。
  const [seeded] = await readSources(page)
  expect(seeded?.name).toBe('E2E local')
  expect(seeded?.type).toBe('local')
  expect(seeded?.is_active).toBe(true)
  expect(seeded?.scan_interval).toBe(3600)
  // 播种那趟真扫描盖的时间戳（`scan_service.py:330`），界面上那一格因此不是「从未」
  expect(seeded?.last_scan_at).not.toBeNull()

  await page.goto('/sources')
  const firstCard = page.locator('.source-card', { hasText: 'E2E local' })
  await expect(firstCard).toHaveCount(1)
  await expect(firstCard.locator('.path-value')).toHaveText(seeded?.path ?? '')
  await expect(firstCard.locator('.info-row', { hasText: '上次扫描' })).not.toContainText('从未')

  // 第二个源指向**同一个目录**——真库里那两个源就是这么来的（#102 的现场形状）
  await page.locator('.page-header button', { hasText: '添加视频源' }).click()
  const dialog = page.locator('.el-dialog')
  await dialog.locator('input[placeholder="例如：我的NAS"]').fill('E2E 同目录')
  await dialog.locator('input[placeholder^="例如：/mnt/videos"]').fill(seeded?.path ?? '')
  await dialog.getByRole('button', { name: '创建' }).click()
  await expect(page.locator('.source-card')).toHaveCount(2)

  const sources = await readSources(page)
  const second = sources.find((entry) => entry.name === 'E2E 同目录')
  const secondId = second?.id
  expect(secondId).toBeTruthy()
  expect(second?.path).toBe(seeded?.path)
  expect(second?.last_scan_at).toBeNull()

  // 扫第二个源：那部片子已经属于源 1，路径撞在全库唯一约束上，于是一行都不许多
  const scanned = await fetchInPage(page, `/api/sources/${secondId}/scan`, {
    method: 'POST',
    headers: CSRF,
  })
  expect(scanned.status).toBe(200)
  const counted = JSON.parse(scanned.text) as { files_found: number; new_videos: number }
  expect(counted.files_found).toBe(1) // 文件确实被看到了，不是"扫了个空目录所以当然没新增"
  expect(counted.new_videos).toBe(0)

  // 时间戳只盖在被扫的那一个源上（源 1 那一格还是播种时的同一个值，精确到字符串）
  const afterScan = await readSources(page)
  expect(afterScan.find((entry) => entry.id === secondId)?.last_scan_at).not.toBeNull()
  expect(afterScan.find((entry) => entry.id === 1)?.last_scan_at).toBe(seeded?.last_scan_at)

  const library = JSON.parse((await fetchInPage(page, '/api/videos')).text) as {
    total: number
    items: { id: number; title: string; source_id: number }[]
  }
  expect(library.total).toBe(1)
  // 归属没被第二个源抢走，也没多出一条重复的行
  expect(library.items.map((entry) => [entry.id, entry.title, entry.source_id])).toEqual([
    [1, 'e2e sample', 1],
  ])

  // 删掉第二个源（界面上要过确认框）：第一个源那部片子和**磁盘上那张封面**都不能受牵连
  // ——删除视频源那条路径出过 500，而"删源的时候把封面文件也删了"是另一单修过的。
  const cover = await fetchInPage(page, '/api/videos/1/thumbnail')
  expect(cover.status).toBe(200)
  expect(cover.bytes).toBeGreaterThan(0)

  await page.reload()
  await page
    .locator('.source-card', { hasText: 'E2E 同目录' })
    .getByRole('button', { name: '删除' })
    .click()
  await page.locator('.el-message-box').getByRole('button', { name: '删除' }).click()
  await expect(page.locator('.source-card')).toHaveCount(1)

  const afterDelete = JSON.parse((await fetchInPage(page, '/api/videos')).text) as { total: number }
  expect(afterDelete.total).toBe(1)
  const coverAfter = await fetchInPage(page, '/api/videos/1/thumbnail')
  expect(coverAfter.status).toBe(200)
  expect(coverAfter.bytes).toBe(cover.bytes)
  const remaining = await readSources(page)
  expect(remaining.map((entry) => entry.name)).toEqual(['E2E local'])
})

/** `GET /api/settings` 读的全部五项——设置页渲染的就是这份形状。 */
type SystemSettings = {
  auto_scan_enabled: boolean
  auto_scan_interval: number
  default_transcode_format: string
  thumbnail_width: number
  thumbnail_height: number
}

async function readSettings(page: Page): Promise<SystemSettings> {
  return JSON.parse((await fetchInPage(page, '/api/settings')).text) as SystemSettings
}

test('系统配置写进真库再读回来：PUT 的回显不算数，一次坏写入也不再打坏整页', async ({ page }) => {
  // `settings` 表播种从不写，所以开头那五项是**代码默认值经过一次 Text→int/bool 强制转换**
  // 之后读回来的样子；而 `PUT /api/settings` 回的是请求体本身，于是"保存成功"和"库里到底
  // 有没有那一行"在替身夹具里是同一件事。这里要把它分开：改完必须换一路读才作数。
  const defaults: SystemSettings = {
    auto_scan_enabled: true,
    auto_scan_interval: 3600,
    default_transcode_format: 'mp4',
    thumbnail_width: 320,
    thumbnail_height: 180,
  }
  expect(await readSettings(page)).toEqual(defaults)

  // 先把两个数字键写成**非默认值**（走单键 PUT，顺带证明那条路径真的落库）。默认值留着
  // 的话最后那句"被拒的写入没有落地"就没有对照——那一格本来就是 320，改成"不落地"也还是
  // 320。注意它**不能**反过来抓"整份保存漏写了一个键"：漏写只是不再覆盖，库里留的是上一次的
  // 值，不是代码默认值（这一条是变异试出来的：漏写 thumbnail_height 全绿，漏写界面真改过的
  // auto_scan_interval 才红）。
  for (const [key, value] of [
    ['thumbnail_width', '640'],
    ['thumbnail_height', '480'],
  ] as const) {
    const written = await fetchInPage(page, `/api/settings/${key}`, {
      method: 'PUT',
      headers: { ...CSRF, 'content-type': 'application/json' },
      body: JSON.stringify({ value }),
    })
    expect(written.status).toBe(200)
  }
  expect(await readSettings(page)).toEqual({ ...defaults, thumbnail_width: 640, thumbnail_height: 480 })

  await page.goto('/settings')
  const form = page.locator('.el-form-item', { hasText: '扫描间隔' })
  await expect(page.locator('.settings-card')).toHaveCount(3)
  await expect(form).toContainText('每小时') // 界面给的是 label，3600 在 value 里
  await expect(page.locator('.el-form-item', { hasText: '自动扫描' }).locator('.el-switch')).toHaveClass(/is-checked/)

  await form.locator('.el-select').click()
  await page.locator('.el-select-dropdown__item', { hasText: '每 2 小时' }).click()
  await page.locator('.el-form-item', { hasText: '自动扫描' }).locator('.el-switch').click()
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.locator('.el-message')).toContainText('设置已保存')

  // 这一路读才算数：`PUT` 那份回显只是把请求体原样送回。界面上没动过的那两格要还带着
  // 640 / 480，说明整份保存把它们一起写回来了（而不是又写了一遍默认值）。
  const saved: SystemSettings = {
    auto_scan_enabled: false,
    auto_scan_interval: 7200,
    default_transcode_format: 'mp4',
    thumbnail_width: 640,
    thumbnail_height: 480,
  }
  expect(await readSettings(page)).toEqual(saved)
  // 库里那一格是 Text 列，读回来才是数字 7200——这一层强制转换只在真库上存在
  const raw = JSON.parse((await fetchInPage(page, '/api/settings/auto_scan_interval')).text) as {
    key: string
    value: string
  }
  expect(raw).toEqual({ key: 'auto_scan_interval', value: '7200' })

  await page.reload()
  await expect(page.locator('.el-form-item', { hasText: '扫描间隔' })).toContainText('每 2 小时')
  await expect(page.locator('.el-form-item', { hasText: '自动扫描' }).locator('.el-switch')).not.toHaveClass(/is-checked/)

  // 本单的修复：单键 PUT 认键名，原先不认值。写一个 `GET` 读不回来的字符串进去，
  // 设置页从此 500，直到有人手工去改那一行。
  const poisoned = await fetchInPage(page, '/api/settings/thumbnail_width', {
    method: 'PUT',
    headers: { ...CSRF, 'content-type': 'application/json' },
    body: JSON.stringify({ value: 'not-a-number' }),
  })
  expect(poisoned.status).toBe(400)
  expect(poisoned.text).toContain('必须是整数')
  expect(await readSettings(page)).toEqual(saved)
})

/** `GET /api/videos` 里这条用例真正在用的那几项。 */
type VideoRow = { id: number; title: string; is_missing: boolean }
type VideoList = { items: VideoRow[]; total: number; page: number; page_size: number }

async function readVideos(page: Page, query = ''): Promise<VideoList> {
  return JSON.parse((await fetchInPage(page, `/api/videos${query}`)).text) as VideoList
}

/** 建一个标签，顺手挂在某部影片上，返回它的 id。 */
async function createTag(page: Page, name: string, videoId: number | null): Promise<number> {
  const created = await fetchInPage(page, '/api/tags', {
    method: 'POST',
    headers: { ...CSRF, 'content-type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  expect(created.status).toBe(201)
  const id = (JSON.parse(created.text) as TagRow).id
  if (videoId !== null) {
    const linked = await fetchInPage(page, `/api/tags/video/${videoId}`, {
      method: 'POST',
      headers: { ...CSRF, 'content-type': 'application/json' },
      body: JSON.stringify({ tag_ids: [id] }),
    })
    expect(linked.status).toBe(204)
  }
  return id
}

/**
 * 在界面上搜一个词，同时核对三处：卡片数、服务器对同一个词报的 total、地址栏里那个词。
 *
 * 收成一个函数不是为了省字，而是因为这条用例的断言本身就是"三处得是同一件事"——分开
 * 抄十几遍，总有一遍会只核对其中两处。替身夹具对这种松动无感：`fixtures.ts` 里那份
 * `matchesSearch` 是拿 TypeScript 把后端的 `src/utils/video_search.py` 又实现了一遍，
 * 两份实现各自测自己那一侧，谁改了对方都不知道。
 */
async function expectSearch(page: Page, text: string, expected: number): Promise<void> {
  await page.locator('.search-input input').fill(text)
  // 先等地址栏：它是那 400ms 防抖之后第一件事。卡片数在"结果没变"的那些探针上不会动，
  // 拿它当同步点会当场通过而什么都没等到（第一次跑就是这么撞上的）。
  await expect
    .poll(() => new URL(page.url()).searchParams.get('q'))
    .toBe(text.trim() || null)
  await expect(page.locator('.video-card')).toHaveCount(expected)
  // 换一路读：服务器对**同一个字符串**报的数，和界面渲染的必须是同一件事
  const list = await readVideos(page, `?search=${encodeURIComponent(text)}`)
  expect([list.total, list.items.length]).toEqual([expected, expected])
  await expect(page.locator('.hero-sub')).toContainText(`共 ${expected} 个视频`)
}

test('搜索框那一个文本框打到真解析器上：算子、通配符和越界的页码', async ({ page }) => {
  // 首页那一个文本框后面是一整套算子（`标签:` `源:` 比较式 观看状态），界面上那个 `?`
  // 弹层还把语法一条条写给用户看。替身那侧另有一份 TS 实现，所以两边各自自洽；这里验的
  // 是浏览器打出来的那一串字符经过 URL 编码、FastAPI 的参数解析和一次真 ILIKE 之后仍认得，
  // 夹具自己永远给不出"编码坏了但两边都说 0"这种情况。
  // 夹具自己建（不借第 8 条留下的标签）：这样它能单独 `-g 搜索框` 跑，改一处后端大约
  // 二十秒出结论，不用先把前面十一条用例的播种链走一遍。
  const attachedTagId = await createTag(page, '深夜标签', 1)
  const looseTagId = await createTag(page, '无人挂载', null)

  await page.goto('/')
  await expect(page.locator('.video-card')).toHaveCount(1)

  // 片名命中，加上**只有真库给得出的两件事**：ILIKE 不区分大小写（替身是 toLowerCase +
  // includes，换一种方言的 collation 又是另一套），以及 `深夜` 这个词在片名和简介里都不
  // 存在，命中走的是一条标签名的 EXISTS。
  await expectSearch(page, 'e2e', 1)
  await expectSearch(page, 'E2E SAMPLE', 1)
  await expectSearch(page, '深夜', 1)
  // 另一个标签的名字必须是 0：它建出来了但一条挂载都没有，所以 `video_tags` 里根本没有
  // 它的行。注意这条**挡不住**"EXISTS 忘了跟外层影片相关"那种写法（我试过：摘掉
  // `.where(video_tags.c.video_id == Video.id)` 以后这里仍是 0，因为库上只有一部影片，
  // 相关与不相关长得一模一样）。真要在全库层面把它钉住，得有两部片子各自挂不同的标签；
  //  service 层那两条 `test_video_search.py` 用例已经这么做了，界面这一侧留给第 13 条。
  await expectSearch(page, '无人挂载', 0)
  // 两个词是"且"，而且命中位置不同（一个在片名、一个在标签名）
  await expectSearch(page, 'e2e 深夜', 1)
  await expectSearch(page, 'e2e 无人', 0)

  // 算子写成关键词是搜不到东西的，所以"命中 1 条"本身就是解析器认了它的证据
  await expectSearch(page, '标签:深夜', 1)
  await expectSearch(page, '标签:无人', 0)
  await expectSearch(page, '源:E2E', 1)
  await expectSearch(page, '源:不存在的源', 0)
  // 观看状态读的是**这个账号**的播放历史（`_played(user_id)`）：播种替 owner 写过一条
  // 18 秒、没看完的历史，于是三个状态各说中一件事
  await expectSearch(page, '未看完', 1)
  await expectSearch(page, '没看过', 0)
  await expectSearch(page, '已看完', 0)

  // 用户手打的通配符必须是字面量。后端靠 `ilike(..., escape="\\")` 那一层转义挡住它们，
  // 摘掉之后 `%` 和 `_` 都成了"匹配一切"，界面上会从 0 张卡变成 1 张。
  await expectSearch(page, '%', 0)
  await expectSearch(page, '_', 0)

  // 越界的页码：`?page=` 是首页自己写进地址栏的，分享一条链接、或者前进后退回到筛选前
  // 那一页，都可能带回来一个已经不存在的页。那一页确实是空的，但库里不空——界面不能同屏
  // 说"共 1 个视频"和"添加视频源并扫描即可开始使用"。
  await page.goto('/?page=2')
  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect(page.locator('.el-empty')).toHaveCount(0)
  await expect.poll(() => new URL(page.url()).searchParams.get('page')).toBeNull()
  await page.goto('/?q=e2e&page=3')
  await expect(page.locator('.video-card')).toHaveCount(1)
  // `Object.fromEntries` 而不是 `{...searchParams}`：URLSearchParams 的条目只在迭代器上，
  // 没有可枚举的自有属性，摊进对象字面量永远得到一个空对象（第一版就是这么"红"的——假红，
  // 应用本身没问题）。
  await expect
    .poll(() => Object.fromEntries(new URL(page.url()).searchParams))
    .toEqual({ q: 'e2e' })

  // 换成员登录：他一条历史都没写过，所以同一个 `未看完` 对他就是 0 条、`没看过` 是 1 条。
  // 同库同一片子，两个人报的数不一样——这只有真中间件加真库给得出（替身那份 `WATCH_STATE`
  // 是按视频 id 写死的，换谁都同一个答案）。
  await signIn(page, E2E_MEMBER_USERNAME)
  await expectSearch(page, '未看完', 0)
  await expectSearch(page, '没看过', 1)

  // 两个下拉：选项本身就是真库读出来的，选中之后走的是 `source_id` / `tag_id` 两个参数，
  // 而不是把名字塞进搜索框——这一层对接错成一个字符，界面就永远在"搜一个不存在的标签"。
  await signIn(page)
  await page.goto('/')
  await page.locator('.source-filter').click()
  await page.locator('.el-select-dropdown__item', { hasText: 'E2E local' }).click()
  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect.poll(() => new URL(page.url()).searchParams.get('source')).toBe('1')

  await page.locator('.tag-filter').click()
  await page.locator('.el-select-dropdown__item', { hasText: '无人挂载' }).click()
  await expect(page.locator('.video-card')).toHaveCount(0)
  // 只筛不搜时是另一句文案（「当前筛选条件下没有视频」），和搜了一个词的说法分开
  await expect(page.locator('.empty-hint')).toContainText('当前筛选条件下没有视频')
  expect((await readVideos(page, `?tag_id=${looseTagId}`)).total).toBe(0)
  expect((await readVideos(page, `?tag_id=${attachedTagId}`)).total).toBe(1)

  await page.locator('.empty-clear').click()
  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect.poll(() => new URL(page.url()).searchParams.toString()).toBe('')
})

/**
 * 丢失标记这一整条链的现场：一行记录、一个磁盘上的文件、一张封面、一条观看历史。
 *
 * 三个常量都是真路径——扫描用的 locator 来自 `MEDIA_DIR`，封面写在 `THUMBNAIL_DIR/<源
 * id>/` 下（`scan_service._thumbnail_target`），所以这条用例能同时核对库里的列、目录里
 * 的文件和界面上的那一句话。`HIDDEN_DIR` 必须落在 `MEDIA_DIR` **之外**：本地扫描是递归的，
 * 任何还留在源目录里、仍以 `.mp4` 结尾的东西都会被登记成一部新片子，那一验的就不是"把
 * 标记翻回去"，而是"多出一行"。
 */
const MEDIA_FILE = join(MEDIA_DIR, 'e2e_sample.mp4')
const HIDDEN_DIR = join(E2E_DIR, 'hidden')
const HIDDEN_FILE = join(HIDDEN_DIR, 'e2e_sample.mp4')

/** `GET /api/videos/{id}` 比列表多出这条用例要用到的那两列。 */
type VideoDetail = VideoRow & { filepath: string; thumbnail_path: string | null }

/** `GET /api/history` 里这一趟真正在用的那三样。 */
async function readHistoryRows(page: Page): Promise<[number, number, string | null][]> {
  const list = JSON.parse((await fetchInPage(page, '/api/history')).text) as {
    items: { id: number; video_id: number; video_title: string | null }[]
  }
  return list.items.map((item) => [item.id, item.video_id, item.video_title])
}

test('片子从磁盘上消失再挂回来：行只翻 is_missing，横幅、算子和那句「已找回」都跟着走', async ({ page }) => {
  // 这一条放在最后：它会把 `notifications` 留成 3 行，还会在中间把 `videos.is_missing`
  // 翻成 true（断言中途失败时磁盘上的文件由 finally 还回去，库里那一行却停在丢失态），
  // 换到中间插一条就会把后面所有用例的起点改掉。
  //
  // 起点是播种那趟真扫描建好的那一行和它名下那张真 FFmpeg 封面。
  const detail = JSON.parse((await fetchInPage(page, '/api/videos/1')).text) as VideoDetail
  expect(detail.is_missing).toBe(false)
  // 本地源存的是绝对路径，Windows 上带反斜杠——和这里拼出来的路径归一成同一种写法再比
  expect(detail.filepath.split(sep).join('/')).toBe(MEDIA_FILE.split(sep).join('/'))
  const coverPath = detail.thumbnail_path ?? ''
  expect(coverPath).toBeTruthy()
  expect(existsSync(coverPath)).toBe(true)
  const covers = coverFingerprints()
  expect(covers.length).toBeGreaterThan(0)
  expect((await readNotifications(page)).total).toBe(1)
  // 观看历史是**另一张表**：只核对影片行挡不住"删了重建"，那一脚会把历史行一起带走
  const history = await readHistoryRows(page)
  expect(history.length).toBe(1)
  expect(history[0]?.[1]).toBe(1)

  mkdirSync(HIDDEN_DIR, { recursive: true })
  try {
    renameSync(MEDIA_FILE, HIDDEN_FILE)

    expect(await scanSource(page, 1)).toEqual({
      files_found: 0,
      new_videos: 0,
      subtitles_found: 0,
    })

    // 扫描不删行：文件没了，那一行只是被标上丢失，界面上仍然读得到它
    const library = await readVideos(page, '')
    expect([library.total, library.items.length]).toEqual([1, 1])
    expect([library.items[0]?.id, library.items[0]?.is_missing]).toEqual([1, true])
    // 找出这批行的那一个算子，读的就是同一列（`_search_filters` 里的 `is_missing`）
    expect((await readVideos(page, `?search=${encodeURIComponent('丢失')}`)).total).toBe(1)

    const gone = await readNotifications(page)
    expect(gone.total).toBe(2)
    expect(gone.items[0]?.message).toContain('1 个文件已找不到')
    expect(gone.items[0]?.data).toEqual({
      source_id: 1,
      new_count: 0,
      subtitles_found: 0,
      missing_changed: 1,
    })

    // 首页那条横幅：`丢失` 探针报的数、卡片角上的标记、横幅里那句话，三处必须同源
    await page.goto('/')
    await expect(page.locator('.video-card')).toHaveCount(1)
    await expect(page.locator('.video-card .missing-badge')).toHaveText('丢失')
    const bar = page.locator('.missing-bar')
    await expect(bar).toBeVisible()
    await expect(bar.locator('.missing-text strong')).toHaveText('1 个文件已不在磁盘上')
    // 「查看」是回到这批行的唯一入口（另一个按钮是破坏性的清理）：它把算子填进搜索框
    await bar.getByRole('button', { name: '查看' }).click()
    await expect(page.locator('.search-input input')).toHaveValue('丢失')
    await expect(page.locator('.video-card')).toHaveCount(1)

    renameSync(HIDDEN_FILE, MEDIA_FILE)

    expect(await scanSource(page, 1)).toEqual({
      files_found: 1,
      new_videos: 0,
      subtitles_found: 0,
    })

    const back = await readVideos(page, '')
    expect([back.total, back.items[0]?.id, back.items[0]?.is_missing]).toEqual([1, 1, false])
    // 同一行、同一批封面文件：这一整趟往返只动了 `is_missing` 那一列
    expect(coverFingerprints()).toEqual(covers)
    expect(await readHistoryRows(page)).toEqual(history)

    const announced = await readNotifications(page)
    expect(announced.total).toBe(3)
    expect(announced.items[0]?.message).toContain('1 个文件已找回')
    expect(announced.items[1]?.message).toContain('1 个文件已找不到')
    // 方向必须分开说：只数"翻了几行"的话这两句会长成同一句话，而后面那句是好消息
    expect(announced.items[0]?.message).not.toContain('已找不到')
    expect(announced.items[0]?.data).toEqual({
      source_id: 1,
      new_count: 0,
      subtitles_found: 0,
      missing_changed: 1,
    })

    await page.goto('/')
    await expect(page.locator('.missing-bar')).toHaveCount(0)
    expect((await readVideos(page, `?search=${encodeURIComponent('丢失')}`)).total).toBe(0)
  } finally {
    // 断言走到哪一步都得把磁盘的样子还回去：这条用例之后还有一轮运行，而媒体目录是
    // gitignored 的一次性目录，留下一个 hidden/ 只会让下一次运行的起点说不清
    if (existsSync(HIDDEN_FILE)) renameSync(HIDDEN_FILE, MEDIA_FILE)
  }
})
