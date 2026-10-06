import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { mockApi } from './fixtures'

/**
 * 标签管理页（`views/Tags.vue`）的三条写流程。
 *
 * 这条视图此前一条用例也没有——14 个视图里只剩它和 `Settings.vue` 两个零测试。它偏偏又是
 * 唯一一条"名字是库里唯一列"的界面：建标签撞重名，后端回 409（#98），而那句原因以前从没
 * 由界面签过字。#128 让替身夹具第一次接得住 `POST/PUT/DELETE /api/tags`，这条页面才算真跑得起来。
 */

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

const card = (page: Page, name: string) => page.locator('.tag-card').filter({ hasText: name })

test('标签页列出标签与每个的影片数', async ({ page }) => {
  await page.goto('/tags')

  await expect(page.locator('.page-header h2')).toHaveText('标签管理')
  await expect(page.locator('.tag-card')).toHaveCount(1)
  await expect(card(page, '动作片')).toContainText('1 个视频')
  await expect(card(page, '动作片').locator('.tag-color-dot')).toHaveCSS(
    'background-color',
    'rgb(124, 108, 255)',
  )
})

/**
 * 这条是 #108 那条规矩的界面版：光看「1 个视频」证不出数对，因为写死 1 也绿。
 * 所以新建一条**故意不挂任何影片**的标签，两张卡片必须一个 1、一个 0——
 * 常数、或者"把全库影片数抄过来"，在这里都会露出来。
 */
test('新建的标签一条影片也没挂，卡片要写 0 个而不是抄别家的数', async ({ page }) => {
  await page.goto('/tags')
  await page.getByRole('button', { name: '添加标签' }).click()

  const dialog = page.locator('.el-dialog')
  await dialog.getByPlaceholder('请输入标签名称').fill('纪录片')
  // 预设色板第 4 个是 #f56c6c；点它而不是打字，是为了让颜色这条路也走一遍。
  await dialog.locator('.preset-color').nth(3).click()

  const created = page.waitForResponse(
    (res) => res.request().method() === 'POST' && /\/api\/tags$/.test(res.url()),
  )
  await dialog.getByRole('button', { name: '创建', exact: true }).click()

  expect((await created).status()).toBe(201)
  await expect(page.locator('.tag-card')).toHaveCount(2)
  await expect(card(page, '纪录片')).toContainText('0 个视频')
  await expect(card(page, '动作片')).toContainText('1 个视频')
  await expect(card(page, '纪录片').locator('.tag-color-dot')).toHaveCSS(
    'background-color',
    'rgb(245, 108, 108)',
  )
})

test('重名建标签时给出服务端的原话，对话框留在原地', async ({ page }) => {
  await page.goto('/tags')
  await page.getByRole('button', { name: '添加标签' }).click()

  const dialog = page.locator('.el-dialog')
  await dialog.getByPlaceholder('请输入标签名称').fill('动作片')
  await dialog.getByRole('button', { name: '创建', exact: true }).click()

  // 这句是这条用例的落点：#74/#75 量过的同一类缺口——服务端的原因被回退文案盖掉。
  await expect(page.locator('.el-message--error')).toContainText('标签「动作片」已存在')
  // 409 之后人还得改名重试，所以对话框不能自己关掉。
  await expect(dialog).toBeVisible()
  await expect(page.locator('.tag-card')).toHaveCount(1)
})

test('名称为空时前置挡下，一次请求也不发', async ({ page }) => {
  await page.goto('/tags')
  await page.getByRole('button', { name: '添加标签' }).click()

  const posts: string[] = []
  page.on('request', (req) => {
    if (req.method() === 'POST') posts.push(req.url())
  })

  const dialog = page.locator('.el-dialog')
  // 只有空格：`.trim()` 之后是空串，和留空走的是同一道闸门。
  await dialog.getByPlaceholder('请输入标签名称').fill('   ')
  await dialog.getByRole('button', { name: '创建', exact: true }).click()
  await expect(page.locator('.el-message--warning')).toContainText('请输入标签名')

  expect(posts).toEqual([])
  await expect(page.locator('.tag-card')).toHaveCount(1)
})

/**
 * #130：`tags.name` 那个唯一列比的是整串，所以「动作片」与「动作片␣」在它眼里是两条，
 * 而界面上一张卡片写着带空格的、另一张写着不带的，看起来就是"莫名多了个重复标签"。
 * 单元层钉的是请求体里那个名字（`toHaveBeenCalledWith`），这一层钉的是卡片上那行字。
 *
 * 替身夹具**没有**跟着加裁剪逻辑——前端在发之前就裁完了，夹具从此收不到带空格的名称，
 * 在那儿加一条量不到的分支就是 #132 记下的那类死写。后端自己那道 `_clean_name` 由
 * `tests/test_api/test_tags.py` 的 6 条签字，这一层只保证界面不再往人眼前塞空格。
 */
test('名字两头带的空格不会跟着存进卡片', async ({ page }) => {
  await page.goto('/tags')
  await page.getByRole('button', { name: '添加标签' }).click()

  const dialog = page.locator('.el-dialog')
  await dialog.getByPlaceholder('请输入标签名称').fill('  纪录片  ')
  const created = page.waitForResponse(
    (res) => res.request().method() === 'POST' && /\/api\/tags$/.test(res.url()),
  )
  await dialog.getByRole('button', { name: '创建', exact: true }).click()
  expect((await created).status()).toBe(201)

  // 渲染出来的名字必须不带两头空格：`hasText: '纪录片'` 对带空格的卡片同样成立（子串匹配），
  // 所以断的是整行的可见文案，而不是"存不存在这么一张卡"。
  await expect(page.locator('.tag-card')).toHaveCount(2)
  await expect(card(page, '纪录片').locator('.tag-name')).toHaveText('纪录片')
})

test('改名只加了一圈空格时，一次更新也不发', async ({ page }) => {
  await page.goto('/tags')
  await card(page, '动作片').getByRole('button', { name: '编辑' }).click()

  const puts: string[] = []
  page.on('request', (req) => {
    if (req.method() === 'PUT') puts.push(req.url())
  })

  const dialog = page.locator('.el-dialog')
  await dialog.getByPlaceholder('请输入标签名称').fill('动作片 ')
  await dialog.getByRole('button', { name: '更新', exact: true }).click()

  // 以前这一步会真的发出一次 PUT，把「动作片␣」写进唯一列，界面上凭空多出同名第二行。
  expect(puts).toEqual([])
  await expect(page.locator('.tag-card')).toHaveCount(1)
  await expect(card(page, '动作片').locator('.tag-name')).toHaveText('动作片')
})

test('改名只发改动的那个字段，卡片跟着换成新名字', async ({ page }) => {
  await page.goto('/tags')
  await card(page, '动作片').getByRole('button', { name: '编辑' }).click()

  const dialog = page.locator('.el-dialog')
  // 编辑对话框必须带着库里的那份预填，否则"更新"就是一次盲写。
  await expect(dialog.getByPlaceholder('请输入标签名称')).toHaveValue('动作片')

  const bodies: string[] = []
  page.on('request', (req) => {
    if (req.method() === 'PUT') bodies.push(req.postData() ?? '')
  })

  await dialog.getByPlaceholder('请输入标签名称').fill('文艺片')
  await dialog.getByRole('button', { name: '更新', exact: true }).click()

  await expect(card(page, '文艺片')).toBeVisible()
  expect(bodies).toHaveLength(1)
  // 颜色一眼没动，就不该跟着被重写一遍。
  expect(JSON.parse(bodies[0])).toEqual({ name: '文艺片' })
})

test('什么都没改时不发出更新请求', async ({ page }) => {
  await page.goto('/tags')
  await card(page, '动作片').getByRole('button', { name: '编辑' }).click()

  const puts: string[] = []
  page.on('request', (req) => {
    if (req.method() === 'PUT') puts.push(req.url())
  })

  await page.locator('.el-dialog').getByRole('button', { name: '更新', exact: true }).click()

  expect(puts).toEqual([])
  // 没有改动就没有"标签已更新"这句谎，但对话框照常关闭、列表照常重载。
  await expect(page.locator('.el-message--success')).toHaveCount(0)
  await expect(card(page, '动作片')).toBeVisible()
})

test('删除标签要先确认，确认后卡片消失、空库给出建标签的入口', async ({ page }) => {
  await page.goto('/tags')
  await card(page, '动作片').getByRole('button', { name: '删除' }).click()

  const box = page.locator('.el-message-box')
  await expect(box).toContainText('这将同时从所有关联的视频中移除该标签')

  const deleted = page.waitForResponse(
    (res) => res.request().method() === 'DELETE' && /\/api\/tags\/1$/.test(res.url()),
  )
  await box.getByRole('button', { name: '删除' }).click()

  expect((await deleted).status()).toBe(204)
  await expect(page.locator('.tag-card')).toHaveCount(0)
  await expect(page.locator('.el-empty')).toContainText('尚未创建标签')
})

test('取消删除对话框时标签原样留着', async ({ page }) => {
  await page.goto('/tags')
  await card(page, '动作片').getByRole('button', { name: '删除' }).click()

  let deleted = false
  page.on('request', (req) => {
    if (req.method() === 'DELETE') deleted = true
  })

  await page.locator('.el-message-box__btns button', { hasText: '取消' }).click()
  await page.waitForTimeout(300)

  expect(deleted).toBe(false)
  await expect(page.locator('.tag-card')).toHaveCount(1)
})
