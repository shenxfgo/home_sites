/**
 * 系统配置页（`views/Settings.vue`）的单元层用例。
 *
 * 这一页此前两层都没有用例（14 个视图里只剩它一个）。它偏偏又是一份**整表读写**的界面：
 * `PUT /api/settings` 的请求模型五个字段全都带默认值，少传一个 Pydantic 就替它填上，
 * 服务端再把五个一起写库——后端那条 `test_a_bulk_put_that_omits_a_key_resets_it` 钉的就是
 * 「漏一个键不是那个键不动，是回到代码默认值」。界面每次都发全五项才碰不到这件事，
 * 而"每次都发全五项"此前一句也没有签过字。
 *
 * 单元层在这里独占的是**能指定服务器回什么**：真库那 18 条里设置页读到的就是库里那份，
 * 指不出「服务器回了一个界面不认识的值」这种形状（下面第 2、4、5 条）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import Settings from '@/views/Settings.vue'
import { getSettings, updateSettings, type Settings as SystemSettings } from '@/api/settings'
import { buttonByText } from '../helpers'

vi.mock('@/api/settings', () => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}))

/** `Settings.vue` 那份 ref 的初始值——也就是"一次也没读进来"时页面会显示的东西。 */
const INITIAL: SystemSettings = {
  auto_scan_enabled: true,
  auto_scan_interval: 3600,
  default_transcode_format: 'mp4',
  thumbnail_width: 320,
  thumbnail_height: 180,
}

/** 和初始值逐项都不同的服务器答案，这样"显示的是服务器那份"才量得出来。 */
const FROM_SERVER: SystemSettings = {
  auto_scan_enabled: false,
  auto_scan_interval: 7200,
  default_transcode_format: 'webm',
  thumbnail_width: 640,
  thumbnail_height: 480,
}

async function mountSettings(answer: SystemSettings | Error = FROM_SERVER) {
  if (answer instanceof Error) vi.mocked(getSettings).mockRejectedValue(answer)
  else vi.mocked(getSettings).mockResolvedValue(answer)

  const wrapper = mount(Settings, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

function field(wrapper: VueWrapper, label: string) {
  const found = wrapper
    .findAll('.el-form-item')
    .find((node) => node.find('.el-form-item__label').text() === label)
  if (!found) throw new Error(`找不到标签为 "${label}" 的表单项`)
  return found
}

/** `el-input-number` 把值放在原生 input 里。 */
function numberValue(wrapper: VueWrapper, label: string) {
  return (field(wrapper, label).find('input').element as HTMLInputElement).value
}

function switchIsChecked(wrapper: VueWrapper) {
  return field(wrapper, '自动扫描').find('.el-switch').classes().includes('is-checked')
}

describe('Settings view', () => {
  beforeEach(() => {
    vi.mocked(updateSettings).mockResolvedValue(FROM_SERVER)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('renders the five values the server answered, not the ref defaults', async () => {
    const wrapper = await mountSettings()

    // 间隔与格式显示的是选项的 label，数字键在 input 里，开关是一个 class。
    expect(field(wrapper, '扫描间隔').text()).toContain('每 2 小时')
    expect(field(wrapper, '默认转码格式').text()).toContain('WebM (VP9)')
    expect(numberValue(wrapper, '缩略图宽度')).toBe('640')
    expect(numberValue(wrapper, '缩略图高度')).toBe('480')
    expect(switchIsChecked(wrapper)).toBe(false)
    // 这一句是反面：初始值恰好是「每小时」，读进来这一步没做的话这里才会绿。
    expect(field(wrapper, '扫描间隔').text()).not.toContain('每小时')
    wrapper.unmount()
  })

  it('shows a stored value the option list does not offer, as-is', async () => {
    // 单键 `PUT /api/settings/{key}` 允许任何整数，所以库里完全可能存着一个界面选项
    // 列表里没有的间隔；`default_transcode_format` 那一键后端连值都不校验。
    const wrapper = await mountSettings({
      ...FROM_SERVER,
      auto_scan_interval: 600,
      default_transcode_format: 'divx',
    })

    // 界面不许把它悄悄显示成列表里的某一项——那会让人以为保存会把它换成那一项。
    expect(field(wrapper, '扫描间隔').text()).toContain('600')
    expect(field(wrapper, '扫描间隔').text()).not.toContain('每小时')
    expect(field(wrapper, '默认转码格式').text()).toContain('divx')
    wrapper.unmount()
  })

  it('posts all five keys on save even when nothing was touched', async () => {
    const wrapper = await mountSettings()

    await buttonByText(wrapper, '保存设置').trigger('click')
    await flushPromises()

    // 「一个控件也没动」是最强的一次：发出去的 body 必须是全五项，而不是差量。
    expect(updateSettings).toHaveBeenCalledTimes(1)
    expect(vi.mocked(updateSettings).mock.calls[0][0]).toEqual(FROM_SERVER)
    expect(ElMessage.success).toHaveBeenCalledWith('设置已保存')
    wrapper.unmount()
  })

  it('sends the edited number through the rest of the payload untouched', async () => {
    // 改一格、另外四格必须跟着人此刻看到的那份走。`INITIAL` 与 `FROM_SERVER` 逐项都不
    // 相等，所以"漏抄初始 ref"在这里会露出来。
    const wrapper = await mountSettings()

    const width = field(wrapper, '缩略图宽度').find('input')
    await width.setValue('800')
    await width.trigger('blur')
    await flushPromises()

    await buttonByText(wrapper, '保存设置').trigger('click')
    await flushPromises()

    expect(vi.mocked(updateSettings).mock.calls[0][0]).toEqual({
      ...FROM_SERVER,
      thumbnail_width: 800,
    })
    wrapper.unmount()
  })

  it('quotes the server when the save is rejected and claims nothing', async () => {
    vi.mocked(updateSettings).mockRejectedValue(new Error('需要管理员权限'))
    const wrapper = await mountSettings()

    await buttonByText(wrapper, '保存设置').trigger('click')
    await flushPromises()

    // #74 那一族：兜底常量会把服务端那句原因吃掉。
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('需要管理员权限'))
    expect(ElMessage.success).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('quotes the server when the initial read fails and leaves the form on its defaults', async () => {
    const wrapper = await mountSettings(new Error('服务未就绪'))

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('服务未就绪'))
    // 读失败时页面停在 ref 的初始值上：这一句是防止有人把 catch 写成"清空重来"。
    expect(field(wrapper, '扫描间隔').text()).toContain('每小时')
    expect(numberValue(wrapper, '缩略图宽度')).toBe(String(INITIAL.thumbnail_width))
    expect(updateSettings).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('disables the save button while the request is in flight', async () => {
    let settle: () => void = () => {}
    vi.mocked(updateSettings).mockImplementation(
      () => new Promise<void>((resolve) => (settle = resolve)) as never,
    )
    const wrapper = await mountSettings()

    await buttonByText(wrapper, '保存设置').trigger('click')
    await flushPromises()
    expect(buttonByText(wrapper, '保存设置').classes()).toContain('is-loading')

    settle?.()
    await flushPromises()
    expect(buttonByText(wrapper, '保存设置').classes()).not.toContain('is-loading')
    wrapper.unmount()
  })
})
