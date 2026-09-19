import { expect, test, type Page } from '@playwright/test'
import { mockApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

async function messageBoxButton(page: Page, label: string) {
  await page.locator('.el-message-box__btns button', { hasText: label }).click()
}

test('顶栏入口进入片单页，排队顺序与条数都按后端给的来', async ({ page }) => {
  await page.goto('/')

  await page.locator('.nav-item', { hasText: '片单' }).click()

  await expect(page).toHaveURL(/\/watchlists$/)
  await expect(page.locator('.page-title')).toHaveText('片单')
  await expect(page.locator('.page-meta')).toHaveText('2 个片单 · 2 条排队')
  await expect(page.locator('.list-panel')).toHaveCount(2)

  const first = page.locator('.list-panel').first()
  await expect(first.locator('.list-name')).toHaveText('今晚看这些')
  await expect(first.locator('.queue-title')).toHaveCount(2)
  await expect(first.locator('.queue-title').first()).toHaveText('深夜测试')
  await expect(first.locator('.queue-title').nth(1)).toHaveText('周末纪录片')
  // 65 秒 + 3600 秒
  await expect(first.locator('.list-meta')).toHaveText('2 部 · 共 1:01:05')
  await expect(first.locator('.queue-meta').first()).toContainText('已看 0:42')
  // 空片单只留一句提示
  await expect(page.locator('.list-panel').nth(1).locator('.queue-empty')).toContainText('去影片详情页点「加入片单」')
})

test('移出片单不会把影片从库里删掉', async ({ page }) => {
  await page.goto('/watchlists')

  await page.locator('.list-panel').first().locator('.queue-item').first().getByRole('button', { name: '移出' }).click()

  await expect(page.locator('.el-message--success')).toContainText('影片仍在库里')
  await expect(page.locator('.list-panel').first().locator('.queue-title')).toHaveCount(1)
  await expect(page.locator('.page-meta')).toHaveText('2 个片单 · 1 条排队')

  await page.goto('/videos/1')
  await expect(page.locator('.video-title')).toHaveText('深夜测试')
})

test('新建与改名都只动片单本身', async ({ page }) => {
  await page.goto('/watchlists')

  await page.getByRole('button', { name: '新建片单' }).click()
  await page.locator('.el-dialog input').first().fill('周末看完')
  await page.locator('.el-dialog').getByRole('button', { name: '保存' }).click()
  await expect(page.locator('.list-panel')).toHaveCount(3)
  await expect(page.locator('.list-name').last()).toHaveText('周末看完')

  await page.locator('.list-panel').first().getByRole('button', { name: '重命名' }).click()
  await expect(page.locator('.el-dialog input').first()).toHaveValue('今晚看这些')
  await page.locator('.el-dialog input').first().fill('明晚看这些')
  await page.locator('.el-dialog').getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.list-name').first()).toHaveText('明晚看这些')
  await expect(page.locator('.list-panel')).toHaveCount(3)
})

test('删除片单要先确认，取消就什么都不动', async ({ page }) => {
  await page.goto('/watchlists')

  await page.locator('.list-panel').first().getByRole('button', { name: '删除片单' }).click()
  await expect(page.locator('.el-message-box')).toContainText('影片本身不会被动')
  await messageBoxButton(page, '取消')
  await expect(page.locator('.list-panel')).toHaveCount(2)

  await page.locator('.list-panel').first().getByRole('button', { name: '删除片单' }).click()
  await messageBoxButton(page, '删除')
  await expect(page.locator('.list-panel')).toHaveCount(1)
  await expect(page.locator('.list-name').first()).toHaveText('还没排片')
})

test('详情页的片单按钮可以勾选与取消队列', async ({ page }) => {
  await page.goto('/videos/1')

  await page.locator('.action-buttons').getByRole('button', { name: '片单' }).click()
  const dialog = page.locator('.el-dialog', { hasText: '加入片单' })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('.el-checkbox', { hasText: '今晚看这些' })).toHaveClass(/is-checked/)
  await expect(dialog.locator('.el-checkbox', { hasText: '还没排片' })).not.toHaveClass(/is-checked/)

  await dialog.locator('.el-checkbox', { hasText: '还没排片' }).click()
  await dialog.getByRole('button', { name: '保存' }).click()
  await expect(page.locator('.el-message--success')).toContainText('片单已更新')

  // 取消勾选同样只是移出队列：1 号片单少了这部，2 号片单还留着
  await page.goto('/videos/1')
  await page.locator('.action-buttons').getByRole('button', { name: '片单' }).click()
  const again = page.locator('.el-dialog', { hasText: '加入片单' })
  await again.locator('.el-checkbox', { hasText: '今晚看这些' }).click()
  await again.getByRole('button', { name: '保存' }).click()
  await page.goto('/watchlists')
  await expect(page.locator('.page-meta')).toHaveText('2 个片单 · 2 条排队')
  await expect(page.locator('.list-panel').first().locator('.queue-title')).toHaveText('周末纪录片')
  await expect(page.locator('.list-panel').nth(1).locator('.queue-title')).toHaveText('深夜测试')
})
