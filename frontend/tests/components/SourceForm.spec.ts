/**
 * 新建片源那一格的默认间隔来自系统配置那张表（#151 甲）。这一层的活只有一件：
 * 把「配置里那个数」变成「界面上看得见、也发得出去的那个数」，而不是在这里再写
 * 一份 3600——从前这同一个数字有三句话（这里的初值、后端建源时的默认、替身夹具里
 * 那句 `?? 3600`），改了设置页下拉一句也不生效。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElInputNumber, ElMessage } from 'element-plus'
import SourceForm from '@/components/SourceForm.vue'
import { getSettings } from '@/api/settings'
import type { Settings } from '@/api/settings'
import { makeSource } from '../factories'

vi.mock('@/api/settings', () => ({ getSettings: vi.fn() }))

const CONFIGURED: Settings = {
  auto_scan_enabled: true,
  auto_scan_interval: 900,
  default_transcode_format: 'mp4',
  thumbnail_width: 320,
  thumbnail_height: 180,
}

async function mountForm(props: Record<string, unknown> = {}) {
  const wrapper = mount(SourceForm, {
    props: { visible: false, ...props },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

/** 真用户的走法：页面先 mount 好对话框（关着的），点「添加视频源」才把它打开。 */
async function openForm(props: Record<string, unknown> = {}) {
  const wrapper = await mountForm(props)
  await wrapper.setProps({ visible: true })
  await flushPromises()
  return wrapper
}

describe('SourceForm 的默认扫描间隔', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockResolvedValue({ ...CONFIGURED })
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('对话框没打开时不去读配置', async () => {
    const wrapper = await mountForm()

    expect(getSettings).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('新建时那一格预填配置里的间隔', async () => {
    const wrapper = await openForm()

    expect(getSettings).toHaveBeenCalledTimes(1)
    expect(wrapper.findComponent(ElInputNumber).props('modelValue')).toBe(900)
    wrapper.unmount()
  })

  it('编辑态用的是这条源自己的间隔，一次配置也不读', async () => {
    const wrapper = await openForm({ source: makeSource({ id: 3, scan_interval: 7200 }) })

    expect(getSettings).not.toHaveBeenCalled()
    expect(wrapper.findComponent(ElInputNumber).props('modelValue')).toBe(7200)
    wrapper.unmount()
  })

  it('配置读不到就把格子留空，并说出原因', async () => {
    vi.mocked(getSettings).mockRejectedValue(new Error('仅管理员可读系统配置'))
    const wrapper = await openForm()

    // 留空不是将就：那条 required 规则会拦住提交，于是发出去的是一个没人猜的数字的
    // 缺席，而不是一个界面上一度显示过、后端却没配过的间隔。
    expect(wrapper.findComponent(ElInputNumber).props('modelValue')).toBeUndefined()
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('仅管理员可读系统配置'))
    wrapper.unmount()
  })

  it('配置读得慢时也不盖掉已经填好的那一格', async () => {
    let release: (value: Settings) => void = () => {}
    vi.mocked(getSettings).mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }),
    )
    const wrapper = await openForm()

    wrapper.findComponent(ElInputNumber).vm.$emit('update:modelValue', 1800)
    await flushPromises()
    release({ ...CONFIGURED, auto_scan_interval: 900 })
    await flushPromises()

    expect(wrapper.findComponent(ElInputNumber).props('modelValue')).toBe(1800)
    wrapper.unmount()
  })
})
