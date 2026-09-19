import { expect, test } from '@playwright/test'
import { mockApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('顶栏入口进入统计页，页首给出小时数', async ({ page }) => {
  await page.goto('/')

  await page.locator('.nav-item', { hasText: '观影统计' }).click()

  await expect(page).toHaveURL(/\/stats$/)
  await expect(page.locator('.stat-card').first()).toContainText('1.5 小时')
  await expect(page.locator('.stat-card')).toHaveCount(4)
  await expect(page.locator('.stat-card').nth(2)).toContainText('1 部')
  await expect(page.locator('.stat-card').nth(3)).toContainText('2 天')
})

test('柱状图给区间内每一天一根柱子，最高的一天铺满', async ({ page }) => {
  await page.goto('/stats')

  const bars = page.locator('.bar')
  await expect(bars).toHaveCount(30)

  const peak = await bars.nth(29).boundingBox()
  const previousDay = await bars.nth(28).boundingBox()
  const idleDay = await bars.nth(0).boundingBox()
  expect(peak!.height).toBeCloseTo(160, 0)
  expect(previousDay!.height).toBeCloseTo(peak!.height * 0.33, 0)
  expect(idleDay!.height).toBeLessThan(5)
  await expect(page.locator('.chart-axis')).toContainText('9月')
})

test('标签分布按最长的一条铺开，并显示各自的小时数', async ({ page }) => {
  await page.goto('/stats')

  const row = page.locator('.tag-row').first()
  await expect(row).toContainText('动作片')
  const track = await row.locator('.tag-track').boundingBox()
  const fill = await row.locator('.tag-fill').boundingBox()
  expect(fill!.width).toBeGreaterThan(track!.width - 2)
  await expect(row).toContainText('2.0 小时')
})

test('切换时间窗会重新取数并只剩七根柱子', async ({ page }) => {
  await page.goto('/stats')
  await expect(page.locator('.bar')).toHaveCount(30)

  const request = page.waitForRequest(/\/api\/history\/stats\?days=7$/)
  await page.locator('.window-btn', { hasText: '近 7 天' }).click()
  await request

  await expect(page.locator('.bar')).toHaveCount(7)
  await expect(page.locator('.window-btn').first()).toHaveClass(/active/)
})
