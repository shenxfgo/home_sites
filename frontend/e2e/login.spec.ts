import { expect, test } from '@playwright/test'
import { mockApi, STUB_PASSWORD, STUB_USER } from './fixtures'

async function signIn(page: import('@playwright/test').Page) {
  await page.locator('#login-username').fill(STUB_USER.username)
  await page.locator('#login-password').fill(STUB_PASSWORD)
  await page.locator('.submit').click()
}

test('未登录时被带回登录页，并记住原本要看的地址', async ({ page }) => {
  await mockApi(page, { signedIn: false })

  await page.goto('/history')

  await expect(page).toHaveURL(/\/login\?redirect=\/history/)
  await expect(page.locator('.login-card')).toBeVisible()
  // 登录页不属于任何导航，顶栏不该出现在这里。
  await expect(page.locator('.top-nav')).toHaveCount(0)
})

test('账号或密码错误时给出后端的原因', async ({ page }) => {
  await mockApi(page, { signedIn: false })
  await page.goto('/login')

  await page.locator('#login-username').fill(STUB_USER.username)
  await page.locator('#login-password').fill('wrong-password')
  await page.locator('.submit').click()

  await expect(page.locator('.error')).toHaveText('账号或密码错误')
  await expect(page).toHaveURL(/\/login/)
})

test('登录成功后回到原本要看的页面', async ({ page }) => {
  await mockApi(page, { signedIn: false })
  await page.goto('/sources')

  await signIn(page)

  await expect(page).toHaveURL(/\/sources$/)
  await expect(page.locator('.top-nav')).toBeVisible()
})

test('已经登录再访问登录页会回到首页', async ({ page }) => {
  await mockApi(page)

  await page.goto('/login')

  await expect(page).toHaveURL(/\/$/)
})

test('首启还没有账号时给出建号指引', async ({ page }) => {
  await mockApi(page, { signedIn: false, needsSetup: true })

  await page.goto('/')

  await expect(page.locator('.notice')).toContainText('create-user')
})

test('顶栏显示当前账号，退出后再回到登录页', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')

  await expect(page.locator('.user-name')).toHaveText(STUB_USER.display_name)
  await page.locator('.user-chip').click()
  await page.locator('.user-popper button', { hasText: '退出登录' }).click()

  await expect(page).toHaveURL(/\/login/)
  await expect(page.locator('.login-card')).toBeVisible()
})

test('我的设备列出这个账号开着的浏览器，并标出当前这一台', async ({ page }) => {
  await mockApi(page)
  await page.goto('/profile')

  const rows = page.locator('.card-devices .device-item')
  await expect(rows).toHaveCount(2)
  await expect(rows.first().locator('.el-tag')).toHaveText('当前设备')
  // 这一台的名字来自浏览器自己上报的 User-Agent，替身照真后端把它存下来。
  await expect(rows.first()).not.toContainText('未知设备')
  await expect(rows.nth(1)).toContainText('Safari · iOS')
  // 退出别人不该影响自己，所以只有另一台有按钮。
  await expect(rows.first().getByRole('button', { name: '退出' })).toHaveCount(0)
  await expect(rows.nth(1).getByRole('button', { name: '退出' })).toBeVisible()
})

test('退出另一台设备只让那一行消失，本机继续是登录的', async ({ page }) => {
  await mockApi(page)
  await page.goto('/profile')

  const phone = page.locator('.card-devices .device-item', { hasText: 'Safari · iOS' })
  await phone.getByRole('button', { name: '退出' }).click()

  await expect(page.locator('.el-message--success')).toContainText('该设备已退出')
  await expect(page.locator('.card-devices .device-item')).toHaveCount(1)
  // 刷新这一页还在登录态：退的是别的浏览器，不是这一台。
  await expect(page.locator('.user-name')).toHaveText(STUB_USER.display_name)
  await page.reload()
  await expect(page.locator('.card-devices .device-item')).toHaveCount(1)
})
