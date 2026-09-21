/** 认证相关的前后端契约类型。 */

export type UserRole = 'owner' | 'member'

export interface AuthUser {
  id: number
  username: string
  role: UserRole
  display_name: string | null
}

/** `/api/auth/status` 是登录前唯一可访问的状态探针。 */
export interface AuthStatus {
  authenticated: boolean
  /** 库里还没有任何账号：登录页要给出建号指引。 */
  needs_setup: boolean
}

/** 用户管理表格里的一行；比 `AuthUser` 多出来的都是管理员要看的字段。 */
export interface AdminUser extends AuthUser {
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
  /** 这个账号现在还开着几个浏览器。 */
  signed_in_devices: number
}

/** "我的设备"里的一行：本账号还留着会话的一个浏览器。 */
export interface AuthDevice {
  /**
   * 会话的 sha256 摘要，也是退出这台设备时 URL 上的地址。它不是 Cookie 值，
   * 拿不到原 token，所以前端把它当作一个普通的行标识用就行。
   */
  token_hash: string
  /** 就是发起这次请求的这个浏览器。 */
  current: boolean
  user_agent: string | null
  created_at: string | null
  last_seen_at: string | null
  expires_at: string | null
}
