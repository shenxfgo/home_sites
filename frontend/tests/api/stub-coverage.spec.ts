import type { Page, Route } from '@playwright/test'
import { beforeAll, describe, expect, it } from 'vitest'

import { mockApi } from '../../e2e/fixtures'
import { moduleKeys, sampleArgKeys, walkApiModules, type Recorded } from './emitted-calls'
import { concretize, declaredOperations, templateFor } from './openapi-schema'

/**
 * 替身夹具必须接得住前端会发出的**每一条**地址。
 *
 * 起因是 #120 的一次偶然：写「我的设备」那条用例时才发现 `e2e/fixtures.ts` 里根本没有
 * `/api/auth/sessions` 的分支，而此前 82 条替身 e2e 全绿——因为**没有任何一条界面用例请求过
 * 那个地址**，兜底那句 `未预置的接口` 一次也没被执行到。缺分支不会红，只会静默把 500 交给界面；
 * 哪天有视图开始请求它，拿到的就是替身编出来的假 500，而不是"这个地址没预置"。
 *
 * 现在地址集合由 `emitted-calls.ts` 遍历 `src/api/*.ts` 得到（和 #122 对路由表核对的是**同一批**），
 * 逐条喂给夹具里那个真的 `page.route` 处理函数，断言任何一条都不落到 `未预置的接口` 那句兜底上。
 *
 * 为什么不复制一份匹配器：复制就只能保证"我抄的这份匹配器"和夹具一致，而真正的失效方式是夹具
 * 改了、守卫没跟着改。所以这里 `import { mockApi }` ——假 `page` 接住它注册的那个处理函数，假
 * `route`/`request` 驱动它，答出来的状态码就是替身用例真会看到的那个。
 *
 * #235 起同一套驱动反着再用一遍：正向问「界面发的每条地址夹具接不接得住」，反向问「夹具接得住
 * 的每条地址界面还发得出吗」。方向换了，判据一个字没改（还是那句 `未预置的接口` 兜底），只是
 * 地址的来源从遍历器换成 `backend/openapi.json` 的操作清单——理由和上面同一条：夹具的匹配器是
 * 动态的，静态抄一份分支清单只会变成「我抄的那份」。这一格的价值在 #232 当场量到过：那单删掉
 * 七条零调用方的封装，替身夹具里对应的七条分支一行没动、107 条替身 e2e 全绿——「界面不再需要
 * 它」这件事在这个仓库里原先没有任何一面会说话。
 */

/** 夹具里那五处兜底共用的一句暗号（`未预置的接口: METHOD /path`）。 */
const UNDEFINED = '未预置的接口'
/** 替身的默认拒绝与会话中间件同形，未登录时业务接口一律 401，那条规则会盖住兜底，所以要先登录。 */
const HERE = 'http://localhost:4173'

interface Answer {
  status: number
  body: string
}

/**
 * 装一次替身，返回它注册的那个 `/api` 处理函数。
 *
 * 每条地址都重新装一遍：夹具是有状态的（`removedVideos`、`readNotifications`、转码状态机…），
 * 复用一份的话"第 20 条地址得到的答案"取决于第 19 条发过什么，而那个先后顺序是测试编出来的，
 * 不是界面的顺序。重装一次只要 1 毫秒，换来每条地址各自独立。
 */
async function installStub(): Promise<(route: Route) => unknown> {
  let handler: ((route: Route) => unknown) | undefined
  const page = {
    route: async (_matcher: unknown, registered: (route: Route) => unknown) => {
      handler = registered
    },
  } as unknown as Page
  await mockApi(page, { signedIn: true })
  if (!handler) throw new Error('替身夹具没有注册任何 /api 路由处理函数')
  return handler
}

/**
 * 驱动一次地址，返回夹具答出来的状态码与响应体。
 *
 * `postData()` 一律回 `{}`：守卫问的是「这个地址有没有分支接得住」，不是「请求体对不对」。
 * 夹具里所有按请求体行事的分支（建号、改偏好、启动转码）都带默认值或 typeof 闸门，空对象走得通。
 */
function driveUrl(
  handler: (route: Route) => unknown,
  method: string,
  url: string,
): Answer | undefined {
  let answer: Answer | undefined
  const route = {
    request: () => ({
      url: () => `${HERE}${url}`,
      method: () => method,
      postData: () => '{}',
      headers: () => ({ 'user-agent': 'stub-coverage-guard' }),
    }),
    fulfill: (response: { status?: number; body?: unknown }) => {
      answer = { status: response.status ?? 200, body: String(response.body ?? '') }
      return Promise.resolve()
    },
  } as unknown as Route
  void handler(route)
  return answer
}

function drive(handler: (route: Route) => unknown, call: Recorded): Answer | undefined {
  return driveUrl(handler, call.method, call.url)
}

function label(call: Recorded): string {
  return `${call.module.replace('../../src/api/', '')}#${call.name}  ${call.method} ${call.url}`
}

const calls: Recorded[] = []
/** 每条地址各自的答案，键是它在 `calls` 里的下标。 */
const answers: Array<Answer | undefined> = []

/**
 * 反向那一半的探针：路由表上每条操作具体化成一句真地址，喂给夹具。
 *
 * 为什么不静态枚举夹具的分支：夹具的匹配器是动态的（前缀判断 + 正则 + `MEMBER_WRITE` 白名单），
 * 从源码里抄一份「有哪些分支」得到的清单只保证"我抄的和夹具今天一致"，而失效方式正是夹具改了、
 * 抄的那份没改——`openapi-schema.ts` 顶部记的同一个理由。所以反向只能**驱动**：拿 openapi 的
 * 操作清单（后端声明的全部地址）逐条问夹具「这句你答不答」，答出来的不是那句兜底就是有分支。
 */
interface Probe {
  /** 大写动词，和 `Recorded.method` 同一口径，好和正向那批直接对键。 */
  method: string
  template: string
  url: string
  /** 非空意味着脚手架够不着这条操作——它不会被算成「没分支」，而是本单自己的洞。 */
  problem: string | undefined
  answer: Answer | undefined
}

const ops = declaredOperations()
const probes: Probe[] = []
/** 前端今天真发得出的地址，键是 `METHOD 模板`。 */
const emitted = new Set<string>()

/** 夹具对这条操作有分支：答了，而且答的不是那句 `未预置的接口`。 */
function hasABranch(probe: Probe): boolean {
  return probe.answer !== undefined && !probe.answer.body.includes(UNDEFINED)
}

function probeKey(probe: Probe): string {
  return `${probe.method} ${probe.template}`
}

beforeAll(async () => {
  calls.push(...(await walkApiModules()))
  // 一份夹具只服务一条地址。这不是洁癖：夹具里 `POST /auth/logout` 会把 `signedIn` 翻回 false，
  // 而遍历顺序是模块名排序，`auth` 排第一——实测共用一份时后面六十条全被替身的默认拒绝拦成
  // 401，兜底那句一次也没执行到，"没有缺分支"那条规则演成一份全绿的空守卫。
  for (const call of calls) answers.push(drive(await installStub(), call))
  for (const call of calls) {
    emitted.add(`${call.method} ${templateFor(call.url, call.method) ?? '（命不中任何模板）'}`)
  }

  for (const op of ops) {
    const concretized = concretize(op)
    const method = op.method.toUpperCase()
    if (!concretized.ok) {
      probes.push({
        method,
        template: op.template,
        url: '',
        problem: concretized.problem,
        answer: undefined,
      })
      continue
    }
    probes.push({
      method,
      template: op.template,
      url: concretized.url,
      problem: undefined,
      answer: driveUrl(await installStub(), method, concretized.url),
    })
  }
})

describe('stub fixtures against the addresses the app emits', () => {
  it('walks the same set of modules as the route-table guard', () => {
    // 两份守卫共用一份遍历器，但"共用"这件事本身也得钉住：glob 走错目录时这里会变成
    // 零条地址、零条违规的一份空测试（#121 的教训）。#232 删掉七条封装后实测 70 条地址。
    expect(moduleKeys.length).toBeGreaterThanOrEqual(12)
    // #233 起总数钉死在实测值（另一处在 `openapi-contract.spec.ts`）：留余量时"glob 少吃到一份
    // 模块"和"按模块核对"会一起看不见那一格（#232 电池 A1）。
    expect(calls.length).toBe(70)
  })

  it('keeps the registered sample arguments alive', () => {
    // 少数几条地址的形状取决于实参（64 位令牌、设置键名），遍历器为它们登记了样本。
    // 登记表不能变成陈账：函数改名或被删掉之后，那份样本对应的就不再是界面会发的地址了。
    const emitted = new Set(calls.map((call) => `${call.module.split('/').pop()}#${call.name}`))
    expect(sampleArgKeys.filter((key) => !emitted.has(key))).toEqual([])
  })

  it('answers every address instead of leaving it unanswered', () => {
    // 兜底之外还有一类失效：分支走到了却一次 `fulfill` 都没调（在真浏览器里是永久挂起，
    // 这里是根本没有答案）。不钉这一条，"没答"会被下面那句兜底规则一起放过。
    const silent = calls
      .filter((_, index) => answers[index] === undefined)
      .map((call) => label(call))
    expect(silent).toEqual([])
  })

  it('never reaches the 未预置的接口 fallback', () => {
    // 先配对再筛：`.filter(...).map((call, index) => answers[index])` 里的那个 index 是
    // **筛过之后**新数组的下标，不是 `calls` 的下标——真缺一条分支时会把另一条地址的响应体
    // 打上去（实测变异 ① 就这么干过：点名了 `GET /api/tags/1/videos`，配的却是登录那一条的 body）。
    const missing = calls
      .map((call, index) => ({ call, answer: answers[index] }))
      .filter(({ answer }) => answer?.body.includes(UNDEFINED))
      .map(({ call, answer }) => `${label(call)} → ${answer?.body}`)
    expect(missing).toEqual([])
  })

  it('walks them as a signed-in owner', () => {
    // 自检那批地址是"登录着的 owner"在走的：忘了这点时业务接口会整批 401（替身的默认拒绝），
    // 兜底那句一次也执行不到，上面两条规则就演成一份空守卫——而它看起来是全绿的。
    // 这一条不是假想敌：共用一份夹具的那版写法就是被它当场拦下来的。
    const unauthorized = calls
      .map((call, index) => ({ call, answer: answers[index] }))
      .filter(
        ({ call, answer }) =>
          !call.url.startsWith('/api/auth/') &&
          (answer?.status === 401 || answer?.status === 403),
      )
      .map(({ call, answer }) => `${label(call)} → ${answer?.status} ${answer?.body}`)
    expect(unauthorized).toEqual([])
  })
})

describe('the reverse direction: fixture branches the app never drives', () => {
  it('reaches every operation on the route table', () => {
    // 反向这条规则的成立前提是「我把路由表上每一条操作都问到了夹具」。这三格各钉一种失效：
    // 表读错（`ops`）、枚举形状变了（`probes` 对不上 `ops`）、参数具体化器够不着新参数形状
    // （`problems`）——后一种尤其不能放过，具体化不了的那条既不会算「有分支」也不会算「没人发」，
    // 于是它从这一面**静默消失**，而规则照样全绿。这是本仓第四次踩在「空匹配集不报错，只是绿」上。
    //
    // 实测 85 条操作里 7 条落在兜底上（`/api/scan/{progress,stop}`、`/api/scheduler` 那四条、
    // `/health`）。它们不是这一面的违规：夹具压根没分支，谈不上「接得住却没人发」。`/health`
    // 连 `/api` 前缀都没有，真浏览器里 `page.route` 的那个匹配器就收不到它；这里直接驱动处理函数
    // 时它一路走到最后一句兜底，所以口径一致，不需要给它单独的豁免。
    expect(ops.length).toBe(85)
    expect(probes.length).toBe(ops.length)
    expect(probes.filter((probe) => probe.problem).map((probe) => probe.problem)).toEqual([])
  })

  it('asks the fixture about every address the app emits', () => {
    // 反向这面真问到了多少条有分支的地址：85 条操作减去上面那 7 条兜底 = 78 条，减去 #235
    // 删掉的 8 条死分支 = **70 条**，和正向那批 `calls.length` 的 70 是同一批地址的两个方向。
    // 钉死它（#233 的同一个口径）：夹具哪天整体失灵、85 条全落到兜底上，这一格先红，
    // 下面那条「没人发的分支」就不会演成一份空规则。
    expect(probes.filter(hasABranch).length).toBe(70)
  })

  it('has no branch the app cannot reach', () => {
    // 夹具接得住、前端一条也发不出 → 红。#232 删掉七条零调用方的封装时，替身夹具里那七条分支
    // 一行没动、107 条替身 e2e 全绿——「界面不再需要它」这件事在这个仓库里没有任何一面会说话。
    // 面板 ② 问的就是要不要补这一句，用户答甲：守卫 + 删分支。
    //
    // 对的是**模板**而不是具体地址：遍历器给 `getVideo(1)` 的是种子 `1`，而具体化器给
    // `/api/videos/{video_id}` 的也是 `1`，这两者今天恰好相等；但 `getSubtitle(1, 2)` 发的是
    // `/api/videos/1/subtitles/2`，具体化出来的是 `/api/videos/1/subtitles/1`——直接比字符串会把
    // 有人发的地址算成没人发。命中的模板由 `templateFor` 判，和正向核对路由表用的是同一个函数。
    const dead = probes.filter((probe) => hasABranch(probe) && !emitted.has(probeKey(probe)))
    expect(dead.map((probe) => `${probeKey(probe)} → ${probe.answer?.status} ${probe.url}`)).toEqual(
      [],
    )
  })
})
