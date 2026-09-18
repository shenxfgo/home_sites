import { expect, test } from '@playwright/test'
import { mockApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('视频源页列出全部数据源', async ({ page }) => {
  await page.goto('/sources')

  await expect(page.locator('.page-header h2')).toHaveText('视频源管理')
  await expect(page.locator('.source-grid > *')).toHaveCount(2)
  await expect(page.locator('.source-grid')).toContainText('本地视频库')
  await expect(page.locator('.source-grid')).toContainText('NAS 片库')
})

test('扫描全部会调用扫描接口并汇报结果', async ({ page }) => {
  await page.goto('/sources')

  const response = page.waitForResponse(
    (res) => res.request().method() === 'POST' && res.url().endsWith('/api/scan/all'),
  )
  await page.getByRole('button', { name: '扫描全部' }).click()

  expect((await response).status()).toBe(200)
  await expect(page.locator('.el-message--success')).toContainText('发现 12 个文件, 3 个新视频')
})

test('删除数据源需要确认，确认后发出 DELETE 请求', async ({ page }) => {
  await page.goto('/sources')

  await page.locator('.source-grid').getByRole('button', { name: '删除' }).first().click()
  const deleted = page.waitForResponse(
    (res) => res.request().method() === 'DELETE' && /\/api\/sources\/1$/.test(res.url()),
  )
  await page.locator('.el-message-box').getByRole('button', { name: '删除' }).click()

  expect((await deleted).status()).toBe(204)
  await expect(page.locator('.el-message--success').last()).toContainText('视频源已删除')
})

test('取消删除对话框时不发出请求', async ({ page }) => {
  await page.goto('/sources')

  let deleted = false
  page.on('request', (request) => {
    if (request.method() === 'DELETE') deleted = true
  })

  await page.locator('.source-grid').getByRole('button', { name: '删除' }).first().click()
  await page.locator('.el-message-box__btns button', { hasText: '取消' }).click()
  await page.waitForTimeout(300)

  expect(deleted).toBe(false)
})
