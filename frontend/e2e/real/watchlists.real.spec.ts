/**
 * 真后端 e2e 的第 26 条：片单页那三条写路径——改名、移出、删单——第一次打到真库。
 *
 * 为什么是这三条：#104 那次只签了**建**（从详情页的弹窗里新建一条并把片子丢进去），而
 * `Watchlists.vue` 上另外三个动作从来没有过一次真后端。替身夹具那边是有实现的，但那是份
 * 手抄本（`e2e/fixtures.ts:1043` 的 PUT、:1096 的移出、:1103 的删单），而那份手抄本
 * (a) 没有 409——桩世界里「改成同一账号另一条片单的名字」是一次绿色 toast，
 * (b) 没有归属——它按 id 直接找，谁点都改得动，
 * (c) 连 404 的措辞都是自己编的：桩里那三处一律回「片单不存在」，而真后端是两套——读那一路
 *    是路由那句「片单不存在」（#188 之后正好和桩撞同），三条写那一路是服务层带着 id 的
 *    「片单 #7 不存在」。前端不知道自己抄的是谁的规则，抄歪了不会红。
 *
 * 顺带量出来的两行：`watchlist_service.py:129`（`watchlist.description = description`）和
 * `api/watchlists.py:125`（改名撞名那句 `raise HTTPException(409)`）在后端测试套里**一次也没
 * 被执行过**——前者是因为没有一个测试往已有片单上 PUT 过备注，后者是因为 409 只在 POST 那一路
 * 撞过（`tests/test_api/test_isolation.py:61`）。这条用例把两句都走到了。
 *
 * 真库才答得出的三件事，一次签完：
 * 1. 改名撞**本人**另一条时是 409 原话，而不是让 PG 那条 `ux_watchlist_owner_name` 抛出去变成
 *    500；反向那一半（改成**成员**那条的名字）必须是 200，签的是索引真的带 owner_id。
 * 2. 移出与删单的谓词范围：这条用例让**同一部片子同时坐在两条片单里**，于是「把甲号那一条端走」
 *    会不会连乙号那一行一起端、删单会不会顺着 video_id 去清别人的行，都有东西可红。夹具播种
 *    那条片单也收着同一部片子，收尾拿它当"不该被动的那一行"。
 * 3. `update` 里那句 `if description is not None`：只带 name 的 PUT 不能把备注抹掉。后端测试
 *    那句 `assert renamed.description is None`（`test_watchlist_service.py:126`）钉的是一条本来
 *    就没有备注的片单，正反两面都没签住。
 *
 * 变异量出来的一件事，和我下笔前的预判**相反**：我原以为摘掉 `Watchlist.items` 上的
 * `cascade="all, delete-orphan"`（`models/watchlist.py:39`）测不出来，因为
 * `watchlist_items.watchlist_id` 那个外键自己也带 `ondelete="CASCADE"`（同文件 :58）。实测它红在
 * 第 9 步——没有 `delete-orphan` 的关系上 `watchlist.items.remove(item)` 不是删子行，而是把它的
 * `watchlist_id` **置空**，PG 立刻以 not-null violation 回一句 500。所以「移出」这一半是真签住了。
 * 剩下「删单」那一半仍是盲区：那一路 `session.delete(watchlist)` 之后 PG 的 FK 会替它把子行端走，
 * 而 M7 在第 9 步就先红了、根本走不到那里。所以「摘掉一道机制测不出来」这句只对「删单」成立，
 * 不能挪到「移出」上。
 *
 * 顺序：文件名 `watchlists…` 按字母排在这套的最后，是第 26 条（`-g 三条写路径`）。它不动播种那
 * 两条片单的任何一列，自己造的三条在 `finally` 里**按身份**收干净（成员那一条只能由成员删），
 * 并在 `finally` 之后用真读回核对（#120：断言不写在收尾的 body 里，否则真正的失败会被自己的
 * 还原断言盖住）。
 */
import { expect, test, type Page } from '@playwright/test'

import { E2E_MEMBER_USERNAME } from './env'
import { CSRF, fetchInPage, requestJson, signIn } from './support'

/** `WatchlistResponse` 里这条用例真正在用的那几项。 */
type Queue = {
  id: number
  name: string
  description: string | null
  created_at: string
  items: { id: number; title: string | null }[]
}

/** 播种那部片子的 id——#104 起它就是这套用例共用的那一条影片行。 */
const VIDEO_ID = 1

/** 五个名字两两互不为子串：面板是按 hasText 找的，前缀撞了就会一次命中两格。 */
const LIST_A = 'E2E 甲号队列'
const LIST_A2 = 'E2E 甲号改名后'
const LIST_A3 = 'E2E 甲号只填名'
const LIST_B = 'E2E 乙号队列'
const LIST_M = 'E2E 丙号成员建'
const DESC_1 = '甲号建单时写的那句备注'
const DESC_2 = '甲号只改备注那一次'

const listOf = (page: Page, id: number): Promise<Queue> =>
  requestJson<Queue>(page, `/api/watchlists/${id}`)
const allLists = (page: Page): Promise<Queue[]> => requestJson<Queue[]>(page, '/api/watchlists')
const namesOf = (lists: Queue[]): string[] => lists.map((list) => list.name).sort()
const idsOf = (lists: Queue[]): number[] =>
  lists.map((list) => list.id).sort((left, right) => left - right)
const queuedIds = (list: Queue): number[] => list.items.map((item) => item.id)

/** `GET /api/watchlists?video_id=` 那条子查询：哪些片单收着这部片子。 */
async function listsHolding(page: Page): Promise<number[]> {
  return idsOf(
    await requestJson<Queue[]>(page, `/api/watchlists?video_id=${VIDEO_ID}`),
  )
}

async function notificationTotal(page: Page): Promise<number> {
  return (await requestJson<{ total: number }>(page, '/api/notifications')).total
}

const panel = (page: Page, name: string) => page.locator('.list-panel', { hasText: name })
const renameDialog = (page: Page) => page.locator('.el-dialog', { hasText: '重命名片单' })
const success = (page: Page) => page.locator('.el-message--success').last()
const failure = (page: Page) => page.locator('.el-message--error').last()

/**
 * 走界面改一次名：填名字、（给定时）填备注、保存。
 *
 * 这里只点不核对——核对一律走真读回。`Watchlists.vue:85` 把 PUT 的回声直接写进
 * `lists.value`，所以在「库里没动」的那个错误世界里，面板上的新名字照样显示。
 */
async function renameThroughUi(
  page: Page,
  from: string,
  to: string,
  description?: string,
): Promise<void> {
  await panel(page, from)
    .locator('.list-actions')
    .getByRole('button', { name: '重命名' })
    .click()
  const dialog = renameDialog(page)
  await expect(dialog).toBeVisible()
  await dialog.locator('.el-input input').fill(to)
  if (description !== undefined) {
    await dialog.locator('.form-desc textarea').fill(description)
  }
  await dialog.getByRole('button', { name: '保存' }).click()
}

/** 界面上点「删除片单」并在那句确认上点「删除」。确认文案由调用方先核对。 */
async function eraseThroughUi(page: Page, name: string): Promise<void> {
  await panel(page, name).getByRole('button', { name: '删除片单' }).click()
  const box = page.locator('.el-message-box')
  await expect(box).toBeVisible()
  await box.locator('.el-message-box__btns button', { hasText: '删除' }).click()
}

/**
 * 直接发一次 PUT，把状态码连同 detail 原话一起读回来。
 *
 * 不能用 `requestJson`：它先把非 2xx 判成失败，而这里要的正是那个 409。
 */
async function putWatchlist(
  page: Page,
  id: number,
  body: Record<string, unknown>,
): Promise<{ status: number; detail: string; list: Queue }> {
  const response = await fetchInPage(page, `/api/watchlists/${id}`, {
    method: 'PUT',
    headers: { ...CSRF, 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  const parsed = JSON.parse(response.text) as Partial<Queue> & { detail?: string }
  return {
    status: response.status,
    detail: typeof parsed.detail === 'string' ? parsed.detail : '',
    list: parsed as Queue,
  }
}

/** 只发 DELETE、不看状态码：收尾不该用一句自夸盖住真正的失败（#120）。 */
async function tryDelete(page: Page, path: string): Promise<void> {
  await fetchInPage(page, path, { method: 'DELETE', headers: CSRF })
}

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec 上，
// 挂错地方的实测症状是这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('片单那三条写路径打真库：改名撞本人重名是 409、移出只端自己那一行、删单不碰同名那条', async ({
  page,
}) => {
  const before = await allLists(page)
  const beforeNames = namesOf(before)
  const holdingBefore = await listsHolding(page)
  const notifBefore = await notificationTotal(page)

  let listA = 0
  let listB = 0
  let listM = 0
  let createdAtA = ''

  try {
    // ---- 1. 自己造两条片单，把**同一部**片子放进两条里：后面那两条谓词全靠这个形状才有东西可红
    listA = (
      await requestJson<Queue>(page, '/api/watchlists', {
        method: 'POST',
        body: { name: LIST_A, description: DESC_1 },
        expectStatus: 201,
      })
    ).id
    listB = (
      await requestJson<Queue>(page, '/api/watchlists', {
        method: 'POST',
        body: { name: LIST_B },
        expectStatus: 201,
      })
    ).id
    const created = await listOf(page, listA)
    createdAtA = created.created_at
    expect([created.name, created.description]).toEqual([LIST_A, DESC_1])
    // 建完是空的：`WatchlistService.create` 那句读回交的是 `items: []`
    expect(created.items).toEqual([])

    for (const id of [listA, listB]) {
      const queued = await requestJson<Queue>(page, `/api/watchlists/${id}/videos`, {
        method: 'POST',
        body: { video_id: VIDEO_ID },
      })
      expect(queuedIds(queued)).toEqual([VIDEO_ID])
    }
    const holdingBoth = await listsHolding(page)
    expect(holdingBoth).toEqual([...holdingBefore, listA, listB].sort((x, y) => x - y))

    // ---- 2. 界面上改名，只动名字：备注、时间戳、队列都得原样
    await page.goto('/watchlists')
    await expect(panel(page, LIST_A).locator('.list-desc')).toHaveText(DESC_1)
    await renameThroughUi(page, LIST_A, LIST_A2)
    await expect(success(page)).toContainText('片单已更新')

    const renamed = await listOf(page, listA)
    expect([renamed.name, renamed.description]).toEqual([LIST_A2, DESC_1])
    // `created_at` 也得还是建单那一次：改名要是走成"删了重建"，这一列和队列位置就是它留下的痕迹
    expect(renamed.created_at).toBe(createdAtA)
    expect(queuedIds(renamed)).toEqual([VIDEO_ID])
    // 第三条读路径是整份列表（页面读的就是它），不是单条那一个接口
    expect(namesOf(await allLists(page))).toContain(LIST_A2)

    // ---- 3. 名字一个字没改、只改备注：那是一次**同名** PUT，本人范围的唯一索引不能把自己撞死
    await page.goto('/watchlists')
    await renameThroughUi(page, LIST_A2, LIST_A2, DESC_2)
    await expect(success(page)).toContainText('片单已更新')
    const descOnly = await listOf(page, listA)
    expect([descOnly.name, descOnly.description]).toEqual([LIST_A2, DESC_2])

    // ---- 4. PUT 只带 name 那一个键：`if description is not None` 的正面
    const nameOnly = await requestJson<Queue>(page, `/api/watchlists/${listA}`, {
      method: 'PUT',
      body: { name: LIST_A3 },
    })
    // 回声必须带着整条队列：三条写路由都是靠重新读回（`_with_videos` 那句
    // `populate_existing`）把队列一起交回来的，交空列表在页面上就是「这个片单还空着」
    expect(queuedIds(nameOnly)).toEqual([VIDEO_ID])
    expect([nameOnly.name, nameOnly.description]).toEqual([LIST_A3, DESC_2])
    expect((await listOf(page, listA)).description).toBe(DESC_2)

    // ---- 5. 反面那一半：显式给了空串就得真清空（现状是空串，不是 null）
    const cleared = await requestJson<Queue>(page, `/api/watchlists/${listA}`, {
      method: 'PUT',
      body: { description: '' },
    })
    expect(cleared.description).toBe('')
    await page.goto('/watchlists')
    await expect(panel(page, LIST_A3).locator('.list-desc')).toHaveCount(0)

    // ---- 6. 改成**本人**另一条的名字：界面那一路看到的是服务端的原话
    await renameThroughUi(page, LIST_A3, LIST_B)
    // 前缀「保存失败：」是界面的，后面那半句是后端 detail 的原话（#188 之后这句是中文）
    await expect(failure(page)).toContainText(`保存失败：片单「${LIST_B}」已存在`)
    // 保存失败时弹窗不关，名字还停在输入框里：那句 `formVisible.value = false` 只在成功那一路
    await expect(renameDialog(page)).toBeVisible()
    await renameDialog(page).getByRole('button', { name: '取消' }).click()

    const blocked = await putWatchlist(page, listA, { name: LIST_B })
    expect(blocked.status).toBe(409)
    expect(blocked.detail).toBe(`片单「${LIST_B}」已存在`)
    // 409 之后那一行一个字没动。这里没有回声可看，只有真读回算证据
    const untouched = await listOf(page, listA)
    expect([untouched.name, untouched.description, untouched.created_at]).toEqual([
      LIST_A3,
      '',
      createdAtA,
    ])
    expect(queuedIds(untouched)).toEqual([VIDEO_ID])
    expect(queuedIds(await listOf(page, listB))).toEqual([VIDEO_ID])

    // ---- 7. 换成员身份：owner 那两条的 id 在成员手里全是 404，而且那两行原样
    const snapshotA = JSON.stringify(await listOf(page, listA))
    const snapshotB = JSON.stringify(await listOf(page, listB))

    await signIn(page, E2E_MEMBER_USERNAME)
    const memberBefore = await allLists(page)
    expect(namesOf(memberBefore)).not.toContain(LIST_A3)
    expect(namesOf(memberBefore)).not.toContain(LIST_B)
    const memberNamesBefore = namesOf(memberBefore)

    listM = (
      await requestJson<Queue>(page, '/api/watchlists', {
        method: 'POST',
        body: { name: LIST_M },
        expectStatus: 201,
      })
    ).id
    const snapshotM = JSON.stringify(await listOf(page, listM))

    // 三条写路径的 404 都是服务层那句 `ValueError` 原话，消息里**带着 id**（`update` /
    // `delete` / `remove_video` 三处 raise，路由只把 `str(e)` 塞进 detail）。成员拿 owner 的
    // id 去写、和任何人去写一个不存在的 id，得到的是同一句话——越权和不存在在这条路上分不出来。
    const denials: [string, string, string, string | undefined][] = [
      ['PUT', `/api/watchlists/${listA}`, `片单 #${listA} 不存在`, JSON.stringify({ name: '归我' })],
      ['DELETE', `/api/watchlists/${listB}`, `片单 #${listB} 不存在`, undefined],
      [
        'DELETE',
        `/api/watchlists/${listA}/videos/${VIDEO_ID}`,
        `片单 #${listA} 不存在`,
        undefined,
      ],
    ]
    for (const [method, path, detail, body] of denials) {
      const denied = await fetchInPage(page, path, {
        method,
        headers: { ...CSRF, 'content-type': 'application/json' },
        body,
      })
      expect(denied.status, path).toBe(404)
      expect(JSON.parse(denied.text).detail, path).toBe(detail)
    }

    // 读那一路是另一种说法（路由自己 raise 的，不走服务层那句 ValueError），而且**没有 id**：
    // 「这条存在但不归你」和「压根没这条」在响应里是同一个字节串——这一句签的是 owner 过滤
    // 没有把别人的行存在性漏出来。
    const ghost = await fetchInPage(page, '/api/watchlists/999999')
    const foreign = await fetchInPage(page, `/api/watchlists/${listA}`)
    expect(ghost.status).toBe(404)
    expect(foreign.text).toBe(ghost.text)

    await signIn(page)
    // 拒绝发生在服务层之前：两行是整份读回来逐字节比的，不是只看名字那一列
    expect(JSON.stringify(await listOf(page, listA))).toBe(snapshotA)
    expect(JSON.stringify(await listOf(page, listB))).toBe(snapshotB)

    // ---- 8. 反向那一半：改成**成员**那条的名字——索引是 (owner_id, name)，本人范围外不挡
    const crossName = await requestJson<Queue>(page, `/api/watchlists/${listB}`, {
      method: 'PUT',
      body: { name: LIST_M },
    })
    expect([crossName.name, queuedIds(crossName)]).toEqual([LIST_M, [VIDEO_ID]])

    // ---- 9. 界面上「移出」：同一部片子在另一条里的那一行必须还在
    await page.goto('/watchlists')
    await panel(page, LIST_A3)
      .locator('.queue-item')
      .getByRole('button', { name: '移出' })
      .click()
    await expect(success(page)).toContainText('移出片单，影片仍在库里')

    expect(queuedIds(await listOf(page, listA))).toEqual([])
    expect(queuedIds(await listOf(page, listB))).toEqual([VIDEO_ID])
    // 影片行本身也还在：移出删的是 watchlist_items 那一行，不是 videos
    expect((await fetchInPage(page, `/api/videos/${VIDEO_ID}`)).status).toBe(200)
    const holdingAfter = await listsHolding(page)
    expect(holdingAfter).not.toContain(listA)
    expect(holdingAfter).toContain(listB)

    // ---- 10. 跨页面：详情页那个弹窗读的是同一批行，勾的状态得跟片单页一致
    await page.goto(`/videos/${VIDEO_ID}`)
    await page
      .locator('.action-buttons')
      .getByRole('button', { name: '片单', exact: true })
      .click()
    const queueDialog = page.locator('.el-dialog', { hasText: '加入片单' })
    await expect(queueDialog).toBeVisible()
    await expect(queueDialog.locator('.el-checkbox', { hasText: LIST_A3 })).not.toHaveClass(
      /is-checked/,
    )
    const inB = queueDialog.locator('.watchlist-checkbox-item', { hasText: LIST_M })
    await expect(inB.locator('.el-checkbox')).toHaveClass(/is-checked/)
    await expect(inB.locator('.watchlist-count')).toHaveText('1 部')
    await queueDialog.getByRole('button', { name: '取消' }).click()

    // ---- 11. 界面上「删除片单」：确认句里那个数是队列的真实长度，删完两次都 404
    await page.goto('/watchlists')
    await expect(panel(page, LIST_M).locator('.queue-title')).toHaveCount(1)
    await eraseThroughUi(page, LIST_M)
    await expect(success(page)).toContainText('片单已删除')

    expect((await fetchInPage(page, `/api/watchlists/${listB}`)).status).toBe(404)
    // 再删一次：那条路径先按 owner 查、查不到就 404，第二次不能变成 500
    expect(
      (await fetchInPage(page, `/api/watchlists/${listB}`, { method: 'DELETE', headers: CSRF }))
        .status,
    ).toBe(404)
    // 级联只端自己那几行：播种那几条片单里同一部片子的那一行一行没少
    expect(await listsHolding(page)).toEqual(holdingBefore)
    expect((await fetchInPage(page, `/api/videos/${VIDEO_ID}`)).status).toBe(200)

    // ---- 12. 空的那条也从界面上删：确认句里那个数跟着队列一起变成 0
    await page.goto('/watchlists')
    await expect(panel(page, LIST_A3).locator('.queue-empty')).toBeVisible()
    await eraseThroughUi(page, LIST_A3)
    await expect(success(page)).toContainText('片单已删除')
    expect((await fetchInPage(page, `/api/watchlists/${listA}`)).status).toBe(404)

    // ---- 13. 成员那条**同名**片单：owner 删了两次都没碰到它（删单要是走成按名字删，红在这里）
    await signIn(page, E2E_MEMBER_USERNAME)
    expect(JSON.stringify(await listOf(page, listM))).toBe(snapshotM)
    await page.goto('/watchlists')
    await eraseThroughUi(page, LIST_M)
    expect(namesOf(await allLists(page))).toEqual(memberNamesBefore)
  } finally {
    // 收尾也是按身份的：成员那一条只有成员删得动。整段吞掉异常——它不该盖住 body 里真正的失败。
    try {
      await signIn(page)
      if (listA) await tryDelete(page, `/api/watchlists/${listA}`)
      if (listB) await tryDelete(page, `/api/watchlists/${listB}`)
      await signIn(page, E2E_MEMBER_USERNAME)
      if (listM) await tryDelete(page, `/api/watchlists/${listM}`)
      await signIn(page)
    } catch {
      // 尽力而为：下面的真读回会说出这一趟到底有没有留东西在库里
    }
  }

  // 收尾之后才核对：库里那两条播种的片单一条没少、名字一个没改，通知一条没多。
  const after = await allLists(page)
  expect(namesOf(after)).toEqual(beforeNames)
  expect(await listsHolding(page)).toEqual(holdingBefore)
  expect((await fetchInPage(page, `/api/videos/${VIDEO_ID}`)).status).toBe(200)
  expect(await notificationTotal(page)).toBe(notifBefore)
})
