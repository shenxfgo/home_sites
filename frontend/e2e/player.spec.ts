import { expect, test, type Page } from '@playwright/test'
import { mockApi } from './fixtures'

/** The detail page only mounts the player after the preview is clicked. */
async function startPlayback(page: Page): Promise<void> {
  await mockApi(page)
  await page.goto('/videos/1')
  await page.locator('.preview-area').click()
  await expect(page.locator('.video-player')).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await startPlayback(page)
})

test('播放页为每个字幕渲染一条 WebVTT 轨道', async ({ page }) => {
  const tracks = page.locator('video track')
  await expect(tracks).toHaveCount(2)
  await expect(tracks.first()).toHaveAttribute('src', '/api/videos/1/subtitles/1/stream')
  await expect(tracks.first()).toHaveAttribute('srclang', 'zh')
  await expect(tracks.first()).toHaveAttribute('label', '中文')
})

test('播放器菜单可以选中一条字幕并显示为开启', async ({ page }) => {
  const subtitleButton = page.locator('.subtitle-btn')
  await expect(subtitleButton).toBeVisible()

  await subtitleButton.click()
  await expect(page.locator('.subtitle-menu-item')).toHaveCount(3)

  await page.locator('.subtitle-menu-item').nth(2).click()
  await expect(page.locator('.subtitle-menu')).toHaveCount(0)
  await expect(subtitleButton).toHaveClass(/is-active/)
})

test('没有字幕的视频不显示字幕按钮', async ({ page }) => {
  await page.goto('/videos/2')
  await page.locator('.preview-area').click()
  await expect(page.locator('.video-player')).toBeVisible()

  await expect(page.locator('video track')).toHaveCount(0)
  await expect(page.locator('.subtitle-btn')).toHaveCount(0)
})

/** 替身流是一段真实的 30 秒片段，浏览器因此报出真实时长 */
const CLIP_SECONDS = 30

const currentTimeOf = (page: Page) =>
  page
    .locator('.video-player video')
    .evaluate((element) => (element as HTMLVideoElement).currentTime)

async function trackBox(page: Page) {
  const track = page.locator('.progress-track')
  // 详情页在 720 高的视口下需要滚动才能露出控制条
  await track.scrollIntoViewIfNeeded()
  const box = await track.boundingBox()
  if (!box) throw new Error('进度条不可见')
  return box
}

/** 浏览器 seek 会带亚像素/帧对齐误差，用可观察的差值断言代替严格相等 */
async function expectCurrentTime(page: Page, seconds: number, tolerance = 0.6): Promise<void> {
  await expect
    .poll(async () => Math.abs((await currentTimeOf(page)) - seconds))
    .toBeLessThan(tolerance)
}

function expectNear(actual: number | undefined, expected: number, label: string): void {
  const message = `${label}：期望约 ${expected.toFixed(1)} px，实际 ${actual ?? '元素不可见'}`
  expect(actual, message).toBeLessThan(expected + 1.5)
  expect(actual, message).toBeGreaterThan(expected - 1.5)
}

/** 用真实指针点击进度条上对应秒数的位置 */
async function clickProgressAt(page: Page, seconds: number): Promise<void> {
  const box = await trackBox(page)
  await page.mouse.click(box.x + (box.width * seconds) / CLIP_SECONDS, box.y + box.height / 2)
}

test('加载真实片段后时长显示为 0:30', async ({ page }) => {
  await expect(page.locator('.time-display')).toHaveText('0:00 / 0:30')
})

test('点击进度条按真实布局跳转到对应时间', async ({ page }) => {
  for (const seconds of [7.5, 15, 27]) {
    await clickProgressAt(page, seconds)
    await expectCurrentTime(page, seconds)
  }
})

test('进度条按住拖动全程跟手，越过两端时收敛到 0 与时长', async ({ page }) => {
  const box = await trackBox(page)
  const y = box.y + box.height / 2
  const at = (seconds: number) => box.x + (box.width * seconds) / CLIP_SECONDS

  await page.mouse.move(at(3), y)
  await page.mouse.down()
  await expectCurrentTime(page, 3)

  // 指针移出进度条之外仍然跟手，并且不超过时长
  await page.mouse.move(at(18), y)
  await expectCurrentTime(page, 18)
  await page.mouse.move(box.x + box.width + 20, y)
  await expectCurrentTime(page, CLIP_SECONDS)
  await page.mouse.move(box.x - 20, y)
  await expectCurrentTime(page, 0)

  await page.mouse.move(at(18), y)
  await expectCurrentTime(page, 18)
  await page.mouse.up()

  // 松开后填充条停在播放位置，而不是回弹到按下时的起点
  const fill = page.locator('.progress-fill')
  await expect(fill).toBeVisible()
  expectNear((await fill.boundingBox())?.width, (box.width * 18) / CLIP_SECONDS, '填充条宽度')
})

test('A-B 段重放：标记区间、按真实像素高亮、经过 B 点回到 A 点', async ({ page }) => {
  await clickProgressAt(page, 10)
  await expectCurrentTime(page, 10)

  const loopButtons = page.locator('.loop-btn')
  await loopButtons.first().click()
  const startAt = await currentTimeOf(page)
  await expect(loopButtons.first()).toHaveClass(/is-active/)
  // 只有 A 点时区间无效，进度条上不高亮
  await expect(page.locator('.progress-loop')).toHaveCount(0)

  // 播放位置尚未越过 A 点时 B 按钮保持禁用
  await clickProgressAt(page, 4)
  await expect(loopButtons.nth(1)).toBeDisabled()

  await clickProgressAt(page, 20)
  await expect(loopButtons.nth(1)).toBeEnabled()
  await loopButtons.nth(1).click()
  const endAt = await currentTimeOf(page)

  const track = await trackBox(page)
  const band = page.locator('.progress-loop')
  await expect(band).toBeVisible()
  const bandBox = await band.boundingBox()
  expectNear(bandBox?.x, track.x + (track.width * startAt) / CLIP_SECONDS, '高亮段左边界')
  expectNear(bandBox?.width, (track.width * (endAt - startAt)) / CLIP_SECONDS, '高亮段宽度')
  await expect(page.locator('.loop-control')).toHaveClass(/is-looping/)

  // 拖到 B 点之后会被拉回 A 点
  await clickProgressAt(page, 27)
  await expectCurrentTime(page, startAt)

  await page.locator('.loop-clear').click()
  await expect(page.locator('.progress-loop')).toHaveCount(0)
  await expect(page.locator('.loop-control')).not.toHaveClass(/is-looping/)

  // 清除之后不再回跳
  await clickProgressAt(page, 27)
  await expectCurrentTime(page, 27)
})

test('A-B 段重放在切换视频后自动清除', async ({ page }) => {
  await clickProgressAt(page, 10)
  await page.locator('.loop-btn').first().click()
  await clickProgressAt(page, 20)
  await page.locator('.loop-btn').nth(1).click()
  await expect(page.locator('.progress-loop')).toHaveCount(1)

  await page.goto('/videos/2')
  await page.locator('.preview-area').click()
  await expect(page.locator('.video-player')).toBeVisible()
  await expect(page.locator('.progress-loop')).toHaveCount(0)
  await expect(page.locator('.loop-clear')).toHaveCount(0)
})
