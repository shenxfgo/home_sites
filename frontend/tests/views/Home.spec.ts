import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Router } from 'vue-router'
import { ElMessage, ElMessageBox, ElSelect } from 'element-plus'
import Home from '@/views/Home.vue'
import VideoCard from '@/components/VideoCard.vue'
import { deleteVideo, listSeriesProgress, listVideos } from '@/api/videos'
import { listSources } from '@/api/sources'
import { listTags } from '@/api/tags'
import { getContinueList } from '@/api/history'
import { makeSeriesProgress, makeSource, makeTag, makeVideo } from '../factories'

vi.mock('@/api/videos', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/videos')>()
  return {
    ...actual,
    deleteVideo: vi.fn(),
    listVideos: vi.fn(),
    listSeriesProgress: vi.fn(async () => []),
  }
})
vi.mock('@/api/sources', () => ({ listSources: vi.fn() }))
vi.mock('@/api/tags', () => ({ listTags: vi.fn() }))
vi.mock('@/api/history', () => ({ getContinueList: vi.fn() }))

const stub = { template: '<div />' }

/** A real router on an in-memory address bar, so query sync is exercised for real. */
async function makeRouter(initial = '/'): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: stub },
      { path: '/videos/:id', name: 'video-detail', component: stub },
    ],
  })
  await router.push(initial)
  await router.isReady()
  return router
}

async function mountHome(initial = '/') {
  const router = await makeRouter(initial)
  // Attached to the document so focus() — and the "/" shortcut that relies on it — behave.
  const wrapper = mount(Home, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

function lastQuery() {
  return vi.mocked(listVideos).mock.calls.at(-1)?.[0]
}

describe('Home view search', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.mocked(listVideos).mockReset()
    vi.mocked(listVideos).mockResolvedValue({ items: [makeVideo({ id: 1 })], total: 1, page: 1, page_size: 20 })
    vi.mocked(listSources).mockResolvedValue([makeSource({ id: 3, name: '剧集' })])
    vi.mocked(listTags).mockResolvedValue([makeTag(7, '悬疑')])
    vi.mocked(getContinueList).mockReset()
    vi.mocked(getContinueList).mockResolvedValue([])
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('loads the library together with both filter lists', async () => {
    const { wrapper } = await mountHome()

    expect(lastQuery()).toMatchObject({ page: 1, page_size: 20 })
    expect(wrapper.findAllComponents(VideoCard)).toHaveLength(1)
    expect(listSources).toHaveBeenCalledWith(true)
    expect(listTags).toHaveBeenCalled()
    expect(wrapper.findAllComponents(ElSelect)).toHaveLength(2)
    wrapper.unmount()
  })

  it('sends the trimmed keyword after the debounce', async () => {
    const router = await makeRouter()
    vi.useFakeTimers()
    const wrapper = mount(Home, { global: { plugins: [router] } })
    await flushPromises()

    const input = wrapper.find('input')
    await input.setValue('  暗涌 第一季 ')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()

    expect(lastQuery()).toMatchObject({ search: '暗涌 第一季' })
    wrapper.unmount()
  })

  it('writes the keyword into the address bar, and takes it back out', async () => {
    const router = await makeRouter()
    vi.useFakeTimers()
    const wrapper = mount(Home, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('input').setValue('暗涌')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ q: '暗涌' })

    await wrapper.find('input').setValue('')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})

    wrapper.unmount()
  })

  it('passes the chosen tag to the api and restarts pagination', async () => {
    const { wrapper } = await mountHome()
    const callsBefore = vi.mocked(listVideos).mock.calls.length

    const tagSelect = wrapper.findAllComponents(ElSelect)[1]
    tagSelect.vm.$emit('update:modelValue', 7)
    await flushPromises()
    tagSelect.vm.$emit('change', 7)
    await flushPromises()

    expect(vi.mocked(listVideos)).toHaveBeenCalledTimes(callsBefore + 1)
    expect(lastQuery()).toMatchObject({ tag_id: 7, page: 1 })
    wrapper.unmount()
  })

  it('leaves the tag out of the query once the select is cleared', async () => {
    const { wrapper } = await mountHome()

    const tagSelect = wrapper.findAllComponents(ElSelect)[1]
    tagSelect.vm.$emit('update:modelValue', 7)
    await flushPromises()
    tagSelect.vm.$emit('change', 7)
    await flushPromises()
    tagSelect.vm.$emit('update:modelValue', undefined)
    await flushPromises()
    tagSelect.vm.$emit('change', undefined)
    await flushPromises()

    expect(lastQuery()).not.toHaveProperty('tag_id')
    wrapper.unmount()
  })

  it('explains an empty search and clears every filter on demand', async () => {
    vi.mocked(listVideos).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    const { wrapper } = await mountHome()

    await wrapper.find('input').setValue('查无此片')
    await wrapper.find('input').trigger('keyup', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.text()).toContain('没有与「查无此片」匹配的结果')

    await wrapper.get('.empty-clear').trigger('click')
    await flushPromises()

    expect(lastQuery()).not.toHaveProperty('search')
    expect(wrapper.find('input').element.value).toBe('')
    wrapper.unmount()
  })

  it('keeps the plain onboarding copy for an untouched library', async () => {
    vi.mocked(listVideos).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    const { wrapper } = await mountHome()

    expect(wrapper.text()).toContain('添加视频源并扫描即可开始使用')
    expect(wrapper.find('.empty-clear').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('Home resume rail', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.mocked(listVideos).mockReset()
    vi.mocked(listVideos).mockResolvedValue({ items: [makeVideo({ id: 1 })], total: 1, page: 1, page_size: 20 })
    vi.mocked(listSources).mockResolvedValue([makeSource({ id: 3, name: '剧集' })])
    vi.mocked(listTags).mockResolvedValue([makeTag(7, '悬疑')])
    vi.mocked(getContinueList).mockReset()
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('shows unfinished titles with the time left and how far they got', async () => {
    vi.mocked(getContinueList).mockResolvedValue([
      makeVideo({ id: 5, title: '暗涌 第一季', duration: 100, progress: 40, thumbnail_path: null }),
    ])
    const { wrapper, router } = await mountHome()

    const items = wrapper.findAll('.rail-item')
    expect(items).toHaveLength(1)
    expect(wrapper.get('.rail-title').text()).toBe('继续观看')
    expect(wrapper.get('.rail-count').text()).toContain('1 部没看完')
    expect(wrapper.get('.rail-remaining').text()).toBe('剩 1:00')
    expect(wrapper.get('.rail-bar-fill').attributes('style')).toContain('width: 40%')
    expect(wrapper.find('.rail-img').exists()).toBe(false)

    await wrapper.get('.rail-caption').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('video-detail')
    expect(router.currentRoute.value.params.id).toBe('5')
    wrapper.unmount()
  })

  it('reads a whole video without a stored position as unstarted', async () => {
    vi.mocked(getContinueList).mockResolvedValue([
      makeVideo({ id: 6, duration: 120, progress: null, thumbnail_path: '/t/6.jpg' }),
    ])
    const { wrapper } = await mountHome()

    expect(wrapper.get('.rail-remaining').text()).toBe('剩 2:00')
    expect(wrapper.get('.rail-bar-fill').attributes('style')).toContain('width: 0%')
    expect(wrapper.get('.rail-img').attributes('src')).toBeTruthy()
    wrapper.unmount()
  })

  it('stays out of the way once the library is filtered', async () => {
    vi.mocked(getContinueList).mockResolvedValue([makeVideo({ id: 5, duration: 100, progress: 40 })])
    const { wrapper } = await mountHome('/?q=暗涌')

    expect(wrapper.find('.resume-rail').exists()).toBe(false)
    expect(wrapper.find('input').element.value).toBe('暗涌')
    wrapper.unmount()
  })

  it('skips the rail when nothing is left unfinished', async () => {
    vi.mocked(getContinueList).mockResolvedValue([])
    const { wrapper } = await mountHome()

    expect(wrapper.find('.resume-rail').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('Home series rail', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.mocked(listVideos).mockReset()
    vi.mocked(listVideos).mockResolvedValue({ items: [makeVideo({ id: 1 })], total: 1, page: 1, page_size: 20 })
    vi.mocked(listSources).mockResolvedValue([makeSource({ id: 3, name: '剧集' })])
    vi.mocked(listTags).mockResolvedValue([makeTag(7, '悬疑')])
    vi.mocked(getContinueList).mockResolvedValue([])
    vi.mocked(listSeriesProgress).mockReset()
    vi.mocked(listSeriesProgress).mockResolvedValue([])
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('shows how far each series got and opens the next episode', async () => {
    vi.mocked(listSeriesProgress).mockResolvedValue([
      makeSeriesProgress({
        series: '暗涌',
        total: 4,
        finished: 3,
        next: makeVideo({ id: 11, series: '暗涌', season: 1, episode: 4 }),
      }),
    ])
    const { wrapper, router } = await mountHome()

    const rail = wrapper.get('.series-rail')
    expect(rail.get('.rail-title').text()).toBe('系列进度')
    expect(rail.get('.rail-count').text()).toContain('1 个系列')
    expect(rail.get('.rail-remaining').text()).toBe('3/4')
    expect(rail.get('.rail-bar-fill').attributes('style')).toContain('width: 75%')
    expect(rail.get('.rail-caption').text()).toBe('暗涌')
    expect(rail.get('.rail-state').text()).toBe('看到 S01E04')

    await rail.get('.rail-item').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.id).toBe('11')
    wrapper.unmount()
  })

  it('reads a season-less episode as 第N集', async () => {
    vi.mocked(listSeriesProgress).mockResolvedValue([
      makeSeriesProgress({ next: makeVideo({ id: 12, season: null, episode: 7 }) }),
    ])
    const { wrapper } = await mountHome()

    expect(wrapper.get('.rail-state').text()).toBe('看到 第7集')
    wrapper.unmount()
  })

  it('labels a finished series and leaves it unclickable', async () => {
    vi.mocked(listSeriesProgress).mockResolvedValue([
      makeSeriesProgress({ series: '公路旅行', total: 2, finished: 2, next: null }),
    ])
    const { wrapper, router } = await mountHome()

    const item = wrapper.get('.series-rail .rail-item')
    expect(item.classes()).toContain('rail-item-done')
    expect(wrapper.get('.rail-state').text()).toBe('已看完')
    expect(wrapper.get('.rail-bar-fill').attributes('style')).toContain('width: 100%')

    await item.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('home')
    wrapper.unmount()
  })

  it('keeps the series rail out of a filtered library', async () => {
    vi.mocked(listSeriesProgress).mockResolvedValue([makeSeriesProgress()])
    const { wrapper } = await mountHome('/?q=暗涌')

    expect(wrapper.find('.series-rail').exists()).toBe(false)
    wrapper.unmount()
  })

  it('skips the rail for a library with no parsed series', async () => {
    const { wrapper } = await mountHome()

    expect(wrapper.find('.series-rail').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('Home lost records banner', () => {
  const LOST = '丢失'

  function lostVideo(id: number) {
    return makeVideo({ id, title: `没了的第${id}部`, is_missing: true })
  }

  /** Answer the lost-records probe and the ordinary grid request separately. */
  function libraryWithLost(count: number) {
    vi.mocked(listVideos).mockImplementation(async (params) => {
      if (params?.search === LOST) {
        return { items: count ? [lostVideo(21)] : [], total: count, page: 1, page_size: 100 }
      }
      return { items: [makeVideo({ id: 1 })], total: 1, page: 1, page_size: 20 }
    })
  }

  beforeEach(() => {
    vi.useRealTimers()
    vi.mocked(listVideos).mockReset()
    vi.mocked(listSources).mockResolvedValue([])
    vi.mocked(listTags).mockResolvedValue([])
    vi.mocked(getContinueList).mockResolvedValue([])
    vi.mocked(listSeriesProgress).mockResolvedValue([])
    vi.mocked(deleteVideo).mockReset()
    vi.mocked(deleteVideo).mockResolvedValue(undefined)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
  })

  it('counts the lost rows and offers the way to them', async () => {
    libraryWithLost(3)
    const { wrapper } = await mountHome()

    expect(vi.mocked(listVideos)).toHaveBeenCalledWith({ search: LOST, page: 1, page_size: 1 })
    const bar = wrapper.get('.missing-bar')
    expect(bar.get('.missing-text strong').text()).toBe('3 个文件已不在磁盘上')
    expect(bar.text()).toContain('等挂载回来重新扫描会自动恢复')
    wrapper.unmount()
  })

  it('stays out of the way while nothing is lost', async () => {
    libraryWithLost(0)
    const { wrapper } = await mountHome()

    expect(wrapper.find('.missing-bar').exists()).toBe(false)
    wrapper.unmount()
  })

  it('points the search box at the operator instead of adding a filter', async () => {
    libraryWithLost(3)
    const { wrapper } = await mountHome()

    await wrapper.get('.missing-actions button').trigger('click')
    await flushPromises()

    expect(wrapper.find('input').element.value).toBe(LOST)
    expect(lastQuery()).toMatchObject({ search: LOST, page: 1 })
    wrapper.unmount()
  })

  it('deletes every lost record through the ordinary endpoint', async () => {
    libraryWithLost(1)
    const { wrapper } = await mountHome()

    await wrapper.findAll('.missing-actions button')[1].trigger('click')
    await flushPromises()

    expect(deleteVideo).toHaveBeenCalledTimes(1)
    expect(deleteVideo).toHaveBeenCalledWith(21)
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 条丢失记录')
    wrapper.unmount()
  })

  it('keeps every record when the confirmation is declined', async () => {
    libraryWithLost(1)
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))
    const { wrapper } = await mountHome()

    await wrapper.findAll('.missing-actions button')[1].trigger('click')
    await flushPromises()

    expect(deleteVideo).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('Home filter state in the address bar', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.mocked(listVideos).mockReset()
    vi.mocked(listVideos).mockResolvedValue({
      items: [makeVideo({ id: 1 })],
      total: 60,
      page: 1,
      page_size: 20,
    })
    vi.mocked(listSources).mockResolvedValue([makeSource({ id: 3, name: '剧集' })])
    vi.mocked(listTags).mockResolvedValue([makeTag(7, '悬疑')])
    vi.mocked(getContinueList).mockResolvedValue([])
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('restores every filter from a shared link', async () => {
    const { wrapper } = await mountHome('/?q=%20暗涌%20&source=3&tag=7&page=2&size=40')

    expect(lastQuery()).toMatchObject({
      search: '暗涌',
      source_id: 3,
      tag_id: 7,
      page: 2,
      page_size: 40,
    })
    expect(wrapper.find('input').element.value).toBe('暗涌')
    wrapper.unmount()
  })

  it('falls back to the defaults for nonsense in the query', async () => {
    const { wrapper } = await mountHome('/?page=abc&size=-5')

    expect(lastQuery()).toMatchObject({ page: 1, page_size: 20 })
    expect(wrapper.find('input').element.value).toBe('')
    wrapper.unmount()
  })

  it('keeps the address bar in step with the tag filter', async () => {
    const { wrapper, router } = await mountHome()

    const tagSelect = wrapper.findAllComponents(ElSelect)[1]
    tagSelect.vm.$emit('update:modelValue', 7)
    await flushPromises()
    tagSelect.vm.$emit('change', 7)
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ tag: '7' })
    wrapper.unmount()
  })

  it('reloads from the address bar when 后退 restores another filter', async () => {
    const { wrapper, router } = await mountHome()
    const callsBefore = vi.mocked(listVideos).mock.calls.length

    await router.push({ query: { q: '星汉' } })
    await flushPromises()

    expect(vi.mocked(listVideos).mock.calls.length).toBe(callsBefore + 1)
    expect(lastQuery()).toMatchObject({ search: '星汉', page: 1 })
    expect(wrapper.find('input').element.value).toBe('星汉')
    wrapper.unmount()
  })

  it('does not reload for the query it wrote itself', async () => {
    const { wrapper, router } = await mountHome()

    const tagSelect = wrapper.findAllComponents(ElSelect)[1]
    tagSelect.vm.$emit('update:modelValue', 7)
    await flushPromises()
    tagSelect.vm.$emit('change', 7)
    await flushPromises()
    const calls = vi.mocked(listVideos).mock.calls.length

    await router.replace({ query: router.currentRoute.value.query })
    await flushPromises()

    expect(vi.mocked(listVideos).mock.calls.length).toBe(calls)
    wrapper.unmount()
  })
})

describe('Home search shortcut', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.mocked(listVideos).mockResolvedValue({ items: [makeVideo({ id: 1 })], total: 1, page: 1, page_size: 20 })
    vi.mocked(listSources).mockResolvedValue([])
    vi.mocked(listTags).mockResolvedValue([])
    vi.mocked(getContinueList).mockResolvedValue([])
  })

  it('focuses the search box on "/" and leaves other keys alone', async () => {
    const { wrapper } = await mountHome()
    const input = wrapper.find('input').element as HTMLInputElement

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'j' }))
    await flushPromises()
    expect(document.activeElement).not.toBe(input)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: '/' }))
    await flushPromises()
    expect(document.activeElement).toBe(input)
    wrapper.unmount()
  })

  it('ignores "/" typed inside the search box itself', async () => {
    const { wrapper } = await mountHome()
    const input = wrapper.find('input').element as HTMLInputElement

    input.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true }))
    await flushPromises()

    expect(document.activeElement).not.toBe(input)
    wrapper.unmount()
  })

  it('stops listening once the page unmounts', async () => {
    const { wrapper } = await mountHome()
    const input = wrapper.find('input').element as HTMLInputElement
    wrapper.unmount()

    document.dispatchEvent(new KeyboardEvent('keydown', { key: '/' }))
    await flushPromises()

    expect(document.activeElement).not.toBe(input)
  })
})
