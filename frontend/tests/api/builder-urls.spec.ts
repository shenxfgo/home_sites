import { describe, expect, it } from 'vitest'

import { embeddedSubtitleTrackUrl, subtitleTrackUrl } from '@/api/subtitles'
import { streamUrl, thumbnailUrl } from '@/api/videos'

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
 */
describe('browser-side URL builders', () => {
  it('puts the video id in the video slot of the cover address', () => {
    expect(thumbnailUrl(11)).toBe('/api/videos/11/thumbnail')
  })

  it('puts the video id in the video slot of the stream address', () => {
    expect(streamUrl(11)).toBe('/api/videos/11/stream')
  })

  it('keeps the sidecar subtitle id out of the video slot', () => {
    expect(subtitleTrackUrl(11, 22)).toBe('/api/videos/11/subtitles/22/stream')
  })

  it('keeps the embedded stream index out of the subtitle id slot', () => {
    expect(embeddedSubtitleTrackUrl(11, 22)).toBe(
      '/api/videos/11/subtitles/embedded/22/stream',
    )
  })
})
