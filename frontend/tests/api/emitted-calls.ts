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
    // `target must be an object`。那是测试脚手架的产物而不是界面行为，这里丢掉它。
    // 这一类函数的查询名由下面那趟哨兵探测（`querySurfaces`）签名，不靠这里。
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

/**
 * 查询面：那些「第一个参数就是查询对象、原样交给 axios」的请求函数。
 *
 * 为什么要单独走一趟：这类函数的查询名**不写在 `src/api/` 里**，它们来自调用方（`Home.vue` 按
 * 筛选状态拼 `{page, page_size, source_id, tag_id, search}`），而声明在参数类型接口上。上面那趟
 * 遍历给它们塞的是 `1`，序列化不了就丢掉，于是 `/api/videos` 那句查询串在这三份守卫里是空的——
 * #122/#124 各自记下的那半盲区。
 *
 * 症状不是报错。实测（一次性探针，跑完即删）：`GET /api/videos?searsh=abc` 回 **200**，返回的是
 * **没筛过**的第一页。FastAPI 只把它声明过的查询参数绑进函数签名，没声明的连 `request.query_params`
 * 都没人读（全仓 grep 无一处），所以查询名拼错 = 筛选无声失效。
 *
 * 认「谁是查询转发函数」用的是**哨兵探测**而不是读代码的形状：把一个只含 `PROBE_KEY` 的对象塞进
 * 每一位参数，真发出去的地址里出现这个键，就说明这一位会原样落到查询串上。这是问函数本身，不是猜
 * 它怎么写——`{ params }` 简写、`{ params: xxx }`、`{ ...extra }` 摊平，形状全都不重要。
 */
export interface QuerySurface {
  /** `videos.ts` 这种短名。 */
  module: string
  name: string
  /** 第一个参数的类型标注（`VideoQueryParams`）；红了要说清去哪个接口读键。 */
  paramType: string
  /** 从那个接口里读出来的查询名；空数组意味着读不到，由守卫判红而不是放过。 */
  keys: string[]
  /** 把整套键交给这个函数之后，浏览器真会发出去的那句地址。 */
  url: string
  /** 那句地址里的查询名（用来核对「我发出去的就是我声明的那一套」）。 */
  emitted: string[]
}

const PROBE_KEY = '__qprobe__'

const rawApiSources = import.meta.glob('../../src/api/*.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const rawTypeSources = import.meta.glob('../../src/types/*.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** 函数第一个参数的类型名——查询键就声明在它身上。 */
function firstParamType(moduleKey: string, fnName: string): string | undefined {
  const source = rawApiSources[moduleKey]
  if (!source) return undefined
  // 工作区里这些文件是 CRLF（#127/#131 量过），`\s` 一并吃掉 `\r`，`\S` 不吃，所以这里只用 `\s`。
  const re = new RegExp(
    `function\\s+${fnName}\\s*\\(\\s*[A-Za-z_$][\\w$]*\\s*:\\s*([A-Za-z_$][\\w$]*)`,
  )
  return re.exec(source)?.[1]
}

/** 具名接口顶层的字段名。这些接口都是平铺的，所以两个空格开头、带冒号的那一行就是一个键。 */
function interfaceFields(iface: string): string[] {
  for (const source of Object.values(rawTypeSources)) {
    // `[\s\S]` 而不是 `\S`/`.`：接口体里有换行和缩进，而 `.` 不吃 `\n`（#139 那条教训的反面——
    // 这里的锚 `\n}` 本身要跨过 CRLF 的 `\r`，所以体段只能整段吞下）。
    const block = new RegExp(`export interface ${iface} \\{([\\s\\S]*?)\\n\\}`).exec(source)
    if (!block) continue
    return [...block[1].matchAll(/^[ \t]+([A-Za-z_$][\w$]*)\??:/gm)].map((m) => m[1])
  }
  return []
}

export async function querySurfaces(): Promise<QuerySurface[]> {
  const surfaces: QuerySurface[] = []
  const originalAdapter = client.defaults.adapter
  let sink: Recorded[] = []
  let currentModule = ''
  let currentName = ''

  client.defaults.adapter = (config) => {
    const params = config.params && typeof config.params === 'object' ? config.params : undefined
    const url = client.getUri({ ...config, params })
    sink.push({
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
          const fn = member as (...rest: unknown[]) => unknown
          const base = SAMPLE_ARGS[`${shortName}#${name}`] ?? [1, 2, 3]
          currentName = name
          // 哨兵探测：逐位替换（位数拿不到——`params = {}` 这种带默认值的函数 `.length` 是 0，
          // 所以按登记表那三位一路探过去，够覆盖本仓所有形状）。
          for (let slot = 0; slot < base.length; slot++) {
            const probeArgs = [...base]
            probeArgs[slot] = { [PROBE_KEY]: 'on' }
            sink = []
            try {
              await fn(...probeArgs)
            } catch {
              // 参数形状不合它的心意（比如把对象递给要 `string` 的模板）——那就不是查询转发，跳过。
              // 探的是「我的对象有没有落到查询串上」，函数在拿到对象时抛异常本身就是答案：没有。
            }
            if (!sink.some((call) => call.query.includes(PROBE_KEY))) continue
            const paramType = firstParamType(key, name)
            const keys = paramType ? interfaceFields(paramType) : []
            const fullArgs = [...base]
            fullArgs[slot] = Object.fromEntries(keys.map((k) => [k, '1']))
            sink = []
            await fn(...fullArgs)
            const call = sink[0]
            surfaces.push({
              module: shortName,
              name,
              paramType: paramType ?? '（读不到第一个参数的类型名）',
              keys,
              url: call?.url ?? '',
              emitted: call ? call.query.filter((q) => q !== PROBE_KEY) : [],
            })
          }
        }
      }
    }
  } finally {
    client.defaults.adapter = originalAdapter
  }
  return surfaces
}
