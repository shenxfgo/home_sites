import type { Page, Route } from '@playwright/test'
import { beforeAll, describe, expect, it } from 'vitest'

import { mockApi } from '../../e2e/fixtures'
import { moduleKeys, sampleArgKeys, walkApiModules, type Recorded } from './emitted-calls'

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
function drive(handler: (route: Route) => unknown, call: Recorded): Answer | undefined {
  let answer: Answer | undefined
  const route = {
    request: () => ({
      url: () => `${HERE}${call.url}`,
      method: () => call.method,
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

function label(call: Recorded): string {
  return `${call.module.replace('../../src/api/', '')}#${call.name}  ${call.method} ${call.url}`
}

const calls: Recorded[] = []
/** 每条地址各自的答案，键是它在 `calls` 里的下标。 */
const answers: Array<Answer | undefined> = []

beforeAll(async () => {
  calls.push(...(await walkApiModules()))
  // 一份夹具只服务一条地址。这不是洁癖：夹具里 `POST /auth/logout` 会把 `signedIn` 翻回 false，
  // 而遍历顺序是模块名排序，`auth` 排第一——实测共用一份时后面六十条全被替身的默认拒绝拦成
  // 401，兜底那句一次也没执行到，"没有缺分支"那条规则演成一份全绿的空守卫。
  for (const call of calls) answers.push(drive(await installStub(), call))
})

describe('stub fixtures against the addresses the app emits', () => {
  it('walks the same set of modules as the route-table guard', () => {
    // 两份守卫共用一份遍历器，但"共用"这件事本身也得钉住：glob 走错目录时这里会变成
    // 零条地址、零条违规的一份空测试（#121 的教训）。实测 14 份模块共 76 条地址。
    expect(moduleKeys.length).toBeGreaterThanOrEqual(12)
    expect(calls.length).toBeGreaterThanOrEqual(74)
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
