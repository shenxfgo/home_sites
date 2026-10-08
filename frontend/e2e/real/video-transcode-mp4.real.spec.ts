/**
 * 真后端 e2e 的第 25 条：转码表里 **mp4** 那一行，第一次有真产物。
 *
 * 前二十四条把 webm、avi、mkv 三行配方都查过了，唯独 mp4 那一行没查——不是漏了，是在播种那部
 * 片子上**测不出来**：闸门比的是源文件的扩展名和目标格式（`transcode_service.py` 里那句
 * `Path(input_path).suffix`），源是 .mp4、目标也是 mp4 时它回
 * `Target format matches the source format`（第 15 条第 3 步签的就是这一句），ffmpeg 因此
 * 从没为那一行启动过。`SUPPORTED_FORMATS['mp4']` 那两个编码器字面值——`-c:v libx264` 和
 * `-c:a aac`——不进任何 API 响应（`get_supported_formats` 只回 `codec` 和 `extension`，
 * `acodec` 从来不回），所以改错 `acodec` 在此前那二十四条真用例和 754 条后端用例里都是一格
 * 都不红。
 *
 * 办法是把源换掉而不是把目标换掉：现场 `-c copy` 出一个 .mkv，扫进来得到库里的第二行，
 * 从那一行转 mp4，闸门就放行（它比的是源的扩展名，.mkv 对 mp4 不撞）。这一步顺带还补上了
 * 另一格——mp4 这个选项在前二十四条里只以"被拒绝"的样子出现过，界面上从没真点成功过一次。
 *
 * 断言只收真进程给得出的东西：产物文件头自报 `ftyp`（不看文件名）、ffprobe 报出的两条流
 * 就是那一行写的编码器、通知里 `data.video_id` 认的是这一行的 id 而不是播种那部的 1，
 * 以及 #154 之后那张产物表里的这一行——`size_bytes` 得等于磁盘上那份文件的字节数，
 * 因为它是这一次请求当场 stat 出来的，不是表里的抄本。
 * `progress` 钉 100 钉的是"跑完了服务端就写 100"（`_run` 成功那一句），不是编码器最后
 * 报到第几秒——avi 那一路已经量过那两者不是一回事（见第 15 条第 5 步的注释）。
 *
 * **为什么单开一支文件**：这套用例的编号就是执行顺序（Playwright 按文件名字母序收集，第 24 条
 * 之后没有东西），而这一条要落在最后。住在 `transcode.real.spec.ts` 里它会排在第 17 条后面、
 * 物理上是第 18 条，那要么把后面七条的编号全推动一遍（那些数字在 CHANGELOG 的历史条目里也
 * 出现，历史不能改写），要么让"第 25 条"和报告里的第 25 行不是同一条用例——两条都是往
 * "编号=位置"这根钉子上打洞。所以文件名排在 `video-tags` 之后（`tags` < `transcode`），
 * 而它要的那张配方表和那几句产物断言从 `transcode.real.spec.ts` 抽进 `transcode_support.ts`
 * 共用：`STREAMS` 抄一份就变成两张表各自红，正是 #143 记下的那个病根。
 */
import { expect, test } from '@playwright/test'
import { existsSync, readFileSync, rmSync, statSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'

import { MEDIA_DIR } from './env'
import { coverFingerprints, fetchInPage, requestJson, scanSource, signIn } from './support'
import {
  FIXTURE,
  STREAMS,
  asUrlPath,
  chooseFormat,
  confirmMessageBox,
  expectRealOutput,
  productPath,
  readNotifications,
  readProducts,
  sha1,
  streamPairs,
  waitSettled,
  type VideoListItem,
} from './transcode_support'

/**
 * 这一条的源：播种那部按流复制出来的一个 .mkv。
 *
 * 存在的唯一理由是**后缀**——闸门比的是源文件的扩展名和目标格式，源是 .mp4 时 mp4 当目标
 * 会被当成"产物和源同名"拒掉，那一行配方因此从没有点成功过。换个容器当源，mp4 那一行
 * 才第一次有点得动。
 */
const MKV_SOURCE = join(MEDIA_DIR, 'e2e_mkvsrc.mkv')

/**
 * 现场把播种那部 `-c copy` 成一个 .mkv：不重编码、半秒，两条流原样带过来。
 *
 * 音轨必须真的带过来，否则这一条只剩半张配方能查——源里没有音频流时 ffmpeg 把 `-c:a`
 * 整个跳过（第 15 条开头记着的那个实测：无声夹具上把 webm 的 acodec 改成容器拒收的编码器，
 * 整跑是绿的）。所以造完先问一次 ffprobe，这一步是夹具自己的钉子。
 */
function writeMkvSource(): void {
  const run = spawnSync(
    'ffmpeg',
    ['-hide_banner', '-loglevel', 'error', '-y', '-i', FIXTURE, '-c', 'copy', MKV_SOURCE],
    { encoding: 'utf8' },
  )
  expect(run.status, run.stderr).toBe(0)
  expect(streamPairs(MKV_SOURCE), 'remux 出来的 .mkv 没有两条流，mp4 那行就只剩视频那半能查').toEqual(
    STREAMS.mp4,
  )
}

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec，
// 挂错地方的实测症状是这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('转码表里 mp4 那一行：换一个不是 mp4 的源，那半张配方才第一次真跑起来', async ({ page }) => {
  const before = await requestJson<{ items: VideoListItem[] }>(page, '/api/videos')
  const beforeIds = before.items.map((item) => item.id).sort((a, b) => a - b)
  const coversBefore = coverFingerprints()
  // 这一条只往旁边多放文件，播种那部的字节一个都不该动
  const fixtureDigest = sha1(readFileSync(FIXTURE))
  // 产物的去处要写进 `finally`，所以这一行的 id 得在 try 外面就存在（0 时那个路径不在
  // 磁盘上，`rmSync(force)` 于是在那里是个空操作）
  let mkvId = 0

  try {
    // ---- 1. 磁盘上多出一个 .mkv，扫进来得到库里的第二行
    writeMkvSource()
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 1,
      subtitles_found: 0,
    })
    const listed = await requestJson<{ items: VideoListItem[] }>(page, '/api/videos')
    const added = listed.items.find((item) => !beforeIds.includes(item.id))
    mkvId = added?.id ?? 0
    expect(mkvId).toBeGreaterThan(0)
    // 名字是从文件名推的，扩展名换成 .mkv 也一样——这一行是扫出来的，不是播种的
    expect(added?.title).toBe('e2e mkvsrc')

    // 通知的基线取在扫描之后（第 16 条同样的理由：那一趟扫描自己也发一条）
    const beforeNotifications = await readNotifications(page)

    // ---- 2. 界面上 mp4 这一项第一次点得动：闸门放行了，任务真起来
    await page.goto(`/videos/${mkvId}/transcode`)
    await chooseFormat(page, 'mp4 (.mp4)')
    await page.getByRole('button', { name: '开始转码' }).click()
    await confirmMessageBox(page)
    await expect(page.locator('.el-message--success')).toContainText('转码任务已启动')

    // 同样没有任何刷新：状态走到「已完成」只能来自那 1.5 秒一次的轮询
    await expect(page.locator('.status-section')).toContainText('已完成', { timeout: 60_000 })
    const done = await waitSettled(page, mkvId)
    expect([
      done.status,
      done.is_transcoding,
      done.progress,
      done.error,
      done.target_format,
    ]).toEqual(['completed', false, 100, null, 'mp4'])

    // ---- 3. 产物是磁盘上真存在的 mp4，里面那两条流就是表里那一行写的编码器
    const product = done.output_path ?? ''
    // 那个路径里的目录格用的是**这一行的 id**（第 2 行，不是播种那部的 1）：布局是按影片
    // 分格的，两个源同名的片子因此不会互相覆盖，而这一句正是那句保证在真库上的样子
    expectRealOutput(product, 'mp4', mkvId, 'e2e_mkvsrc')

    // ---- 3b. 产物表里那一行的字节数是当场 stat 出来的，不是表里的抄本
    const products = await readProducts(page, mkvId)
    expect(products.map((row) => [row.target_format, asUrlPath(row.output_path)])).toEqual([
      ['mp4', asUrlPath(product)],
    ])
    expect(products[0]?.size_bytes).toBe(statSync(product).size)
    expect(products[0]?.deleted_at).toBeNull()
    await expect(page.locator('.products-section .el-table__body tr')).toHaveCount(1)

    // ---- 4. 后台任务写进真库的那一条，认的是这一行
    const announced = await readNotifications(page)
    expect(announced.total).toBe(beforeNotifications.total + 1)
    expect(announced.items[0]).toMatchObject({
      type: 'transcode_complete',
      title: '转码完成',
      data: { video_id: mkvId, format: 'mp4' },
    })

    // ---- 5. 源文件没被碰过：转码只往旁边写
    expect(sha1(readFileSync(FIXTURE))).toBe(fixtureDigest)

    // ---- 6. 自己造的现场自己收干净：行删掉（连带它那张封面），磁盘回到只有播种那一个
    await requestJson(page, `/api/videos/${mkvId}`, { method: 'DELETE', expectStatus: 204 })
    expect((await fetchInPage(page, `/api/videos/${mkvId}`)).status).toBe(404)
    const afterDelete = await requestJson<{ items: VideoListItem[] }>(page, '/api/videos')
    expect(afterDelete.items.map((item) => item.id).sort((a, b) => a - b)).toEqual(beforeIds)
    expect(coverFingerprints()).toEqual(coversBefore)
    // 产物那一行跟着影片没了（那条 FK 是 ON DELETE CASCADE）——留一行指向已删影片的产物，
    // 输出目录里就再没人说得出它是哪一部片子留下的
    expect(await readProducts(page, mkvId)).toEqual([])
  } finally {
    // 排在后面的用例——这一条是最后一条，所以"后面"是**下一轮起跑**——都按「媒体目录里只有
    // 播种那一个文件」数数（同目录第二个源那条、删影片那条的 `files_found` 都是从这一个数出来的），
    // 所以那个 .mkv 得由这一条自己带走；它的 mp4 产物住在输出目录里，扫描器够不着，但留着
    // 同样会让下一轮读到一份旧文件。
    // 和 `writeSlowClip` 那一条同一句规矩：删除失败必须闭嘴——`finally` 里抛出的异常会顶掉
    // try 块里那个真正的断言失败，而下一轮起跑 `e2e_seed.prepare_media()` 会把整个目录 rmtree。
    for (const path of [MKV_SOURCE, productPath(mkvId, 'e2e_mkvsrc', 'mp4')]) {
      try {
        rmSync(path, { force: true, maxRetries: 10, retryDelay: 500 })
      } catch {
        // 由下一轮起跑那次 rmtree 兜底
      }
    }
  }

  // 收尾之后才核对（#120 的规矩）：这两个文件真从磁盘上没了，用 `existsSync` 而不是字节数——
  // 产物刚被编码器写完，Windows 上半秒内可能还读不动。
  expect(existsSync(MKV_SOURCE), MKV_SOURCE).toBe(false)
  expect(existsSync(productPath(mkvId, 'e2e_mkvsrc', 'mp4'))).toBe(false)
})
