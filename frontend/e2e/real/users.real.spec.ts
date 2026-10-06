/**
 * 真后端 e2e 的第 18 条：用户管理页那五条写路径，两头都要落——库里那一行，和**别的那台浏览器**
 * 当场失效这件事。
 *
 * `Users.vue` 是这一页第一次打真库：第 7 条只让它列出账号、读那一格设备数。替身那一侧
 * （`e2e/roles.spec.ts`）有建号、改角色、重置密码、踢下线四条，可它们签的是夹具里手写的响应表。
 *
 * 后端接口层（`backend/tests/test_api/test_users.py`）把语义签得很死：建完能登录、重名 400、弱密码
 * 400、停用会切断会话、重置密码后旧口令失效、踢下线报数。所以这条用例**不是**去重抄那份断言。它签
 * 的是那份表在浏览器接缝上独有的三段：
 * 1. **服务端那句原因要一路走到人眼前**。四个失败各有各的闸门：pydantic 的 422（`username` 短了）、
 *    服务层的 400（账号名正则、重名、弱密码）。它们在界面上都只剩 `.el-message--error` 一句话，而那
 *    句话是 `client.ts` 把 `detail` 摊平成 `Error.message` 再拼上前缀出来的——#74 与 #126 两次断掉的
 *    都是这一环，页面退成写死的兜底文案。替身给不出这种断法：它那份 400 是前端自己写的。
 * 2. **一台浏览器的 Cookie 被另一台的动作作废**。停用、降级别人、重置密码、踢下线，四种动作的落点都
 *    是「那一台从此 401、这一台照常干活」，而 `signed_in_devices` 跟着掉到 0。这条链穿过中间件、穿过
 *    axios 那个 401 拦截器、再穿过路由守卫，而接口层那个假客户端只有一个 cookie jar。
 * 3. **角色是每次请求现查的，不是登录时冻在 Cookie 里的**。把成员提上来，他手里**那枚旧的** cookie
 *    下一跳就读得到管理面；反过来把自己降级，会话一行没少，管理面却当场 403。后半句是
 *    `api/users.py` 里 `user.id != actor.id` 那半条判断唯一的签字处——接口层只测过「最后一个管理员
 *    降不得」，没测过「两个管理员时降级自己不踢自己」。
 *
 * 支点句是页面顶部那句谁都当装饰看的说明：「停用的账号会立即在所有浏览器退出，历史与收藏都会保留」。
 * 前半句接口层签了，后半句**一层都没有**：所以这里在停用之前先让那台浏览器真收藏一部片子，启用回来
 * 后卡片还在原地。少了这一句，把「停用」写成「删号」也能让前面所有断言全绿。
 *
 * 一处顺序风险值得说明：中段要让管理员把自己降级，那一刻全库唯一能把他升回来的只有刚提拔的那个成员，
 * 所以那三步（降级自己 → 由它升回自己 → 把它降回成员）之间任何一步崩掉，后面的第 18、19、20 条都会
 * 对着一个没有管理员的库满屏 403。收尾的 `keepAnOwner` 不带断言地补回这个不变量（先试本人自己的
 * 口令，绿的那一路一次登录失败都不产生），跑绿之后仍然真的核对一遍库里的角色。
 *
 * 声称之外的五件事（实测出来的边界，不是偷懒）：
 * - 那一格「登录设备」数的是 `sessions` 表的行数，不筛 `expires_at`，也没有任何定时清理（全仓库只有
 *   `resolve_session` 会在主人回来时删掉自己那一枚过期行）。所以一枚过期 Cookie 在主人回来之前一直
 *   算「还开着」。这里钉的是今天的行为，不是它对不对。
 * - 表单里把角色选成「管理员」建号会顺带认领库里所有无主的收藏/历史/事件/片单（`claim_legacy_rows`）。
 *   这个一次性库里第一个 owner 是播种建的，之后再没有 `user_id IS NULL` 的行，所以那条分支在这台
 *   浏览器上是空跑——要真跑出它得手工把归属列抹回 NULL，那属于接口层的活（`test_database.py` 里
 *   `test_claiming_the_legacy_rows_twice_stays_a_no_op` 签的正是这一句）。
 * - 停用的那条护栏「至少要保留一个可用的管理员，不能停用最后一个」从 HTTP 永远到不了：能调这一格的
 *   actor 自己就是个可用管理员，而 `update_status` 更早就挡下「停用自己」。那句原话只有 CLI 碰得到。
 * - 「登录设备」那一格只跟着**这一台浏览器自己的写**重读（`Users.vue` 只在四个动作的 `finally` 和
 *   `onMounted` 里调 `loadUsers`）。别的浏览器登进来时它停在旧数，而「踢下线」的灰不灰正是按这一个数
 *   算出来的——这里不钉它新不新鲜（那会挡掉将来加的轮询或刷新按钮），只在自己动手刷新一次之后再点。
 * - 「停用会切断会话」这一条由**删掉会话行**那一半把关，不由 `is_active` 那一半：把 `get_current_user`
 *   里的 `not user.is_active` 单独拆掉，这条照样全绿（实测过）。留着那句是因为它防的是"会话行还在、
 *   人已经被停用"那种中间态，而那一种态今天从 HTTP 到不了。
 */
import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'

import { APP_PORT, E2E_PASSWORD, E2E_USERNAME } from './env'
import { CSRF, fetchInPage, requestJson, signIn } from './support'

/** 这一条现建的账号和它的两个口令。口令进版本库不构成凭据：库名必须以 `_test` 结尾才允许被清空。 */
const MANAGED = 'e2e_managed'
const MEMBER = 'e2e_member'
const MANAGED_PASSWORD = 'e2e-managed-password'
const MANAGED_RESET = 'e2e-managed-reset'

type Account = {
  id: number
  username: string
  role: string
  display_name: string | null
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
  signed_in_devices: number
}

const accounts = (page: Page): Promise<Account[]> => requestJson<Account[]>(page, '/api/users')

function byName(rows: Account[], username: string): Account {
  const row = rows.find((entry) => entry.username === username)
  expect(row, `账号 ${username} 不在 /api/users 里`).toBeTruthy()
  return row as Account
}

/** 状态码就够回答「这一台还登着吗」，而且不经过任何前端代码——那是中间件那一侧的证词。 */
const meStatus = (page: Page): Promise<number> =>
  fetchInPage(page, '/api/auth/me').then((response) => response.status)

/** 那一台「我的设备」真有几行——踢下线报的数要对着它，而不是对着界面上的格子。 */
const deviceHashes = (page: Page): Promise<string[]> =>
  requestJson<{ token_hash: string }[]>(page, '/api/auth/sessions').then((rows) =>
    rows.map((row) => row.token_hash),
  )

/**
 * 用真表单登录任意账号。`signIn` 只认 `E2E_PASSWORD`，而这一条要证明的正是「表单里现建的那个口令
 * 真能换来一张 cookie」——那是 bcrypt 的一次完整往返；替身里那句 `signedIn = true` 什么都不是。
 */
async function signInWith(page: Page, username: string, password: string): Promise<void> {
  await page.context().clearCookies()
  await page.goto('/login')
  await page.locator('#login-username').fill(username)
  await page.locator('#login-password').fill(password)
  await page.locator('.submit').click()
  await expect(page).toHaveURL(/\/$/)
}

/** 登录失败的现场：界面那句话，和它停在登录页没走。用一台没有会话的浏览器发，免得动到别人的 Cookie。 */
async function loginRefused(page: Page, username: string, password: string): Promise<string> {
  await page.goto('/login')
  await page.locator('#login-username').fill(username)
  await page.locator('#login-password').fill(password)
  await page.locator('.submit').click()
  const text = (await page.locator('.error').textContent()) ?? ''
  await expect(page).toHaveURL(/\/login/)
  return text.trim()
}

async function newContextPage(browser: Browser): Promise<Page> {
  // `newContext` 不继承 config 里的 `use`，baseURL 要自己带上，否则相对地址拼不出来。
  const context = await browser.newContext({
    baseURL: `http://localhost:${APP_PORT}`,
    locale: 'zh-CN',
  })
  return context.newPage()
}

async function openBrowser(browser: Browser, username: string, password: string): Promise<Page> {
  const page = await newContextPage(browser)
  await signInWith(page, username, password)
  return page
}

const success = (page: Page): Locator => page.locator('.el-message--success').last()
const failure = (page: Page): Locator => page.locator('.el-message--error').last()

/** 表格按 `list_users` 的 id 序渲染，所以先按账号名等到那一行出现，再拿第几行去点。 */
async function rowFor(page: Page, username: string): Promise<Locator> {
  // 用 poll 而不是读一次：`onMounted(loadUsers)` 还在飞的时候 `.cell-username` 是个空列表，
  // 那一刻 indexOf 回 -1，报出来的就是「表格里没有这个账号」——和第 22 条那个同一类坑。
  await expect
    .poll(async () => (await page.locator('.cell-username').allTextContents()).join(','), {
      message: `表格里等不到账号 ${username}`,
    })
    .toContain(username)
  const index = (await page.locator('.cell-username').allTextContents()).indexOf(username)
  return page.locator('.users-table .el-table__row').nth(index)
}

async function pickRole(row: Locator, page: Page, label: string): Promise<void> {
  await row.locator('.el-select').click()
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: label }).click()
}

/**
 * 不带断言地把「库里还有一个能用口令登录的管理员」补回来。
 *
 * 中段把自己降级过一次，那一刻能把他升回来的只有刚提拔的那个成员；如果用例死在那三步中间，后面的
 * 第 18、19、20 条看到的就是一个没有管理员的库。所以这里按「本人 → 那个成员（旧口令 → 新口令）」
 * 各试一次：谁登进来且角色是 owner，就用它把 owner 那一行写回去。这里**一句都不断**——`finally`
 * 里抛出会把真正的失败原因整条盖掉（同 `profile.real.spec.ts` 那次实测）。
 */
async function keepAnOwner(browser: Browser, ownerId: number): Promise<void> {
  // 本人排在第一个：他的口令这一条从没动过，所以绿的那一路登得进来、也不需要任何重试；
  // 只有当他已经被降级（就是这里要救的那种死法）时才轮到那个刚提拔的成员。
  const attempts = [
    { username: E2E_USERNAME, password: E2E_PASSWORD },
    { username: MANAGED, password: MANAGED_PASSWORD },
    { username: MANAGED, password: MANAGED_RESET },
  ]
  for (const attempt of attempts) {
    const page = await newContextPage(browser)
    await page.goto('/login')
    const login = await fetchInPage(page, '/api/auth/login', {
      method: 'POST',
      headers: { ...CSRF, 'content-type': 'application/json' },
      body: JSON.stringify({ username: attempt.username, password: attempt.password }),
    })
    let restored = false
    if (login.status === 200 && (JSON.parse(login.text) as { role: string }).role === 'owner') {
      await fetchInPage(page, `/api/users/${ownerId}/role`, {
        method: 'PUT',
        headers: { ...CSRF, 'content-type': 'application/json' },
        body: JSON.stringify({ role: 'owner' }),
      })
      restored = true
    }
    await page.context().close()
    if (restored) return
  }
}

test.beforeEach(async ({ page }) => {
  await signIn(page)
})

// 30 秒那道默认闸是照「一条用例一个页面几步点完」定的，这条不是那种：四个真浏览器各自登录过一次，
// 每一次登录都要过一遍 bcrypt，中间还夹着一次 `page.reload()`。本机绿的那一遍是 17 秒——离那道闸
// 只剩 13 秒的余量，而这台机器一有别的负载，慢的就是这种靠真哈希计时的用例。放宽的是墙，不是断言。
test('用户管理那五条写路径打真库：现建的口令能真登录，被改动的那台浏览器当场掉回登录页', async ({
  page,
  browser,
}) => {
  test.setTimeout(90_000)
  const owner = byName(await accounts(page), E2E_USERNAME)
  const opened: Page[] = []

  try {
    // ---------- 1. 从表单建一个账号：写进库的是真 bcrypt 摘要，界面上多的是真行 ----------
    await page.goto('/users')
    await expect(page.locator('.users-table .el-table__row')).toHaveCount(2)
    await page.getByRole('button', { name: '新建账号' }).click()
    const dialog = page.locator('.el-dialog')
    const nameBox = dialog.locator('input[placeholder="小写字母、数字或 . _ -"]')
    const passBox = dialog.locator('input[placeholder="至少 8 位"]')
    await nameBox.fill(MANAGED)
    await passBox.fill(MANAGED_PASSWORD)
    // 昵称那一格**故意留空**：服务层写的是 `(display_name or cleaned)`，所以「可留空」落到库里不是
    // NULL 而是账号名本身。下面顶栏那个名字就是这一句的落点。
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(success(page)).toContainText('账号已创建')
    await expect(dialog).toBeHidden()

    const created = await accounts(page)
    expect(created.map((entry) => entry.username)).toEqual([E2E_USERNAME, MEMBER, MANAGED])
    const managed = byName(created, MANAGED)
    // 回读而不是信回显：这一整格都是刚从库里查出来的（`created_at` 每次跑都不同，所以只核它非空）
    expect({ ...managed, id: 0, created_at: null }).toEqual({
      id: 0,
      username: MANAGED,
      role: 'member',
      display_name: MANAGED,
      is_active: true,
      created_at: null,
      last_login_at: null,
      signed_in_devices: 0,
    })
    expect(managed.created_at).toBeTruthy()

    // 库里那一行和界面上那一行是同一件事：设备数 0，所以「踢下线」这颗钮根本不给点
    const fresh = await rowFor(page, MANAGED)
    await expect(fresh.locator('td').nth(3)).toHaveText('0')
    await expect(fresh.getByRole('button', { name: '踢下线' })).toBeDisabled()
    await expect(fresh.getByRole('button', { name: '重置密码' })).toBeEnabled()

    // ---------- 2. 那个新口令走一遍真登录表单：换来一张真 cookie，也换来一行真会话 ----------
    const managedBrowser = await openBrowser(browser, MANAGED, MANAGED_PASSWORD)
    opened.push(managedBrowser)
    // 顶栏显示的是 display_name，而它从没被填过——这里出现账号名，就是第 1 段那句回退的后半句
    await expect(managedBrowser.locator('.user-name')).toHaveText(MANAGED)
    expect(await meStatus(managedBrowser)).toBe(200)

    await page.goto('/users')
    const logged = await accounts(page)
    expect(byName(logged, MANAGED).signed_in_devices).toBe(1)
    expect(byName(logged, MANAGED).last_login_at).toBeTruthy()

    // ---------- 3. 支点句的后半句：先在那台浏览器上真收藏一部片子 ----------
    const library = await requestJson<{ items: { id: number; title: string | null }[]; total: number }>(
      page,
      '/api/videos',
    )
    expect(library.total).toBeGreaterThan(0)
    const video = library.items[0]
    const favorite = await fetchInPage(managedBrowser, `/api/favorites/${video.id}`, {
      method: 'POST',
      headers: CSRF,
    })
    expect(favorite.status).toBe(201)
    await managedBrowser.goto('/favorites')
    await expect(managedBrowser.locator('.favorite-card')).toHaveCount(1)

    // ---------- 4. 四句拒绝各有各的闸门，而每一句都得原样出现在浮层里 ----------
    await page.goto('/users')
    await page.getByRole('button', { name: '新建账号' }).click()

    // 4a pydantic 先拦下短的：422 的 detail 是数组，摊平成「字段 原因」才有人话
    await nameBox.fill('ab')
    await passBox.fill(MANAGED_PASSWORD)
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(failure(page)).toContainText('创建失败: username 长度至少 3 个字符')

    // 4b 过了 pydantic 才轮到服务层那条正则：大写和中间的空格 normalize 都救不回来
    await nameBox.fill('Bad Name')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(failure(page)).toContainText('创建失败: 账号名需为 3-64 位小写字母、数字或 . _ -')

    // 4c 重名。密码是合规的，所以这一句只可能由「已存在」那条判断给出
    await nameBox.fill(MANAGED)
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(failure(page)).toContainText('创建失败: 账号已存在')

    // 4d 名字还是那一个重名的，报错却是密码的锅——这一句顺手钉住 `create_user` 里两道闸的先后
    await passBox.fill('123')
    await dialog.getByRole('button', { name: '创建' }).click()
    await expect(failure(page)).toContainText('创建失败: 密码至少 8 位')

    // 四次都没写成：库里那一行不多不少，界面上也没有第四行
    await dialog.getByRole('button', { name: '取消' }).click()
    expect((await accounts(page)).map((entry) => entry.username)).toEqual([
      E2E_USERNAME,
      MEMBER,
      MANAGED,
    ])
    await expect(page.locator('.users-table .el-table__row')).toHaveCount(3)

    // ---------- 5. 提上去：同一枚旧 cookie 下一跳就有管理面，而且一行会话都没少 ----------
    await pickRole(await rowFor(page, MANAGED), page, '管理员')
    await expect(success(page)).toContainText(`${MANAGED} 已设为管理员`)
    const promoted = byName(await accounts(page), MANAGED)
    expect(promoted.role).toBe('owner')
    expect(promoted.signed_in_devices).toBe(1)
    // 没有重新登录：这一台手里那枚 cookie 是当成员签的，角色是这一跳现查出来的
    expect(await meStatus(managedBrowser)).toBe(200)
    expect(await requestJson<Account[]>(managedBrowser, '/api/users')).toHaveLength(3)

    // ---------- 6. 降级自己不踢自己：会话一行没少，管理面当场 403（那句 `user.id != actor.id`） ----------
    const demoted = await requestJson<Account>(page, `/api/users/${owner.id}/role`, {
      method: 'PUT',
      body: { role: 'member' },
    })
    expect(demoted.role).toBe('member')
    expect(await meStatus(page)).toBe(200)
    expect((await fetchInPage(page, '/api/users')).status).toBe(403)

    // ---------- 7. 由那个新管理员把自己升回来：还是同一枚 cookie，下一跳又有管理面 ----------
    await requestJson<Account>(managedBrowser, `/api/users/${owner.id}/role`, {
      method: 'PUT',
      body: { role: 'owner' },
    })
    expect(byName(await accounts(page), E2E_USERNAME).role).toBe('owner')

    // ---------- 8. 降级别人：那一台当场作废，这一台不动 ----------
    await pickRole(await rowFor(page, MANAGED), page, '成员')
    await expect(success(page)).toContainText(`${MANAGED} 已设为成员`)
    expect(await meStatus(managedBrowser)).toBe(401)
    expect(await meStatus(page)).toBe(200)
    expect(byName(await accounts(page), MANAGED).signed_in_devices).toBe(0)
    // 那一台上正在看的页面被送回登录页，还带上「回来去哪儿」——这条链是拦截器和守卫接力的结果
    await managedBrowser.goto('/favorites')
    await expect(managedBrowser).toHaveURL(/\/login\?redirect=\/favorites$/)

    // 重新登录换来一枚新 cookie：这次挡在他前面的不是会话，是角色
    await signInWith(managedBrowser, MANAGED, MANAGED_PASSWORD)
    expect(await fetchInPage(managedBrowser, '/api/users').then((r) => r.status)).toBe(403)

    // ---------- 9. 两条护栏：自己那一格不给点，最后一个管理员降不得 ----------
    const selfRow = await rowFor(page, E2E_USERNAME)
    await expect(selfRow.locator('.el-switch input')).toBeDisabled()
    const selfDisabled = await requestJson<{ detail: string }>(page, `/api/users/${owner.id}/status`, {
      method: 'PUT',
      body: { is_active: false },
      expectStatus: 400,
    })
    expect(selfDisabled.detail).toBe('不能停用自己的账号')

    // 此刻可用管理员只剩这一个：`_require_another_owner` 那句话在这里，而不是在第 6 段
    const lastOwner = await requestJson<{ detail: string }>(page, `/api/users/${owner.id}/role`, {
      method: 'PUT',
      body: { role: 'member' },
      expectStatus: 400,
    })
    expect(lastOwner.detail).toBe('至少要保留一个可用的管理员，不能降级最后一个')
    expect(byName(await accounts(page), E2E_USERNAME).role).toBe('owner')
    // 同一段在界面上的样子：浮层给原话，下拉退回管理员（服务端点头之前表格不该自己先改）
    const ownerRow = await rowFor(page, E2E_USERNAME)
    await pickRole(ownerRow, page, '成员')
    await expect(failure(page)).toContainText('改角色失败: 至少要保留一个可用的管理员')
    await expect(ownerRow.locator('.el-select')).toContainText('管理员')

    // ---------- 10. 停用那一个：所有浏览器退出，而收藏还在（那句「历史与收藏都会保留」） ----------
    await signInWith(managedBrowser, MANAGED, MANAGED_PASSWORD)
    expect(await meStatus(managedBrowser)).toBe(200)
    await (await rowFor(page, MANAGED)).locator('.el-switch').click()
    await expect(success(page)).toContainText('账号已停用，该账号的所有浏览器都已退出')
    const off = byName(await accounts(page), MANAGED)
    expect(off.is_active).toBe(false)
    expect(off.signed_in_devices).toBe(0)
    expect(await meStatus(managedBrowser)).toBe(401)
    await managedBrowser.goto('/favorites')
    await expect(managedBrowser).toHaveURL(/\/login\?redirect=\/favorites$/)

    const visitor = await newContextPage(browser)
    opened.push(visitor)
    // 停用与密码错误共用同一句话，免得这条地址用来枚举账号——而库里那一行明明白白是停用
    expect(await loginRefused(visitor, MANAGED, MANAGED_PASSWORD)).toBe('账号或密码错误')

    await (await rowFor(page, MANAGED)).locator('.el-switch').click()
    await expect(success(page)).toContainText('账号已启用')
    expect(byName(await accounts(page), MANAGED).is_active).toBe(true)
    await signInWith(managedBrowser, MANAGED, MANAGED_PASSWORD)
    await managedBrowser.goto('/favorites')
    await expect(managedBrowser.locator('.favorite-card')).toHaveCount(1)
    await expect(managedBrowser.locator('.video-title')).toContainText(video.title ?? '')

    // ---------- 11. 重置密码：界面那道 8 位的闸和后端那道各管一头 ----------
    await (await rowFor(page, MANAGED)).getByRole('button', { name: '重置密码' }).click()
    const box = page.locator('.el-message-box')
    await expect(box).toContainText(`为 ${MANAGED} 设置新密码`)
    await box.locator('input').fill('778899')
    await box.getByRole('button', { name: '重置' }).click()
    // 前端闸：短了连请求都不发——浮层还开着，那一台手里那枚会话也还在
    await expect(box.locator('.el-message-box__errormsg')).toBeVisible()
    expect(byName(await accounts(page), MANAGED).signed_in_devices).toBe(1)
    await box.locator('input').fill(MANAGED_RESET)
    await box.getByRole('button', { name: '重置' }).click()
    await expect(box).toHaveCount(0)
    await expect(success(page)).toContainText(`已重置 ${MANAGED} 的密码`)
    expect(await meStatus(managedBrowser)).toBe(401)
    expect(byName(await accounts(page), MANAGED).signed_in_devices).toBe(0)
    expect(await loginRefused(visitor, MANAGED, MANAGED_PASSWORD)).toBe('账号或密码错误')
    const resetBrowser = await openBrowser(browser, MANAGED, MANAGED_RESET)
    opened.push(resetBrowser)
    expect(await meStatus(resetBrowser)).toBe(200)

    // ---------- 12. 踢下线：报出来的数就是那一台手里真有的行数 ----------
    const live = await deviceHashes(resetBrowser)
    expect(live).toHaveLength(1)
    // 那一格只在**这一台浏览器**做过一次写之后才重读；别的浏览器刚登进来时它还是旧数，
    // 而「踢下线」的灰不灰正是按那一个数算出来的（`Users.vue` 的 `:disabled="!row.signed_in_devices"`）。
    // 所以这里刷新一次页面走 `onMounted(loadUsers)`，而不是去钉那一格新不新鲜。
    await page.reload()
    await (await rowFor(page, MANAGED)).getByRole('button', { name: '踢下线' }).click()
    const confirm = page.locator('.el-message-box')
    await expect(confirm).toContainText(`退出 ${MANAGED} 的所有浏览器`)
    await confirm.getByRole('button', { name: '退出登录' }).click()
    await expect(success(page)).toContainText(`已退出 ${live.length} 个设备`)
    expect(await meStatus(resetBrowser)).toBe(401)
    expect(await meStatus(page)).toBe(200)
    expect(byName(await accounts(page), MANAGED).signed_in_devices).toBe(0)
    // 设备归零之后这颗钮又灰了——它不是装饰，是按库里那一列算出来的
    await expect(
      (await rowFor(page, MANAGED)).getByRole('button', { name: '踢下线' }),
    ).toBeDisabled()

    // ---------- 13. 撤销会话从不动个人数据：那台浏览器重新登回来，收藏一行没少 ----------
    await signInWith(resetBrowser, MANAGED, MANAGED_RESET)
    const kept = await requestJson<{ total: number }>(resetBrowser, '/api/favorites')
    expect(kept.total).toBe(1)
    // 收干净：这条留下的收藏挂在那个现建的账号名下，后面的用例读不到，但没必要留
    expect(
      await fetchInPage(resetBrowser, `/api/favorites/${video.id}`, { method: 'DELETE', headers: CSRF }),
    ).toMatchObject({ status: 204 })
    expect(
      await requestJson<{ total: number }>(resetBrowser, '/api/favorites').then((r) => r.total),
    ).toBe(0)
  } finally {
    for (const extra of opened) await extra.context().close()
    await keepAnOwner(browser, owner.id)
  }

  // 复原真的生效了：这一条之后还有第 18、19、20 条要用管理员身份动手
  const ending = await accounts(page)
  expect(byName(ending, E2E_USERNAME).role).toBe('owner')
  expect(byName(ending, E2E_USERNAME).is_active).toBe(true)
  expect(byName(ending, MANAGED).role).toBe('member')
  expect(byName(ending, MANAGED).is_active).toBe(true)
  expect(ending.map((entry) => entry.username)).toEqual([E2E_USERNAME, MEMBER, MANAGED])
})
