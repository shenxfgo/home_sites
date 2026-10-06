/**
 * 真后端 e2e 的第 21 条：一部**字幕装在容器里面**的片子，从磁盘一路走到浏览器渲染出的那句字幕。
 *
 * 缝在哪：`backend/src/utils/media_streams.py` 那两个函数——`probe_streams`（问 ffprobe 这个文件里有
 * 哪几条字幕轨、哪条能转）和 `extract_subtitle_webvtt`（问 ffmpeg 把其中一条抠成 WebVTT，写 stdout、
 * 不落盘）。它那边有 9 条服务用例（`backend/tests/test_utils/test_media_streams.py`），其中 8 条把
 * `subprocess.run` 换成一份手写的 ffprobe JSON、第九条连子进程都不碰（它在「文件不存在」那一步就抛），
 * 所以「真容器会被 ffprobe 报成什么样」这一件事从来没有人问过真进程：`WEBVTT_CODECS` 那道
 * `supported` 闸门、`_LANGUAGE_NAMES` 里 `chi → 中文` 那一格、
 * `stream_index` 与 `position` 的区别（前端拿前者拼提取地址）、`_label_of` 的三级兜底、以及 ffmpeg
 * 自己那句失败原因——全是对着我自己造的字典测出来的。而 100 条桩用例这一头更直接：
 * `frontend/e2e/fixtures.ts` 那份 `/videos/{id}/subtitles/streams` 处理器**永远回 `subtitles: []`**，
 * `/subtitles/embedded/{n}/stream` 无论问哪一条都回同一段写死的 `SAMPLE_VTT`。
 *
 * 所以核对的全是只有真文件给得出的东西：一条 `mov_text` 加一条 `ttml` 装在同一个 mp4 里，前者在
 * 允许清单内、后者不在；提取出来的 WebVTT 里那句字幕文本，只存在于我现场编进去的那条轨上（替身给
 * 的那段是另一句话，播种那部的 sidecar 又是第三句）；`stream_index` 必须是 2 和 3 而不是 0 和 1——
 * 拼错一位，界面上点「中文」就会去要视频轨。播放页那一头签的是**浏览器自己解析出来的 cue**：
 * `video.textTracks` 里那条轨的 cue 文本必须等于现场写进容器的那两句，这一句是整条用例里唯一
 * "真进程 + 真容器 + 真浏览器"三方都在场的断言。
 *
 * 顺序：文件名排在 `video-edit` 之后、`video-tags` 之前。它自己造的那个 mp4 和那一行影片都由本条
 * 收走（留在媒体目录里，下一轮扫描就把它当成一部新片子，`files_found` 那一族断言全得重写），
 * 而且必须排在第 9 条（通知）之后——它自己那一趟扫描会往 `notifications` 里真写一行。
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdtempSync, rmSync, writeFileSync, existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

import { MEDIA_DIR } from './env'
import { CSRF, coverFingerprints, fetchInPage, requestJson, scanSource, signIn } from './support'

/** 现场编出来的那一部：h264 + aac + mov_text(chi) + ttml(eng)，全在媒体目录里。 */
const EMBEDDED_FILE = join(MEDIA_DIR, 'e2e_embedded.mp4')
const PARSED_TITLE = 'e2e embedded'
/** 只存在于这条轨上的两句话：替身那段 `SAMPLE_VTT` 和播种那部的 sidecar 都不是这两句。 */
const CUE_ONE = '内嵌字幕·第一句 EMBEDDED-CUE-ONE'
const CUE_TWO = '内嵌字幕·第二句 EMBEDDED-CUE-TWO'

interface EmbeddedTrack {
  stream_index: number
  position: number
  codec: string
  language: string | null
  label: string
  supported: boolean
}

interface AudioTrack {
  stream_index: number
  position: number
  codec: string
  language: string | null
  label: string
  default: boolean
}

interface MediaStreams {
  probed: boolean
  container: string | null
  subtitles: EmbeddedTrack[]
  audio: AudioTrack[]
}

interface VideoRow {
  id: number
  title: string | null
  filepath: string
  duration: number | null
}

/**
 * 编出那部带两条内嵌字幕的 mp4。
 *
 * 为什么是 `ttml` 而不是 PGS/DVD 那种图像字幕：本机的 ffmpeg 只允许「文字转文字、图像转图像」
 * 的字幕编码（`-c:s dvbsub` 直接回 `Subtitle encoding currently only possible from text to text
 * or bitmap to bitmap`），手边没有 bitmap 源。`ttml` 是 `WEBVTT_CODECS` 清单外唯一还能由文本
 * 编出来的那一格，所以 `supported: false` 这一半照样有真容器可对；而它反过来还**送出一个 415**——
 * ffmpeg 没有 ttml 解码器，于是 `-c:s webvtt` 在那条轨上真的失败一次，那句原因是 ffmpeg 自己的。
 *
 * SRT 写在系统临时目录而不是媒体目录：本地扫描是递归的，而 sidecar 是按「同名 + 语言后缀」认的，
 * 落在媒体目录里就可能被登记成播种那部的一新增字幕轨，`subtitles_found` 就不是 0 了。
 */
function writeEmbeddedClip(scratchDir: string): void {
  const srt = join(scratchDir, 'embedded.srt')
  writeFileSync(
    srt,
    `1\n00:00:00,500 --> 00:00:01,500\n${CUE_ONE}\n\n2\n00:00:01,500 --> 00:00:02,000\n${CUE_TWO}\n`,
    'utf8',
  )
  const run = spawnSync(
    'ffmpeg',
    [
      '-v', 'error', '-y',
      '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=24:duration=2',
      '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100:duration=2',
      '-i', srt,
      '-i', srt,
      '-map', '0', '-map', '1', '-map', '2', '-map', '3',
      '-c:v', 'libx264', '-preset', 'ultrafast', '-profile:v', 'baseline', '-pix_fmt', 'yuv420p',
      '-c:a', 'aac', '-ac', '1', '-b:a', '16k',
      // 两条字幕轨：`-c:s:<n>` 的下标数的是**字幕流**，不是输出流
      '-c:s:0', 'mov_text', '-c:s:1', 'ttml',
      '-metadata:s:s:0', 'language=chi',
      '-metadata:s:s:1', 'language=eng',
      '-movflags', '+faststart',
      EMBEDDED_FILE,
    ],
    { encoding: 'utf8' },
  )
  expect(run.status, run.stderr).toBe(0)
}

async function videoIds(page: Page): Promise<number[]> {
  const list = await requestJson<{ items: VideoRow[] }>(page, '/api/videos?page=1&page_size=50')
  return list.items.map((item) => item.id).sort((a, b) => a - b)
}

/** 播放页字幕菜单里此刻看得见的条目文本。 */
async function subtitleMenuItems(page: Page): Promise<string[]> {
  return (await page.locator('.subtitle-menu .subtitle-menu-item').allTextContents()).map((text) =>
    text.trim(),
  )
}

/**
 * 浏览器真的把那条轨拉下来并解析成了 cue —— 返回它读到的 cue 文本清单。
 *
 * 读的是 `video.textTracks`，不是界面：`<track>` 的 src 是应用拼出来的， cue 文本却只有
 * "服务器真的从那个容器里抠出了 WebVTT、浏览器真的拉回来并解析"两边都对才可能出现。
 */
async function renderedCues(page: Page): Promise<{ src: string; mode: string; cues: string[] }[]> {
  return page.evaluate(() => {
    const video = document.querySelector('video')
    if (!video) return []
    // `textTracks` 的下标数的是 `<track>` 元素在文档里的位置——应用自己也是这么假设的
    // （`VideoPlayer.vue` 顶上那句注释），所以 src 按同一个顺序配对拿回来。
    const elements = Array.from(video.querySelectorAll('track'))
    return Array.from(video.textTracks).map((track, index) => ({
      src: elements[index]?.getAttribute('src') ?? '',
      mode: track.mode,
      cues: Array.from(track.cues ?? []).map((cue) => ((cue as VTTCue).text ?? '').trim()),
    }))
  })
}

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec，
// 挂错地方的实测症状是这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('内嵌字幕那一路：真 ffprobe 报出那两条轨、真 ffmpeg 抠出那两句、浏览器渲染出来', async ({
  page,
}) => {
  const idsBefore = await videoIds(page)
  const coversBefore = coverFingerprints()
  const scratch = mkdtempSync(join(tmpdir(), 'e2e-sub-'))

  writeEmbeddedClip(scratch)
  let videoId = 0

  try {
    // ---- 1. 一次真扫描把这部片子变成一行
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 1,
      subtitles_found: 0,
    })
    const listed = await requestJson<{ items: VideoRow[] }>(page, '/api/videos?page=1&page_size=50')
    const created = listed.items.find((item) => item.title === PARSED_TITLE)
    expect(created, `扫描没有把 ${PARSED_TITLE} 变成一行`).toBeDefined()
    videoId = created!.id
    expect(created!.filepath.replace(/\\/g, '/')).toContain('e2e_embedded.mp4')

    // ---- 2. 问真 ffprobe：这个容器里有哪几条轨（替身在这里永远回空清单）
    const streams = await requestJson<MediaStreams>(page, `/api/videos/${videoId}/subtitles/streams`)
    expect(streams.probed).toBe(true)
    expect(streams.container, 'ffprobe 报的容器名').toContain('mp4')
    expect(streams.subtitles).toEqual([
      {
        stream_index: 2,
        position: 0,
        codec: 'mov_text',
        language: 'chi',
        label: '中文',
        supported: true,
      },
      {
        stream_index: 3,
        position: 1,
        codec: 'ttml',
        language: 'eng',
        label: '英文',
        supported: false,
      },
    ])
    // 音频那一清单顺带签了 `_language_of` 的 und→null 和 `_label_of` 的最后一级兜底：
    // mp4 里这条 aac 的语言标签是 `und`，标题没有，所以名字只能落到「轨道 1」。
    expect(streams.audio).toEqual([
      {
        stream_index: 1,
        position: 0,
        codec: 'aac',
        language: null,
        label: '轨道 1',
        default: true,
      },
    ])
    // 反面：播种那部只有视频轨 + 音轨，内嵌清单必须是空的。少了这一句，"列表里永远有两条轨"
    // 这种写法在这条用例里也是全绿的（而它替的是另一件事）。
    const seededStreams = await requestJson<MediaStreams>(page, '/api/videos/1/subtitles/streams')
    expect(seededStreams.subtitles).toEqual([])

    // ---- 3. 提取那条支持的轨：WebVTT 是从容器里现抠的，不落盘
    const extracted = await fetchInPage(page, `/api/videos/${videoId}/subtitles/embedded/2/stream`)
    expect(extracted.status).toBe(200)
    expect(extracted.contentType).toContain('text/vtt')
    expect(extracted.text.startsWith('WEBVTT'), extracted.text.slice(0, 200)).toBe(true)
    expect(extracted.text).toContain(CUE_ONE)
    expect(extracted.text).toContain(CUE_TWO)
    // ffmpeg 的 WebVTT muxer 写的是点号时间戳，而我那句 cue 文本在这里只可能来自这一条轨。
    expect(extracted.text).toContain('00:00.500 --> 00:01.500')
    // 不是别处的字幕：播种那部的 sidecar 文案、以及替身夹具那段写死的 `SAMPLE_VTT` 都不许出现。
    expect(extracted.text).not.toContain('E2E subtitle line')

    // ---- 4. 两种"要不到"各有原话，而且都是真进程/真探测说出来的
    const ttml = await fetchInPage(page, `/api/videos/${videoId}/subtitles/embedded/3/stream`)
    expect(ttml.status, ttml.text).toBe(415)
    // 本机的 ffmpeg 没有 ttml 解码器；这句是它的 stderr 尾巴，不是应用写的文案。
    expect(ttml.text).toContain('内嵌字幕提取失败：')
    expect(ttml.text).toContain('Invalid argument')

    // 视频轨（0）和音频轨（1）都不是字幕轨：这一句挡的是"清单是用全部流建的"这种写法。
    for (const index of [0, 1]) {
      const notSubtitle = await fetchInPage(
        page,
        `/api/videos/${videoId}/subtitles/embedded/${index}/stream`,
      )
      expect(notSubtitle.status, notSubtitle.text).toBe(404)
      expect(notSubtitle.text).toContain(`文件里没有编号为 ${index} 的字幕轨`)
    }

    // ---- 5. 界面上：菜单里只有那条 supported 的，另一条以计数出现，点下去浏览器真有词
    // 播放器挂在 `VideoDetail.vue` 的 `v-if="isPlaying"` 下面——不点这张海报，`.subtitle-btn`
    // 永远不存在（实测症状就是 20 秒超时后报"element(s) not found"，而那一页的前四步全对）。
    await page.goto(`/videos/${videoId}`)
    await page.locator('.preview-area').click()
    await expect(page.locator('.video-player')).toBeVisible()
    // 菜单里那两条是 `listMediaStreams` 异步探出来的，所以要等按钮出现，不能假定它已经在。
    await expect(page.locator('.subtitle-btn')).toBeVisible({ timeout: 20_000 })
    await page.locator('.subtitle-btn').click()
    await expect(page.locator('.subtitle-menu')).toBeVisible()
    await expect(page.locator('.subtitle-menu-group', { hasText: '文件内嵌' })).toBeVisible()
    const items = await subtitleMenuItems(page)
    // 「中文」在、「英文」不在：这一句是 `VideoPlayer.vue` 那道 `.filter(track => track.supported)`
    // 的签字，而它读的是服务器给的 `supported`，不是自己按 codec 名猜的。
    expect(items).toContain('中文')
    expect(items).not.toContain('英文')
    await expect(page.locator('.subtitle-menu-note')).toContainText('1 条图像字幕浏览器放不出来')

    await page.locator('.subtitle-menu-item', { hasText: '中文' }).click()
    await expect
      .poll(() => renderedCues(page), {
        message: '那条内嵌轨没有被浏览器拉下来并解析成 cue',
      })
      .toContainEqual({
        src: `/api/videos/${videoId}/subtitles/embedded/2/stream`,
        mode: 'showing',
        cues: [CUE_ONE, CUE_TWO],
      })

    // ---- 6. 行不在的时候，那两个接口改口 404：它们读的是行，不是一份缓存
    const gone = await fetchInPage(page, '/api/videos/99999/subtitles/streams')
    expect(gone.status, gone.text).toBe(404)
    expect(gone.text).toContain('视频不存在')
    const goneExtract = await fetchInPage(page, '/api/videos/99999/subtitles/embedded/2/stream')
    expect(goneExtract.status, goneExtract.text).toBe(404)
    expect(goneExtract.text).toContain('视频不存在')
  } finally {
    // `finally` 里只收场、不抛（#136 的规矩：这里抛出的异常会顶掉真正的失败原因）。
    // 磁盘上这两个文件就算没删干净也不影响下一轮——`e2e_seed.prepare_media()` 起跑就 rmtree。
    if (videoId) {
      await fetchInPage(page, `/api/videos/${videoId}`, { method: 'DELETE', headers: CSRF })
    }
    try {
      rmSync(EMBEDDED_FILE, { force: true, maxRetries: 10, retryDelay: 500 })
      rmSync(scratch, { recursive: true, force: true, maxRetries: 10, retryDelay: 500 })
    } catch {
      // 下一轮起跑的那次 rmtree 兜底
    }
  }

  // 收尾之后才核对（#120 的规矩：断言不写在 `finally` 的 body 里）。
  expect(await videoIds(page)).toEqual(idsBefore)
  expect(existsSync(EMBEDDED_FILE)).toBe(false)
  // 别人的封面一张都不能少：这一趟扫描多写一张，删除只该带走它自己那一张。
  expect(coverFingerprints()).toEqual(coversBefore)
})
