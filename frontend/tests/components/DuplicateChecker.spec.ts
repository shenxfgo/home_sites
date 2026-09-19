import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import DuplicateChecker from '@/components/DuplicateChecker.vue'
import { deleteVideo, listDuplicates } from '@/api/videos'
import { makeDuplicateGroup, makeVideo } from '../factories'
import { buttonByText, CONFIRMED } from '../helpers'

vi.mock('@/api/videos', () => ({
  listDuplicates: vi.fn(),
  deleteVideo: vi.fn(),
}))

async function mountChecker() {
  const wrapper = mount(DuplicateChecker)
  await flushPromises()
  return wrapper
}

async function runCheck(wrapper: Awaited<ReturnType<typeof mountChecker>>) {
  await buttonByText(wrapper, '开始检测').trigger('click')
  await flushPromises()
  return wrapper
}

/** Click the button carrying ``label`` inside one row of the report. */
async function clickInRow(
  wrapper: Awaited<ReturnType<typeof mountChecker>>,
  row: number,
  label: string,
) {
  const node = wrapper.findAll('.dup-item')[row]
  const button = node.findAll('button').find((b) => b.text().includes(label))
  if (!button) throw new Error(`第 ${row} 行没有 "${label}" 按钮`)
  await button.trigger('click')
  await flushPromises()
}

describe('DuplicateChecker', () => {
  beforeEach(() => {
    vi.mocked(listDuplicates).mockResolvedValue([makeDuplicateGroup()])
    vi.mocked(deleteVideo).mockResolvedValue(undefined)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(CONFIRMED)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  })

  it('only reads the library when the user asks for it', async () => {
    const wrapper = await mountChecker()

    expect(listDuplicates).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('重复文件检测')

    await runCheck(wrapper)

    expect(listDuplicates).toHaveBeenCalledTimes(1)
  })

  it('lists every confirmed copy with the bytes it costs', async () => {
    const wrapper = await runCheck(await mountChecker())

    expect(wrapper.findAll('.dup-item')).toHaveLength(2)
    expect(wrapper.find('.dup-summary').text()).toContain('1 组重复')
    expect(wrapper.find('.dup-summary').text()).toContain('1.00 GB')
    expect(wrapper.text()).toContain('D:\\videos\\备份\\午夜列车.mkv')
  })

  it('marks the copy with the watch history as the one to keep', async () => {
    const wrapper = await runCheck(await mountChecker())

    const kept = wrapper.findAll('.dup-item')[0]
    expect(kept.text()).toContain('建议保留')
    expect(kept.text()).toContain('午夜列车')
    expect(wrapper.findAll('.dup-item')[1].find('.keep-tag').exists()).toBe(false)
  })

  it('says so when nothing matched', async () => {
    vi.mocked(listDuplicates).mockResolvedValue([])
    const wrapper = await runCheck(await mountChecker())

    expect(wrapper.find('.dup-group').exists()).toBe(false)
    expect(wrapper.text()).toContain('没有发现内容完全相同的文件')
    expect(buttonByText(wrapper, '重新检测').exists()).toBe(true)
  })

  it('surfaces a failed check as an error toast', async () => {
    vi.mocked(listDuplicates).mockRejectedValue(new Error('共享盘没有挂载'))
    const wrapper = await mountChecker()

    await buttonByText(wrapper, '开始检测').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining('共享盘没有挂载'))
    expect(wrapper.find('.dup-empty').exists()).toBe(false)
  })

  it('removes one record after asking, then drops the group left with a single copy', async () => {
    const wrapper = await runCheck(await mountChecker())

    await clickInRow(wrapper, 1, '移除记录')

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining('磁盘上的文件不会被动'),
      expect.any(String),
      expect.any(Object),
    )
    expect(deleteVideo).toHaveBeenCalledWith(22)
    expect(wrapper.findAll('.dup-group')).toHaveLength(0)
    expect(ElMessage.success).toHaveBeenCalledWith('已移除这条记录')
  })

  it('keeps the suggested copy when the dialog is dismissed', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const wrapper = await runCheck(await mountChecker())

    await clickInRow(wrapper, 0, '移除记录')

    expect(deleteVideo).not.toHaveBeenCalled()
    expect(wrapper.findAll('.dup-item')).toHaveLength(2)
  })

  it('clears the extra copies of a group in one go', async () => {
    const wrapper = await runCheck(await mountChecker())

    await buttonByText(wrapper, '移除多余记录').trigger('click')
    await flushPromises()

    expect(deleteVideo).toHaveBeenCalledTimes(1)
    expect(deleteVideo).toHaveBeenCalledWith(22)
    expect(ElMessage.success).toHaveBeenCalledWith('已移除 1 条重复记录')
    // One copy left is no longer a duplicate, so the group drops out.
    expect(wrapper.findAll('.dup-group')).toHaveLength(0)
  })

  it('recounts what is still on the shelf after a removal', async () => {
    vi.mocked(listDuplicates).mockResolvedValue([
      makeDuplicateGroup({
        count: 3,
        wasted_bytes: 2 * 1024 * 1024 * 1024,
        items: [
          makeVideo({ id: 21, title: '午夜列车' }),
          makeVideo({ id: 22, title: '午夜列车 备份' }),
          makeVideo({ id: 23, title: '午夜列车 又一份' }),
        ],
      }),
    ])
    const wrapper = await runCheck(await mountChecker())
    expect(wrapper.find('.dup-summary').text()).toContain('2.00 GB')

    await clickInRow(wrapper, 2, '移除记录')

    expect(wrapper.findAll('.dup-item')).toHaveLength(2)
    expect(wrapper.find('.dup-summary').text()).toContain('1.00 GB')
    expect(wrapper.find('.keep-tag').text()).toContain('建议保留')
  })
})
