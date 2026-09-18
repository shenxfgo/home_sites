import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox, ElProgress, ElSelect } from 'element-plus'
import Transcode from '@/views/Transcode.vue'
import { buttonByText, CONFIRMED } from '../helpers'

const env = vi.hoisted(() => ({
  get: [] as string[],
  post: [] as { url: string; data?: unknown }[],
  video: null as Record<string, unknown> | null,
  status: null as Record<string, unknown> | null,
  formats: [] as Record<string, unknown>[],
}))

vi.mock('@/api/client', () => ({
  default: {
    get: (url: string) => {
      env.get.push(url)
      if (url === '/transcode/formats') return Promise.resolve({ data: env.formats })
      if (url.endsWith('/status')) return Promise.resolve({ data: env.status })
      return Promise.resolve({ data: env.video })
    },
    post: (url: string, data?: unknown) => {
      env.post.push({ url, data })
      return Promise.resolve({ data: {} })
    },
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '7' } }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}))

function idleStatus(overrides: Record<string, unknown> = {}) {
  return {
    video_id: 7,
    is_transcoding: false,
    status: 'idle',
    progress: 0,
    target_format: null,
    output_path: null,
    error: null,
    ...overrides,
  }
}

describe('Transcode view', () => {
  beforeEach(() => {
    env.get = []
    env.post = []
    env.formats = [{ format: 'webm', codec: 'libvpx-vp9', extension: 'webm' }]
    env.video = {
      id: 7,
      title: '深夜测试',
      filepath: 'D:\\videos\\深夜测试.mp4',
      format: 'mp4',
      duration: 5,
    }
    env.status = idleStatus()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('requests the video, formats and status through the proxied api paths', async () => {
    const wrapper = mount(Transcode)
    await flushPromises()

    expect(env.get).toEqual(['/videos/7', '/transcode/formats', '/transcode/7/status'])
    expect(wrapper.text()).toContain('深夜测试.mp4')
    wrapper.unmount()
  })

  it('shows a live progress bar and keeps polling while the job runs', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running', progress: 33, target_format: 'webm' })
    vi.useFakeTimers()

    const wrapper = mount(Transcode)
    await flushPromises()

    expect(wrapper.findComponent(ElProgress).props('percentage')).toBe(33)
    expect(wrapper.text()).toContain('转码中')

    env.status = idleStatus({ status: 'completed', target_format: 'webm' })
    await vi.advanceTimersByTimeAsync(1500)
    const statusCalls = env.get.filter((url) => url.endsWith('/status')).length
    expect(statusCalls).toBe(2)
    expect(ElMessage.success).toHaveBeenCalledWith('转码完成')

    await vi.advanceTimersByTimeAsync(5000)
    expect(env.get.filter((url) => url.endsWith('/status')).length).toBe(statusCalls)
    wrapper.unmount()
  })

  it('stops polling once the component unmounts', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running' })
    vi.useFakeTimers()

    const wrapper = mount(Transcode)
    await flushPromises()
    wrapper.unmount()

    await vi.advanceTimersByTimeAsync(5000)
    expect(env.get.filter((url) => url.endsWith('/status'))).toHaveLength(1)
  })

  it('reports the failure reason returned by the backend', async () => {
    env.status = idleStatus({ status: 'failed', error: 'WebM 不支持 aac 音频编码器' })

    const wrapper = mount(Transcode)
    await flushPromises()

    expect(wrapper.find('.status-error').text()).toBe('WebM 不支持 aac 音频编码器')
    expect(wrapper.text()).toContain('失败')
    wrapper.unmount()
  })

  it('posts the chosen format to the transcode endpoint after confirmation', async () => {
    const wrapper = mount(Transcode)
    await flushPromises()

    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 'webm')
    await flushPromises()
    await buttonByText(wrapper, '开始转码').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(env.post).toEqual([{ url: '/transcode/7', data: { target_format: 'webm' } }])
    wrapper.unmount()
  })

  it('refuses to start a transcode without a target format', async () => {
    const wrapper = mount(Transcode)
    await flushPromises()

    await buttonByText(wrapper, '开始转码').trigger('click')
    await flushPromises()

    expect(ElMessage.warning).toHaveBeenCalledWith('请选择目标格式')
    expect(env.post).toEqual([])
    wrapper.unmount()
  })

  it('sends nothing when the confirmation dialog is dismissed', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const wrapper = mount(Transcode)
    await flushPromises()

    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 'webm')
    await flushPromises()
    await buttonByText(wrapper, '开始转码').trigger('click')
    await flushPromises()

    expect(env.post).toEqual([])
    expect(ElMessage.error).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('cancels a running job through the cancel endpoint', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running', progress: 12 })
    const wrapper = mount(Transcode)
    await flushPromises()

    await buttonByText(wrapper, '取消转码').trigger('click')
    await flushPromises()

    expect(env.post).toContainEqual({ url: '/transcode/7/cancel', data: undefined })
    expect(ElMessage.success).toHaveBeenCalledWith('转码已取消')
    wrapper.unmount()
  })

  it('disables the start button while a job is already running', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running' })

    const wrapper = mount(Transcode)
    await flushPromises()

    expect(buttonByText(wrapper, '开始转码').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
