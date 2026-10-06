import { expect, test, type Page } from '@playwright/test'
import { mockApi } from './fixtures'

/**
 * 影片详情页的「编辑标签」那条写流程。
 *
 * 这几条要感谢 #132 把替身夹具的影片↔标签关系变成了有状态的：在此之前
 * `POST/DELETE /api/tags/video/...` 只回一句 204、谁也没落库，所以「保存后重新读这部影片」
 * 永远拿回安装前那份标签——用例只能红，而红的是替身不是界面。现在关系存在每次安装一份的
 * `videoTagLinks` 里，读路径一律按 id 现取，这条流程才算真跑得起来。
 *
 * 层次分工也是量出来的：「只发变动的那几项」这类请求内容，替身答得一样好（多挂一次、
 * 摘一次没挂的都不报错），只有单测能看穿；而「存下来没有」只有这里能证——见
 * `tests/views/VideoDetail.spec.ts` 的 `VideoDetail tag dialog` 一节。
 */

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

/** 标签条上此刻挂着的那几个名字。 */
const attached = (page: Page) => page.locator('.tags-list .el-tag')

async function openTagDialog(page: Page): Promise<void> {
  await page.locator('.tags-list button').click()
  await expect(page.locator('.el-dialog')).toContainText('编辑标签')
}

/** 对话框里某一个标签的复选框。 */
const checkboxFor = (page: Page, name: string) =>
  page.locator('.el-dialog .el-checkbox').filter({ hasText: name })

test('勾上标签保存后，影片真的带着它——标签页那个计数跟着涨', async ({ page }) => {
  await page.goto('/videos/2')
  await expect(attached(page)).toHaveCount(0)

  await openTagDialog(page)
  // 这部影片此刻一个标签也没挂，对话框就不该替它勾上任何一项。
  await expect(checkboxFor(page, '动作片')).not.toHaveClass(/is-checked/)

  await checkboxFor(page, '动作片').click()
  await page.locator('.el-dialog').getByRole('button', { name: '保存' }).click()

  // 这一句是本次改夹具的落点：保存后界面重新读这部影片，读回来的必须有它。
  await expect(attached(page)).toHaveText('动作片')

  // 同一个关系，换个入口读回来必须也是它：种子里 动作片 只挂在 深夜测试 上（1 个），
  // 现在多了一部，写死任何常数都过不了这一句。
  await page.goto('/tags')
  await expect(page.locator('.tag-card').filter({ hasText: '动作片' })).toContainText('2 个视频')
})

test('取消勾选保存后卡片真的少一个，标签页的计数跟着降回 0', async ({ page }) => {
  await page.goto('/videos/1')
  await expect(attached(page)).toHaveText('动作片')

  await openTagDialog(page)
  // 反过来：这部影片本来就挂着它，对话框必须预勾上，否则「保存」就是一次盲写。
  await expect(checkboxFor(page, '动作片')).toHaveClass(/is-checked/)

  await checkboxFor(page, '动作片').click()
  const removed = page.waitForResponse((res) =>
    res.request().method() === 'DELETE' && /\/api\/tags\/video\/1\/1$/.test(res.url()),
  )
  await page.locator('.el-dialog').getByRole('button', { name: '保存' }).click()

  expect((await removed).status()).toBe(204)
  await expect(attached(page)).toHaveCount(0)

  await page.goto('/tags')
  await expect(page.locator('.tag-card').filter({ hasText: '动作片' })).toContainText('0 个视频')
})

test('点开对话框看了一眼就取消，一个写请求也不发', async ({ page }) => {
  await page.goto('/videos/1')

  const writes: string[] = []
  page.on('request', (req) => {
    if (['POST', 'PUT', 'DELETE'].includes(req.method())) writes.push(`${req.method()} ${req.url()}`)
  })

  await openTagDialog(page)
  await checkboxFor(page, '动作片').click()
  await page.locator('.el-dialog').getByRole('button', { name: '取消' }).click()

  await expect(page.locator('.el-dialog')).toBeHidden()
  expect(writes).toEqual([])
  // 没保存就没有落库，卡片还是那一个。
  await expect(attached(page)).toHaveText('动作片')
})
