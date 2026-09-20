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
