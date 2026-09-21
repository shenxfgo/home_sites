import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import client from '@/api/client'
import {
  changePassword,
  getAuthStatus,
  getMe,
  listSessions,
  login,
  logout,
  revokeSession,
} from '@/api/auth'

function captureRequests(): string[] {
  const seen: string[] = []
  client.defaults.adapter = (config: InternalAxiosRequestConfig) => {
    seen.push(`${config.method?.toUpperCase()} ${config.baseURL ?? ''}${config.url ?? ''}`)
    return Promise.resolve({
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      data: { id: 1, username: 'tester', role: 'owner', display_name: 'Tester' },
    } as AxiosResponse)
  }
  return seen
}

describe('auth api', () => {
  afterEach(() => {
    delete client.defaults.adapter
  })

  it('calls the seven auth routes without repeating the /api prefix', async () => {
    const seen = captureRequests()

    await login('tester', 'secret-pass', true)
    await getAuthStatus()
    await getMe()
    await logout()
    await changePassword('secret-pass', 'newer-pass')
    await listSessions()
    await revokeSession('a'.repeat(64))

    expect(seen).toEqual([
      'POST /api/auth/login',
      'GET /api/auth/status',
      'GET /api/auth/me',
      'POST /api/auth/logout',
      'POST /api/auth/password',
      'GET /api/auth/sessions',
      `DELETE /api/auth/sessions/${'a'.repeat(64)}`,
    ])
  })

  it('sends the password fields the backend model expects', async () => {
    const body = vi.fn()
    client.defaults.adapter = (config: InternalAxiosRequestConfig) => {
      body(JSON.parse(String(config.data)))
      return Promise.resolve({
        status: 204,
        statusText: 'No Content',
        headers: {},
        config,
        data: undefined,
      } as AxiosResponse)
    }

    await changePassword('old', 'new')

    expect(body).toHaveBeenCalledWith({ old_password: 'old', new_password: 'new' })
  })
})
