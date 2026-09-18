import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sources from '@/views/Sources.vue'
import SourceCard from '@/components/SourceCard.vue'
import { deleteSource, listSources } from '@/api/sources'
import { makeSource } from '../factories'
import { buttonByText, CONFIRMED } from '../helpers'

const client = vi.hoisted(() => ({
  posts: [] as { url: string; data?: unknown }[],
  failWith: null as string | null,
}))

vi.mock('@/api/client', () => ({
  default: {
    post: (url: string, data?: unknown) => {
      client.posts.push({ url, data })
      if (client.failWith) return Promise.reject(new Error(client.failWith))
      if (url === '/scan/all') {
        return Promise.resolve({ data: { sources_scanned: 2, total_files: 9, total_new_videos: 3 } })
      }
      return Promise.resolve({ data: { files_found: 4, new_videos: 1 } })
    },
  },
}))

vi.mock('@/api/sources', () => ({
  listSources: vi.fn(),
  createSource: vi.fn(),
  updateSource: vi.fn(),
  deleteSource: vi.fn(),
}))

async function mountSources() {
  const wrapper = mount(Sources)
  await flushPromises()
  return wrapper
}

describe('Sources view', () => {
  beforeEach(() => {
    client.posts.length = 0
    vi.mocked(listSources).mockResolvedValue([makeSource({ id: 3, name: '测试视频源' })])
    vi.mocked(deleteSource).mockResolvedValue(undefined)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('lists the configured sources as cards', async () => {
    const wrapper = await mountSources()

    expect(listSources).toHaveBeenCalled()
    expect(wrapper.findAllComponents(SourceCard)).toHaveLength(1)
    expect(wrapper.text()).toContain('测试视频源')
    wrapper.unmount()
  })

  it('triggers a full scan through the scan endpoint', async () => {
    const wrapper = await mountSources()

    await buttonByText(wrapper, '扫描全部').trigger('click')
    await flushPromises()

    expect(client.posts).toContainEqual({ url: '/scan/all', data: undefined })
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('9 个文件'))
    wrapper.unmount()
  })

  it('scans a single source from its card', async () => {
    const wrapper = await mountSources()

    wrapper.findComponent(SourceCard).vm.$emit('scan', makeSource({ id: 3, name: '测试视频源' }))
    await flushPromises()

    expect(client.posts).toContainEqual({ url: '/sources/3/scan', data: undefined })
    expect(ElMessage.success).toHaveBeenCalledWith(expect.stringContaining('测试视频源'))
    wrapper.unmount()
  })

  it('deletes a source only after confirmation', async () => {
    const wrapper = await mountSources()

    wrapper.findComponent(SourceCard).vm.$emit('delete', makeSource({ id: 3, name: '测试视频源' }))
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(deleteSource).toHaveBeenCalledWith(3)
    expect(listSources).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('keeps the source list untouched when the delete dialog is dismissed', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const wrapper = await mountSources()

    wrapper.findComponent(SourceCard).vm.$emit('delete', makeSource({ id: 3 }))
    await flushPromises()

    expect(deleteSource).not.toHaveBeenCalled()
    expect(ElMessage.error).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('surfaces a failed scan as an error toast', async () => {
    const wrapper = await mountSources()

    client.failWith = '目录不存在'
    await buttonByText(wrapper, '扫描全部').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('目录不存在'))
    wrapper.unmount()
  })
})
