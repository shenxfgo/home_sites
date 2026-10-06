import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { mockApi } from './fixtures'

/**
 * 系统配置页（`views/Settings.vue`）的界面层用例。
 *
 * 这一页的真库那一路已经由真后端 e2e 的第 11 条签过（写进去换一路读、被拒的写入不落地），
 * 但**桩面两层一条也没有**：14 个视图里它是最后一个零测试的。这里独占的是"真打字"和
 * "真刷新"两件事——`el-input-number` 的那道 `:min`/`:max` 是全系统唯一一处范围闸门
 * （后端对这三个数字键**只校验是不是整数，不校验范围**，#112 立的口径），而"保存后刷新
 * 还在"要求替身真的把整份 PUT 落进 `systemSettings`。
 */

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

const field = (page: Page, label: string) =>
  page.locator('.el-form-item').filter({ has: page.locator('.el-form-item__label', { hasText: label }) })

/** 替身库里 `systemSettings` 那五项（`fixtures.ts` 每次安装重建）。 */
const SEEDED = {
  auto_scan_enabled: true,
  auto_scan_interval: 3600,
  default_transcode_format: 'mp4',
  thumbnail_width: 320,
  thumbnail_height: 180,
}

test('设置页读出替身那份配置：三张卡片、间隔显示的是 label', async ({ page }) => {
  await page.goto('/settings')

  await expect(page.locator('.page-header h2')).toHaveText('应用设置')
  await expect(page.locator('.settings-card')).toHaveCount(3)
  // 3600 在 value 里，界面上给人看的是「每小时」这一档。
  await expect(field(page, '扫描间隔')).toContainText('每小时')
  await expect(field(page, '默认转码格式')).toContainText('MP4 (H.264)')
  await expect(field(page, '自动扫描').locator('.el-switch')).toHaveClass(/is-checked/)
  await expect(field(page, '缩略图宽度').locator('input')).toHaveValue('320')
})

test('改动落进替身那张表，刷新之后读回来的是改过的值', async ({ page }) => {
  await page.goto('/settings')

  await field(page, '扫描间隔').locator('.el-select').click()
  await page.locator('.el-select-dropdown__item', { hasText: '每 2 小时' }).click()
  await field(page, '自动扫描').locator('.el-switch').click()
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.locator('.el-message--success')).toContainText('设置已保存')

  // 这一句才把"回显"和"落库"分开：整份 PUT 回的就是请求体，只看提示等于自证。
  const stored = await page.evaluate(async () => {
    const res = await fetch('/api/settings')
    return res.json()
  })
  expect(stored).toEqual({ ...SEEDED, auto_scan_interval: 7200, auto_scan_enabled: false })

  await page.reload()
  await expect(field(page, '扫描间隔')).toContainText('每 2 小时')
  await expect(field(page, '自动扫描').locator('.el-switch')).not.toHaveClass(/is-checked/)
})

test('保存发出去的是全五项，一个键也没漏', async ({ page }) => {
  await page.goto('/settings')

  const bodies: string[] = []
  page.on('request', (req) => {
    if (req.method() === 'PUT' && req.url().endsWith('/api/settings')) bodies.push(req.postData() ?? '')
  })

  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.locator('.el-message--success')).toContainText('设置已保存')

  // 少发一项不是"那一项不动"：后端那个请求模型五项都带默认值，漏的那项会被写成默认值。
  expect(bodies).toHaveLength(1)
  expect(JSON.parse(bodies[0])).toEqual(SEEDED)
})

test('缩略图宽度打到范围之外，界面上被钳住、发出去的也是钳后的值', async ({ page }) => {
  await page.goto('/settings')

  const width = field(page, '缩略图宽度').locator('input')
  await width.fill('50')
  await width.blur()
  // `:min="100"` 是这一整条链路上唯一的范围闸门（后端只认"是不是整数"）。
  await expect(width).toHaveValue('100')

  const bodies: string[] = []
  page.on('request', (req) => {
    if (req.method() === 'PUT' && req.url().endsWith('/api/settings')) bodies.push(req.postData() ?? '')
  })
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.locator('.el-message--success')).toContainText('设置已保存')

  expect(JSON.parse(bodies[0])).toMatchObject({ thumbnail_width: 100 })
})

test('高度那一格的上下限和宽度不是同一对，各自钳各自', async ({ page }) => {
  await page.goto('/settings')

  const height = field(page, '缩略图高度').locator('input')
  await height.fill('5000')
  await height.blur()
  await expect(height).toHaveValue('1080')

  // 宽度留在播种的 320：两格各有 :min/:max，把任何一对写反都会在这里露出来。
  await expect(field(page, '缩略图宽度').locator('input')).toHaveValue('320')
})
