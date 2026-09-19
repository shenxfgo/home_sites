import { expect, test } from '@playwright/test'
import { mockApi } from './fixtures'

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

test('搜索框按标题过滤视频', async ({ page }) => {
  await page.goto('/')

  await page.getByPlaceholder('搜索视频...').fill('纪录')

  await expect(page.locator('.video-card')).toHaveCount(1)
  await expect(page.locator('.video-card').first()).toContainText('周末纪录片')
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
