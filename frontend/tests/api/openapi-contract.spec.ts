import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { beforeAll, describe, expect, it } from 'vitest'

import {
  moduleKeys,
  querySurfaces,
  walkApiModules,
  type QuerySurface,
  type Recorded,
} from './emitted-calls'

/**
 * 前端 URL 对着后端真实路由表核对——补上 `paths.spec.ts` 那一层看不见的东西。
 *
 * `paths.spec.ts` 看的是写代码那个人交给 axios 的那段原文（`config.url`，到适配器这里还没拼
 * 前缀），因此只能验形状。这一份拿的是 `client.getUri` 拼完的完整地址（遍历器在 `emitted-calls.ts`，
 * 替身夹具守卫 `stub-coverage.spec.ts` 共用同一份）：axios 自己先把 `baseURL + url` 拼起来，
 * 所以拿到的是真会发出去的 `/api/...`，再逐条对照 `backend/openapi.json` 的路径模板与方法。
 * 段名拼错（`/auth/session` 少一个 `s`）在这里会一个候选模板都没有，而形状规则完全放它过去——
 * 那正是 #121 承认钉不住的一类。
 *
 * #124 起，遍历器还记 `src/api/` 里那几个**只返回字符串**的构造器：`<img>`/`<video>`/`<track>`
 * 的 src 走的就是它们，一次 axios 都不经过，所以适配器那条路子天生看不见。现在它们按 GET
 * 对同一张路由表核对。此前这一半是彻底的盲区——实测改坏 `subtitles/embedded/` 或详情页的
 * 流地址，31 份测试全绿。
 *
 * 这份 schema 由 `python -m src.export_openapi` 生成，`backend/tests/test_openapi_snapshot.py`
 * 保证它与代码一致。两半缺一条都不成立。
 *
 * #148 起还钉**查询名**。前面那些规则看的都是「地址」，而一句地址还带着查询串：
 * `listVideos(params)` 这类函数的查询名既不写在 `src/api/` 里（它原样转发调用方给的对象），
 * 也不在遍历器塞进去的 `1` 里（序列化不了就被丢掉），所以 #122/#124 各记下了一份「没签到的键」。
 * 现在由 `querySurfaces()` 用哨兵探出这类函数，再把它参数类型接口上声明的整套键逐个发出去核对。
 * 症状不是报错：实测 `?searsh=abc` 回 200、回的是**没筛过的**第一页，筛选就此无声失效。
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
function templateFor(url: string, method: string): string | undefined {
  const lower = method.toLowerCase()
  return candidates(url).find((template) => {
    const operation = operationFor(template, lower)
    return operation !== undefined && pathValuesFit(template, operation, url)
  })
}

function matchedTemplate(call: Recorded): string | undefined {
  return templateFor(call.url, call.method)
}

function label(call: Recorded): string {
  const shapeMatches = candidates(call.url)
  const hint = shapeMatches.length
    ? `（形状相符的模板有 ${shapeMatches.join(' | ')}，但方法或路径参数类型不成立）`
    : '（连形状相符的模板都没有）'
  return `${call.module.replace('../../src/api/', '')}#${call.name}  ${call.method} ${call.url}${hint}`
}

const calls: Recorded[] = []
const surfaces: QuerySurface[] = []

beforeAll(async () => {
  calls.push(...(await walkApiModules()))
  surfaces.push(...(await querySurfaces()))
})

describe('api URLs against the backend route table', () => {
  it('finds every src/api module without a hand-written list', () => {
    // 实测 14 份；断言下限是为了让"glob 什么都没匹配到"不至于演成一份空测试
    expect(moduleKeys.length).toBeGreaterThanOrEqual(12)
  })

  it('walks the modules and reaches the real /api prefix', () => {
    // #123 实测 12→14 份模块共 72 次请求；#124 又记上 4 条不经过 axios 的构造器，共 76 次。
    // 下限挡的是"遍历器换形状了却没发现"：构造器那一段要是哪天不再返回字符串，
    // 记数会静默掉下来，所以这里同时钉住两者各自的数量。
    expect(calls.length).toBeGreaterThanOrEqual(74)
    const wrongPrefix = calls.filter((call) => !call.url.startsWith('/api/'))
    expect(wrongPrefix.map(label)).toEqual([])
  })

  it('records the browser-side builders, which never touch axios', () => {
    // 经过 client 的请求由适配器记录；构造器是函数返回值，靠遍历器补记。
    // 两类分开计数，任何一类静默归零都会红，而不是"总数还够"就混过去。
    const built = calls.filter((call) => !call.viaClient)
    expect(built.length).toBeGreaterThanOrEqual(4)
    expect(built.every((call) => call.method === 'GET')).toBe(true)
  })

  it('resolves every recorded URL against a declared path and method', () => {
    if (calls.length === 0) throw new Error('遍历器一条请求都没记到')
    const unmatched = calls.filter((call) => !matchedTemplate(call)).map(label)
    expect(unmatched).toEqual([])
  })

  it('checks the query strings against the operation parameters', () => {
    const undocumented = calls.flatMap((call) => {
      const template = matchedTemplate(call)
      if (!template) return []
      const operation = operationFor(template, call.method.toLowerCase())
      const declared = new Set(
        (operation?.parameters ?? []).filter((p) => p.in === 'query').map((p) => p.name),
      )
      return call.query
        .filter((key) => !declared.has(key))
        .map(
          (key) =>
            `${call.module.replace('../../src/api/', '')}#${call.name} ${call.method} ${call.url} 的查询参数 ${key} 后端没声明（模板 ${template}）`,
        )
    })
    expect(undocumented).toEqual([])
  })

  it('finds the query-forwarding functions by probe, not by a written list', () => {
    // 实测这一族只有一条：`videos.ts#listVideos`。下限钉的是探测本身——哨兵要哪天不再生效
    // （适配器换错、axios 改了序列化），surfaces 会静默空掉，而"没有未声明的键"照样全绿。
    // 这是本仓第四次踩在「空匹配集不报错，只是绿」上（#122 glob 深度、#128 空遍历、#131 切片偏移）。
    expect(surfaces.length).toBeGreaterThanOrEqual(1)
    expect(surfaces.map((s) => `${s.module}#${s.name}`)).toContain('videos.ts#listVideos')
  })

  it('reads a key set off the parameter type of every surface', () => {
    // 新加一条查询转发函数却没给它声明具名参数接口，就落在这儿红，而不是悄悄躲过核对。
    const unreadable = surfaces
      .filter((surface) => surface.keys.length === 0)
      .map((surface) => `${surface.module}#${surface.name}（参数类型 ${surface.paramType}）读不出键集`)
    expect(unreadable).toEqual([])
  })

  it('sends only the query names the backend declares', () => {
    const undocumented = surfaces.flatMap((surface) => {
      const template = templateFor(surface.url, 'GET')
      if (!template) {
        return [`${surface.module}#${surface.name} 带整套键的地址 ${surface.url} 命不中任何模板`]
      }
      const operation = operationFor(template, 'get')
      const declared = new Set(
        (operation?.parameters ?? []).filter((p) => p.in === 'query').map((p) => p.name),
      )
      return surface.emitted
        .filter((key) => !declared.has(key))
        // 症状写进消息里：后端不是 422，是 200 加一句没筛过的结果（实测见 emitted-calls 顶部）。
        .map(
          (key) =>
            `${surface.module}#${surface.name} 发出去的查询名 ${key} 后端没声明（模板 ${template} 只认 ${[...declared].join(' / ')}）——真后端会 200 回一句没筛过的结果`,
        )
    })
    expect(undocumented).toEqual([])
  })

  it('sends every query name the parameter interface declares', () => {
    // 反向不是缺陷：后端声明了前端没用的键只是那半能力没接，所以这里钉的是**子集**，不是集合相等。
    // 这一条管的是另一半：界面声明了、也真发给了模块，模块却没把它放到线上——筛子无声少一个。
    const dropped = surfaces
      .filter((surface) => [...surface.emitted].sort().join() !== [...surface.keys].sort().join())
      .map(
        (surface) =>
          `${surface.module}#${surface.name} 接口 ${surface.paramType} 声明的是 [${surface.keys.join(' ')}]，发出去的是 [${surface.emitted.join(' ')}]`,
      )
    expect(dropped).toEqual([])
    const listVideos = surfaces.find((s) => `${s.module}#${s.name}` === 'videos.ts#listVideos')
    expect(listVideos?.keys).toEqual(
      expect.arrayContaining(['source_id', 'tag_id', 'search', 'page', 'page_size']),
    )
  })
})
