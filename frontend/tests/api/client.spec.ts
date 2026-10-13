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
      // 这一格从前写的是 `value_error`。#211 自己就把「后端改完之后 `value_error` 从此不再
      // 由我们自己产生」记进了 `frontend/CLAUDE.md`，用例却留在旧代号上：退路钉的是一个
      // 再也不会来的形状。现在对准真产口——`SourceUpdate._not_null_columns_cannot_be_cleared`
      // 量到的原文是 `{type: 'cannot_be_cleared', loc: ('path',), msg: '路径不能留空'}`，
      // FastAPI 把 loc 包成 ['body', 'path']。
      { type: 'cannot_be_cleared', loc: ['body', 'path'], msg: '路径不能留空' },
    ]

    await expect(
      client.post('/sources', {}, { adapter: failingAdapter(422, { detail }, 'Request failed') }),
    ).rejects.toThrow('name 长度最多 50 个字符；interval_seconds 不能小于 60；source_id 不能为空；path 路径不能留空')
  })

  /**
   * 同一个字段错两处，摊平之后是**同一句话**：`PUT /api/videos/1` 带 `{"tag_ids": ["a","b"]}`
   * 真后端回两条，loc 分别是 `('body','tag_ids',0)` 与 `('body','tag_ids',1)`（量到的原文，
   * `msg` 逐字相同），而 `fieldOf` 把尾巴上那个数字下标滤掉了，两边都剩 `tag_ids`。
   * 断言取的是**整条消息相等**而不是包含：写成 `toThrow('tag_ids 必须是整数')` 的话，
   * 「说了两遍」也照样绿——去重那一句（`[...new Set(lines)]`）就白钉了。
   */
  it('同一个字段错两处只说一遍，loc 尾巴上的下标不算字段名', async () => {
    const detail = [
      { type: 'int_parsing', loc: ['body', 'tag_ids', 0], msg: 'Input should be a valid integer, unable to parse string as an integer' },
      { type: 'int_parsing', loc: ['body', 'tag_ids', 1], msg: 'Input should be a valid integer, unable to parse string as an integer' },
    ]

    const message = await client
      .put('/videos/1', {}, { adapter: failingAdapter(422, { detail }, 'Request failed') })
      .then(() => null, (err: unknown) => (err as Error).message)
    expect(message).toBe('tag_ids 必须是整数')
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
