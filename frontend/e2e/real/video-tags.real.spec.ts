/**
 * 真后端 e2e 的第 24 条：在影片详情页手工挂一枚标签，再让扫描跑过那一行，看那枚标签还在不在。
 *
 * 这条用例的动机是 `scan_service._backfill_coordinates` 那句 docstring：「a title **or tag set**
 * someone curated by hand is left alone」。#127 只在真库上签了前半句（标题），后半句从来没被
 * *执行过*：那道闸门是 `if video.series is not None: return`，而播种那部 `e2e_sample.mp4` 解析
 * 不出 series，函数在第 166 行就返回了——前面那 23 条用例一次也没走到第 171 行那条 append。
 *
 * 服务层确实有一条对着它的（`test_rescan_backfills_coordinates_into_old_rows`），但那一行的
 * 手工标签是**同一个 session 用 ORM 直接插进去的**，而真实世界是两趟：浏览器发
 * `POST /api/tags/video/{id}` 提交一个事务，随后 `POST /api/sources/1/scan` 在**另一个请求、
 * 另一个 session** 里把同一条影片行重新捞出来。`Video.tags` 是 `lazy="selectin"`，捞出来那份
 * 列表里有没有别的 session 刚提交的那一枚，只有真 HTTP + 真 PG 会说谎说得出口。这里就是那一头。
 *
 * 反面那一半（「扫描真的走到了 append，而不是提前 return 所以标签当然还在」）靠的是坐标：
 * 扫描前把三个坐标列清空、扫描后必须被填回来。少了这一句，整条用例可以在"函数压根没走到
 * 第 171 行"这个错误世界里照样全绿——和 #127 那句"改名之前的旧片名也要钉"是同一个办法。
 *
 * 顺序：文件名排在 `video-edit` 之后，是这一套的最后一条。它不改播种那部的任何一列，自己造的
 * 那一行和那两枚标签在 `finally` 里收干净，并在 `finally` **之后**用一次真读回核对（#120 那条
 * 规矩：收尾的 body 里不写断言，否则真正的失败会被自己的还原断言盖住）。
 */
import { expect, test, type Page } from '@playwright/test'
import { copyFileSync, existsSync, rmSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'

import { BACKEND_DIR, MEDIA_DIR, backendEnv, pythonPath } from './env'
import { CSRF, fetchInPage, requestJson, scanSource, signIn } from './support'

interface TagBody {
  id: number
  name: string
  color: string
}

interface VideoRow {
  id: number
  title: string | null
  series: string | null
  season: number | null
  episode: number | null
  tags: TagBody[]
}

/** 磁盘上是播种那部的字节，名字必须解析得出 series——否则 backfill 在第 166 行就返回了。 */
const LEGACY_FILE = join(MEDIA_DIR, 'morning.squad.s02e03.mp4')
const PARSED_TITLE = 'morning squad S02E03'
const AUTO_TAG = 'morning squad'
const HAND_TAG = '周末重看'

const tagNames = (tags: TagBody[]): string[] => tags.map((tag) => tag.name).sort()

/** 详情页标签条上此刻挂着的名字。 */
async function attachedNames(page: Page): Promise<string[]> {
  return (await page.locator('.tags-list .el-tag').allTextContents())
    .map((text) => text.trim())
    .sort()
}

/**
 * 标签条要「等界面把那部片子读回来」再比。
 *
 * 直接 `await expect(await attachedNames(page)).toEqual(...)` 在这里测不到任何东西：`goto` 只
 * 等文档加载完，Vue 那一路的 `getVideo` 还在飞，第一次读回来的就是空数组——实测症状是断言
 * 立刻红，而快照里那一页还停在被 `VideoDetail.vue:113` 弹回首页之后的样子。
 */
async function expectAttached(page: Page, names: string[]): Promise<void> {
  const sorted = [...names].sort()
  await expect.poll(() => attachedNames(page)).toEqual(sorted)
}

async function readVideo(page: Page, id: number): Promise<VideoRow> {
  return requestJson<VideoRow>(page, `/api/videos/${id}`)
}

async function videoIds(page: Page): Promise<number[]> {
  const list = await requestJson<{ items: VideoRow[] }>(page, '/api/videos?page=1&page_size=50')
  return list.items.map((item) => item.id).sort((a, b) => a - b)
}

/**
 * 把刚建出来的那一行拍成"解析器出现之前写进去的样子"：三个坐标列清空。
 *
 * 为什么只能走 SQL：库里没有任何接口能把 `series` 写回 null（`VideoUpdate` 只有
 * title / description / rating / tag_ids，手工建档的接口压根不存在），而这种形状正是
 * `db_transfer.py` 搬过来的那批行的形状。被验的是**扫描**怎么处理标签，不是这一列怎么变空的。
 * 连接的口令只进子进程的环境变量（`backendEnv` 里就是那串 TEST_DATABASE_URL），不进 argv。
 *
 * 那句 `rowcount` 是这条安排自己的钉子：清空的要是别行，后面全部断言就在替空谈话。
 */
function clearCoordinates(videoId: number): void {
  const script = [
    'import asyncio, os',
    'from sqlalchemy import text',
    'from sqlalchemy.ext.asyncio import create_async_engine',
    '',
    'async def main():',
    '    engine = create_async_engine(os.environ["DATABASE_URL"])',
    '    async with engine.begin() as conn:',
    '        result = await conn.execute(',
    '            text("UPDATE videos SET series=NULL, season=NULL, episode=NULL WHERE id=:id"),',
    '            {"id": int(os.environ["LEGACY_VIDEO_ID"])},',
    '        )',
    '    await engine.dispose()',
    '    print(result.rowcount)',
    '',
    'asyncio.run(main())',
  ].join('\n')
  const run = spawnSync(pythonPath(), ['-'], {
    input: script,
    encoding: 'utf8',
    cwd: BACKEND_DIR,
    env: backendEnv({ LEGACY_VIDEO_ID: String(videoId) }),
  })
  expect(run.status, run.stderr).toBe(0)
  expect(run.stdout.trim()).toBe('1')
}

/** 收尾用的删除：不核对状态码，也不抛——#120 的规矩是 body 里不写断言。 */
async function tryDelete(page: Page, path: string): Promise<void> {
  await fetchInPage(page, path, { method: 'DELETE', headers: CSRF })
}

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec，
// 挂错地方的实测症状是这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('手工挂的标签扛得过一次真扫描：补坐标那一趟只往里加，不重列', async ({ page }) => {
  const idsBefore = await videoIds(page)
  const tagsBefore = (await requestJson<TagBody[]>(page, '/api/tags')).map((tag) => tag.name).sort()
  expect(tagsBefore).not.toContain(AUTO_TAG)
  expect(tagsBefore).not.toContain(HAND_TAG)

  copyFileSync(join(MEDIA_DIR, 'e2e_sample.mp4'), LEGACY_FILE)
  let videoId = 0
  let autoTagId = 0
  let handTagId = 0

  try {
    // ---- 1. 一次真扫描把磁盘上这个新文件变成一行，顺带建出那枚自动标签
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 1,
      subtitles_found: 0,
    })
    const listed = await requestJson<{ items: VideoRow[] }>(page, '/api/videos?page=1&page_size=50')
    const created = listed.items.find((item) => item.title === PARSED_TITLE)
    expect(created, `扫描没有把 ${PARSED_TITLE} 变成一行`).toBeDefined()
    videoId = created!.id
    expect([created!.series, created!.season, created!.episode]).toEqual([AUTO_TAG, 2, 3])
    expect(tagNames(created!.tags)).toEqual([AUTO_TAG])

    const tagRows = await requestJson<TagBody[]>(page, '/api/tags')
    autoTagId = tagRows.find((tag) => tag.name === AUTO_TAG)?.id ?? 0
    expect(autoTagId, '扫描建出的那枚自动标签没有落库').toBeGreaterThan(0)

    // ---- 2. 界面上手工挂第二枚：这是 #132 只在替身里走过的那条写流程，真库这一头还没签过
    handTagId = (
      await requestJson<TagBody>(page, '/api/tags', {
        method: 'POST',
        body: { name: HAND_TAG },
        expectStatus: 201,
      })
    ).id

    await page.goto(`/videos/${videoId}`)
    await expectAttached(page, [AUTO_TAG])
    await page.locator('.tags-list button').click()
    await expect(page.locator('.el-dialog')).toContainText('编辑标签')
    // 预勾上必须是这部片子此刻挂着的，不是整个标签表——否则「保存」是一次盲写
    const autoBox = page.locator('.el-dialog .el-checkbox').filter({ hasText: AUTO_TAG })
    const handBox = page.locator('.el-dialog .el-checkbox').filter({ hasText: HAND_TAG })
    await expect(autoBox).toHaveClass(/is-checked/)
    await expect(handBox).not.toHaveClass(/is-checked/)
    await handBox.click()
    await page.locator('.el-dialog').getByRole('button', { name: '保存' }).click()

    await expect(page.locator('.el-message--success')).toContainText('标签已更新')
    await expectAttached(page, [AUTO_TAG, HAND_TAG])
    // 同一个关系换个入口读回来必须也是这两枚：详情页读 `video.tags`，标签页读那条计数
    await page.goto('/tags')
    await expect(page.locator('.tag-card').filter({ hasText: HAND_TAG })).toContainText('1 个视频')

    // ---- 3. 安排成"解析器之前写进去的行"：坐标清空，标签一枚不动
    clearCoordinates(videoId)
    const arranged = await readVideo(page, videoId)
    expect([arranged.series, arranged.season, arranged.episode]).toEqual([null, null, null])
    expect(tagNames(arranged.tags)).toEqual([AUTO_TAG, HAND_TAG].sort())

    // ---- 4. 真扫描那一趟：补回坐标，同时把两枚标签都留着
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 0,
      subtitles_found: 0,
    })
    const scanned = await readVideo(page, videoId)
    // 这一句是整条用例的支点：坐标回来了，才证明 backfill 走到了第 171 行那条 append，
    // 而不是在第 162 行就 return——后者会让"标签还在"变成一句空话。
    expect([scanned.series, scanned.season, scanned.episode]).toEqual([AUTO_TAG, 2, 3])
    expect(tagNames(scanned.tags)).toEqual([AUTO_TAG, HAND_TAG].sort())
    // 关联行不翻倍。**但这一句不是那句 `if tag not in video.tags` 的签名**：实测把那个 `if`
    // 整段去掉（`video.tags = [*video.tags, *auto]`），本用例照样全绿——secondary 关系上
    // SQLAlchemy 默认的 `AppendsUniqueBehavior` 本来就会吃掉同一个实例的重复 append。这一句
    // 钉的是"这一趟扫描没把关联表写成两条"，那是所有写路径共同的账，不是那句护栏的账。
    expect(scanned.tags.length).toBe(2)
    // 反向那一头：自动标签自己也得说这部片子是它的（关联行是真行，不是详情页顺带查出来的）
    const underAutoTag = await requestJson<VideoRow[]>(page, `/api/tags/${autoTagId}/videos`)
    expect(underAutoTag.map((item) => item.id)).toEqual([videoId])
    const underHandTag = await requestJson<VideoRow[]>(page, `/api/tags/${handTagId}/videos`)
    expect(underHandTag.map((item) => item.id)).toEqual([videoId])

    await page.goto(`/videos/${videoId}`)
    await expectAttached(page, [AUTO_TAG, HAND_TAG])

    // ---- 5. 第三趟扫描：坐标已经填好了，那一行该在闸门处直接返回，什么都不动
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 0,
      subtitles_found: 0,
    })
    expect(tagNames((await readVideo(page, videoId)).tags)).toEqual([AUTO_TAG, HAND_TAG].sort())
    // 标签表不涨：#85 那一族（每轮定时扫描重复投递）搬到关联行上的同一件事
    const tagRowsAfter = await requestJson<TagBody[]>(page, '/api/tags')
    expect(tagRowsAfter.map((tag) => tag.name).sort()).toEqual([...tagsBefore, AUTO_TAG, HAND_TAG].sort())

    await page.goto('/tags')
    await expect(page.locator('.tag-card').filter({ hasText: HAND_TAG })).toContainText('1 个视频')
  } finally {
    // 顺序是先删片子（关联行跟着级联走）再删两枚标签，最后把磁盘上那个文件收掉。
    if (videoId) await tryDelete(page, `/api/videos/${videoId}`)
    if (handTagId) await tryDelete(page, `/api/tags/${handTagId}`)
    if (autoTagId) await tryDelete(page, `/api/tags/${autoTagId}`)
    if (existsSync(LEGACY_FILE)) rmSync(LEGACY_FILE, { force: true })
  }

  // 收尾之后才核对：这一趟有没有在库里留下痕迹，用的是真读回，不是 `finally` 里的一句自夸。
  expect(await videoIds(page)).toEqual(idsBefore)
  expect((await requestJson<TagBody[]>(page, '/api/tags')).map((tag) => tag.name).sort()).toEqual(
    tagsBefore,
  )
  expect(existsSync(LEGACY_FILE)).toBe(false)
})
