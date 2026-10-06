/**
 * 真后端 e2e 的第 18 条：删掉一部影片，它名下那张封面必须跟着从磁盘上消失。
 *
 * 这条不是后端服务用例的重复。封面清理是 #75 补上的，当时签它的是服务层用例——它们把
 * 封面路径喂成临时目录里的一个字符串，验的是"那个函数调用到了"。从浏览器点下「删除」
 * 到磁盘上少一个文件，中间还隔着 axios 那个 `X-Requested-With`、中间件的 CSRF 与角色
 * 两道闸、`DELETE` 的 204、Vue 里那句 `router.push`，以及扫描真写进库里的那列
 * `thumbnail_path` 到底指向哪儿。这一整串原先没有一处签过字：替身夹具那 82 条里，"删除"
 * 只是把一份手写响应表里的行抹掉，磁盘从来不在场。
 *
 * 所以断言两头都要落下：库里那一行没了（`GET` 它 404、列表回到原样、界面上的卡片少一张），
 * 磁盘上它那张封面没了，而**别人的**封面一个字节都没动——最后这句靠 `coverFingerprints`
 * 把整个封面目录拍成「路径 + 内容哈希」逐项比。它才是这条用例最值钱的地方：删除走的是
 * "先把路径取出来、提交之后再删文件"，一步写错就是把别人的图一起端走。
 *
 * 这一趟是这轮里唯一会改变库里影片数的一条（它自己往媒体目录里现编第二个真片子），
 * 所以文件名排在最后（`v` 排在 `transcode` 的 `t` 之后），收场也在自己的 finally 里把
 * 文件删干净——不留给下一轮一个"多出来的片子"。
 */
import { expect, test, type Page } from '@playwright/test'
import { existsSync, rmSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { join, sep } from 'node:path'

import { MEDIA_DIR, THUMBNAIL_DIR } from './env'
import { CSRF, coverFingerprints, fetchInPage, requestJson, scanSource, signIn } from './support'

/** 这一条现场造的第二个源文件；扫描认的是 `视频源` 那条路径，所以必须落在媒体目录里。 */
const EXTRA_FILE = join(MEDIA_DIR, 'e2e_extra.mp4')

/** 两边都可能是 `\` 或 `/`，归一到 `/` 再比（第 13 条比 filepath 用的是同一个办法）。 */
function asUrlPath(path: string): string {
  return path.split(sep).join('/')
}

/** 库里现在的影片行：`[id, 标题, 封面路径]`，按 id 排。列表响应就带着这三列。 */
type VideoRow = { id: number; title: string | null; thumbnail_path: string | null }

async function readVideos(page: Page): Promise<{ rows: VideoRow[]; total: number }> {
  const list = await requestJson<{ items: VideoRow[]; total: number }>(page, '/api/videos')
  return {
    rows: [...list.items].sort((a, b) => a.id - b.id),
    total: list.total,
  }
}

/**
 * 现编一条 15 秒、64x36 的 H.264 + AAC。
 *
 * 时长和字节数都刻意和播种那部（30 秒）不一样：扫描把两个文件认成两部片子这件事，只有
 * 当它们真的不同的时候才成立。这条用例不需要音轨（扫描、封面和时长读的全是视频流），
 * 带上只是让它和播种那部保持同一种族——两份夹具只差在长多少。
 */
function writeExtraClip(): void {
  const run = spawnSync(
    'ffmpeg',
    [
      '-v', 'error', '-y',
      // 两路 lavfi 输入：一条 15 秒的黑屏，一条 1 秒的正弦音轨
      '-f', 'lavfi', '-i', 'color=c=black:s=64x36:r=1:d=15',
      '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=44100:duration=1',
      '-c:v', 'libx264', '-preset', 'veryfast', '-profile:v', 'baseline', '-pix_fmt', 'yuv420p',
      '-c:a', 'aac', '-ac', '1', '-b:a', '16k',
      EXTRA_FILE,
    ],
    { encoding: 'utf8' },
  )
  expect(run.status, run.stderr).toBe(0)
}

async function favoriteIds(page: Page): Promise<number[]> {
  const list = await requestJson<{ items: VideoRow[] }>(page, '/api/favorites')
  return list.items.map((item) => item.id).sort((a, b) => a - b)
}

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec，
// 挂错地方的实测症状是这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('删掉一部影片：库里那行没了，它名下那张真封面也从磁盘上消失，别人的封面不动', async ({ page }) => {
  // 起点是前面那些用例留下的现场（收藏、片单、标签都可能挂着行），所以这里一律
  // "先读一遍再比差值"，不写死任何一个数。
  const before = await readVideos(page)
  const coversBefore = coverFingerprints()
  // 这一句不是装饰：封面目录要是空着，后面那句「回到删除前那份清单」就是在比两个空数组。
  expect(coversBefore.length).toBeGreaterThan(0)

  try {
    writeExtraClip()

    // ---- 1. 扫描把磁盘上这个新文件变成库里的一行，顺带抽出一张真封面
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 1,
      subtitles_found: 0,
    })
    const after = await readVideos(page)
    expect([after.total, after.rows.length]).toEqual([before.total + 1, before.rows.length + 1])
    const extra = after.rows.find((row) => !before.rows.some((old) => old.id === row.id))
    expect(extra?.title).toBe('e2e extra')
    const extraId = extra?.id ?? 0
    expect(extraId).toBeGreaterThan(0)

    // 库里那一列指的是一个真存在的文件，而且就在封面根目录下面：`thumbnail_path` 曾经
    // 写成相对路径，进程换个 cwd 起它就指到别处（#63），只核对"文件在"挡不住这件事。
    const extraCover = extra?.thumbnail_path ?? ''
    expect(asUrlPath(extraCover).startsWith(`${asUrlPath(THUMBNAIL_DIR)}/`)).toBe(true)
    expect(existsSync(extraCover), extraCover).toBe(true)
    const coverName = asUrlPath(extraCover).slice(asUrlPath(THUMBNAIL_DIR).length + 1)
    expect(coverFingerprints().map((line) => line.split(' ')[0])).toContain(coverName)

    // ---- 2. 给它留一行收藏：级联清单少一张表，界面上看不出来，删除时才看得出来
    // 非 GET 必须带 CSRF 头，这一趟故意先不带它——403 才是真中间件的答案，顺手把这道闸
    // 也签一次（前端 axios 全局带那个头，所以正常点击走的是放行那条路）。
    const blocked = await fetchInPage(page, `/api/favorites/${extraId}`, {
      method: 'POST',
      headers: {},
    })
    expect(blocked.status).toBe(403)
    await requestJson(page, `/api/favorites/${extraId}`, { method: 'POST', expectStatus: 201 })
    const favorites = await favoriteIds(page)
    expect(favorites).toContain(extraId)

    // ---- 3. 从界面上删：按钮、确认框、提示、跳回首页，一路都是真请求
    await page.goto(`/videos/${extraId}`)
    await page
      .locator('.action-buttons')
      .getByRole('button', { name: '删除', exact: true })
      .click()
    await page.locator('.el-message-box__btns button', { hasText: '删除' }).click()
    await expect(page.locator('.el-message--success')).toContainText('视频已删除')
    await expect(page).toHaveURL(/\/$/)

    // ---- 4. 库里那一行和它的收藏都没了
    const gone = await fetchInPage(page, `/api/videos/${extraId}`)
    expect([gone.status, gone.text]).toEqual([404, expect.stringContaining('Video not found')])
    // 删除那条路自己也要能重走一遍：`delete_video` 抛的是 ValueError，它和"读不到"两句
    // 原话不一样，各自 mapped 到 404。第二脚若漏了 except，浏览器看到的是一片 500。
    const again = await fetchInPage(page, `/api/videos/${extraId}`, {
      method: 'DELETE',
      headers: CSRF,
    })
    expect([again.status, again.text]).toEqual([
      404,
      expect.stringContaining(`Video with id ${extraId} not found`),
    ])
    // 封面接口读的是同一行，行没了它也只能说没有这部片子（不是"没有封面"）
    const thumb = await fetchInPage(page, `/api/videos/${extraId}/thumbnail`)
    expect([thumb.status, thumb.text]).toEqual([404, expect.stringContaining('Video not found')])
    const afterDelete = await readVideos(page)
    expect(afterDelete.rows.map((row) => row.id)).toEqual(before.rows.map((row) => row.id))
    expect(afterDelete.total).toBe(before.total)
    expect(await favoriteIds(page)).toEqual(favorites.filter((id) => id !== extraId))

    // ---- 5. 磁盘：它那张封面没了，整个目录回到删除前那份清单（名字和内容哈希逐项相等）
    expect(existsSync(extraCover), extraCover).toBe(false)
    expect(coverFingerprints()).toEqual(coversBefore)
    // 用户的媒体文件**不该**被删：行是应用建的，片子是用户放的，只有前者归应用管
    expect(existsSync(EXTRA_FILE)).toBe(true)

    // ---- 6. 界面上那张卡片跟着少一张，首页的计数也是
    await page.goto('/')
    await expect(page.locator('.video-card')).toHaveCount(afterDelete.rows.length)
  } finally {
    // 这一条自己造的文件自己收走：留在媒体目录里，下一轮扫描就会把它当成一部新片子，
    // "共 1 个视频"那一整族断言全要跟着改。封面已经在用例里核过没了。
    rmSync(EXTRA_FILE, { force: true })
  }
})
