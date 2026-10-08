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
  products: [] as Record<string, unknown>[],
  // 拦截器（src/api/client.ts）在服务端返回 detail 时 reject 的是一个新的
  // Error，只留一句人话，不再带 response。替身照这个形状失败，用例才测得到
  // 视图有没有把那句原因显示出来。
  failGet: [] as { on: string; message: string }[],
  failPost: [] as { on: string; message: string }[],
}))

function rejectionFor(table: { on: string; message: string }[], url: string) {
  return table.find((entry) => url.includes(entry.on))?.message ?? null
}

vi.mock('@/api/client', () => ({
  default: {
    get: (url: string) => {
      env.get.push(url)
      const failure = rejectionFor(env.failGet, url)
      if (failure) return Promise.reject(new Error(failure))
      if (url === '/transcode/formats') return Promise.resolve({ data: env.formats })
      if (url.endsWith('/outputs')) return Promise.resolve({ data: env.products })
      if (url.endsWith('/status')) return Promise.resolve({ data: env.status })
      return Promise.resolve({ data: env.video })
    },
    post: (url: string, data?: unknown) => {
      env.post.push({ url, data })
      const failure = rejectionFor(env.failPost, url)
      if (failure) return Promise.reject(new Error(failure))
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
    env.failGet = []
    env.failPost = []
    env.formats = [{ format: 'webm', codec: 'libvpx-vp9', extension: 'webm' }]
    env.products = []
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

  it('requests the video, formats, status and products through the proxied api paths', async () => {
    const wrapper = mount(Transcode)
    await flushPromises()

    expect(env.get).toEqual([
      '/videos/7',
      '/transcode/formats',
      '/transcode/7/status',
      '/transcode/7/outputs',
    ])
    expect(wrapper.text()).toContain('深夜测试.mp4')
    wrapper.unmount()
  })

  it('lists a product with its size and where it landed', async () => {
    env.products = [
      {
        id: 3,
        target_format: 'mkv',
        output_path: 'D:\\transcode\\7\\深夜测试.mkv',
        size_bytes: 1_572_864,
        created_at: '2026-10-08T03:00:00+00:00',
        deleted_at: null,
      },
    ]

    const wrapper = mount(Transcode)
    await flushPromises()

    const row = wrapper.find('.products-section .el-table__body tr')
    expect(row.text()).toContain('MKV')
    expect(row.text()).toContain('深夜测试.mkv')
    expect(row.text()).toContain('1.5 MB')
    expect(row.text()).toContain('在磁盘上')
    wrapper.unmount()
  })

  it('says 已不在 for a product whose file is gone instead of hiding the row', async () => {
    env.products = [
      {
        id: 3,
        target_format: 'mkv',
        output_path: 'D:\\transcode\\7\\深夜测试.mkv',
        size_bytes: null,
        created_at: '2026-10-08T03:00:00+00:00',
        deleted_at: '2026-10-08T04:00:00+00:00',
      },
    ]

    const wrapper = mount(Transcode)
    await flushPromises()

    const row = wrapper.find('.products-section .el-table__body tr')
    expect(row.text()).toContain('已不在')
    // 大小那一格只能是一个破折号：库里那份数字已经不作数了
    expect(row.text()).toContain('—')
    wrapper.unmount()
  })

  it('shows an empty product table rather than pretending nothing exists', async () => {
    const wrapper = mount(Transcode)
    await flushPromises()

    expect(wrapper.find('.products-section').text()).toContain('还没有转码产物')
    wrapper.unmount()
  })

  it('says why the product list is empty when the endpoint fails', async () => {
    env.failGet = [{ on: '/outputs', message: '产物表读取失败' }]

    const wrapper = mount(Transcode)
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('产物表读取失败'))
    wrapper.unmount()
  })

  it('re-reads the products when a polled job completes', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running' })
    vi.useFakeTimers()

    const wrapper = mount(Transcode)
    await flushPromises()
    expect(env.get.filter((url) => url.endsWith('/outputs'))).toHaveLength(1)

    env.status = idleStatus({ status: 'completed', target_format: 'mkv' })
    await vi.advanceTimersByTimeAsync(1500)

    // 那一行是任务成功那一刻才写进库的，不重读就得刷新页面才看得到
    expect(env.get.filter((url) => url.endsWith('/outputs'))).toHaveLength(2)
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

  it('shows the server reason when the video cannot be loaded', async () => {
    env.failGet = [{ on: '/videos/', message: '视频不存在' }]

    const wrapper = mount(Transcode)
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('视频不存在'))
    wrapper.unmount()
  })

  it('says why the format list is empty instead of only logging it', async () => {
    env.failGet = [{ on: '/transcode/formats', message: '转码服务未就绪' }]

    const wrapper = mount(Transcode)
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('转码服务未就绪'))
    wrapper.unmount()
  })

  it('toasts the reason once when the very first status request fails', async () => {
    env.failGet = [{ on: '/status', message: '请求超时' }]

    const wrapper = mount(Transcode)
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledTimes(1)
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('请求超时'))
    expect(wrapper.find('.status-fetch-error').text()).toBe('请求超时')
    wrapper.unmount()
  })

  it('keeps a polling failure on the panel instead of stacking toasts', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running' })
    vi.useFakeTimers()

    const wrapper = mount(Transcode)
    await flushPromises()
    expect(ElMessage.error).not.toHaveBeenCalled()

    env.failGet = [{ on: '/status', message: '转码服务无响应' }]
    await vi.advanceTimersByTimeAsync(1500)
    await vi.advanceTimersByTimeAsync(1500)

    // 轮询每 1.5 秒一次，每失败一次弹一层 toast 就会把屏幕刷成一堵墙
    expect(ElMessage.error).not.toHaveBeenCalled()
    expect(wrapper.find('.status-fetch-error').text()).toBe('转码服务无响应')
    wrapper.unmount()
  })

  it('clears the status failure line once the poll answers again', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running' })
    vi.useFakeTimers()

    const wrapper = mount(Transcode)
    await flushPromises()

    env.failGet = [{ on: '/status', message: '转码服务无响应' }]
    await vi.advanceTimersByTimeAsync(1500)
    expect(wrapper.find('.status-fetch-error').exists()).toBe(true)

    env.failGet = []
    await vi.advanceTimersByTimeAsync(1500)
    expect(wrapper.find('.status-fetch-error').exists()).toBe(false)
    wrapper.unmount()
  })

  it('surfaces the server reason when starting a transcode is refused', async () => {
    env.failPost = [{ on: '/transcode/7', message: '源文件已不在原路径' }]

    const wrapper = mount(Transcode)
    await flushPromises()

    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 'webm')
    await flushPromises()
    await buttonByText(wrapper, '开始转码').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('源文件已不在原路径')
    wrapper.unmount()
  })

  it('surfaces the server reason when cancelling is refused', async () => {
    env.status = idleStatus({ is_transcoding: true, status: 'running' })
    env.failPost = [{ on: '/transcode/7/cancel', message: '当前没有正在进行的转码任务' }]

    const wrapper = mount(Transcode)
    await flushPromises()

    await buttonByText(wrapper, '取消转码').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('当前没有正在进行的转码任务')
    wrapper.unmount()
  })
})
