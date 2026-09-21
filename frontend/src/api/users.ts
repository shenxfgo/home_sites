import client from './client'
import type { AdminUser, UserRole } from '@/types/auth'

/** 用户管理只有 owner 调得动：成员请求这些路径会被中间件挡成 403。 */

export interface NewUser {
  username: string
  password: string
  role: UserRole
  display_name?: string | null
}

/** List every account with its role and open browsers. */
export function listUsers(): Promise<AdminUser[]> {
  return client.get<AdminUser[]>('/users').then((r) => r.data)
}

/** Create an account, the same way the command line does. */
export function createUser(data: NewUser): Promise<AdminUser> {
  return client.post<AdminUser>('/users', data).then((r) => r.data)
}

/** Promote or demote one account. */
export function setUserRole(userId: number, role: UserRole): Promise<AdminUser> {
  return client.put<AdminUser>(`/users/${userId}/role`, { role }).then((r) => r.data)
}

/** Enable or disable an account; disabling signs it out everywhere. */
export function setUserStatus(userId: number, isActive: boolean): Promise<AdminUser> {
  return client
    .put<AdminUser>(`/users/${userId}/status`, { is_active: isActive })
    .then((r) => r.data)
}

/** Hand a forgotten password back; that account is signed out everywhere. */
export function resetUserPassword(userId: number, newPassword: string): Promise<void> {
  return client
    .post(`/users/${userId}/password`, { new_password: newPassword })
    .then(() => undefined)
}

/** Sign one account out of every browser, returning how many sessions went. */
export function revokeUserSessions(userId: number): Promise<number> {
  return client
    .delete<{ revoked: number }>(`/users/${userId}/sessions`)
    .then((r) => r.data.revoked)
}
