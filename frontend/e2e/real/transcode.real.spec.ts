/**
 * 真后端 e2e 的第 15 条：转码那条长流程。
 *
 * 这条流程原先是**两层假**夹着的：前端 82 条桩用例把 `/api/transcode*` 四个端点全部
 * 手写在自己的处理器里（那份处理器**不做任何校验**、也永远不会失败，`output_path` 写死成
 * `/tmp/out.<格式>`），而后端那 11 条服务用例里凡是跑到编码那一步的都把 `transcode_video`
 * 整个换掉、剩下 6 条只测拒绝——于是
 * "真的调一次 FFmpeg、真的往磁盘上写一个文件"这一段，整套测试里没有一处跑过。格式大小写
 * 那个 bug 正是从这条缝里掉下去的：闸门 `check_format_support` 大小写不敏感、编码器查表
 * 敏感，而两层测试各自都摸不到对方那一层。
 *
 * 所以这条用例断言的是只有真进程给得出的东西：服务器报回来的那个**绝对输出路径**在磁盘上
 * 确实在、里面确实是所请求的那种容器（读文件头那几个字节，不看文件名）、里面真有着那半张
 * 配方编出来的两条流（问 ffprobe：webm 是 vp9 + opus、avi 与 mkv 是 h264 + aac；`acodec` 不进任何
 * 响应，而源里没有音频流时 ffmpeg 会把 `-c:a` 整个跳过——所以这一句要成立，播种那部片子
 * 就得带一条音轨，见 `backend/src/e2e_seed.py`）、后台任务写进真库的那条通知带着自己的格式
 * 与影片 id，以及三种拒绝（同格式、不认识、已经结束的任务）各有原话可说。
 */
import { expect, test, type Page } from '@playwright/test'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { join, sep } from 'node:path'

import { MEDIA_DIR } from './env'
import { CSRF, fetchInPage, requestJson, signIn } from './support'

/** 播种那部片子的文件；转码产物按 `with_suffix` 就落在它旁边。 */
const FIXTURE = join(MEDIA_DIR, 'e2e_sample.mp4')

/**
 * 每种容器的"自报家门"写在文件头几十个字节里（matroska / webm 是 EBML 的 DocType，
 * avi 是 RIFF 的 FormType）。读它而不是只看文件名的扩展名：文件名是应用拼出来的，
 * 里面那几个字节才是 FFmpeg 真写下去的东西。
 */
const CONTAINER: Record<string, string> = {
  mkv: 'matroska',
  webm: 'webm',
  avi: 'AVI LIST',
}

/**
 * 产物里应该有的那两条流。`-c:v` / `-c:a` 这半张配方不进任何 API 响应
 * （`get_supported_formats` 只回 `codec` 和 `extension`），所以它原先在整套测试里
 * 一处都证不到：把 webm 的 acodec 从 `libopus` 改成容器直接拒收的 `aac`，无声夹具那趟
 * 整跑下来是绿的（没有音频流可选时 ffmpeg 把 `-c:a` 整个跳过，实测 rc=0、产物只有一条
 * vp9）。这里写的是 ffprobe 那一侧的编码器名，不是配方字面值：libvpx-vp9 → vp9、
 * libx264 → h264、libopus → opus、aac → aac。
 *
 * 四行配方现在有三行能查：webm、avi 和 mkv 都由本用例产出（源文件是 .mp4，同格式那道闸门
 * 只挡得住 mp4 那一行）。所以 `mp4` 的 acodec 至今没有真进程签字，改错它不会红。
 * mkv 与 avi 那两行的编码器字面值是一样的，但查表按格式名各查各的：改错 mkv 那一行只红 mkv 那一步，实测 codec / acodec 两个变异都红在它的流清单上。
 */
const STREAMS: Record<string, [string, string][]> = {
  webm: [
    ['audio', 'opus'],
    ['video', 'vp9'],
  ],
  mkv: [
    ['audio', 'aac'],
    ['video', 'h264'],
  ],
  avi: [
    ['audio', 'aac'],
    ['video', 'h264'],
  ],
}

interface FormatRow {
  format: string
  codec: string
  extension: string
}

interface TranscodeStatus {
  video_id: number
  is_transcoding: boolean
  status: string
  progress: number
  target_format: string | null
  output_path: string | null
  error: string | null
}

interface StartedResponse {
  video_id: number
  status: string
  target_format: string
  output_path: string
}

interface NotificationList {
  total: number
  items: {
    id: number
    type: string
    title: string
    message: string
    data: Record<string, unknown> | null
  }[]
}

/** 两边都可能是 `\` 或 `/`，归一到 `/` 再比：和第 13 条比 filepath 用的是同一个办法。 */
function asUrlPath(path: string): string {
  return path.split(sep).join('/')
}

function sha1(bytes: Buffer): string {
  return createHash('sha1').update(bytes).digest('hex')
}

async function readStatus(page: Page, videoId = 1): Promise<TranscodeStatus> {
  return requestJson<TranscodeStatus>(page, `/api/transcode/${videoId}/status`)
}

async function readNotifications(page: Page): Promise<NotificationList> {
  const response = await fetchInPage(page, '/api/notifications')
  expect(response.status).toBe(200)
  return JSON.parse(response.text) as NotificationList
}

/** 等这一个任务离开 running：终态是 completed / failed / cancelled。 */
async function waitSettled(page: Page): Promise<TranscodeStatus> {
  await expect
    .poll(async () => (await readStatus(page)).status, {
      timeout: 60_000,
      message: 'the transcode job never left the running state',
    })
    .not.toBe('running')
  return readStatus(page)
}

/** 问 ffprobe 这个文件里有哪几条流：编出来的东西只有它说了才算。 */
function probeStreams(path: string): { codec_type: string; codec_name: string }[] {
  const probe = spawnSync(
    'ffprobe',
    ['-v', 'quiet', '-print_format', 'json', '-show_streams', path],
    { encoding: 'utf8' },
  )
  expect(probe.status, `ffprobe ${path}`).toBe(0)
  const parsed = JSON.parse(probe.stdout) as { streams: { codec_type: string; codec_name: string }[] }
  return parsed.streams
}

/** 服务器报回来的输出路径，必须是磁盘上真存在、且文件头自报家门的那个文件。 */
function expectRealOutput(outputPath: string, format: string): void {
  const mediaRoot = asUrlPath(MEDIA_DIR)
  // 替身夹具给的是 `/tmp/out.<格式>`；这里要的是它落在媒体目录里、和源文件同级
  expect(asUrlPath(outputPath).startsWith(`${mediaRoot}/`)).toBe(true)
  expect(asUrlPath(outputPath)).toBe(`${mediaRoot}/e2e_sample.${format}`)
  expect(existsSync(outputPath), outputPath).toBe(true)
  const bytes = readFileSync(outputPath)
  expect(bytes.length, outputPath).toBeGreaterThan(0)
  expect(bytes.subarray(0, 64).toString('latin1'), outputPath).toContain(
    CONTAINER[format] as string,
  )
  const streams = probeStreams(outputPath)
    .map((stream) => [stream.codec_type, stream.codec_name] as [string, string])
    .sort()
  expect(streams, outputPath).toEqual(STREAMS[format])
}

async function chooseFormat(page: Page, label: string): Promise<void> {
  await page.locator('.transcode-section .el-select').click()
  await page.locator('.el-select-dropdown__item', { hasText: label }).click()
}

async function confirmMessageBox(page: Page): Promise<void> {
  await page.locator('.el-message-box__btns button', { hasText: '确定' }).click()
}

const produced: string[] = []

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec（库名缓存），
// 挂错地方的实测症状是整跑时这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test.afterEach(() => {
  // 产物留在媒体目录里，下一轮扫描就会把它当成一部新片子——那时"共 1 个视频"那些断言
  // 全都要跟着变，所以这一条用例自己造的文件自己收走（源文件一个字节都没动）。
  for (const path of produced.splice(0)) {
    rmSync(path, { force: true })
  }
})

test('转码：真 FFmpeg 写出真文件，通知由后台任务写进真库，三种拒绝各有原话', async ({ page }) => {
  const fixtureDigest = sha1(readFileSync(FIXTURE))

  // ---- 1. 格式清单来自真后端：四种、各带编码器，扩展名是 `.mkv` 这种带点的写法
  const formats = await requestJson<FormatRow[]>(page, '/api/transcode/formats')
  expect(Object.fromEntries(formats.map((row) => [row.format, [row.codec, row.extension]]))).toEqual({
    mp4: ['libx264', '.mp4'],
    webm: ['libvpx-vp9', '.webm'],
    mkv: ['libx264', '.mkv'],
    avi: ['libx264', '.avi'],
  })

  await page.goto('/videos/1/transcode')
  await expect(page.locator('.formats-section .el-table__body tr')).toHaveCount(4)
  // 下拉里那个选项写的就是 `.mkv`（带点）——替身夹具那份手抄清单里是没点的 'mkv'
  await expect(page.locator('.formats-section')).toContainText('.webm')

  // ---- 2. 走一遍界面：选 webm → 确认 → 任务真跑完 → 页面自己轮询到「已完成」
  // 挑 webm 是因为它是这四种里和 mkv/avi 不同族的那一个：视频、音频两半配方（VP9 + Opus）
  // 都和另外三个不一样。
  await chooseFormat(page, 'webm (.webm)')
  const beforeStart = await readNotifications(page)
  await page.getByRole('button', { name: '开始转码' }).click()
  await confirmMessageBox(page)
  await expect(page.locator('.el-message--success')).toContainText('转码任务已启动')

  // 这一句没有任何刷新：状态从「转码中」走到「已完成」只能来自那 1.5 秒一次的轮询
  await expect(page.locator('.status-section')).toContainText('已完成', { timeout: 60_000 })
  await expect(page.locator('.status-section')).toContainText('WEBM')

  const done = await readStatus(page)
  expect([done.status, done.is_transcoding, done.progress, done.error]).toEqual([
    'completed',
    false,
    100,
    null,
  ])
  const webmPath = done.output_path ?? ''
  expectRealOutput(webmPath, 'webm')
  produced.push(webmPath)

  // 通知那一条读的是真库：类型、标题、`data` 那列在 JSON 列上往返一遍，铃铛看到的就是
  // 同一行。至于它是响应返回**之后**由后台任务写进去的——这从"这一行存在"看不出来，
  // 也就不是这条断言钉的东西；它钉的是"任务自己报的那一句话，参数没在中间被改掉"
  const announced = await readNotifications(page)
  expect(announced.total).toBe(beforeStart.total + 1)
  expect(announced.items[0]).toMatchObject({
    type: 'transcode_complete',
    title: '转码完成',
    data: { video_id: 1, format: 'webm' },
  })
  expect(announced.items[0]?.message).toContain('webm')

  // ---- 3. 同格式必须被拦住，而且说的是原话（替身那份 POST 处理器根本不校验）
  await chooseFormat(page, 'mp4 (.mp4)')
  await page.getByRole('button', { name: '开始转码' }).click()
  await confirmMessageBox(page)
  await expect(page.locator('.el-message--error')).toContainText('overwrite the original file')

  // 被拒绝的任务不留痕迹：上一条 completed 记录还在、没有新通知、源文件一个字节没动
  expect(await readStatus(page)).toEqual(done)
  expect((await readNotifications(page)).total).toBe(announced.total)
  expect(sha1(readFileSync(FIXTURE))).toBe(fixtureDigest)

  // ---- 4. 不认识的格式：400 当场说清，同样不进任务表、不发通知
  const rejected = await fetchInPage(page, '/api/transcode/1', {
    method: 'POST',
    headers: { ...CSRF, 'content-type': 'application/json' },
    body: JSON.stringify({ target_format: 'exe' }),
  })
  expect([rejected.status, rejected.text]).toEqual([
    400,
    expect.stringContaining('Unsupported format: exe'),
  ])
  expect((await readStatus(page)).status).toBe('completed')
  expect((await readNotifications(page)).total).toBe(announced.total)

  // ---- 5. 格式名大小写：闸门认得 'AVI'，编码器就得真按 avi 把文件跑出来（这一句原先是红的）
  const upper = await requestJson<StartedResponse>(page, '/api/transcode/1', {
    method: 'POST',
    body: { target_format: 'AVI' },
  })
  expect([upper.status, upper.target_format]).toEqual(['started', 'avi'])
  const avi = await waitSettled(page)
  // 进度钉的是"跑完了就是 100"，不是"编码器最后一条进度行报到哪"：avi 那一路最后一条
  // `out_time` 是 28 秒（30 秒的片子差最后一帧），照它算只有 93.3 —— 摘掉 `job.progress =
  // 100.0` 那一句，红的就是这里（webm 那一趟容器自己补到了 30 秒，所以它证不到这件事）
  expect([avi.status, avi.error, avi.target_format, avi.progress]).toEqual([
    'completed',
    null,
    'avi',
    100,
  ])
  const aviPath = avi.output_path ?? ''
  expect(aviPath).not.toBe(webmPath)
  expectRealOutput(aviPath, 'avi')
  produced.push(aviPath)
  const afterUpper = await readNotifications(page)
  // 第二个任务同样自己报了一次：`data.format` 用的是归一之后的那个写法
  expect(afterUpper.total).toBe(announced.total + 1)
  expect(afterUpper.items[0]?.data).toEqual({ video_id: 1, format: 'avi' })
  expect(afterUpper.items[0]?.type).toBe('transcode_complete')

  // ---- 6. mkv 那一行配方同样要有真产物：闸门只挡 mp4，这一步原先就可以做，只是没做
  await chooseFormat(page, 'mkv (.mkv)')
  await page.getByRole('button', { name: '开始转码' }).click()
  await confirmMessageBox(page)
  const mkv = await waitSettled(page)
  // 这一步不钉 progress：avi 那一趟已经说明「容器最后报到第几秒」是编码器的细节（见上一步）
  expect([mkv.status, mkv.is_transcoding, mkv.error, mkv.target_format]).toEqual([
    'completed',
    false,
    null,
    'mkv',
  ])
  const mkvPath = mkv.output_path ?? ''
  expect(mkvPath).not.toBe(aviPath)
  expectRealOutput(mkvPath, 'mkv')
  produced.push(mkvPath)
  const afterMkv = await readNotifications(page)
  expect(afterMkv.total).toBe(afterUpper.total + 1)
  expect(afterMkv.items[0]?.data).toEqual({ video_id: 1, format: 'mkv' })

  // ---- 7. 已经跑完的任务不能被「取消」：取消只认还在跑的那一个
  const cancel = await fetchInPage(page, '/api/transcode/1/cancel', {
    method: 'POST',
    headers: CSRF,
  })
  expect([cancel.status, cancel.text]).toEqual([
    404,
    expect.stringContaining('No active transcoding'),
  ])
  // 拒绝不能顺手把记录改掉
  expect(await readStatus(page)).toEqual(mkv)

  // ---- 8. 转码不往库里加片子：产物只是媒体目录里多出来的文件，没扫过就不是影片
  expect((await requestJson<{ total: number }>(page, '/api/videos')).total).toBe(1)
})
