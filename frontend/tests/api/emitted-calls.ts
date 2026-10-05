import client from '@/api/client'

/**
 * 前端**真会发出去的每一条地址**——三份静态守卫共用的那一半遍历器。
 *
 * 为什么要共用：#121（形状）、#122（对路由表核对）和 #128（对替身夹具核对）问的是同一个集合的
 * 三种性质——「原文像不像一条路径」「后端有没有这条路由」「替身接不接得住这条地址」。各自抄一份
 * 遍历器的话，几份会漂：#124 给构造器补记的那一段只写在其中一份里的话，另两份就静默少四条地址，
 * 而"少了几条"在测试里从来不报错，只是绿。所以遍历器只有一份。
 *
 * 拿法是不 mock：把 `client.defaults.adapter` 换成记录器，axios 自己先把 `baseURL + url`
 * 拼成完整地址，所以拿到的是浏览器真正请求的那一句 `/api/...`（`config.url` 到适配器这里
 * 还没拼前缀，实测是 `/videos/new`，所以要走 `client.getUri(config)`；原文也一并记下来，
 * 给 #121 那三条形状规则用）。
 *
 * 模块清单从文件系统推导，不手写——#121 的教训：手写 `MODULES` 那份声称"遍历所有 api 模块"，
 * 实际只有 8 份，漏掉的连双前缀护栏都没有。glob 让"漏一份"在结构上不可能。
 */

export interface Recorded {
  method: string
  /** axios 自己拼出来的完整请求地址（`client.getUri`），带 `/api` 前缀与查询串。 */
  url: string
  /** 写代码的那个人交给 axios 的那一段（`config.url`），也就是**没拼前缀**的原文。 */
  rawUrl: string
  query: string[]
  /** `../../src/api/videos.ts` 这种 glob 键，红了能直接说出是谁的 URL。 */
  module: string
  /** 导出名；挂在对象上的方法（`notificationsApi.list`）取方法名。 */
  name: string
  /** 这条是 axios 真发出去的，还是只返回字符串的构造器补记的。 */
  viaClient: boolean
}

const loaders = import.meta.glob('../../src/api/*.ts')

/** 除 `client.ts`（它就是那个 axios 实例本身）之外的全部请求模块。 */
export const moduleKeys: string[] = Object.keys(loaders)
  .filter((key) => !key.endsWith('client.ts'))
  .sort()

/**
 * 遍历器给每个函数都传同一组实参，而绝大多数函数的路径参数是数字，`1` 就够用。
 * 少数几条不是：它们的实参形状会**改变地址的形状**，用 `1` 凑出来的那句不是前端会发出的地址，
 * 拿去核对替身就会红在脚手架上而不是界面行为上。所以这几条单独登记，键是「模块名#导出名」。
 *
 * - `revokeSession(tokenHash)`：后端和替身都只认 64 位十六进制（`Path(pattern=…)`，#126 那条），
 *   `/auth/sessions/1` 是个真后端根本收不到的地址。
 * - `getSetting(key)` / `updateSetting(key, value)`：键名是字符串，走 `SYSTEM_SETTING_KEYS` 白名单。
 *
 * 这份登记表的键必须都能在遍历里走到，见 `stub-coverage.spec.ts` 里那条"没有陈年样本"的规则。
 */
const SAMPLE_ARGS: Record<string, unknown[]> = {
  'auth.ts#revokeSession': ['f'.repeat(64)],
  'settings.ts#getSetting': ['auto_scan_interval'],
  'settings.ts#updateSetting': ['auto_scan_interval', '3600'],
}

export const sampleArgKeys = Object.keys(SAMPLE_ARGS)

/** 每次请求都记录，并回一个"任何属性都是空数组"的响应，让 `.then(r => r.data.items)` 之类走得通。 */
const anyData = new Proxy(
  {},
  {
    get: () => [],
  },
)

function queryNames(url: string): string[] {
  return (url.split('?')[1] ?? '')
    .split('&')
    .filter(Boolean)
    // 遍历器塞进去的 `{dummy:true}` 落在查询位时，axios 会序列化成
    // `page_size%5Bdummy%5D=true`。查询名仍然是 `page_size`，所以只剪掉后面那段，
    // 不能整条丢掉——丢了就把"查询名拼错"这一类一起放过去了（#122 实测变异 ③ 因此演成绿的）。
    .map((pair) => pair.split('=')[0].split('%5B')[0])
}

/**
 * 走一遍全部模块，返回它们发出的每条地址（含只返回字符串的那几个构造器）。
 *
 * 适配器在函数内部装上、返回前复原，所以几份守卫各走各的、互不影响，也不会有"遍历过一次之后
 * 整个文件的 axios 都还在被记录"这种跨用例泄漏。
 */
export async function walkApiModules(): Promise<Recorded[]> {
  const calls: Recorded[] = []
  const originalAdapter = client.defaults.adapter
  let currentModule = ''
  let currentName = ''

  client.defaults.adapter = (config) => {
    // 遍历器给每个函数都传 `(1, 2, 3)`（或登记表里那几条的样本），于是"第一个参数是查询对象"
    // 的那几个（`listVideos(params)`）会拿到 `params: 1`；axios 序列化非对象查询串会直接抛
    // `target must be an object`。那是测试脚手架的产物而不是界面行为，这里丢掉它，
    // 代价是这几个函数的查询名在本测试里没有签名（见 openapi-contract 文件末的说明）。
    const params = config.params && typeof config.params === 'object' ? config.params : undefined
    const url = client.getUri({ ...config, params })
    calls.push({
      method: String(config.method ?? 'get').toUpperCase(),
      url,
      rawUrl: String(config.url ?? ''),
      query: queryNames(url),
      module: currentModule,
      name: currentName,
      viaClient: true,
    })
    return Promise.resolve({ data: anyData, status: 200, statusText: 'OK', headers: {}, config })
  }

  try {
    for (const key of moduleKeys) {
      currentModule = key
      const apiModule = (await loaders[key]()) as Record<string, unknown>
      const shortName = key.split('/').pop() ?? key
      for (const [exportName, value] of Object.entries(apiModule)) {
        const members =
          typeof value === 'function'
            ? [[exportName, value] as const]
            : value && typeof value === 'object'
              ? Object.entries(value as Record<string, unknown>).filter(
                  ([, item]) => typeof item === 'function',
                )
              : []
        for (const [name, member] of members) {
          const args = SAMPLE_ARGS[`${shortName}#${name}`] ?? [1, 2, 3]
          currentName = name
          const returned = await (member as (...rest: unknown[]) => unknown)(...args)
          // 浏览器自己取地址的那几个函数（`<img>`/`<video>`/`<track>` 的 src）只返回字符串，
          // 一次 axios 都不走，所以适配器记不到它们 —— #122 承认的那半盲区。这里按它们
          // 在浏览器里的真实方法（GET）补记一条，让三份守卫（形状 / 路由表 / 替身）也能管到。
          if (typeof returned === 'string' && returned.startsWith('/')) {
            calls.push({
              method: 'GET',
              url: returned,
              rawUrl: returned,
              query: queryNames(returned),
              module: key,
              name,
              viaClient: false,
            })
          }
        }
      }
    }
  } finally {
    client.defaults.adapter = originalAdapter
  }
  return calls
}
