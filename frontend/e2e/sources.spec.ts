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

test('重复文件检测列出确认过内容的副本', async ({ page }) => {
  await page.goto('/sources')

  await expect(page.locator('.dup-card')).toContainText('重复文件检测')
  await expect(page.locator('.dup-group')).toHaveCount(0)

  await page.getByRole('button', { name: '开始检测' }).click()

  await expect(page.locator('.dup-group')).toHaveCount(1)
  await expect(page.locator('.dup-item')).toHaveCount(2)
  await expect(page.locator('.dup-summary')).toContainText('1 组重复')
  await expect(page.locator('.dup-summary')).toContainText('2.0 KB')
  await expect(page.locator('.dup-item').first()).toContainText('建议保留')
  await expect(page.locator('.dup-item').last()).toContainText('深夜测试 备份')
})

test('移除多余副本会先确认，只发出一次记录级 DELETE', async ({ page }) => {
  await page.goto('/sources')
  await page.getByRole('button', { name: '开始检测' }).click()
  await expect(page.locator('.dup-item')).toHaveCount(2)

  const deletedUrls: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'DELETE') deletedUrls.push(request.url())
  })

  await page.getByRole('button', { name: '移除多余记录' }).click()
  await expect(page.locator('.el-message-box')).toContainText('磁盘上的文件不会被动')
  await page.locator('.el-message-box__btns button', { hasText: '移除记录' }).click()

  await expect(page.locator('.dup-group')).toHaveCount(0)
  await expect(page.locator('.el-message--success')).toContainText('已移除 1 条重复记录')
  expect(deletedUrls).toHaveLength(1)
  expect(deletedUrls[0]).toContain('/api/videos/41')
})

test('取消移除对话框时保留全部副本', async ({ page }) => {
  await page.goto('/sources')
  await page.getByRole('button', { name: '开始检测' }).click()
  await expect(page.locator('.dup-item')).toHaveCount(2)

  let deleted = false
  page.on('request', (request) => {
    if (request.method() === 'DELETE') deleted = true
  })

  await page.getByRole('button', { name: '移除多余记录' }).click()
  await page.locator('.el-message-box__btns button', { hasText: '再想想' }).click()
  await page.waitForTimeout(300)

  expect(deleted).toBe(false)
  await expect(page.locator('.dup-item')).toHaveCount(2)
})
