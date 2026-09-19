import { expect, test, type Page } from '@playwright/test'
import { mockApi } from './fixtures'

/** 地址栏里的查询串，已解码，方便直接和中文关键词比对。 */
async function queryOf(page: Page) {
  return page.evaluate(() => {
    const param = (key: string) => new URL(location.href).searchParams.get(key)
    return { q: param('q'), source: param('source'), tag: param('tag'), page: param('page'), size: param('size') }
  })
}

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('首页渲染视频卡片和真实缩略图', async ({ page }) => {
  await page.goto('/')

  await expect(page.locator('.hero-sub')).toHaveText('共 2 个视频，挑一部开始今天的观影吧')

  const first = page.locator('.video-card').first()
  await expect(page.locator('.video-card')).toHaveCount(2)
  await expect(first).toContainText('深夜测试')
  await expect(first.locator('.duration-badge')).toHaveText('1:05')
  await expect(first.locator('.new-badge')).toHaveText('新')
  // 角标跟着 is_new 走，不是按文件新旧算的，所以另一部没有
  await expect(page.locator('.video-card').nth(1).locator('.new-badge')).toHaveCount(0)

  const thumb = first.locator('img.thumbnail-img')
  await expect(thumb).toHaveAttribute('src', '/api/videos/1/thumbnail')
  await expect(thumb).toHaveJSProperty('naturalWidth', 1)
})

test('搜索框支持片名、简介、标签、评分、时长与观看状态', async ({ page }) => {
  await page.goto('/')

  const box = page.getByPlaceholder('搜索片名、简介或标签…')
  const cards = page.locator('.video-card')

  // 只出现在片名里
  await box.fill('深夜')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('深夜测试')

  // 只出现在简介里
  await box.fill('极地')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('周末纪录片')

  // 只出现在标签名里
  await box.fill('动作片')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('深夜测试')

  // 多个词之间是且的关系
  await box.fill('深夜 测试')
  await expect(cards).toHaveCount(1)
  await box.fill('深夜 纪录片')
  await expect(cards).toHaveCount(0)

  await box.fill('评分>=4')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('深夜测试')

  await box.fill('时长>40分钟')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('周末纪录片')

  await box.fill('源:NAS')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('周末纪录片')

  await box.fill('没看过')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('周末纪录片')

  await box.fill('未看完')
  await expect(cards).toHaveCount(1)
  await expect(cards.first()).toContainText('深夜测试')
})

test('搜索无结果时给出提示并能一键清除筛选', async ({ page }) => {
  await page.goto('/')

  await page.getByPlaceholder('搜索片名、简介或标签…').fill('查无此片')

  await expect(page.locator('.empty-hint')).toContainText('没有与「查无此片」匹配的结果')

  await page.getByRole('button', { name: '清除筛选' }).click()

  await expect(page.locator('.video-card')).toHaveCount(2)
  await expect(page.getByPlaceholder('搜索片名、简介或标签…')).toHaveValue('')
})

test('标签下拉按标签过滤首页', async ({ page }) => {
  await page.goto('/')

  await page.locator('.tag-filter').click()
  await page.getByRole('option', { name: '动作片' }).click()

  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect(page.locator('.video-card').first()).toContainText('深夜测试')
})

test('点击卡片进入视频详情页', async ({ page }) => {
  await page.goto('/')

  await page.locator('.video-card').first().click()

  await expect(page).toHaveURL(/\/videos\/1$/)
  await expect(page.locator('h1, .video-title').first()).toContainText('深夜测试')
})

test('播放历史显示视频标题，缺失标题时退回视频编号', async ({ page }) => {
  await page.goto('/history')

  const rows = page.locator('.el-table__body tr')
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toContainText('深夜测试')
  await expect(rows.nth(1)).toContainText('视频 #999')

  // 一行未看完、一行已完成，列名说的是最后一次观看，不是第一次
  await expect(rows.nth(0)).toContainText('未看完')
  await expect(rows.nth(1)).toContainText('已完成')
  await expect(page.locator('.el-table__header')).toContainText('最后观看')
})

test('未知地址显示 404 页并能回到首页', async ({ page }) => {
  await page.goto('/this/page/does/not/exist')

  await expect(page.locator('.not-found .code')).toHaveText('404')
  await expect(page.locator('.not-found .title')).toHaveText('页面不存在')

  await page.getByRole('button', { name: '回到首页' }).click()

  await expect(page).toHaveURL('/')
  await expect(page.locator('.video-card')).toHaveCount(2)
})

test('首页「继续观看」横排显示剩余时长与进度线', async ({ page }) => {
  await page.goto('/')

  const rail = page.locator('.resume-rail')
  await expect(rail.locator('.rail-title')).toHaveText('继续观看')
  await expect(rail.locator('.rail-count')).toHaveText('1 部没看完')
  // 只有看完一半的那部进横排，替身数据里另一部没有进度
  await expect(rail.locator('.rail-item')).toHaveCount(1)

  const item = rail.locator('.rail-item').first()
  await expect(item.locator('.rail-caption')).toHaveText('深夜测试')
  await expect(item.locator('.rail-remaining')).toHaveText('剩 0:23')

  // 65 秒看到 42 秒 = 64.6%，进度线按真实像素铺满同样比例
  await expect(item.locator('.rail-bar-fill')).toHaveAttribute('style', /width: 64\.6\d*%/)
  const bar = await rail.locator('.rail-bar').boundingBox()
  const fill = await item.locator('.rail-bar-fill').boundingBox()
  expect(fill?.width).toBeGreaterThan((bar?.width ?? 0) * 0.6)
  expect(fill?.width).toBeLessThan((bar?.width ?? 0) * 0.7)

  await item.locator('.rail-caption').click()
  await expect(page).toHaveURL(/\/videos\/1$/)
})

test('卡片封面底部画出停下来的位置，未看过则没有', async ({ page }) => {
  await page.goto('/')

  const watched = page.locator('.video-card').first()
  await expect(watched.locator('.resume-bar')).toHaveAttribute('style', /width: 64\.6\d*%/)
  await expect(page.locator('.video-card').nth(1).locator('.resume-bar')).toHaveCount(0)
})

test('系列横排说出下一集是哪一集，点开即播', async ({ page }) => {
  await page.goto('/')

  const rail = page.locator('.series-rail')
  await expect(rail.locator('.rail-title')).toHaveText('系列进度')
  await expect(rail.locator('.rail-count')).toHaveText('1 个系列')

  const item = rail.locator('.rail-item').first()
  await expect(item.locator('.rail-caption')).toHaveText('深夜客车')
  await expect(item.locator('.rail-remaining')).toHaveText('1/3')
  await expect(item.locator('.rail-state')).toHaveText('看到 S01E02')

  // 3 集看完 1 集 = 33%，按真实像素铺进度线
  await expect(item.locator('.rail-bar-fill')).toHaveAttribute('style', /width: 33\.3\d*%/)
  const bar = await item.locator('.rail-bar').boundingBox()
  const fill = await item.locator('.rail-bar-fill').boundingBox()
  expect(fill?.width).toBeGreaterThan((bar?.width ?? 0) * 0.3)
  expect(fill?.width).toBeLessThan((bar?.width ?? 0) * 0.4)

  await item.click()
  await expect(page).toHaveURL(/\/videos\/1$/)
})

test('卡片右上角标出文件名里解析出的季集', async ({ page }) => {
  await page.goto('/')

  const first = page.locator('.video-card').first()
  await expect(first.locator('.episode-badge')).toHaveText('S01E02')
  // 另一部不是剧集，不该凭空出现角标
  await expect(page.locator('.video-card').nth(1).locator('.episode-badge')).toHaveCount(0)
})

test('搜索与筛选写进地址，换个入口打开同一个地址能还原', async ({ page }) => {
  await page.goto('/')

  await page.getByPlaceholder('搜索片名').fill('深夜')
  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect.poll(() => queryOf(page)).toMatchObject({ q: '深夜' })

  await page.getByPlaceholder('搜索片名').fill('')
  await expect(page.locator('.video-card')).toHaveCount(2)
  await expect.poll(() => queryOf(page)).toEqual({
    q: null,
    source: null,
    tag: null,
    page: null,
    size: null,
  })

  // 直接打开一条深链：关键词与标签都从地址里读回来，页码 1 是默认值被收掉
  await page.goto('/?q=深夜&tag=1&page=1')
  await expect(page.getByPlaceholder('搜索片名')).toHaveValue('深夜')
  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect(page.locator('.video-card').first()).toContainText('深夜测试')
  await expect(page.locator('.tag-filter')).toContainText('动作片')
  await expect.poll(() => queryOf(page)).toMatchObject({ q: '深夜', tag: '1', page: null })

  // 地址里写错的参数按默认值处理，不会把列表问空
  await page.goto('/?page=abc&size=-5')
  await expect(page.locator('.video-card')).toHaveCount(2)
})

test('筛选之后点进片子再后退，条件仍然在', async ({ page }) => {
  await page.goto('/')

  await page.getByPlaceholder('搜索片名').fill('深夜')
  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect.poll(() => queryOf(page)).toMatchObject({ q: '深夜' })

  await page.locator('.video-card').first().click()
  await expect(page).toHaveURL(/\/videos\/1$/)

  await page.goBack()

  await expect(page.getByPlaceholder('搜索片名')).toHaveValue('深夜')
  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect(page.locator('.video-card').first()).toContainText('深夜测试')
})

test('按 / 跳到搜索框，按 ? 看快捷键清单', async ({ page }) => {
  await page.goto('/')
  // 首页是按路由切出来的异步块，等它挂上再按键
  await expect(page.locator('.video-card')).toHaveCount(2)

  await page.keyboard.press('/')
  await expect(page.getByPlaceholder('搜索片名')).toBeFocused()

  // 焦点离开输入框之后，? 才是"看快捷键"
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await page.keyboard.press('?')
  const dialog = page.locator('.el-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('跳到首页搜索框')
  await expect(dialog).toContainText('后退 / 前进 5 秒')
  await expect(dialog).toContainText('音量，之后会记住')

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  // 正在输入时这两个键都交还给输入框
  await page.getByPlaceholder('搜索片名').fill('?')
  await expect(dialog).toBeHidden()
  await expect(page.getByPlaceholder('搜索片名')).toHaveValue('?')
})

