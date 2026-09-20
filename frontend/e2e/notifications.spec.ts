import { expect, test, type Page } from '@playwright/test'
import { mockApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

async function openPopover(page: Page) {
  await page.locator('.notification-badge button').click()
  await expect(page.locator('.notification-popper .notification-item')).toHaveCount(2)
}

test('顶栏铃铛显示未读通知数量', async ({ page }) => {
  await page.goto('/')

  await expect(page.locator('.notification-badge .el-badge__content')).toHaveText('2')
})

test('打开通知面板可以看到内容', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  await expect(page.locator('.notification-popper')).toContainText('扫描完成')
  await expect(page.locator('.notification-popper')).toContainText('深夜测试.mp4 已入库')
})

test('点击单条通知后未读数减一', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  await page.locator('.notification-popper .notification-item').first().click()

  await expect(page.locator('.notification-badge .el-badge__content')).toHaveText('1')
})

test('一键已读会清空未读角标', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  await page.locator('.notification-popper button', { hasText: '全部已读' }).click()

  await expect(page.locator('.notification-badge .el-badge__content')).toBeHidden()
})

test('单条通知可以删掉，未读数跟着减少', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  await page.locator('.notification-popper .notification-item').first().locator('.notification-remove').click()

  await expect(page.locator('.notification-popper .notification-item')).toHaveCount(1)
  await expect(page.locator('.notification-popper .notification-item').first()).toContainText('深夜测试.mp4 已入库')
  await expect(page.locator('.notification-badge .el-badge__content')).toHaveText('1')
})

test('清空通知要按两次，之后列表回到空状态', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  const clear = page.locator('.notification-popper .clear-btn')
  await clear.click()
  await expect(clear).toHaveText('确认清空')
  await expect(page.locator('.notification-popper .notification-item')).toHaveCount(2)

  await clear.click()

  await expect(page.locator('.notification-popper .notification-item')).toHaveCount(0)
  await expect(page.locator('.notification-popper')).toContainText('暂无通知')
  await expect(page.locator('.notification-badge .el-badge__content')).toBeHidden()
  // 列表空了就没有可清空的东西了
  await expect(page.locator('.notification-popper .clear-btn')).toHaveCount(0)
})

test('清空提示超时后自动收回，不会误删', async ({ page }) => {
  await page.goto('/')
  await openPopover(page)

  const clear = page.locator('.notification-popper .clear-btn')
  await clear.click()
  await expect(clear).toHaveText('确认清空')

  await page.waitForTimeout(4200)
  await expect(clear).toHaveText('清空')

  await clear.click()
  await expect(page.locator('.notification-popper .notification-item')).toHaveCount(2)
})
