import { beforeAll, describe, expect, it } from 'vitest'

import { moduleKeys, walkApiModules, type Recorded } from './emitted-calls'

/**
 * `src/api/` 的形状规则——这一层看的是**写代码的人交出去的那一段路径**（`config.url`，
 * 还没拼 baseURL），所以它管得住另外两层管不到的东西：
 * - 把 baseURL 已经带的 `/api` 又写一遍（`/api/videos` → 实际请求 `/api/api/videos`）——#10 那一类；
 * - 相对路径（`videos/${id}`），那样 `baseURL` 就白配了；
 * - 多写一个 `/`（`/sources/${id}/` + `/scan`）或结尾斜杠，浏览器眼里那是另一个地址。
 *
 * `openapi-contract.spec.ts` 拿完整地址对路由表，`stub-coverage.spec.ts` 拿完整地址对替身夹具，
 * 这一份拿原文对形状——三份共用 `emitted-calls.ts` 那一个遍历器，所以"漏一份模块"在结构上不可能，
 * 也不会出现两边各抄一份遍历、一边加了地址另一边静默少一条（#121/#122 的教训）。
 */

const calls: Recorded[] = []

beforeAll(async () => {
  calls.push(...(await walkApiModules()))
})

/** 只有走 axios 的那几条才有"原文"；构造器返回的就是浏览器要取的完整地址，本来就带 `/api`。 */
function authored(): Recorded[] {
  return calls.filter((call) => call.viaClient)
}

function short(call: Recorded): string {
  return `${call.module.replace('../../src/api/', '')}#${call.name}  ${call.rawUrl}`
}

describe('api request paths', () => {
  it('exercise every exported api function', () => {
    // glob 什么都没匹配到时，这份测试会变成一份什么都不做的绿——先把清单本身钉住。
    expect(moduleKeys.length).toBeGreaterThanOrEqual(12)
    // 空的那一份 = 这份模块里的函数没有一个真正打到 client（改成了不请求、或者整个模块
    // 被 rewrite 成走缓存）。只看总数测不到它：14 份实测共 72 次，整份停掉也还剩 71 次。
    const silent = moduleKeys.filter(
      (key) => !authored().some((call) => call.module === key),
    )
    expect(silent).toEqual([])
    expect(authored().length).toBeGreaterThan(40)
  })

  it('never repeat the /api prefix that the axios instance already carries', () => {
    const doubled = authored().filter((call) => call.rawUrl.startsWith('/api'))
    expect(doubled.map(short)).toEqual([])
  })

  it('keeps every path absolute so the baseURL stays meaningful', () => {
    const relative = authored().filter((call) => !call.rawUrl.startsWith('/'))
    expect(relative.map(short)).toEqual([])
  })

  it('keeps one separator per join: no // and no trailing slash', () => {
    // 拼路径时多写一个 `/`（`/sources/${id}/` + `/scan`）在浏览器里是个新地址，会打到
    // 前缀中间去；尾斜杠同样是另一条路由。真库里没人点过的组合只有这条静态钉子挡得住。
    const malformed = authored().filter(
      (call) => call.rawUrl.includes('//') || call.rawUrl.endsWith('/'),
    )
    expect(malformed.map(short)).toEqual([])
  })
})
