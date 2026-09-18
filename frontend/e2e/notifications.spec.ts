import { expect, test, type Page } from '@playwright/test'
import { mockApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

async function openPopover(page: Page) {
  await page.locator('.notification-badge button').click()
  await expect(page.locator('.el-popover .notification-item')).toHaveCount(2)
}

test('顶栏铃铛显示未读通知数量', async ({ page }) => {
  await page.goto('/')

  await expect(page.locator('.notification-badge .el-badge__content')).toHaveText('2')
})

test('打开通知面板可以看到内容', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  await expect(page.locator('.el-popover')).toContainText('扫描完成')
  await expect(page.locator('.el-popover')).toContainText('深夜测试.mp4 已入库')
})

test('点击单条通知后未读数减一', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  await page.locator('.el-popover .notification-item').first().click()

  await expect(page.locator('.notification-badge .el-badge__content')).toHaveText('1')
})

test('一键已读会清空未读角标', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  await page.locator('.el-popover button', { hasText: '全部已读' }).click()

  await expect(page.locator('.notification-badge .el-badge__content')).toBeHidden()
})
