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

const MODULES = [
  '@/api/videos',
  '@/api/subtitles',
  '@/api/sources',
  '@/api/history',
  '@/api/favorites',
  '@/api/tags',
  '@/api/settings',
  '@/api/notifications',
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

describe('api request paths', () => {
  beforeEach(() => {
    recorded.calls.length = 0
  })

  it('exercise every exported api function', async () => {
    for (const path of MODULES) {
      await invokeEveryExport(path)
    }
    expect(recorded.calls.length).toBeGreaterThan(20)
  })

  it('never repeat the /api prefix that the axios instance already carries', async () => {
    for (const path of MODULES) {
      await invokeEveryExport(path)
    }

    const doubled = recorded.calls.filter((url) => url.startsWith('/api'))
    expect(doubled).toEqual([])
  })

  it('keeps every path absolute so the baseURL stays meaningful', async () => {
    for (const path of MODULES) {
      await invokeEveryExport(path)
    }

    const relative = recorded.calls.filter((url) => !url.startsWith('/'))
    expect(relative).toEqual([])
  })
})
