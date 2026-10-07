import { beforeAll, describe, expect, it } from 'vitest'

import { embeddedSubtitleTrackUrl, subtitleTrackUrl } from '@/api/subtitles'
import { streamUrl, thumbnailUrl } from '@/api/videos'
import { type Recorded, walkApiModules } from './emitted-calls'

/**
 * 这四个函数返回的是浏览器自己去取的地址（封面、播放流、两条字幕轨），一次 axios 都不走。
 * `openapi-contract.spec.ts` 已经把它们对过路由表了 —— 那一层管「这个地址后端到底有没有」。
 *
 * 这里管剩下那一半：**哪个实参落在哪一段**。路由表对这一半是瞎的，两条都不是推测：
 * - `/api/videos/{video_id}/subtitles/{subtitle_id}/stream` 两个参数都声明成 integer，
 *   实参写反仍然命中同一个模板；
 * - 把详情页的流地址改成封面地址（实测的变异 ⑥）也仍然是一条已声明的路由，
 *   对表核对全绿，页面只会安静地把一张 jpg 当视频播。
 *
 * 所以断言用的是**互不相等的哨兵值**，把它钉成一句具体地址，而不是形状或者命中模板。
 *
 * #149 之前这张表是**只按名字手写**的，于是它有第二种失效方式：`src/api/` 里新添一个返回字符串
 * 的构造器，遍历器会记到它（`viaClient === false`）、路由表那层会对上它（模板存在就绿）、
 * 形状与替身那两层也照绿，**只有"槽位归属"这一层根本不知道它存在**。实测：往 `videos.ts`
 * 加一个 `tempSubtitleUrl` 复用那条已声明的字幕轨模板，`tests/api/` 的 11 份文件 50 条全绿。
 * 所以下面多了一条钉子：这张哨兵表的键集必须**等于**遍历器记到的构造器集合——少钉一条红，
 * 多钉一条（构造器被删掉而表没跟着改）也红。表本身仍然是人写的，这是故意的：要的就是
 * "新构造器必须有人为它算一句期望地址"这一步，自动化把它代掉就等于把这一层又变回空转。
 */

interface Pin {
  /** `videos.ts#thumbnailUrl`，和遍历器补记的那一条同一个键。 */
  key: string
  /** 拿互不相等的哨兵实参（11 / 22）叫起来得到的那一句。 */
  actual: string
  /** 人算出来的期望地址：红了就知道实参落错了哪一段。 */
  expected: string
}

const pins: Pin[] = [
  {
    key: 'videos.ts#thumbnailUrl',
    actual: thumbnailUrl(11),
    expected: '/api/videos/11/thumbnail',
  },
  {
    key: 'videos.ts#streamUrl',
    actual: streamUrl(11),
    expected: '/api/videos/11/stream',
  },
  {
    key: 'subtitles.ts#subtitleTrackUrl',
    actual: subtitleTrackUrl(11, 22),
    expected: '/api/videos/11/subtitles/22/stream',
  },
  {
    key: 'subtitles.ts#embeddedSubtitleTrackUrl',
    actual: embeddedSubtitleTrackUrl(11, 22),
    expected: '/api/videos/11/subtitles/embedded/22/stream',
  },
]

function shortKey(record: Recorded): string {
  return `${record.module.split('/').pop()}#${record.name}`
}

let recorded: string[] = []

beforeAll(async () => {
  const calls = await walkApiModules()
  recorded = calls.filter((call) => !call.viaClient).map(shortKey)
})

describe('browser-side URL builders', () => {
  it('has builders to pin', () => {
    // 空集合不报错，它只是绿：这张表被清空、遍历器那一半同时静默失效时，下面每条都会空跑。
    expect(pins.length).toBeGreaterThanOrEqual(4)
  })

  for (const pin of pins) {
    it(`puts the sentinels where ${pin.key} says they belong`, () => {
      expect(pin.actual).toBe(pin.expected)
    })
  }

  it('pins exactly the builders the walker records', () => {
    const unpinned = recorded.filter((key) => !pins.some((pin) => pin.key === key))
    const stale = pins.filter((pin) => !recorded.includes(pin.key)).map((pin) => pin.key)
    expect(
      { unpinned: unpinned.sort(), stale: stale.sort() },
      '哨兵表与遍历器记到的构造器必须一一对应：新构造器要有人为它算一句期望地址，删掉的要从表里一起删',
    ).toEqual({ unpinned: [], stale: [] })
  })
})
