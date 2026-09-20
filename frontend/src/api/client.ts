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

/** Global error interceptor – surfaces a readable message on network / server errors. */
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const url: string = error.config?.url ?? ''
    // 登录接口的 401 是「账号或密码错误」，不是会话过期。
    if (error.response?.status === 401 && !url.startsWith('/auth/') && onUnauthorized) {
      onUnauthorized()
    }
    const message = error.response?.data?.detail ?? error.message ?? 'Unknown error'
    return Promise.reject(new Error(message))
  },
)

export default client
