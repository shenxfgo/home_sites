import { expect, test, type Page } from '@playwright/test'
import { mockApi } from './fixtures'

/**
 * 播放器可见 ≠ 元数据到达。这条用例把流接口按住 1.5 秒，让「点进度条」这一击
 * 确定落在 `duration` 还是 NaN 的窗口里——#229 之前它会被悄悄丢掉，播放头不动，
 * 也没有任何提示。
 */
const CLIP_SECONDS = 30
const METADATA_DELAY_MS = 1500

const videoElement = (page: Page) => page.locator('.video-player video')

const hasDuration = (page: Page) =>
  videoElement(page).evaluate((element) => Number.isFinite((element as HTMLVideoElement).duration))

const currentTimeOf = (page: Page) =>
  videoElement(page).evaluate((element) => (element as HTMLVideoElement).currentTime)

/** 浏览器 seek 会带帧对齐误差，用可观察的差值断言代替严格相等 */
async function expectCurrentTime(page: Page, seconds: number, tolerance = 0.6): Promise<void> {
  await expect
    .poll(async () => Math.abs((await currentTimeOf(page)) - seconds))
    .toBeLessThan(tolerance)
}

/** 按住第一次流请求，后续请求照常放行（快进片段只被拖慢一次）。 */
async function holdFirstStreamRequest(page: Page, ms = METADATA_DELAY_MS): Promise<void> {
  let held = false
  await page.route(/\/api\/videos\/1\/stream/, async (route) => {
    if (!held) {
      held = true
      await new Promise((resolve) => setTimeout(resolve, ms))
    }
    await route.fallback()
  })
}

test('元数据到达之前点下的进度条，时长报出来后会被补做', async ({ page }) => {
  await mockApi(page)
  await holdFirstStreamRequest(page)
  await page.goto('/videos/1')
  await page.locator('.preview-area').click()
  await expect(page.locator('.video-player')).toBeVisible()

  // 前置条件：这一击确实落在元数据之前，否则测的是另一条路径
  await expect.poll(() => hasDuration(page)).toBe(false)

  const track = page.locator('.progress-track')
  await track.scrollIntoViewIfNeeded()
  const box = await track.boundingBox()
  if (!box) throw new Error('进度条不可见')
  await page.mouse.click(box.x + (box.width * 18) / CLIP_SECONDS, box.y + box.height / 2)

  // 点下的一瞬间播放头确实没动——这正是今天的全部症状
  await expectCurrentTime(page, 0, 0.1)

  // 时长报出来后补做：停在用户按下的 18 秒，界面也写着它
  await expectCurrentTime(page, 18)
  await expect(page.locator('.time-display')).toHaveText('0:18 / 0:30')
})

test('量不出长度的文件不补做：播放头不动、进度条不写 NaN、也不报错', async ({ page }) => {
  await mockApi(page)
  // 按住到用例结束：这一条只让合成事件把元数据送进来，真时长不许插队
  await holdFirstStreamRequest(page, 120_000)
  await page.goto('/videos/1')
  await page.locator('.preview-area').click()
  await expect(page.locator('.video-player')).toBeVisible()
  await expect.poll(() => hasDuration(page)).toBe(false)

  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))

  const track = page.locator('.progress-track')
  await track.scrollIntoViewIfNeeded()
  const box = await track.boundingBox()
  if (!box) throw new Error('进度条不可见')
  await page.mouse.click(box.x + (box.width * 18) / CLIP_SECONDS, box.y + box.height / 2)

  // 元数据到了，可这条文件量不出长度——直播的形状
  await page.evaluate(() => {
    const video = document.querySelector('.video-player video') as HTMLVideoElement
    Object.defineProperty(video, 'duration', { get: () => Number.POSITIVE_INFINITY, configurable: true })
    video.dispatchEvent(new Event('loadedmetadata'))
  })

  await expectCurrentTime(page, 0, 0.1)
  await expect(page.locator('.progress-fill')).toHaveJSProperty('style.width', '0%')
  expect(errors).toEqual([])
})
