import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElSelect } from 'element-plus'
import Home from '@/views/Home.vue'
import VideoCard from '@/components/VideoCard.vue'
import { listVideos } from '@/api/videos'
import { listSources } from '@/api/sources'
import { listTags } from '@/api/tags'
import { makeSource, makeTag, makeVideo } from '../factories'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/api/videos', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/videos')>()
  return { ...actual, listVideos: vi.fn() }
})
vi.mock('@/api/sources', () => ({ listSources: vi.fn() }))
vi.mock('@/api/tags', () => ({ listTags: vi.fn() }))

async function mountHome() {
  const wrapper = mount(Home)
  await flushPromises()
  return wrapper
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
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('loads the library together with both filter lists', async () => {
    const wrapper = await mountHome()

    expect(lastQuery()).toMatchObject({ page: 1, page_size: 20 })
    expect(wrapper.findAllComponents(VideoCard)).toHaveLength(1)
    expect(listSources).toHaveBeenCalledWith(true)
    expect(listTags).toHaveBeenCalled()
    expect(wrapper.findAllComponents(ElSelect)).toHaveLength(2)
    wrapper.unmount()
  })

  it('sends the trimmed keyword after the debounce', async () => {
    vi.useFakeTimers()
    const wrapper = mount(Home)
    await flushPromises()

    const input = wrapper.find('input')
    await input.setValue('  暗涌 第一季 ')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()

    expect(lastQuery()).toMatchObject({ search: '暗涌 第一季' })
    wrapper.unmount()
  })

  it('passes the chosen tag to the api and restarts pagination', async () => {
    const wrapper = await mountHome()
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
    const wrapper = await mountHome()

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
    const wrapper = await mountHome()

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
    const wrapper = await mountHome()

    expect(wrapper.text()).toContain('添加视频源并扫描即可开始使用')
    expect(wrapper.find('.empty-clear').exists()).toBe(false)
    wrapper.unmount()
  })
})
