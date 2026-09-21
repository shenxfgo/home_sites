import { expect, test } from '@playwright/test'
import { mockApi, STUB_MEMBER, STUB_PASSWORD, STUB_USER } from './fixtures'

/** 顶栏那一排按钮的文案，用来比对角色看见了什么。 */
async function navLabels(page: import('@playwright/test').Page) {
  return (await page.locator('.nav-item').allTextContents()).map((text) => text.trim())
}

/** 点开当前那个下拉里的一个选项：每一行都有自己的下拉，只有打开的那个看得见。 */
async function openOption(page: import('@playwright/test').Page, label: string) {
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: label }).click()
}

async function signIn(page: import('@playwright/test').Page, username: string) {
  await page.locator('#login-username').fill(username)
  await page.locator('#login-password').fill(STUB_PASSWORD)
  await page.locator('.submit').click()
}

test('成员看不到管理入口', async ({ page }) => {
  await mockApi(page, { role: 'member' })
  await page.goto('/')

  const labels = await navLabels(page)
  expect(labels).toContain('片单')
  expect(labels).not.toContain('视频源')
  expect(labels).not.toContain('标签管理')
  expect(labels).not.toContain('设置')

  await page.locator('.user-chip').click()
  await expect(page.locator('.user-popper button', { hasText: '个人设置' })).toBeVisible()
  await expect(page.locator('.user-popper button', { hasText: '用户管理' })).toHaveCount(0)
})

test('成员的通知面板里没有删除入口', async ({ page }) => {
  await mockApi(page, { role: 'member' })
  await page.goto('/')

  await page.locator('.notification-badge button').click()
  await expect(page.locator('.notification-popper')).toContainText('扫描完成')
  // 删一行等于全家少一行，所以这一处对成员整个收起。
  await expect(page.locator('.notification-popper button', { hasText: '清空' })).toHaveCount(0)
  await expect(page.locator('.notification-remove')).toHaveCount(0)
  // 标记已读记在自己名下，成员照旧能做。
  await page.locator('.notification-popper button', { hasText: '全部已读' }).click()
  await expect(page.locator('.notification-badge .el-badge__content')).toBeHidden()
})

test('成员手敲管理地址会被带回首页', async ({ page }) => {
  await mockApi(page, { role: 'member' })

  for (const path of ['/settings', '/users', '/sources', '/tags', '/videos/1/transcode']) {
    await page.goto(path)
    // 守卫要等会话探测完才会把人送回首页，所以用带重试的断言而不是读一次 url
    await expect(page).toHaveURL(/\/$/)
  }

  // 自己的页面照旧能进
  await page.goto('/profile')
  await expect(page.locator('.profile-page')).toBeVisible()
})

test('成员的首页留着丢失记录横幅，但没有清理入口', async ({ page }) => {
  await mockApi(page, { role: 'member' })
  await page.goto('/')

  const bar = page.locator('.missing-bar')
  await expect(bar.locator('.missing-text strong')).toHaveText('1 个文件已不在磁盘上')
  // 清理走的是删片接口，成员点了只会拿 403，所以这一处整个收起；看还是能看。
  await expect(bar.getByRole('button', { name: '清理丢失记录' })).toHaveCount(0)
  await bar.getByRole('button', { name: '查看' }).click()
  await expect(page.locator('.video-card')).toHaveCount(1)
})

test('成员的影片详情页没有库级操作', async ({ page }) => {
  await mockApi(page, { role: 'member' })
  await page.goto('/videos/1')

  await expect(page.getByRole('button', { name: '片单' })).toBeVisible()
  for (const label of ['转码', '编辑', '删除']) {
    await expect(page.getByRole('button', { name: label })).toHaveCount(0)
  }
  // 标签那一行的加号只开到"编辑标签"弹窗，成员也不该看见
  await expect(page.locator('.tags-list button')).toHaveCount(0)
  await expect(page.locator('.tags-list .el-tag').first()).toHaveText('动作片')
})

test('管理员的影片详情页保留全部库级操作', async ({ page }) => {
  await mockApi(page)
  await page.goto('/videos/1')

  for (const label of ['转码', '编辑', '删除']) {
    await expect(page.getByRole('button', { name: label })).toBeVisible()
  }
  await expect(page.locator('.tags-list button')).toHaveCount(1)
})

test('管理员的顶栏保留全部入口', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')

  expect(await navLabels(page)).toEqual(
    expect.arrayContaining(['视频源', '标签管理', '设置']),
  )

  await page.locator('.user-chip').click()
  await page.locator('.user-popper button', { hasText: '用户管理' }).click()
  await expect(page).toHaveURL(/\/users$/)
  await expect(page.locator('.users-page')).toBeVisible()
})

test('用户管理列出账号，但不让管理员停用自己', async ({ page }) => {
  await mockApi(page)
  await page.goto('/users')

  const rows = page.locator('.el-table__row')
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0)).toContainText(STUB_USER.username)
  await expect(rows.nth(0)).toContainText('本人')
  await expect(rows.nth(1)).toContainText(STUB_MEMBER.username)
  // 第三行是已停用的 guest，设备数为 0，所以"踢下线"是灰的
  await expect(rows.nth(2)).toContainText('guest')
  await expect(rows.nth(2).locator('button', { hasText: '踢下线' })).toBeDisabled()

  const switches = page.locator('.el-table__row .el-switch input')
  await expect(switches.nth(0)).toBeDisabled()
  await expect(switches.nth(1)).toBeEnabled()
})

test('在界面上建账号并改角色', async ({ page }) => {
  await mockApi(page)
  await page.goto('/users')

  await page.getByRole('button', { name: '新建账号' }).click()
  const dialog = page.locator('.el-dialog')
  await dialog.locator('input').nth(0).fill('newface')
  await dialog.locator('input').nth(1).fill(STUB_PASSWORD)
  await dialog.getByRole('button', { name: '创建' }).click()

  await expect(page.locator('.el-table__row')).toHaveCount(4)
  await expect(page.locator('.el-table__row').nth(3)).toContainText('newface')

  // 把成员提上来，再降回去：服务端点头之前表格不该自己先改
  const kidRow = page.locator('.el-table__row', { hasText: STUB_MEMBER.username })
  await kidRow.locator('.el-select').click()
  await openOption(page, '管理员')
  await expect(kidRow.locator('.el-select')).toContainText('管理员')
})

test('服务端拒绝时给出原因并回到原来的样子', async ({ page }) => {
  await mockApi(page)
  await page.goto('/users')

  const ownerRow = page.locator('.el-table__row', { hasText: STUB_USER.username })
  await ownerRow.locator('.el-select').click()
  await openOption(page, '成员')

  await expect(page.locator('.el-message--error')).toContainText('至少要保留一个可用的管理员')
  await expect(ownerRow.locator('.el-select')).toContainText('管理员')
})

test('重置密码和踢下线都要人先确认', async ({ page }) => {
  await mockApi(page)
  await page.goto('/users')

  const kidRow = page.locator('.el-table__row', { hasText: STUB_MEMBER.username })
  await kidRow.locator('button', { hasText: '踢下线' }).click()
  const confirm = page.locator('.el-message-box')
  await expect(confirm).toContainText(`退出 ${STUB_MEMBER.username} 的所有浏览器`)
  await confirm.getByRole('button', { name: '退出登录' }).click()
  await expect(kidRow).toContainText('0')

  await kidRow.locator('button', { hasText: '重置密码' }).click()
  const prompt = page.locator('.el-message-box')
  await expect(prompt).toBeVisible()
  await prompt.locator('input').fill('short')
  await prompt.getByRole('button', { name: '重置' }).click()
  await expect(prompt.locator('.el-message-box__errormsg')).toBeVisible()
  await prompt.locator('input').fill(STUB_PASSWORD)
  await prompt.getByRole('button', { name: '重置' }).click()
  await expect(prompt).toHaveCount(0)
})

test('系统设置里不再有主题', async ({ page }) => {
  await mockApi(page)
  await page.goto('/settings')

  await expect(page.locator('.settings-card .card-header')).toHaveText([
    '扫描设置',
    '转码设置',
    '缩略图设置',
  ])
  await expect(page.locator('.settings-page')).not.toContainText('主题')
})

test('主题跟着人走，不跟着浏览器走', async ({ page }) => {
  await mockApi(page, { signedIn: false, themes: { owner: 'light', member: 'light' } })
  // 这台设备上次是深色：账号说浅色，就该变回浅色
  await page.addInitScript(() => localStorage.setItem('theme', 'dark'))

  await page.goto('/login')
  await signIn(page, STUB_USER.username)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')

  await page.goto('/profile')
  await page.locator('.el-radio', { hasText: '深色' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  // 换个人登录：他存的是浅色之外的另一份选择，界面该换成他的
  await page.locator('.user-chip').click()
  await page.locator('.user-popper button', { hasText: '退出登录' }).click()
  await expect(page.locator('.login-card')).toBeVisible()
  await signIn(page, STUB_MEMBER.username)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
})

test('个人设置里改密码先验原密码，再落下新密码', async ({ page }) => {
  await mockApi(page)
  await page.goto('/profile')

  const fields = page.locator('.card-password').locator('input')
  await fields.nth(0).fill('wrong-password')
  await fields.nth(1).fill('another-pass')
  await fields.nth(2).fill('another-pass')
  await page.getByRole('button', { name: '更新密码' }).click()
  await expect(page.locator('.el-message--error')).toContainText('原密码不正确')

  // 三次确认一致、原密码也对，才会真的发出去
  await fields.nth(0).fill(STUB_PASSWORD)
  await page.getByRole('button', { name: '更新密码' }).click()
  await expect(page.locator('.el-message--success')).toContainText('密码已更新')
  await expect(fields.nth(1)).toHaveValue('')
  // 服务端顺手退了别的浏览器，列表要跟着重读，不能还挂着那一行。
  await expect(page.locator('.card-devices .device-item')).toHaveCount(1)

  await fields.nth(1).fill('short')
  await fields.nth(2).fill('short')
  await page.getByRole('button', { name: '更新密码' }).click()
  await expect(page.locator('.el-message--warning')).toContainText('至少 8 位')
})

test('成员也管得动自己名下的设备', async ({ page }) => {
  await mockApi(page, { role: 'member' })
  await page.goto('/profile')

  // 会话是按账号存的，退掉自己另一台不需要管理员权限。
  await expect(page.locator('.card-devices .device-item')).toHaveCount(2)
  const phone = page.locator('.card-devices .device-item', { hasText: 'Safari · iOS' })
  await phone.getByRole('button', { name: '退出' }).click()
  await expect(page.locator('.el-message--success')).toContainText('该设备已退出')
  await expect(page.locator('.card-devices .device-item')).toHaveCount(1)
  await expect(page.locator('.user-name')).toBeVisible()
})
