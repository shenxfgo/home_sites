/**
 * 转码那几条真后端用例共用的那几行：查配方表、验磁盘上的产物、轮询作业状态、点那两个下拉框。
 *
 * 单独成一个文件而不是让第 25 条把 `STREAMS` 那张表再抄一遍：这张表是「四行配方四行都有真
 * 产物」这句话的唯一出处，抄一份就变成两张表各自红——#143 教的正是这件事（两条写路径各从
 * 文件名里切一次，切法就各自漂了，直到真库上摆着两种名字才看见）。
 *
 * 和 `support.ts` 的分工：那一份管登录、带 cookie 发请求、封面目录拍扁这些**跨流程**的接线，
 * 这一份只管转码这一条流程内部的形状。根级 `beforeEach(signIn)` 两边都不注册，仍然写在每个
 * spec 文件自己身上（模块缓存只绑第一个引入它的文件，理由见 `support.ts` 文件头）。
 */
import { expect, type Page } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { join, sep } from 'node:path'

import { MEDIA_DIR, TRANSCODE_DIR } from './env'
import { fetchInPage, requestJson } from './support'

/** 播种那部片子的文件；产物**不**落在它旁边（#154），这里只当源文件用。 */
export const FIXTURE = join(MEDIA_DIR, 'e2e_sample.mp4')

/**
 * 每种容器的"自报家门"写在文件头几十个字节里（matroska / webm 是 EBML 的 DocType，
 * avi 是 RIFF 的 FormType，mp4 是第 4 个字节起那四个字符 `ftyp`）。读它而不是只看文件名的
 * 扩展名：文件名是应用拼出来的，里面那几个字节才是 FFmpeg 真写下去的东西。
 */
export const CONTAINER: Record<string, string> = {
  mkv: 'matroska',
  webm: 'webm',
  avi: 'AVI LIST',
  mp4: 'ftyp',
}

/**
 * 产物里应该有的那两条流。`-c:v` / `-c:a` 这半张配方不进任何 API 响应
 * （`get_supported_formats` 只回 `codec` 和 `extension`），所以它原先在整套测试里
 * 一处都证不到：把 webm 的 acodec 从 `libopus` 改成容器直接拒收的 `aac`，无声夹具那趟
 * 整跑下来是绿的（没有音频流可选时 ffmpeg 把 `-c:a` 整个跳过，实测 rc=0、产物只有一条
 * vp9）。这里写的是 ffprobe 那一侧的编码器名，不是配方字面值：libvpx-vp9 → vp9、
 * libx264 → h264、libopus → opus、aac → aac。
 *
 * 四行配方四行都有真产物了：webm、avi、mkv 那三行由 `transcode.real.spec.ts` 第 15 条从播种
 * 那部 .mp4 转出来，mp4 那一行由第 25 条（`video-transcode-mp4.real.spec.ts`）从一部**现场
 * remux 出来的 .mkv** 转出来。差别只在源：同格式那道闸门比的是源文件的扩展名和目标格式是不是
 * 同一个（`transcode_service.py` 里那句 `Path(input_path).suffix`），源是 .mp4 时它刚好把唯一
 * 一种"目标是 mp4"的写法挡死，所以那一行从前改错也不会红。mkv 与 avi 那两行的编码器字面值
 * 是一样的，但查表按格式名各查各的：改错 mkv 那一行只红 mkv 那一步，实测 codec / acodec 两个
 * 变异都红在它的流清单上。
 */
export const STREAMS: Record<string, [string, string][]> = {
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
  mp4: [
    ['audio', 'aac'],
    ['video', 'h264'],
  ],
}

/** `/api/videos` 列表里这些用例要读的那几列。 */
export interface VideoListItem {
  id: number
  title: string | null
  duration: number | null
  thumbnail_path: string | null
}

export interface TranscodeStatus {
  video_id: number
  is_transcoding: boolean
  status: string
  progress: number
  target_format: string | null
  output_path: string | null
  error: string | null
}

/** `/api/transcode/{id}/outputs` 的一行（#154 那张产物表从 HTTP 出来的形状）。 */
export interface TranscodeProduct {
  id: number
  target_format: string
  output_path: string
  /** 这次请求当场 stat 出来的，不是表里的抄本；文件没了就是 null。 */
  size_bytes: number | null
  created_at: string
  deleted_at: string | null
}

export interface NotificationList {
  total: number
  items: {
    id: number
    type: string
    title: string
    message: string
    /** 后台任务往 `data` 那列 JSON 上写的就是这两个键，写死形状才按得到 id。 */
    data: { video_id: number; format: string } | null
  }[]
}

/** 两边都可能是 `\` 或 `/`，归一到 `/` 再比：和第 13 条比 filepath 用的是同一个办法。 */
export function asUrlPath(path: string): string {
  return path.split(sep).join('/')
}

export function sha1(bytes: Buffer): string {
  return createHash('sha1').update(bytes).digest('hex')
}

/** 问 ffprobe 这个文件里有哪几条流：编出来的东西只有它说了才算。 */
export function probeStreams(path: string): { codec_type: string; codec_name: string }[] {
  const probe = spawnSync(
    'ffprobe',
    ['-v', 'quiet', '-print_format', 'json', '-show_streams', path],
    { encoding: 'utf8' },
  )
  expect(probe.status, `ffprobe ${path}`).toBe(0)
  const parsed = JSON.parse(probe.stdout) as { streams: { codec_type: string; codec_name: string }[] }
  return parsed.streams
}

/** 问 ffprobe 这个文件里有哪几条流，按 `[类型, 编码器]` 排好——和 `STREAMS` 同一种形状。 */
export function streamPairs(path: string): [string, string][] {
  return probeStreams(path)
    .map((stream) => [stream.codec_type, stream.codec_name] as [string, string])
    .sort()
}

/** 某一部片子那一格产物目录：`<输出目录>/<影片 id>`（#154 定下的布局）。 */
export function productDir(videoId: number): string {
  return join(TRANSCODE_DIR, String(videoId))
}

/** 那一格里应该躺着的文件名：`<源文件名去扩展>.<格式>`。 */
export function productPath(videoId: number, stem: string, format: string): string {
  return join(productDir(videoId), `${stem}.${format}`)
}

/**
 * 服务器报回来的输出路径，必须是磁盘上真存在、且文件头自报家门的那个文件。
 *
 * 前两句是 #154 加的：产物从前就写在源文件旁边，而那个目录正是被扫的那一个——写在那里
 * 的下一个任务不是"转码"而是"库里多出一行影片"。所以这里除了核对形状，还当场核对一次
 * **它在产物目录里、且不在媒体目录里**：把 `product_path` 改回 `with_suffix` 的那一刻，
 * 这个函数就会红，而不是等到哪天扫描把产物当成片子才看见。
 */
export function expectRealOutput(
  outputPath: string,
  format: string,
  videoId = 1,
  stem = 'e2e_sample',
): void {
  const expected = asUrlPath(productPath(videoId, stem, format))
  expect(asUrlPath(outputPath), outputPath).toBe(expected)
  expect(asUrlPath(outputPath).startsWith(`${asUrlPath(MEDIA_DIR)}/`)).toBe(false)
  expect(existsSync(outputPath), outputPath).toBe(true)
  const bytes = readFileSync(outputPath)
  expect(bytes.length, outputPath).toBeGreaterThan(0)
  expect(bytes.subarray(0, 64).toString('latin1'), outputPath).toContain(
    CONTAINER[format] as string,
  )
  expect(streamPairs(outputPath), outputPath).toEqual(STREAMS[format])
}

export async function readStatus(page: Page, videoId = 1): Promise<TranscodeStatus> {
  return requestJson<TranscodeStatus>(page, `/api/transcode/${videoId}/status`)
}

/**
 * 读某一部片子的产物表。
 *
 * 这一次读**顺带把 `deleted_at` 写了**：`list_outputs()` 是那一列唯一的写的人（读时核对）。
 * 所以调用它会改变服务端状态——不是纯 getter，用例里把它当成"核对一次并告诉我结果"来用。
 */
export async function readProducts(page: Page, videoId = 1): Promise<TranscodeProduct[]> {
  return requestJson<TranscodeProduct[]>(page, `/api/transcode/${videoId}/outputs`)
}

export async function readNotifications(page: Page): Promise<NotificationList> {
  const response = await fetchInPage(page, '/api/notifications')
  expect(response.status).toBe(200)
  return JSON.parse(response.text) as NotificationList
}

/**
 * 等这一个任务离开 running：终态是 completed / failed / cancelled。
 *
 * `timeout` 是给第 17 条留的：那一步重编的是一部真 720p 片子，而播种那部 5 KB 黑屏
 * 0.06 秒就编完了——两个时长不是一个量级，不该为了一个去放宽另一个的闸。
 */
export async function waitSettled(
  page: Page,
  videoId = 1,
  timeout = 60_000,
): Promise<TranscodeStatus> {
  await expect
    .poll(async () => (await readStatus(page, videoId)).status, {
      timeout,
      message: 'the transcode job never left the running state',
    })
    .not.toBe('running')
  return readStatus(page, videoId)
}

export async function chooseFormat(page: Page, label: string): Promise<void> {
  await page.locator('.transcode-section .el-select').click()
  await page.locator('.el-select-dropdown__item', { hasText: label }).click()
}

export async function confirmMessageBox(page: Page): Promise<void> {
  await page.locator('.el-message-box__btns button', { hasText: '确定' }).click()
}
