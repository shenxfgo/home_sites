import client from './client'
import type { AuthStatus, AuthUser } from '@/types/auth'

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
