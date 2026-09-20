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
