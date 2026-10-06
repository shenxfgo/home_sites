/**
 * 真后端 e2e 的第 22、23 条：字幕装在**影片旁边**的那一路——sidecar 从磁盘走到浏览器解析出的
 * cue，再走到其中那个文件被人删掉之后那条轨停在哪儿（第 22 条），以及那份文件**不是 UTF-8** 的
 * 时候这一路都发生些什么（第 23 条，写在同一支文件里：同一个缝、同一套夹具和收尾）。
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
 * 顺序：文件名排在 `video-embedded-subtitles` 之后、`video-tags` 之前。两支用例各自造的文件和
 * 那一行影片都由自己收走（第 22 条四个、第 23 条五个；留在媒体目录里，下一轮扫描就把它们当成一
 * 部新片子，`files_found` 那一族断言全得重写），而且必须排在第 9 条（通知）之后——它们自己那
 * 一趟扫描会往 `notifications` 里真写一行。
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

// ---- 第 23 条的夹具：同一个句子写成四种编码，差别只在文件头那几个字节。
const ENC_CLIP_FILE = join(MEDIA_DIR, 'e2e_encoding.mp4')
const ENC_GBK_FILE = join(MEDIA_DIR, 'e2e_encoding.chi.srt')
const ENC_UTF16_FILE = join(MEDIA_DIR, 'e2e_encoding.eng.srt')
const ENC_BOMVTT_FILE = join(MEDIA_DIR, 'e2e_encoding.jpn.vtt')
const ENC_NOBOM_FILE = join(MEDIA_DIR, 'e2e_encoding.kor.srt')
const ENC_PARSED_TITLE = 'e2e encoding'

const ENC_CUE_GBK_ONE = '编码GBK那一句 ENCODING-GBK-ONE'
const ENC_CUE_GBK_TWO = '编码GBK那一句 ENCODING-GBK-ONE-2'
// 带 BOM 和不带 BOM 那两条 sidecar 用的是**同一个句子**：这一条的论证全靠这两条只差一个 BOM。
const ENC_CUE_UTF16 = 'UTF16带BOM那一句 ENCODING-SAME-SENTENCE'
const ENC_CUE_BOMVTT = '带BOM的VTT那一句 ENCODING-VTT-ONE'

/** SRT 一律按 CRLF 写：中文 Windows 上另存的字幕就是这个换行法，而 `srt_to_webvtt` 得先把它折平。 */
const ENC_SRT_UTF16 = '1\r\n00:00:03,000 --> 00:00:04,000\r\n' + ENC_CUE_UTF16 + '\r\n'
/** 本身就是一份合法 WebVTT：`.vtt` 那一支不转换，只做编码嗅探后原样交出去。 */
const ENC_VTT_BODY = 'WEBVTT\r\n\r\n00:00:07.000 --> 00:00:08.000\r\n' + ENC_CUE_BOMVTT + '\r\n'
const BOM_UTF16LE = Buffer.from([0xff, 0xfe])
const BOM_UTF8 = Buffer.from([0xef, 0xbb, 0xbf])
/**
 * 那份 GBK 字幕的**字节**，136 个。它对应的文本是：`1` / `00:00:01,000 --> 00:00:02,000` /
 * `ENC_CUE_GBK_ONE` / 空行 / `2` / `00:00:04,000 --> 00:00:05,000` / `ENC_CUE_GBK_TWO`，用 CRLF
 * 连起来。为什么要以 base64 住在这里：Node 的 `Buffer` 不支持 GBK/gb18030（只认 utf8、utf16le、
 * latin1 那几样），写不出这个编码；重新生成办法是本机 `.venv/Scripts/python.exe` 把上面那段文本
 * `.encode('gb18030')` 再过一遍 `b64encode`。它到底是不是那句话，不靠这段注释——第 3 步那句
 * **整个响应体相等**就是它的钉子，抄错任何一个字节都会红在那里。
 */
const ENC_GBK_BYTES = Buffer.from(
  'MQ0KMDA6MDA6MDEsMDAwIC0tPiAwMDowMDowMiwwMDANCrHgwutHQkvEx9K7vuQgRU5DT0RJTkctR0JLLU9ORQ0KDQoyDQowMDowMDowNCwwMDAgLS0+IDAwOjAwOjA1LDAwMA0KseDC60dCS8TH0ru+5CBFTkNPRElORy1HQkstT05FLTINCg==',
  'base64',
)

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

/**
 * 第 23 条的夹具：一份影片加四份字幕，四份字幕是**同一个句子的四种编码**。
 *
 * 每一份都按字节写：`writeFileSync` 拿到 `Buffer` 才不会再套一层编码。
 */
function writeEncodingFixtures(): void {
  copyFileSync(SEEDED_FILE, ENC_CLIP_FILE)
  writeFileSync(ENC_GBK_FILE, ENC_GBK_BYTES)
  writeFileSync(ENC_UTF16_FILE, Buffer.concat([BOM_UTF16LE, Buffer.from(ENC_SRT_UTF16, 'utf16le')]))
  writeFileSync(ENC_BOMVTT_FILE, Buffer.concat([BOM_UTF8, Buffer.from(ENC_VTT_BODY, 'utf8')]))
  writeFileSync(ENC_NOBOM_FILE, Buffer.from(ENC_SRT_UTF16, 'utf16le'))

  // 夹具自己的钉子——这一组比第 22 条那三行更要紧：这一条签的是"服务器认出了编码"，而那份 base64
  // 万一抄成了一份 UTF-8 的文件，嗅探分支根本没被执行，用例却会绿（响应里照样有那句中文）。
  // 所以先钉磁盘上**不是** UTF-8，再钉 BOM 那对文件只差 BOM。
  expect(ENC_GBK_BYTES.includes(Buffer.from(ENC_CUE_GBK_ONE, 'utf8')), 'GBK 夹具里混进了 UTF-8 字节').toBe(false)
  expect(ENC_GBK_BYTES.includes(Buffer.from([0xb1, 0xe0])), 'GBK 夹具里没有「编」那两个字节').toBe(true)
  expect(readFileSync(ENC_UTF16_FILE).includes(Buffer.from(ENC_CUE_UTF16, 'utf8')), 'UTF-16 夹具里混进了 UTF-8 字节').toBe(
    false,
  )
  expect(readFileSync(ENC_UTF16_FILE).subarray(2).equals(readFileSync(ENC_NOBOM_FILE)), '两条 UTF-16 不只差一个 BOM').toBe(
    true,
  )
  expect(readFileSync(ENC_BOMVTT_FILE).subarray(3).toString('utf8'), '带 BOM 的 VTT 后面不是那份文本').toBe(ENC_VTT_BODY)
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
    // ASS 的 `\N` 被 muxer 写成一次真的换行，而时间戳行后面紧跟空行在 WebVTT 里的意思是"这条
    // cue 到此为止"——那句词因此落在所有 cue 之外，浏览器上一条也不显示。转换器把紧跟时间戳
    // 的那一段空行收掉（#140），词回到自己的 cue 里。
    expect(ass.text).toContain('00:10.000 --> 00:12.000\n' + CUE_ASS_TWO)
    // 反向那一半：不许顺手把所有空行都删掉，那会把下一条 cue 的时间戳吞进上一条的文本里。
    expect(ass.text).not.toContain('00:12.000\n\n')

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
    // 两句都在：ASS 那句以 `\N` 开头，muxer 把它写成空行、浏览器就在那儿结束了这条 cue，第 22 条
    // 上线时这里解析出的是 `[CUE_ASS_ONE, '']`——词在响应体里，却一句也不显示。#140 修的是转换器。
    await expect
      .poll(() => trackStates(page), {
        message: '那条外挂 ASS 没有被浏览器拉下来并解析成 cue',
      })
      .toContainEqual({
        src: `/api/videos/${videoId}/subtitles/${rows[0].id}/stream`,
        mode: 'showing',
        elementState: 2,
        cues: [CUE_ASS_ONE, CUE_ASS_TWO],
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
        cues: [CUE_ASS_ONE, CUE_ASS_TWO],
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

/**
 * 真后端 e2e 的第 23 条：字幕文件**不是 UTF-8** 的那一路——四种真字节（GBK、UTF-16LE 带 BOM、
 * UTF-8 带 BOM 的 `.vtt`、UTF-16LE 不带 BOM）从磁盘走到浏览器解析出的 cue。
 *
 * 缝在哪：`backend/src/utils/subtitles.py` 的 `read_subtitle_text`。那边 12 条服务用例里只有
 * **一条**碰过编码，而它喂的文件既没有 BOM、也只有一行时间戳：于是 `utf-16` 和 `utf-8-sig`
 * 两个分支到现在**在任何一层都没有一条用例**（单元没有；100 条桩用例那一头 `fixtures.ts` 的
 * stream 处理器永远回同一段手写的 `SAMPLE_VTT`，字节从哪儿来它根本不知道）。这一格空着是有
 * 代价的：`convert_to_webvtt` 的两条支路（`.srt` 走 Python、`.vtt` 原样交出去）都拿这份嗅探的
 * 结果当输入，而**读错编码从来不会报错**——它只会安静地交出一段谁都不认得的字节。
 *
 * 所以核对的全是只有真文件给得出的东西：一份 GBK 的字幕经服务器之后必须是**重编码过的
 * UTF-8**（`Content-Type` 里那个 `charset=utf-8` 说的就是这件事，而 `Content-Length` 是字节数、
 * 中文一个字占三个字节，所以磁盘上 136 字节进去、响应里 143 字节出来，这两个数就是这份响应的身份证）；三条识别成功的响应体一个字都不许
 * 差（解码走错不是"少一个字"，是每一句都换一种乱码）；`.vtt` 那一支的 CRLF 原样保留而开头那三个
 * 字节必须消失（BOM 留在响应里的话 `charCodeAt(0)` 就不是 `W`）；`srt_to_webvtt` 的折平和剥序号
 * 发生在使用 GBK 字节的文件上，才说明"先认编码、再按 SRT 规则转换"这个顺序是真的；最后签**浏览器
 * 自己解析出的 cue**——三方（真文件、真服务器、真浏览器）都在场，任一边走错都不会是那三句中文。
 *
 * 第四条钉的是现状，不是愿望：**没有 BOM 的 UTF-16 认不出来，而且它"成功"了**。UTF-16LE 的字节
 * 序列 `decode('utf-8')` 不会抛（每个字符的低字节都是合法 ASCII，中间夹一个 0x00），所以 gb18030
 * 那道兜底压根不会触发；带 NUL 的时间戳行匹配不上 `_TIMESTAMP_RANGE`、序号行也过不了
 * `isdigit()`，两个过滤器白跑，最后交出去的仍是一份合法 VTT 头加一串垃圾，**状态码 200**。同一
 * 句话在磁盘上真的存在（那两个文件按 UTF-16 读回来是同一份文本），而界面上那条轨和另外三条长得
 * 一模一样——列着、能点、点下去一个字都没有。
 */
test('外挂字幕的四种编码：GBK 与 UTF-16 真文件走到浏览器变成真 cue，少了 BOM 那一份安静地什么都没有', async ({
  page,
}) => {
  expect(existsSync(SEEDED_FILE), '播种那部不在，复制不出第二部').toBe(true)
  const idsBefore = await videoIds(page)
  const coversBefore = coverFingerprints()
  writeEncodingFixtures()

  const encFiles = [ENC_CLIP_FILE, ENC_GBK_FILE, ENC_UTF16_FILE, ENC_BOMVTT_FILE, ENC_NOBOM_FILE]
  let videoId = 0

  try {
    // ---- 1. 一次真扫描：一部新片 + 四条 sidecar。扫描器只看文件名，四种编码它一视同仁。
    expect(await scanSource(page, 1)).toEqual({
      files_found: 2,
      new_videos: 1,
      subtitles_found: 4,
    })
    const listed = await requestJson<{ items: VideoRow[] }>(page, '/api/videos?page=1&page_size=50')
    const created = listed.items.find((item) => item.title === ENC_PARSED_TITLE)
    expect(created, `扫描没有把 ${ENC_PARSED_TITLE} 变成一行`).toBeDefined()
    videoId = created!.id

    // ---- 2. 四条行都登记上了。后面的地址一律按 filepath 取 id，不按位置取——这一条读的是
    // 编码，不是排序（排序已经由第 22 条那条整表比对签过）。
    const rows = await requestJson<SubtitleRow[]>(page, `/api/videos/${videoId}/subtitles`)
    const idOf = (file: string): string => {
      const target = file.replace(/\\/g, '/')
      const row = rows.find((item) => item.filepath.replace(/\\/g, '/') === target)
      expect(row, `清单里没有 ${target} 这一行`).toBeDefined()
      return `/api/videos/${videoId}/subtitles/${row!.id}/stream`
    }
    expect(rows.map((row) => row.label)).toEqual(['chi', 'eng', 'jpn', 'kor'])
    expect(rows.map((row) => row.language)).toEqual(['zh', 'en', 'ja', 'ko'])

    // ---- 3. 三路识别成功的响应体：整段相等，一个字符都不许差
    const gbk = await fetchInPage(page, idOf(ENC_GBK_FILE))
    expect(gbk.status, gbk.text).toBe(200)
    // `text/vtt; charset=utf-8` 是路由自己声明的；浏览器那条轨拉这份文件时读的就是它。
    expect(gbk.contentType).toBe('text/vtt; charset=utf-8')
    expect(gbk.text).toBe(
      'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n' +
        ENC_CUE_GBK_ONE +
        '\n\n00:00:04.000 --> 00:00:05.000\n' +
        ENC_CUE_GBK_TWO +
        '\n',
    )
    // CRLF 已经折平、序号行已经剥掉，而这两件事发生在使用 GBK 字节的文件上。
    expect(gbk.text).not.toContain('\r')
    expect(gbk.bytes, 'GBK 那一份转出来的 UTF-8 字节数（中文每字三字节，走错编码这个数一定变）').toBe(143)
    // 磁盘上是 136 字节的 GBK，交出去是 143 字节的 UTF-8：这一格挡的是"把原始字节直接回给
    // 浏览器"那种写法——它同样 200、同样一份 VTT 头，界面上一片乱码。
    expect(readFileSync(ENC_GBK_FILE)).toHaveLength(136)

    const utf16 = await fetchInPage(page, idOf(ENC_UTF16_FILE))
    expect(utf16.status, utf16.text).toBe(200)
    // `read_subtitle_text` 里那个「开头是 UTF-16 BOM 就整份按 UTF-16 读」的分支，第一次有用例。
    expect(utf16.text).toBe('WEBVTT\n\n00:00:03.000 --> 00:00:04.000\n' + ENC_CUE_UTF16 + '\n')
    expect(utf16.text).not.toContain(String.fromCharCode(0))

    const bomvtt = await fetchInPage(page, idOf(ENC_BOMVTT_FILE))
    expect(bomvtt.status, bomvtt.text).toBe(200)
    // `.vtt` 那一支是原样交出去（转换一次都不做），所以连 CRLF 都还在；唯一的差别是开头那三个
    // 字节被 `utf-8-sig` 吃掉了。
    expect(bomvtt.text).toBe(ENC_VTT_BODY)
    // 这一格是补出来的：**只比文本看不见那个 BOM**。`fetchInPage` 用 `TextDecoder` 读响应，而
    // 按规范它会把开头的 U+FEFF 丢掉——所以 BOM 留在响应里时 `text` 和 `charCodeAt(0)` 两样都
    // 照样好看（M2 那次实测整条绿，就是这么发现的）。字节数是唯一不骗人的读数：BOM 在就多半
    // 个字节。至于浏览器那一头，M2 也顺手量了：Chromium 拉这份带 BOM 的 VTT 照样解析出 cue，
    // 所以剥 BOM 不是"浏览器放不出来"的闸门，是"交出去的字节就是那份文本"的闸门。
    expect(bomvtt.bytes, '带 BOM 的 VTT 交出去的字节数——BOM 没剥掉的话这里是 +3').toBe(
      Buffer.byteLength(ENC_VTT_BODY, 'utf8'),
    )

    // ---- 4. 现状：没有 BOM 的 UTF-16 认不出来，而且它"成功"了
    const nobom = await fetchInPage(page, idOf(ENC_NOBOM_FILE))
    expect(nobom.status, nobom.text).toBe(200)
    expect(nobom.text.startsWith('WEBVTT\n\n')).toBe(true)
    expect(nobom.text).toContain(String.fromCharCode(0))
    expect(nobom.text).not.toContain(ENC_CUE_UTF16)
    // 同一句话在磁盘上真的存在：这两个文件只差一个 BOM，按 UTF-16 读回来是同一份文本。
    expect(readFileSync(ENC_NOBOM_FILE).toString('utf16le')).toContain(ENC_CUE_UTF16)

    // ---- 5. 界面上：四条轨都列着，三条有词，第四条什么都没有
    // 播放器挂在 `VideoDetail.vue` 的 `v-if="isPlaying"` 下面，先点海报（第 22 条那次的超时）。
    await page.goto(`/videos/${videoId}`)
    await page.locator('.preview-area').click()
    await expect(page.locator('.video-player')).toBeVisible()
    await expect(page.locator('.subtitle-btn')).toBeVisible({ timeout: 20_000 })
    await page.locator('.subtitle-btn').click()
    await expect(page.locator('.subtitle-menu')).toBeVisible()
    await expect(page.locator('.subtitle-menu-group')).toHaveCount(0)
    expect(await subtitleMenuItems(page)).toEqual(['关闭', 'chi', 'eng', 'jpn', 'kor'])

    await page.locator('.subtitle-menu-item', { hasText: 'chi' }).click()
    // cue 是浏览器自己解析出来的 UTF-8 文本：服务器嗅错编码的话这里不会是那三句中文。
    // 第四条的加载状态是 2（=已加载）而不是 3：那份响应合法、只是没有一条 cue，浏览器完全不
    // 觉得有事——和第 22 条第 5 步那个"200 而零条 cue"同一个形状。
    await expect
      .poll(() => trackStates(page), { message: '四种编码的字幕没有都变成浏览器里的 cue' })
      .toEqual([
        { src: idOf(ENC_GBK_FILE), mode: 'showing', elementState: 2, cues: [ENC_CUE_GBK_ONE, ENC_CUE_GBK_TWO] },
        { src: idOf(ENC_UTF16_FILE), mode: 'hidden', elementState: 2, cues: [ENC_CUE_UTF16] },
        { src: idOf(ENC_BOMVTT_FILE), mode: 'hidden', elementState: 2, cues: [ENC_CUE_BOMVTT] },
        { src: idOf(ENC_NOBOM_FILE), mode: 'hidden', elementState: 2, cues: [] },
      ])

    // 现状的后半句：那条读错了编码的轨，界面上和一个正常字幕**完全一样**——菜单里要点开才看得见
    // （`selectTrack` 收尾会把菜单关掉，第 22 条那次的挂起），点下去切得动、字一个没有。
    await page.locator('.subtitle-btn').click()
    await expect(page.locator('.subtitle-menu')).toBeVisible()
    await page.locator('.subtitle-menu-item', { hasText: 'kor' }).click()
    await expect
      .poll(() => trackStates(page), { message: '那条没 BOM 的轨切不上 showing，或者它其实有 cue' })
      .toContainEqual({ src: idOf(ENC_NOBOM_FILE), mode: 'showing', elementState: 2, cues: [] })
    await expect(page.locator('.subtitle-menu-note')).toHaveCount(0)
  } finally {
    // `finally` 里只收场、不抛（#136 的规矩）。
    if (videoId) {
      await fetchInPage(page, `/api/videos/${videoId}`, { method: 'DELETE', headers: CSRF })
    }
    for (const file of encFiles) {
      try {
        rmSync(file, { force: true, maxRetries: 10, retryDelay: 500 })
      } catch {
        // 下一轮起跑的那次 rmtree 兜底
      }
    }
  }

  // 收尾之后才核对（#120 的规矩）。
  expect(await videoIds(page)).toEqual(idsBefore)
  for (const file of encFiles) {
    expect(existsSync(file), file).toBe(false)
  }
  const seededSubtitles = await requestJson<SubtitleRow[]>(page, '/api/videos/1/subtitles')
  expect(seededSubtitles.map((row) => row.filepath.replace(/\\/g, '/'))).toEqual([
    join(MEDIA_DIR, 'e2e_sample.zh.srt').replace(/\\/g, '/'),
  ])
  expect(coverFingerprints()).toEqual(coversBefore)
})
