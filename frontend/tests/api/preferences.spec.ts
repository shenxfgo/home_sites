import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import client from '@/api/client'
import { getPreferences, updatePreferences } from '@/api/preferences'

interface Sent {
  calls: string[]
  bodies: Record<string, unknown>[]
}

/** Record every request the module makes, answering each one with the stored prefs. */
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

describe('preferences api', () => {
  afterEach(() => {
    delete client.defaults.adapter
  })

  it('reads and writes /api/preferences without the /api prefix twice', async () => {
    const sent = captureRequests({ theme: 'dark' })

    expect(await getPreferences()).toEqual({ theme: 'dark' })
    expect(await updatePreferences({ theme: 'dark' })).toEqual({ theme: 'dark' })

    expect(sent.calls).toEqual(['GET /api/preferences', 'PUT /api/preferences'])
  })

  it('sends only the keys it was given, so the rest keep their stored value', async () => {
    const sent = captureRequests({ theme: 'auto' })

    await updatePreferences({ theme: 'auto' })

    expect(sent.bodies[0]).toEqual({ theme: 'auto' })
  })
})
