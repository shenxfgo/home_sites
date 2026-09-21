import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import client from '@/api/client'
import {
  createUser,
  listUsers,
  resetUserPassword,
  revokeUserSessions,
  setUserRole,
  setUserStatus,
} from '@/api/users'

interface Sent {
  calls: string[]
  bodies: Record<string, unknown>[]
}

/** Record every request the module makes, answering each one with `data`. */
function captureRequests(data: unknown): Sent {
  const sent: Sent = { calls: [], bodies: [] }
  client.defaults.adapter = (config: InternalAxiosRequestConfig) => {
    sent.calls.push(`${config.method?.toUpperCase()} ${config.baseURL ?? ''}${config.url ?? ''}`)
    sent.bodies.push(config.data ? JSON.parse(String(config.data)) : {})
    return Promise.resolve({
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      data,
    } as AxiosResponse)
  }
  return sent
}

const ROW = {
  id: 2,
  username: 'kid',
  role: 'member',
  display_name: null,
  is_active: true,
  created_at: null,
  last_login_at: null,
  signed_in_devices: 1,
}

describe('users api', () => {
  afterEach(() => {
    delete client.defaults.adapter
  })

  it('talks to the six management routes under /api/users', async () => {
    const sent = captureRequests([ROW])

    await listUsers()
    await createUser({ username: 'kid', password: 'secret-pass', role: 'member' })
    await setUserRole(2, 'owner')
    await setUserStatus(2, false)
    await resetUserPassword(2, 'newer-pass')
    await revokeUserSessions(2)

    expect(sent.calls).toEqual([
      'GET /api/users',
      'POST /api/users',
      'PUT /api/users/2/role',
      'PUT /api/users/2/status',
      'POST /api/users/2/password',
      'DELETE /api/users/2/sessions',
    ])
  })

  it('sends the field names the backend models use', async () => {
    const sent = captureRequests([ROW])

    await createUser({ username: 'kid', password: 'secret-pass', role: 'member', display_name: '小明' })
    await setUserRole(2, 'owner')
    await setUserStatus(2, false)
    await resetUserPassword(2, 'newer-pass')

    expect(sent.bodies).toEqual([
      { username: 'kid', password: 'secret-pass', role: 'member', display_name: '小明' },
      { role: 'owner' },
      { is_active: false },
      { new_password: 'newer-pass' },
    ])
  })

  it('reports how many browsers were signed out', async () => {
    const sent = captureRequests({ revoked: 3 })

    expect(await revokeUserSessions(2)).toBe(3)
    expect(sent.bodies[0]).toEqual({})
  })
})
