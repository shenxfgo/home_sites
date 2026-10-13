import { expect, test, type Page } from '@playwright/test'
import { mockApi, SEEDED_SETTINGS } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

async function confirmDialog(page: Page) {
  await page.locator('.el-message-box__btns button', { hasText: '确定' }).click()
}

async function chooseFormat(page: Page, format: string) {
  await page.locator('.transcode-section .el-select').click()
  await page.locator('.el-select-dropdown__item', { hasText: format }).click()
}

/** 覆盖替身那份系统配置：只改要的那一项，其余五项从夹具展开。 */
async function overrideSettings(page: Page, overrides: Record<string, unknown>) {
  // 后注册的路由先匹配，所以这条盖得住 `mockApi` 那份兜底的 `/api/**`。
  await page.route((url) => url.pathname === '/api/settings', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...SEEDED_SETTINGS, ...overrides }),
    }),
  )
}

test('转码页展示视频信息与可选格式', async ({ page }) => {
  await page.goto('/videos/1/transcode')

  await expect(page.locator('.page-title')).toHaveText('视频转码')
  await expect(page.locator('.content-card')).toContainText('深夜测试')
  await expect(page.locator('.content-card')).toContainText('深夜测试.mp4')
  await expect(page.locator('.formats-section .el-table__body tr')).toHaveCount(2)
  // 这部片子还没转码过：新地址真的被请求了，界面拿到的是一张空表而不是一片空白
  await expect(page.locator('.products-section')).toContainText('还没有转码产物')
})

test('转码进行中有进度条，完成后提示并落位为已完成', async ({ page }) => {
  await page.goto('/videos/1/transcode')

  await chooseFormat(page, 'webm')
  await page.getByRole('button', { name: '开始转码' }).click()
  await confirmDialog(page)

  await expect(page.getByRole('button', { name: '取消转码' })).toBeVisible()
  await expect(page.locator('.el-progress')).toBeVisible()
  await expect(page.locator('.el-message--success')).toContainText('转码任务已启动')

  await expect(page.locator('.status-section')).toContainText('已完成', { timeout: 20_000 })
  await expect(page.locator('.el-message--success').last()).toContainText('转码完成')

  // 完成那一刻才写进产物表，页面不重读就得刷新才看得到（#154）
  await expect(page.locator('.products-section .el-table__body tr')).toHaveCount(1)
  await expect(page.locator('.products-section')).toContainText('WEBM')
  await expect(page.locator('.products-section')).toContainText('/data/transcode/1/')
  await expect(page.locator('.products-section')).toContainText('在磁盘上')
})

test('取消转码会停掉任务并结束轮询', async ({ page }) => {
  await page.goto('/videos/1/transcode')

  await chooseFormat(page, 'mp4')
  await page.getByRole('button', { name: '开始转码' }).click()
  await confirmDialog(page)
  await expect(page.getByRole('button', { name: '取消转码' })).toBeVisible()

  await page.getByRole('button', { name: '取消转码' }).click()
  await confirmDialog(page)

  await expect(page.locator('.status-section')).toContainText('已取消')
  await expect(page.getByRole('button', { name: '取消转码' })).toBeHidden()
})

test('目标格式默认就是系统配置里那一项', async ({ page }) => {
  // 替身播种的默认是 mp4，这里换成 webm 才分得开「读了配置」和「写了个默认值」。
  await overrideSettings(page, { default_transcode_format: 'webm' })
  await page.goto('/videos/1/transcode')

  await expect(page.locator('.transcode-section .el-select')).toContainText('webm (webm)')
})

test('配置里那项不在支持的格式列表里就不预填，也就发不出转码', async ({ page }) => {
  // 这一条把 #151 甲的"只给界面当下拉默认"和原来那条「未选择目标格式」一起签了：
  // 替身只支持 mp4 与 webm，`avi` 是列表外的一档——硬填进去点了就是后端一句拒绝，
  // 所以界面宁可不填，让「请选择目标格式」那句话来说话。
  await overrideSettings(page, { default_transcode_format: 'avi' })
  await page.goto('/videos/1/transcode')

  let posted = false
  page.on('request', (request) => {
    if (request.method() === 'POST' && /\/api\/transcode\/\d+$/.test(request.url())) posted = true
  })

  await page.getByRole('button', { name: '开始转码' }).click()

  await expect(page.locator('.el-message--warning')).toContainText('请选择目标格式')
  expect(posted).toBe(false)
})

test('加载不到视频时弹的是服务端原话而不是统一一句失败', async ({ page }) => {
  await page.goto('/videos/5/transcode')

  await expect(page.locator('.el-message--error')).toContainText('视频不存在')
})

// 后端的详情接口挂掉时页面不能只是安静地留着上一次的进度：状态卡片上要写明原因。
test('状态接口失败时在卡片上写明原因', async ({ page }) => {
  await page.route(/\/api\/transcode\/\d+\/status$/, (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '转码服务未就绪' }),
    }),
  )
  await page.goto('/videos/1/transcode')

  await expect(page.locator('.status-fetch-error')).toHaveText('转码服务未就绪')
  await expect(page.locator('.el-message--error')).toContainText('转码服务未就绪')
})
