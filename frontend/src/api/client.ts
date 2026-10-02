import axios from 'axios'

/** Axios instance pre-configured with base URL and JSON headers. */
const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
    // 配合后端的 SameSite=Lax 会话 Cookie 挡 CSRF：跨站表单发不出自定义头。
    'X-Requested-With': 'fetch',
  },
})

/** 会话失效时的回调，由 router 挂上「回登录页」。 */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

/** 422 里的一条校验错误，字段名藏在 loc 数组里，和 body/query/path 这类定位 scope 混在一起。 */
type ValidationErrorItem = {
  type?: unknown
  loc?: unknown
  msg?: unknown
  ctx?: unknown
}

/** loc 的第 0 项是 body/query/path 这类定位 scope，剩下的才是字段名（列表下标是数字）。 */
function fieldOf(item: ValidationErrorItem): string {
  if (!Array.isArray(item.loc)) return ''
  const names = item.loc.slice(1).filter((part): part is string => typeof part === 'string')
  return names[names.length - 1] ?? ''
}

/** pydantic 的错误类型 → 中文说法；没列出的退回后端原文，至少还是一句话。 */
function reasonOf(item: ValidationErrorItem): string {
  const ctx = (item.ctx && typeof item.ctx === 'object' ? item.ctx : {}) as Record<string, unknown>
  const fallback = typeof item.msg === 'string' && item.msg ? item.msg : '输入不合法'
  switch (item.type) {
    case 'missing':
      return '不能为空'
    // 后端普遍写 min_length=1 来表达「必填」，翻成「不能为空」比「至少 1 个字符」更像人话
    case 'string_too_short':
      if (ctx.min_length === 1) return '不能为空'
      return typeof ctx.min_length === 'number' ? `长度至少 ${ctx.min_length} 个字符` : fallback
    case 'string_too_long':
      return typeof ctx.max_length === 'number' ? `长度最多 ${ctx.max_length} 个字符` : fallback
    case 'too_short':
      return typeof ctx.min_length === 'number' ? `至少需要 ${ctx.min_length} 项` : fallback
    case 'too_long':
      return typeof ctx.max_length === 'number' ? `最多 ${ctx.max_length} 项` : fallback
    case 'greater_than_equal':
      return ctx.ge === undefined ? fallback : `不能小于 ${ctx.ge}`
    case 'less_than_equal':
      return ctx.le === undefined ? fallback : `不能大于 ${ctx.le}`
    case 'greater_than':
      return ctx.gt === undefined ? fallback : `必须大于 ${ctx.gt}`
    case 'less_than':
      return ctx.lt === undefined ? fallback : `必须小于 ${ctx.lt}`
    case 'int_parsing':
      return '必须是整数'
    case 'bool_parsing':
      return '只能是 true 或 false'
    case 'string_pattern_mismatch':
      return '格式不正确'
    default:
      return fallback
  }
}

/**
 * FastAPI 的 422 把校验错误装在 detail 数组里，每项是个对象；原样当消息用会被
 * 浏览器渲染成 "[object Object],[object Object]"。这里摊成「字段 原因；字段 原因」。
 */
function flattenDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail || null
  if (!Array.isArray(detail) || detail.length === 0) return null
  const lines = detail
    .map((raw) => {
      const item = raw as ValidationErrorItem
      const field = fieldOf(item)
      const reason = reasonOf(item)
      return field ? `${field} ${reason}` : reason
    })
    .filter(Boolean)
  if (lines.length === 0) return null
  return [...new Set(lines)].join('；')
}

/** Global error interceptor – surfaces a readable message on network / server errors. */
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const url: string = error.config?.url ?? ''
    // 登录接口的 401 是「账号或密码错误」，不是会话过期。
    if (error.response?.status === 401 && !url.startsWith('/auth/') && onUnauthorized) {
      onUnauthorized()
    }
    const message = flattenDetail(error.response?.data?.detail) ?? error.message ?? 'Unknown error'
    return Promise.reject(new Error(message))
  },
)

export default client
