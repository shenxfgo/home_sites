import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * `backend/openapi.json` 的读法与路由表匹配机器。
 *
 * 为什么单独一份：`openapi-contract.spec.ts`（前端发的地址要命中的路由表）和
 * `stub-coverage.spec.ts`（替身夹具要接住的地址集合，反向那半要把路由表逐条具体化）用的是
 * **同一套**「这段地址算不算命中这个模板」的判断。抄第二份就等于把判断标准变成两份，而这里的
 * 失效方式恰好就是 #121 拒掉手写清单的那个理由：改一处、另一处跟着漂移，守卫还在绿。
 *
 * 这份 schema 由 `python -m src.export_openapi` 生成，`backend/tests/test_openapi_snapshot.py`
 * 保证它与代码一致。两半缺一条都不成立。
 */

export interface ParameterObject {
  name: string
  in: string
  schema?: { type?: string; pattern?: string }
}

export interface OperationObject {
  parameters?: ParameterObject[]
}

export interface PathItem {
  parameters?: ParameterObject[]
  get?: OperationObject
  post?: OperationObject
  put?: OperationObject
  delete?: OperationObject
  patch?: OperationObject
}

export interface OpenApiSchema {
  paths: Record<string, PathItem>
}

// jsdom 环境里 `new URL(..., import.meta.url)` 返回的是 jsdom 的 URL 实例，
// `readFileSync` 认不出它的 `file:` scheme（实测 `ERR_INVALID_URL_SCHEME`），所以走
// fileURLToPath + path.resolve 这条纯 Node 的路。
const schemaPath = resolve(dirname(fileURLToPath(import.meta.url)), '../../../backend/openapi.json')

export const schema = JSON.parse(readFileSync(schemaPath, 'utf8')) as OpenApiSchema

export const METHODS = ['get', 'post', 'put', 'delete', 'patch']

export function segmentsOf(url: string): string[] {
  return url.split('?')[0].split('/').filter((s) => s !== '')
}

/** 找出所有候选模板：段数相同、字面段相同，`{x}` 接受任意一段。 */
export function candidates(url: string): string[] {
  const segments = segmentsOf(url)
  return Object.keys(schema.paths).filter((template) => {
    const tSegments = template.split('/').filter((s) => s !== '')
    if (tSegments.length !== segments.length) return false
    return tSegments.every((segment, i) => segment.startsWith('{') || segment === segments[i])
  })
}

export function operationFor(template: string, method: string): OperationObject | undefined {
  if (!METHODS.includes(method)) return undefined
  // 路径项上除了五个动词还挂着 `parameters`，所以这里过一次收窄取值，
  // 而不是 `item[method as keyof PathItem]` 那种把 union 摊回去的写法。
  const item = schema.paths[template] as unknown as Record<string, unknown>
  const value = item[method]
  return value && typeof value === 'object' ? (value as OperationObject) : undefined
}

export function declaredParams(template: string, operation: OperationObject): ParameterObject[] {
  return [...(schema.paths[template].parameters ?? []), ...(operation.parameters ?? [])]
}

/**
 * 具体值要过模板声明的路径参数类型。这一条不是装饰：`/videos/duplicates` 写成
 * `/videos/duplicate` 时，形状上仍然命中 `/api/videos/{video_id}`，而 `video_id` 声明是
 * integer，`duplicate` 不是整数——真后端会回 422 而不是 404，形状规则看不见这个差别
 * （实测变异 ④ 因此演成绿的，加上本条才红）。
 */
export function pathValuesFit(template: string, operation: OperationObject, url: string): boolean {
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
export function templateFor(url: string, method: string): string | undefined {
  const lower = method.toLowerCase()
  return candidates(url).find((template) => {
    const operation = operationFor(template, lower)
    return operation !== undefined && pathValuesFit(template, operation, url)
  })
}

export interface DeclaredOperation {
  /** 小写动词，和 openapi 的键一致。 */
  method: string
  /** 带 `/api` 前缀的模板原文（`/api/videos/{video_id}`）——openapi 的键本身就带前缀，别再拼一次。 */
  template: string
}

/** 路由表上声明的每一个操作。实测 85 条。 */
export function declaredOperations(): DeclaredOperation[] {
  const ops: DeclaredOperation[] = []
  for (const [template, item] of Object.entries(schema.paths)) {
    for (const method of METHODS) {
      const value = (item as unknown as Record<string, unknown>)[method]
      if (value && typeof value === 'object') ops.push({ method, template })
    }
  }
  return ops
}

/**
 * 非整数路径参数的样本，键是参数名。全表实测只有 11 个路径参数名，其中 9 个是 integer，
 * 剩下这两个的形状不是数字：
 *
 * - `token_hash`：`/auth/sessions/{token_hash}` 声明了 pattern `^[0-9a-f]{64}$`（#126 那条），
 *   `/auth/sessions/1` 是个真后端收不到的地址。
 * - `key`：`/settings/{key}` 走 `SYSTEM_SETTING_KEYS` 白名单，随便填一个串会命中"键不存在"那条分支。
 *
 * 和遍历器 `emitted-calls.ts` 里的 `SAMPLE_ARGS` 是同一批地址的两半：那边管前端发出的形状，
 * 这边管路由表反推出来的形状，两边的样本必须一致，否则反向核对会在样本本身上红。
 */
const NON_INTEGER_PATH_SAMPLES: Record<string, string> = {
  key: 'auto_scan_interval',
  token_hash: 'f'.repeat(64),
}

/**
 * 具体化的结果。`ok` 是判别位——TS 不吃「靠 `problem` 的真假窄化」这一套（实测两个分支都留成
 * `string | undefined`），而这里要的正是「要么有地址要么有问题」互斥，所以拿字面量当闸门。
 */
export type Concretization =
  | { ok: true; url: string }
  | { ok: false; problem: string }

/**
 * 把模板里的路径参数换成一个**真后端收得下**的具体值。
 *
 * 为什么按声明类型而不是按参数名硬编码：反向守卫问的是「这条地址夹具接不接得住」，具体值只要
 * 类型收得下就够。而**遇到认不出的类型必须报问题，不能兜底填 `s1`**——那样会把「有分支接得住」
 * 演成「没接」（分支是按值挑的），凭空造出一个洞。这条不是假想敌：#234 的探针就是靠
 * `{s1}/w1/q1` 这类填充才把清单量错的。
 */
export function concretize(op: DeclaredOperation): Concretization {
  const operation = operationFor(op.template, op.method)
  if (!operation)
    return { ok: false, problem: `${op.method.toUpperCase()} ${op.template} 在路由表上取不到操作对象` }
  const pathParams = declaredParams(op.template, operation).filter((p) => p.in === 'path')
  const segments = op.template.split('/')
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i]
    if (!segment.startsWith('{')) continue
    const name = segment.slice(1, -1)
    const type = pathParams.find((p) => p.name === name)?.schema?.type
    if (type === 'integer' || type === 'number') {
      segments[i] = '1'
      continue
    }
    if (type === 'boolean') {
      segments[i] = 'true'
      continue
    }
    const sample = NON_INTEGER_PATH_SAMPLES[name]
    if (sample !== undefined) {
      segments[i] = sample
      continue
    }
    return {
      ok: false,
      problem: `${op.method.toUpperCase()} ${op.template} 的路径参数 ${name}（声明类型 ${type ?? '读不到'}）没有具体化样本`,
    }
  }
  return { ok: true, url: segments.join('/') }
}
