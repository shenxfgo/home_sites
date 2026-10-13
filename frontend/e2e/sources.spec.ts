import { expect, test, type Page } from '@playwright/test'
import { mockApi, SEEDED_SETTINGS } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

/** 替身里的系统配置，只改这一个人的默认间隔。 */
async function overrideScanInterval(page: Page, seconds: number) {
  await page.route((url) => url.pathname === '/api/settings', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...SEEDED_SETTINGS, auto_scan_interval: seconds }),
    }),
  )
}

test('添加视频源时扫描间隔预填的是系统配置里那一项', async ({ page }) => {
  // 3600 是这个格子从前写死的那个数，替身播种的也是它——换成 900 才分得开
  // 「从那张表读的」和「代码里写死的」。
  await overrideScanInterval(page, 900)
  await page.goto('/sources')

  await page.getByRole('button', { name: '添加视频源' }).click()
  const dialog = page.locator('.el-dialog')
  await expect(dialog).toBeVisible()

  const interval = dialog
    .locator('.el-form-item')
    .filter({ has: page.locator('.el-form-item__label', { hasText: '扫描间隔' }) })
    .locator('input')
  await expect(interval).toHaveValue('900')
  await expect(dialog.locator('.interval-hint')).toHaveText('秒，默认取自系统设置')

  const bodies: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/sources')) {
      bodies.push(request.postData() ?? '')
    }
  })

  await dialog.getByPlaceholder('例如：我的NAS').fill('配置默认值的片源')
  await dialog.getByPlaceholder(/mnt\/videos/).fill('D:\\from-settings')
  await dialog.getByRole('button', { name: '创建' }).click()

  await expect(page.locator('.el-message--success')).toContainText('视频源已创建')
  // 预填不能只是一个看不见的值：发出去的那份 body 里就得带上这个数
  expect(bodies).toHaveLength(1)
  expect(JSON.parse(bodies[0])).toMatchObject({ scan_interval: 900 })
})

test('省略扫描间隔时替身答的也是配置里那一项', async ({ page }) => {
  // 界面上这一格永远会被预填，「省略就读那张表」那半句只有不带这个字段的请求才走得到。
  // 而替身从前在这里自己写死一个 3600：真后端接上了、替身没接上，同一个数就还是两句话，
  // 后面那些拿替身当后端的用例就会跟着一起假绿。这条钉的是替身的口径。
  await page.goto('/sources')

  const created = await page.evaluate(async (seeded) => {
    await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...seeded, auto_scan_interval: 900 }),
    })
    const response = await fetch('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: '不填间隔的片源', path: 'D:\\no-interval', type: 'local' }),
    })
    return {
      status: response.status,
      body: (await response.json()) as { scan_interval: number },
    }
  }, SEEDED_SETTINGS)

  expect(created.status).toBe(201)
  expect(created.body.scan_interval).toBe(900)
})

test('视频源页列出全部数据源', async ({ page }) => {
  await page.goto('/sources')

  await expect(page.locator('.page-header h2')).toHaveText('视频源管理')
  await expect(page.locator('.source-grid > *')).toHaveCount(2)
  await expect(page.locator('.source-grid')).toContainText('本地视频库')
  await expect(page.locator('.source-grid')).toContainText('NAS 片库')
})

test('选择对象存储类型时会说清路径写法和能力限制', async ({ page }) => {
  await page.goto('/sources')
  await page.getByRole('button', { name: '添加视频源' }).click()

  const dialog = page.locator('.el-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('.path-hint')).toHaveCount(0)

  await dialog.locator('.el-select__wrapper').click()
  await page.locator('.el-select-dropdown__item', { hasText: 'S3 / MinIO' }).click()

  await expect(dialog.locator('.path-hint')).toContainText('没有缩略图、转码和字幕')
  await expect(dialog.getByPlaceholder('例如：s3://my-videos/shows')).toBeVisible()
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
  await expect(page.locator('.el-message-box')).toContainText('磁盘上的视频文件不会被动')
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
