import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import client from '@/api/client'
import { getVideo, listVideos, thumbnailUrl, updateProgress } from '@/api/videos'

interface Seen {
  url: string
  params?: unknown
  data?: unknown
}

function captureRequests(payload: unknown = {}): Seen[] {
  const seen: Seen[] = []
  client.defaults.adapter = (config: InternalAxiosRequestConfig) => {
    seen.push({ url: `${config.baseURL ?? ''}${config.url ?? ''}`, params: config.params, data: config.data })
    return Promise.resolve({
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
      data: payload,
    } as AxiosResponse)
  }
  return seen
}

describe('videos api', () => {
  afterEach(() => {
    delete client.defaults.adapter
  })

  it('builds thumbnail urls against the backend route including the /api prefix', () => {
    expect(thumbnailUrl(7)).toBe('/api/videos/7/thumbnail')
  })

  it('forwards list filters to /videos', async () => {
    const seen = captureRequests({ items: [], total: 0, page: 1, page_size: 20 })

    await listVideos({ page: 2, search: '测试' })

    expect(seen).toEqual([{ url: '/api/videos', params: { page: 2, search: '测试' } }])
  })

  it('requests a single video by id', async () => {
    const seen = captureRequests()

    await getVideo(3)

    expect(seen[0]?.url).toBe('/api/videos/3')
  })

  it('posts playback progress as a number payload', async () => {
    const seen = captureRequests()

    await updateProgress(5, 42.5)

    expect(seen[0]?.url).toBe('/api/videos/5/progress')
    expect(JSON.parse(String(seen[0]?.data))).toEqual({ progress: 42.5 })
  })
})
