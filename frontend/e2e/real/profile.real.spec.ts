/**
 * 第 14 条：个人设置页的两条写路径打真库——按 `token_hash` 退掉**别的那台**，以及主题按人存。
 *
 * `Profile.vue` 是除 NotFound 外唯一从没在真库上签过字的视图。设备列表、单台退出、改密码后
 * 「这台留着、其余全退」这三件事，在替身夹具里连处理器都没有（`fixtures.ts` 不接
 * `/api/auth/sessions`，所以那 82 条从没真的请求过它），服务层那边也只有 CLI 那条**不带**
 * `keep_token_hash` 的路有测试——也就是说"改完密码这台还登录着"这句写在界面上的承诺，
 * 此前没有任何一层签过。
 *
 * 为什么值得单独开一个文件：这一页的状态是**跨浏览器**的。一条会话属于哪台设备、`current`
 * 是相对于谁算出来的、删一行会不会伤到另一行——都得有两个各自握着 cookie 的 context 才证得
 * 出来，而 `page` 夹具只有一个。第二台用 `browser.newContext()` 起，**不能**在同一个 context
 * 里再登录一次：那样 Set-Cookie 会把原 token 覆盖掉，「被退出的那台从此 401」就只能靠猜。
 *
 * 行一律按**服务端回的那份数组的下标**去点，不写死条数，也不按设备名找：一轮跑到这里，前面
 * 13 条各自 `signIn` 过一次，owner 名下已有十几行活会话，而 `devices.value = await
 * listSessions()`（`Profile.vue:94`）是原样渲染——DOM 的第 i 行就是数组的第 i 项，这个对应
 * 关系本身就是被测的一环。UA 在这里帮不上忙：两个 context 的 User-Agent 一模一样。
 *
 * 明确不声称的三件事（实测出来的边界，不是偷懒）：
 * 1. 主题那颗单选钮**刷新后的选中态是不确定的**：`Profile.vue:18` 在 setup 里快照
 *    `getTheme()`，而 `useAuth.ts:47` 的 `loadAccountTheme()` 是 fire-and-forget。所以这里
 *    只断言 `html[data-theme]`（那才是真生效的那个属性），不碰 radio。
 * 2. 原始 token 从不进任何响应（`auth_service.py:428` 只回摘要），"摘要推不回原值"这层在
 *    浏览器接缝上测不到。
 * 3. 退掉**自己当前**这一台在后端是合法的（204，行照删），但界面把按钮藏了
 *    （`Profile.vue:217` 的 `v-if="!device.current"`），浏览器走不到那条路；本用例只能由
 *    member 删 owner 那一步的 404 侧证闸门在位。
 *
 * 收尾会把口令换回 `E2E_PASSWORD`（后面的第 15、16 条还要用它登录），换回写在 `finally`
 * 里；万一它失败，表现是后面两条在登录处 401，不是静默错位。除此之外它给库里留下的是
 * owner 的 `theme='dark'` 和两三行活会话——`transcode` 与 `video-delete` 都不读这两样。
 */
import { expect, test, type Browser, type Page } from '@playwright/test'
import { APP_PORT, E2E_MEMBER_USERNAME, E2E_PASSWORD, E2E_USERNAME } from './env'
import { CSRF, fetchInPage, requestJson, signIn } from './support'

/** 轮换口令用的第二个值，只在条用例内部出现，跑完换回原值。 */
const ROTATED = 'e2e-rotated-password'

type Device = { token_hash: string; current: boolean }

const hashes = (rows: Device[]): string[] => rows.map((row) => row.token_hash)

/** 服务端那份「我的设备」，按它自己的顺序。 */
function devices(page: Page): Promise<Device[]> {
  return requestJson<Device[]>(page, '/api/auth/sessions')
}

/**
 * 再起一台浏览器：新 context = 新 cookie jar + 空的 localStorage，所以它看到的主题一定
 * 来自服务端，而不是本机上次留下的缓存。`newContext` 不继承 config 里的 `use`，baseURL
 * 要自己带上，否则相对地址拼不出来。
 */
async function anotherBrowser(browser: Browser, username = E2E_USERNAME): Promise<Page> {
  const context = await browser.newContext({
    baseURL: `http://localhost:${APP_PORT}`,
    locale: 'zh-CN',
  })
  const page = await context.newPage()
  await signIn(page, username)
  return page
}

test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('个人设置页：退掉的是那一台而不是这一台，主题只跟着这个账号走', async ({ page, browser }) => {
  // ---------- 1. 列表本身：每行一个浏览器，且"就是这台"恰有一枚 ----------
  const base = await devices(page)
  expect(base.length).toBeGreaterThan(0)
  for (const row of base) expect(row.token_hash).toMatch(/^[0-9a-f]{64}$/)
  // 摘要是主键，所以两行不可能同值；真同值说明 `create_session` 复用了 token
  expect(new Set(hashes(base)).size).toBe(base.length)
  const mine = base.filter((row) => row.current)
  expect(mine).toHaveLength(1)

  // ---------- 2. 第二台登录：多出来的那一行是它的，`current` 是各自视角的 ----------
  const second = await anotherBrowser(browser)
  const withSecond = await devices(page)
  const extra = hashes(withSecond).filter((hash) => !hashes(base).includes(hash))
  expect(extra, '第二台登录应当只多出一行').toHaveLength(1)
  // 从第二台读到的行集合和顺序与第一台完全一致，但它标出来的"当前"是另一行——
  // 这一句挡的是把 `current` 存成列、或者拿创建时间当"当前"的那种写法。
  const asSecond = await devices(second)
  expect(hashes(asSecond)).toEqual(hashes(withSecond))
  expect(asSecond.filter((row) => row.current).map((row) => row.token_hash)).toEqual(extra)

  // ---------- 3. 界面上那几行就是服务端那几行 ----------
  await page.goto('/profile')
  const rows = page.locator('.device-item')
  await expect(rows).toHaveCount(withSecond.length)
  await expect(page.getByText('当前设备')).toHaveCount(1)
  const currentIndex = hashes(withSecond).indexOf(mine[0].token_hash)
  await expect(rows.nth(currentIndex).locator('.el-tag')).toHaveText('当前设备')
  await expect(rows.nth(currentIndex).getByText('管这一台')).toBeVisible()
  await expect(rows.nth(currentIndex).getByRole('button', { name: '退出', exact: true })).toHaveCount(0)
  // 其余每一行都有能按的那颗钮
  await expect(rows.getByRole('button', { name: '退出', exact: true })).toHaveCount(withSecond.length - 1)

  // ---------- 4. 从界面上退掉第二台：只少那一行，另一台照常干活 ----------
  const extraIndex = hashes(withSecond).indexOf(extra[0])
  await rows.nth(extraIndex).getByRole('button', { name: '退出', exact: true }).click()
  await expect(page.locator('.el-message--success')).toContainText('该设备已退出')
  // `handleRevoke` 是本地筛一遍就收工（`Profile.vue:107`），所以点「刷新」逼服务端重答一次：
  // 下面这份清单才是库里真的少了一行、而且只少了一行。
  await page.locator('.card-header').getByRole('button', { name: '刷新' }).click()
  const afterRevoke = await devices(page)
  expect(hashes(afterRevoke).sort()).toEqual(
    hashes(withSecond).filter((hash) => hash !== extra[0]).sort(),
  )
  await expect(rows).toHaveCount(afterRevoke.length)
  // 被退的那台从此要重新登录，这台不受影响——这句是整条用例唯一能证明"删的是对的行"的
  expect((await fetchInPage(second, '/api/auth/me')).status).toBe(401)
  expect((await fetchInPage(page, '/api/auth/me')).status).toBe(200)

  // ---------- 5. 换一个人的 cookie 来删同一枚摘要：404，而且那一行还在 ----------
  const member = await anotherBrowser(browser, E2E_MEMBER_USERNAME)
  const stolen = await requestJson<{ detail: string }>(
    member,
    `/api/auth/sessions/${mine[0].token_hash}`,
    { method: 'DELETE', expectStatus: 404 },
  )
  expect(stolen.detail).toBe('设备不存在或已退出')
  expect(hashes(await devices(page)).sort()).toEqual(hashes(afterRevoke).sort())
  expect((await fetchInPage(page, '/api/auth/me')).status).toBe(200)

  // 形状不对的摘要根本进不到服务层：`auth.py:158` 的 `Path(pattern=...)` 先给 422。
  // 不带这个模式的话它会一路走到 `revoke_session` 然后回 404——两个码分得很清，所以这一句
  // 钉得住。用 owner 发：member 发这个地址会先撞中间件的白名单正则（同一条 `TOKEN_HASH_HEX`），
  // 拿到的是 403，那就测不到路由这一层了。
  const shaped = await fetchInPage(page, '/api/auth/sessions/zZZ', { method: 'DELETE', headers: CSRF })
  expect(shaped.status).toBe(422)

  // ---------- 6. 主题：选了即存，存的是这个账号的，不是这台浏览器的 ----------
  await page.locator('.card-theme .el-radio', { hasText: '深色' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  // PUT 是 `void updatePreferences(...).catch()`（`useTheme.ts:40`），不 await，所以要 poll；
  // 读也换一条**独立的路径**读：PUT 的响应回显的就是刚写进去的那份，拿它当证据等于自证。
  await expect
    .poll(async () => (await requestJson<{ theme: string }>(page, '/api/preferences')).theme)
    .toBe('dark')
  // 另一个人不该看见它（播种从没写过 `user_preferences`，所以成员这里就是默认值）
  expect((await requestJson<{ theme: string }>(member, '/api/preferences')).theme).toBe('light')
  // 第三台全新浏览器：没有 localStorage 可依赖，深色只能是从库里拉回来的
  const third = await anotherBrowser(browser)
  expect((await requestJson<{ theme: string }>(third, '/api/preferences')).theme).toBe('dark')
  await third.goto('/profile')
  await expect(third.locator('html')).toHaveAttribute('data-theme', 'dark')

  // ---------- 7. 闸门：不在 `Literal` 里的值进不了那张 JSON 列 ----------
  const bogus = await requestJson<{ detail: unknown }>(page, '/api/preferences', {
    method: 'PUT',
    body: { theme: 'neon' },
    expectStatus: 422,
  })
  expect(bogus.detail).toBeTruthy()
  expect((await requestJson<{ theme: string }>(page, '/api/preferences')).theme).toBe('dark')

  // ---------- 8. 改密码：那句「其他浏览器会被退出，这台仍然保持登录」是写在界面上的 ----------
  try {
    const fields = page.locator('.card-password .el-input__inner')
    await fields.nth(0).fill(E2E_PASSWORD)
    await fields.nth(1).fill(ROTATED)
    await fields.nth(2).fill(ROTATED)
    await page.getByRole('button', { name: '更新密码' }).click()
    // `.last()`：第 4 步那句「该设备已退出」的浮层可能还挂在 DOM 上（Element Plus 3 秒才收），
    // 而两条都是 `.el-message--success`，不取最后一条就是 strict mode 二义。
    await expect(page.locator('.el-message--success').last()).toContainText('密码已更新')
    // `Profile.vue:49` 是重读而不是本地删，所以这一句直接对得上库
    await expect(rows).toHaveCount(1)
    await expect(page.getByText('当前设备')).toHaveCount(1)
    expect(hashes(await devices(page))).toEqual([mine[0].token_hash])
    expect((await fetchInPage(page, '/api/auth/me')).status).toBe(200)
    // 第三台（改密码前签进来的）从此要拿新口令重来
    expect((await fetchInPage(third, '/api/auth/me')).status).toBe(401)
    // 批量撤销只动这个账号：member 那台还在
    expect((await fetchInPage(member, '/api/auth/me')).status).toBe(200)
  } finally {
    // 口令必须换回去——后面的第 15、16 条要用 `E2E_PASSWORD` 登录。这一句里**不断言**：
    // `finally` 里抛出的错误会把上面真正的失败原因整条盖掉（实测：变异 F 下第 8 步先红，
    // 报出来的却是这里），而"到底换没换回去"由下面那次真登录去证。
    // 也不复用 `page`：F 那种写法正是把这台的会话也退了，此时它的 cookie 已经作废。
    const rescue = await browser.newContext({
      baseURL: `http://localhost:${APP_PORT}`,
      locale: 'zh-CN',
    })
    const rescuePage = await rescue.newPage()
    await rescuePage.goto('/login')
    const rotatedLogin = await fetchInPage(rescuePage, '/api/auth/login', {
      method: 'POST',
      headers: { ...CSRF, 'content-type': 'application/json' },
      body: JSON.stringify({ username: E2E_USERNAME, password: ROTATED }),
    })
    if (rotatedLogin.status === 200) {
      await fetchInPage(rescuePage, '/api/auth/password', {
        method: 'POST',
        headers: { ...CSRF, 'content-type': 'application/json' },
        body: JSON.stringify({ old_password: ROTATED, new_password: E2E_PASSWORD }),
      })
    }
    await rescue.close()
  }

  // 复原真的生效了：再开一台全新浏览器，用原口令走一遍真登录表单。
  const revived = await anotherBrowser(browser)
  await expect(revived.locator('.user-name')).toHaveText('E2E')
})
