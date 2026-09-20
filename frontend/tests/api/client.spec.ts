import { describe, expect, it, vi } from 'vitest'
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import client, { setUnauthorizedHandler } from '@/api/client'

function failingAdapter(status: number, data: unknown, message: string) {
  return (config: InternalAxiosRequestConfig) => {
    const response = { status, statusText: '', headers: {}, config, data } as AxiosResponse
    return Promise.reject(new AxiosError(message, 'ERR_BAD_RESPONSE', config, {}, response))
  }
}

describe('api client', () => {
  it('uses /api as its base url so call sites stay prefix-free', () => {
    expect(client.defaults.baseURL).toBe('/api')
  })

  it('surfaces the backend detail message as the rejection reason', async () => {
    const adapter = failingAdapter(400, { detail: '扫描间隔不能小于 60 秒' }, 'Request failed')

    await expect(client.get('/sources', { adapter })).rejects.toThrow('扫描间隔不能小于 60 秒')
  })

  it('falls back to the transport message when the payload has no detail', async () => {
    const adapter = failingAdapter(0, undefined, 'Network Error')

    await expect(client.get('/sources', { adapter })).rejects.toThrow('Network Error')
  })

  it('leaves successful responses untouched', async () => {
    const payload = { items: [], total: 0 }
    const adapter = (config: InternalAxiosRequestConfig) =>
      Promise.resolve({
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: payload,
      } as AxiosResponse)

    await expect(client.get('/videos', { adapter })).resolves.toMatchObject({ data: payload })
  })

  it('sends the header that stands in for a CSRF token', async () => {
    let sent: string | undefined
    const adapter = (config: InternalAxiosRequestConfig) => {
      sent = config.headers.get('X-Requested-With')
      return Promise.resolve({
        status: 204,
        statusText: 'No Content',
        headers: {},
        config,
        data: undefined,
      } as AxiosResponse)
    }

    await client.delete('/sources/1', { adapter })

    expect(sent).toBe('fetch')
  })

  it('hands a 401 on a data path to the session handler, and not a failed login', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await expect(
      client.post('/auth/login', {}, { adapter: failingAdapter(401, { detail: '账号或密码错误' }, 'Unauthorized') }),
    ).rejects.toThrow('账号或密码错误')
    expect(handler).not.toHaveBeenCalled()

    await expect(
      client.get('/videos', { adapter: failingAdapter(401, { detail: '未认证' }, 'Unauthorized') }),
    ).rejects.toThrow('未认证')
    expect(handler).toHaveBeenCalledTimes(1)
  })
})
