import client from './client'
import type { AuthDevice, AuthStatus, AuthUser } from '@/types/auth'

/** Exchange credentials for an HttpOnly session cookie. */
export function login(
  username: string,
  password: string,
  remember = false,
): Promise<AuthUser> {
  return client
    .post<AuthUser>('/auth/login', { username, password, remember })
    .then((r) => r.data)
}

/** Ask whether this browser holds a valid session, and whether setup is due. */
export function getAuthStatus(): Promise<AuthStatus> {
  return client.get<AuthStatus>('/auth/status').then((r) => r.data)
}

/** The signed-in user, used to restore the top bar after a refresh. */
export function getMe(): Promise<AuthUser> {
  return client.get<AuthUser>('/auth/me').then((r) => r.data)
}

/** Revoke this browser's session. */
export function logout(): Promise<void> {
  return client.post('/auth/logout').then(() => undefined)
}

/** Rotate the password; every other device is signed out. */
export function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  return client
    .post('/auth/password', { old_password: oldPassword, new_password: newPassword })
    .then(() => undefined)
}

/**
 * 这个账号当前还开着会话的浏览器，`current` 标出"就是这一台"。
 *
 * 两种角色都调得动：列的是本人数据，管理员那份走 `/users/{id}/sessions` 的整账号踢下线。
 */
export function listSessions(): Promise<AuthDevice[]> {
  return client.get<AuthDevice[]>('/auth/sessions').then((r) => r.data)
}

/** 退出名下的某一台设备；`tokenHash` 取自 {@link listSessions}，不是 Cookie 值。 */
export function revokeSession(tokenHash: string): Promise<void> {
  return client.delete(`/auth/sessions/${tokenHash}`).then(() => undefined)
}
