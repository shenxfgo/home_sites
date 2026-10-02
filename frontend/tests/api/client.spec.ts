import { describe, expect, it, vi } from 'vitest'
import { AxiosError, type AxiosHeaderValue, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
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

  it('摊平 FastAPI 的 422 数组，而不是留下 [object Object]', async () => {
    const detail = [
      {
        type: 'string_too_short',
        loc: ['body', 'username'],
        msg: 'String should have at least 1 character',
        input: '',
        ctx: { min_length: 1 },
      },
      {
        type: 'string_too_short',
        loc: ['body', 'password'],
        msg: 'String should have at least 1 character',
        input: '',
        ctx: { min_length: 1 },
      },
    ]

    await expect(
      client.post('/auth/login', {}, { adapter: failingAdapter(422, { detail }, 'Request failed') }),
    ).rejects.toThrow('username 不能为空；password 不能为空')
  })

  it('按校验类型说人话，认不出的类型退回后端原文', async () => {
    const detail = [
      { type: 'string_too_long', loc: ['body', 'name'], msg: 'String should have at most 50 characters', ctx: { max_length: 50 } },
      { type: 'greater_than_equal', loc: ['body', 'interval_seconds'], msg: 'Input should be greater than or equal to 60', ctx: { ge: 60 } },
      { type: 'missing', loc: ['query', 'source_id'], msg: 'Field required' },
      { type: 'value_error', loc: ['body', 'path'], msg: '路径必须存在' },
    ]

    await expect(
      client.post('/sources', {}, { adapter: failingAdapter(422, { detail }, 'Request failed') }),
    ).rejects.toThrow('name 长度最多 50 个字符；interval_seconds 不能小于 60；source_id 不能为空；path 路径必须存在')
  })

  it('422 数组是空的时退回传输层的消息', async () => {
    await expect(
      client.get('/sources', { adapter: failingAdapter(422, { detail: [] }, 'Request failed') }),
    ).rejects.toThrow('Request failed')
  })

  it('认不出的 422 条目形状也有一句话可看，不是 [object Object]', async () => {
    await expect(
      client.get('/sources', { adapter: failingAdapter(422, { detail: [{}] }, 'Request failed') }),
    ).rejects.toThrow('输入不合法')
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
    let sent: AxiosHeaderValue | undefined
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
