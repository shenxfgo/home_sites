/**
 * 真后端 e2e 的第 20 条：从详情页改一部影片的名字、简介和评分，写进真库，再真扫描一轮，
 * 看扫描器会不会把手改的那一份覆盖掉。
 *
 * 这条用例签的是三段以前只有替身答过的字。`PUT /api/videos/{id}` 是库面上最后一个还没有
 * 真库签名的写接口：替身夹具里「编辑」改的是一份手写响应表里的行，磁盘和 PostgreSQL 都不
 * 在场，所以 `updated_at` 那一列的 `onupdate` 到底有没有真的触发、详情和列表这两条**不同的
 * 查询**会不会各读各的答案、以及这条路由的四种答复（400 / 404 / 422 / 200）分别是谁说的，
 * 全都没有人对过账。
 *
 * 第二段是 `scan_service._backfill_coordinates` 的 docstring：「a title or tag set someone
 * curated by hand is left alone」。那句话的主语是扫描器，而它以前只被服务层用例读过；界面
 * 上点一次重新扫描之后那个名字还在不在，浏览器这一头没人看过。这里就是那一头。
 *
 * 第三段是这条用例顺手撞出来的缺陷，也是它最值钱的一行：`VideoUpdate.rating` 标的是
 * `int | None`，而 `videos.rating` 那一列是 NOT NULL。显式 null 在闸口放行，到
 * `UPDATE videos SET rating=NULL` 才由数据库拒绝，而路由那句 `except ValueError` 接不住
 * SQLAlchemy 的 `IntegrityError`——真服务器上这是一次 500。和 #112 是同一条规矩：**写得
 * 进去的必须读得出来**。修在请求模型那侧，这一头留下 422 的签名，以及反面那一半（标题
 * 那一列可以为空，所以不能靠"整个 body 不许有 null"蒙绿）。
 *
 * 顺序：文件名排在 `video-delete` 之后（`d` 在 `e` 前）。它会改名，所以末尾把播种那一份原样
 * 写回去——不是给后面的用例让路（第 21 条 `video-tags` 不读片名，也不按名字找那一行），是让
 * `-g 编辑影片` 单跑和整跑读到同一个现场。
 */
import { expect, test, type Page } from '@playwright/test'

import { E2E_MEMBER_USERNAME } from './env'
import { requestJson, scanSource, signIn } from './support'

/** 详情、列表、继续观看三处都带着的那几列——只取这条用例真正在用的字段。 */
interface VideoRow {
  id: number
  title: string | null
  description: string | null
  rating: number
  duration: number | null
  thumbnail_path: string | null
  updated_at: string
  progress?: number | null
}

const NEW_TITLE = '手改的片名'
const NEW_DESCRIPTION = '这条简介是在浏览器里手打的'

function readVideo(page: Page, id: number): Promise<VideoRow> {
  return requestJson<VideoRow>(page, `/api/videos/${id}`)
}

/** 首页搜索框那一路：先等地址栏（卡片数在"结果没变"的探针上根本不动），再两头对账。 */
async function expectSearch(page: Page, text: string, expectedIds: number[]): Promise<void> {
  await page.locator('.search-input input').fill(text)
  await expect
    .poll(() => new URL(page.url()).searchParams.get('q'))
    .toBe(text || null)
  await expect(page.locator('.video-card')).toHaveCount(expectedIds.length)
  const list = await requestJson<{ items: { id: number }[]; total: number }>(
    page,
    `/api/videos?search=${encodeURIComponent(text)}`,
  )
  expect([list.total, list.items.map((item) => item.id)]).toEqual([
    expectedIds.length,
    expectedIds,
  ])
}

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec（库名缓存），
// 挂错地方的实测症状是整跑时这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('编辑影片：写进真库、扫描不覆盖手改的名字，评分留空是 422 而不是 500', async ({
  page,
}) => {
  // ---- 0. 现场自己造：先落一条"看过但没看完"的历史行，那条轨和时间线才各有东西可读
  // 走的是真写入路径（`POST /play` + `/progress`），和播种同一套：手插一行就绕过了
  // `is_completed()` 那个按时长比例算的容差，界面上会变成"播过却不进轨"。
  await requestJson(page, '/api/videos/1/play', { method: 'POST' })
  await requestJson(page, '/api/videos/1/progress', { method: 'POST', body: { progress: 12 } })

  const base = await readVideo(page, 1)
  // 这个名字来自播种那一步的文件名解析（`e2e_sample.mp4` → `e2e sample`）。写死在这里
  // 是为了让后面那句"旧名字搜不到"不是空话：改的目标和对照必须是两个不同的串。
  expect(base.title).toBe('e2e sample')
  expect(base.rating).toBe(0)
  // 改名之前，时间线读到的也该是旧名字——第 3 步那句"变成新名字"需要一个对照面
  const timelineBefore = await requestJson<{
    items: { video_id: number; video_title: string | null }[]
  }>(page, '/api/history')
  expect(timelineBefore.items.length).toBeGreaterThan(0)
  expect([...new Set(timelineBefore.items.map((item) => item.video_title))]).toEqual([
    base.title,
  ])

  // ---- 1. 三个控件都是真点击，保存之后页面自己退回浏览态
  await page.goto('/videos/1')
  await page
    .locator('.action-buttons')
    .getByRole('button', { name: '编辑', exact: true })
    .click()
  await page.getByPlaceholder('视频标题').fill(NEW_TITLE)
  await page.getByPlaceholder('视频描述').fill(NEW_DESCRIPTION)
  await page.locator('.edit-rating .star-icon').nth(3).click()
  await page.locator('.edit-actions').getByRole('button', { name: '保存' }).click()
  await expect(page.locator('.el-message--success')).toContainText('视频信息已更新')
  await expect(page.locator('.video-title')).toHaveText(NEW_TITLE)
  await expect(page.locator('.description')).toHaveText(NEW_DESCRIPTION)
  await expect(page.locator('.rating-text')).toHaveText('4/5')

  // ---- 2. 库里那一行：详情和列表是两条不同的查询，答案必须一样
  const after = await readVideo(page, 1)
  expect([after.title, after.description, after.rating]).toEqual([
    NEW_TITLE,
    NEW_DESCRIPTION,
    4,
  ])
  // 编辑不该重抽封面——那一列指的还是同一个文件
  expect(after.thumbnail_path).toBe(base.thumbnail_path)
  // `updated_at` 由列上的 `onupdate` 写，替身夹具里这一列压根不存在，所以只有真库会
  // 替你把时间戳推新；相等就意味着那句 UPDATE 没走到。
  expect(Date.parse(after.updated_at)).toBeGreaterThan(Date.parse(base.updated_at))

  const firstPage = await requestJson<{ items: VideoRow[] }>(
    page,
    '/api/videos?page=1&page_size=20',
  )
  const listed = firstPage.items.find((item) => item.id === 1)
  expect([listed?.title, listed?.description, listed?.rating]).toEqual([
    NEW_TITLE,
    NEW_DESCRIPTION,
    4,
  ])

  // ---- 3. 名字是**读时 join** 出来的，不是历史行里存的快照：两处 API + 两处 DOM
  const rail = await requestJson<VideoRow[]>(page, '/api/history/continue')
  expect(rail.map((row) => [row.id, row.title, row.progress])).toEqual([
    [1, NEW_TITLE, 12],
  ])
  const timeline = await requestJson<{
    items: { video_id: number; video_title: string | null }[]
  }>(page, '/api/history')
  // 整表只看一个集合：所有行的名字都得是新的。按行比时间顺序挡不住"某一行还挂着旧快照"，
  // 而如果哪天有人为了性能给历史行加一列 `video_title`，红的就是这里。
  expect([...new Set(timeline.items.map((item) => item.video_title))]).toEqual([NEW_TITLE])

  await page.goto('/')
  await expect(page.locator('.resume-rail .rail-caption')).toHaveText(NEW_TITLE)
  await page.goto('/history')
  await expect(page.locator('.continue-card .continue-title')).toHaveText(NEW_TITLE)
  await expect(page.locator('.video-link span').first()).toHaveText(NEW_TITLE)

  // ---- 4. 搜索读的就是那一列：新名字搜得到，旧名字一条都不剩
  await page.goto('/')
  await expectSearch(page, NEW_TITLE, [1])
  await expectSearch(page, 'e2e sample', [])
  // 名字没了，横幅上那句计数也跟着是 0，而不是同屏"共 1 个视频 + 空列表"（#113 那一族）
  await expect(page.locator('.hero-sub')).toContainText('共 0 个视频')

  // ---- 5. 真扫描一轮：手改的那份一个字都不许动
  // 磁盘上还是那一个文件，所以 `files_found` 是 1、`new_videos` 是 0——那一行走的是
  // `existing` 分支，也就是 `_backfill_coordinates` 那句 docstring 负责的地方。
  expect(await scanSource(page, 1)).toEqual({
    files_found: 1,
    new_videos: 0,
    subtitles_found: 0,
  })
  const afterScan = await readVideo(page, 1)
  expect([afterScan.title, afterScan.description, afterScan.rating]).toEqual([
    NEW_TITLE,
    NEW_DESCRIPTION,
    4,
  ])
  expect(afterScan.thumbnail_path).toBe(base.thumbnail_path)

  // ---- 6. 这条路由另外三种答复，两句 422 说的是各自的边界
  for (const [label, body, type] of [
    ['评分越界', { rating: 6 }, 'less_than_equal'],
    ['标题空串', { title: '' }, 'string_too_short'],
    // 修之前这一发是 500：NOT NULL 由数据库在 UPDATE 时才报，路由接不住 IntegrityError
    ['评分留空', { rating: null }, 'value_error'],
  ] as const) {
    const rejected = await requestJson<{ detail: { type: string; loc: string[] }[] }>(
      page,
      '/api/videos/1',
      { method: 'PUT', body, expectStatus: 422 },
    )
    expect(rejected.detail[0]?.type, label).toBe(type)
  }
  // 被拒的那一次没把那一行写坏：拒绝在闸口，不是写完再回滚
  expect((await readVideo(page, 1)).rating).toBe(4)

  // 空 body 是 400、不存在的行是 404，两句原话不一样，各自都有人 mapped
  expect(
    (await requestJson<{ detail: string }>(page, '/api/videos/1', {
      method: 'PUT',
      body: {},
      expectStatus: 400,
    })).detail,
  ).toBe('No fields to update')
  expect(
    (await requestJson<{ detail: string }>(page, '/api/videos/99999', {
      method: 'PUT',
      body: { title: '没人认领' },
      expectStatus: 404,
    })).detail,
  ).toBe('Video with id 99999 not found')

  // ---- 7. 成员这一头：界面上没有那个入口，接口也不放行，两层说的是同一件事
  await signIn(page, E2E_MEMBER_USERNAME)
  await page.goto('/videos/1')
  await expect(
    page.locator('.action-buttons').getByRole('button', { name: '编辑', exact: true }),
  ).toHaveCount(0)
  const forbidden = await requestJson<{ detail: string }>(page, '/api/videos/1', {
    method: 'PUT',
    body: { title: '成员改的名' },
    expectStatus: 403,
  })
  expect(forbidden.detail).toBe('需要管理员权限')
  // 那一行还是 owner 刚才写的样子（403 出在中间件，服务层压根没被叫到）
  expect((await readVideo(page, 1)).title).toBe(NEW_TITLE)

  // ---- 8. 回到 owner：标题那一列**可以**为空，于是界面上的兜底是文件名而不是空白
  await signIn(page)
  const cleared = await requestJson<VideoRow>(page, '/api/videos/1', {
    method: 'PUT',
    body: { title: null },
  })
  expect(cleared.title).toBe(null)
  await page.goto('/videos/1')
  await expect(page.locator('.video-title')).toHaveText('e2e_sample.mp4')

  // ---- 9. 收尾：把播种那一份原样写回去（简介和评分也一起，负值不留在库里给下一位）
  await requestJson(page, '/api/videos/1', {
    method: 'PUT',
    body: { title: base.title, description: base.description, rating: base.rating },
  })
  const restored = await readVideo(page, 1)
  expect([restored.title, restored.description, restored.rating]).toEqual([
    base.title,
    base.description,
    base.rating,
  ])
})
