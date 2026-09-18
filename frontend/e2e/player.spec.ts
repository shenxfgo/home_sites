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
