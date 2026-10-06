/**
 * 真后端 e2e 的第 22 条：字幕装在**影片旁边**的那一路——三个 sidecar 从磁盘走到浏览器解析出的
 * cue，再走到其中那个文件被人删掉之后那条轨停在哪儿。
 *
 * 缝在哪：`backend/src/utils/subtitles.py`。它那边有 12 条服务用例，把「认文件」和「转 WebVTT」
 * 两头都覆盖了，但**转换那一半只有一条真进程**：`.ass`/`.ssa` 走的是 `_ffmpeg_to_webvtt`，而它
 * 唯一的用例（`test_convert_ass_uses_ffmpeg`）把 `subprocess.run` 换成一份写死的
 * `subprocess.CompletedProcess(stdout="WEBVTT\n\n")`——真 ffmpeg 遇到真 ASS 会吐出什么，从来没
 * 有人问过真进程。于是这一格能红的原因有好几个各自独立：`-f webvtt` 写错成别的格式、输入没按
 * 容器自动认（本机实测：把 `[Script Info]` 那一段去掉，ffprobe 报的是 `lrc`，ffmpeg 用 `text`
 * 解码器读完，出来一句 `WEBVTT` 后面**一个 cue 都没有**，退出码仍是 0）、ASS 的覆写标记没被剥掉
 * （真转换会把 `{\an8}` 吃掉、把 `\N` 变成换行）。还有 `_LANGUAGE_ALIASES` 那一张表：
 * `chi → zh`、`eng → en` 只有真文件名会喂给它，而 100 条桩用例那一头 `fixtures.ts` 的
 * `/videos/{id}/subtitles` 处理器回的是手抄的两行、那个 stream 处理器无论问哪一条都回同一段
 * `SAMPLE_VTT`。
 *
 * 所以核对的全是只有真文件给得出的东西：三条 sidecar 认出来的是 `zh`/`en`/`ja` 而不是文件名里
 * 那三个后缀（别名表）、而界面上的名字是**没归一化**的 `chi`/`eng`/`jpn`（`label` 存的是原始
 * 后缀——内嵌那一路给的是「中文」，这一路给的是「chi」，两边不对称是真的，本条把它钉成现状）；
 * 同一次转换里两条时间轴方言：Python 手写的那条保留小时（`00:00:03.000 -->`），ffmpeg 那条把
 * 小时省了（`00:05.000 -->`），谁把两边统一成一种写法就说明其中一路没走真进程；`{\an8}` 在
 * WebVTT 里必须消失而 `Dialogue:` 和 `ScriptType` 必须整个不见（原样吐回一个 `.ass` 是这一路
 * 最像"成功"的失败）；以及两句只有真文件才会给的现状——**一个 cue 都解析不出来的转换仍然回
 * 200**，而**字幕文件被人删掉之后界面上有两副样子**：不重载时那条轨放的是浏览器早就解析完存在
 * 内存里的旧 cue（接口那句 404 谁也没听见，切过去照样那两句词），重载之后 `<track>` 才真的去
 * 拉一次、`readyState` 变成 3，而菜单里那个条目照旧在、照旧可点、照旧什么都不提示。第 7 步两头
 * 都钉住了。播放页那一头签的还是浏览器自己解析出的 cue，和上一条同一族"真进程 + 真文件 +
 * 真浏览器"三方都在场的断言。
 *
 * 一个踩过的坑写在这里省后人半天：`selectTrack` 收尾会把 `showSubtitleMenu` 关掉，所以**连着点
 * 两个字幕条目必须在中间重新点开菜单**。不重开的症状不是断言失败，是那条 `.click()` 一直等到
 * 用例超时——Playwright 等一个永远不出现的元素时不会替你分辨"没这个元素"和"元素没可见"。
 *
 * 顺序：文件名排在 `video-embedded-subtitles` 之后、`video-tags` 之前。它自己造的那四个文件
 * 和那一行影片都由本条收走（留在媒体目录里，下一轮扫描就把它们当成一部新片子，`files_found`
 * 那一族断言全得重写），而且必须排在第 9 条（通知）之后——它自己那一趟扫描会往 `notifications`
 * 里真写一行。
 */
import { expect, test, type Page } from '@playwright/test'
import { copyFileSync, existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { MEDIA_DIR } from './env'
import { CSRF, coverFingerprints, fetchInPage, requestJson, scanSource, signIn } from './support'

/** 播种那部的字节，复制成第二部：sidecar 这一路要验的是认文件和转换，与画面无关。 */
const SEEDED_FILE = join(MEDIA_DIR, 'e2e_sample.mp4')
const CLIP_FILE = join(MEDIA_DIR, 'e2e_sidecar.mp4')
const ASS_FILE = join(MEDIA_DIR, 'e2e_sidecar.chi.ass')
const SRT_FILE = join(MEDIA_DIR, 'e2e_sidecar.eng.srt')
/** 只有 `[Events]` 那一段的 ASS：模拟一个被截断的下载，ffmpeg 认不出容器。 */
const BROKEN_FILE = join(MEDIA_DIR, 'e2e_sidecar.jpn.ass')
const PARSED_TITLE = 'e2e sidecar'

const CUE_ASS_ONE = '外挂 ASS·第一句 SIDECAR-ASS-ONE'
const CUE_ASS_TWO = '外挂 ASS·第二句 SIDECAR-ASS-TWO'
const CUE_SRT_ONE = '外挂 SRT·第一句 SIDECAR-SRT-ONE'
const CUE_SRT_TWO = '外挂 SRT·第二句 SIDECAR-SRT-TWO'
const CUE_BROKEN = '截断那半句 SIDECAR-BROKEN'

interface SubtitleRow {
  id: number
  video_id: number
  language: string | null
  filepath: string
  label: string | null
}

interface VideoRow {
  id: number
  title: string | null
  filepath: string
}

/**
 * 一份带完整头的 ASS：`[Script Info]` 那一段在不在，决定 ffprobe 认它是 `ass` 还是 `lrc`，
 * 而后者会让整条转换安静地变成零条 cue。所以夹具自己先把这个头钉住——本条的立足点就是这个
 * 前缀，写夹具的人（包括写它的我）一旦把它丢了，红应该红在夹具上而不是红在结论上。
 */
const ASS_HEAD = [
  '[Script Info]',
  'ScriptType: v4.00+',
  'PlayResX: 320',
  'PlayResY: 180',
  '',
  '[V4+ Styles]',
  'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
  'Style: Default,Arial,16,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1',
  '',
]
const ASS_EVENTS = [
  '[Events]',
  'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
  // `{\an8}` 是覆写标记（顶对齐），`\N` 是换行：两个都只有真解码器会处理
  `Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,{\\an8}${CUE_ASS_ONE}`,
  `Dialogue: 0,0:00:10.00,0:00:12.00,Default,,0,0,0,,\\N${CUE_ASS_TWO}`,
  '',
]
/** 只留事件段、没有 `[Script Info]` 头：ffprobe 把这样的文件认成 `lrc`，于是转换出来一句 cue 都没有。 */
const BROKEN_EVENTS = [
  ...ASS_EVENTS.slice(0, 2),
  `Dialogue: 0,0:00:14.00,0:00:16.00,Default,,0,0,0,,${CUE_BROKEN}`,
  '',
]

function writeSidecarFixtures(): void {
  copyFileSync(SEEDED_FILE, CLIP_FILE)
  writeFileSync(ASS_FILE, [...ASS_HEAD, ...ASS_EVENTS].join('\n'), 'utf8')
  writeFileSync(BROKEN_FILE, BROKEN_EVENTS.join('\n'), 'utf8')
  // SRT 按字节写：`srt_to_webvtt` 先把 \r\n 折成 \n，而文本模式会在 Windows 上把 \n 再翻成
  // \r\n——翻完就成了 \r\r\n，那条时间戳行的匹配照样成立，但每一句文本前面多出一个空行。
  writeFileSync(
    SRT_FILE,
    `1\r\n00:00:03,000 --> 00:00:05,000\r\n${CUE_SRT_ONE}\r\n\r\n2\r\n00:00:06,000 --> 00:00:09,000\r\n${CUE_SRT_TWO}\r\n`,
    'utf8',
  )
  // 夹具自己的钉子：这两个转义序列在 TS 里都写成了双反斜杠，落到磁盘上必须是单反斜杠。
  expect(readFileSync(ASS_FILE, 'utf8')).toContain(`{\\an8}${CUE_ASS_ONE}`)
  expect(readFileSync(ASS_FILE, 'utf8')).toContain(`\\N${CUE_ASS_TWO}`)
  expect(readFileSync(BROKEN_FILE, 'utf8').startsWith('[Events]')).toBe(true)
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
 * 浏览器自己那条轨的此刻状态：地址、模式、加载状态、以及它解析出了哪几句（读不到 cue 时给空清单）。
 *
 * 读的是 `video.textTracks` 而不是界面：src 是应用拼的、WebVTT 是服务器转出来的、cue 却是
 * 浏览器自己解析的，三方任一边走错这里都不会有那两句词。
 *
 * 加载状态取 `<track>` **元素**上那个 0..3（`TextTrack.readyState` 那个字符串枚举在 TS 的
 * lib.dom 里根本没声明，而元素上的 2=已加载、3=失败是类型可用的）。
 */
async function trackStates(
  page: Page,
): Promise<{ src: string; mode: string; elementState: number; cues: string[] }[]> {
  return page.evaluate(() => {
    const video = document.querySelector('video')
    if (!video) return []
    const elements = Array.from(video.querySelectorAll('track'))
    return Array.from(video.textTracks).map((track, index) => ({
      src: elements[index]?.getAttribute('src') ?? '',
      mode: track.mode,
      elementState: elements[index]?.readyState ?? -1,
      cues: Array.from(track.cues ?? []).map((cue) => ((cue as VTTCue).text ?? '').trim()),
    }))
  })
}

// 根级钩子必须写在本文件里：`support.ts` 那份 import 只会绑到第一个引入它的 spec，
// 挂错地方的实测症状是这条用例停在 about:blank 上、相对 fetch 直接拼不出地址。
test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('sidecar 字幕那一路：真文件名认出三种语言、真 ffmpeg 转掉 ASS 的标记、文件没了浏览器标成 error', async ({
  page,
}) => {
  expect(existsSync(SEEDED_FILE), '播种那部不在，复制不出第二部').toBe(true)
  const idsBefore = await videoIds(page)
  const coversBefore = coverFingerprints()
  writeSidecarFixtures()

  let videoId = 0
  let srtId = 0

  try {
    // ---- 1. 一次真扫描：一部新片 + 三条 sidecar
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 1,
      subtitles_found: 3,
    })
    const listed = await requestJson<{ items: VideoRow[] }>(page, '/api/videos?page=1&page_size=50')
    const created = listed.items.find((item) => item.title === PARSED_TITLE)
    expect(created, `扫描没有把 ${PARSED_TITLE} 变成一行`).toBeDefined()
    videoId = created!.id

    // ---- 2. 认文件：`language` 走的是别名表，`label` 是原始后缀
    const rows = await requestJson<SubtitleRow[]>(page, `/api/videos/${videoId}/subtitles`)
    // 下面的整表比对押的是接口自己的排序，所以先钉一遍它真按 id 升序回。`sort` 是原地改，
    // 所以比的是副本——直接 `rows.map(...).sort()` 对 `rows.map(...)` 永远成真。
    const ids = rows.map((row) => row.id)
    expect([...ids].sort((a, b) => a - b)).toEqual(ids)
    const shaped = rows.map(({ video_id, language, label, filepath }) => ({
      video_id,
      language,
      label,
      // 库里存的是 `os.path.normpath` 出来的 Windows 反斜杠，比较前两头都折成 `/`。
      filepath: filepath.replace(/\\/g, '/'),
    }))
    expect(shaped).toEqual([
      {
        video_id: videoId,
        language: 'zh',
        label: 'chi',
        filepath: ASS_FILE.replace(/\\/g, '/'),
      },
      {
        video_id: videoId,
        language: 'en',
        label: 'eng',
        filepath: SRT_FILE.replace(/\\/g, '/'),
      },
      {
        video_id: videoId,
        language: 'ja',
        label: 'jpn',
        filepath: BROKEN_FILE.replace(/\\/g, '/'),
      },
    ])
    srtId = rows[1].id

    // ---- 3. 再扫一遍：同一个文件不会二次登记（`known_paths` 那道去重靠的是两次 HTTP）
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 0,
      subtitles_found: 0,
    })

    // ---- 4. 转换：两条时间轴方言、ASS 的标记被真解码器吃掉
    const ass = await fetchInPage(page, `/api/videos/${videoId}/subtitles/${rows[0].id}/stream`)
    expect(ass.status, ass.text).toBe(200)
    expect(ass.contentType).toContain('text/vtt')
    expect(ass.text).toContain(CUE_ASS_ONE)
    expect(ass.text).toContain(CUE_ASS_TWO)
    // 覆写标记是解码器消化掉的：原样吐回文件就不是转换。
    expect(ass.text).not.toContain('{\\an8}')
    expect(ass.text).not.toContain('Dialogue:')
    expect(ass.text).not.toContain('ScriptType')
    // ffmpeg 的 webvtt muxer 省掉小时，`srt_to_webvtt`（纯 Python）保留小时。
    expect(ass.text).toContain('00:05.000 --> 00:08.000')
    // ASS 的 `\N` 被写成了一次换行，而时间戳行后面紧跟空行在 WebVTT 里的意思是"这条 cue 到此
    // 为止"。所以这句的词**在响应体里**、却不再是一条 cue 的文本（第 6 步在浏览器那一头钉这个
    // 后果）。这一句钉的是现状不是愿望：修掉之后这里该是 `--> 00:12.000\n${CUE_ASS_TWO}`。
    expect(ass.text).toContain('00:10.000 --> 00:12.000\n\n' + CUE_ASS_TWO)

    const srt = await fetchInPage(page, `/api/videos/${videoId}/subtitles/${srtId}/stream`)
    expect(srt.status, srt.text).toBe(200)
    expect(srt.contentType).toContain('text/vtt')
    expect(srt.text).toContain(CUE_SRT_ONE)
    expect(srt.text).toContain(CUE_SRT_TWO)
    expect(srt.text).toContain('00:00:03.000 --> 00:00:05.000')
    // 序号行是 Python 那条路剥掉的（`line.strip().isdigit()`），逗号时间戳也归成了点。
    expect(srt.text).not.toContain(',000 -->')
    expect(srt.text.split('\n').some((line) => /^\s*\d+\s*$/.test(line)), srt.text).toBe(false)

    // ---- 5. 现状：一个 cue 都没有的转换仍然回 200，界面上没有任何东西说它坏了
    const broken = await fetchInPage(page, `/api/videos/${videoId}/subtitles/${rows[2].id}/stream`)
    expect(broken.status, broken.text).toBe(200)
    expect(broken.contentType).toContain('text/vtt')
    expect(broken.text.trim(), 'ffmpeg 认不出这个容器时的整段输出').toBe('WEBVTT')
    // 那句词在文件里、却不在响应里——"200 而零条 cue"要是不钉住这一句，它和一次成功的转换长得一模一样。
    expect(readFileSync(BROKEN_FILE, 'utf8')).toContain(CUE_BROKEN)
    expect(broken.text).not.toContain(CUE_BROKEN)

    // ---- 6. 界面上：三条都在菜单里，名字是那个没归一化的后缀；点下去浏览器真有词
    // 播放器挂在 `VideoDetail.vue` 的 `v-if="isPlaying"` 下面——不点这张海报，`.subtitle-btn`
    // 永远不存在（第 21 条实测过的那次超时）。
    await page.goto(`/videos/${videoId}`)
    await page.locator('.preview-area').click()
    await expect(page.locator('.video-player')).toBeVisible()
    await expect(page.locator('.subtitle-btn')).toBeVisible({ timeout: 20_000 })
    await page.locator('.subtitle-btn').click()
    await expect(page.locator('.subtitle-menu')).toBeVisible()
    // 这部片子容器里一条字幕轨都没有（复制来的 mp4 只有视频轨 + 音轨），所以「文件内嵌」那一段
    // 不该出现：这一句挡的是"菜单把两条来源合起来渲染"这种写法。
    await expect(page.locator('.subtitle-menu-group')).toHaveCount(0)
    expect(await subtitleMenuItems(page)).toEqual(['关闭', 'chi', 'eng', 'jpn'])

    await page.locator('.subtitle-menu-item', { hasText: 'chi' }).click()
    // 第二句是空串：ASS 那句以 `\N` 开头，ffmpeg 把它写成空行，浏览器就在那儿结束了这条 cue。
    // 现状钉在这里，第 4 步响应体里那句词还在——修转换的那一单要把这一格改成两句话。
    await expect
      .poll(() => trackStates(page), {
        message: '那条外挂 ASS 没有被浏览器拉下来并解析成 cue',
      })
      .toContainEqual({
        src: `/api/videos/${videoId}/subtitles/${rows[0].id}/stream`,
        mode: 'showing',
        elementState: 2,
        cues: [CUE_ASS_ONE, ''],
      })

    // 三条轨一次看全。第三条是第 5 步那个"200 而零条 cue"在浏览器那一头的样子：加载状态
    // 2（=已加载）、cue 清单空、模式照常可切——**浏览器完全不觉得有事**。这一句是整条用例
    // 里唯一能证明"这个洞是安静的"的断言，替身夹具那一头永远给不出这个形状。
    // 用 poll 而不是直接读一次：另外两条轨的加载和这条一样是异步的。
    await expect.poll(() => trackStates(page)).toEqual([
      {
        src: `/api/videos/${videoId}/subtitles/${rows[0].id}/stream`,
        mode: 'showing',
        elementState: 2,
        cues: [CUE_ASS_ONE, ''],
      },
      {
        src: `/api/videos/${videoId}/subtitles/${srtId}/stream`,
        mode: 'hidden',
        elementState: 2,
        cues: [CUE_SRT_ONE, CUE_SRT_TWO],
      },
      {
        src: `/api/videos/${videoId}/subtitles/${rows[2].id}/stream`,
        mode: 'hidden',
        elementState: 2,
        cues: [],
      },
    ])

    // ---- 7. 文件从磁盘上没了（行还在）：接口换 404 那句原话，浏览器那一头两段都安静
    rmSync(SRT_FILE, { force: true })
    expect(existsSync(SRT_FILE)).toBe(false)
    // 扫描没有"字幕丢了"这一说：行仍然在清单里，界面也仍然列着它。这是现状，不是本条要的修法。
    const afterLoss = await requestJson<SubtitleRow[]>(page, `/api/videos/${videoId}/subtitles`)
    expect(afterLoss.map((row) => row.id)).toEqual(rows.map((row) => row.id))
    const gone = await fetchInPage(page, `/api/videos/${videoId}/subtitles/${srtId}/stream`)
    expect(gone.status, gone.text).toBe(404)
    expect(gone.text).toContain('字幕文件不存在')

    // 切过去用的还是**已经在内存里的那份** WebVTT：`<track>` 在插入时（`mode` 默认 `hidden`
    // 就够触发一次拉取）就把这条轨解析完了，之后改 `mode` 不再发请求。所以磁盘上那个文件
    // 没了，播放器照样把那两句词放出来——接口那句 404 谁也没听见。
    // 菜单在这里必须重新点开：`selectTrack` 收尾会把 `showSubtitleMenu` 关掉（第 6 步点完
    // 'chi' 之后条目就不在了，直接点第二次的话 Playwright 是在等永远不出现的元素——实测症状
    // 是本条超时报在 `.click()` 上，而不是报在断言上）。
    await page.locator('.subtitle-btn').click()
    await expect(page.locator('.subtitle-menu')).toBeVisible()
    expect(await subtitleMenuItems(page)).toEqual(['关闭', 'chi', 'eng', 'jpn'])
    await page.locator('.subtitle-menu-item', { hasText: 'eng' }).click()
    await expect
      .poll(() => trackStates(page), {
        message: '那条轨没有被切成 showing，或者浏览器把它的旧 cue 丢了',
      })
      .toContainEqual({
        src: `/api/videos/${videoId}/subtitles/${srtId}/stream`,
        mode: 'showing',
        elementState: 2,
        cues: [CUE_SRT_ONE, CUE_SRT_TWO],
      })

    // 重载一次才轮到那个 404 走到浏览器：行还在，所以应用照样列出这条轨、照样给它拼出地址，
    // 而拉取失败之后界面上没有任何东西说它坏了——条目还在、还能点、点下去什么都没有。
    await page.goto(`/videos/${videoId}`)
    await page.locator('.preview-area').click()
    await expect(page.locator('.subtitle-btn')).toBeVisible({ timeout: 20_000 })
    await page.locator('.subtitle-btn').click()
    await expect(page.locator('.subtitle-menu')).toBeVisible()
    expect(await subtitleMenuItems(page)).toEqual(['关闭', 'chi', 'eng', 'jpn'])
    await page.locator('.subtitle-menu-item', { hasText: 'eng' }).click()
    await expect
      .poll(() => trackStates(page), {
        message: '那条已经不在磁盘上的轨没有被浏览器标成失败',
      })
      .toContainEqual({
        src: `/api/videos/${videoId}/subtitles/${srtId}/stream`,
        mode: 'showing',
        elementState: 3,
        cues: [],
      })
    // 到这一步为止，界面对"字幕文件不见了"的全部反应就是：什么都没有。重新点开菜单核对最后
    // 这一句——条目还在、还是可点，而那一段唯一会说话的位置（`.subtitle-menu-note`，内嵌那一路
    // 用它报「1 条图像字幕浏览器放不出来」）对这条死轨一个字都不提。
    await page.locator('.subtitle-btn').click()
    await expect(page.locator('.subtitle-menu')).toBeVisible()
    expect(await subtitleMenuItems(page)).toEqual(['关闭', 'chi', 'eng', 'jpn'])
    await expect(page.locator('.subtitle-menu-note')).toHaveCount(0)
  } finally {
    // `finally` 里只收场、不抛（#136 的规矩：这里抛出的异常会顶掉真正的失败原因）。
    if (videoId) {
      await fetchInPage(page, `/api/videos/${videoId}`, { method: 'DELETE', headers: CSRF })
    }
    for (const file of [CLIP_FILE, ASS_FILE, SRT_FILE, BROKEN_FILE]) {
      try {
        rmSync(file, { force: true, maxRetries: 10, retryDelay: 500 })
      } catch {
        // 下一轮起跑的那次 rmtree 兜底
      }
    }
  }

  // 收尾之后才核对（#120 的规矩：断言不写在 `finally` 的 body 里）。
  expect(await videoIds(page)).toEqual(idsBefore)
  for (const file of [CLIP_FILE, ASS_FILE, SRT_FILE, BROKEN_FILE]) {
    expect(existsSync(file), file).toBe(false)
  }
  // 删一行影片带走它自己的三条字幕行和那一张封面，别人的一张都不能少。
  const seededSubtitles = await requestJson<SubtitleRow[]>(page, '/api/videos/1/subtitles')
  expect(seededSubtitles.map((row) => row.filepath.replace(/\\/g, '/'))).toEqual([
    join(MEDIA_DIR, 'e2e_sample.zh.srt').replace(/\\/g, '/'),
  ])
  expect(coverFingerprints()).toEqual(coversBefore)
})
