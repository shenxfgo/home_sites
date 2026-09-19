import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import client from '@/api/client'
import { notificationsApi } from '@/api/notifications'

function captureRequests(): string[] {
  const seen: string[] = []
  client.defaults.adapter = (config: InternalAxiosRequestConfig) => {
    seen.push(`${config.method?.toUpperCase()} ${config.baseURL ?? ''}${config.url ?? ''}`)
    return Promise.resolve({
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      data: { count: 0 },
    } as AxiosResponse)
  }
  return seen
}

describe('notifications api', () => {
  afterEach(() => {
    delete client.defaults.adapter
  })

  it('lists and counts through the read endpoints', async () => {
    const seen = captureRequests()

    await notificationsApi.list(2, 10)
    await notificationsApi.getUnreadCount()

    expect(seen).toEqual([
      'GET /api/notifications',
      'GET /api/notifications/unread',
    ])
  })

  it('deletes one notification by id', async () => {
    const seen = captureRequests()

    await notificationsApi.remove(12)

    expect(seen).toEqual(['DELETE /api/notifications/12'])
  })

  it('clears the whole list with a single call to the collection', async () => {
    const seen = captureRequests()

    await notificationsApi.clearAll()

    expect(seen).toEqual(['DELETE /api/notifications'])
  })
})
