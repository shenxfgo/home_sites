import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterAll, beforeEach, describe, expect, it } from 'vitest'

import client from '@/api/client'

/**
 * 前端 URL 对着后端真实路由表核对——补上 `paths.spec.ts` 那一层看不见的东西。
 *
 * `paths.spec.ts` 用 `vi.mock('@/api/client')`，只看得到传进 axios 的那段相对路径，因此只能验
 * 形状。这里不 mock，而是把 `client.defaults.adapter` 换成记录器：axios 自己先把 `baseURL + url`
 * 拼成完整地址，所以拿到的是真会发出去的 `/api/...`，再逐条对照 `backend/openapi.json` 的路径
 * 模板与方法。段名拼错（`/auth/session` 少一个 `s`）在这里会一个候选模板都没有，而形状规则
 * 完全放它过去——那正是 #121 承认钉不住的一类。
 *
 * #124 起，遍历器还记 `src/api/` 里那几个**只返回字符串**的构造器：`<img>`/`<video>`/`<track>`
 * 的 src 走的就是它们，一次 axios 都不经过，所以适配器那条路子天生看不见。现在它们按 GET
 * 对同一张路由表核对。此前这一半是彻底的盲区——实测改坏 `subtitles/embedded/` 或详情页的
 * 流地址，31 份测试全绿。
 *
 * 这份 schema 由 `python -m src.export_openapi` 生成，`backend/tests/test_openapi_snapshot.py`
 * 保证它与代码一致。两半缺一条都不成立。
 */

interface ParameterObject {
  name: string
  in: string
  schema?: { type?: string }
}

interface OperationObject {
  parameters?: ParameterObject[]
}

interface PathItem {
  parameters?: ParameterObject[]
  get?: OperationObject
  post?: OperationObject
  put?: OperationObject
  delete?: OperationObject
  patch?: OperationObject
}

interface OpenApiSchema {
  paths: Record<string, PathItem>
}

// jsdom 环境里 `new URL(..., import.meta.url)` 返回的是 jsdom 的 URL 实例，
// `readFileSync` 认不出它的 `file:` scheme（实测 `ERR_INVALID_URL_SCHEME`），所以走
// fileURLToPath + path.resolve 这条纯 Node 的路。
const schemaPath = resolve(dirname(fileURLToPath(import.meta.url)), '../../../backend/openapi.json')

const schema = JSON.parse(readFileSync(schemaPath, 'utf8')) as OpenApiSchema

const METHODS = ['get', 'post', 'put', 'delete', 'patch']

interface Recorded {
  method: string
  /** axios 自己拼出来的完整请求地址（`client.getUri`），带 `/api` 前缀与查询串。 */
  url: string
  query: string[]
  module: string
  /** 这条是 axios 真发出去的，还是只返回字符串的构造器补记的。 */
  viaClient: boolean
}

const calls: Recorded[] = []

/** 正在遍历哪一份模块，写进每条记录里，红了能直接说出是谁的 URL。 */
let currentModule = ''

/** 每次请求都记录，并回一个"任何属性都是空数组"的响应，让 `.then(r => r.data.items)` 之类走得通。 */
const anyData = new Proxy(
  {},
  {
    get: () => [],
  },
)

const originalAdapter = client.defaults.adapter

/**
 * 注意 `config.url` 到适配器这里**还没拼前缀**（实测是 `/videos/new`，`config.baseURL` 是
 * `/api`；拼接收在适配器内部），所以取完整地址要用 `client.getUri(config)`——它走的就是
 * axios 自己那套 `buildFullPath` + 参数序列化，不是在测试里手抄一遍拼接规则。
 */
client.defaults.adapter = (config) => {
  // 遍历器给每个函数都传 `(1, {dummy:true}, 1)`，于是"第一个参数是查询对象"的那几个
  // （`listVideos(params)`）会拿到 `params: 1`；axios 序列化非对象查询串会直接抛
  // `target must be an object`。那是测试脚手架的产物而不是界面行为，这里丢掉它，
  // 代价是这几个函数的查询名在本测试里没有签名（见文件末的说明）。
  const params =
    config.params && typeof config.params === 'object' ? config.params : undefined
  const url = client.getUri({ ...config, params })
  calls.push({
    method: String(config.method ?? 'get').toUpperCase(),
    url,
    query: (url.split('?')[1] ?? '')
      .split('&')
      .filter(Boolean)
      // 遍历器塞进去的 `{dummy:true}` 落在查询位时，axios 会序列化成
      // `page_size%5Bdummy%5D=true`。查询名仍然是 `page_size`，所以只剪掉后面那段，
      // 不能整条丢掉——丢了就把"查询名拼错"这一类一起放过去了（实测变异 ③ 因此演成绿的）。
      .map((pair) => pair.split('=')[0].split('%5B')[0]),
    module: currentModule,
    viaClient: true,
  })
  return Promise.resolve({ data: anyData, status: 200, statusText: 'OK', headers: {}, config })
}

/**
 * 模块清单从文件系统推导，不手写。#121 的教训：`paths.spec.ts` 那份手写 `MODULES` 声称
 * "遍历所有 api 模块"，实际只有 8 份，漏掉的连双前缀护栏都没有。glob 让"漏一份"在结构上不可能。
 */
const loaders = import.meta.glob('../../src/api/*.ts')
const moduleKeys = Object.keys(loaders)
  .filter((key) => !key.endsWith('client.ts'))
  .sort()

async function walkAll(): Promise<void> {
  for (const key of moduleKeys) {
    currentModule = key
    const apiModule = (await loaders[key]()) as Record<string, unknown>
    for (const value of Object.values(apiModule)) {
      const members =
        typeof value === 'function'
          ? [value]
          : value && typeof value === 'object'
            ? Object.values(value as Record<string, unknown>)
            : []
      for (const member of members) {
        if (typeof member === 'function') {
          // 三个参数都给数字：路径里的 id 段必须是数字才谈得上"类型收得下"，而第二个参数
          // 在各模块里都只是请求体（对象还是数字不影响 URL）。
          const returned = await (member as (...args: unknown[]) => unknown)(1, 2, 3)
          // 浏览器自己取地址的那几个函数（`<img>`/`<video>`/`<track>` 的 src）只返回字符串，
          // 一次 axios 都不走，所以适配器记不到它们 —— #122 承认的那半盲区。这里按它们
          // 在浏览器里的真实方法（GET）补记一条，让下面两条路由表规则也能管到。
          if (typeof returned === 'string' && returned.startsWith('/')) {
            calls.push({ method: 'GET', url: returned, query: [], module: currentModule, viaClient: false })
          }
        }
      }
    }
  }
}

/** 找出所有候选模板：段数相同、字面段相同，`{x}` 接受任意一段。 */
function candidates(url: string): string[] {
  const segments = url.split('?')[0].split('/').filter((s) => s !== '')
  return Object.keys(schema.paths).filter((template) => {
    const tSegments = template.split('/').filter((s) => s !== '')
    if (tSegments.length !== segments.length) return false
    return tSegments.every((segment, i) => segment.startsWith('{') || segment === segments[i])
  })
}

function segmentsOf(url: string): string[] {
  return url.split('?')[0].split('/').filter((s) => s !== '')
}

function operationFor(template: string, method: string): OperationObject | undefined {
  if (!METHODS.includes(method)) return undefined
  // 路径项上除了五个动词还挂着 `parameters`，所以这里过一次收窄取值，
  // 而不是 `item[method as keyof PathItem]` 那种把 union 摊回去的写法。
  const item = schema.paths[template] as unknown as Record<string, unknown>
  const value = item[method]
  return value && typeof value === 'object' ? (value as OperationObject) : undefined
}

function declaredParams(template: string, operation: OperationObject): ParameterObject[] {
  return [...(schema.paths[template].parameters ?? []), ...(operation.parameters ?? [])]
}

/**
 * 具体值要过模板声明的路径参数类型。这一条不是装饰：`/videos/duplicates` 写成
 * `/videos/duplicate` 时，形状上仍然命中 `/api/videos/{video_id}`，而 `video_id` 声明是
 * integer，`duplicate` 不是整数——真后端会回 422 而不是 404，形状规则看不见这个差别
 * （实测变异 ④ 因此演成绿的，加上本条才红）。
 */
function pathValuesFit(template: string, operation: OperationObject, url: string): boolean {
  const tSegments = template.split('/').filter((s) => s !== '')
  const values = segmentsOf(url)
  const params = declaredParams(template, operation).filter((p) => p.in === 'path')
  return tSegments.every((segment, i) => {
    if (!segment.startsWith('{')) return true
    const name = segment.slice(1, -1)
    const type = params.find((p) => p.name === name)?.schema?.type
    const value = decodeURIComponent(values[i])
    if (type === 'integer' || type === 'number') return /^-?\d+$/.test(value)
    if (type === 'boolean') return value === 'true' || value === 'false'
    return true
  })
}

/** 该 URL 是否命中某个"声明了此方法、且路径参数类型收得下"的模板。 */
function matchedTemplate(call: Recorded): string | undefined {
  const method = call.method.toLowerCase()
  return candidates(call.url).find((template) => {
    const operation = operationFor(template, method)
    return operation !== undefined && pathValuesFit(template, operation, call.url)
  })
}

function label(call: Recorded): string {
  const shapeMatches = candidates(call.url)
  const hint = shapeMatches.length
    ? `（形状相符的模板有 ${shapeMatches.join(' | ')}，但方法或路径参数类型不成立）`
    : '（连形状相符的模板都没有）'
  return `${call.module.replace('../../src/api/', '')}  ${call.method} ${call.url}${hint}`
}

function recordedCalls(): Recorded[] {
  if (calls.length === 0) throw new Error('还没有遍历任何请求')
  return calls
}

describe('api URLs against the backend route table', () => {
  beforeEach(() => {
    calls.length = 0
  })

  afterAll(() => {
    client.defaults.adapter = originalAdapter
  })

  it('finds every src/api module without a hand-written list', () => {
    // 实测 12 份；断言下限是为了让"glob 什么都没匹配到"不至于演成一份空测试
    expect(moduleKeys.length).toBeGreaterThanOrEqual(12)
  })

  it('walks the modules and reaches the real /api prefix', async () => {
    await walkAll()
    // #123 实测 12→14 份模块共 72 次请求；#124 又记上 4 条不经过 axios 的构造器，共 76 次。
    // 下限挡的是"遍历器换形状了却没发现"：构造器那一段要是哪天不再返回字符串，
    // 记数会静默掉下来，所以这里同时钉住两者各自的数量。
    expect(calls.length).toBeGreaterThanOrEqual(74)
    const wrongPrefix = calls.filter((call) => !call.url.startsWith('/api/'))
    expect(wrongPrefix.map(label)).toEqual([])
  })

  it('records the browser-side builders, which never touch axios', async () => {
    await walkAll()
    // 经过 client 的请求由适配器记录；构造器是函数返回值，靠 walkAll 里那一段补记。
    // 两类分开计数，任何一类静默归零都会红，而不是"总数还够"就混过去。
    const built = calls.filter((call) => !call.viaClient)
    expect(built.length).toBeGreaterThanOrEqual(4)
    expect(built.every((call) => call.method === 'GET')).toBe(true)
  })

  it('resolves every recorded URL against a declared path and method', async () => {
    await walkAll()
    const unmatched = recordedCalls().filter((call) => !matchedTemplate(call)).map(label)
    expect(unmatched).toEqual([])
  })

  it('checks the query strings against the operation parameters', async () => {
    await walkAll()
    const undocumented = recordedCalls().flatMap((call) => {
      const template = matchedTemplate(call)
      if (!template) return []
      const operation = operationFor(template, call.method.toLowerCase())
      const declared = new Set(
        (operation?.parameters ?? []).filter((p) => p.in === 'query').map((p) => p.name),
      )
      return call.query
        .filter((key) => !declared.has(key))
        .map((key) => `${call.method} ${call.url} 的查询参数 ${key} 后端没声明（模板 ${template}）`)
    })
    expect(undocumented).toEqual([])
  })
})
