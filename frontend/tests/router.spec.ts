import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('router', () => {
  it('exposes the main navigation routes', () => {
    const names = router.getRoutes().map((route) => route.name).filter(Boolean)

    expect(names).toEqual(
      expect.arrayContaining([
        'home',
        'sources',
        'history',
        'stats',
        'favorites',
        'tags',
        'settings',
      ]),
    )
  })

  it('sends unknown paths to the 404 page instead of rendering nothing', async () => {
    await router.push('/definitely/not/a/page')

    expect(router.currentRoute.value.name).toBe('not-found')
    expect(router.currentRoute.value.params.pathMatch).toEqual(['definitely', 'not', 'a', 'page'])
  })

  it('keeps the video detail and transcode routes addressable by id', () => {
    expect(router.resolve('/videos/12').name).toBe('video-detail')
    expect(router.resolve('/videos/12/transcode').name).toBe('transcode')
    expect(router.resolve('/videos/12/transcode').params.id).toBe('12')
  })

  it('writes the route title into the document title', async () => {
    await router.push('/history')

    expect(document.title).toBe('播放历史 - Home Sites')
  })
})
