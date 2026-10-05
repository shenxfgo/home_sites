import { beforeEach, describe, expect, it, vi } from 'vitest'

const recorded = vi.hoisted(() => ({ calls: [] as string[] }))

vi.mock('@/api/client', () => {
  const data = new Proxy(
    {},
    {
      get: () => [],
    },
  )
  const make = () => (url: string) => {
    recorded.calls.push(url)
    return Promise.resolve({ data })
  }
  return {
    default: { get: make(), post: make(), put: make(), delete: make() },
  }
})

/**
 * `src/api/` 里除 `client.ts`（它就是被上面那份替身换掉的那个 axios 实例）之外的**全部**
 * 请求模块。少列一份不是"少测一个函数"，而是那一整份的 URL 从此没有任何静态钉子——#119
 * 量到这里只覆盖 12 份里的 8 份，auth / preferences / users / watchlists 四份连"别把
 * baseURL 已经带的 `/api` 再写一遍"（#10 那一类）都翻不出来。
 */
const MODULES = [
  '@/api/videos',
  '@/api/subtitles',
  '@/api/sources',
  '@/api/history',
  '@/api/favorites',
  '@/api/tags',
  '@/api/settings',
  '@/api/notifications',
  '@/api/auth',
  '@/api/preferences',
  '@/api/users',
  '@/api/watchlists',
]

async function invokeEveryExport(path: string): Promise<void> {
  const module = (await import(path)) as Record<string, unknown>
  for (const value of Object.values(module)) {
    const members =
      typeof value === 'function'
        ? [value]
        : value && typeof value === 'object'
          ? Object.values(value as Record<string, unknown>)
          : []
    for (const member of members) {
      if (typeof member === 'function') {
        await (member as (...args: unknown[]) => Promise<unknown>)(1, { dummy: true }, 1)
      }
    }
  }
}

/** 跑一份模块，返回它**新增**的那几次调用——按模块归账才数得出"哪一份没走到 client"。 */
async function invokeModule(path: string): Promise<string[]> {
  const before = recorded.calls.length
  await invokeEveryExport(path)
  return recorded.calls.slice(before)
}

async function invokeAll(): Promise<Map<string, string[]>> {
  const byModule = new Map<string, string[]>()
  for (const path of MODULES) {
    byModule.set(path, await invokeModule(path))
  }
  return byModule
}

describe('api request paths', () => {
  beforeEach(() => {
    recorded.calls.length = 0
  })

  it('exercise every exported api function', async () => {
    const byModule = await invokeAll()
    // 空的那一份= 这份模块里的函数没有一个真正打到 client（改成了不请求、或者整个模块
    // 被 rewrite 成走缓存）。只看总数测不到它：12 份实测共 66 次，整份停掉也还剩 64 次。
    const silent = [...byModule].filter(([, urls]) => urls.length === 0).map(([path]) => path)
    expect(silent).toEqual([])
    expect(recorded.calls.length).toBeGreaterThan(40)
  })

  it('never repeat the /api prefix that the axios instance already carries', async () => {
    await invokeAll()

    const doubled = recorded.calls.filter((url) => url.startsWith('/api'))
    expect(doubled).toEqual([])
  })

  it('keeps every path absolute so the baseURL stays meaningful', async () => {
    await invokeAll()

    const relative = recorded.calls.filter((url) => !url.startsWith('/'))
    expect(relative).toEqual([])
  })

  it('keeps one separator per join: no // and no trailing slash', async () => {
    // 拼路径时多写一个 `/`（`/sources/${id}/` + `/scan`）在浏览器里是个新地址，会打到
    // 前缀中间去；尾斜杠同样是另一条路由。真库里没人点过的组合只有这条静态钉子挡得住。
    await invokeAll()

    const malformed = recorded.calls.filter((url) => url.includes('//') || url.endsWith('/'))
    expect(malformed).toEqual([])
  })
})
